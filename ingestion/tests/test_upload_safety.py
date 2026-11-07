"""Upload safety tests (from the upload review): dimensions, retries, resumable errors, namespace,
index checks, input validation, dry run. Everything is offline: Pinecone is replaced by fakes."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.retrieval import pinecone_config as cfg
from vitalnest_ingest import cli, vectors
from vitalnest_ingest.models import Chunk
from vitalnest_ingest.validation import ChunkValidationError, validate_chunks

REAL_CHUNKS = Path(__file__).resolve().parents[1] / "data" / "build" / "chunks.jsonl"


def make_chunk(n: int, **overrides) -> Chunk:
    values = dict(
        chunk_id=f"medlineplus-{n}-000", doc_id=f"medlineplus-{n}", source_name="MedlinePlus",
        title=f"Topic {n}", url=f"https://medlineplus.gov/topic{n}.html", text=f"Body text {n}.",
        retrieved_at="2026-10-31", licence="Public domain",
        attribution="Courtesy of MedlinePlus from the National Library of Medicine",
    )
    values.update(overrides)
    return Chunk(**values)


def chunks_of(count: int) -> list[Chunk]:
    return [make_chunk(i) for i in range(count)]


class FakeEmbedder:
    def __init__(self, dimension: int = cfg.EMBEDDING_DIMENSION, fail_times: int = 0, fail_always_from_call: int | None = None):
        self.dimension, self.fail_times, self.fail_from = dimension, fail_times, fail_always_from_call
        self.calls = 0

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        if self.fail_from is not None and self.calls >= self.fail_from:
            raise RuntimeError("secret-token-123 rate limited")
        if self.calls <= self.fail_times:
            raise RuntimeError("temporary failure")
        return [[0.5] * self.dimension for _ in texts]


class FakeStore:
    def __init__(self, fail_times: int = 0):
        self.records: list[dict] = []
        self.calls = 0
        self.fail_times = fail_times

    def upsert(self, records: list[dict]) -> None:
        self.calls += 1
        if self.calls <= self.fail_times:
            raise RuntimeError("temporary store failure")
        self.records.extend(records)


# ---------- dimensions ----------

def test_a_vector_of_the_wrong_size_is_rejected_before_anything_is_stored():
    store = FakeStore()
    with pytest.raises(ValueError, match="dimension"):
        vectors.upsert_chunks(chunks_of(3), FakeEmbedder(dimension=512), store, sleep=lambda s: None)
    assert store.calls == 0


def test_a_wrong_size_is_not_retried():
    embedder = FakeEmbedder(dimension=512)
    with pytest.raises(ValueError):
        vectors.upsert_chunks(chunks_of(3), embedder, FakeStore(), sleep=lambda s: None)
    assert embedder.calls == 1


def test_vectors_have_exactly_the_configured_dimension():
    store = FakeStore()
    vectors.upsert_chunks(chunks_of(3), FakeEmbedder(), store, sleep=lambda s: None)
    assert all(len(r["values"]) == cfg.EMBEDDING_DIMENSION == 1024 for r in store.records)


# ---------- retries and resumable errors ----------

def test_temporary_embedding_failures_are_retried_with_growing_pauses():
    embedder, store, pauses = FakeEmbedder(fail_times=2), FakeStore(), []
    count = vectors.upsert_chunks(chunks_of(3), embedder, store, sleep=pauses.append)
    assert count == 3
    assert pauses == [1, 2]
    assert len(store.records) == 3  # stored once, not once per attempt


def test_temporary_store_failures_are_retried_without_duplicating_records():
    store = FakeStore(fail_times=1)
    vectors.upsert_chunks(chunks_of(3), FakeEmbedder(), store, sleep=lambda s: None)
    assert [r["id"] for r in store.records] == [c.chunk_id for c in chunks_of(3)]


def test_a_permanent_failure_reports_progress_and_that_rerunning_is_safe():
    embedder = FakeEmbedder(fail_always_from_call=2)  # first batch succeeds, second always fails
    store = FakeStore()
    with pytest.raises(vectors.UploadError) as exc:
        vectors.upsert_chunks(chunks_of(5), embedder, store, batch_size=2, sleep=lambda s: None)
    assert exc.value.uploaded == 2
    assert len(store.records) == 2
    assert "2 of 5" in str(exc.value) and "re-run" in str(exc.value).lower()


def test_error_messages_do_not_leak_provider_details():
    with pytest.raises(vectors.UploadError) as exc:
        vectors.upsert_chunks(chunks_of(2), FakeEmbedder(fail_always_from_call=1), FakeStore(), sleep=lambda s: None)
    assert "secret-token-123" not in str(exc.value)


def test_the_number_of_attempts_is_bounded():
    embedder = FakeEmbedder(fail_always_from_call=1)
    with pytest.raises(vectors.UploadError):
        vectors.upsert_chunks(chunks_of(2), embedder, FakeStore(), max_attempts=3, sleep=lambda s: None)
    assert embedder.calls == 3


def test_progress_is_reported_after_each_batch():
    seen = []
    vectors.upsert_chunks(chunks_of(5), FakeEmbedder(), FakeStore(), batch_size=2,
                          sleep=lambda s: None, progress=lambda done, total: seen.append((done, total)))
    assert seen == [(2, 5), (4, 5), (5, 5)]


# ---------- batch size ----------

def test_the_default_batch_size_is_48():
    assert vectors.DEFAULT_BATCH_SIZE == 48


def test_by_default_chunks_are_embedded_and_stored_48_at_a_time():
    sizes = []

    class RecordingEmbedder(FakeEmbedder):
        def embed_passages(self, texts):
            sizes.append(len(texts))
            return super().embed_passages(texts)

    store = FakeStore()
    vectors.upsert_chunks(chunks_of(100), RecordingEmbedder(), store, sleep=lambda s: None)
    assert sizes == [48, 48, 4]
    assert store.calls == 3 and len(store.records) == 100


def test_the_command_line_default_is_also_48(tmp_path, monkeypatch):
    sizes = []

    class RecordingEmbedder(FakeEmbedder):
        def embed_passages(self, texts):
            sizes.append(len(texts))
            return super().embed_passages(texts)

    monkeypatch.setenv("PINECONE_API_KEY", "test-key")
    monkeypatch.setattr(vectors, "open_pinecone", lambda key, name: (RecordingEmbedder(), FakeStore()))
    path = write_chunks(tmp_path / "chunks.jsonl", chunks_of(100))
    assert cli.main(["upload", "--chunks", str(path)]) == 0
    assert sizes == [48, 48, 4]


@pytest.mark.skipif(not REAL_CHUNKS.exists(), reason="run the ingestion build first")
def test_a_default_batch_stays_under_the_request_size_limit():
    """Worst case: the longest real chunks, with full-precision (17-decimal) numbers like a JSON
    encoder can emit. Pinecone caps an upsert request at 2 MB."""
    import random

    rows = [json.loads(line) for line in REAL_CHUNKS.read_text(encoding="utf-8").splitlines()]
    longest = sorted(rows, key=lambda r: len(r["text"]), reverse=True)[: vectors.DEFAULT_BATCH_SIZE]
    rng = random.Random(1)
    records = [
        {
            "id": r["chunk_id"],
            "values": [round(rng.uniform(-0.1, 0.1), 17) for _ in range(cfg.EMBEDDING_DIMENSION)],
            "metadata": {k: v for k, v in r.items() if k != "chunk_id"},
        }
        for r in longest
    ]
    size = len(json.dumps({"vectors": records, "namespace": cfg.NAMESPACE}).encode("utf-8"))
    assert size < 1_500_000, f"a default batch could be {size} bytes; Pinecone's limit is 2,000,000"


# ---------- namespace ----------

def test_the_namespace_is_explicit_and_shared_with_the_api():
    from app.retrieval.dense import PineconeVectorIndex

    assert cfg.NAMESPACE == ""
    written, queried = {}, {}

    class FakeIndex:
        def upsert(self, **kwargs):
            written.update(kwargs)

        def query(self, **kwargs):
            queried.update(kwargs)
            return SimpleNamespace(matches=[])

    vectors.PineconeStore(FakeIndex()).upsert([{"id": "a", "values": [0.0], "metadata": {}}])
    PineconeVectorIndex(FakeIndex()).query([0.0], top_k=1)
    assert written["namespace"] == queried["namespace"] == cfg.NAMESPACE


# ---------- opening the index: never create, always verify ----------

class FakeClient:
    def __init__(self, exists=True, dimension=1024, metric="cosine", ready=True):
        self.exists, self.created, self.indexes_opened = exists, False, []
        self._info = SimpleNamespace(dimension=dimension, metric=metric, status=SimpleNamespace(ready=ready))
        self.inference = object()

    def has_index(self, name):
        return self.exists

    def describe_index(self, name):
        return self._info

    def create_index(self, **kwargs):
        self.created = True

    def Index(self, name):
        self.indexes_opened.append(name)
        return object()


def test_a_missing_index_is_an_error_and_is_never_created():
    client = FakeClient(exists=False)
    with pytest.raises(vectors.UploadTargetError, match="does not exist"):
        vectors.open_pinecone("key", "vitalnest", client=client)
    assert not client.created


@pytest.mark.parametrize(
    "kwargs, expected",
    [({"dimension": 512}, "dimension"), ({"metric": "euclidean"}, "metric"), ({"ready": False}, "ready")],
)
def test_an_index_with_the_wrong_configuration_is_refused(kwargs, expected):
    client = FakeClient(**kwargs)
    with pytest.raises(vectors.UploadTargetError, match=expected):
        vectors.open_pinecone("key", "vitalnest", client=client)
    assert client.indexes_opened == []


def test_a_correct_index_is_opened():
    client = FakeClient()
    embedder, store = vectors.open_pinecone("key", "vitalnest", client=client)
    assert client.indexes_opened == ["vitalnest"] and not client.created
    assert embedder is not None and store is not None


# ---------- input validation ----------

def test_clean_medlineplus_chunks_pass():
    validate_chunks(chunks_of(5))


def test_duplicate_chunk_ids_are_rejected():
    with pytest.raises(ChunkValidationError, match="duplicate"):
        validate_chunks([make_chunk(1), make_chunk(1)])


def test_other_sources_are_rejected():
    with pytest.raises(ChunkValidationError, match="source"):
        validate_chunks([make_chunk(1, source_name="SomeOtherSite")])


@pytest.mark.parametrize(
    "url",
    ["http://medlineplus.gov/a.html", "https://evil.example/a.html", "https://medlineplus.gov.evil.example/a.html", ""],
)
def test_urls_outside_https_medlineplus_are_rejected(url):
    with pytest.raises(ChunkValidationError, match="url"):
        validate_chunks([make_chunk(1, url=url)])


@pytest.mark.parametrize("field", ["text", "title", "attribution", "licence"])
def test_missing_required_content_is_rejected(field):
    with pytest.raises(ChunkValidationError, match=field):
        validate_chunks([make_chunk(1, **{field: "  "})])


def test_oversized_metadata_is_rejected():
    with pytest.raises(ChunkValidationError, match="too large"):
        validate_chunks([make_chunk(1, text="x" * 50_000)])


def test_an_empty_list_is_rejected():
    with pytest.raises(ChunkValidationError, match="no chunks"):
        validate_chunks([])


def test_the_error_lists_a_bounded_number_of_problems():
    bad = [make_chunk(i, source_name="Other") for i in range(30)]
    with pytest.raises(ChunkValidationError) as exc:
        validate_chunks(bad)
    assert str(exc.value).count("approved source") <= 5
    assert "and 25 more" in str(exc.value)


@pytest.mark.skipif(not REAL_CHUNKS.exists(), reason="run the ingestion build first")
def test_the_real_built_chunk_file_is_valid_and_complete():
    rows = [json.loads(line) for line in REAL_CHUNKS.read_text(encoding="utf-8").splitlines()]
    chunks = [Chunk(**row) for row in rows]
    validate_chunks(chunks)
    by_source = {name: sum(1 for c in chunks if c.source_name == name) for name in {c.source_name for c in chunks}}
    assert by_source["MedlinePlus"] == 2827
    assert set(by_source) <= {"MedlinePlus", "WHO", "CDC"}


# ---------- CLI ----------

def write_chunks(path: Path, chunks: list[Chunk]) -> Path:
    path.write_text("\n".join(json.dumps(c.to_dict()) for c in chunks) + "\n", encoding="utf-8")
    return path


def no_network(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("must not contact Pinecone")

    monkeypatch.setattr(vectors, "open_pinecone", boom)


def test_dry_run_validates_and_reports_without_a_key_or_network(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("PINECONE_API_KEY", raising=False)
    no_network(monkeypatch)
    path = write_chunks(tmp_path / "chunks.jsonl", chunks_of(4))
    assert cli.main(["upload", "--chunks", str(path), "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "4 chunks" in out and "MedlinePlus" in out and "No data was sent" in out


def test_invalid_chunks_stop_the_upload_before_any_network_call(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("PINECONE_API_KEY", "test-key")
    no_network(monkeypatch)
    path = write_chunks(tmp_path / "chunks.jsonl", [make_chunk(1, source_name="Other")])
    assert cli.main(["upload", "--chunks", str(path)]) == 1
    assert "source" in capsys.readouterr().err


def test_malformed_chunk_files_give_a_clear_error(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("PINECONE_API_KEY", "test-key")
    no_network(monkeypatch)
    path = tmp_path / "chunks.jsonl"
    path.write_text('{"not": "a chunk"}\n', encoding="utf-8")
    assert cli.main(["upload", "--chunks", str(path)]) == 1
    assert "Traceback" not in capsys.readouterr().err


def test_missing_chunk_file_gives_a_clear_error(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("PINECONE_API_KEY", "test-key")
    no_network(monkeypatch)
    assert cli.main(["upload", "--chunks", str(tmp_path / "nope.jsonl")]) == 1
    assert "not found" in capsys.readouterr().err.lower()


def test_successful_upload_reports_the_count(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("PINECONE_API_KEY", "test-key")
    store = FakeStore()
    monkeypatch.setattr(vectors, "open_pinecone", lambda key, name: (FakeEmbedder(), store))
    path = write_chunks(tmp_path / "chunks.jsonl", chunks_of(3))
    assert cli.main(["upload", "--chunks", str(path)]) == 0
    assert "Upserted 3 chunks" in capsys.readouterr().out
    assert len(store.records) == 3


def test_a_failed_upload_prints_how_far_it_got_and_returns_1(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("PINECONE_API_KEY", "test-key")
    monkeypatch.setattr(vectors, "open_pinecone", lambda key, name: (FakeEmbedder(fail_always_from_call=1), FakeStore()))
    monkeypatch.setattr(vectors.time, "sleep", lambda s: None)
    path = write_chunks(tmp_path / "chunks.jsonl", chunks_of(3))
    assert cli.main(["upload", "--chunks", str(path)]) == 1
    err = capsys.readouterr().err
    assert "0 of 3" in err and "Traceback" not in err and "secret-token-123" not in err


def test_an_unsuitable_index_is_reported_as_an_error(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("PINECONE_API_KEY", "test-key")

    def refuse(key, name):
        raise vectors.UploadTargetError("Index 'vitalnest' does not exist")

    monkeypatch.setattr(vectors, "open_pinecone", refuse)
    path = write_chunks(tmp_path / "chunks.jsonl", chunks_of(1))
    assert cli.main(["upload", "--chunks", str(path)]) == 1
    assert "does not exist" in capsys.readouterr().err
