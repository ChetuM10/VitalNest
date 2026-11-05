"""Split a document into overlapping, sentence-aligned chunks.

Defaults are starting values; the retrieval evaluation (T16) decides the final numbers.
"""
import re

from vitalnest_ingest.models import Chunk, Document

DEFAULT_MAX_CHARS = 1000
DEFAULT_OVERLAP_CHARS = 150

_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+|\n+")


def _hard_split(text: str, max_chars: int) -> list[str]:
    """Break an over-long sentence on word boundaries, slicing words that are themselves too long."""
    pieces: list[str] = []
    current = ""
    for word in text.split():
        while len(word) > max_chars:
            if current:
                pieces.append(current)
                current = ""
            pieces.append(word[:max_chars])
            word = word[max_chars:]
        candidate = f"{current} {word}" if current else word
        if len(candidate) > max_chars:
            pieces.append(current)
            current = word
        else:
            current = candidate
    if current:
        pieces.append(current)
    return pieces


def _pieces(text: str, max_chars: int) -> list[str]:
    pieces: list[str] = []
    for sentence in (s.strip() for s in _SENTENCE_BOUNDARY.split(text)):
        if not sentence:
            continue
        pieces.extend([sentence] if len(sentence) <= max_chars else _hard_split(sentence, max_chars))
    return pieces


def _overlap_tail(pieces: list[str], budget: int) -> list[str]:
    tail: list[str] = []
    for piece in reversed(pieces):
        if len(" ".join([piece, *tail])) > budget:
            break
        tail.insert(0, piece)
    return tail


def chunk_document(
    doc: Document, max_chars: int = DEFAULT_MAX_CHARS, overlap_chars: int = DEFAULT_OVERLAP_CHARS
) -> list[Chunk]:
    texts: list[str] = []
    current: list[str] = []
    for piece in _pieces(doc.text, max_chars):
        if current and len(" ".join([*current, piece])) > max_chars:
            texts.append(" ".join(current))
            current = _overlap_tail(current, overlap_chars)
            while current and len(" ".join([*current, piece])) > max_chars:
                current.pop(0)
        current.append(piece)
    if current:
        texts.append(" ".join(current))

    return [
        Chunk(
            chunk_id=f"{doc.doc_id}-{index:03d}",
            doc_id=doc.doc_id,
            source_name=doc.source_name,
            title=doc.title,
            url=doc.url,
            text=text,
            retrieved_at=doc.retrieved_at,
            licence=doc.licence,
            attribution=doc.attribution,
        )
        for index, text in enumerate(texts)
    ]
