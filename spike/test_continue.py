"""Call frame crosses two relays. Notification and QR carry no letter."""

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib import request as urlrequest

from spike.call import CallSession
from spike.dest import serve_dest
from spike.envelope import generate_keypair
from spike.forward import pump
from spike.hop import seal_route
from spike.invite import pack_invite, qr_payload
from spike.notify import notification
from spike.relay import RelayStore, serve


AUDIO = b"AUDIO-FRAME-18"


class ContinueTest(unittest.TestCase):
    def test_audio_crosses_two_relays_and_stays_sealed(self) -> None:
        bob_priv, bob_pub = generate_keypair()
        dest_priv, dest_pub = generate_keypair()
        with TemporaryDirectory() as tmp:
            dest_store = RelayStore(Path(tmp) / "dest.bin")
            queue, owner = dest_store.create_queue()
            dest_http = serve_dest(dest_store, dest_priv)
            forward_store = RelayStore(Path(tmp) / "fwd.bin")
            forward_http = serve(forward_store)
            try:
                dest_port = dest_http.server_address[1]
                fwd_port = forward_http.server_address[1]
                session = CallSession(f"http://127.0.0.1:{fwd_port}")
                frame = session.frame(bob_pub, "c1", 1, AUDIO)
                token = dest_store.issue_invite(queue, owner)
                route = seal_route(dest_pub, queue, frame, token)
                body = json.dumps(
                    {
                        "dest": f"http://127.0.0.1:{dest_port}/v1/hop",
                        "blob_hex": route.hex(),
                    }
                ).encode()
                self.assertNotIn(AUDIO, body)
                self.assertNotIn(queue.encode(), body)
                req = urlrequest.Request(
                    f"http://127.0.0.1:{fwd_port}/v1/forward",
                    data=body,
                    method="POST",
                    headers={"Content-Type": "application/json"},
                )
                with urlrequest.urlopen(req) as res:
                    self.assertEqual(res.status, 202)
                self.assertEqual(pump(forward_store), 1)
                self.assertNotIn(AUDIO, forward_store.disk_bytes())
                self.assertNotIn(AUDIO, dest_store.disk_bytes())
                pulled = dest_store.take(queue, owner)
                self.assertEqual(session.open_frame(bob_priv, pulled), AUDIO)
            finally:
                dest_http.shutdown()
                forward_http.shutdown()

    def test_notification_has_no_letter(self) -> None:
        alert = notification("hy")["alert"]
        self.assertEqual(alert, "նոր ծրար")
        self.assertNotIn("գաղտնի", alert)

    def test_qr_payload_is_the_invite_only(self) -> None:
        _priv, pub = generate_keypair()
        invite = pack_invite("q" * 32, "t" * 32, pub)
        self.assertEqual(qr_payload(invite), invite)
        self.assertNotIn(b"private", invite.encode())


if __name__ == "__main__":
    unittest.main()
