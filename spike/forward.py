"""Move hop blobs from the forward relay to the dest relay. No client address is added."""

from urllib import request as urlrequest
from urllib.error import URLError


class ForwardFailed(Exception):
    pass


def pump(store, timeout: float = 3) -> int:
    sent = 0
    for dest, blob in store.take_forwards():
        req = urlrequest.Request(dest, data=blob, method="POST")
        try:
            with urlrequest.urlopen(req, timeout=timeout) as res:
                if res.status not in (200, 204):
                    raise ForwardFailed("dest rejected the hop")
        except (URLError, TimeoutError, OSError) as exc:
            raise ForwardFailed("dest relay down; direct connection is forbidden") from exc
        sent += 1
    return sent
