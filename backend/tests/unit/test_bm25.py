"""T5 tests: BM25 index loading, search, and loading at app startup."""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.retrieval.bm25 import Bm25Index, IndexLoadError
from app.retrieval.tokenize import tokenize

CHUNKS = [
    ("asthma-000", "Asthma", "Wheezing, cough and shortness of breath are asthma symptoms. An inhaler helps."),
    ("diabetes-000", "Diabetes", "Insulin controls blood sugar. High blood sugar is a sign of diabetes."),
    ("stroke-000", "Stroke", "Face drooping, arm weakness and slurred speech are stroke warning signs."),
    ("bp-000", "High Blood Pressure", "High blood pressure is often treated with lifestyle changes and medicine."),
]


def chunk_record(chunk_id: str, title: str, text: str) -> dict:
    return {
        "chunk_id": chunk_id, "doc_id": chunk_id.rsplit("-", 1)[0], "source_name": "MedlinePlus",
        "title": title, "url": f"https://medlineplus.gov/{title.lower().replace(' ', '')}.html",
        "text": text, "retrieved_at": "2026-10-31", "licence": "Public domain",
        "attribution": "Courtesy of MedlinePlus from the National Library of Medicine",
    }


def write_index(path: Path, chunks=CHUNKS, version: int = 1, tokens=None) -> Path:
    records = [chunk_record(*c) for c in chunks]
    data = {
        "version": version,
        "chunks": records,
        "tokens": tokens if tokens is not None else [tokenize(f"{r['title']} {r['text']}") for r in records],
    }
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


@pytest.fixture
def index(tmp_path) -> Bm25Index:
    return Bm25Index.load(write_index(tmp_path / "bm25_index.json"))


# ---------- search ----------

def test_most_relevant_chunk_is_ranked_first(index):
    hits = index.search("high blood sugar insulin")
    assert hits[0].chunk_id == "diabetes-000"


@pytest.mark.parametrize(
    "query, expected",
    [
        ("asthma symptoms wheezing", "asthma-000"),
        ("slurred speech face drooping", "stroke-000"),
        ("how is high blood pressure treated", "bp-000"),
    ],
)
def test_each_topic_is_found_by_its_own_words(index, query, expected):
    assert index.search(query)[0].chunk_id == expected


def test_results_are_sorted_by_descending_score_with_positive_scores(index):
    hits = index.search("blood sugar")
    scores = [h.score for h in hits]
    assert scores == sorted(scores, reverse=True)
    assert all(s > 0 for s in scores)


def test_top_k_limits_the_number_of_results(index):
    # BM25 gives a word that appears in half the chunks no weight, so use words unique to one chunk.
    assert len(index.search("asthma insulin", top_k=1)) == 1
    assert len(index.search("asthma insulin", top_k=20)) == 2


def test_hits_carry_everything_needed_for_citations(index):
    hit = index.search("insulin")[0]
    assert (hit.title, hit.source_name) == ("Diabetes", "MedlinePlus")
    assert hit.url.startswith("https://medlineplus.gov/")
    assert "Insulin controls blood sugar" in hit.text
    assert "National Library of Medicine" in hit.attribution
    assert (hit.doc_id, hit.retrieved_at, hit.licence) == ("diabetes", "2026-10-31", "Public domain")


def test_query_with_no_matching_words_returns_nothing(index):
    assert index.search("quantum chromodynamics") == []


@pytest.mark.parametrize("query", ["", "   ", "?!...", "\n"])
def test_empty_or_symbol_only_queries_return_nothing(index, query):
    assert index.search(query) == []


def test_search_is_case_and_punctuation_insensitive(index):
    assert [h.chunk_id for h in index.search("INSULIN!!!")] == [h.chunk_id for h in index.search("insulin")]


def test_repeating_a_query_word_does_not_change_the_ranking(index):
    assert [h.chunk_id for h in index.search("insulin insulin insulin blood")] == [
        h.chunk_id for h in index.search("insulin blood")
    ]


def test_ties_are_broken_deterministically(tmp_path):
    twins = [("a-000", "Same", "identical wording here"), ("b-000", "Same", "identical wording here")]
    fillers = [(f"f{i}-000", f"Filler {i}", f"unrelated filler text number {i}") for i in range(6)]
    path = write_index(tmp_path / "i.json", chunks=twins + fillers)
    results = [Bm25Index.load(path).search("identical wording") for _ in range(3)]
    assert all([h.chunk_id for h in r] == ["a-000", "b-000"] for r in results)


@pytest.mark.parametrize("bad_top_k", [0, -1])
def test_top_k_must_be_positive(index, bad_top_k):
    with pytest.raises(ValueError):
        index.search("blood", top_k=bad_top_k)


def test_index_reports_its_size(index):
    assert len(index) == 4


# ---------- loading errors ----------

def test_missing_file_is_a_clear_error(tmp_path):
    with pytest.raises(IndexLoadError, match="not found"):
        Bm25Index.load(tmp_path / "nope.json")


def test_invalid_json_is_a_clear_error(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(IndexLoadError, match="valid JSON"):
        Bm25Index.load(path)


def test_unknown_version_is_rejected(tmp_path):
    with pytest.raises(IndexLoadError, match="version"):
        Bm25Index.load(write_index(tmp_path / "v.json", version=2))


def test_chunk_and_token_counts_must_match(tmp_path):
    with pytest.raises(IndexLoadError, match="match"):
        Bm25Index.load(write_index(tmp_path / "m.json", tokens=[["only", "one"]]))


def test_empty_corpus_is_rejected(tmp_path):
    with pytest.raises(IndexLoadError, match="empty"):
        Bm25Index.load(write_index(tmp_path / "e.json", chunks=[], tokens=[]))


def test_missing_chunk_fields_are_rejected(tmp_path):
    path = tmp_path / "f.json"
    path.write_text(json.dumps({"version": 1, "chunks": [{"chunk_id": "x"}], "tokens": [["x"]]}), encoding="utf-8")
    with pytest.raises(IndexLoadError, match="fields"):
        Bm25Index.load(path)


# ---------- loaded once at app startup ----------

def test_index_is_loaded_when_the_app_starts(tmp_path, monkeypatch):
    monkeypatch.setenv("BM25_INDEX_PATH", str(write_index(tmp_path / "bm25_index.json")))
    with TestClient(create_app()) as client:
        assert client.get("/v1/health").status_code == 200
        assert len(client.app.state.bm25) == 4


def test_app_still_starts_when_the_index_file_is_absent(tmp_path, monkeypatch):
    monkeypatch.setenv("BM25_INDEX_PATH", str(tmp_path / "missing.json"))
    with TestClient(create_app()) as client:
        assert client.get("/v1/health").status_code == 200
        assert client.app.state.bm25 is None


def test_app_refuses_to_start_with_a_corrupt_index(tmp_path, monkeypatch):
    bad = tmp_path / "bm25_index.json"
    bad.write_text("{broken", encoding="utf-8")
    monkeypatch.setenv("BM25_INDEX_PATH", str(bad))
    with pytest.raises(IndexLoadError):
        with TestClient(create_app()):
            pass


# ---------- real index (skipped when ingestion has not been run) ----------

REAL_INDEX = Path(__file__).resolve().parents[3] / "ingestion" / "data" / "build" / "bm25_index.json"


@pytest.mark.skipif(not REAL_INDEX.exists(), reason="run the ingestion build first")
@pytest.mark.parametrize(
    "query, expected_title",
    [
        ("face drooping slurred speech stroke", "Stroke"),
        ("what are the symptoms of asthma", "Asthma"),
        ("what is type 2 diabetes", "Diabetes"),
    ],
)
def test_real_index_finds_the_obvious_topic_in_the_top_five(query, expected_title):
    hits = Bm25Index.load(REAL_INDEX).search(query, top_k=5)
    assert any(expected_title in h.title for h in hits), [h.title for h in hits]
