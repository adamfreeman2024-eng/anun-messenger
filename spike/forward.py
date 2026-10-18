"""Move hop blobs from the forward relay to the dest relay. No client address is added."""

from urllib import request as urlrequest
from urllib.error import URLError

from spike.hopurl import HopUrlError, allowed_hop_url


class ForwardFailed(Exception):
    pass


class _NoRedirect(urlrequest.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ForwardFailed("redirect forbidden")


def pump(store, timeout: float = 3) -> int:
    sent = 0
    opener = urlrequest.build_opener(_NoRedirect)
    for dest, blob in store.take_forwards():
        try:
            dest = allowed_hop_url(dest)
        except HopUrlError as exc:
            raise ForwardFailed("dest url rejected") from exc
        req = urlrequest.Request(dest, data=blob, method="POST")
        try:
            with opener.open(req, timeout=timeout) as res:
                if res.status not in (200, 204):
                    raise ForwardFailed("dest rejected the hop")
        except (URLError, TimeoutError, OSError) as exc:
            raise ForwardFailed("dest relay down; direct connection is forbidden") from exc
        sent += 1
    return sent
