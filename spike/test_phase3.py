"""Phase 3 and two-hop. Not a phone call, and not an external audit."""

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib import request as urlrequest

from spike.call import CallDropped, CallSession
from spike.envelope import EnvelopeError, generate_keypair, open_envelope, seal
from spike.filebox import open_file, seal_file
from spike.hop import open_route, seal_route
from spike.keystore import load_private, save_private
from spike.relay import RelayStore, serve
from spike.strings import STRINGS


class Phase3Test(unittest.TestCase):
    def test_file_chunks_stay_sealed(self) -> None:
        priv, pub = generate_keypair()
        data = b"FILE-BYTES-" + b"z" * 40_000
        chunks = seal_file(pub, "note.txt", data, expire_at=9_999_999_999)
        self.assertGreater(len(chunks), 1)
        with TemporaryDirectory() as tmp:
            store = RelayStore(Path(tmp) / "disk.bin")
            queue, _owner = store.create_queue()
            for chunk in chunks:
                self.assertNotIn(data, chunk)
                store.deposit(queue, chunk, ttl=60)
            self.assertNotIn(data, store.disk_bytes())
            self.assertNotIn(b"note.txt", store.disk_bytes())
            pulled = []
            while True:
                item = store.take(queue, store._owner[queue])
                if item is None:
                    break
                pulled.append(item)
            name, got = open_file(priv, pulled, now=1)
            self.assertEqual(name, "note.txt")
            self.assertEqual(got, data)

    def test_call_drops_when_relay_is_down(self) -> None:
        session = CallSession("http://127.0.0.1:9")
        self.assertFalse(hasattr(session, "peer_ip"))
        _priv, pub = generate_keypair()
        frame = session.frame(pub, "call-1", 1, b"\x00\x01audio")
        self.assertNotIn(b"127.0.0.1", frame)
        with self.assertRaises(CallDropped):
            session.send_frame("queue-does-not-matter-000000000000", "cap", frame)
        src = Path(__file__).with_name("call.py").read_text()
        self.assertNotIn("peer_ip", src)
        self.assertNotIn("direct_ip", src)
        self.assertIn("direct connection is forbidden", src)

    def test_forward_relay_does_not_see_queue_or_letter(self) -> None:
        bob_priv, bob_pub = generate_keypair()
        dest_priv, dest_pub = generate_keypair()
        letter = "երկու ցատկ".encode()
        user_env = seal(bob_pub, letter)
        with TemporaryDirectory() as tmp:
            dest = RelayStore(Path(tmp) / "dest.bin")
            queue, owner = dest.create_queue()
            route = seal_route(dest_pub, queue, user_env)
            self.assertNotIn(queue.encode(), route)
            self.assertNotIn(letter, route)
            with self.assertRaises(EnvelopeError):
                open_envelope(dest_priv, user_env)

            forward = RelayStore(Path(tmp) / "fwd.bin")
            httpd = serve(forward)
            port = httpd.server_address[1]
            try:
                body = json.dumps({"dest": "dest-relay.example", "blob_hex": route.hex()}).encode()
                self.assertNotIn(letter, body)
                self.assertNotIn(queue.encode(), body)
                req = urlrequest.Request(
                    f"http://127.0.0.1:{port}/v1/forward",
                    data=body,
                    method="POST",
                    headers={"Content-Type": "application/json"},
                )
                with urlrequest.urlopen(req) as res:
                    self.assertEqual(res.status, 202)
                self.assertNotIn(queue.encode(), forward.forward_bytes())
                self.assertNotIn(letter, forward.forward_bytes())
                _dest_url, blob = forward.take_forwards()[0]
                got_queue, got_env = open_route(dest_priv, blob)
                dest.deposit(got_queue, got_env, ttl=60)
                self.assertNotIn(letter, dest.disk_bytes())
                pulled = dest.take(queue, owner)
                self.assertEqual(open_envelope(bob_priv, pulled), letter)
            finally:
                httpd.shutdown()

    def test_device_file_hides_the_raw_key(self) -> None:
        priv, _pub = generate_keypair()
        raw = priv.private_bytes_raw()
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "key.json"
            save_private(path, raw, "long-passphrase")
            disk = path.read_bytes()
            self.assertNotIn(raw, disk)
            self.assertEqual(load_private(path, "long-passphrase"), raw)

    def test_both_languages_have_the_same_keys(self) -> None:
        self.assertEqual(set(STRINGS["hy"]), set(STRINGS["en"]))
        self.assertNotIn("100%", " ".join(STRINGS["hy"].values()))


if __name__ == "__main__":
    unittest.main()
