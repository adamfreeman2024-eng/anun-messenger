"""Destination relay. Opens only the hop wrapper, never the user letter."""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading

from spike.hop import open_route


class DestHandler(BaseHTTPRequestHandler):
    store = None
    private = None

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
            queue_id, envelope = open_route(self.private, blob)
            self.store.deposit(queue_id, envelope, ttl=30)
        except Exception:
            raw = json.dumps({"error": "bad hop"}).encode()
            self.send_response(400)
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            return
        self.send_response(204)
        self.end_headers()


def serve_dest(store, private, host: str = "127.0.0.1", port: int = 0) -> ThreadingHTTPServer:
    DestHandler.store = store
    DestHandler.private = private
    httpd = ThreadingHTTPServer((host, port), DestHandler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd
