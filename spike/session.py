"""Sender talks only to the forward relay. The dest hop URL is never opened here."""

import json
from urllib import request as urlrequest

from spike.call import CallSession
from spike.envelope import open_envelope, seal
from spike.filebox import seal_file
from spike.hop import seal_route
from spike.invite import pack_invite_v2, unpack_invite_v2, unpack_invite_v3
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
        self._tokens: list[str] = []

    def accept(self, invite: str) -> None:
        if invite.startswith("anun3."):
            queue_id, tokens, user_pub, hop_pub, hop_url = unpack_invite_v3(invite)
            self.peer = (queue_id, tokens[0], user_pub, hop_pub, hop_url)
            self._tokens = list(tokens)
            return
        self.peer = unpack_invite_v2(invite)
        self._tokens = [self.peer[1]]

    def alert(self) -> str:
        return notification(self.lang)["alert"]

    def label(self, key: str) -> str:
        return text(self.lang, key)

    def send_letter(
        self,
        recipient_public: bytes,
        letter: bytes,
        expire_at: int,
        reply_invite: str | None = None,
    ) -> None:
        payload = {"v": 1, "text": letter.decode(), "expire_at": expire_at}
        if reply_invite:
            payload["reply_invite"] = reply_invite
        body = json.dumps(payload, ensure_ascii=False).encode()
        self._forward(seal(recipient_public, body))

    def send_file(self, recipient_public: bytes, name: str, data: bytes, expire_at: int) -> None:
        chunks = seal_file(recipient_public, name, data, expire_at)
        if len(self._tokens) < len(chunks):
            raise ValueError("not enough invites for every chunk")
        for chunk in chunks:
            self._forward(chunk)

    def send_audio(self, recipient_public: bytes, audio: bytes) -> None:
        frame = CallSession(self.forward).frame(recipient_public, "call", 1, audio)
        self._forward(frame)

    def _forward(self, envelope: bytes) -> None:
        if self.peer is None:
            raise RuntimeError("no invite")
        queue_id, _token, _user_pub, hop_pub, hop_url = self.peer
        if not self._tokens:
            raise RuntimeError("invite already used")
        token = self._tokens.pop(0)
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


def open_letter(private, envelope: bytes, now: int | None = None) -> dict | None:
    data = json.loads(open_envelope(private, envelope))
    if now is not None and int(data.get("expire_at", 0)) <= now:
        return None
    return data
