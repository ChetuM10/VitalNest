"""Live, read-only query test: embeds a question with the hosted model and searches the index.

    export PINECONE_API_KEY=...        # in your shell only; this script never prints it
    python query_test.py [index_name] ["your question"]

Uses the same code the API will use (backend/app/retrieval/dense.py). It makes two calls: one
embedding request and one query. It upserts, deletes and modifies nothing. Before the ingestion
`upload` step the index is empty, so zero matches is the expected, healthy result.
"""
import math
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from pinecone import Pinecone

from vitalnest_ingest.env import load_env_files  # noqa: E402

from app.retrieval.dense import DenseRetriever, PineconeQueryEmbedder, PineconeVectorIndex  # noqa: E402

EXPECTED_DIMENSION = 1024
DEFAULT_QUESTION = "What are the symptoms of asthma?"


def run_test(embedder, index, question: str) -> int:
    """Returns 0 when embedding and querying both work."""
    vector = embedder.embed_query(question)
    if len(vector) != EXPECTED_DIMENSION or not all(math.isfinite(x) for x in vector):
        print(f"FAIL  query embedding has {len(vector)} values (expected {EXPECTED_DIMENSION}) or non-finite values")
        return 1
    print(f"OK    query embedded: {len(vector)} dimensions")

    matches = DenseRetriever(embedder, index).search(question, top_k=3)
    print(f"OK    query ran: {len(matches)} match(es) returned")
    if not matches:
        print("NOTE  zero matches: expected while the index is empty (before the upload step).")
    for hit in matches:
        print(f"      {hit.score:.3f}  {hit.title}  <{hit.url}>")
    return 0


def main() -> int:
    load_env_files()  # ingestion/.env or ~/.vitalnest.env; a shell variable still wins
    key = os.environ.get("PINECONE_API_KEY")
    if not key:
        print("FAIL  PINECONE_API_KEY is not set in this shell.")
        return 2
    name = sys.argv[1] if len(sys.argv) > 1 else "vitalnest"
    question = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_QUESTION

    client = Pinecone(api_key=key)
    try:
        if not client.has_index(name):
            print(f"FAIL  index '{name}' does not exist.")
            return 1
        embedder = PineconeQueryEmbedder(client)
        index = PineconeVectorIndex(client.Index(name))
        return run_test(embedder, index, question)
    except Exception as error:  # messages can carry request details, so print the type only
        print(f"FAIL  live call failed ({type(error).__name__}). Nothing was modified.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
