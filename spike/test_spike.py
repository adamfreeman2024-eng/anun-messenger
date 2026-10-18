"""Spike acceptance: one sealed letter, relay disk has no plaintext."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib import request as urlrequest
from urllib.error import HTTPError

from spike.envelope import EnvelopeError, generate_keypair, open_envelope, seal
from spike.relay import RelayStore, serve


PLAIN = "գաղտնի նամակ 18.10.2026".encode()


class SpikeTest(unittest.TestCase):
    def test_relay_cannot_read_the_letter(self) -> None:
        with TemporaryDirectory() as tmp:
            store = RelayStore(Path(tmp) / "envelopes.bin")
            httpd = serve(store)
            port = httpd.server_address[1]
            try:
                alice_priv, alice_pub = generate_keypair()
                bob_priv, bob_pub = generate_keypair()
                alice_q = self._create(port)
                bob_q = self._create(port)
                self.assertNotEqual(alice_q, bob_q)

                envelope = seal(bob_pub, PLAIN)
                self.assertNotIn(PLAIN, envelope)
                self._put(port, bob_q, envelope)

                disk = store.disk_bytes()
                self.assertNotIn(PLAIN, disk)
                self.assertNotIn(bob_priv.private_bytes_raw(), disk)
                self.assertNotIn(alice_priv.private_bytes_raw(), disk)

                pulled = self._get(port, bob_q)
                self.assertEqual(open_envelope(bob_priv, pulled), PLAIN)
                with self.assertRaises(EnvelopeError):
                    open_envelope(alice_priv, pulled)
            finally:
                httpd.shutdown()

    def test_relay_source_has_no_decrypt(self) -> None:
        src = Path(__file__).with_name("relay.py").read_text()
        self.assertNotIn("open_envelope", src)
        self.assertNotIn("private_key", src.lower())
        self.assertNotIn("AESGCM", src)

    def _create(self, port: int) -> str:
        req = urlrequest.Request(f"http://127.0.0.1:{port}/v1/queues", method="POST")
        with urlrequest.urlopen(req) as res:
            import json
            return json.load(res)["queue_id"]

    def _put(self, port: int, queue_id: str, body: bytes) -> None:
        req = urlrequest.Request(
            f"http://127.0.0.1:{port}/v1/queues/{queue_id}",
            data=body,
            method="PUT",
        )
        with urlrequest.urlopen(req) as res:
            self.assertIn(res.status, (200, 204))

    def _get(self, port: int, queue_id: str) -> bytes:
        try:
            with urlrequest.urlopen(f"http://127.0.0.1:{port}/v1/queues/{queue_id}") as res:
                return res.read()
        except HTTPError as exc:
            self.fail(exc.read().decode())
            raise


if __name__ == "__main__":
    unittest.main()
