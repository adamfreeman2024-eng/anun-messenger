"""A reply travels back inside the letter. Neither side opens the other's hop."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib import request as urlrequest

from spike.dest import serve_dest
from spike.envelope import generate_keypair
from spike.forward import pump
from spike.invite import pack_invite_v2
from spike.relay import RelayStore, serve
from spike.session import Session, open_letter


class ReplyTest(unittest.TestCase):
    def test_reply_does_not_touch_the_other_hop(self) -> None:
        alice_priv, alice_pub = generate_keypair()
        bob_priv, bob_pub = generate_keypair()
        alice_hop_priv, alice_hop_pub = generate_keypair()
        bob_hop_priv, bob_hop_pub = generate_keypair()
        opened: list[str] = []
        real_open = urlrequest.urlopen

        def spy(req, timeout=None):
            opened.append(req.full_url)
            return real_open(req, timeout=timeout)

        with TemporaryDirectory() as tmp:
            alice_dest = RelayStore(Path(tmp) / "alice-dest.bin")
            bob_dest = RelayStore(Path(tmp) / "bob-dest.bin")
            alice_fwd = RelayStore(Path(tmp) / "alice-fwd.bin")
            bob_fwd = RelayStore(Path(tmp) / "bob-fwd.bin")
            alice_dest_http = serve_dest(alice_dest, alice_hop_priv)
            bob_dest_http = serve_dest(bob_dest, bob_hop_priv)
            alice_fwd_http = serve(alice_fwd)
            bob_fwd_http = serve(bob_fwd)
            try:
                alice_hop = f"http://127.0.0.1:{alice_dest_http.server_address[1]}/v1/hop"
                bob_hop = f"http://127.0.0.1:{bob_dest_http.server_address[1]}/v1/hop"
                alice_forward = f"http://127.0.0.1:{alice_fwd_http.server_address[1]}"
                bob_forward = f"http://127.0.0.1:{bob_fwd_http.server_address[1]}"

                bob_queue, bob_owner = bob_dest.create_queue()
                bob_token = bob_dest.issue_invite(bob_queue, bob_owner)
                bob_invite = pack_invite_v2(bob_queue, bob_token, bob_pub, bob_hop_pub, bob_hop)

                alice_queue, alice_owner = alice_dest.create_queue()
                alice_token = alice_dest.issue_invite(alice_queue, alice_owner)
                alice_invite = pack_invite_v2(
                    alice_queue, alice_token, alice_pub, alice_hop_pub, alice_hop
                )

                alice = Session(alice_forward)
                bob = Session(bob_forward)
                urlrequest.urlopen = spy
                try:
                    alice.accept(bob_invite)
                    alice.send_letter(
                        bob_pub,
                        "բարև".encode(),
                        expire_at=9_999_999_999,
                        reply_invite=alice_invite,
                    )
                    bob.accept(alice_invite)
                    bob.send_letter(alice_pub, "պատասխան".encode(), expire_at=9_999_999_999)
                finally:
                    urlrequest.urlopen = real_open

                self.assertTrue(all(url.startswith(alice_forward) or url.startswith(bob_forward) for url in opened))
                self.assertTrue(all("/v1/hop" not in url for url in opened))
                self.assertEqual(pump(alice_fwd), 1)
                self.assertEqual(pump(bob_fwd), 1)

                bob_letter = open_letter(bob_priv, bob_dest.take(bob_queue, bob_owner))
                self.assertEqual(bob_letter["text"], "բարև")
                self.assertEqual(bob_letter["reply_invite"], alice_invite)
                self.assertNotIn("պատասխան".encode(), bob_dest.disk_bytes())
                alice_letter = open_letter(alice_priv, alice_dest.take(alice_queue, alice_owner))
                self.assertEqual(alice_letter["text"], "պատասխան")
                self.assertNotIn(alice_priv.private_bytes_raw(), alice_invite.encode())
            finally:
                alice_dest_http.shutdown()
                bob_dest_http.shutdown()
                alice_fwd_http.shutdown()
                bob_fwd_http.shutdown()


if __name__ == "__main__":
    unittest.main()
