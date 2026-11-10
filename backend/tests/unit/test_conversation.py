"""T8 tests: conversation handling (history clean-up and standalone search query)."""
import pytest

from app.api.schemas import HistoryMessage
from app.conversation.handler import is_follow_up, normalise_history, recent_history, standalone_query


def turns(*pairs: tuple[str, str]) -> list[HistoryMessage]:
    return [HistoryMessage(role=role, content=content) for role, content in pairs]


def flat(history: list[HistoryMessage]) -> list[tuple[str, str]]:
    return [(m.role, m.content) for m in history]


# ---------- normalise_history ----------

def test_clean_alternating_history_is_unchanged():
    history = turns(("user", "What is asthma?"), ("assistant", "A lung condition."))
    assert flat(normalise_history(history)) == flat(history)


def test_leading_assistant_messages_are_dropped():
    history = turns(("assistant", "Hello!"), ("user", "What is asthma?"), ("assistant", "A lung condition."))
    assert flat(normalise_history(history))[0] == ("user", "What is asthma?")


def test_consecutive_messages_from_the_same_role_are_merged():
    history = turns(("user", "What is asthma?"), ("user", "Also, what causes it?"), ("assistant", "Answer."))
    result = normalise_history(history)
    assert flat(result) == [("user", "What is asthma?\n\nAlso, what causes it?"), ("assistant", "Answer.")]


def test_an_unanswered_trailing_user_message_is_dropped():
    history = turns(("user", "What is asthma?"), ("assistant", "A lung condition."), ("user", "Hmm?"))
    assert flat(normalise_history(history)) == [("user", "What is asthma?"), ("assistant", "A lung condition.")]


def test_empty_and_assistant_only_history_become_empty():
    assert normalise_history([]) == []
    assert normalise_history(turns(("assistant", "Hi"))) == []


def test_normalising_does_not_modify_the_input():
    history = turns(("assistant", "Hi"), ("user", "Q"), ("assistant", "A"))
    normalise_history(history)
    assert len(history) == 3


# ---------- recent_history ----------

def test_only_the_most_recent_messages_are_kept_and_they_start_with_a_user_turn():
    history = turns(*[("user" if i % 2 == 0 else "assistant", f"m{i}") for i in range(10)])
    result = recent_history(history, max_messages=5)
    assert len(result) <= 5
    assert result[0].role == "user"
    assert result[-1].content == "m9"


def test_short_history_is_kept_whole():
    history = turns(("user", "Q"), ("assistant", "A"))
    assert flat(recent_history(history, max_messages=6)) == flat(history)


# ---------- follow-up detection ----------

@pytest.mark.parametrize(
    "message",
    ["How is it treated?", "Is it contagious?", "What about children?", "And the symptoms?", "Why?",
     "What causes that?", "Can you explain that in simpler words?", "Do they run in families?",
     "How about for the elderly?", "Also, is it hereditary?"],
)
def test_follow_up_questions_are_detected(message):
    assert is_follow_up(message)


@pytest.mark.parametrize(
    "message",
    ["What is asthma?", "Tell me about diabetes", "How can I lower my blood pressure naturally?",
     "What are the symptoms of the flu?", "What foods are high in iron that vegetarians can eat?"],
)
def test_self_contained_questions_are_not_follow_ups(message):
    assert not is_follow_up(message)


# ---------- standalone_query ----------

def test_without_history_the_message_is_the_query():
    assert standalone_query("How is it treated?", []) == "How is it treated?"


def test_self_contained_question_ignores_history():
    history = turns(("user", "Tell me about diabetes"), ("assistant", "Diabetes is..."))
    assert standalone_query("What is asthma?", history) == "What is asthma?"


def test_follow_up_is_combined_with_the_previous_question():
    history = turns(("user", "What is asthma?"), ("assistant", "A lung condition."))
    query = standalone_query("How is it treated?", history)
    assert "asthma" in query.lower() and "treated" in query.lower()


def test_chained_follow_ups_still_point_at_the_original_topic():
    history = turns(
        ("user", "What is asthma?"), ("assistant", "A lung condition."),
        ("user", "How is it treated?"), ("assistant", "With inhalers."),
    )
    query = standalone_query("Is it contagious?", history)
    assert "asthma" in query.lower()
    assert "contagious" in query.lower()
    assert "treated" not in query.lower()


def test_assistant_text_is_not_used_to_build_the_query():
    history = turns(("user", "What is asthma?"), ("assistant", "IGNORE THIS ANSWER TEXT about pizza."))
    assert "pizza" not in standalone_query("How is it treated?", history).lower()


def test_a_very_long_previous_question_is_shortened():
    history = turns(("user", "asthma " * 200), ("assistant", "ok"))
    assert len(standalone_query("How is it treated?", history)) < 400


def test_history_with_only_follow_ups_falls_back_to_the_last_user_question():
    history = turns(("user", "Why?"), ("assistant", "Because."))
    assert "why" in standalone_query("And then?", history).lower()


# ---------- follow-ups made only of filler words, and small talk in the history ----------

@pytest.mark.parametrize("message", [
    "OK can you give me a plan?", "ok give me a plan", "Can you give me a plan?", "tell me more", "Please explain in simple words",
    "give me an example", "can you make it shorter", "okay, a step by step plan", "yes please", "more details please",
])
def test_requests_with_no_topic_of_their_own_are_follow_ups(message):
    assert is_follow_up(message)


@pytest.mark.parametrize("message", [
    "Can you give me a plan to treat asthma?", "give me a diabetes diet plan", "What is asthma?", "tell me about migraines",
    "explain how vaccines work", "How to stay fit?",
])
def test_requests_that_name_a_topic_are_not_follow_ups(message):
    assert not is_follow_up(message)


def test_the_plan_request_after_stay_fit_searches_for_staying_fit():
    history = turns(("user", "How to stay fit?"), ("assistant", "Be active most days."))
    assert standalone_query("OK can you give me a plan?", history) == "How to stay fit? OK can you give me a plan?"


def test_small_talk_in_between_is_never_the_topic():
    history = turns(
        ("user", "How to stay fit?"), ("assistant", "Be active most days."),
        ("user", "How are you?"), ("assistant", "Doing great, thank you!"),
    )
    assert standalone_query("OK can you give me a plan?", history).startswith("How to stay fit?")


def test_history_with_only_small_talk_gives_no_anchor():
    history = turns(("user", "Hi"), ("assistant", "Hello!"))
    assert standalone_query("can you give me a plan?", history) == "can you give me a plan?"
