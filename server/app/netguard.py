"""Who is asking: the real client address, and whether it may use the server.

By default only loopback, private LAN and link-local clients are served. This
stops the usual self-hosting accident (a router port forward exposing the
library, or an unclaimed first-run setup, to the internet). Public clients need
LINXIV_WEB_ALLOW_EXTERNAL=true.

Behind a reverse proxy the TCP peer is the proxy. X-Forwarded-For is read only
when the peer is listed in LINXIV_WEB_TRUSTED_PROXIES (IPs or CIDRs), and then
from the right: the first hop that is not a trusted proxy is the client. The
left end of the header is whatever the client sent, so it is never trusted.
"""

from __future__ import annotations

import ipaddress
import logging
import time
from collections.abc import Iterable

from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

log = logging.getLogger(__name__)

Network = ipaddress.IPv4Network | ipaddress.IPv6Network
# One "blocked" log line per address per interval; bounded so a scanner rotating
# addresses can't grow memory or fill the log.
BLOCK_LOG_INTERVAL = 60
BLOCK_LOG_MAX = 1024


def parse_networks(entries: Iterable[str]) -> list[Network]:
    """`10.0.0.1`, `172.16.0.0/12`, `::1` ... -> networks. Bad entries raise ValueError."""
    out = []
    for e in entries:
        try:
            out.append(ipaddress.ip_network(e.strip(), strict=False))
        except ValueError:
            raise ValueError(
                f"LINXIV_WEB_TRUSTED_PROXIES: {e.strip()!r} is not an IP or CIDR"
            ) from None
    return out


def _ip(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        ip = ipaddress.ip_address(host.strip())
    except ValueError:
        return None
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        return ip.ipv4_mapped
    return ip


def _trusted(host: str, proxies: list[Network]) -> bool:
    ip = _ip(host)
    return ip is not None and any(ip in net for net in proxies)


def client_ip(peer: str, forwarded_for: str | None, proxies: list[Network]) -> str:
    """The client's address as seen through any trusted proxies."""
    if not forwarded_for or not _trusted(peer, proxies):
        return peer
    hops = [h.strip() for h in forwarded_for.split(",") if h.strip()]
    for hop in reversed(hops):
        if not _trusted(hop, proxies):
            return hop
    # Every hop is a trusted proxy: the leftmost one is as far back as we can see.
    return hops[0] if hops else peer


def is_private(host: str) -> bool:
    """Loopback, private (RFC 1918, ULA) or link-local. Unparseable = public (fail closed)."""
    ip = _ip(host)
    return ip is not None and (ip.is_loopback or ip.is_private or ip.is_link_local)


class ClientGuard(BaseHTTPMiddleware):
    """Sets request.state.client_ip; answers 403 to public clients unless allowed."""

    def __init__(self, app, *, allow_external: bool, trusted_proxies: list[Network]):
        super().__init__(app)
        self.allow_external = allow_external
        self.proxies = trusted_proxies
        self._logged: dict[str, float] = {}

    def _log_blocked(self, host: str, path: str) -> None:
        now = time.monotonic()
        last = self._logged.get(host)
        if last is not None and now - last < BLOCK_LOG_INTERVAL:
            return
        self._logged[host] = now
        if len(self._logged) > BLOCK_LOG_MAX:
            cutoff = now - BLOCK_LOG_INTERVAL
            self._logged = {k: v for k, v in self._logged.items() if v >= cutoff}
            if len(self._logged) > BLOCK_LOG_MAX:
                newest = sorted(self._logged.items(), key=lambda kv: kv[1], reverse=True)
                self._logged = dict(newest[:BLOCK_LOG_MAX])
        log.warning("blocked external request from %s to %s", host, path)

    async def dispatch(self, request, call_next):
        peer = request.client.host if request.client else ""
        host = client_ip(peer, request.headers.get("x-forwarded-for"), self.proxies)
        request.state.client_ip = host or "unknown"
        if not self.allow_external and not is_private(host):
            self._log_blocked(host or "unknown", request.url.path)
            return JSONResponse(
                {
                    "detail": "External requests are disabled. Set LINXIV_WEB_ALLOW_EXTERNAL=true "
                    "to serve public clients."
                },
                status_code=403,
            )
        return await call_next(request)
