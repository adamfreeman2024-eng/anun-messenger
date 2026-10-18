"""File as sealed chunks. The relay sees envelopes, not the file."""

import base64
import json
import uuid

from spike.envelope import open_envelope, seal

CHUNK = 16 * 1024


def seal_file(recipient_public: bytes, name: str, data: bytes, expire_at: int) -> list[bytes]:
    if len(data) > 8 * 1024 * 1024:
        raise ValueError("file too large")
    file_id = uuid.uuid4().hex
    chunks = [data[i : i + CHUNK] for i in range(0, max(len(data), 1), CHUNK)] or [b""]
    out = []
    total = len(chunks)
    for index, piece in enumerate(chunks):
        payload = json.dumps(
            {
                "v": 1,
                "kind": "file",
                "file_id": file_id,
                "index": index,
                "total": total,
                "name": name,
                "data_b64": base64.b64encode(piece).decode(),
                "expire_at": expire_at,
            },
            ensure_ascii=False,
        ).encode()
        out.append(seal(recipient_public, payload))
    return out


def open_file(private, envelopes: list[bytes], now: int) -> tuple[str, bytes]:
    parts: dict[int, bytes] = {}
    name = ""
    total = 0
    for env in envelopes:
        letter = json.loads(open_envelope(private, env))
        if int(letter["expire_at"]) <= now:
            raise ValueError("file disappeared")
        if letter.get("kind") != "file":
            raise ValueError("not a file")
        total = int(letter["total"])
        name = str(letter["name"])
        parts[int(letter["index"])] = base64.b64decode(letter["data_b64"])
    if len(parts) != total or sorted(parts) != list(range(total)):
        raise ValueError("incomplete file")
    return name, b"".join(parts[i] for i in range(total))
