import httpx
import pytest

from app.services.errors import IngestError
from app.services.extractor import extract_page
from app.services.fetcher import fetch_page
from app.services.url_safety import UnsafeUrlError, check_url

from .conftest import public_resolver

ARTICLE = """<html><head><title>Sourdough Guide</title></head><body>
<nav>Home | About | Contact</nav>
<article><h1>Sourdough Guide</h1>
<p>Feed the starter twice a day with equal weights of flour and water. A healthy starter doubles within six hours.</p>
<p>Bake at 250 degrees Celsius in a covered Dutch oven for the first twenty minutes.</p>
</article><footer>Copyright 2026</footer></body></html>"""


@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com/x",
        "javascript:alert(1)",
        "http://localhost:8000/",
        "http://api.localhost/",
        "http://127.0.0.1/",
        "http://10.0.0.5/",
        "http://192.168.1.1/",
        "http://169.254.169.254/latest/meta-data/",
        "http://[::1]/",
        "http://[::ffff:127.0.0.1]/",
        "http://0.0.0.0/",
        "http://user:pass@example.com/",
        "not a url",
        "http://example.com:99999/",
    ],
)
def test_check_url_rejects(url):
    with pytest.raises(UnsafeUrlError):
        check_url(url)


@pytest.mark.parametrize("url", ["https://example.com/post", "http://8.8.8.8/", " https://example.com "])
def test_check_url_accepts(url):
    assert check_url(url) == url.strip()


def _fetch(handler, resolver=public_resolver, **kw):
    return fetch_page(
        "https://example.com/post",
        timeout_s=kw.get("timeout_s", 10),
        max_bytes=kw.get("max_bytes", 2_000_000),
        max_redirects=kw.get("max_redirects", 5),
        user_agent="KnowledgeInbox-test/0.1",
        resolver=resolver,
        transport=httpx.MockTransport(handler),
    )


def test_fetch_and_extract():
    page = _fetch(lambda r: httpx.Response(200, html=ARTICLE))
    extracted = extract_page(page.html, page.url)
    assert extracted.title == "Sourdough Guide"
    assert "starter twice a day" in extracted.text
    assert "Home | About" not in extracted.text


def test_dns_to_private_ip_is_blocked():
    with pytest.raises(IngestError, match="private"):
        _fetch(lambda r: httpx.Response(200, html=ARTICLE), resolver=lambda h, p: ["10.1.2.3"])


def test_redirect_to_private_ip_literal_is_blocked():
    def handler(request):
        return httpx.Response(302, headers={"Location": "http://169.254.169.254/latest/"})

    with pytest.raises(IngestError, match="private|link-local"):
        _fetch(handler)


def test_redirect_is_followed():
    def handler(request):
        if request.url.path == "/post":
            return httpx.Response(301, headers={"Location": "/moved"})
        return httpx.Response(200, html=ARTICLE)

    assert _fetch(handler).url == "https://example.com/moved"


def test_redirect_loop():
    with pytest.raises(IngestError, match="Too many redirects"):
        _fetch(lambda r: httpx.Response(302, headers={"Location": "/again"}), max_redirects=3)


def test_non_2xx():
    with pytest.raises(IngestError, match="HTTP 404"):
        _fetch(lambda r: httpx.Response(404, html="nope"))


def test_non_html():
    with pytest.raises(IngestError, match="application/pdf"):
        _fetch(lambda r: httpx.Response(200, content=b"%PDF", headers={"Content-Type": "application/pdf"}))


def test_body_too_large():
    big = "<html><body>" + "a" * 5000 + "</body></html>"
    with pytest.raises(IngestError, match="larger than"):
        _fetch(lambda r: httpx.Response(200, html=big), max_bytes=1000)


def test_timeout():
    def handler(request):
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(IngestError, match="Timed out"):
        _fetch(handler)


def test_unreachable():
    def handler(request):
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(IngestError, match="Could not connect"):
        _fetch(handler)


def test_no_extractable_text():
    with pytest.raises(IngestError, match="No readable text"):
        extract_page("<html><body><script>x()</script></body></html>", "https://example.com")
