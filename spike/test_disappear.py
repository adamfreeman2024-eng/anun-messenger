"""Expired letters are not shown, even if the relay still holds the envelope."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from spike.dest import serve_dest
from spike.envelope import generate_keypair
from spike.forward import pump
from spike.invite import pack_invite_v2
from spike.relay import RelayStore, serve
from spike.session import Session
from spike.talk import show_letter


class DisappearTest(unittest.TestCase):
    def test_expired_letter_is_not_shown(self) -> None:
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
                alice = Session(f"http://127.0.0.1:{fwd_http.server_address[1]}", lang="hy")
                alice.accept(invite)
                alice.send_letter(bob_pub, "ժամկետ".encode(), expire_at=100)
                self.assertEqual(pump(forward), 1)
                envelope = dest.take(queue, owner)
                self.assertEqual(show_letter(bob_priv, envelope, now=100, lang="hy"), "նամակը անհետացել է")
                self.assertEqual(show_letter(bob_priv, envelope, now=99, lang="en"), "ժամկետ")
                self.assertNotIn("ժամկետ".encode(), dest.disk_bytes())
            finally:
                dest_http.shutdown()
                fwd_http.shutdown()


if __name__ == "__main__":
    unittest.main()
