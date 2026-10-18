"""Local product path. Not a phone, and not an audit."""

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib import request as urlrequest

from spike.dest import serve_dest
from spike.envelope import generate_keypair, open_envelope
from spike.filebox import open_file
from spike.forward import ForwardFailed, pump
from spike.invite import pack_invite_v2
from spike.qrimg import write_qr
from spike.relay import RelayStore, serve
from spike.session import Session


LETTER = "բարև"


class ProductTest(unittest.TestCase):
    def test_sender_never_opens_the_dest_relay(self) -> None:
        bob_priv, bob_pub = generate_keypair()
        dest_priv, dest_pub = generate_keypair()
        opened: list[str] = []
        real_open = urlrequest.urlopen

        def spy(req, timeout=None):
            url = req.full_url if hasattr(req, "full_url") else str(req)
            opened.append(url)
            return real_open(req, timeout=timeout)

        with TemporaryDirectory() as tmp:
            dest_store = RelayStore(Path(tmp) / "dest.bin")
            queue, owner = dest_store.create_queue()
            dest_http = serve_dest(dest_store, dest_priv)
            forward_store = RelayStore(Path(tmp) / "fwd.bin")
            forward_http = serve(forward_store)
            try:
                dest_port = dest_http.server_address[1]
                fwd_port = forward_http.server_address[1]
                hop_url = f"http://127.0.0.1:{dest_port}/v1/hop"
                alice = Session(f"http://127.0.0.1:{fwd_port}", lang="hy")
                self.assertEqual(alice.alert(), "նոր ծրար")

                def invite() -> str:
                    token = dest_store.issue_invite(queue, owner)
                    packed = pack_invite_v2(queue, token, bob_pub, dest_pub, hop_url)
                    return packed

                first = invite()
                qr_path = Path(tmp) / "invite.png"
                write_qr(first, qr_path)
                self.assertGreater(qr_path.stat().st_size, 100)
                self.assertNotIn(bob_priv.private_bytes_raw(), qr_path.read_bytes())

                urlrequest.urlopen = spy
                try:
                    alice.accept(first)
                    alice.send_letter(bob_pub, LETTER.encode(), expire_at=9_999_999_999)
                    alice.accept(invite())
                    alice.send_file(bob_pub, "a.txt", b"file-byte", expire_at=9_999_999_999)
                    alice.accept(invite())
                    alice.send_audio(bob_pub, b"AUDIO")
                finally:
                    urlrequest.urlopen = real_open

                self.assertTrue(opened)
                self.assertTrue(all(url.startswith(f"http://127.0.0.1:{fwd_port}/") for url in opened))
                self.assertTrue(all("/v1/hop" not in url for url in opened))
                self.assertEqual(pump(forward_store), 3)
                self.assertNotIn(LETTER.encode(), dest_store.disk_bytes())
                self.assertNotIn(b"file-byte", dest_store.disk_bytes())
                self.assertNotIn(b"AUDIO", dest_store.disk_bytes())

                letter_env = dest_store.take(queue, owner)
                file_env = dest_store.take(queue, owner)
                audio_env = dest_store.take(queue, owner)
                self.assertEqual(json.loads(open_envelope(bob_priv, letter_env))["text"], LETTER)
                name, data = open_file(bob_priv, [file_env], now=1)
                self.assertEqual((name, data), ("a.txt", b"file-byte"))
                self.assertEqual(alice.send_audio.__name__, "send_audio")
                from spike.call import CallSession
                self.assertEqual(CallSession(alice.forward).open_frame(bob_priv, audio_env), b"AUDIO")

                alice.accept(first)
                alice.send_letter(bob_pub, b"again", expire_at=9_999_999_999)
                with self.assertRaises(ForwardFailed):
                    pump(forward_store)
            finally:
                dest_http.shutdown()
                forward_http.shutdown()

    def test_session_source_has_no_direct_hop(self) -> None:
        src = Path(__file__).with_name("session.py").read_text()
        self.assertNotIn("/v1/hop", src)
        self.assertNotIn("peer_ip", src)
        self.assertNotIn("phone", src.lower())


if __name__ == "__main__":
    unittest.main()
