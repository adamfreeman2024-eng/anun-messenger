"""Blind relay. Stores opaque envelopes. Has no keys and no decrypt path."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hmac
import json
import re
import secrets
import struct
import threading
import time
from pathlib import Path

from spike.hopurl import allowed_hop_url

MAX_ENVELOPE = 64 * 1024
MAX_TTL = 7 * 24 * 3600
QUEUE_RE = re.compile(r"^[A-Za-z0-9_-]{32,64}$")


def _eq(left: str, right: str) -> bool:
    return hmac.compare_digest(left.encode(), right.encode())


class RelayStore:
    def __init__(self, path: Path, now_fn=time.time, max_ttl: int = MAX_TTL):
        self.path = path
        self.now_fn = now_fn
        self.max_ttl = max_ttl
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(exist_ok=True)
        self._lock = threading.Lock()
        self._queues: dict[str, list[tuple[bytes, float]]] = {}
        self._owner: dict[str, str] = {}
        self._invites: dict[str, str] = {}
        self._send: dict[str, str] = {}
        self._forwards: list[tuple[str, bytes]] = []

    def create_queue(self) -> tuple[str, str]:
        queue_id = secrets.token_urlsafe(32)
        owner = secrets.token_urlsafe(32)
        with self._lock:
            self._queues[queue_id] = []
            self._owner[queue_id] = owner
        return queue_id, owner

    def issue_invite(self, queue_id: str, owner_cap: str) -> str:
        with self._lock:
            if queue_id not in self._owner or not _eq(self._owner[queue_id], owner_cap):
                raise PermissionError("not owner")
            token = secrets.token_urlsafe(32)
            self._invites[token] = queue_id
        return token

    def redeem(self, token: str) -> tuple[str, str]:
        with self._lock:
            queue_id = self._invites.pop(token, None)
            if queue_id is None:
                raise PermissionError("invite used or unknown")
            send_cap = secrets.token_urlsafe(32)
            self._send[send_cap] = queue_id
        return queue_id, send_cap

    def put(self, queue_id: str, envelope: bytes, send_cap: str, ttl: int) -> None:
        if not QUEUE_RE.match(queue_id):
            raise KeyError("bad queue")
        if len(envelope) > MAX_ENVELOPE:
            raise ValueError("envelope too large")
        ttl = max(1, min(int(ttl), self.max_ttl))
        now = self.now_fn()
        with self._lock:
            if self._send.get(send_cap) != queue_id:
                raise PermissionError("bad send cap")
            self._drop_expired(now)
            self._queues[queue_id].append((envelope, now + ttl))
            self._rewrite()

    def take(self, queue_id: str, owner_cap: str) -> bytes | None:
        now = self.now_fn()
        with self._lock:
            if queue_id not in self._owner or not _eq(self._owner[queue_id], owner_cap):
                raise PermissionError("not owner")
            self._drop_expired(now)
            items = self._queues[queue_id]
            if not items:
                self._rewrite()
                return None
            blob, _expires = items.pop(0)
            self._rewrite()
            return blob

    def deposit(self, queue_id: str, envelope: bytes, ttl: int) -> None:
        """Dest relay only, after the hop wrapper is removed. Still not plaintext."""
        if queue_id not in self._queues:
            raise KeyError("unknown queue")
        if len(envelope) > MAX_ENVELOPE:
            raise ValueError("envelope too large")
        ttl = max(1, min(int(ttl), self.max_ttl))
        now = self.now_fn()
        with self._lock:
            self._drop_expired(now)
            self._queues[queue_id].append((envelope, now + ttl))
            self._rewrite()

    def hold_forward(self, dest_url: str, blob: bytes) -> None:
        allowed_hop_url(dest_url)
        if len(blob) > MAX_ENVELOPE:
            raise ValueError("envelope too large")
        with self._lock:
            self._forwards.append((dest_url, blob))

    def take_forwards(self) -> list[tuple[str, bytes]]:
        with self._lock:
            items = list(self._forwards)
            self._forwards.clear()
            return items

    def forward_bytes(self) -> bytes:
        with self._lock:
            return b"".join(url.encode() + b"\n" + blob for url, blob in self._forwards)

    def disk_bytes(self) -> bytes:
        return self.path.read_bytes()

    def _drop_expired(self, now: float) -> None:
        for queue_id, items in self._queues.items():
            self._queues[queue_id] = [item for item in items if item[1] > now]

    def _rewrite(self) -> None:
        chunks = []
        for items in self._queues.values():
            for blob, expires_at in items:
                chunks.append(struct.pack(">dI", expires_at, len(blob)) + blob)
        self.path.write_bytes(b"".join(chunks))


class RelayHandler(BaseHTTPRequestHandler):
    store: RelayStore

    def log_message(self, fmt: str, *args) -> None:
        return

    def _json(self, code: int, payload: dict) -> None:
        raw = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _read(self) -> bytes:
        length = int(self.headers.get("Content-Length", "0"))
        return self.rfile.read(length)

    def do_POST(self) -> None:
        if self.path == "/v1/queues":
            queue_id, owner = self.store.create_queue()
            self._json(201, {"queue_id": queue_id, "owner_cap": owner})
            return
        invite = re.fullmatch(r"/v1/queues/([^/]+)/invites", self.path)
        if invite:
            owner = self.headers.get("X-Anun-Owner", "")
            try:
                token = self.store.issue_invite(invite.group(1), owner)
            except PermissionError:
                self._json(401, {"error": "not owner"})
                return
            self._json(201, {"token": token})
            return
        if self.path == "/v1/invites/redeem":
            try:
                token = json.loads(self._read() or b"{}").get("token", "")
                queue_id, send_cap = self.store.redeem(str(token))
            except (PermissionError, json.JSONDecodeError):
                self._json(401, {"error": "invite used or unknown"})
                return
            self._json(200, {"queue_id": queue_id, "send_cap": send_cap})
            return
        if self.path == "/v1/forward":
            try:
                data = json.loads(self._read() or b"{}")
                self.store.hold_forward(str(data["dest"]), bytes.fromhex(data["blob_hex"]))
            except (KeyError, ValueError, json.JSONDecodeError):
                self._json(400, {"error": "bad forward"})
                return
            self._json(202, {"ok": True})
            return
        self._json(404, {"error": "not found"})

    def do_PUT(self) -> None:
        m = re.fullmatch(r"/v1/queues/([^/]+)", self.path)
        if not m:
            self._json(404, {"error": "not found"})
            return
        ttl = int(self.headers.get("X-Anun-TTL", "86400") or "86400")
        try:
            self.store.put(
                m.group(1),
                self._read(),
                self.headers.get("X-Anun-Send", ""),
                ttl,
            )
        except PermissionError:
            self._json(401, {"error": "bad send cap"})
            return
        except KeyError:
            self._json(404, {"error": "unknown queue"})
            return
        except ValueError:
            self._json(413, {"error": "too large"})
            return
        self.send_response(204)
        self.end_headers()

    def do_GET(self) -> None:
        m = re.fullmatch(r"/v1/queues/([^/]+)", self.path)
        if not m:
            self._json(404, {"error": "not found"})
            return
        try:
            envelope = self.store.take(m.group(1), self.headers.get("X-Anun-Owner", ""))
        except PermissionError:
            self._json(401, {"error": "not owner"})
            return
        except KeyError:
            self._json(404, {"error": "unknown queue"})
            return
        if envelope is None:
            self.send_response(204)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(envelope)))
        self.end_headers()
        self.wfile.write(envelope)


def serve(store: RelayStore, host: str = "127.0.0.1", port: int = 0) -> ThreadingHTTPServer:
    class Handler(RelayHandler):
        pass

    Handler.store = store
    httpd = ThreadingHTTPServer((host, port), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd
