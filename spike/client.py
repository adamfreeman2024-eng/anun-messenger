"""Local client. The private key stays in this object. It is never sent."""

import json
from urllib import request as urlrequest

from spike.envelope import open_envelope, seal
from spike.invite import pack_invite, unpack_invite


class LocalClient:
    def __init__(self, keypair: tuple):
        self.private, self.public = keypair
        self.queue_id: str | None = None
        self.owner_cap: str | None = None
        self.peers: dict[str, tuple[str, bytes]] = {}

    def private_raw(self) -> bytes:
        return self.private.private_bytes_raw()

    def create_inbox(self, base: str) -> None:
        req = urlrequest.Request(f"{base}/v1/queues", method="POST")
        with urlrequest.urlopen(req) as res:
            data = json.load(res)
        self.queue_id = data["queue_id"]
        self.owner_cap = data["owner_cap"]

    def make_invite(self, base: str) -> str:
        if not self.queue_id or not self.owner_cap:
            raise RuntimeError("no inbox")
        req = urlrequest.Request(
            f"{base}/v1/queues/{self.queue_id}/invites",
            method="POST",
            headers={"X-Anun-Owner": self.owner_cap},
        )
        with urlrequest.urlopen(req) as res:
            token = json.load(res)["token"]
        return pack_invite(self.queue_id, token, self.public)

    def accept_invite(self, base: str, invite: str) -> str:
        queue_id, token, peer_pub = unpack_invite(invite)
        body = json.dumps({"token": token}).encode()
        self._refuse_key(body)
        req = urlrequest.Request(
            f"{base}/v1/invites/redeem",
            data=body,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urlrequest.urlopen(req) as res:
            data = json.load(res)
        self.peers[data["queue_id"]] = (data["send_cap"], peer_pub)
        return queue_id

    def send_text(self, base: str, queue_id: str, text: str, expire_at: int, ttl: int) -> None:
        send_cap, peer_pub = self.peers[queue_id]
        payload = json.dumps(
            {"v": 1, "text": text, "expire_at": expire_at},
            ensure_ascii=False,
        ).encode()
        envelope = seal(peer_pub, payload)
        self._refuse_key(envelope)
        req = urlrequest.Request(
            f"{base}/v1/queues/{queue_id}",
            data=envelope,
            method="PUT",
            headers={"X-Anun-Send": send_cap, "X-Anun-TTL": str(ttl)},
        )
        with urlrequest.urlopen(req) as res:
            if res.status not in (200, 204):
                raise RuntimeError(f"send failed {res.status}")

    def read_text(self, base: str, now: int) -> str | None:
        if not self.queue_id or not self.owner_cap:
            raise RuntimeError("no inbox")
        req = urlrequest.Request(
            f"{base}/v1/queues/{self.queue_id}",
            headers={"X-Anun-Owner": self.owner_cap},
        )
        with urlrequest.urlopen(req) as res:
            if res.status == 204:
                return None
            envelope = res.read()
        raw = open_envelope(self.private, envelope)
        letter = json.loads(raw)
        if int(letter["expire_at"]) <= now:
            return None
        return str(letter["text"])

    def _refuse_key(self, blob: bytes) -> None:
        if self.private_raw() in blob:
            raise RuntimeError("refusing to send the private key")
