"""Phase 1 and 2. The relay disk must not contain the letter or a private key."""

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.error import HTTPError
from urllib import request as urlrequest

from spike.client import LocalClient
from spike.envelope import generate_keypair
from spike.relay import RelayStore, serve


LETTER = "գաղտնի նամակ 18.10.2026"


class SpikeTest(unittest.TestCase):
    def test_invite_once_and_key_never_leaves(self) -> None:
        with TemporaryDirectory() as tmp:
            store = RelayStore(Path(tmp) / "envelopes.bin")
            httpd = serve(store)
            port = httpd.server_address[1]
            base = f"http://127.0.0.1:{port}"
            try:
                alice = LocalClient(generate_keypair())
                bob = LocalClient(generate_keypair())
                bob.create_inbox(base)
                invite = bob.make_invite(base)
                alice.accept_invite(base, invite)
                with self.assertRaises(HTTPError) as ctx:
                    alice.accept_invite(base, invite)
                self.assertEqual(ctx.exception.code, 401)

                alice.send_text(base, bob.queue_id, LETTER, expire_at=9_999_999_999, ttl=3600)
                self.assertEqual(bob.read_text(base, now=1_700_000_000), LETTER)

                disk = store.disk_bytes()
                self.assertNotIn(LETTER.encode(), disk)
                self.assertNotIn(alice.private_raw(), disk)
                self.assertNotIn(bob.private_raw(), disk)
                self.assertNotIn(alice.private_raw(), invite.encode())
            finally:
                httpd.shutdown()

    def test_expired_envelope_is_deleted_from_disk(self) -> None:
        clock = {"now": 1_000.0}

        def now() -> float:
            return clock["now"]

        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "envelopes.bin"
            store = RelayStore(path, now_fn=now)
            queue_id, owner = store.create_queue()
            token = store.issue_invite(queue_id, owner)
            _queue, send_cap = store.redeem(token)
            marker = b"UNIQUE-ENVELOPE-MARKER"
            store.put(queue_id, marker, send_cap, ttl=10)
            self.assertIn(marker, store.disk_bytes())
            clock["now"] = 1_011.0
            self.assertIsNone(store.take(queue_id, owner))
            self.assertNotIn(marker, store.disk_bytes())

    def test_disappeared_letter_is_not_shown(self) -> None:
        with TemporaryDirectory() as tmp:
            store = RelayStore(Path(tmp) / "envelopes.bin")
            httpd = serve(store)
            port = httpd.server_address[1]
            base = f"http://127.0.0.1:{port}"
            try:
                alice = LocalClient(generate_keypair())
                bob = LocalClient(generate_keypair())
                bob.create_inbox(base)
                alice.accept_invite(base, bob.make_invite(base))
                alice.send_text(base, bob.queue_id, LETTER, expire_at=100, ttl=3600)
                self.assertIsNone(bob.read_text(base, now=101))
                self.assertNotIn(LETTER.encode(), store.disk_bytes())
            finally:
                httpd.shutdown()

    def test_stranger_cannot_post(self) -> None:
        with TemporaryDirectory() as tmp:
            store = RelayStore(Path(tmp) / "envelopes.bin")
            queue_id, _owner = store.create_queue()
            with self.assertRaises(PermissionError):
                store.put(queue_id, b"ANUN1nope", "wrong-cap", ttl=10)

    def test_relay_source_has_no_decrypt(self) -> None:
        src = Path(__file__).with_name("relay.py").read_text()
        self.assertNotIn("open_envelope", src)
        self.assertNotIn("private_key", src.lower())
        self.assertNotIn("AESGCM", src)

    def test_wrong_owner_cannot_read(self) -> None:
        with TemporaryDirectory() as tmp:
            store = RelayStore(Path(tmp) / "envelopes.bin")
            httpd = serve(store)
            port = httpd.server_address[1]
            try:
                req = urlrequest.Request(
                    f"http://127.0.0.1:{port}/v1/queues",
                    method="POST",
                )
                with urlrequest.urlopen(req) as res:
                    data = json.load(res)
                get = urlrequest.Request(
                    f"http://127.0.0.1:{port}/v1/queues/{data['queue_id']}",
                    headers={"X-Anun-Owner": "nope"},
                )
                with self.assertRaises(HTTPError) as ctx:
                    urlrequest.urlopen(get)
                self.assertEqual(ctx.exception.code, 401)
            finally:
                httpd.shutdown()


if __name__ == "__main__":
    unittest.main()
