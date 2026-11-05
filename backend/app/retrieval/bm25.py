"""Keyword retrieval with BM25 (rank-bm25) over the index file written by the ingestion script.

The file holds chunks and their tokens (see ingestion/vitalnest_ingest/bm25_index.py). The
BM25 statistics are rebuilt from the tokens when the app starts; searching then costs milliseconds.
"""
import json
from dataclasses import fields
from pathlib import Path

import numpy as np
from rank_bm25 import BM25Okapi

from app.retrieval.tokenize import tokenize
from app.retrieval.types import RetrievedChunk

SUPPORTED_VERSION = 1
_CHUNK_FIELDS = [f.name for f in fields(RetrievedChunk) if f.name != "score"]


class IndexLoadError(Exception):
    """The BM25 index file is missing, unreadable or inconsistent."""


class Bm25Index:
    def __init__(self, chunks: list[dict], tokens: list[list[str]]) -> None:
        self._chunks = chunks
        self._bm25 = BM25Okapi(tokens)

    @classmethod
    def load(cls, path: Path) -> "Bm25Index":
        path = Path(path)
        try:
            raw = path.read_text(encoding="utf-8")
        except FileNotFoundError as error:
            raise IndexLoadError(f"BM25 index file not found: {path}") from error
        try:
            data = json.loads(raw)
        except ValueError as error:
            raise IndexLoadError(f"BM25 index file is not valid JSON: {path}") from error

        if not isinstance(data, dict) or data.get("version") != SUPPORTED_VERSION:
            version = data.get("version") if isinstance(data, dict) else None
            raise IndexLoadError(f"Unsupported BM25 index version: {version!r}")
        chunks, tokens = data.get("chunks"), data.get("tokens")
        if not isinstance(chunks, list) or not isinstance(tokens, list) or len(chunks) != len(tokens):
            raise IndexLoadError("BM25 index chunk and token counts must match")
        if not chunks:
            raise IndexLoadError("BM25 index is empty")
        if any(not isinstance(c, dict) or any(name not in c for name in _CHUNK_FIELDS) for c in chunks):
            raise IndexLoadError(f"BM25 index chunks are missing required fields: {_CHUNK_FIELDS}")
        return cls(chunks, tokens)

    def __len__(self) -> int:
        return len(self._chunks)

    def texts(self) -> list[str]:
        """Title and text of every chunk (the source of the spelling vocabulary)."""
        return [f"{chunk['title']} {chunk['text']}" for chunk in self._chunks]

    def titles(self) -> list[str]:
        """Page titles (topic names), which the spelling vocabulary favours over incidental words."""
        return [chunk["title"] for chunk in self._chunks]

    def search(self, query: str, top_k: int = 20) -> list[RetrievedChunk]:
        if top_k < 1:
            raise ValueError("top_k must be at least 1")
        # Repeating a word in the query should not count it twice.
        terms = list(dict.fromkeys(tokenize(query)))
        if not terms:
            return []
        scores = self._bm25.get_scores(terms)
        # Stable sort on negated scores: equal scores keep index order, so results are deterministic.
        order = np.argsort(-scores, kind="stable")
        hits: list[RetrievedChunk] = []
        for position in order:
            score = float(scores[position])
            if score <= 0 or len(hits) >= top_k:
                break
            record = self._chunks[int(position)]
            hits.append(RetrievedChunk(**{name: record[name] for name in _CHUNK_FIELDS}, score=score))
        return hits
