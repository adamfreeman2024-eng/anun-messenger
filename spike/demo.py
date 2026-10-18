"""One local run. Writes a WAV. Does not play sound: this machine has no card."""

from pathlib import Path

from spike.dest import serve_dest
from spike.device import create_device, open_device
from spike.envelope import generate_keypair
from spike.filebox import open_file
from spike.forward import pump
from spike.invite import pack_invite_v3
from spike.opus_frame import decode_frame, encode_frame
from spike.relay import RelayStore, serve
from spike.session import Session, open_letter
from spike.strings import text
from spike.test_opus import tone
from spike.wavout import write_wav


def run(out_dir: Path, lang: str = "hy") -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    packet = encode_frame(tone())
    dest_priv, dest_pub = generate_keypair()
    bob_priv, bob_pub = create_device(out_dir / "bob.key", "bob-pass")
    loaded, _pub = open_device(out_dir / "bob.key", "bob-pass")
    dest = RelayStore(out_dir / "dest.bin")
    forward = RelayStore(out_dir / "fwd.bin")
    queue, owner = dest.create_queue()
    tokens = [dest.issue_invite(queue, owner) for _ in range(4)]
    dest_http = serve_dest(dest, dest_priv)
    fwd_http = serve(forward)
    try:
        hop = f"http://127.0.0.1:{dest_http.server_address[1]}/v1/hop"
        invite = pack_invite_v3(queue, tokens, bob_pub, dest_pub, hop)
        alice = Session(f"http://127.0.0.1:{fwd_http.server_address[1]}", lang=lang)
        alice.accept(invite)
        alice.send_letter(bob_pub, "տեղային".encode(), expire_at=9_999_999_999)
        alice.send_file(bob_pub, "note.bin", b"file-bytes", expire_at=9_999_999_999)
        alice.send_call(bob_pub, [packet, packet], "local")
        sent = pump(forward)
        letter = open_letter(loaded, dest.take(queue, owner))
        file_env = dest.take(queue, owner)
        name, data = open_file(bob_priv, [file_env], now=1)
        frames = 0
        while True:
            item = dest.take(queue, owner)
            if item is None:
                break
            frames += 1
        wav = out_dir / "frame.wav"
        write_wav(wav, decode_frame(packet))
        return {
            "sent": sent,
            "letter": letter["text"] if letter else "",
            "file": name,
            "file_ok": data == b"file-bytes",
            "frames": frames,
            "wav": str(wav),
            "alert": text(lang, "not_audited"),
            "private_on_disk": bob_priv.private_bytes_raw() in dest.disk_bytes(),
        }
    finally:
        dest_http.shutdown()
        fwd_http.shutdown()
