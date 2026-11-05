"""Result type shared by every retriever (BM25, dense) and by the fusion step."""
from dataclasses import dataclass


@dataclass(frozen=True)
class RetrievedChunk:
    """A chunk found by a retriever, with everything needed to build prompts and citations."""
    chunk_id: str
    doc_id: str
    source_name: str
    title: str
    url: str
    text: str
    retrieved_at: str
    licence: str
    attribution: str
    score: float = 0.0


class RetrievalError(Exception):
    """A retrieval backend (for example Pinecone) failed. The API reports it as an upstream error."""
