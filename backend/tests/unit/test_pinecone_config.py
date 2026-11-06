"""The Pinecone settings are shared by ingestion (writes) and the API (reads), so they live in one place."""
from types import SimpleNamespace

from app.retrieval import pinecone_config as cfg
from app.retrieval.dense import EMBEDDING_MODEL, PineconeVectorIndex


def test_shared_settings_match_the_index_that_was_created():
    assert cfg.INDEX_NAME == "vitalnest"
    assert cfg.EMBEDDING_MODEL == "multilingual-e5-large" == EMBEDDING_MODEL
    assert cfg.EMBEDDING_DIMENSION == 1024
    assert cfg.METRIC == "cosine"
    assert cfg.NAMESPACE == ""


def test_queries_name_the_namespace_explicitly():
    captured = {}

    class FakeIndex:
        def query(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(matches=[])

    PineconeVectorIndex(FakeIndex()).query([0.1], top_k=2)
    assert captured["namespace"] == cfg.NAMESPACE
    PineconeVectorIndex(FakeIndex(), namespace="other").query([0.1], top_k=2)
    assert captured["namespace"] == "other"
