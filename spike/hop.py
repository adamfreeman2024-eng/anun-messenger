"""Hop wrapper. The forward relay cannot open it. The dest relay learns only the queue id."""

import json

from spike.envelope import MAGIC, EnvelopeError, open_envelope, seal

HOP_MAGIC = b"ANUNH"
HOP_INFO = b"anun-hop-v1"


def seal_route(dest_public: bytes, queue_id: str, envelope: bytes, token: str = "") -> bytes:
    payload = json.dumps(
        {"queue_id": queue_id, "token": token, "envelope_b64": envelope.hex()},
        separators=(",", ":"),
    ).encode()
    return seal(dest_public, payload, magic=HOP_MAGIC, info=HOP_INFO)


def open_route(dest_private, blob: bytes) -> tuple[str, bytes, str]:
    if blob.startswith(MAGIC):
        raise EnvelopeError("refusing a user letter")
    raw = open_envelope(dest_private, blob, magic=HOP_MAGIC, info=HOP_INFO)
    data = json.loads(raw)
    return str(data["queue_id"]), bytes.fromhex(data["envelope_b64"]), str(data.get("token") or "")
