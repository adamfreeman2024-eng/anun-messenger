"""Phase 1 and 2. The relay disk must not contain the letter or a private key."""

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.error import HTTPError
from urllib import request as urlrequest

from spike.client import LocalClient
from spike.dest import serve_dest
from spike.envelope import generate_keypair
from spike.forward import pump
from spike.invite import pack_invite_v2
from spike.relay import RelayStore, serve
from spike.session import Session, open_letter


LETTER = "գաղտնի նամակ 18.10.2026"


class SpikeTest(unittest.TestCase):
    def test_invite_once_and_key_never_leaves(self) -> None:
        with TemporaryDirectory() as tmp:
            dest = RelayStore(Path(tmp) / "dest.bin")
            forward = RelayStore(Path(tmp) / "fwd.bin")
            dest_priv, dest_pub = generate_keypair()
            bob = LocalClient(generate_keypair())
            alice = Session("http://127.0.0.1:9")
            dest_http = serve(dest)
            hop_http = serve_dest(dest, dest_priv)
            fwd_http = serve(forward)
            try:
                bob_base = f"http://127.0.0.1:{dest_http.server_address[1]}"
                bob.create_inbox(bob_base)
                invite = bob.make_invite(bob_base)
                token = invite.split(".")[2]
                body = json.dumps({"token": token}).encode()
                req = urlrequest.Request(
                    f"{bob_base}/v1/invites/redeem",
                    data=body,
                    method="POST",
                    headers={"Content-Type": "application/json"},
                )
                with urlrequest.urlopen(req) as res:
                    self.assertEqual(res.status, 200)
                with self.assertRaises(HTTPError) as ctx:
                    urlrequest.urlopen(req)
                self.assertEqual(ctx.exception.code, 401)
                fresh = dest.issue_invite(bob.queue_id, bob.owner_cap)
                hop = f"http://127.0.0.1:{hop_http.server_address[1]}/v1/hop"
                alice = Session(f"http://127.0.0.1:{fwd_http.server_address[1]}")
                alice.accept(pack_invite_v2(bob.queue_id, fresh, bob.public, dest_pub, hop))
                alice.send_letter(bob.public, LETTER.encode(), expire_at=9_999_999_999)
                self.assertEqual(pump(forward), 1)
                opened = open_letter(bob.private, dest.take(bob.queue_id, bob.owner_cap))
                self.assertEqual(opened["text"], LETTER)
                disk = dest.disk_bytes() + forward.disk_bytes()
                self.assertNotIn(LETTER.encode(), disk)
                self.assertNotIn(bob.private_raw(), disk)
                self.assertNotIn(bob.private_raw(), invite.encode())
            finally:
                dest_http.shutdown()
                hop_http.shutdown()
                fwd_http.shutdown()

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
            dest = RelayStore(Path(tmp) / "dest.bin")
            forward = RelayStore(Path(tmp) / "fwd.bin")
            dest_priv, dest_pub = generate_keypair()
            bob = LocalClient(generate_keypair())
            dest_http = serve(dest)
            hop_http = serve_dest(dest, dest_priv)
            fwd_http = serve(forward)
            try:
                bob_base = f"http://127.0.0.1:{dest_http.server_address[1]}"
                bob.create_inbox(bob_base)
                token = dest.issue_invite(bob.queue_id, bob.owner_cap)
                alice = Session(f"http://127.0.0.1:{fwd_http.server_address[1]}")
                alice.accept(
                    pack_invite_v2(
                        bob.queue_id,
                        token,
                        bob.public,
                        dest_pub,
                        f"http://127.0.0.1:{hop_http.server_address[1]}/v1/hop",
                    )
                )
                alice.send_letter(bob.public, LETTER.encode(), expire_at=100)
                self.assertEqual(pump(forward), 1)
                self.assertIsNone(open_letter(bob.private, dest.take(bob.queue_id, bob.owner_cap), now=101))
                self.assertNotIn(LETTER.encode(), dest.disk_bytes())
            finally:
                dest_http.shutdown()
                hop_http.shutdown()
                fwd_http.shutdown()

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
