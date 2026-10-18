"""QR image of an invite. The image payload is the invite string alone."""

from pathlib import Path

import qrcode

from spike.invite import qr_payload


def write_qr(invite: str, path: Path) -> None:
    img = qrcode.make(qr_payload(invite))
    img.save(path)
