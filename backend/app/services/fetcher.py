"""Fetch a web page safely: public IPs only (checked on every redirect hop), HTML only, size and time capped."""

import socket
import time
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

import httpx

from app.services.errors import IngestError
from app.services.url_safety import UnsafeUrlError, check_url, is_public_ip

HTML_TYPES = {"text/html", "application/xhtml+xml"}
DEFAULT_USER_AGENT = "KnowledgeInbox/0.1 (python-httpx)"

Resolver = Callable[[str, int], list[str]]


def system_resolver(host: str, port: int) -> list[str]:
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return [info[4][0] for info in infos]


@dataclass(frozen=True)
class FetchedPage:
    url: str
    html: str


def _ensure_public(url: str, resolver: Resolver) -> None:
    try:
        check_url(url)
    except UnsafeUrlError as exc:
        raise IngestError(str(exc)) from exc
    parts = urlsplit(url)
    host = parts.hostname or ""
    port = parts.port or (443 if parts.scheme == "https" else 80)
    try:
        addresses = resolver(host, port)
    except (socket.gaierror, UnicodeError) as exc:
        raise IngestError(f"Could not resolve host '{host}'") from exc
    if not addresses:
        raise IngestError(f"Could not resolve host '{host}'")
    # Note: httpx resolves again when connecting, so a DNS-rebinding attacker could still
    # race this check. Pinning the connection to the vetted IP closes that gap (see README).
    if not all(is_public_ip(a) for a in addresses):
        raise IngestError(f"Host '{host}' resolves to a private or reserved address")


def _decode(body: bytes, charset: str | None) -> str:
    for enc in (charset, "utf-8"):
        if enc:
            try:
                return body.decode(enc)
            except (LookupError, UnicodeDecodeError):
                continue
    return body.decode("utf-8", errors="replace")


def fetch_page(
    url: str,
    *,
    timeout_s: float,
    max_bytes: int,
    max_redirects: int,
    resolver: Resolver = system_resolver,
    transport: httpx.BaseTransport | None = None,
    user_agent: str = DEFAULT_USER_AGENT,
) -> FetchedPage:
    deadline = time.monotonic() + timeout_s
    current = url
    with httpx.Client(
        timeout=httpx.Timeout(timeout_s),
        follow_redirects=False,  # followed manually so every hop is re-vetted
        headers={"User-Agent": user_agent, "Accept": "text/html,application/xhtml+xml"},
        transport=transport,
    ) as client:
        for _ in range(max_redirects + 1):
            _ensure_public(current, resolver)
            host = urlsplit(current).hostname
            try:
                with client.stream("GET", current) as resp:
                    if resp.is_redirect:
                        location = resp.headers.get("location")
                        if not location:
                            raise IngestError(f"Redirect from {host} had no Location header")
                        current = urljoin(current, location)
                        continue
                    if not resp.is_success:
                        raise IngestError(f"Page returned HTTP {resp.status_code}")

                    content_type = resp.headers.get("content-type", "").split(";")[0].strip().lower()
                    if content_type not in HTML_TYPES:
                        raise IngestError(
                            f"Unsupported content type '{content_type or 'unknown'}'; only HTML pages can be saved"
                        )
                    declared = resp.headers.get("content-length")
                    if declared and declared.isdigit() and int(declared) > max_bytes:
                        raise IngestError(f"Page is larger than {max_bytes // 1_000_000} MB")

                    body = bytearray()
                    for chunk in resp.iter_bytes():
                        body.extend(chunk)
                        if len(body) > max_bytes:
                            raise IngestError(f"Page is larger than {max_bytes // 1_000_000} MB")
                        if time.monotonic() > deadline:
                            raise IngestError(f"Timed out after {timeout_s:g}s fetching the page")
                    return FetchedPage(url=current, html=_decode(bytes(body), resp.charset_encoding))
            except httpx.TimeoutException as exc:
                raise IngestError(f"Timed out after {timeout_s:g}s fetching the page") from exc
            except httpx.RequestError as exc:
                raise IngestError(f"Could not connect to {host}") from exc
    raise IngestError(f"Too many redirects (more than {max_redirects})")
