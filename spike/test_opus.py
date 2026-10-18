"""Opus frame stays sealed on the relay. Not a phone call."""

import array
import math
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from spike.dest import serve_dest
from spike.envelope import generate_keypair
from spike.forward import pump
from spike.invite import pack_invite_v2
from spike.opus_frame import decode_frame, encode_frame
from spike.relay import RelayStore, serve
from spike.session import Session
from spike.call import CallSession


def tone() -> bytes:
    samples = array.array("h")
    for i in range(960):
        samples.append(int(8000 * math.sin(2 * math.pi * 440 * i / 48000)))
    return samples.tobytes()


class OpusTest(unittest.TestCase):
    def test_opus_frame_is_not_on_the_relay_disk(self) -> None:
        pcm = tone()
        packet = encode_frame(pcm)
        self.assertNotIn(pcm[:16], packet)
        heard = decode_frame(packet)
        self.assertEqual(len(heard), len(pcm))

        bob_priv, bob_pub = generate_keypair()
        dest_priv, dest_pub = generate_keypair()
        with TemporaryDirectory() as tmp:
            dest = RelayStore(Path(tmp) / "dest.bin")
            forward = RelayStore(Path(tmp) / "fwd.bin")
            queue, owner = dest.create_queue()
            token = dest.issue_invite(queue, owner)
            dest_http = serve_dest(dest, dest_priv)
            fwd_http = serve(forward)
            try:
                hop = f"http://127.0.0.1:{dest_http.server_address[1]}/v1/hop"
                invite = pack_invite_v2(queue, token, bob_pub, dest_pub, hop)
                alice = Session(f"http://127.0.0.1:{fwd_http.server_address[1]}")
                alice.accept(invite)
                alice.send_audio(bob_pub, packet)
                self.assertEqual(pump(forward), 1)
                self.assertNotIn(pcm, dest.disk_bytes())
                self.assertNotIn(pcm[:16], dest.disk_bytes())
                frame = dest.take(queue, owner)
                opened = CallSession(alice.forward).open_frame(bob_priv, frame)
                self.assertEqual(decode_frame(opened), heard)
            finally:
                dest_http.shutdown()
                fwd_http.shutdown()


if __name__ == "__main__":
    unittest.main()
