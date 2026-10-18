"""Voice frames go to the relay only. There is no direct-address fallback."""

import json

from spike.envelope import open_envelope, seal


class CallDropped(Exception):
    pass


class CallSession:
    def __init__(self, relay_base: str):
        if not relay_base.startswith("http://") and not relay_base.startswith("https://"):
            raise ValueError("relay url required")
        self.relay_base = relay_base.rstrip("/")

    def frame(self, recipient_public: bytes, call_id: str, seq: int, audio: bytes) -> bytes:
        payload = json.dumps(
            {"v": 1, "kind": "audio", "call_id": call_id, "seq": seq, "audio_hex": audio.hex()},
            separators=(",", ":"),
        ).encode()
        return seal(recipient_public, payload)

    def open_frame(self, private, frame: bytes) -> bytes:
        letter = json.loads(open_envelope(private, frame))
        if letter.get("kind") != "audio":
            raise ValueError("not audio")
        return bytes.fromhex(letter["audio_hex"])

    def read_frame(self, private, frame: bytes) -> tuple[str, int, bytes]:
        letter = json.loads(open_envelope(private, frame))
        if letter.get("kind") != "audio":
            raise ValueError("not audio")
        return str(letter["call_id"]), int(letter["seq"]), bytes.fromhex(letter["audio_hex"])
