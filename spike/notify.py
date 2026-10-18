"""Alert text only. The letter never enters the notification."""

from spike.strings import text


def notification(lang: str) -> dict:
    return {"alert": text(lang, "new_envelope")}
