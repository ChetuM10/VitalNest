# Retrieval evaluation (T16)

- `retrieval_questions.json`: 15 hand-written questions (expected MedlinePlus pages and key facts) and 10 questions the corpus cannot answer.
- `retrieval_eval.py`: compares BM25, Pinecone and RRF (Hit@k, MRR, fact coverage) and checks the "not enough information" cutoff. Read-only: about 25 Pinecone embedding calls, no uploads, no Claude calls.
- `results/`: saved reports.

```bash
cd evaluation
../.venv/Scripts/python retrieval_eval.py                 # needs the Pinecone key (ingestion/.env)
../.venv/Scripts/python -m pytest tests -q -o pythonpath=.  # metric helper tests, offline
```
