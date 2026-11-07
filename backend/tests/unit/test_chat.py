"""T11 tests: POST /v1/chat wired from the existing parts, with every outside service faked.

Covers the happy path, each safety route, the no-context rule, error handling before and during
streaming, input limits, and that secrets and message text never leak into responses or logs.
"""
import json
import logging

import anthropic
import httpx
import pytest
from fastapi.testclient import TestClient

from conftest import bearer

from app.api.chat import get_chat_service
from app.chat.service import ChatService
from app.llm.claude import LLMError
from app.llm.output_format import SUGGESTIONS_MARKER
from app.llm.prompt import SYSTEM_PROMPT
from app.main import create_app
from app.retrieval.types import RetrievalError, RetrievedChunk
from app.safety import messages

IDENTITY = bearer()


def chunk(n: int, title: str = "Asthma", score: float = 0.9, url: str | None = None) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=f"c-{n}", doc_id="d", source_name="MedlinePlus", title=title,
        url=url or f"https://medlineplus.gov/{title.lower().replace(' ', '')}.html",
        text=f"{title} is explained here in chunk {n}. " * 8, retrieved_at="2026-10-31",
        licence="Public domain", attribution="Courtesy of MedlinePlus from the National Library of Medicine",
        score=score,
    )


class FakeRetriever:
    def __init__(self, hits=None, error: Exception | None = None):
        self.hits, self.error, self.queries = hits or [], error, []

    def search(self, query: str, top_k: int = 20):
        self.queries.append((query, top_k))
        if self.error:
            raise self.error
        return self.hits


class FakeClaudeStream:
    def __init__(self, pieces, stop_reason="end_turn", enter_error=None, error_after=None):
        self.pieces, self.stop_reason_value = pieces, stop_reason
        self.enter_error, self.error_after = enter_error, error_after
        self.stop_reason = None
        self.cancelled = self.closed = False

    async def __aenter__(self):
        if self.enter_error:
            raise self.enter_error
        return self

    async def __aexit__(self, *exc):
        self.closed = True
        return False

    def __aiter__(self):
        return self._iterate()

    async def _iterate(self):
        for index, piece in enumerate(self.pieces):
            if self.cancelled:
                return
            if self.error_after is not None and index == self.error_after:
                raise LLMError("upstream_error")
            yield piece
        self.stop_reason = self.stop_reason_value

    async def cancel(self):
        self.cancelled = True


class FakeClaude:
    def __init__(self, stream: FakeClaudeStream | None = None):
        self.stream_obj = stream or FakeClaudeStream([])
        self.calls: list[dict] = []

    def stream(self, system: str, messages_: list[dict]):
        self.calls.append({"system": system, "messages": messages_})
        return self.stream_obj


ANSWER = "Asthma is a chronic lung disease. It can cause wheezing and a cough.\n- Coughing\n- Wheezing\nTalk to a healthcare professional if symptoms get worse."
SUGGESTIONS = json.dumps({"questions": ["What triggers asthma attacks?", "How is asthma diagnosed?", "Can asthma be prevented?"]})


def good_claude(**kwargs) -> FakeClaude:
    pieces = [ANSWER[:30], ANSWER[30:90], ANSWER[90:], "\n" + SUGGESTIONS_MARKER[:8], SUGGESTIONS_MARKER[8:] + SUGGESTIONS]
    return FakeClaude(FakeClaudeStream(pieces, **kwargs))


def make_service(dense=None, bm25=None, claude=None, **kwargs) -> ChatService:
    return ChatService(
        dense=dense or FakeRetriever([chunk(1), chunk(2, "COPD", 0.88), chunk(3, "Lung Diseases", 0.87)]),
        bm25=bm25 if bm25 is not None else FakeRetriever([chunk(2, "COPD"), chunk(4, "Bronchitis"), chunk(1)]),
        claude=claude or good_claude(),
        **kwargs,
    )


def client_for(service: ChatService | None, **kwargs) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_chat_service] = lambda: service
    return TestClient(app, **kwargs)


def parse_sse(text: str) -> list[tuple[str, dict]]:
    events = []
    for block in text.strip().split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.splitlines())
        events.append((fields["event"], json.loads(fields["data"])))
    return events


def post(client: TestClient, message="What are the symptoms of asthma?", history=None, headers=IDENTITY):
    return client.post("/v1/chat", json={"message": message, "history": history or []}, headers=headers)


def names(events) -> list[str]:
    return [name for name, _ in events]


def text_of(events) -> str:
    return "".join(data["text"] for name, data in events if name == "token")


# ---------- happy path ----------

def test_a_grounded_answer_streams_tokens_then_sources_suggestions_safety_and_done():
    response = post(client_for(make_service()))
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = parse_sse(response.text)
    assert names(events)[-4:] == ["sources", "suggestions", "safety", "done"]
    assert set(names(events)[:-4]) == {"token"}
    assert text_of(events).rstrip() == ANSWER  # the newline before the marker is released with the answer


def test_the_marker_and_suggestion_json_never_reach_the_visible_answer():
    events = parse_sse(post(client_for(make_service())).text)
    visible = text_of(events)
    assert SUGGESTIONS_MARKER not in visible and "questions" not in visible


def test_sources_come_from_retrieved_metadata_one_entry_per_page():
    service = make_service(dense=FakeRetriever([chunk(1), chunk(2, "Asthma"), chunk(3, "COPD", 0.88)]), bm25=FakeRetriever([]))
    events = dict(parse_sse(post(client_for(service)).text))
    sources = events["sources"]["sources"]
    assert [s["title"] for s in sources] == ["Asthma", "COPD"]  # two chunks of the same page become one source
    first = sources[0]
    assert set(first) == {"title", "url", "snippet", "source_name", "attribution"}
    assert first["url"].startswith("https://medlineplus.gov/")
    assert "National Library of Medicine" in first["attribution"]
    assert len(first["snippet"]) <= 205


def test_suggestions_are_parsed_and_safety_carries_the_approved_disclaimer():
    events = dict(parse_sse(post(client_for(make_service())).text))
    assert events["suggestions"]["suggested_questions"] == ["What triggers asthma attacks?", "How is asthma diagnosed?", "Can asthma be prevented?"]
    assert events["safety"] == {"status": "ok", "disclaimer": messages.DISCLAIMER}


def test_unsafe_suggestions_are_filtered_out():
    bad = json.dumps({"questions": ["What dose of ibuprofen should I take?", "How is asthma diagnosed?"]})
    claude = FakeClaude(FakeClaudeStream(["Asthma is a lung condition. ", SUGGESTIONS_MARKER + bad]))
    events = dict(parse_sse(post(client_for(make_service(claude=claude))).text))
    assert events["suggestions"]["suggested_questions"] == ["How is asthma diagnosed?"]


def test_claude_receives_the_fixed_system_prompt_fenced_sources_and_the_question():
    claude = good_claude()
    post(client_for(make_service(claude=claude)))
    call = claude.calls[0]
    assert call["system"] == SYSTEM_PROMPT
    last = call["messages"][-1]
    assert last["role"] == "user"
    assert "<sources>" in last["content"] and '<source id="1"' in last["content"]
    assert "<question>What are the symptoms of asthma?</question>" in last["content"]


def test_both_retrievers_are_used_and_fused_with_rrf():
    dense, bm25 = FakeRetriever([chunk(1), chunk(2, "COPD")]), FakeRetriever([chunk(2, "COPD"), chunk(4, "Bronchitis")])
    claude = good_claude()
    post(client_for(make_service(dense=dense, bm25=bm25, claude=claude)))
    assert dense.queries == [("What are the symptoms of asthma?", 20)]
    assert bm25.queries == [("What are the symptoms of asthma?", 20)]
    content = claude.calls[0]["messages"][-1]["content"]
    # COPD was found by both retrievers, so it is ranked first by RRF.
    assert content.index('title="COPD"') < content.index('title="Asthma"')


def test_at_most_six_sources_are_sent_to_claude():
    many = [chunk(i, f"Topic {i}") for i in range(15)]
    claude = good_claude()
    post(client_for(make_service(dense=FakeRetriever(many), bm25=FakeRetriever([]), claude=claude)))
    assert claude.calls[0]["messages"][-1]["content"].count("<source ") == 6


def test_follow_up_questions_search_with_the_earlier_topic_added():
    dense, claude = FakeRetriever([chunk(1)]), good_claude()
    history = [{"role": "user", "content": "What is asthma?"}, {"role": "assistant", "content": "A lung condition."}]
    post(client_for(make_service(dense=dense, bm25=FakeRetriever([]), claude=claude)), "How is it treated?", history)
    assert "asthma" in dense.queries[0][0].lower() and "treated" in dense.queries[0][0].lower()
    roles = [m["role"] for m in claude.calls[0]["messages"]]
    assert roles == ["user", "assistant", "user"]


def test_chat_works_when_the_keyword_index_is_not_loaded():
    service = ChatService(dense=FakeRetriever([chunk(1)]), bm25=None, claude=good_claude())
    assert names(parse_sse(post(client_for(service)).text))[-1] == "done"


# ---------- safety routes: no retrieval, no Claude ----------

@pytest.mark.parametrize(
    "message, status, expected",
    [
        ("I can't breathe", "emergency", messages.EMERGENCY_MESSAGE),
        ("I want to kill myself", "emergency", messages.SELF_HARM_MESSAGE),
        ("How much paracetamol should I take?", "refused", messages.DOSING_REFUSAL),
        ("Do I have diabetes?", "refused", messages.DIAGNOSIS_REFUSAL),
        ("Can you prescribe me antibiotics?", "refused", messages.PRESCRIPTION_REFUSAL),
        ("Write me a poem about the sea", "refused", messages.OUT_OF_SCOPE_REFUSAL),
    ],
)
def test_unsafe_requests_get_the_fixed_reply_without_searching_or_calling_claude(message, status, expected):
    dense, bm25, claude = FakeRetriever([chunk(1)]), FakeRetriever([chunk(1)]), good_claude()
    events = parse_sse(post(client_for(make_service(dense=dense, bm25=bm25, claude=claude)), message).text)
    assert names(events) == ["token", "safety", "done"]
    assert text_of(events) == expected
    assert dict(events)["safety"] == {"status": status, "disclaimer": messages.DISCLAIMER}
    assert dense.queries == [] and bm25.queries == [] and claude.calls == []


# ---------- no context ----------

def test_a_weak_match_gives_the_no_context_reply_and_never_calls_claude():
    dense, claude = FakeRetriever([chunk(1, score=0.78)]), good_claude()
    events = parse_sse(post(client_for(make_service(dense=dense, claude=claude)), "How do I bake sourdough bread?").text)
    assert names(events) == ["token", "safety", "done"]
    assert text_of(events) == messages.NO_CONTEXT_MESSAGE
    assert dict(events)["safety"]["status"] == "no_context"
    assert claude.calls == []


def test_no_matches_at_all_is_also_no_context():
    events = parse_sse(post(client_for(make_service(dense=FakeRetriever([]), claude=good_claude()))).text)
    assert dict(events)["safety"]["status"] == "no_context"


def test_the_threshold_is_configurable():
    service = make_service(dense=FakeRetriever([chunk(1, score=0.80)]), min_dense_score=0.7)
    assert dict(parse_sse(post(client_for(service)).text))["safety"]["status"] == "ok"


# ---------- output guardrail while streaming ----------

def test_an_unsafe_sentence_is_never_sent_the_stream_is_cancelled_and_a_notice_is_added():
    stream = FakeClaudeStream(
        ["Asthma is a lung condition. ", "Take 500 mg of ibuprofen twice a day. ", "More text. ", SUGGESTIONS_MARKER + SUGGESTIONS]
    )
    claude = FakeClaude(stream)
    events = parse_sse(post(client_for(make_service(claude=claude))).text)
    visible = text_of(events)
    assert "Asthma is a lung condition." in visible
    assert "500 mg" not in visible and "More text" not in visible
    assert visible.endswith(messages.BLOCK_NOTICE)
    assert names(events)[-2:] == ["safety", "done"]
    assert dict(events)["safety"]["status"] == "refused"
    assert "sources" not in names(events) and "suggestions" not in names(events)
    assert stream.cancelled and stream.closed


def test_an_unsafe_first_sentence_leaves_only_the_notice():
    claude = FakeClaude(FakeClaudeStream(["You probably have diabetes. ", "Rest."]))
    events = parse_sse(post(client_for(make_service(claude=claude))).text)
    assert text_of(events) == messages.BLOCK_NOTICE


def test_a_refusal_from_the_model_is_reported_as_refused():
    claude = FakeClaude(FakeClaudeStream([], stop_reason="refusal"))
    events = parse_sse(post(client_for(make_service(claude=claude))).text)
    assert text_of(events) == messages.BLOCK_NOTICE
    assert dict(events)["safety"]["status"] == "refused"


def test_an_empty_answer_becomes_an_error_event():
    claude = FakeClaude(FakeClaudeStream([]))
    events = parse_sse(post(client_for(make_service(claude=claude))).text)
    assert names(events) == ["error"]
    assert events[0][1]["code"] == "upstream_error"


# ---------- failures ----------

def test_a_search_failure_before_streaming_is_a_502_json_error():
    service = make_service(dense=FakeRetriever(error=RetrievalError("Dense retrieval failed")))
    response = post(client_for(service))
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "upstream_error"


def test_claude_being_unreachable_before_streaming_is_a_502_json_error():
    claude = FakeClaude(FakeClaudeStream([], enter_error=LLMError("upstream_error")))
    response = post(client_for(make_service(claude=claude)))
    assert response.status_code == 502 and response.json()["error"]["code"] == "upstream_error"


def test_a_claude_timeout_before_streaming_is_a_504():
    claude = FakeClaude(FakeClaudeStream([], enter_error=LLMError("timeout", "too slow")))
    response = post(client_for(make_service(claude=claude)))
    assert response.status_code == 504 and response.json()["error"]["code"] == "timeout"


def test_a_failure_in_the_middle_of_streaming_becomes_an_error_event_after_earlier_text():
    stream = FakeClaudeStream(["Asthma is a lung condition. ", "It causes wheezing. ", "x"], error_after=2)
    events = parse_sse(post(client_for(make_service(claude=FakeClaude(stream)))).text)
    assert names(events)[-1] == "error"
    assert "Asthma is a lung condition." in text_of(events)
    assert "done" not in names(events) and "sources" not in names(events)
    assert stream.closed


def test_an_unconfigured_service_is_a_503():
    response = post(client_for(None))
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "service_unavailable"


# ---------- auth and limits ----------

def test_no_identity_is_a_401():
    assert post(client_for(make_service()), headers={}).status_code == 401


def test_over_long_messages_and_payloads_are_rejected_before_any_work():
    claude, dense = good_claude(), FakeRetriever([chunk(1)])
    client = client_for(make_service(dense=dense, claude=claude))
    assert post(client, "a" * 501).status_code == 422
    big = [{"role": "user" if i % 2 == 0 else "assistant", "content": "y" * 376} for i in range(20)]
    assert post(client, "m" * 500, big).status_code == 413
    assert dense.queries == [] and claude.calls == []


# ---------- secrets and privacy ----------

SECRET = "sk-ant-test-secret-0123456789abcdef"


def test_secrets_in_the_environment_and_in_provider_errors_never_reach_the_response(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", SECRET)
    monkeypatch.setenv("PINECONE_API_KEY", "pcsk_test_secret_0123456789abcdef")
    ok = post(client_for(make_service()))
    leaky = anthropic.APIConnectionError(request=httpx.Request("POST", f"https://api.example/?key={SECRET}"))
    failing = post(client_for(make_service(claude=FakeClaude(FakeClaudeStream([], enter_error=_translated(leaky))))))
    for response in (ok, failing):
        assert SECRET not in response.text and "pcsk_test_secret" not in response.text
        assert "ANTHROPIC_API_KEY" not in response.text and "api.example" not in response.text


def _translated(error):
    from app.llm.claude import _translate

    return _translate(error)


def test_logs_never_contain_the_message_text_history_or_secrets(caplog, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", SECRET)
    caplog.set_level(logging.DEBUG)
    private = "my private health worry about my left knee"
    history = [{"role": "user", "content": "earlier private detail"}, {"role": "assistant", "content": "earlier answer"}]
    post(client_for(make_service()), f"What are the symptoms of asthma? {private}"[:200], history)
    post(client_for(make_service()), "I can't breathe")
    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert private not in logged and "earlier private detail" not in logged and "can't breathe" not in logged
    assert SECRET not in logged


def test_a_chat_request_logs_only_counts_and_status(caplog):
    caplog.set_level(logging.INFO, logger="vitalnest")
    post(client_for(make_service()))
    lines = [r.getMessage() for r in caplog.records if r.name == "vitalnest" and r.getMessage().startswith("chat ")]
    assert len(lines) == 1
    assert "status=ok" in lines[0] and "dense_hits=" in lines[0]
