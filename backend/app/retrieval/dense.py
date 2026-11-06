"""Dense (semantic) retrieval: embed the question and ask Pinecone for the closest chunks (cosine).

`DenseRetriever` only knows two small interfaces, so it is tested with fakes. The Pinecone
adapters below are thin and have not been run against a live account yet (needs an API key
and the ingestion `upload` step).
"""
from dataclasses import fields
from typing import Protocol

from app.retrieval.pinecone_config import EMBEDDING_MODEL, INDEX_NAME, NAMESPACE
from app.retrieval.types import RetrievalError, RetrievedChunk

# The model is shared with ingestion (pinecone_config); only `input_type` differs (passage there, query here).
_METADATA_FIELDS = [f.name for f in fields(RetrievedChunk) if f.name not in ("chunk_id", "score")]


class QueryEmbedder(Protocol):
    def embed_query(self, text: str) -> list[float]: ...


class VectorIndex(Protocol):
    def query(self, vector: list[float], top_k: int) -> list[dict]: ...


class DenseRetriever:
    def __init__(self, embedder: QueryEmbedder, index: VectorIndex) -> None:
        self._embedder = embedder
        self._index = index

    def search(self, query: str, top_k: int = 20) -> list[RetrievedChunk]:
        if top_k < 1:
            raise ValueError("top_k must be at least 1")
        query = query.strip()
        if not query:
            return []
        try:
            matches = self._index.query(self._embedder.embed_query(query), top_k)
        except Exception as error:
            # The original error may carry request details, so it is chained but not put in the message.
            raise RetrievalError("Dense retrieval failed") from error

        hits: list[RetrievedChunk] = []
        for match in matches:
            metadata = match.get("metadata")
            if not isinstance(metadata, dict) or any(name not in metadata for name in _METADATA_FIELDS):
                continue  # a vector without its citation fields cannot be used
            hits.append(
                RetrievedChunk(
                    chunk_id=match["id"], score=float(match["score"]),
                    **{name: metadata[name] for name in _METADATA_FIELDS},
                )
            )
        return hits


class PineconeQueryEmbedder:
    def __init__(self, client, model: str = EMBEDDING_MODEL) -> None:
        self._client = client
        self._model = model

    def embed_query(self, text: str) -> list[float]:
        result = self._client.inference.embed(
            model=self._model, inputs=[text], parameters={"input_type": "query", "truncate": "END"}
        )
        return list(result.data[0].values)


class PineconeVectorIndex:
    def __init__(self, index, namespace: str = NAMESPACE) -> None:
        self._index = index
        self._namespace = namespace

    def query(self, vector: list[float], top_k: int) -> list[dict]:
        response = self._index.query(
            vector=vector, top_k=top_k, include_metadata=True, namespace=self._namespace
        )
        return [{"id": m.id, "score": m.score, "metadata": m.metadata} for m in response.matches]


def open_dense_retriever(api_key: str, index_name: str = INDEX_NAME) -> DenseRetriever:
    from pinecone import Pinecone

    client = Pinecone(api_key=api_key)
    return DenseRetriever(PineconeQueryEmbedder(client), PineconeVectorIndex(client.Index(index_name)))
