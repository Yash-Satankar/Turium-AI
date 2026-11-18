"""SSRF guards shared by request validation (syntax, IP literals) and the fetcher (resolved IPs)."""

import ipaddress
from urllib.parse import urlsplit


class UnsafeUrlError(ValueError):
    pass


def is_public_ip(value: str) -> bool:
    try:
        ip = ipaddress.ip_address(value)
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


def check_url(url: str) -> str:
    """Checks everything knowable without network access. Returns the stripped URL."""
    url = url.strip()
    try:
        parts = urlsplit(url)
        host = parts.hostname
        parts.port  # raises ValueError on an invalid port
    except ValueError as exc:
        raise UnsafeUrlError("URL is malformed") from exc

    if parts.scheme.lower() not in ("http", "https"):
        raise UnsafeUrlError("Only http:// and https:// URLs are supported")
    if not host:
        raise UnsafeUrlError("URL must include a host name")
    if parts.username or parts.password:
        raise UnsafeUrlError("URLs with embedded credentials are not allowed")

    host = host.rstrip(".").lower()
    if host == "localhost" or host.endswith(".localhost"):
        raise UnsafeUrlError("URLs pointing at localhost are not allowed")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return url  # a domain name; resolved IPs are checked at fetch time
    if not is_public_ip(host):
        raise UnsafeUrlError("URLs pointing at private, loopback or link-local addresses are not allowed")
    return url
