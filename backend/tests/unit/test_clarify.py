"""Clarifying questions for vague "I am unwell" messages: asked before any search, one at a time, never repeated."""
import pytest
from test_chat import chunk, good_claude, names, parse_sse, post, text_of
from test_chat_friendly import Scripted, client_for, corrector, service_with

from app.api.schemas import HistoryMessage
from app.chat import clarify
from app.chat.clarify import (
    ASK_HOW_LONG_REPLIES,
    ASK_MORE_REPLIES,
    ASK_WHAT_REPLIES,
    clarifying_question,
    context_prefix,
    is_symptom_without_duration,
    is_vague_unwell,
)
from app.safety import messages

VAGUE = [
    "I am not feeling well.", "I'm feeling sick", "I'm not feeling okay", "Something is wrong", "I need help with my health", "im not well",
    "I feel unwell", "Not feeling well", "feeling sick today", "I don't feel well", "I'm not feeling very well right now", "Something feels off",
    "I have a health problem", "I'm worried about my health", "I think I'm sick", "I am not feeling well, what should I do?",
    "Hey, I'm not feeling well", "I'm sick", "I feel terrible", "I'm in pain", "I'm not ok", "I feel bad", "ive been feeling unwell lately",
    "I have not been feeling well", "I AM NOT FEELING WELL!!!", "Something is wrong with me", "I feel sick 😞",
]
NOT_VAGUE = [
    "I'm feeling great", "I feel good", "I'm well, thanks", "What is asthma?", "I am not sure what to ask", "I am sick of this weather",
    "Why am I not feeling well after eating?", "hi", "What are the symptoms of the flu?", "How do I stay healthy?",
]
SYMPTOM_NO_DURATION = [
    "I've been having headaches", "I have a headache", "I feel dizzy", "my stomach hurts", "My back pain is bad", "I'm so tired",
    "I have a sore throat", "I keep coughing", "I feel anxious",
]
NOT_ASKED = [
    "I've had a headache since yesterday and I feel dizzy", "I have headaches for 3 days", "What causes headaches?",
    "I have a headache, what should I do?", "how to treat a headache", "headaches", "I have diabetes", "I had a fever two days ago",
    "I'm tired of waiting", "My headache started this morning", "Can headaches be caused by stress", "I have a headache. How do I treat it?",
]


def turns(*pairs):
    return [HistoryMessage(role=role, content=content) for role, content in pairs]


def first(replies):
    return replies[0]


@pytest.mark.parametrize("text", VAGUE)
def test_vague_unwell_statements_are_recognised(text):
    assert is_vague_unwell(text), text


@pytest.mark.parametrize("text", NOT_VAGUE)
def test_everything_else_is_not_vague(text):
    assert not is_vague_unwell(text), text


@pytest.mark.parametrize("text", SYMPTOM_NO_DURATION)
def test_symptom_statements_without_a_length_of_time_are_recognised(text):
    assert is_symptom_without_duration(text), text


@pytest.mark.parametrize("text", NOT_ASKED)
def test_questions_and_statements_with_enough_context_are_not_clarified(text):
    assert not is_symptom_without_duration(text), text
    assert clarifying_question(text, []) is None, text


# ---------- the three steps from the brief ----------

def test_step_1_vague_statement_asks_what_they_are_experiencing():
    reply = clarifying_question("I am not feeling well.", [], choose=first)
    assert reply == "I'm sorry you're not feeling well. Help me understand exactly what's going on. What are you experiencing right now?"


def test_step_2_a_symptom_asks_how_long_and_about_other_symptoms():
    history = turns(("user", "I am not feeling well."), ("assistant", ASK_WHAT_REPLIES[0]))
    reply = clarifying_question("I've been having headaches.", history, choose=first)
    assert reply == "How long have you been experiencing this? Have you noticed any other symptoms?"


def test_step_3_enough_context_means_no_question():
    history = turns(
        ("user", "I am not feeling well."), ("assistant", ASK_WHAT_REPLIES[0]),
        ("user", "I've been having headaches."), ("assistant", ASK_HOW_LONG_REPLIES[0]),
    )
    assert clarifying_question("I've had a headache since yesterday and I feel dizzy.", history) is None


# ---------- never repeat ----------

def test_the_same_question_is_never_asked_twice_in_a_row():
    history = turns(("user", "I am not feeling well"), ("assistant", ASK_WHAT_REPLIES[0]))
    again = clarifying_question("I feel bad", history, choose=first)
    assert again == ASK_MORE_REPLIES[0] and again not in ASK_WHAT_REPLIES


def test_after_two_questions_nothing_more_is_asked():
    history = turns(
        ("user", "I am not feeling well"), ("assistant", ASK_WHAT_REPLIES[0]),
        ("user", "I feel bad"), ("assistant", ASK_MORE_REPLIES[0]),
    )
    assert clarifying_question("I feel sick", history) is None
    assert clarifying_question("my head hurts", history) is None


def test_how_long_is_asked_only_once():
    history = turns(("user", "I have a headache"), ("assistant", ASK_HOW_LONG_REPLIES[0]))
    assert clarifying_question("my stomach hurts too", history) is None


def test_a_clarification_long_ago_does_not_count():
    history = turns(
        ("user", "I am not feeling well"), ("assistant", ASK_WHAT_REPLIES[0]),
        ("user", "What is asthma?"), ("assistant", "Asthma is a lung condition."),
    )
    assert clarifying_question("I am not feeling well", history) in ASK_WHAT_REPLIES


def test_history_that_is_malformed_is_handled():
    assert clarifying_question("I am not feeling well", turns(("assistant", ASK_WHAT_REPLIES[0]))) in ASK_WHAT_REPLIES
    assert clarifying_question("I am not feeling well", turns(("user", "x"), ("user", "y"))) in ASK_WHAT_REPLIES


# ---------- context for the search that follows ----------

def test_context_prefix_collects_what_was_said_after_the_questions_but_not_the_vague_opener():
    history = turns(
        ("user", "I am not feeling well"), ("assistant", ASK_WHAT_REPLIES[0]),
        ("user", "I've been having headaches"), ("assistant", ASK_HOW_LONG_REPLIES[0]),
    )
    assert context_prefix(history) == "I've been having headaches"


def test_context_prefix_is_empty_when_the_last_turn_was_not_a_clarification():
    assert context_prefix([]) == ""
    assert context_prefix(turns(("user", "What is asthma?"), ("assistant", "A lung condition."))) == ""


# ---------- through the real service ----------

@pytest.mark.parametrize("message", VAGUE[:8])
def test_a_vague_message_gets_a_question_and_calls_nothing(message):
    dense, bm25, claude = Scripted({}), Scripted({}), good_claude()
    from app.chat.service import ChatService

    events = parse_sse(post(client_for(ChatService(dense=dense, bm25=bm25, claude=claude)), message).text)
    assert names(events) == ["token", "safety", "done"]
    assert text_of(events) in ASK_WHAT_REPLIES
    assert dict(events)["safety"]["status"] == "ok"
    assert text_of(events) != messages.NO_CONTEXT_MESSAGE
    assert dense.queries == [] and bm25.queries == [] and claude.calls == []


def test_a_symptom_gets_the_how_long_question_without_any_search():
    dense, claude = Scripted({}), good_claude()
    events = parse_sse(post(client_for(service_with(dense, claude)), "I've been having headaches").text)
    assert text_of(events) in ASK_HOW_LONG_REPLIES
    assert dense.queries == [] and claude.calls == []


def test_the_full_conversation_ends_in_the_normal_pipeline_with_the_context_in_the_search():
    answer_query = "I've been having headaches I've had them since yesterday and I feel dizzy"
    dense = Scripted({answer_query: [chunk(1, "Headache")]})
    claude = good_claude()
    client = client_for(service_with(dense, claude))

    history: list[dict] = []
    first_events = parse_sse(post(client, "I am not feeling well.", history).text)
    history += [{"role": "user", "content": "I am not feeling well."}, {"role": "assistant", "content": text_of(first_events)}]
    second = parse_sse(post(client, "I've been having headaches", history).text)
    assert text_of(second) in ASK_HOW_LONG_REPLIES
    history += [{"role": "user", "content": "I've been having headaches"}, {"role": "assistant", "content": text_of(second)}]
    assert dense.queries == [] and claude.calls == []  # nothing searched during the questions

    third = parse_sse(post(client, "I've had them since yesterday and I feel dizzy", history).text)
    assert "sources" in names(third) and "token" in names(third)
    assert dense.queries == [answer_query]
    assert len(claude.calls) == 1


def test_a_message_with_enough_context_goes_straight_to_the_pipeline():
    message = "I've had a headache since yesterday and I feel dizzy"
    dense, claude = Scripted({message: [chunk(1, "Headache")]}), good_claude()
    events = parse_sse(post(client_for(service_with(dense, claude)), message).text)
    assert "sources" in names(events)
    assert dense.queries == [message] and len(claude.calls) == 1


@pytest.mark.parametrize("message", [
    "I am not feeling well and I can't breathe", "I'm not feeling well, I have chest pain", "I don't feel well, I want to kill myself",
    "I feel sick and my father is not breathing", "Something is wrong, I'm having a stroke",
])
def test_emergencies_and_self_harm_always_win_over_a_clarifying_question(message):
    dense, claude = Scripted({}), good_claude()
    events = parse_sse(post(client_for(service_with(dense, claude)), message).text)
    assert dict(events)["safety"]["status"] in ("emergency", "refused")
    assert text_of(events) not in clarify._ALL_REPLIES
    assert dense.queries == [] and claude.calls == []


def test_an_emergency_in_the_middle_of_a_clarification_still_wins():
    history = [{"role": "user", "content": "I am not feeling well"}, {"role": "assistant", "content": ASK_WHAT_REPLIES[0]}]
    events = parse_sse(post(client_for(service_with(Scripted({}))), "I have chest pain right now", history).text)
    assert dict(events)["safety"]["status"] == "emergency"


@pytest.mark.parametrize("message", ["Hey, what are asthma symptoms?", "thanks, but how is diabetes treated?", "What causes headaches?"])
def test_mixed_and_real_health_questions_are_not_clarified(message):
    dense, claude = Scripted({message: [chunk(1)]}), good_claude()
    events = parse_sse(post(client_for(service_with(dense, claude)), message).text)
    assert "sources" in names(events)
    assert dense.queries == [message]


def test_small_talk_still_wins_for_plain_openers_and_greetings():
    for message in ("I need help", "Hi", "How are you?"):
        events = parse_sse(post(client_for(service_with(Scripted({}))), message).text)
        assert text_of(events) not in clarify._ALL_REPLIES


def test_a_misspelled_vague_message_is_still_recognised():
    from app.retrieval.spelling import SpellingCorrector

    vocabulary = SpellingCorrector(["Feeling unwell is common. Feeling tired and feeling sick can have many causes."])
    dense, claude = Scripted({}), good_claude()
    events = parse_sse(post(client_for(service_with(dense, claude, vocabulary)), "I am not feling well").text)
    assert text_of(events) in ASK_WHAT_REPLIES  # "feling" is read as "feeling"
    assert dense.queries == [] and claude.calls == []
