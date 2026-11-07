"""Embed chunks and store them in Pinecone.

`upsert_chunks` only knows two tiny interfaces, so it is tested with fakes. Safety properties
(each one has a test in tests/test_upload_safety.py):
- every vector must have the index's dimension, checked before anything is stored;
- temporary failures are retried with growing pauses; a permanent failure says how many chunks
  were stored, and re-running is safe because ids are stable and upserts replace;
- the index is never created here: it must exist with the expected dimension and metric;
- uploads and queries use the same explicit namespace (pinecone_config).
"""
import time
from collections.abc import Callable
from typing import Protocol

from app.retrieval.pinecone_config import EMBEDDING_DIMENSION, EMBEDDING_MODEL, METRIC, NAMESPACE
from vitalnest_ingest.models import Chunk

# Chunks per embed-then-upsert round. Pinecone's hosted model accepts up to 96 inputs per call, but an
# upsert request is capped at 2 MB: 96 vectors of 1,024 floats with full-precision numbers could reach
# about 2.2 MB, while 48 stay near 1.1 MB (see test_a_default_batch_stays_under_the_request_size_limit).
DEFAULT_BATCH_SIZE = 48
DEFAULT_ATTEMPTS = 3


class UploadError(Exception):
    """The upload stopped part-way. `uploaded` chunks are already stored; re-running is safe."""

    def __init__(self, message: str, uploaded: int) -> None:
        super().__init__(message)
        self.uploaded = uploaded


class UploadTargetError(Exception):
    """The Pinecone index is missing or not configured the way ingestion expects."""


class Embedder(Protocol):
    def embed_passages(self, texts: list[str]) -> list[list[float]]: ...


class VectorStore(Protocol):
    def upsert(self, records: list[dict]) -> None: ...


def _embed_and_store(batch: list[Chunk], embedder: Embedder, store: VectorStore, dimension: int) -> None:
    embeddings = embedder.embed_passages([chunk.embedding_text for chunk in batch])
    if len(embeddings) != len(batch):
        raise ValueError(f"Embedder returned {len(embeddings)} vectors for {len(batch)} chunks")
    for values in embeddings:
        if len(values) != dimension:
            raise ValueError(f"Embedding has dimension {len(values)}, but the index needs {dimension}")
    store.upsert(
        [
            {"id": chunk.chunk_id, "values": values, "metadata": chunk.metadata()}
            for chunk, values in zip(batch, embeddings)
        ]
    )


def upsert_chunks(
    chunks: list[Chunk],
    embedder: Embedder,
    store: VectorStore,
    batch_size: int = DEFAULT_BATCH_SIZE,
    dimension: int = EMBEDDING_DIMENSION,
    max_attempts: int = DEFAULT_ATTEMPTS,
    sleep: Callable[[float], None] | None = None,
    progress: Callable[[int, int], None] | None = None,
) -> int:
    pause = sleep or time.sleep  # looked up here, not in the signature, so tests can replace it
    total, done = len(chunks), 0
    for start in range(0, total, batch_size):
        batch = chunks[start:start + batch_size]
        for attempt in range(1, max_attempts + 1):
            try:
                _embed_and_store(batch, embedder, store, dimension)
                break
            except ValueError:
                raise  # a wrong size or count will not fix itself, so do not retry
            except Exception as error:
                if attempt == max_attempts:
                    # The original error may carry request details, so only its type is shown.
                    raise UploadError(
                        f"Upload stopped after {done} of {total} chunks ({type(error).__name__}). "
                        "Chunks already stored are kept; re-run the same command to continue safely.",
                        uploaded=done,
                    ) from error
                pause(2 ** (attempt - 1))
        done += len(batch)
        if progress is not None:
            progress(done, total)
    return done


class PineconeEmbedder:
    def __init__(self, client, model: str = EMBEDDING_MODEL) -> None:
        self._client = client
        self._model = model

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        result = self._client.inference.embed(
            model=self._model, inputs=texts, parameters={"input_type": "passage", "truncate": "END"}
        )
        return [list(item.values) for item in result.data]


class PineconeStore:
    def __init__(self, index, namespace: str = NAMESPACE) -> None:
        self._index = index
        self._namespace = namespace

    def upsert(self, records: list[dict]) -> None:
        self._index.upsert(vectors=records, namespace=self._namespace)


def open_pinecone(api_key: str, index_name: str, client=None) -> tuple[PineconeEmbedder, PineconeStore]:
    """Connect to an existing, correctly configured index. Never creates or changes an index."""
    if client is None:
        from pinecone import Pinecone

        client = Pinecone(api_key=api_key)
    if not client.has_index(index_name):
        raise UploadTargetError(
            f"Index '{index_name}' does not exist. Create it first with create_index.py; the upload never creates it."
        )
    info = client.describe_index(index_name)
    if info.dimension != EMBEDDING_DIMENSION:
        raise UploadTargetError(f"Index '{index_name}' has dimension {info.dimension}, expected {EMBEDDING_DIMENSION}")
    if info.metric != METRIC:
        raise UploadTargetError(f"Index '{index_name}' uses metric {info.metric}, expected {METRIC}")
    if not info.status.ready:
        raise UploadTargetError(f"Index '{index_name}' is not ready yet")
    return PineconeEmbedder(client), PineconeStore(client.Index(index_name))
