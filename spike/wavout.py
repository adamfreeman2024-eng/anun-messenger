"""Write decoded PCM as a WAV file. This does not play a phone call."""

import wave
from pathlib import Path


def write_wav(path: Path, pcm: bytes, rate: int = 48000) -> None:
    if len(pcm) % 2:
        raise ValueError("pcm must be int16")
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(pcm)
