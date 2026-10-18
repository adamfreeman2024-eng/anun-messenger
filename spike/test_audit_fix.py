"""Fixes from the read-only spike audit. Not an external audit."""

import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib import request as urlrequest
from urllib.error import HTTPError

from spike.dest import serve_dest
from spike.envelope import generate_keypair
from spike.hop import seal_route
from spike.forward import ForwardFailed, pump
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
        os.environ["ANUN_ALLOW_LOOPBACK"] = "1"
        with self.assertRaises(HopUrlError):
            allowed_hop_url("http://169.254.169.254/v1/hop")
        with self.assertRaises(HopUrlError):
            allowed_hop_url("https://100.100.100.200/v1/hop")
        with self.assertRaises(HopUrlError):
            allowed_hop_url("https://127.0.0.1/v1/hop")
        with self.assertRaises(HopUrlError):
            allowed_hop_url("http://127.0.0.1/latest/meta-data")
        with self.assertRaises(HopUrlError):
            allowed_hop_url("file:///etc/passwd")
        self.assertEqual(allowed_hop_url("http://127.0.0.1/v1/hop")[1], "127.0.0.1")
        saved = os.environ.pop("ANUN_ALLOW_LOOPBACK")
        try:
            with self.assertRaises(HopUrlError):
                allowed_hop_url("http://127.0.0.1/v1/hop")
        finally:
            os.environ["ANUN_ALLOW_LOOPBACK"] = saved
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

    def test_mismatch_does_not_burn_the_token(self) -> None:
        dest_priv, dest_pub = generate_keypair()
        with TemporaryDirectory() as tmp:
            store = RelayStore(Path(tmp) / "dest.bin")
            queue_a, owner_a = store.create_queue()
            queue_b, _owner_b = store.create_queue()
            token = store.issue_invite(queue_a, owner_a)
            httpd = serve_dest(store, dest_priv)
            try:
                blob = seal_route(dest_pub, queue_b, b"letter", token)
                req = urlrequest.Request(
                    f"http://127.0.0.1:{httpd.server_address[1]}/v1/hop",
                    data=blob,
                    method="POST",
                )
                with self.assertRaises(HTTPError):
                    urlrequest.urlopen(req)
                self.assertEqual(store.invite_queue(token), queue_a)
            finally:
                httpd.shutdown()

    def test_one_bad_forward_leaves_the_rest(self) -> None:
        os.environ["ANUN_ALLOW_LOOPBACK"] = "1"
        with TemporaryDirectory() as tmp:
            store = RelayStore(Path(tmp) / "fwd.bin")
            store.hold_forward("http://127.0.0.1:9/v1/hop", b"bad")
            store.hold_forward("http://127.0.0.1:9/v1/hop", b"kept")
            with self.assertRaises(ForwardFailed):
                pump(store)
            left = store.take_forwards()
            self.assertEqual([blob for _url, blob in left], [b"kept"])


if __name__ == "__main__":
    unittest.main()
