"""Move hop blobs from the forward relay to the dest relay. No client address is added."""

import http.client
import socket
import ssl
from urllib.parse import urlparse

from spike.hopurl import HopUrlError, allowed_hop_url


class ForwardFailed(Exception):
    pass


class _PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, pin: str, port: int, timeout: float, server_name: str) -> None:
        super().__init__(pin, port, timeout=timeout, context=ssl.create_default_context())
        self._server_name = server_name

    def connect(self) -> None:
        sock = socket.create_connection((self.host, self.port), self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self._server_name)


def _post(url: str, pin: str, port: int, body: bytes, timeout: float) -> int:
    parsed = urlparse(url)
    if parsed.scheme == "https":
        conn = _PinnedHTTPS(pin, port, timeout, parsed.hostname or pin)
    else:
        conn = http.client.HTTPConnection(pin, port, timeout=timeout)
    try:
        conn.putrequest("POST", "/v1/hop")
        conn.putheader("Host", parsed.hostname or pin)
        conn.putheader("Content-Length", str(len(body)))
        conn.endheaders()
        conn.send(body)
        res = conn.getresponse()
        status = res.status
        res.read()
        return status
    finally:
        conn.close()


def pump(store, timeout: float = 3) -> int:
    sent = 0
    while True:
        item = store.pop_forward()
        if item is None:
            return sent
        dest, blob = item
        try:
            url, pin, port = allowed_hop_url(dest)
            status = _post(url, pin, port, blob, timeout)
        except (HopUrlError, OSError, TimeoutError) as exc:
            raise ForwardFailed("dest url rejected or relay down") from exc
        if status not in (200, 204):
            raise ForwardFailed("dest rejected the hop")
        sent += 1
