"""Retrieval evaluation (T16): how well do BM25, Pinecone (dense) and RRF find the right MedlinePlus
page for 15 hand-written questions, and where should the 'not enough information' cutoff sit?

    cd evaluation && ../.venv/Scripts/python retrieval_eval.py

Read-only: it queries Pinecone (about 25 embedding calls) and never uploads, deletes or calls Claude.
It also tries a few settings offline (stop-word filtering for BM25, RRF k) so changes can be judged
on evidence. Results are printed and saved to results/retrieval_eval_<date>.md.
"""
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from rank_bm25 import BM25Okapi  # noqa: E402

from app.config.env import load_env_files  # noqa: E402
from app.config.settings import no_context_min_dense_score  # noqa: E402
from app.retrieval.dense import open_dense_retriever  # noqa: E402
from app.retrieval.rrf import reciprocal_rank_fusion  # noqa: E402
from app.retrieval.tokenize import tokenize  # noqa: E402
from app.retrieval.types import RetrievedChunk  # noqa: E402
from metrics import fact_coverage, first_rank, hit_rate, mean_reciprocal_rank, threshold_report  # noqa: E402

INDEX_FILE = ROOT / "ingestion" / "data" / "build" / "bm25_index.json"
QUESTIONS_FILE = Path(__file__).resolve().parent / "retrieval_questions.json"
POOL = 50  # candidates fetched once per question; smaller pools are slices of it
SENT_TO_CLAUDE = 6  # chunks the chat pipeline sends to Claude

STOP_WORDS = set(
    "a an and are as at be been but by can could did do does for from had has have how i if in into is it its "
    "may me might my of on or our should so than that the their them then there these they this to was we were "
    "what when where which who why will with would you your".split()
)


class KeywordSearch:
    """BM25 over the stored tokens, optionally ignoring stop words (an offline experiment)."""

    def __init__(self, chunks: list[dict], tokens: list[list[str]], drop_stop_words: bool) -> None:
        self.chunks, self.drop = chunks, drop_stop_words
        corpus = [[t for t in doc if t not in STOP_WORDS] for doc in tokens] if drop_stop_words else tokens
        self.bm25 = BM25Okapi(corpus)

    def search(self, query: str, top_k: int) -> list[RetrievedChunk]:
        terms = list(dict.fromkeys(tokenize(query)))
        if self.drop:
            terms = [t for t in terms if t not in STOP_WORDS]
        if not terms:
            return []
        scores = self.bm25.get_scores(terms)
        order = sorted(range(len(scores)), key=lambda i: (-scores[i], i))[:top_k]
        fields = ["chunk_id", "doc_id", "source_name", "title", "url", "text", "retrieved_at", "licence", "attribution"]
        return [RetrievedChunk(**{f: self.chunks[i][f] for f in fields}, score=float(scores[i])) for i in order if scores[i] > 0]


def titles(chunks: list[RetrievedChunk]) -> list[str]:
    return [c.title for c in chunks]


def validate_dataset(questions: list[dict], chunks: list[dict]) -> list[str]:
    """Catch mistakes in the question set itself: unknown pages, or facts the expected pages never state."""
    by_title: dict[str, str] = {}
    for c in chunks:
        by_title[c["title"]] = by_title.get(c["title"], "") + " " + c["text"]
    problems = []
    for q in questions:
        known = [t for t in q["expected_titles"] if t in by_title]
        for t in q["expected_titles"]:
            if t not in by_title:
                problems.append(f"{q['id']}: expected page {t!r} is not in the corpus")
        if known and fact_coverage([by_title[t] for t in known], q["facts"]) < 1.0:
            problems.append(f"{q['id']}: not every fact appears on the expected pages {known}")
    return problems


def main() -> int:
    load_env_files()
    key = os.environ.get("PINECONE_API_KEY")
    if not key:
        print("PINECONE_API_KEY is not available (see ingestion/README.md).")
        return 2

    data = json.loads(QUESTIONS_FILE.read_text(encoding="utf-8"))
    questions, negatives = data["questions"], data["unanswerable"]
    index = json.loads(INDEX_FILE.read_text(encoding="utf-8"))
    chunks, tokens = index["chunks"], index["tokens"]

    problems = validate_dataset(questions, chunks)
    print(f"Dataset: {len(questions)} questions, {len(negatives)} unanswerable. Corpus: {len(chunks)} chunks.")
    for problem in problems:
        print("  DATASET PROBLEM:", problem)

    dense = open_dense_retriever(key)
    keyword = {"current": KeywordSearch(chunks, tokens, False), "stopwords": KeywordSearch(chunks, tokens, True)}

    runs: dict[str, dict[str, list[RetrievedChunk]]] = {}
    dense_cache: dict[str, list[RetrievedChunk]] = {}
    for q in questions:
        dense_cache[q["question"]] = dense.search(q["question"], top_k=POOL)
    negative_dense = {text: dense.search(text, top_k=POOL) for text in negatives}

    configs = {
        "bm25 (current)": lambda q, d: keyword["current"].search(q, 20),
        "bm25 (stop words removed)": lambda q, d: keyword["stopwords"].search(q, 20),
        "dense (Pinecone)": lambda q, d: d[:20],
        "RRF  current bm25 + dense, k=60  [shipped]": lambda q, d: reciprocal_rank_fusion([keyword["current"].search(q, 20), d[:20]], k=60, top_n=20),
        "RRF  stop-word bm25 + dense, k=60": lambda q, d: reciprocal_rank_fusion([keyword["stopwords"].search(q, 20), d[:20]], k=60, top_n=20),
        "RRF  current bm25 + dense, k=10": lambda q, d: reciprocal_rank_fusion([keyword["current"].search(q, 20), d[:20]], k=10, top_n=20),
        "RRF  stop-word bm25 + dense, pool 10": lambda q, d: reciprocal_rank_fusion([keyword["stopwords"].search(q, 10), d[:10]], k=60, top_n=20),
    }

    sources = ", ".join(f"{name} {sum(1 for c in chunks if c['source_name'] == name)} chunks" for name in sorted({c["source_name"] for c in chunks}))
    lines = [f"# Retrieval evaluation, {date.today().isoformat()}", "", f"{len(questions)} questions; corpus {len(chunks)} chunks / {len({c['doc_id'] for c in chunks})} pages ({sources}). "
             f"Hit@k = first expected page within the top k chunks; the chat pipeline sends the top {SENT_TO_CLAUDE} to Claude.", ""]
    if problems:
        lines += ["**Dataset problems:** " + "; ".join(problems), ""]
    lines += ["| Configuration | Hit@1 | Hit@3 | Hit@6 | Hit@20 | MRR | Facts in top 6 |", "|---|---|---|---|---|---|---|"]

    detail: dict[str, list[tuple[dict, int | None, list[str]]]] = {}
    for name, build in configs.items():
        ranks, coverage, rows = [], [], []
        for q in questions:
            result = build(q["question"], dense_cache[q["question"]])
            rank = first_rank(titles(result), set(q["expected_titles"]))
            ranks.append(rank)
            coverage.append(fact_coverage([c.text for c in result[:SENT_TO_CLAUDE]], q["facts"]))
            rows.append((q, rank, titles(result)[:4]))
        detail[name] = rows
        lines.append(f"| {name} | {hit_rate(ranks, 1):.0%} | {hit_rate(ranks, 3):.0%} | {hit_rate(ranks, 6):.0%} | "
                     f"{hit_rate(ranks, 20):.0%} | {mean_reciprocal_rank(ranks):.3f} | {sum(coverage) / len(coverage):.0%} |")

    shipped = "RRF  current bm25 + dense, k=60  [shipped]"
    lines += ["", f"## Per question, shipped configuration (rank of the first expected page; top titles retrieved)", "",
              "| # | Question | Rank | Top retrieved pages |", "|---|---|---|---|"]
    for q, rank, top in detail[shipped]:
        lines.append(f"| {q['id']} | {q['question']} | {rank if rank else 'MISS'} | {', '.join(top)} |")

    misses = [(name, q["id"]) for name, rows in detail.items() for q, rank, _ in rows if rank is None or rank > SENT_TO_CLAUDE]
    lines += ["", "## Questions where the expected page is not in the top 6", ""]
    lines += [f"- {name}: {qid}" for name, qid in misses] or ["- none"]

    answerable = [dense_cache[q["question"]][0].score for q in questions if dense_cache[q["question"]]]
    unanswerable = [hits[0].score for hits in negative_dense.values() if hits]
    report = threshold_report(answerable, unanswerable)
    current = no_context_min_dense_score()
    lines += ["", "## No-context threshold (best Pinecone cosine score)", "",
              f"- Answerable questions: lowest best-score {report['lowest_answerable']:.3f}, mean {sum(answerable) / len(answerable):.3f}",
              f"- Unanswerable questions: highest best-score {report['highest_unanswerable']:.3f}, mean {sum(unanswerable) / len(unanswerable):.3f}",
              f"- Cleanly separable by one cutoff: {report['separable']}; suggested cutoff {report['suggested']}",
              f"- Shipped cutoff {current}: wrongly refuses {sum(1 for s in answerable if s < current)} of {len(answerable)} answerable, "
              f"wrongly answers {sum(1 for s in unanswerable if s >= current)} of {len(unanswerable)} unanswerable",
              "", "Unanswerable questions, best score and page:", ""]
    lines += [f"- {hits[0].score:.3f}  {hits[0].title}  <- {text}" for text, hits in negative_dense.items() if hits]

    output = "\n".join(lines)
    print(output)
    result_file = Path(__file__).resolve().parent / "results" / f"retrieval_eval_{date.today().isoformat()}.md"
    result_file.write_text(output + "\n", encoding="utf-8")
    print(f"\nSaved to {result_file}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
