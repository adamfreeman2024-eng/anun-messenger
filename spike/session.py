"""Sender talks only to the forward relay. The dest hop URL is never opened here."""

import json
from urllib import request as urlrequest

from spike.call import CallSession
from spike.envelope import seal
from spike.filebox import seal_file
from spike.hop import seal_route
from spike.invite import pack_invite_v2, unpack_invite_v2
from spike.notify import notification
from spike.strings import text


class Session:
    def __init__(self, forward_base: str, lang: str = "hy"):
        if lang not in ("hy", "en"):
            raise ValueError("lang")
        if not forward_base.startswith("http://") and not forward_base.startswith("https://"):
            raise ValueError("forward relay required")
        self.forward = forward_base.rstrip("/")
        self.lang = lang
        self.peer: tuple[str, str, bytes, bytes, str] | None = None

    def accept(self, invite: str) -> None:
        self.peer = unpack_invite_v2(invite)

    def alert(self) -> str:
        return notification(self.lang)["alert"]

    def label(self, key: str) -> str:
        return text(self.lang, key)

    def send_letter(self, recipient_public: bytes, letter: bytes, expire_at: int) -> None:
        body = json.dumps(
            {"v": 1, "text": letter.decode(), "expire_at": expire_at},
            ensure_ascii=False,
        ).encode()
        self._forward(seal(recipient_public, body))

    def send_file(self, recipient_public: bytes, name: str, data: bytes, expire_at: int) -> None:
        chunks = seal_file(recipient_public, name, data, expire_at)
        if len(chunks) != 1:
            raise ValueError("file too large for one hop")
        self._forward(chunks[0])

    def send_audio(self, recipient_public: bytes, audio: bytes) -> None:
        frame = CallSession(self.forward).frame(recipient_public, "call", 1, audio)
        self._forward(frame)

    def _forward(self, envelope: bytes) -> None:
        if self.peer is None:
            raise RuntimeError("no invite")
        queue_id, token, _user_pub, hop_pub, hop_url = self.peer
        route = seal_route(hop_pub, queue_id, envelope, token)
        payload = json.dumps({"dest": hop_url, "blob_hex": route.hex()}).encode()
        req = urlrequest.Request(
            f"{self.forward}/v1/forward",
            data=payload,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urlrequest.urlopen(req, timeout=3) as res:
            if res.status != 202:
                raise RuntimeError("forward rejected")


def make_v2_invite(queue_id: str, token: str, user_public: bytes, hop_public: bytes, hop_url: str) -> str:
    return pack_invite_v2(queue_id, token, user_public, hop_public, hop_url)
