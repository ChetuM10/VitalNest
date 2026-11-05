"""Polite, safe download of individual WHO fact-sheet and CDC pages (a reviewed list, not a crawl).

Safety rules enforced here (tested in test_who.py):
- only https://www.who.int/news-room/fact-sheets/detail/<name> (WHO) or https://www.cdc.gov/<path>.html (CDC),
  checked before every request including each redirect hop;
- the site's robots.txt is read once and every page and redirect hop is checked against it;
- at least `delay` seconds between network requests; cached pages cause no request at all;
- an existing cached page is never replaced unless the caller says so;
- the page is only saved if it looks like a fact sheet, and a size cap stops a runaway download.
"""
import re
import time
import urllib.robotparser
from pathlib import Path
from urllib.parse import quote, urljoin, urlsplit

import httpx

from vitalnest_ingest.files import write_text_atomic

HOST = "www.who.int"
PATH_PREFIX = "/news-room/fact-sheets/detail/"
ROBOTS_URL = f"https://{HOST}/robots.txt"
USER_AGENT = "VitalNest-ingestion/0.1 (educational health-information project)"
MAX_BYTES = 5 * 1024 * 1024
MAX_REDIRECTS = 3
DEFAULT_DELAY = 2.0
SLUG_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9()\-]*$")


class FetchRefused(Exception):
    """The page was not downloaded because a safety rule said no."""


def make_client() -> httpx.Client:
    # Redirects are followed by hand so every hop can be checked first.
    return httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=60, follow_redirects=False)


def fact_sheet_url(slug: str) -> str:
    if not SLUG_PATTERN.match(slug):
        raise FetchRefused(f"Not a valid fact-sheet name: {slug!r}")
    return f"https://{HOST}{PATH_PREFIX}{quote(slug, safe='()-')}"


CDC_HOST = "www.cdc.gov"
CDC_PATH_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_\-]*(?:/[a-z0-9][a-z0-9_\-]*)*\.html$")


def cdc_url(path: str) -> str:
    if not CDC_PATH_PATTERN.match(path) or "__" in path:  # "__" stands for "/" in saved file names
        raise FetchRefused(f"Not a valid CDC page path: {path!r}")
    return f"https://{CDC_HOST}/{path}"


def _require_host(url: str, host: str, path_ok) -> None:
    parts = urlsplit(url)
    if (
        parts.scheme != "https"
        or parts.hostname != host
        or parts.port not in (None, 443)
        or parts.username is not None
        or not path_ok(parts.path)
        or ".." in parts.path
    ):
        raise FetchRefused(f"Refusing a URL outside the approved pages of https://{host}: {url!r}")


class _PoliteFetcher:
    """Shared rules; subclasses say which URLs are acceptable and what a good page looks like."""

    host: str
    page_name: str  # for messages, e.g. "WHO fact sheet"

    def __init__(self, client: httpx.Client, cache_dir: Path, delay: float = DEFAULT_DELAY, sleep=time.sleep):
        self._client = client
        self._cache_dir = Path(cache_dir)
        self._delay = delay
        self._sleep = sleep
        self._robots: urllib.robotparser.RobotFileParser | None = None
        self._requests_made = 0

    # --- subclass hooks ---
    def _url(self, key: str) -> str: ...
    def _cache_name(self, key: str) -> str: ...
    def _path_ok(self, path: str) -> bool: ...
    def _looks_valid(self, html: str) -> bool: ...

    def cache_path(self, key: str) -> Path:
        self._url(key)  # validates the name, so it can never contain a path traversal
        return self._cache_dir / self._cache_name(key)

    def _pause(self) -> None:
        if self._requests_made and self._delay:
            self._sleep(self._delay)
        self._requests_made += 1

    def _load_robots(self) -> urllib.robotparser.RobotFileParser:
        if self._robots is None:
            self._pause()
            response = self._client.get(f"https://{self.host}/robots.txt")
            response.raise_for_status()
            parser = urllib.robotparser.RobotFileParser()
            parser.parse(response.text.splitlines())
            self._robots = parser
        return self._robots

    def fetch(self, key: str, overwrite: bool = False) -> tuple[Path, bool]:
        """Return (cached file, downloaded). A cached file is used without touching the network."""
        destination = self.cache_path(key)
        if destination.exists() and not overwrite:
            return destination, False
        html = self._download(self._url(key))
        destination.parent.mkdir(parents=True, exist_ok=True)
        write_text_atomic(destination, html)
        return destination, True

    def _download(self, url: str) -> str:
        current = url
        for _ in range(MAX_REDIRECTS + 1):
            _require_host(current, self.host, self._path_ok)
            if not self._load_robots().can_fetch(USER_AGENT, current):
                raise FetchRefused(f"robots.txt does not allow {current}")
            self._pause()
            with self._client.stream("GET", current) as response:
                if response.is_redirect:
                    current = urljoin(current, response.headers.get("location", ""))
                    continue
                response.raise_for_status()
                body = bytearray()
                for block in response.iter_bytes():
                    body.extend(block)
                    if len(body) > MAX_BYTES:
                        raise ValueError(f"Page is too large (more than {MAX_BYTES} bytes); stopped")
                html = bytes(body).decode(response.encoding or "utf-8", errors="replace")
            if not self._looks_valid(html):
                raise ValueError(f"{current} does not look like a {self.page_name}; not saved")
            return html
        raise ValueError("Too many redirects")


class FactSheetFetcher(_PoliteFetcher):
    host = HOST
    page_name = "WHO fact sheet"

    def _url(self, key: str) -> str:
        return fact_sheet_url(key)

    def _cache_name(self, key: str) -> str:
        return f"{key}.html"

    def _path_ok(self, path: str) -> bool:
        return path.startswith(PATH_PREFIX)

    def _looks_valid(self, html: str) -> bool:
        return 'class="sf-detail-body-wrapper"' in html


class CdcFetcher(_PoliteFetcher):
    """Fetches www.cdc.gov pages by path, e.g. "diabetes/about/index.html"."""

    host = CDC_HOST
    page_name = "CDC page"

    def _url(self, key: str) -> str:
        return cdc_url(key)

    def _cache_name(self, key: str) -> str:
        return key.replace("/", "__")

    def _path_ok(self, path: str) -> bool:
        return path.endswith(".html")

    def _looks_valid(self, html: str) -> bool:
        return "cdc-main" in html
