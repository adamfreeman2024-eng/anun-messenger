"""The local path that can be finished here. Not a phone, not an audit."""

import unittest
import wave
from pathlib import Path
from tempfile import TemporaryDirectory

from spike.dest import serve_dest
from spike.device import create_device, open_device
from spike.envelope import generate_keypair
from spike.forward import pump
from spike.invite import pack_invite_v2
from spike.opus_frame import decode_frame, encode_frame
from spike.relay import RelayStore, serve
from spike.session import Session, open_letter
from spike.test_opus import tone
from spike.wavout import write_wav


class LocalPathTest(unittest.TestCase):
    def test_device_key_file_and_wav(self) -> None:
        packet = encode_frame(tone())
        dest_priv, dest_pub = generate_keypair()
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            bob_priv, bob_pub = create_device(root / "bob.key", "bob-pass")
            loaded, loaded_pub = open_device(root / "bob.key", "bob-pass")
            self.assertEqual(loaded_pub, bob_pub)
            self.assertNotIn(bob_priv.private_bytes_raw(), (root / "bob.key").read_bytes())

            dest = RelayStore(root / "dest.bin")
            forward = RelayStore(root / "fwd.bin")
            queue, owner = dest.create_queue()
            token = dest.issue_invite(queue, owner)
            dest_http = serve_dest(dest, dest_priv)
            fwd_http = serve(forward)
            try:
                hop = f"http://127.0.0.1:{dest_http.server_address[1]}/v1/hop"
                invite = pack_invite_v2(queue, token, bob_pub, dest_pub, hop)
                alice = Session(f"http://127.0.0.1:{fwd_http.server_address[1]}")
                alice.accept(invite)
                alice.send_letter(bob_pub, "վերջ".encode(), expire_at=9_999_999_999)
                self.assertEqual(pump(forward), 1)
                letter = open_letter(loaded, dest.take(queue, owner))
                self.assertEqual(letter["text"], "վերջ")
                wav = root / "frame.wav"
                write_wav(wav, decode_frame(packet))
                with wave.open(str(wav), "rb") as handle:
                    self.assertEqual(handle.getnchannels(), 1)
                    self.assertEqual(handle.getframerate(), 48000)
                    self.assertEqual(handle.getnframes(), 960)
                self.assertNotIn("վերջ".encode(), dest.disk_bytes())
                self.assertNotIn(tone(), wav.read_bytes())
            finally:
                dest_http.shutdown()
                fwd_http.shutdown()

    def test_no_phone_login_in_device(self) -> None:
        src = Path(__file__).with_name("device.py").read_text().lower()
        self.assertNotIn("phone_number", src)
        self.assertNotIn("sms", src)


if __name__ == "__main__":
    unittest.main()
