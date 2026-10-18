"""Destination relay. Opens only the hop wrapper, never the user letter."""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading

from spike.hop import open_route

HOP_TTL = 24 * 3600


def serve_dest(store, private, host: str = "127.0.0.1", port: int = 0) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args) -> None:
            return

        def do_POST(self) -> None:
            if self.path != "/v1/hop":
                self.send_response(404)
                self.end_headers()
                return
            length = int(self.headers.get("Content-Length", "0"))
            blob = self.rfile.read(length)
            try:
                queue_id, envelope, token = open_route(private, blob)
                if not token:
                    raise PermissionError("token required")
                got_queue, _send = store.redeem(token)
                if got_queue != queue_id:
                    raise PermissionError("token queue mismatch")
                store.deposit(queue_id, envelope, ttl=HOP_TTL)
            except Exception:
                raw = json.dumps({"error": "bad hop"}).encode()
                self.send_response(400)
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
                return
            self.send_response(204)
            self.end_headers()

    httpd = ThreadingHTTPServer((host, port), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd
