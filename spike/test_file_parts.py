"""A multi-part file crosses only the forward relay, one invite token per part."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from spike.dest import serve_dest
from spike.envelope import generate_keypair
from spike.filebox import open_file
from spike.forward import pump
from spike.invite import pack_invite_v3
from spike.relay import RelayStore, serve
from spike.session import Session


class FilePartsTest(unittest.TestCase):
    def test_three_parts_use_three_tokens(self) -> None:
        bob_priv, bob_pub = generate_keypair()
        dest_priv, dest_pub = generate_keypair()
        data = b"PARTS-" + b"x" * 9000
        with TemporaryDirectory() as tmp:
            dest = RelayStore(Path(tmp) / "dest.bin")
            forward = RelayStore(Path(tmp) / "fwd.bin")
            queue, owner = dest.create_queue()
            tokens = [dest.issue_invite(queue, owner) for _ in range(3)]
            dest_http = serve_dest(dest, dest_priv)
            fwd_http = serve(forward)
            try:
                hop = f"http://127.0.0.1:{dest_http.server_address[1]}/v1/hop"
                invite = pack_invite_v3(queue, tokens, bob_pub, dest_pub, hop)
                alice = Session(f"http://127.0.0.1:{fwd_http.server_address[1]}")
                alice.accept(invite)
                alice.send_file(bob_pub, "parts.bin", data, expire_at=9_999_999_999)
                self.assertEqual(pump(forward), 3)
                self.assertNotIn(data, dest.disk_bytes())
                self.assertNotIn(b"parts.bin", dest.disk_bytes())
                parts = []
                while True:
                    item = dest.take(queue, owner)
                    if item is None:
                        break
                    parts.append(item)
                name, got = open_file(bob_priv, parts, now=1)
                self.assertEqual(name, "parts.bin")
                self.assertEqual(got, data)
                self.assertEqual(alice._tokens, [])
            finally:
                dest_http.shutdown()
                fwd_http.shutdown()


if __name__ == "__main__":
    unittest.main()
