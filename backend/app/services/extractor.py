import html as html_lib
import re
from dataclasses import dataclass
from urllib.parse import urlsplit

import trafilatura

from app.services.errors import IngestError

_TITLE_TAG = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
MAX_TITLE = 200
MIN_TEXT_CHARS = 20


@dataclass(frozen=True)
class ExtractedPage:
    title: str
    text: str


def _clean_title(title: str | None) -> str | None:
    if not title:
        return None
    title = " ".join(html_lib.unescape(title).split())
    return title[:MAX_TITLE] or None


def extract_page(html: str, url: str) -> ExtractedPage:
    text = trafilatura.extract(html, url=url, include_comments=False, include_tables=True)
    if not text or len(text.strip()) < MIN_TEXT_CHARS:
        raise IngestError("No readable text found on the page")

    title = None
    meta = trafilatura.extract_metadata(html, default_url=url)
    if meta is not None:
        title = _clean_title(meta.title)
    if not title and (m := _TITLE_TAG.search(html)):
        title = _clean_title(m.group(1))
    return ExtractedPage(title=title or (urlsplit(url).hostname or url), text=text.strip())
