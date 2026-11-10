# VitalNest ingestion (T3)

Manual, offline script (decision G2). It is never deployed. Source terms: [../docs/sources.md](../docs/sources.md).

From the repository root, with the project's `.venv` active:

```bash
cd ingestion
../.venv/Scripts/python -m vitalnest_ingest fetch     # newest MedlinePlus topics XML -> data/raw/
../.venv/Scripts/python -m vitalnest_ingest build --input data/raw/<file>.xml   # chunks.jsonl + bm25_index.json -> data/build/
export PINECONE_API_KEY=...                           # in your shell only, never in a file
../.venv/Scripts/python create_index.py               # once: creates "vitalnest" (cosine, 1024 dims) if absent
../.venv/Scripts/python -m vitalnest_ingest upload --dry-run   # validates the file; sends nothing, needs no key
../.venv/Scripts/python -m vitalnest_ingest upload    # embed + upsert; never creates the index
```

- `build` works fully offline. Only `upload` needs the Pinecone key.
- Safety: downloads only from `https://medlineplus.gov` (checked on every redirect hop), is validated as a MedlinePlus topics file before being saved, and never replaces an existing file. `fetch` and `build` refuse to overwrite earlier output unless you pass `--force`. Errors are printed as one-line messages with exit code 1.
- `data/` is git-ignored. After a rebuild, copy `data/build/bm25_index.json` to `backend/app/data/bm25_index.json` (that copy is committed: it is what the deployed API loads) and re-run the retrieval evaluation.
- Chunk size (1000) and overlap (150) are starting values; T16's retrieval evaluation sets the final numbers.
- Tests: `cd ingestion && ../.venv/Scripts/python -m pytest` (offline: HTTP is mocked, Pinecone is faked).

## Where to put the Pinecone key

Copy `ingestion/.env.example` to `ingestion/.env` and replace the placeholder with your key. The commands
(`python -m vitalnest_ingest ...`, `check_pinecone.py`, `create_index.py`, `query_test.py`) read it
automatically. A variable already set in the shell wins over the file. `.env` is git-ignored.
The project folder is inside OneDrive, which syncs files to the cloud, so if you prefer to keep the key
off OneDrive, put the same one line in `C:\Users\cheta\.vitalnest.env` instead (also read automatically).
