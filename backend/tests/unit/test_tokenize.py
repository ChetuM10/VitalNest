"""The tokenizer is shared by the ingestion script (index build) and the API (query time).
If the two ever differ, BM25 silently stops matching, so its behaviour is pinned here."""
from app.retrieval.tokenize import tokenize


def test_lowercases_and_splits_on_non_word_characters():
    assert tokenize("Type-2 Diabetes, explained!") == ["type", "2", "diabetes", "explained"]


def test_keeps_numbers_and_unicode_letters():
    assert tokenize("Vitamin B12 and café") == ["vitamin", "b12", "and", "café"]


def test_empty_and_symbol_only_text_gives_no_tokens():
    assert tokenize("") == []
    assert tokenize("  ?!  ") == []
