"""T3 tests: ingestion pipeline (clean, chunk, parse MedlinePlus, BM25 index, vectors, CLI).

Everything runs offline: HTTP uses httpx.MockTransport, Pinecone is replaced by fakes.
"""
import json
from datetime import date

import httpx
import pytest
from rank_bm25 import BM25Okapi

from app.retrieval.tokenize import tokenize
from vitalnest_ingest import bm25_index, cli, fetching, medlineplus, vectors
from vitalnest_ingest.chunking import chunk_document
from vitalnest_ingest.cleaning import html_to_text
from vitalnest_ingest.models import Chunk, Document

# ---------- fixtures ----------

TOPICS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<health-topics total="5" date-generated="10/30/2026">
  <health-topic meta-desc="Asthma overview" title="Asthma" url="https://medlineplus.gov/asthma.html"
                id="101" language="English" date-created="01/01/2000">
    <also-called>Bronchial asthma</also-called>
    <also-called>Reactive airway disease</also-called>
    <full-summary>&lt;p&gt;Asthma is a chronic disease that affects your airways.&lt;/p&gt;&lt;ul&gt;&lt;li&gt;Coughing&lt;/li&gt;&lt;li&gt;Wheezing&lt;/li&gt;&lt;/ul&gt;</full-summary>
    <site title="Other Org Asthma Page" url="https://example.org/asthma">
      <organization>Some Other Organisation</organization>
      <standard-description>Third-party description that must not be ingested.</standard-description>
    </site>
  </health-topic>
  <health-topic meta-desc="Diabetes" title="Diabetes" url="https://medlineplus.gov/diabetes.html"
                id="102" language="English" date-created="01/01/2000">
    <full-summary><p>Diabetes is a disease in which your blood sugar levels are too high.</p></full-summary>
  </health-topic>
  <health-topic meta-desc="Asma" title="Asma" url="https://medlineplus.gov/spanish/asthma.html"
                id="201" language="Spanish" date-created="01/01/2000">
    <full-summary>&lt;p&gt;El asma es una enfermedad cronica.&lt;/p&gt;</full-summary>
  </health-topic>
  <health-topic meta-desc="Empty" title="Empty Topic" url="https://medlineplus.gov/empty.html"
                id="103" language="English" date-created="01/01/2000">
    <full-summary></full-summary>
  </health-topic>
</health-topics>
"""


def make_document(text: str, doc_id: str = "doc") -> Document:
    return Document(
        doc_id=doc_id,
        source_name="MedlinePlus",
        title="Test Topic",
        url="https://example.test/topic",
        text=text,
        retrieved_at="2026-10-31",
        licence="Public domain",
        attribution="Courtesy of MedlinePlus",
    )


def make_chunk(chunk_id: str, title: str, text: str) -> Chunk:
    return Chunk(
        chunk_id=chunk_id, doc_id=chunk_id.rsplit("-", 1)[0], source_name="MedlinePlus",
        title=title, url=f"https://example.test/{chunk_id}", text=text,
        retrieved_at="2026-10-31", licence="Public domain", attribution="Courtesy of MedlinePlus",
    )


# ---------- cleaning ----------

def test_html_tags_are_removed_and_inline_text_stays_on_one_line():
    assert html_to_text("<p>Hello <b>big</b> <a href='/x'>world</a></p>") == "Hello big world"


def test_blocks_become_separate_lines_and_list_items_get_dashes():
    text = html_to_text("<h2>Symptoms</h2><p>Common signs:</p><ul><li>Cough</li><li>Wheeze</li></ul>")
    assert text.splitlines() == ["Symptoms", "Common signs:", "- Cough", "- Wheeze"]


def test_script_style_and_navigation_are_dropped():
    html = "<nav>Menu</nav><script>alert(1)</script><style>p{}</style><p>Keep me</p><footer>Foot</footer>"
    assert html_to_text(html) == "Keep me"


def test_entities_are_decoded_and_whitespace_normalised():
    assert html_to_text("<p>Fish &amp;   chips&nbsp;are\n\n  fine</p>") == "Fish & chips are fine"


def test_empty_html_gives_empty_text():
    assert html_to_text("") == ""
    assert html_to_text("<p>   </p>") == ""


# ---------- chunking ----------

SENTENCES = [f"Sentence number {i:02d} is here." for i in range(60)]


def test_short_document_is_a_single_chunk_with_metadata():
    doc = make_document("Short text about asthma.")
    chunks = chunk_document(doc, max_chars=300, overlap_chars=60)
    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk.text == "Short text about asthma."
    assert chunk.chunk_id == "doc-000"
    assert (chunk.doc_id, chunk.source_name, chunk.title) == ("doc", "MedlinePlus", "Test Topic")
    assert (chunk.url, chunk.retrieved_at) == ("https://example.test/topic", "2026-10-31")
    assert (chunk.licence, chunk.attribution) == ("Public domain", "Courtesy of MedlinePlus")


def test_long_document_is_split_within_the_size_limit_in_order():
    chunks = chunk_document(make_document(" ".join(SENTENCES)), max_chars=300, overlap_chars=60)
    assert len(chunks) > 3
    assert all(0 < len(c.text) <= 300 for c in chunks)
    assert [c.chunk_id for c in chunks] == [f"doc-{i:03d}" for i in range(len(chunks))]
    # Every sentence appears, and first appearances are in the original order.
    first_seen = [min(i for i, c in enumerate(chunks) if s in c.text) for s in SENTENCES]
    assert first_seen == sorted(first_seen)


def test_consecutive_chunks_overlap_by_whole_sentences_within_the_overlap_budget():
    chunks = chunk_document(make_document(" ".join(SENTENCES)), max_chars=300, overlap_chars=60)
    for before, after in zip(chunks, chunks[1:]):
        shared = [s for s in SENTENCES if s in before.text and s in after.text]
        assert shared, "chunks should share at least one sentence"
        assert len(" ".join(shared)) <= 60


def test_zero_overlap_gives_disjoint_chunks():
    chunks = chunk_document(make_document(" ".join(SENTENCES)), max_chars=300, overlap_chars=0)
    seen = [s for s in SENTENCES for c in chunks if s in c.text]
    assert len(seen) == len(SENTENCES)


def test_a_single_overlong_sentence_is_hard_split():
    chunks = chunk_document(make_document("word " * 200), max_chars=300, overlap_chars=0)
    assert len(chunks) > 1
    assert all(len(c.text) <= 300 for c in chunks)


def test_a_single_unbroken_token_longer_than_the_limit_is_sliced():
    chunks = chunk_document(make_document("x" * 700), max_chars=300, overlap_chars=0)
    assert [len(c.text) for c in chunks] == [300, 300, 100]


def test_empty_document_gives_no_chunks():
    assert chunk_document(make_document("   \n  "), max_chars=300, overlap_chars=60) == []


def test_chunking_is_deterministic():
    doc = make_document(" ".join(SENTENCES))
    assert chunk_document(doc, 300, 60) == chunk_document(doc, 300, 60)


def test_embedding_text_includes_the_title():
    chunk = chunk_document(make_document("Body text."), 300, 60)[0]
    assert chunk.embedding_text == "Test Topic\nBody text."


def test_chunk_to_dict_contains_all_citation_fields():
    data = chunk_document(make_document("Body text."), 300, 60)[0].to_dict()
    assert {"chunk_id", "doc_id", "source_name", "title", "url", "text",
            "retrieved_at", "licence", "attribution"} <= set(data)


# ---------- MedlinePlus parser ----------

def parse(xml: str = TOPICS_XML) -> list[Document]:
    return medlineplus.parse_topics(xml, retrieved_at="2026-10-31")


def test_only_english_topics_with_content_are_kept():
    assert [d.title for d in parse()] == ["Asthma", "Diabetes"]


def test_document_metadata_and_attribution():
    asthma = parse()[0]
    assert asthma.doc_id == "medlineplus-101"
    assert asthma.source_name == "MedlinePlus"
    assert asthma.url == "https://medlineplus.gov/asthma.html"
    assert asthma.retrieved_at == "2026-10-31"
    assert "National Library of Medicine" in asthma.attribution
    assert "not copyrighted" in asthma.licence.lower() or "public domain" in asthma.licence.lower()


def test_escaped_html_summary_is_cleaned_and_synonyms_appended():
    text = parse()[0].text
    assert "Asthma is a chronic disease that affects your airways." in text
    assert "- Coughing" in text and "- Wheezing" in text
    assert "<p>" not in text
    assert "Also called: Bronchial asthma, Reactive airway disease" in text


def test_raw_markup_summary_is_cleaned_too():
    text = parse()[1].text
    assert text == "Diabetes is a disease in which your blood sugar levels are too high."


def test_third_party_site_records_are_never_ingested():
    all_text = " ".join(d.text for d in parse())
    assert "Some Other Organisation" not in all_text
    assert "Third-party description" not in all_text


def test_invalid_xml_raises_a_clear_error():
    with pytest.raises(ValueError, match="MedlinePlus"):
        medlineplus.parse_topics("<health-topics><oops>", retrieved_at="2026-10-31")


# ---------- fetching ----------

def mock_client(available_dates: set[str], downloads: dict | None = None) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        name = request.url.path.rsplit("/", 1)[-1]
        stamp = name.removeprefix("mplus_topics_").removesuffix(".xml")
        if stamp in available_dates:
            return httpx.Response(200, content=b"<health-topics/>")
        return httpx.Response(404)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_finds_the_newest_file_looking_back_from_today():
    client = mock_client({"2026-10-29", "2026-10-28"})
    url = fetching.find_latest_topics_url(client, date(2026, 10, 31))
    assert url == "https://medlineplus.gov/xml/mplus_topics_2026-10-29.xml"


def test_raises_when_no_file_exists_in_the_lookback_window():
    with pytest.raises(LookupError):
        fetching.find_latest_topics_url(mock_client(set()), date(2026, 10, 31), max_back=3)


def test_download_writes_the_file(tmp_path):
    client = mock_client({"2026-10-29"})
    target = tmp_path / "raw" / "topics.xml"
    fetching.download(client, "https://medlineplus.gov/xml/mplus_topics_2026-10-29.xml", target)
    assert target.read_bytes() == b"<health-topics/>"


def test_download_failure_raises_and_leaves_no_file(tmp_path):
    target = tmp_path / "topics.xml"
    with pytest.raises(httpx.HTTPStatusError):
        fetching.download(mock_client(set()), "https://medlineplus.gov/xml/mplus_topics_2026-01-01.xml", target)
    assert not target.exists()


def test_client_identifies_itself_with_a_user_agent():
    with fetching.make_client() as client:
        assert client.headers["user-agent"].startswith("VitalNest")


# ---------- BM25 index ----------

CORPUS = [
    make_chunk("a-000", "Asthma", "Wheezing cough and an inhaler help with asthma."),
    make_chunk("b-000", "Diabetes", "Insulin controls blood sugar in diabetes."),
    make_chunk("c-000", "Stroke", "Face drooping and slurred speech are stroke signs."),
]


def test_index_file_round_trip(tmp_path):
    path = tmp_path / "bm25_index.json"
    bm25_index.save_index(CORPUS, path)
    loaded = bm25_index.load_index(path)
    assert [c["chunk_id"] for c in loaded.chunks] == ["a-000", "b-000", "c-000"]
    assert loaded.chunks[1]["attribution"] == "Courtesy of MedlinePlus"
    assert len(loaded.tokens) == 3


def test_index_file_is_plain_versioned_json(tmp_path):
    path = tmp_path / "bm25_index.json"
    bm25_index.save_index(CORPUS, path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["version"] == 1
    assert set(data) >= {"version", "chunks", "tokens"}


def test_tokens_come_from_the_shared_tokenizer_and_include_the_title(tmp_path):
    path = tmp_path / "bm25_index.json"
    bm25_index.save_index(CORPUS, path)
    loaded = bm25_index.load_index(path)
    assert loaded.tokens[1] == tokenize("Diabetes Insulin controls blood sugar in diabetes.")


def test_rebuilt_bm25_ranks_the_relevant_chunk_first(tmp_path):
    path = tmp_path / "bm25_index.json"
    bm25_index.save_index(CORPUS, path)
    loaded = bm25_index.load_index(path)
    scores = BM25Okapi(loaded.tokens).get_scores(tokenize("blood sugar insulin"))
    assert loaded.chunks[int(scores.argmax())]["chunk_id"] == "b-000"


def test_loading_an_unknown_index_version_fails(tmp_path):
    path = tmp_path / "bm25_index.json"
    path.write_text(json.dumps({"version": 99, "chunks": [], "tokens": []}), encoding="utf-8")
    with pytest.raises(ValueError, match="version"):
        bm25_index.load_index(path)


# ---------- vectors ----------

class FakeEmbedder:
    def __init__(self, drop_one: bool = False):
        self.batches: list[list[str]] = []
        self.drop_one = drop_one

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        self.batches.append(list(texts))
        vectors_ = [[float(len(t))] + [1.0] * 1023 for t in texts]  # the index needs 1024 values
        return vectors_[:-1] if self.drop_one else vectors_


class FakeStore:
    def __init__(self):
        self.records: list[dict] = []
        self.calls = 0

    def upsert(self, records: list[dict]) -> None:
        self.calls += 1
        self.records.extend(records)


def five_chunks() -> list[Chunk]:
    return [make_chunk(f"d-{i:03d}", "Title", f"Chunk text number {i}.") for i in range(5)]


def test_chunks_are_embedded_and_upserted_in_batches():
    embedder, store = FakeEmbedder(), FakeStore()
    count = vectors.upsert_chunks(five_chunks(), embedder, store, batch_size=2)
    assert count == 5
    assert [len(b) for b in embedder.batches] == [2, 2, 1]
    assert store.calls == 3
    assert [r["id"] for r in store.records] == [f"d-{i:03d}" for i in range(5)]


def test_embedder_receives_title_plus_text():
    embedder, store = FakeEmbedder(), FakeStore()
    vectors.upsert_chunks(five_chunks()[:1], embedder, store)
    assert embedder.batches[0] == ["Title\nChunk text number 0."]


def test_vector_metadata_carries_text_and_citation_fields():
    store = FakeStore()
    vectors.upsert_chunks(five_chunks()[:1], FakeEmbedder(), store)
    record = store.records[0]
    assert record["values"] == [float(len("Title\nChunk text number 0."))] + [1.0] * 1023
    meta = record["metadata"]
    assert meta["text"] == "Chunk text number 0."
    assert meta["source_name"] == "MedlinePlus"
    assert meta["url"].startswith("https://example.test/")
    assert meta["attribution"] == "Courtesy of MedlinePlus"
    assert "chunk_id" not in meta  # the id is the vector id


def test_embedder_returning_the_wrong_number_of_vectors_is_an_error():
    with pytest.raises(ValueError, match="vectors"):
        vectors.upsert_chunks(five_chunks(), FakeEmbedder(drop_one=True), FakeStore(), batch_size=5)


def test_no_chunks_means_no_calls():
    embedder, store = FakeEmbedder(), FakeStore()
    assert vectors.upsert_chunks([], embedder, store) == 0
    assert embedder.batches == [] and store.calls == 0


# ---------- CLI ----------

def test_build_command_writes_chunks_and_index_offline(tmp_path):
    xml_path = tmp_path / "topics.xml"
    xml_path.write_text(TOPICS_XML, encoding="utf-8")
    out = tmp_path / "out"
    code = cli.main(["build", "--input", str(xml_path), "--output-dir", str(out),
                     "--retrieved-at", "2026-10-31"])
    assert code == 0
    rows = [json.loads(line) for line in (out / "chunks.jsonl").read_text(encoding="utf-8").splitlines()]
    assert {r["title"] for r in rows} == {"Asthma", "Diabetes"}
    assert all(r["retrieved_at"] == "2026-10-31" for r in rows)
    loaded = bm25_index.load_index(out / "bm25_index.json")
    assert len(loaded.chunks) == len(rows)


def test_upload_without_an_api_key_stops_before_any_network_call(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("PINECONE_API_KEY", raising=False)
    chunks_file = tmp_path / "chunks.jsonl"
    chunks_file.write_text("", encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        cli.main(["upload", "--chunks", str(chunks_file)])
    assert exc.value.code != 0
    assert "PINECONE_API_KEY" in capsys.readouterr().err
