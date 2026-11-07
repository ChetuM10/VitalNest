"""Create the VitalNest Pinecone index if (and only if) it does not exist yet. Uploads no vectors.

    export PINECONE_API_KEY=...        # in your shell only; this script never prints it
    python create_index.py [index_name]

- If the index already exists it is NOT touched: the script reports its configuration and stops.
- Otherwise it creates a serverless index with the settings ingestion expects (1024 dimensions,
  cosine, AWS us-east-1, the only region on Pinecone's free plan), waits until it is ready, then
  verifies the configuration it created.
"""
import os
import sys

from pinecone import Pinecone, ServerlessSpec

from vitalnest_ingest.env import load_env_files

DIMENSION = 1024  # multilingual-e5-large
METRIC = "cosine"
CLOUD, REGION = "aws", "us-east-1"


def main() -> int:
    load_env_files()  # ingestion/.env or ~/.vitalnest.env; a shell variable still wins
    key = os.environ.get("PINECONE_API_KEY")
    if not key:
        print("FAIL  PINECONE_API_KEY is not set in this shell.")
        return 2
    name = sys.argv[1] if len(sys.argv) > 1 else "vitalnest"
    client = Pinecone(api_key=key)

    try:
        if client.has_index(name):
            info = client.describe_index(name)
            print(f"EXISTS  '{name}' already exists, left untouched: dimension={info.dimension}, "
                  f"metric={info.metric}, ready={info.status.ready}")
            return 3
        print(f"Creating '{name}' ({DIMENSION} dimensions, {METRIC}, {CLOUD}/{REGION}) ...")
        client.create_index(
            name=name, dimension=DIMENSION, metric=METRIC, spec=ServerlessSpec(cloud=CLOUD, region=REGION)
        )
        info = client.describe_index(name)
    except Exception as error:  # messages can carry request details, so print the type only
        print(f"FAIL  Pinecone call failed ({type(error).__name__}). Nothing else was changed.")
        return 1

    checks = {
        "dimension": (info.dimension, DIMENSION),
        "metric": (info.metric, METRIC),
        "ready": (info.status.ready, True),
    }
    bad = {k: v for k, v in checks.items() if v[0] != v[1]}
    print(f"index '{name}': dimension={info.dimension}, metric={info.metric}, ready={info.status.ready}, spec={info.spec}")
    if bad:
        print(f"FAIL  unexpected configuration: {bad}")
        return 1
    print("OK    index created and verified. No vectors were uploaded.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
