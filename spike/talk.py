"""Show a letter only if its timer has not passed. The relay is not asked."""

from spike.session import open_letter
from spike.strings import text


def show_letter(private, envelope: bytes, now: int, lang: str = "hy") -> str:
    letter = open_letter(private, envelope, now=now)
    if letter is None:
        return text(lang, "disappeared")
    return str(letter["text"])
