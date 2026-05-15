"""SSRF guard for outbound URL fetches.

Blocks:
- Non-http(s) schemes (file://, gopher://, etc.)
- Hostnames that resolve to private / loopback / link-local / reserved IPs
- Cloud metadata endpoints (169.254.169.254, AWS/Aliyun IMDS)
- Empty/malformed URLs

Allows public IPv4 and IPv6 by default. Optionally allow private (dev only) via
URL_CRAWL_ALLOW_PRIVATE=true.
"""
import ipaddress
import socket
from urllib.parse import urlparse

from app.core.config import settings


class UnsafeURLError(ValueError):
    pass


_BLOCKED_HOSTNAMES = {
    "metadata.google.internal",
    "metadata",
}


def assert_safe_url(url: str) -> None:
    if not url or not isinstance(url, str):
        raise UnsafeURLError("URL is empty")
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https"):
        raise UnsafeURLError(f"Unsupported scheme: {parsed.scheme!r}")
    host = (parsed.hostname or "").strip().lower()
    if not host:
        raise UnsafeURLError("URL has no host")
    if host in _BLOCKED_HOSTNAMES:
        raise UnsafeURLError(f"Blocked host: {host}")

    # Resolve all A/AAAA records — block if ANY is private
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as e:
        raise UnsafeURLError(f"DNS resolution failed: {e}") from e

    for info in infos:
        addr = info[4][0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            continue
        if settings.URL_CRAWL_ALLOW_PRIVATE:
            continue
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
            raise UnsafeURLError(f"URL resolves to non-public IP {addr}")
