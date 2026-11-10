"""Grounding check (T16): are Claude's answers supported by the text it was given?

    cd evaluation && ../.venv/Scripts/python grounding_check.py

Sends the 15 evaluation questions through the real chat pipeline (real Pinecone, real BM25, real
Claude Haiku: 15 small paid calls), records the exact sources each answer was given, and flags answer
sentences that look unsupported: low word overlap with the sources, or numbers not found in them.
The flags are a screening aid; a person (or reviewer) still judges each flagged sentence.
"""
import asyncio
import html
import json
import os
import re
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.api.schemas import ChatRequest  # noqa: E402
from app.chat.service import ChatService  # noqa: E402
from app.config.env import load_env_files  # noqa: E402
from app.config.settings import claude_model, no_context_min_dense_score  # noqa: E402
from app.llm.claude import ClaudeClient  # noqa: E402
from app.retrieval.bm25 import Bm25Index  # noqa: E402
from app.retrieval.dense import open_dense_retriever  # noqa: E402
from app.safety.output_guard import split_complete_sentences  # noqa: E402

QUESTIONS = json.loads((Path(__file__).resolve().parent / "retrieval_questions.json").read_text(encoding="utf-8"))["questions"]
INDEX_FILE = ROOT / "ingestion" / "data" / "build" / "bm25_index.json"
OVERLAP_FLAG = 0.6
FILLER = set("this that with from have been your what when which also such some many most more than into they them their there these those about other only like very much will would could should".split())


class RecordingClaude:
    """Wraps the real client and remembers the prompt of the last request (the sources it contained)."""

    def __init__(self, inner: ClaudeClient) -> None:
        self.inner, self.last_messages = inner, None

    def stream(self, system, messages):
        self.last_messages = messages
        return self.inner.stream(system, messages)


def words(text: str) -> set[str]:
    return {w.rstrip("s") for w in re.findall(r"[a-z]{4,}", text.casefold()) if w not in FILLER}


def parse(raw: list[str]):
    events = []
    for block in raw:
        fields = dict(line.split(": ", 1) for line in block.strip().splitlines())
        events.append((fields["event"], json.loads(fields["data"])))
    return events


def screen(answer: str, source_text: str) -> list[dict]:
    """Sentences whose content words are mostly absent from the sources, or whose numbers are."""
    vocabulary, flagged = words(source_text), []
    sentences, rest = split_complete_sentences(answer + "\n")
    for sentence in [s for s, _ in sentences] + ([rest] if rest.strip() else []):
        text = re.sub(r"[*#]", "", sentence).strip().lstrip("- ").strip()
        if len(text) < 25:
            continue
        content = words(text)
        overlap = len(content & vocabulary) / len(content) if content else 1.0
        numbers = [n for n in re.findall(r"\d+(?:[.,]\d+)?", text) if n not in source_text]
        if overlap < OVERLAP_FLAG or numbers:
            flagged.append({"sentence": text, "overlap": round(overlap, 2), "numbers_not_in_sources": numbers})
    return flagged


async def ask(service: ChatService, recorder: RecordingClaude, question: str) -> dict:
    started = time.perf_counter()
    plan = await service.prepare(ChatRequest(message=question))
    raw = [event async for event in plan.events()]
    await plan.close()
    events = parse(raw)
    data = dict(events)
    answer = "".join(d["text"] for n, d in events if n == "token").strip()
    sources_text = ""
    if recorder.last_messages:
        sources_text = html.unescape(" ".join(re.findall(r"<source [^>]*>(.*?)</source>", recorder.last_messages[-1]["content"], re.S)))
    status = data.get("safety", {}).get("status", "error")
    return {
        "question": question, "status": status, "seconds": round(time.perf_counter() - started, 1),
        "answer": answer, "sources": [s["title"] for s in data.get("sources", {}).get("sources", [])],
        "suggestions": data.get("suggestions", {}).get("suggested_questions", []),
        "flagged": screen(answer, sources_text) if status == "ok" else [],
        "sources_text": sources_text if status == "ok" else "",
    }


async def run() -> list[dict]:
    recorder = RecordingClaude(ClaudeClient.from_settings(os.environ["ANTHROPIC_API_KEY"]))
    service = ChatService(open_dense_retriever(os.environ["PINECONE_API_KEY"]), Bm25Index.load(INDEX_FILE), recorder,
                          min_dense_score=no_context_min_dense_score())
    results = []
    for q in QUESTIONS:
        recorder.last_messages = None
        results.append(await ask(service, recorder, q["question"]))
    return results


def main() -> int:
    load_env_files()
    if not (os.environ.get("PINECONE_API_KEY") and os.environ.get("ANTHROPIC_API_KEY")):
        print("Both keys are needed (ingestion/.env).")
        return 2
    results = asyncio.run(run())
    out_dir = Path(__file__).resolve().parent / "results"
    (out_dir / f"grounding_{date.today().isoformat()}.json").write_text(json.dumps(results, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"model={claude_model()}  questions={len(results)}  statuses={[r['status'] for r in results]}")
    for i, r in enumerate(results, start=1):
        print(f"\n[{i:02d}] {r['question']}   ({r['status']}, {r['seconds']}s)  sources={r['sources']}")
        print("     " + r["answer"].replace("\n", "\n     "))
        for f in r["flagged"]:
            print(f"     FLAG overlap={f['overlap']} numbers={f['numbers_not_in_sources']}: {f['sentence'][:160]}")
    print(f"\nFlagged sentences: {sum(len(r['flagged']) for r in results)} in {sum(1 for r in results if r['flagged'])} of {len(results)} answers")
    return 0


if __name__ == "__main__":
    sys.exit(main())
