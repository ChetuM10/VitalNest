"""Persist the BM25 index as plain JSON (decision G3).

The file stores the chunks and their tokens. The API rebuilds `rank_bm25.BM25Okapi` from the
tokens at startup, which takes a moment for a few thousand chunks. JSON is used instead of pickle
so the file is inspectable and loading it cannot run code.
"""
import json
from dataclasses import dataclass
from pathlib import Path

from app.retrieval.tokenize import tokenize
from vitalnest_ingest.files import write_text_atomic
from vitalnest_ingest.models import Chunk

INDEX_VERSION = 1


@dataclass(frozen=True)
class LoadedIndex:
    chunks: list[dict]
    tokens: list[list[str]]


def save_index(chunks: list[Chunk], path: Path) -> None:
    data = {
        "version": INDEX_VERSION,
        "chunks": [chunk.to_dict() for chunk in chunks],
        # Title is included so a query for a topic name matches its chunks.
        "tokens": [tokenize(f"{chunk.title} {chunk.text}") for chunk in chunks],
    }
    write_text_atomic(path, json.dumps(data, ensure_ascii=False))


def load_index(path: Path) -> LoadedIndex:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("version") != INDEX_VERSION:
        raise ValueError(f"Unsupported BM25 index version: {data.get('version')!r}")
    return LoadedIndex(chunks=data["chunks"], tokens=data["tokens"])
