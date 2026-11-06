"""Suggested follow-up questions: parse the model's JSON, then keep only safe, useful ones.

The model writes the questions after SUGGESTIONS_MARKER (see output_format.py). Nothing here
raises: if the model's output is unusable the answer simply has no suggestions.
"""
import json

from app.safety.input_check import check_input, normalise
from app.safety.output_guard import check_sentence

MAX_SUGGESTIONS = 3
MIN_CHARS = 8
MAX_CHARS = 150


def _json_candidates(raw: str):
    text = raw.strip()
    yield text
    for opener, closer in (("{", "}"), ("[", "]")):
        start, end = text.find(opener), text.rfind(closer)
        if start != -1 and end > start:
            yield text[start:end + 1]


def _parse_all(raw: str) -> list[str]:
    if not isinstance(raw, str):
        return []
    items = None
    for candidate in _json_candidates(raw):
        try:
            data = json.loads(candidate)
        except ValueError:
            continue
        items = data.get("questions") if isinstance(data, dict) else data
        if isinstance(items, list):
            break
        items = None
    if items is None:
        return []

    questions: list[str] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, str):
            continue
        question = item.strip()
        if not (MIN_CHARS <= len(question) <= MAX_CHARS) or "\n" in question or not question.endswith("?"):
            continue
        key = question.casefold()
        if key in seen:
            continue
        seen.add(key)
        questions.append(question)
    return questions


def parse_suggestions(raw: str) -> list[str]:
    return _parse_all(raw)[:MAX_SUGGESTIONS]


def _same_question(a: str, b: str) -> bool:
    return normalise(a).rstrip("? ") == normalise(b).rstrip("? ")


def suggestions_from_raw(raw: str, current_question: str) -> list[str]:
    """Parsed suggestions that pass both safety checks and are not just the question asked."""
    safe = [
        question
        for question in _parse_all(raw)
        if not _same_question(question, current_question)
        and check_input(question).allowed
        and check_sentence(question).allowed
    ]
    return safe[:MAX_SUGGESTIONS]
