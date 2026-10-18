"""Device key file. The raw private key is not written. Phone SecureStore is not this file."""

import json
import os
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes


def save_private(path: Path, private_raw: bytes, passphrase: str) -> None:
    salt = os.urandom(16)
    key = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=200_000).derive(
        passphrase.encode()
    )
    nonce = os.urandom(12)
    blob = AESGCM(key).encrypt(nonce, private_raw, b"anun-device-key")
    path.write_text(
        json.dumps({"salt": salt.hex(), "nonce": nonce.hex(), "blob": blob.hex()}),
        encoding="utf-8",
    )


def load_private(path: Path, passphrase: str) -> bytes:
    data = json.loads(path.read_text(encoding="utf-8"))
    salt = bytes.fromhex(data["salt"])
    key = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=200_000).derive(
        passphrase.encode()
    )
    return AESGCM(key).decrypt(bytes.fromhex(data["nonce"]), bytes.fromhex(data["blob"]), b"anun-device-key")
