"""Parse the official MedlinePlus Health Topics XML file (see docs/sources.md).

Only the English `full-summary` and `also-called` terms are read. `site` records (links to other
organisations' pages) and all other elements are ignored on purpose: they are not NLM's to license.
"""
import xml.etree.ElementTree as ET

from vitalnest_ingest.cleaning import html_to_text
from vitalnest_ingest.models import Document

SOURCE_NAME = "MedlinePlus"
LICENCE = "Public domain (U.S. government work, not copyrighted)"
ATTRIBUTION = "Courtesy of MedlinePlus from the National Library of Medicine"


def _summary_text(summary: ET.Element) -> str:
    """The summary may be escaped HTML (text) or real child elements; accept both."""
    inner = (summary.text or "") + "".join(ET.tostring(child, encoding="unicode") for child in summary)
    return html_to_text(inner)


def parse_topics(xml: str | bytes, retrieved_at: str) -> list[Document]:
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as error:
        raise ValueError(f"Could not parse MedlinePlus XML: {error}") from error

    documents: list[Document] = []
    for topic in root.iter("health-topic"):
        if topic.get("language") != "English":
            continue
        summary = topic.find("full-summary")
        text = _summary_text(summary) if summary is not None else ""
        if not text:
            continue
        also_called = [t.text.strip() for t in topic.findall("also-called") if t.text and t.text.strip()]
        if also_called:
            text = f"{text}\nAlso called: {', '.join(also_called)}"
        documents.append(
            Document(
                doc_id=f"medlineplus-{topic.get('id')}",
                source_name=SOURCE_NAME,
                title=topic.get("title") or topic.findtext("title", default="").strip(),
                url=topic.get("url", ""),
                text=text,
                retrieved_at=retrieved_at,
                licence=LICENCE,
                attribution=ATTRIBUTION,
            )
        )
    return documents
