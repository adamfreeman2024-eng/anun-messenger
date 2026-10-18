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


def qr_payload(invite: str) -> str:
    """The QR image encodes this string and nothing else."""
    if invite.startswith("anun2."):
        unpack_invite_v2(invite)
    else:
        unpack_invite(invite)
    return invite


def pack_invite_v2(
    queue_id: str,
    token: str,
    user_public: bytes,
    hop_public: bytes,
    hop_url: str,
) -> str:
    if "." in queue_id or "." in token:
        raise InviteError("bad invite field")
    return (
        f"anun2.{queue_id}.{token}.{_b64(user_public)}."
        f"{_b64(hop_public)}.{_b64(hop_url.encode())}"
    )


def unpack_invite_v2(invite: str) -> tuple[str, str, bytes, bytes, str]:
    parts = invite.split(".")
    if len(parts) != 6 or parts[0] != "anun2":
        raise InviteError("bad invite")
    user_public = _b64d(parts[3])
    hop_public = _b64d(parts[4])
    hop_url = _b64d(parts[5]).decode()
    if len(user_public) != 32 or len(hop_public) != 32:
        raise InviteError("bad public key")
    if not hop_url.startswith("http://") and not hop_url.startswith("https://"):
        raise InviteError("bad hop url")
    return parts[1], parts[2], user_public, hop_public, hop_url
