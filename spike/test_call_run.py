"""Three Opus frames in order. A dead relay drops the call."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from spike.call import CallDropped, CallSession
from spike.dest import serve_dest
from spike.envelope import generate_keypair
from spike.forward import pump
from spike.invite import pack_invite_v3
from spike.opus_frame import decode_frame, encode_frame
from spike.relay import RelayStore, serve
from spike.session import Session
from spike.test_opus import tone


class CallRunTest(unittest.TestCase):
    def test_three_frames_then_drop(self) -> None:
        packet = encode_frame(tone())
        bob_priv, bob_pub = generate_keypair()
        dest_priv, dest_pub = generate_keypair()
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
                base = f"http://127.0.0.1:{fwd_http.server_address[1]}"
                alice = Session(base)
                alice.accept(invite)
                alice.send_call(bob_pub, [packet, packet, packet], "call-3")
                self.assertEqual(pump(forward), 3)
                self.assertNotIn(tone(), dest.disk_bytes())
                call = CallSession(base)
                seqs = []
                for _ in range(3):
                    call_id, seq, audio = call.read_frame(bob_priv, dest.take(queue, owner))
                    self.assertEqual(call_id, "call-3")
                    seqs.append(seq)
                    self.assertEqual(len(decode_frame(audio)), 960 * 2)
                self.assertEqual(seqs, [1, 2, 3])
            finally:
                dest_http.shutdown()
                fwd_http.shutdown()

        dead = Session("http://127.0.0.1:9")
        dead.accept(pack_invite_v3("q" * 32, ["t" * 32], bob_pub, dest_pub, "http://127.0.0.1:9/v1/hop"))
        with self.assertRaises(CallDropped):
            dead.send_call(bob_pub, [packet], "dead")


if __name__ == "__main__":
    unittest.main()
