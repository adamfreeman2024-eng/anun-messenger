"""Device key file. Not a phone SecureStore."""

from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

from spike.envelope import generate_keypair
from spike.keystore import load_private, save_private


def create_device(path: Path, passphrase: str) -> tuple[X25519PrivateKey, bytes]:
    private, public = generate_keypair()
    save_private(path, private.private_bytes_raw(), passphrase)
    return private, public


def open_device(path: Path, passphrase: str) -> tuple[X25519PrivateKey, bytes]:
    private = X25519PrivateKey.from_private_bytes(load_private(path, passphrase))
    return private, private.public_key().public_bytes_raw()
