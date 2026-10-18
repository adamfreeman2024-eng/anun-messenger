"""Voice frames go to the relay only. There is no direct-address fallback."""

import json
from urllib import request as urlrequest
from urllib.error import URLError

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

    def send_frame(self, queue_id: str, send_cap: str, frame: bytes) -> None:
        req = urlrequest.Request(
            f"{self.relay_base}/v1/queues/{queue_id}",
            data=frame,
            method="PUT",
            headers={"X-Anun-Send": send_cap, "X-Anun-TTL": "30"},
        )
        try:
            with urlrequest.urlopen(req, timeout=3) as res:
                if res.status not in (200, 204):
                    raise CallDropped("relay rejected the frame")
        except (URLError, TimeoutError, OSError) as exc:
            raise CallDropped("relay down; direct connection is forbidden") from exc
