"""Polite, safe downloading of the MedlinePlus topics file: one file from NLM, not a crawl.

Safety rules enforced here (tested in test_ingestion_safety.py):
- only https://medlineplus.gov, checked before every request including each redirect hop;
- an existing file is never replaced unless the caller says so;
- the download goes to a temporary file, is checked to be a MedlinePlus topics XML, and only then
  swapped into place, so a bad or interrupted download cannot corrupt an existing file;
- a size cap stops a runaway download.
"""
import time
import xml.etree.ElementTree as ET
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import httpx

OFFICIAL_HOST = "medlineplus.gov"
TOPICS_URL = "https://" + OFFICIAL_HOST + "/xml/mplus_topics_{stamp}.xml"
USER_AGENT = "VitalNest-ingestion/0.1 (educational health-information project)"
MAX_BYTES = 200 * 1024 * 1024
MAX_REDIRECTS = 3


def make_client() -> httpx.Client:
    # Redirects are followed by hand in download() so every hop can be checked first.
    return httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=60, follow_redirects=False)


def _require_official(url: str) -> None:
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.hostname != OFFICIAL_HOST or parts.port not in (None, 443):
        raise ValueError(f"Refusing to download from a non-official URL: {url!r} (only https://{OFFICIAL_HOST})")


def find_latest_topics_url(
    client: httpx.Client, today: date, max_back: int = 7, pause: float = 0.0
) -> str:
    """MedlinePlus publishes Tuesday to Saturday, so look back from today for the newest file."""
    for offset in range(max_back + 1):
        url = TOPICS_URL.format(stamp=(today - timedelta(days=offset)).isoformat())
        if client.head(url).status_code == 200:
            return url
        if pause:
            time.sleep(pause)
    raise LookupError(f"No MedlinePlus topics file found in the last {max_back} days")


def _validate_topics_xml(path: Path) -> None:
    if path.stat().st_size == 0:
        raise ValueError("Downloaded file is empty")
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as error:
        raise ValueError(f"Downloaded file is not valid XML: {error}") from error
    if root.tag != "health-topics":
        raise ValueError(f"Downloaded file is not a MedlinePlus topics file (root element: {root.tag!r})")


def _save_body(response: httpx.Response, partial: Path) -> None:
    written = 0
    with partial.open("wb") as handle:
        for block in response.iter_bytes():
            written += len(block)
            if written > MAX_BYTES:
                raise ValueError(f"Download is too large (more than {MAX_BYTES} bytes); stopped")
            handle.write(block)


def download(client: httpx.Client, url: str, destination: Path, overwrite: bool = False) -> None:
    _require_official(url)
    if destination.exists() and not overwrite:
        raise FileExistsError(f"{destination} already exists; pass --force to replace it")
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix + ".part")
    try:
        current = url
        for _ in range(MAX_REDIRECTS + 1):
            _require_official(current)
            with client.stream("GET", current, follow_redirects=False) as response:
                if response.is_redirect:
                    current = urljoin(current, response.headers.get("location", ""))
                    continue
                response.raise_for_status()
                _save_body(response, partial)
                break
        else:
            raise ValueError("Too many redirects")
        _validate_topics_xml(partial)
        partial.replace(destination)
    finally:
        partial.unlink(missing_ok=True)
