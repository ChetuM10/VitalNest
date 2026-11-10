"""Chat: friendly small talk, and the spelling-correction fallback (with the 'Showing results for' event)."""
import logging

import pytest
from fastapi.testclient import TestClient

from app.api.chat import get_chat_service
from app.chat import factory
from app.chat.service import ChatService
from app.main import create_app
from app.retrieval.spelling import SpellingCorrector
from app.retrieval.types import RetrievalError
from app.safety import messages
from test_chat import FakeClaude, IDENTITY, chunk, good_claude, names, parse_sse, post, text_of

CORPUS = [
    "Alzheimer's Disease Alzheimer's disease is the most common cause of dementia in older adults.",
    "Diabetes Diabetes is a disease. Symptoms of diabetes vary. Asthma symptoms include wheezing. Do not hurt myself. What should I take?",
]


class Scripted:
    """A retriever whose result depends on the exact query text."""

    def __init__(self, results: dict[str, list], errors: dict[str, Exception] | None = None):
        self.results, self.errors, self.queries = results, errors or {}, []

    def search(self, query: str, top_k: int = 20):
        self.queries.append(query)
        if query in self.errors:
            raise self.errors[query]
        return self.results.get(query, [])


def client_for(service) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_chat_service] = lambda: service
    return TestClient(app)


def service_with(dense, claude=None, corrector=None) -> ChatService:
    return ChatService(dense=dense, bm25=Scripted({}), claude=claude or good_claude(), corrector=corrector)


# ---------- small talk ----------

@pytest.mark.parametrize(
    "message, reply",
    [("Hi", messages.GREETING_REPLIES), ("Hello, how are you?", messages.HOW_ARE_YOU_REPLIES),
     ("What can you do?", (messages.GREETING_MESSAGE,)), ("Thank you!", messages.THANKS_REPLIES), ("Goodbye", messages.GOODBYE_REPLIES),
     ("I need help", messages.OPENER_REPLIES)],
)
def test_small_talk_gets_a_friendly_reply_without_searching_or_calling_claude(message, reply):
    dense, claude = Scripted({}), good_claude()
    events = parse_sse(post(client_for(service_with(dense, claude)), message).text)
    assert names(events) == ["token", "safety", "done"]
    assert text_of(events) in reply
    assert dict(events)["safety"] == {"status": "ok", "disclaimer": messages.DISCLAIMER}
    assert dense.queries == [] and claude.calls == []


def test_a_real_question_after_a_greeting_word_is_still_answered():
    dense = Scripted({"hi what is asthma": [chunk(1)]})
    events = parse_sse(post(client_for(service_with(dense)), "hi what is asthma").text)
    assert "sources" in names(events)
    assert dense.queries == ["hi what is asthma"]


def test_a_greeting_together_with_an_emergency_is_an_emergency():
    events = parse_sse(post(client_for(service_with(Scripted({}))), "Hi, I can't breathe").text)
    assert dict(events)["safety"]["status"] == "emergency"
    assert text_of(events) == messages.EMERGENCY_MESSAGE


# ---------- spelling correction ----------

TYPO, FIXED = "Tell me about Alzeihmers", "Tell me about Alzheimer's"


def corrector() -> SpellingCorrector:
    return SpellingCorrector(CORPUS)


def test_a_misspelled_question_is_retried_with_the_correction_and_the_change_is_announced_first():
    dense = Scripted({TYPO: [chunk(1, score=0.80)], FIXED: [chunk(1, "Alzheimer's Disease", score=0.90)]})
    claude = good_claude()
    events = parse_sse(post(client_for(service_with(dense, claude, corrector())), TYPO).text)
    assert names(events)[0] == "corrected"
    assert events[0][1] == {"original": TYPO, "corrected": FIXED, "changes": [{"from": "Alzeihmers", "to": "Alzheimer's"}]}
    assert names(events)[-4:] == ["sources", "suggestions", "safety", "done"]
    assert dense.queries == [TYPO, FIXED]
    assert "<question>Tell me about Alzheimer&#x27;s</question>" in claude.calls[0]["messages"][-1]["content"]


def test_a_question_that_already_works_keeps_its_own_wording_when_the_correction_is_not_clearly_better():
    dense = Scripted({TYPO: [chunk(1, score=0.90)], FIXED: [chunk(1, score=0.905)]})
    events = parse_sse(post(client_for(service_with(dense, corrector=corrector())), TYPO).text)
    assert "corrected" not in names(events)
    assert dict(events)["safety"]["status"] == "ok"
    assert dense.queries == [TYPO, FIXED]  # both were tried; the original was kept


def test_a_misspelling_that_still_finds_an_answer_is_corrected_when_that_finds_clearly_better_sources():
    dense = Scripted({TYPO: [chunk(1, score=0.86)], FIXED: [chunk(1, "Alzheimer's Disease", score=0.90)]})
    events = parse_sse(post(client_for(service_with(dense, corrector=corrector())), TYPO).text)
    assert events[0][0] == "corrected" and events[0][1]["corrected"] == FIXED


def test_a_right_page_that_wins_by_a_small_margin_is_accepted_when_it_contains_the_corrected_word():
    # The typo still scores just above the cutoff but finds the wrong page; the corrected search finds the right one.
    wrong = chunk(1, "Amyotrophic Lateral Sclerosis", score=0.847)
    right = chunk(2, "Alzheimer's Disease", score=0.859)
    dense = Scripted({TYPO: [wrong], FIXED: [right]})
    events = parse_sse(post(client_for(service_with(dense, corrector=corrector())), TYPO).text)
    assert events[0][0] == "corrected"
    assert dict(events)["sources"]["sources"][0]["title"] == "Alzheimer's Disease"


def test_a_corrected_search_that_is_worse_is_never_used_even_if_it_mentions_the_word():
    dense = Scripted({TYPO: [chunk(1, score=0.90)], FIXED: [chunk(2, "Alzheimer's Disease", score=0.88)]})
    events = parse_sse(post(client_for(service_with(dense, corrector=corrector())), TYPO).text)
    assert "corrected" not in names(events)


def test_a_failure_of_the_corrected_search_never_breaks_the_original_answer():
    dense = Scripted({TYPO: [chunk(1, score=0.90)]}, errors={FIXED: RetrievalError("boom")})
    events = parse_sse(post(client_for(service_with(dense, corrector=corrector())), TYPO).text)
    assert "corrected" not in names(events) and dict(events)["safety"]["status"] == "ok"


def test_a_failure_of_the_original_search_is_still_an_error():
    dense = Scripted({FIXED: [chunk(1, score=0.90)]}, errors={TYPO: RetrievalError("boom")})
    assert post(client_for(service_with(dense, corrector=corrector())), TYPO).status_code == 502


def test_a_correction_that_barely_helps_is_not_used():
    dense = Scripted({TYPO: [chunk(1, score=0.839)], FIXED: [chunk(1, score=0.85)]})  # passes the cutoff, but only +0.011
    claude = good_claude()
    events = parse_sse(post(client_for(service_with(dense, claude, corrector())), TYPO).text)
    assert dict(events)["safety"]["status"] == "no_context"
    assert "corrected" not in names(events) and claude.calls == []


def test_a_correction_that_still_finds_nothing_leaves_the_no_context_reply():
    dense = Scripted({TYPO: [chunk(1, score=0.80)], FIXED: [chunk(1, score=0.82)]})
    events = parse_sse(post(client_for(service_with(dense, corrector=corrector())), TYPO).text)
    assert dict(events)["safety"]["status"] == "no_context"
    assert "corrected" not in names(events)


def test_no_retry_when_nothing_in_the_question_looks_misspelled():
    dense = Scripted({"How do I bake sourdough bread?": [chunk(1, score=0.78)]})
    events = parse_sse(post(client_for(service_with(dense, corrector=corrector())), "How do I bake sourdough bread?").text)
    assert dict(events)["safety"]["status"] == "no_context"
    assert len(dense.queries) == 1


def test_without_a_corrector_a_weak_question_just_gets_the_no_context_reply():
    dense = Scripted({TYPO: [chunk(1, score=0.80)]})
    events = parse_sse(post(client_for(service_with(dense, corrector=None)), TYPO).text)
    assert dict(events)["safety"]["status"] == "no_context"
    assert dense.queries == [TYPO]


def test_the_correction_applies_to_follow_up_questions_too():
    dense = Scripted({
        "What is Alzheimer's? How is it treatd?": [],
    })
    # the follow-up search text includes the earlier question; a misspelling in the new message is still corrected
    corr = SpellingCorrector(["Alzheimer's disease is treated with medicine. Treated early, symptoms improve."])
    history = [{"role": "user", "content": "What is Alzheimer's?"}, {"role": "assistant", "content": "A brain disease."}]
    original_query = "What is Alzheimer's? How is it treatd?"
    dense.results[original_query] = [chunk(1, score=0.80)]
    dense.results["What is Alzheimer's? How is it treated?"] = [chunk(1, score=0.89)]
    events = parse_sse(post(client_for(service_with(dense, corrector=corr)), "How is it treatd?", history).text)
    assert events[0] == ("corrected", {"original": "How is it treatd?", "corrected": "How is it treated?", "changes": [{"from": "treatd", "to": "treated"}]})


def test_logs_note_that_a_correction_was_used_but_never_the_text(caplog):
    caplog.set_level(logging.INFO, logger="vitalnest")
    dense = Scripted({TYPO: [chunk(1, score=0.80)], FIXED: [chunk(1, score=0.90)]})
    post(client_for(service_with(dense, corrector=corrector())), TYPO)
    lines = [r.getMessage() for r in caplog.records if r.getMessage().startswith("chat ")]
    assert len(lines) == 1 and "corrected=1" in lines[0]
    assert "Alzeihmers" not in caplog.text and "Alzheimer" not in caplog.text


# ---------- startup wiring ----------

class FakeBm25:
    def texts(self):
        return CORPUS

    def titles(self):
        return ["Alzheimer's Disease"]


def test_the_service_gets_a_spelling_corrector_when_the_keyword_index_is_loaded(monkeypatch):
    monkeypatch.setenv("PINECONE_API_KEY", "pcsk_test_key_value")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key-value")
    monkeypatch.setattr(factory, "open_dense_retriever", lambda key, index: object())
    monkeypatch.setattr(factory.ClaudeClient, "from_settings", classmethod(lambda cls, key: object()))
    with_index = factory.build_chat_service(bm25=FakeBm25())
    assert with_index is not None and with_index._corrector.correct("Alzeihmers")[0] == "Alzheimer's"
    assert factory.build_chat_service(bm25=None)._corrector is None


# ---------- spelling must never get in the way of safety ----------

def test_a_misspelled_self_harm_message_is_still_caught_after_correction():
    dense, claude = Scripted({}), good_claude()
    events = parse_sse(post(client_for(service_with(dense, claude, corrector())), "I want to hurt myslef").text)
    assert text_of(events) == messages.SELF_HARM_MESSAGE
    assert dict(events)["safety"]["status"] == "emergency"
    assert dense.queries == [] and claude.calls == []


def test_a_misspelled_dosing_request_is_still_refused_after_correction():
    dense, claude = Scripted({}), good_claude()
    events = parse_sse(post(client_for(service_with(dense, claude, corrector())), "How much paracetamol shoud I take?").text)
    assert text_of(events) == messages.DOSING_REFUSAL
    assert dense.queries == [] and claude.calls == []


def test_the_original_wording_is_checked_first_and_still_wins():
    events = parse_sse(post(client_for(service_with(Scripted({}), corrector=corrector())), "I can't breathe, diabtes").text)
    assert text_of(events) == messages.EMERGENCY_MESSAGE


@pytest.mark.parametrize("message", ["Good morning, I want to kill myself", "hey I overdosed", "Hi, I can't breathe", "thanks, I think I'm having a heart attack"])
def test_small_talk_words_never_hide_an_emergency(message):
    dense, claude = Scripted({}), good_claude()
    events = parse_sse(post(client_for(service_with(dense, claude, corrector())), message).text)
    assert dict(events)["safety"]["status"] == "emergency"
    assert dense.queries == [] and claude.calls == []


# ---------- small talk variations ----------

@pytest.mark.parametrize(
    "message, reply",
    [
        ("What's up", messages.CASUAL_REPLIES), ("hey there, how's it going?", messages.HOW_ARE_YOU_REPLIES), ("Good Evening!", messages.GREETING_REPLIES),
        ("HELLO!!!", messages.GREETING_REPLIES), ("Hi 👋", messages.GREETING_REPLIES),
        ("Appreciate it", messages.THANKS_REPLIES), ("Thanks a lot!", messages.THANKS_REPLIES), ("thank-you", messages.THANKS_REPLIES),
        ("Catch you later", messages.GOODBYE_REPLIES), ("take care!", messages.GOODBYE_REPLIES), ("See you", messages.GOODBYE_REPLIES),
        ("thanks, bye", messages.GOODBYE_REPLIES),
        ("Can you help me?", messages.OPENER_REPLIES), ("I have a question", messages.OPENER_REPLIES), ("How are you?", messages.HOW_ARE_YOU_REPLIES),
    ],
)
def test_small_talk_variations_never_reach_pinecone_bm25_or_claude(message, reply):
    dense, bm25, claude = Scripted({}), Scripted({}), good_claude()
    service = ChatService(dense=dense, bm25=bm25, claude=claude, corrector=corrector())
    events = parse_sse(post(client_for(service), message).text)
    assert names(events) == ["token", "safety", "done"]
    assert text_of(events) in reply
    assert dense.queries == [] and bm25.queries == [] and claude.calls == []


@pytest.mark.parametrize("message", ["Hey, what are asthma symptoms?", "Hello, can you tell me about diabetes?", "thanks, but how is it treated?"])
def test_real_questions_with_small_talk_words_go_through_the_normal_pipeline(message):
    dense, bm25, claude = Scripted({message: [chunk(1)]}), Scripted({}), good_claude()
    service = ChatService(dense=dense, bm25=bm25, claude=claude)
    events = parse_sse(post(client_for(service), message).text)
    assert "sources" in names(events) and "token" in names(events)
    assert dense.queries == [message] and bm25.queries == [message] and len(claude.calls) == 1


@pytest.mark.parametrize("message", ["Help me, I can't breathe", "I need help, my father has chest pain right now", "hi I want to kill myself"])
def test_openers_and_greetings_with_an_emergency_are_still_emergencies(message):
    dense, claude = Scripted({}), good_claude()
    events = parse_sse(post(client_for(service_with(dense, claude)), message).text)
    assert dict(events)["safety"]["status"] in ("emergency", "refused")
    assert dense.queries == [] and claude.calls == []


def test_a_vague_opener_never_gets_the_no_context_reply():
    dense = Scripted({})
    events = parse_sse(post(client_for(service_with(dense)), "I need help").text)
    assert text_of(events) in messages.OPENER_REPLIES
    assert text_of(events) != messages.NO_CONTEXT_MESSAGE
