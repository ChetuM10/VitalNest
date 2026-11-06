"""T4 tests: dense retrieval wrapper. Pinecone and the embedding model are replaced by fakes."""
from types import SimpleNamespace

import pytest

from app.retrieval.dense import DenseRetriever, PineconeQueryEmbedder, PineconeVectorIndex
from app.retrieval.types import RetrievalError


def metadata(title: str = "Asthma") -> dict:
    return {
        "doc_id": "medlineplus-1", "source_name": "MedlinePlus", "title": title,
        "url": "https://medlineplus.gov/asthma.html", "text": f"{title} chunk text.",
        "retrieved_at": "2026-10-31", "licence": "Public domain",
        "attribution": "Courtesy of MedlinePlus from the National Library of Medicine",
    }


class FakeEmbedder:
    def __init__(self, error: Exception | None = None):
        self.queries: list[str] = []
        self.error = error

    def embed_query(self, text: str) -> list[float]:
        if self.error:
            raise self.error
        self.queries.append(text)
        return [0.25, 0.75]


class FakeIndex:
    def __init__(self, matches=None, error: Exception | None = None):
        self.matches = matches if matches is not None else []
        self.error = error
        self.calls: list[tuple] = []

    def query(self, vector: list[float], top_k: int) -> list[dict]:
        if self.error:
            raise self.error
        self.calls.append((vector, top_k))
        return self.matches


def test_results_are_returned_in_order_with_scores_and_citation_fields():
    index = FakeIndex([
        {"id": "asthma-000", "score": 0.91, "metadata": metadata("Asthma")},
        {"id": "copd-002", "score": 0.80, "metadata": metadata("COPD")},
    ])
    hits = DenseRetriever(FakeEmbedder(), index).search("what is asthma")
    assert [h.chunk_id for h in hits] == ["asthma-000", "copd-002"]
    assert [h.score for h in hits] == [0.91, 0.80]
    first = hits[0]
    assert (first.title, first.source_name, first.doc_id) == ("Asthma", "MedlinePlus", "medlineplus-1")
    assert first.text == "Asthma chunk text."
    assert first.url == "https://medlineplus.gov/asthma.html"
    assert "National Library of Medicine" in first.attribution


def test_the_query_is_embedded_and_the_vector_and_top_k_are_passed_on():
    embedder, index = FakeEmbedder(), FakeIndex()
    DenseRetriever(embedder, index).search("  what is asthma  ", top_k=7)
    assert embedder.queries == ["what is asthma"]
    assert index.calls == [([0.25, 0.75], 7)]


def test_default_top_k_is_20():
    index = FakeIndex()
    DenseRetriever(FakeEmbedder(), index).search("asthma")
    assert index.calls[0][1] == 20


@pytest.mark.parametrize("query", ["", "   ", "\n"])
def test_blank_queries_make_no_calls(query):
    embedder, index = FakeEmbedder(), FakeIndex()
    assert DenseRetriever(embedder, index).search(query) == []
    assert embedder.queries == [] and index.calls == []


@pytest.mark.parametrize("top_k", [0, -1])
def test_top_k_must_be_positive(top_k):
    with pytest.raises(ValueError):
        DenseRetriever(FakeEmbedder(), FakeIndex()).search("asthma", top_k=top_k)


def test_matches_with_incomplete_metadata_are_skipped_not_fatal():
    broken = {"id": "bad-000", "score": 0.99, "metadata": {"title": "No text or url"}}
    good = {"id": "ok-000", "score": 0.5, "metadata": metadata()}
    hits = DenseRetriever(FakeEmbedder(), FakeIndex([broken, good])).search("asthma")
    assert [h.chunk_id for h in hits] == ["ok-000"]


def test_matches_without_metadata_are_skipped():
    hits = DenseRetriever(FakeEmbedder(), FakeIndex([{"id": "x", "score": 1.0, "metadata": None}])).search("a")
    assert hits == []


def test_embedding_failure_becomes_a_retrieval_error():
    with pytest.raises(RetrievalError):
        DenseRetriever(FakeEmbedder(error=RuntimeError("boom")), FakeIndex()).search("asthma")


def test_index_failure_becomes_a_retrieval_error_without_leaking_details():
    with pytest.raises(RetrievalError) as exc:
        DenseRetriever(FakeEmbedder(), FakeIndex(error=RuntimeError("secret-key-123 rejected"))).search("asthma")
    assert "secret-key-123" not in str(exc.value)


# ---------- thin Pinecone adapters ----------

def test_query_embedding_uses_the_query_input_type_not_passage():
    captured = {}

    class FakeInference:
        def embed(self, model, inputs, parameters):
            captured.update(model=model, inputs=inputs, parameters=parameters)
            return SimpleNamespace(data=[SimpleNamespace(values=[0.1, 0.2, 0.3])])

    embedder = PineconeQueryEmbedder(SimpleNamespace(inference=FakeInference()))
    assert embedder.embed_query("what is asthma") == [0.1, 0.2, 0.3]
    assert captured["parameters"]["input_type"] == "query"
    assert captured["inputs"] == ["what is asthma"]
    assert captured["model"] == "multilingual-e5-large"


def test_pinecone_index_adapter_requests_metadata_and_returns_plain_dicts():
    captured = {}

    class FakePineconeIndex:
        def query(self, **kwargs):
            captured.update(kwargs)
            match = SimpleNamespace(id="asthma-000", score=0.9, metadata=metadata())
            return SimpleNamespace(matches=[match])

    rows = PineconeVectorIndex(FakePineconeIndex()).query([0.5, 0.5], top_k=3)
    assert captured["vector"] == [0.5, 0.5] and captured["top_k"] == 3
    assert captured["include_metadata"] is True
    assert rows == [{"id": "asthma-000", "score": 0.9, "metadata": metadata()}]
