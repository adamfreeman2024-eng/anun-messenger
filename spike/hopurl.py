"""Only a hop URL may be stored or opened by the forward relay."""

import ipaddress
import os
import socket
from urllib.parse import urlparse


class HopUrlError(ValueError):
    pass


_SHARED = ipaddress.ip_network("100.64.0.0/10")


def allowed_hop_url(url: str) -> tuple[str, str, int]:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise HopUrlError("bad scheme")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise HopUrlError("bad url")
    if parsed.path != "/v1/hop":
        raise HopUrlError("bad path")
    host = parsed.hostname
    if not host or host != host.lower():
        raise HopUrlError("bad host")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise HopUrlError("unresolved host") from exc
    if not infos:
        raise HopUrlError("unresolved host")
    pins: list[str] = []
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_loopback:
            if parsed.scheme != "http" or os.environ.get("ANUN_ALLOW_LOOPBACK") != "1":
                raise HopUrlError("loopback blocked")
            pins.append(str(ip))
            continue
        if not ip.is_global or ip in _SHARED:
            raise HopUrlError("blocked address")
        pins.append(str(ip))
    return url, pins[0], port
