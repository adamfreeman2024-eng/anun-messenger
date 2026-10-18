"""Only a hop URL may be stored or opened by the forward relay."""

import ipaddress
import socket
from urllib.parse import urlparse


class HopUrlError(ValueError):
    pass


def allowed_hop_url(url: str) -> str:
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
    if parsed.scheme == "http" and host not in ("127.0.0.1", "localhost"):
        raise HopUrlError("http only on loopback")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise HopUrlError("unresolved host") from exc
    if not infos:
        raise HopUrlError("unresolved host")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_loopback:
            continue
        if parsed.scheme != "https" or _blocked(ip):
            raise HopUrlError("blocked address")
    return url


def _blocked(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return (
        ip.is_private
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
        or ip.is_loopback
    )
