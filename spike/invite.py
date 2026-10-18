"""One-time invite. Public fields only. Never a private key."""

import base64

PREFIX = "anun1"


class InviteError(Exception):
    pass


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _b64d(text: str) -> bytes:
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


def pack_invite(queue_id: str, token: str, public_key: bytes) -> str:
    if "." in queue_id or "." in token:
        raise InviteError("bad invite field")
    return f"{PREFIX}.{queue_id}.{token}.{_b64(public_key)}"


def unpack_invite(invite: str) -> tuple[str, str, bytes]:
    parts = invite.split(".")
    if len(parts) != 4 or parts[0] != PREFIX:
        raise InviteError("bad invite")
    public = _b64d(parts[3])
    if len(public) != 32:
        raise InviteError("bad public key")
    return parts[1], parts[2], public
