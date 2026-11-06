"""T9 tests: suggested questions (parse the model's JSON, then filter through the safety checks)."""
import json

import pytest

from app.llm.suggestions import MAX_SUGGESTIONS, parse_suggestions, suggestions_from_raw


def raw(questions) -> str:
    return json.dumps({"questions": questions})


GOOD = ["What triggers asthma attacks?", "How is asthma diagnosed?", "Can asthma be prevented?"]


def test_valid_json_gives_the_questions_in_order():
    assert parse_suggestions(raw(GOOD)) == GOOD


def test_code_fences_and_surrounding_text_are_tolerated():
    assert parse_suggestions("```json\n" + raw(GOOD) + "\n```") == GOOD
    assert parse_suggestions("Here you go: " + raw(GOOD) + " Thanks!") == GOOD


def test_a_bare_json_list_is_accepted():
    assert parse_suggestions(json.dumps(GOOD)) == GOOD


@pytest.mark.parametrize("bad", ["", "   ", "not json", "{broken", '{"questions": "nope"}', '{"other": []}', "null", "42"])
def test_unparseable_or_wrongly_shaped_output_gives_an_empty_list(bad):
    assert parse_suggestions(bad) == []


def test_non_string_empty_and_overlong_items_are_dropped():
    questions = [123, None, "", "   ", "x" * 200 + "?", "Valid question here?"]
    assert parse_suggestions(raw(questions)) == ["Valid question here?"]


def test_items_that_are_not_questions_are_dropped():
    assert parse_suggestions(raw(["Asthma is a lung disease.", "What is asthma?"])) == ["What is asthma?"]


def test_items_containing_line_breaks_are_dropped():
    assert parse_suggestions(raw(["What is\nasthma?", "What is asthma?"])) == ["What is asthma?"]


def test_whitespace_is_trimmed_and_duplicates_removed_ignoring_case():
    assert parse_suggestions(raw(["  What is asthma? ", "what is ASTHMA?", "How is it treated?"])) == [
        "What is asthma?",
        "How is it treated?",
    ]


def test_at_most_three_suggestions_are_returned():
    many = [f"What is question number {i}?" for i in range(8)]
    assert len(parse_suggestions(raw(many))) == MAX_SUGGESTIONS == 3


# ---------- safety filtering ----------

def test_suggestions_that_the_input_check_would_refuse_are_removed():
    questions = ["What dose of ibuprofen should I take?", "Do I have asthma?", "What triggers asthma attacks?"]
    assert suggestions_from_raw(raw(questions), current_question="What is asthma?") == ["What triggers asthma attacks?"]


def test_suggestions_that_the_output_check_would_block_are_removed():
    questions = ["Why do you probably have diabetes?", "How is diabetes diagnosed?"]
    assert suggestions_from_raw(raw(questions), current_question="What is diabetes?") == ["How is diabetes diagnosed?"]


def test_the_question_just_asked_is_not_suggested_back():
    questions = ["What is asthma?", "How is asthma treated?"]
    assert suggestions_from_raw(raw(questions), current_question="what is asthma?") == ["How is asthma treated?"]


def test_filtering_can_leave_fewer_than_three_or_none():
    assert len(suggestions_from_raw(raw(GOOD[:2]), current_question="Q?")) == 2
    assert suggestions_from_raw(raw(["Do I have asthma?"]), current_question="Q?") == []


def test_garbage_input_never_raises():
    assert suggestions_from_raw("}{ not json", current_question="What is asthma?") == []
    assert suggestions_from_raw("", current_question="What is asthma?") == []
