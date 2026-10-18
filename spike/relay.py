"""Blind relay. Stores opaque envelopes. Has no keys and no decrypt path."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import re
import secrets
import threading
from pathlib import Path

MAX_ENVELOPE = 64 * 1024
QUEUE_RE = re.compile(r"^[A-Za-z0-9_-]{32,64}$")


class RelayStore:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(exist_ok=True)
        self._lock = threading.Lock()
        self._queues: dict[str, list[bytes]] = {}

    def create_queue(self) -> str:
        queue_id = secrets.token_urlsafe(32)
        with self._lock:
            self._queues[queue_id] = []
        return queue_id

    def put(self, queue_id: str, envelope: bytes) -> None:
        if not QUEUE_RE.match(queue_id):
            raise KeyError("bad queue")
        if len(envelope) > MAX_ENVELOPE:
            raise ValueError("envelope too large")
        with self._lock:
            if queue_id not in self._queues:
                raise KeyError("unknown queue")
            self._queues[queue_id].append(envelope)
            with self.path.open("ab") as fh:
                fh.write(envelope + b"\n")

    def take(self, queue_id: str) -> bytes | None:
        with self._lock:
            items = self._queues.get(queue_id)
            if items is None:
                raise KeyError("unknown queue")
            if not items:
                return None
            return items.pop(0)

    def disk_bytes(self) -> bytes:
        return self.path.read_bytes()


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

    def do_POST(self) -> None:
        if self.path != "/v1/queues":
            self._json(404, {"error": "not found"})
            return
        self._json(201, {"queue_id": self.store.create_queue()})

    def do_PUT(self) -> None:
        m = re.fullmatch(r"/v1/queues/([^/]+)", self.path)
        if not m:
            self._json(404, {"error": "not found"})
            return
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        try:
            self.store.put(m.group(1), body)
        except KeyError:
            self._json(404, {"error": "unknown queue"})
            return
        except ValueError:
            self._json(413, {"error": "too large"})
            return
        self._json(204, {"ok": True})

    def do_GET(self) -> None:
        m = re.fullmatch(r"/v1/queues/([^/]+)", self.path)
        if not m:
            self._json(404, {"error": "not found"})
            return
        try:
            envelope = self.store.take(m.group(1))
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
    RelayHandler.store = store
    httpd = ThreadingHTTPServer((host, port), RelayHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd
