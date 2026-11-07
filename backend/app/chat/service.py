"""The chat pipeline (T11): input check, query rewrite, BM25 + dense retrieval, RRF, prompt, Claude
streaming through the sentence-level output guard, then sources, suggestions and the disclaimer.

`prepare` does everything that can fail with a normal HTTP error (search, opening the Claude
stream) before any bytes are sent, so those failures return 502/504 JSON. After that the plan's
`events()` streams Server-Sent Events; a failure from then on becomes an `error` event.

Privacy: log lines carry counts, scores, status and timing only, never the message, history or answer.
"""
import asyncio
import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable

from app.api.schemas import ChatRequest
from app.api.sse import sse
from app.chat.small_talk import detect_small_talk
from app.conversation.handler import standalone_query
from app.llm.claude import LLMError
from app.llm.prompt import build_prompt
from app.llm.suggestions import suggestions_from_raw
from app.retrieval.rrf import reciprocal_rank_fusion
from app.retrieval.types import RetrievedChunk
from app.safety import messages
from app.safety.input_check import check_input
from app.safety.output_guard import StreamGuard

logger = logging.getLogger("vitalnest")

RETRIEVE_K = 20      # candidates from each retriever
FUSED_TOP_N = 6      # chunks sent to Claude after RRF
SNIPPET_CHARS = 200
MIN_IMPROVEMENT = 0.02  # a spelling correction must raise the best score by at least this much


def _plain(text: str) -> str:
    return text.casefold().replace("'", "").replace("\u2019", "").replace("-", "")


def _mentions(chunks: list[RetrievedChunk], words: list[str]) -> bool:
    """True if every corrected word appears in the title or text of the retrieved chunks."""
    blob = _plain(" ".join(f"{chunk.title} {chunk.text}" for chunk in chunks))
    return all(_plain(word) in blob for word in words)


def _snippet(text: str) -> str:
    if len(text) <= SNIPPET_CHARS:
        return text
    return text[:SNIPPET_CHARS].rsplit(" ", 1)[0] + "…"


def _sources(chunks: list[RetrievedChunk]) -> list[dict]:
    """One entry per page: several chunks of the same page are a single source."""
    seen: set[str] = set()
    sources = []
    for chunk in chunks:
        if chunk.url in seen:
            continue
        seen.add(chunk.url)
        sources.append(
            {
                "title": chunk.title,
                "url": chunk.url,
                "snippet": _snippet(chunk.text),
                "source_name": chunk.source_name,
                "attribution": chunk.attribution,
            }
        )
    return sources


class ChatPlan:
    """What to send back for one request. `close` releases the Claude connection (safe to call twice)."""

    def __init__(self, events: Callable[[], AsyncIterator[str]], close: Callable[[], Awaitable[None]] | None = None):
        self._events = events
        self._close = close

    def events(self) -> AsyncIterator[str]:
        return self._events()

    async def close(self) -> None:
        if self._close is not None:
            await self._close()


async def _fixed(events: list[str]) -> AsyncIterator[str]:
    for event in events:
        yield event


class ChatService:
    def __init__(self, dense, bm25, claude, min_dense_score: float = 0.84, corrector=None) -> None:
        self._dense = dense
        self._bm25 = bm25
        self._claude = claude
        self._min_dense_score = min_dense_score
        self._corrector = corrector

    # ---- phase 1: everything that can still become a normal HTTP error ----

    async def prepare(self, request: ChatRequest) -> ChatPlan:
        started = time.perf_counter()

        fixed, changes = self._corrector.correct(request.message) if self._corrector is not None else (request.message, [])

        verdict = check_input(request.message)
        if verdict.allowed and changes:
            # A misspelling must never hide an emergency, self-harm or an unsafe request, so the corrected
            # wording is checked too. This can only make the check stricter, never looser.
            verdict = check_input(fixed)
        if not verdict.allowed:
            self._log(verdict.status, started, category=verdict.category.value)
            return self._fixed_plan(verdict.status, verdict.response)

        talk = detect_small_talk(request.message)
        if talk is not None:
            self._log("small_talk", started)
            return self._fixed_plan("ok", talk.reply)

        question = request.message
        correction = None
        searches = [self._retrieve(standalone_query(request.message, request.history))]
        if changes:
            searches.append(self._retrieve(standalone_query(fixed, request.history)))
        results = await asyncio.gather(*searches, return_exceptions=True)
        if isinstance(results[0], BaseException):
            raise results[0]
        dense_hits, bm25_hits = results[0]
        if changes and not isinstance(results[1], BaseException):
            # Use the corrected spelling only if it finds good enough sources, never worse ones, and either clearly
            # better ones or sources that really contain the corrected word (scores of different pages are not
            # directly comparable, so a right page can win by a small margin). A correctly spelled question keeps
            # its own wording, and a change is always announced.
            fixed_dense, fixed_bm25 = results[1]
            gain = (fixed_dense[0].score if fixed_dense else 0.0) - (dense_hits[0].score if dense_hits else 0.0)
            if (
                not self._is_weak(fixed_dense)
                and gain >= 0
                and (gain >= MIN_IMPROVEMENT or _mentions(fixed_dense[:3], [new for _, new in changes]))
            ):
                dense_hits, bm25_hits, question = fixed_dense, fixed_bm25, fixed
                correction = {
                    "original": request.message,
                    "corrected": fixed,
                    "changes": [{"from": old, "to": new} for old, new in changes],
                }

        top_score = dense_hits[0].score if dense_hits else 0.0
        counts = {"dense_hits": len(dense_hits), "bm25_hits": len(bm25_hits), "top_dense": f"{top_score:.3f}"}
        if correction:
            counts["corrected"] = 1

        if self._is_weak(dense_hits):
            self._log("no_context", started, **counts)
            return self._fixed_plan("no_context", messages.NO_CONTEXT_MESSAGE)

        chunks = reciprocal_rank_fusion([bm25_hits, dense_hits], top_n=FUSED_TOP_N)
        prompt = build_prompt(question, request.history, chunks)
        stream = self._claude.stream(prompt.system, prompt.messages)
        await stream.__aenter__()  # connection failures surface here, before any bytes are sent

        async def close() -> None:
            await stream.__aexit__(None, None, None)

        return ChatPlan(lambda: self._generate(stream, chunks, question, correction, started, counts), close)

    def _is_weak(self, dense_hits) -> bool:
        """No hits, or a best score below the cutoff: the sources do not clearly cover the question."""
        return not dense_hits or dense_hits[0].score < self._min_dense_score

    async def _retrieve(self, query: str):
        """Both retrievers run at once. The dense one is required (its scores decide whether we have
        enough information); the keyword index is optional and only improves the ranking."""
        dense_task = asyncio.to_thread(self._dense.search, query, RETRIEVE_K)
        bm25_task = (
            asyncio.to_thread(self._bm25.search, query, RETRIEVE_K) if self._bm25 is not None else asyncio.sleep(0, [])
        )
        return await asyncio.gather(dense_task, bm25_task)

    # ---- phase 2: the stream ----

    def _fixed_plan(self, status: str, text: str) -> ChatPlan:
        events = [
            sse("token", {"text": text}),
            sse("safety", {"status": status, "disclaimer": messages.DISCLAIMER}),
            sse("done", {}),
        ]
        return ChatPlan(lambda: _fixed(events))

    async def _generate(self, stream, chunks, question, correction, started, counts) -> AsyncIterator[str]:
        guard = StreamGuard()
        released = False
        try:
            if correction:
                yield sse("corrected", correction)
            async for piece in stream:
                for text in guard.feed(piece):
                    released = True
                    yield sse("token", {"text": text})
                if guard.blocked:
                    await stream.cancel()  # stop paying for text we will never show
                    break
            if not guard.blocked:
                for text in guard.finish():
                    released = True
                    yield sse("token", {"text": text})

            if guard.blocked or (not released and stream.stop_reason == "refusal"):
                notice = messages.BLOCK_NOTICE if not released else "\n\n" + messages.BLOCK_NOTICE
                yield sse("token", {"text": notice})
                yield sse("safety", {"status": "refused", "disclaimer": messages.DISCLAIMER})
                yield sse("done", {})
                self._log("refused", started, **counts, reason=guard.block_reason.value if guard.block_reason else "model_refusal")
                return
            if not released:
                yield sse("error", {"code": "upstream_error", "message": "The AI service returned no answer."})
                self._log("error", started, **counts)
                return

            yield sse("sources", {"sources": _sources(chunks)})
            yield sse("suggestions", {"suggested_questions": suggestions_from_raw(guard.suggestions_raw, question)})
            yield sse("safety", {"status": "ok", "disclaimer": messages.DISCLAIMER})
            yield sse("done", {})
            self._log("ok", started, **counts)
        except LLMError as error:
            yield sse("error", {"code": error.code, "message": str(error)})
            self._log("error", started, **counts, code=error.code)
        finally:
            await stream.__aexit__(None, None, None)

    @staticmethod
    def _log(status: str, started: float, **fields) -> None:
        extra = " ".join(f"{key}={value}" for key, value in fields.items())
        logger.info("chat status=%s ms=%d %s", status, (time.perf_counter() - started) * 1000, extra)
