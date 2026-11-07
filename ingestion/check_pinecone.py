"""Read-only Pinecone health check. Creates, changes and uploads nothing.

    export PINECONE_API_KEY=...        # in your shell only; this script never prints it
    python check_pinecone.py [index_name]

Checks: the key is accepted, which indexes exist, whether the expected index exists with the
configuration ingestion creates (cosine, 1024 dimensions, ready), how many vectors it holds,
and whether the hosted embedding model is available to this account.
"""
import os
import sys

from pinecone import Pinecone

from vitalnest_ingest.env import load_env_files

EXPECTED_METRIC = "cosine"
EXPECTED_DIMENSION = 1024  # multilingual-e5-large
EMBEDDING_MODEL = "multilingual-e5-large"


def main() -> int:
    load_env_files()  # ingestion/.env or ~/.vitalnest.env; a shell variable still wins
    key = os.environ.get("PINECONE_API_KEY")
    if not key:
        print("FAIL  PINECONE_API_KEY is not set in this shell.")
        return 2
    index_name = sys.argv[1] if len(sys.argv) > 1 else "vitalnest"
    problems = 0

    client = Pinecone(api_key=key)
    try:
        indexes = client.list_indexes()
    except Exception as error:  # the message can include request details, so print the type only
        print(f"FAIL  key rejected or Pinecone unreachable ({type(error).__name__}).")
        return 1
    print(f"OK    key accepted. Indexes in this project: {[i.name for i in indexes] or 'none'}")

    if not client.has_index(index_name):
        print(f"MISSING  index '{index_name}' does not exist yet (the ingestion upload step creates it).")
        problems += 1
    else:
        info = client.describe_index(index_name)
        spec = info.spec
        print(f"OK    index '{index_name}' exists: dimension={info.dimension}, metric={info.metric}, "
              f"ready={info.status.ready}, spec={spec}")
        if info.metric != EXPECTED_METRIC:
            print(f"FAIL  metric is {info.metric}, expected {EXPECTED_METRIC}")
            problems += 1
        if info.dimension != EXPECTED_DIMENSION:
            print(f"FAIL  dimension is {info.dimension}, expected {EXPECTED_DIMENSION}")
            problems += 1
        if not info.status.ready:
            print("FAIL  index is not ready yet")
            problems += 1
        stats = client.Index(index_name).describe_index_stats()
        print(f"OK    vectors stored: {stats.total_vector_count}")

    try:
        names = [m.model for m in client.inference.list_models()]
        found = EMBEDDING_MODEL in names
        print(f"{'OK  ' if found else 'FAIL'}  hosted embedding model '{EMBEDDING_MODEL}' "
              f"{'is' if found else 'is NOT'} available to this account")
        problems += 0 if found else 1
    except Exception as error:
        print(f"WARN  could not list hosted models ({type(error).__name__})")
        problems += 1

    print("RESULT: all checks passed" if not problems else f"RESULT: {problems} problem(s) found")
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
