"""T10 tests: streaming output guardrail (sentence checker, sentence splitter, stream guard).

The checker is rule-based and blunt, like the input check: it catches common unsafe patterns
in a model's answer and does not guarantee medical safety.
"""
import pytest

from app.llm.output_format import SUGGESTIONS_MARKER
from app.safety.output_guard import (
    OutputIssue,
    StreamGuard,
    check_sentence,
    split_complete_sentences,
)

DOSAGE = [
    "Take 500 mg of ibuprofen every 6 hours.",
    "Adults can take two tablets twice a day.",
    "Give your child 5 ml of the syrup three times a day.",
    "The usual dose is 10 mg once daily.",
    "Take 2 pills before bed.",
]
DIAGNOSIS = [
    "You probably have diabetes.",
    "Based on your symptoms, you have pneumonia.",
    "It sounds like you have an infection.",
    "You are suffering from depression.",
    "Your symptoms indicate that you have asthma.",
    "This is definitely cancer.",
    "I think you have the flu.",
]
MEDICATION_CHANGE = [
    "You should stop taking your blood pressure medicine.",
    "Stop taking your medication right away.",
    "You can safely skip your insulin tonight.",
    "Double your dose if symptoms get worse.",
    "Increase your inhaler use.",
]
PRESCRIBING = [
    "I recommend you take ibuprofen.",
    "You should take paracetamol for the pain.",
    "I suggest that you start antibiotics.",
    "You need to take an antibiotic.",
]
SAFE = [
    "Asthma is a chronic disease that affects your airways.",
    "A normal A1C level is below 5.7%.",
    "Many people with high blood pressure have no symptoms.",
    "If you have any of these symptoms, call your doctor.",
    "You have the right to ask questions about your care.",
    "Doctors diagnose asthma with a breathing test.",
    "Do not stop taking your medicine without talking to your provider.",
    "Talk to your provider before you stop taking any medicine.",
    "Never skip your insulin.",
    "Adults should limit sodium to 2,300 mg per day.",
    "Brush your teeth twice a day.",
    "Eat at least 25 g of fibre a day.",
    "Take a deep breath and relax.",
    "Take your medicine as prescribed by your provider.",
    "People with asthma should take their controller medicine every day as their provider directs.",
    "Symptoms include fever, cough and shortness of breath.",
    "- Coughing",
    "Your provider may recommend medicines to control your symptoms.",
    "In some cases, your provider may decide to change your medicines.",
    "Ask whether you need to take antibiotics before dental work or surgery.",
    "If you need to take antibiotics before dental work, your provider will tell you.",
    "If you have type 1 diabetes, you must take insulin because your body no longer makes it.",
    "Most side effects go away after you stop taking the medicine.",
    "Limit sodium to about 1 teaspoon of salt a day.",
]


@pytest.mark.parametrize(
    "sentences, issue",
    [
        (DOSAGE, OutputIssue.DOSAGE),
        (DIAGNOSIS, OutputIssue.DIAGNOSIS),
        (MEDICATION_CHANGE, OutputIssue.MEDICATION_CHANGE),
        (PRESCRIBING, OutputIssue.PRESCRIBING),
    ],
    ids=["dosage", "diagnosis", "medication_change", "prescribing"],
)
def test_unsafe_sentences_are_blocked_with_the_right_issue(sentences, issue):
    for sentence in sentences:
        result = check_sentence(sentence)
        assert not result.allowed, sentence
        assert result.issue == issue, sentence


@pytest.mark.parametrize("sentence", SAFE)
def test_ordinary_health_information_passes(sentence):
    result = check_sentence(sentence)
    assert result.allowed, sentence
    assert result.issue is None


def test_a_dosage_split_across_two_sentences_is_caught_using_the_previous_one():
    assert check_sentence("Take this medicine.").allowed
    assert not check_sentence("500 mg twice a day.", previous="Take this medicine.").allowed


def test_case_and_spacing_do_not_hide_unsafe_text():
    assert not check_sentence("TAKE   500 MG  of ibuprofen").allowed


# ---------- sentence splitting ----------

def test_complete_sentences_are_split_and_the_unfinished_tail_is_kept():
    done, rest = split_complete_sentences("Asthma is common. It causes wheezing. And coug")
    assert [s for s, _ in done] == ["Asthma is common.", "It causes wheezing."]
    assert rest == "And coug"


def test_separators_are_preserved_so_text_can_be_rebuilt():
    done, rest = split_complete_sentences("One. Two.\nThree")
    assert "".join(s + sep for s, sep in done) + rest == "One. Two.\nThree"


def test_a_full_stop_at_the_very_end_waits_for_more_text():
    done, rest = split_complete_sentences("Asthma is common.")
    assert done == [] and rest == "Asthma is common."


def test_decimals_do_not_split_sentences():
    done, _ = split_complete_sentences("A level below 5.7 percent is normal. Next")
    assert [s for s, _ in done] == ["A level below 5.7 percent is normal."]


def test_abbreviations_do_not_split_sentences():
    done, _ = split_complete_sentences("Dr. Smith said e.g. this works. Done")
    assert [s for s, _ in done] == ["Dr. Smith said e.g. this works."]


def test_newlines_split_list_items():
    done, rest = split_complete_sentences("- Cough\n- Fever\n- Fatig")
    assert [s for s, _ in done] == ["- Cough", "- Fever"]
    assert rest == "- Fatig"


def test_question_and_exclamation_marks_end_sentences():
    done, _ = split_complete_sentences("Is it serious? Yes! Maybe")
    assert [s for s, _ in done] == ["Is it serious?", "Yes!"]


# ---------- stream guard ----------

def run(guard: StreamGuard, pieces: list[str]) -> list[str]:
    approved: list[str] = []
    for piece in pieces:
        approved.extend(guard.feed(piece))
    approved.extend(guard.finish())
    return approved


def by_char(text: str) -> list[str]:
    return list(text)


ANSWER = "Asthma is a lung condition. It causes wheezing.\n- Cough\n- Fever\nSee a provider if it gets worse."


def test_safe_text_comes_out_unchanged_however_it_is_chunked():
    for pieces in (by_char(ANSWER), [ANSWER], [ANSWER[:17], ANSWER[17:40], ANSWER[40:]]):
        guard = StreamGuard()
        assert "".join(run(guard, pieces)) == ANSWER
        assert not guard.blocked


def test_nothing_is_released_before_a_sentence_is_complete():
    guard = StreamGuard()
    assert guard.feed("Asthma is a lung") == []
    assert guard.feed(" condition. ") == []  # the next word could still change the boundary
    assert "".join(guard.feed("It")).startswith("Asthma is a lung condition.")


def test_an_unsafe_sentence_is_never_released_and_stops_the_stream():
    guard = StreamGuard()
    released = run(guard, ["Asthma is common. ", "Take 500 mg of ibuprofen twice a day. ", "More text. "])
    text = "".join(released)
    assert "Asthma is common." in text
    assert "500 mg" not in text and "More text" not in text
    assert guard.blocked
    assert guard.block_reason == OutputIssue.DOSAGE


def test_after_a_block_further_input_is_ignored():
    guard = StreamGuard()
    run(guard, ["You probably have diabetes. "])
    assert guard.blocked
    assert guard.feed("Harmless text. ") == []
    assert guard.finish() == []


def test_unsafe_text_is_caught_even_when_it_arrives_one_character_at_a_time():
    guard = StreamGuard()
    released = "".join(run(guard, by_char("Fine sentence. Stop taking your medication right away. Tail.")))
    assert "Stop taking" not in released
    assert guard.blocked


def test_cross_sentence_dosage_is_blocked_at_the_second_sentence():
    guard = StreamGuard()
    released = "".join(run(guard, ["Take this medicine. ", "500 mg twice a day. ", "Done. "]))
    assert "500 mg" not in released
    assert guard.blocked


def test_the_last_unfinished_sentence_is_checked_at_the_end():
    guard = StreamGuard()
    released = run(guard, ["Fine. ", "You probably have diabetes"])
    assert "diabetes" not in "".join(released)
    assert guard.blocked


def test_the_last_safe_sentence_without_punctuation_is_released_at_the_end():
    guard = StreamGuard()
    assert "".join(run(guard, ["Asthma is common. ", "See a provider"])) == "Asthma is common. See a provider"


def test_very_long_text_without_punctuation_is_released_in_bounded_pieces():
    guard = StreamGuard(max_buffer=100)
    text = "word " * 150
    released = run(guard, [text])
    assert len(released) > 1
    assert all(len(piece) <= 101 for piece in released)
    assert "".join(released).split() == text.split()


# ---------- fixed texts used when a stream is stopped ----------

def test_block_notice_and_disclaimer_point_to_professional_help():
    from app.safety.messages import BLOCK_NOTICE, DISCLAIMER

    assert "healthcare professional" in BLOCK_NOTICE
    assert "not medical advice" in DISCLAIMER and "emergency" in DISCLAIMER


# ---------- suggestions marker ----------

SUGGESTIONS = '{"questions": ["What triggers asthma?"]}'


def test_text_after_the_marker_is_collected_and_never_released():
    guard = StreamGuard()
    released = "".join(run(guard, ["Asthma is common. ", SUGGESTIONS_MARKER, SUGGESTIONS]))
    assert released.strip() == "Asthma is common."
    assert SUGGESTIONS_MARKER not in released and "triggers" not in released
    assert guard.suggestions_raw == SUGGESTIONS
    assert not guard.blocked


def test_the_marker_is_found_even_when_split_across_chunks():
    guard = StreamGuard()
    text = f"Asthma is common. {SUGGESTIONS_MARKER}{SUGGESTIONS}"
    released = "".join(run(guard, by_char(text)))
    assert released.strip() == "Asthma is common."
    assert guard.suggestions_raw == SUGGESTIONS


def test_an_unfinished_sentence_before_the_marker_is_checked_and_released():
    guard = StreamGuard()
    released = "".join(run(guard, [f"See a provider{SUGGESTIONS_MARKER}{SUGGESTIONS}"]))
    assert released == "See a provider"


def test_an_unsafe_sentence_before_the_marker_is_still_blocked():
    guard = StreamGuard()
    released = "".join(run(guard, [f"You probably have diabetes.{SUGGESTIONS_MARKER}{SUGGESTIONS}"]))
    assert released == ""
    assert guard.blocked


def test_a_dangling_partial_marker_at_the_end_is_dropped():
    guard = StreamGuard()
    released = "".join(run(guard, ["Asthma is common. ", SUGGESTIONS_MARKER[:6]]))
    assert released.strip() == "Asthma is common."


def test_no_marker_means_no_suggestions():
    guard = StreamGuard()
    run(guard, ["Asthma is common."])
    assert guard.suggestions_raw == ""
