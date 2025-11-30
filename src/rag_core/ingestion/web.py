from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Iterator, List, Optional, Set
from urllib.parse import urljoin, urldefrag, urlparse
import re
import time

import requests
from bs4 import BeautifulSoup

from .base import IngestionSource, IngestItem


def _html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    # remove non-content
    for tag in soup(["script", "style", "noscript", "iframe", "header", "footer", "nav"]):
        tag.decompose()
    text = soup.get_text("\n", strip=True)
    return text


def _fetch(url: str, *, timeout: float = 20.0, headers: Optional[dict] = None) -> Optional[str]:
    try:
        h = {"User-Agent": "OneLiteFeather-RAG/1.0"}
        if headers:
            h.update(headers)
        resp = requests.get(url, timeout=timeout, headers=h)
        if resp.status_code >= 400:
            return None
        ctype = resp.headers.get("content-type", "")
        if "text/html" not in ctype and "xml" not in ctype:
            return None
        return resp.text
    except Exception:
        return None


@dataclass
class UrlSource(IngestionSource):
    urls: List[str]

    def stream(self) -> Iterable[IngestItem]:
        for u in self.urls:
            html = _fetch(u)
            if not html:
                continue
            text = _html_to_text(html)
            if not text.strip():
                continue
            yield IngestItem(doc_id=u, text=text, metadata={"source_url": u}, checksum=str(hash(text)))


@dataclass
class SitemapSource(IngestionSource):
    sitemap_url: str
    limit: Optional[int] = None

    def stream(self) -> Iterable[IngestItem]:
        xml = _fetch(self.sitemap_url)
        if not xml:
            return []
        urls: List[str] = re.findall(r"<loc>(.*?)</loc>", xml)
        if self.limit:
            urls = urls[: self.limit]
        return UrlSource(urls=urls).stream()


@dataclass
class WebsiteCrawlerSource(IngestionSource):
    start_urls: List[str]
    allowed_prefixes: Optional[List[str]] = None
    max_pages: int = 100
    sleep_seconds: float = 0.0

    def _allowed(self, url: str) -> bool:
        if not self.allowed_prefixes:
            # default: stay within the same host(s) as start_urls
            hosts = {urlparse(u).netloc for u in self.start_urls}
            return urlparse(url).netloc in hosts
        return any(url.startswith(p) for p in self.allowed_prefixes)

    def stream(self) -> Iterable[IngestItem]:
        seen: Set[str] = set()
        queue: List[str] = []
        for u in self.start_urls:
            queue.append(u)
        out: List[IngestItem] = []
        while queue and len(seen) < self.max_pages:
            url = queue.pop(0)
            url = urldefrag(url)[0]
            if url in seen or not self._allowed(url):
                continue
            seen.add(url)
            html = _fetch(url)
            if not html:
                continue
            text = _html_to_text(html)
            if text.strip():
                out.append(IngestItem(doc_id=url, text=text, metadata={"source_url": url}, checksum=str(hash(text))))
            # extract links
            try:
                soup = BeautifulSoup(html, "html.parser")
                for a in soup.find_all("a", href=True):
                    href = urljoin(url, a["href"]) if not a["href"].startswith("http") else a["href"]
                    href = urldefrag(href)[0]
                    if href not in seen and self._allowed(href):
                        queue.append(href)
            except Exception:
                pass
            if self.sleep_seconds:
                time.sleep(self.sleep_seconds)
        return out

