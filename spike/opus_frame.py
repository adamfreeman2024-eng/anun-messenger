"""One Opus frame via the system libopus. This is not a phone call."""

import array
import ctypes
from ctypes import c_int, c_int32

_LIB = ctypes.CDLL("libopus.so.0")
_VOIP = 2048
_RATE = 48000
_FRAME = 960

_LIB.opus_encoder_create.argtypes = [c_int32, c_int, c_int, ctypes.POINTER(c_int)]
_LIB.opus_encoder_create.restype = ctypes.c_void_p
_LIB.opus_encode.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_int16), c_int, ctypes.POINTER(ctypes.c_ubyte), c_int32]
_LIB.opus_encode.restype = c_int32
_LIB.opus_encoder_destroy.argtypes = [ctypes.c_void_p]
_LIB.opus_decoder_create.argtypes = [c_int32, c_int, ctypes.POINTER(c_int)]
_LIB.opus_decoder_create.restype = ctypes.c_void_p
_LIB.opus_decode.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ubyte), c_int32, ctypes.POINTER(ctypes.c_int16), c_int, c_int]
_LIB.opus_decode.restype = c_int
_LIB.opus_decoder_destroy.argtypes = [ctypes.c_void_p]


class OpusError(Exception):
    pass


def _create(kind: str):
    err = c_int()
    if kind == "enc":
        handle = _LIB.opus_encoder_create(_RATE, 1, _VOIP, ctypes.byref(err))
    else:
        handle = _LIB.opus_decoder_create(_RATE, 1, ctypes.byref(err))
    if err.value != 0 or not handle:
        raise OpusError(f"opus {kind} failed {err.value}")
    return handle


def encode_frame(pcm: bytes) -> bytes:
    if len(pcm) != _FRAME * 2:
        raise OpusError("need 960 int16 samples")
    samples = array.array("h")
    samples.frombytes(pcm)
    enc = _create("enc")
    try:
        out = (ctypes.c_ubyte * 4000)()
        n = _LIB.opus_encode(enc, (ctypes.c_int16 * _FRAME).from_buffer(samples), _FRAME, out, 4000)
        if n < 1:
            raise OpusError(f"encode failed {n}")
        return bytes(out[:n])
    finally:
        _LIB.opus_encoder_destroy(enc)


def decode_frame(packet: bytes) -> bytes:
    dec = _create("dec")
    try:
        incoming = (ctypes.c_ubyte * len(packet)).from_buffer_copy(packet)
        out = (ctypes.c_int16 * _FRAME)()
        n = _LIB.opus_decode(dec, incoming, len(packet), out, _FRAME, 0)
        if n != _FRAME:
            raise OpusError(f"decode failed {n}")
        return array.array("h", out).tobytes()
    finally:
        _LIB.opus_decoder_destroy(dec)
