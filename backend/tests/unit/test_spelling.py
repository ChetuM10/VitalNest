"""Spelling correction against the vocabulary of the health pages."""
import pytest

from app.retrieval.spelling import SpellingCorrector, edit_distance

TEXTS = [
    "Alzheimer's Disease Alzheimer's disease is the most common cause of dementia. Symptoms include memory loss.",
    "Diabetes Diabetes is a disease in which your blood sugar levels are too high. Diabetes affects many people. Symptoms of diabetes vary.",
    "Asthma Asthma is a lung disease. Asthma symptoms include wheezing and coughing. Treat asthma early.",
    "Cholesterol Cholesterol is a waxy substance in your blood. High cholesterol raises risk. Symptoms are rare.",
    "Hypertension and Osteoporosis. Osteoporosis makes bones weak. Hypertension is high blood pressure.",
    "Migraine A migraine is a headache with throbbing pain. Symptoms of migraine vary.",
    "Hemophilia is a rare bleeding disorder. Symptoms include easy bruising. Do not hurt myself or others.",
    "Ask what you should do if symptoms get worse.",
]


@pytest.fixture
def corrector() -> SpellingCorrector:
    return SpellingCorrector(TEXTS)


# ---------- the examples from the brief ----------

@pytest.mark.parametrize(
    "typo, expected",
    [("diabtes", "diabetes"), ("diabts", "diabetes"), ("ashtma", "asthma"), ("alzeihmers", "alzheimer's"), ("symtoms", "symptoms")],
)
def test_the_examples_from_the_brief_are_corrected(corrector, typo, expected):
    fixed, changes = corrector.correct(typo)
    assert fixed == expected
    assert changes == [(typo, expected)]


@pytest.mark.parametrize(
    "typo, expected",
    [("diabetis", "diabetes"), ("diabeties", "diabetes"), ("asthama", "asthma"), ("asthmaa", "asthma"), ("colestrol", "cholesterol"),
     ("hypertention", "hypertension"), ("migrane", "migraine"), ("osteoperosis", "osteoporosis"), ("osteoprosis", "osteoporosis"),
     ("sympotms", "symptoms"), ("symptons", "symptoms"), ("haemophilia", "hemophilia"), ("alzhiemers", "alzheimer's")],
)
def test_similar_misspellings_are_corrected(corrector, typo, expected):
    assert corrector.correct(f"what is {typo}")[0] == f"what is {expected}"


def test_a_capital_letter_is_kept_when_the_person_typed_one(corrector):
    assert corrector.correct("Alzeihmers")[0] == "Alzheimer's"
    assert corrector.correct("Diabtes, explained.")[0] == "Diabetes, explained."


def test_surrounding_words_punctuation_and_spacing_are_untouched(corrector):
    assert corrector.correct("Tell me about  diabtes (type 2)!") == ("Tell me about  diabetes (type 2)!", [("diabtes", "diabetes")])
    assert corrector.correct("(migrane)")[0] == "(migraine)"


# ---------- edit distance ----------

def test_a_swap_of_neighbouring_letters_counts_as_one_edit():
    assert edit_distance("ashtma", "asthma", 2) == 1
    assert edit_distance("diabtes", "diabetes", 2) == 1  # one missing letter
    assert edit_distance("diabets", "diabetes", 2) == 1
    assert edit_distance("cancer", "cancef", 2) == 1  # one wrong letter
    assert edit_distance("symtoms", "symptoms", 2) == 1


def test_distance_stops_early_when_over_the_limit():
    assert edit_distance("abcdef", "uvwxyz", 1) == 2
    assert edit_distance("short", "muchlongerword", 2) == 3


# ---------- never change a correctly spelled word ----------

def test_words_that_are_already_known_are_left_alone(corrector):
    text = "What are the symptoms of asthma and diabetes?"
    assert corrector.correct(text) == (text, [])


def test_known_words_stay_even_if_they_are_rare_or_one_edit_from_a_common_word():
    corrector = SpellingCorrector(["Asthma asthma asthma asthma asthma. Astham is a rare surname."], min_frequency=3)
    assert corrector.correct("astham")[1] == []  # in the vocabulary, so never "corrected", even though it is rare


def test_plain_inflections_of_known_words_are_not_treated_as_typos(corrector):
    assert corrector.correct("What causes diabetes problems and bones?")[1] == []


def test_short_words_are_never_changed(corrector):
    assert corrector.correct("asma flu hiv")[1] == []


def test_words_with_no_close_match_are_left_alone(corrector):
    text = "How do I bake sourdough bread?"
    assert corrector.correct(text) == (text, [])


def test_non_word_tokens_are_left_alone(corrector):
    text = "123456 !!!!!! ~~~~~~ a1b2c3d4"
    assert corrector.correct(text) == (text, [])


# ---------- uncertain meaning: do not guess ----------

def test_two_equally_likely_corrections_mean_nothing_is_changed():
    corrector = SpellingCorrector(["cancer cancer cancer. cancel cancel cancel."])
    assert corrector.correct("cancef") == ("cancef", [])


def test_a_clearly_more_common_candidate_wins():
    corrector = SpellingCorrector(["cancer " * 9 + "cancel"])
    assert corrector.correct("cancef")[0] == "cancer"


def test_topic_titles_break_ties_in_favour_of_medical_terms():
    texts = ["diabetes and diabetic care. diabetic foot."]
    assert SpellingCorrector(texts).correct("diabetis")[1] == []  # diabetes vs diabetic: uncertain
    assert SpellingCorrector(texts, priority_texts=["Diabetes"]).correct("diabetis")[0] == "diabetes"


def test_words_too_far_from_any_known_word_are_left_alone(corrector):
    assert corrector.correct("dibetxxs") == ("dibetxxs", [])


# ---------- vocabulary ----------

def test_rare_words_are_known_but_not_offered_as_corrections():
    corrector = SpellingCorrector(["Asthma asthma asthma. Astham."], min_frequency=2)
    assert corrector.correct("asthmo")[0] == "asthma"
    assert corrector.correct("asthaa")[0] == "asthma"  # not "astham": that word is too rare to suggest


def test_the_most_common_form_is_used_for_display():
    corrector = SpellingCorrector(["Alzheimer's disease. Alzheimer's care. Alzheimers support."])
    assert corrector.correct("Alzeihmers")[0] == "Alzheimer's"


def test_vocabulary_comes_only_from_the_given_texts():
    small = SpellingCorrector(["Asthma is a lung disease."])
    assert small.correct("diabetis")[1] == []
    assert small.correct("asthmaa")[0] == "asthma"


def test_empty_input_is_fine(corrector):
    assert corrector.correct("") == ("", [])
    assert corrector.correct("   ") == ("   ", [])


def test_the_same_input_always_gives_the_same_output(corrector):
    text = "tell me about diabtes and colestrol and ashtma"
    assert corrector.correct(text) == corrector.correct(text)


def test_a_misspelled_safety_word_is_corrected_so_the_safety_check_can_see_it(corrector):
    assert corrector.correct("I want to hurt myslef")[0] == "I want to hurt myself"
