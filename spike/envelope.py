"""Envelope v1. X25519 + HKDF-SHA256 + AES-256-GCM. No homemade cipher."""

import os

from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes

MAGIC = b"ANUN1"
EPH_LEN = 32
NONCE_LEN = 12
TAG_LEN = 16
MAX_PLAINTEXT = 48 * 1024


class EnvelopeError(Exception):
    pass


def generate_keypair() -> tuple[X25519PrivateKey, bytes]:
    private = X25519PrivateKey.generate()
    return private, private.public_key().public_bytes_raw()


def _key(shared: bytes, eph_pub: bytes) -> bytes:
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=eph_pub,
        info=b"anun-spike-v1",
    ).derive(shared)


def seal(recipient_public: bytes, plaintext: bytes) -> bytes:
    if not isinstance(plaintext, bytes):
        raise EnvelopeError("plaintext must be bytes")
    if len(plaintext) > MAX_PLAINTEXT:
        raise EnvelopeError("plaintext too large")
    if len(recipient_public) != EPH_LEN:
        raise EnvelopeError("bad recipient key")
    eph = X25519PrivateKey.generate()
    eph_pub = eph.public_key().public_bytes_raw()
    shared = eph.exchange(X25519PublicKey.from_public_bytes(recipient_public))
    nonce = os.urandom(NONCE_LEN)
    aad = MAGIC + eph_pub
    body = AESGCM(_key(shared, eph_pub)).encrypt(nonce, plaintext, aad)
    return MAGIC + eph_pub + nonce + body


def open_envelope(recipient_private: X25519PrivateKey, envelope: bytes) -> bytes:
    need = len(MAGIC) + EPH_LEN + NONCE_LEN + TAG_LEN
    if len(envelope) < need or not envelope.startswith(MAGIC):
        raise EnvelopeError("not an Anun envelope")
    off = len(MAGIC)
    eph_pub = envelope[off : off + EPH_LEN]
    off += EPH_LEN
    nonce = envelope[off : off + NONCE_LEN]
    body = envelope[off + NONCE_LEN :]
    shared = recipient_private.exchange(X25519PublicKey.from_public_bytes(eph_pub))
    aad = MAGIC + eph_pub
    try:
        return AESGCM(_key(shared, eph_pub)).decrypt(nonce, body, aad)
    except Exception as exc:
        raise EnvelopeError("cannot open") from exc
