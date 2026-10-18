"""Local client. The private key stays in this object. It is never sent."""

import json
from urllib import request as urlrequest

from spike.envelope import open_envelope
from spike.invite import pack_invite


class LocalClient:
    def __init__(self, keypair: tuple):
        self.private, self.public = keypair
        self.queue_id: str | None = None
        self.owner_cap: str | None = None

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
