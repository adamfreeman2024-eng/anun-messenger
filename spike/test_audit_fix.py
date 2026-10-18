"""Fixes from the read-only spike audit. Not an external audit."""

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib import request as urlrequest
from urllib.error import HTTPError

from spike.dest import serve_dest
from spike.envelope import generate_keypair
from spike.hop import seal_route
from spike.hopurl import HopUrlError, allowed_hop_url
from spike.relay import RelayStore, serve


class AuditFixTest(unittest.TestCase):
    def test_empty_token_is_rejected_and_ttl_is_not_30_seconds(self) -> None:
        _bob_priv, bob_pub = generate_keypair()
        dest_priv, dest_pub = generate_keypair()
        clock = {"t": 1_000.0}
        with TemporaryDirectory() as tmp:
            store = RelayStore(Path(tmp) / "dest.bin", now_fn=lambda: clock["t"])
            queue, owner = store.create_queue()
            token = store.issue_invite(queue, owner)
            httpd = serve_dest(store, dest_priv)
            try:
                port = httpd.server_address[1]
                empty = seal_route(dest_pub, queue, b"sealed-letter")
                req = urlrequest.Request(
                    f"http://127.0.0.1:{port}/v1/hop",
                    data=empty,
                    method="POST",
                )
                with self.assertRaises(HTTPError):
                    urlrequest.urlopen(req)
                self.assertIsNone(store.take(queue, owner))
                good = seal_route(dest_pub, queue, b"sealed-letter", token)
                req = urlrequest.Request(
                    f"http://127.0.0.1:{port}/v1/hop",
                    data=good,
                    method="POST",
                )
                with urlrequest.urlopen(req) as res:
                    self.assertEqual(res.status, 204)
                clock["t"] = 1_031.0
                self.assertEqual(store.take(queue, owner), b"sealed-letter")
            finally:
                httpd.shutdown()

    def test_forward_rejects_arbitrary_urls(self) -> None:
        with self.assertRaises(HopUrlError):
            allowed_hop_url("http://169.254.169.254/v1/hop")
        with self.assertRaises(HopUrlError):
            allowed_hop_url("http://127.0.0.1/latest/meta-data")
        with self.assertRaises(HopUrlError):
            allowed_hop_url("file:///etc/passwd")
        self.assertTrue(allowed_hop_url("http://127.0.0.1/v1/hop"))
        with TemporaryDirectory() as tmp:
            store = RelayStore(Path(tmp) / "fwd.bin")
            httpd = serve(store)
            try:
                body = json.dumps(
                    {"dest": "http://169.254.169.254/v1/hop", "blob_hex": "aa"}
                ).encode()
                req = urlrequest.Request(
                    f"http://127.0.0.1:{httpd.server_address[1]}/v1/forward",
                    data=body,
                    method="POST",
                    headers={"Content-Type": "application/json"},
                )
                with self.assertRaises(HTTPError) as caught:
                    urlrequest.urlopen(req)
                self.assertEqual(caught.exception.code, 400)
                self.assertEqual(store.take_forwards(), [])
            finally:
                httpd.shutdown()


if __name__ == "__main__":
    unittest.main()
