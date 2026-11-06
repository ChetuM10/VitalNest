"""Reciprocal Rank Fusion: merge ranked lists without comparing their (incomparable) scores.

    score(chunk) = sum over lists of 1 / (k + rank)        rank starts at 1, k = 60 by default
"""
from dataclasses import replace

from app.retrieval.types import RetrievedChunk

DEFAULT_K = 60


def reciprocal_rank_fusion(
    rankings: list[list[RetrievedChunk]], k: int = DEFAULT_K, top_n: int | None = None
) -> list[RetrievedChunk]:
    if k < 1:
        raise ValueError("k must be at least 1")
    if top_n is not None and top_n < 1:
        raise ValueError("top_n must be at least 1")

    scores: dict[str, float] = {}
    chunks: dict[str, RetrievedChunk] = {}
    first_seen: dict[str, int] = {}
    for ranking in rankings:
        counted: set[str] = set()
        for rank, chunk in enumerate(ranking, start=1):
            if chunk.chunk_id in counted:
                continue  # a repeat inside one list counts once, at its best rank
            counted.add(chunk.chunk_id)
            scores[chunk.chunk_id] = scores.get(chunk.chunk_id, 0.0) + 1.0 / (k + rank)
            if chunk.chunk_id not in chunks:
                chunks[chunk.chunk_id] = chunk
                first_seen[chunk.chunk_id] = len(first_seen)

    # Ties (equal scores, to 12 places) keep the order in which chunks first appeared.
    ordered = sorted(chunks, key=lambda chunk_id: (-round(scores[chunk_id], 12), first_seen[chunk_id]))
    fused = [replace(chunks[chunk_id], score=scores[chunk_id]) for chunk_id in ordered]
    return fused if top_n is None else fused[:top_n]
