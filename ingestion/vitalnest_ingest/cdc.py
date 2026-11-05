"""Parse saved CDC pages from a reviewed list (see docs/sources.md).

Only the main content of each page is read. A page is skipped, never summarised, when it carries a
copyright or permission notice (the project owner's rule), and tables, figures, images, video and
the page furniture around the article (date stamps, share buttons, related links, "Content Source")
are dropped.
"""
import re
from html import unescape
from pathlib import Path

from vitalnest_ingest.cleaning import html_to_text
from vitalnest_ingest.models import Document
from vitalnest_ingest.pages import CDC_HOST, CDC_PATH_PATTERN, cdc_url

SOURCE_NAME = "CDC"
LICENCE = (
    "Public domain (U.S. government work) unless a page says otherwise; pages with a copyright notice "
    "are not used. Text extracted by VitalNest from CDC web pages; not endorsed by CDC."
)
# The label on a source card is built from the text after "from" (see frontend SourceCards).
ATTRIBUTION = "Content from the Centers for Disease Control and Prevention"
MIN_TEXT_CHARS = 400

_MAIN = re.compile(r"<main\b.*?</main>", re.S | re.I)
_TITLE = re.compile(r"<title>(.*?)</title>", re.S | re.I)
_CANONICAL = re.compile(r'<link[^>]*rel="canonical"[^>]*href="([^"]+)"')
_NON_TEXT = re.compile(r"<(table|figure|iframe|video|audio|button)\b.*?</\1>", re.S | re.I)
_MEDIA = re.compile(r"<(img|source|track)\b[^>]*>", re.I)
# Any of these inside the page content means the page has its own copyright / permission terms.
_COPYRIGHT = re.compile(r"©|&copy;|&#169;|&#xa9;|\bcopyright\b|(?:used|reprinted|reproduced|adapted) with permission|\bpermission of\b", re.I)
_DATE_LINE = re.compile(r"^(?:[A-Z][a-z]{2,8}\.?|Sept\.) \d{1,2}, \d{4}$")
_FURNITURE_LINE = re.compile(r"^(?:espa[ñn]ol|en espa[ñn]ol|print|share|syndicate|facebook|linkedin|twitter|x|email|download|for everyone|facebook linkedin twitter syndicate|get more information:?|keep reading\b.*)$", re.I)
# From here to the end is related links, sign-ups and credits, not content.
_TAIL_START = re.compile(
    r"^(?:get email updates|sign up for\b.*|sources(?: and page info)?(?: print share)?.*|content source:?|related (?:pages|topics|links)|"
    r"more information|additional resources|resources|references:?|last reviewed.*|page last reviewed.*)$",
    re.I,
)


class Skipped(Exception):
    """A page that is deliberately not used, with the reason."""


def load_page_list(path: Path) -> list[str]:
    """Page paths from the reviewed list file: one per line, '#' starts a comment, blanks ignored."""
    pages: list[str] = []
    for number, raw in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if not CDC_PATH_PATTERN.match(line) or "__" in line:
            raise ValueError(f"{path} line {number}: not a valid CDC page path: {line!r}")
        if line not in pages:
            pages.append(line)
    return pages


def cache_name(key: str) -> str:
    return key.replace("/", "__")


def _body_text(main_html: str) -> str:
    main_html = _NON_TEXT.sub("", main_html)
    main_html = _MEDIA.sub("", main_html)
    lines = [line for line in html_to_text(main_html).split("\n") if line.strip()]
    lines = [line for line in lines if not _DATE_LINE.match(line.strip()) and not _FURNITURE_LINE.match(line.strip())]
    # Cut the trailing links/credits, looking only in the second half so a real early heading survives.
    for index in range(len(lines) // 2, len(lines)):
        if _TAIL_START.match(lines[index].strip()):
            lines = lines[:index]
            break
    return "\n".join(lines).strip()


def _canonical_url(html: str, key: str) -> str:
    match = _CANONICAL.search(html)
    if match:
        candidate = unescape(match.group(1)).strip()
        if candidate.startswith(f"https://{CDC_HOST}/") and candidate.endswith(".html"):
            return candidate
    return cdc_url(key)


def parse_page(html: str, key: str, retrieved_at: str) -> Document:
    """One Document for a saved CDC page. Raises Skipped (with the reason) when it must not be used."""
    main = _MAIN.search(html)
    title_match = _TITLE.search(html)
    if main is None or title_match is None:
        raise Skipped("no main content")
    if _COPYRIGHT.search(main.group(0)):
        raise Skipped("page has a copyright or permission notice")
    title = re.sub(r"\s+", " ", unescape(title_match.group(1))).split(" | ")[0].strip()
    text = _body_text(main.group(0))
    if not title or title.lower().startswith("page not found"):
        raise Skipped("no usable title")
    if len(text) < MIN_TEXT_CHARS:
        raise Skipped("too little text")
    return Document(
        doc_id="cdc-" + re.sub(r"[^a-z0-9]+", "-", key.removesuffix(".html").lower()).strip("-"),
        source_name=SOURCE_NAME,
        title=title,
        url=_canonical_url(html, key),
        text=text,
        retrieved_at=retrieved_at,
        licence=LICENCE,
        attribution=ATTRIBUTION,
    )


def load_documents(directory: Path, retrieved_at: str) -> tuple[list[Document], dict[str, str]]:
    """Parse every saved page in `directory`. Returns (documents, {page: reason it was skipped})."""
    documents: list[Document] = []
    skipped: dict[str, str] = {}
    for path in sorted(Path(directory).glob("*.html")):
        key = path.stem.replace("__", "/") + ".html"
        try:
            documents.append(parse_page(path.read_text(encoding="utf-8"), key, retrieved_at))
        except Skipped as reason:
            skipped[key] = str(reason)
    return documents, skipped
