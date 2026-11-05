"""WHO fact-sheet ingestion tests: topic list, parser, polite fetcher, validation, CLI. All offline."""
import json
import re

import httpx
import pytest

from vitalnest_ingest import cli, pages, who
from vitalnest_ingest.chunking import chunk_document
from vitalnest_ingest.models import Chunk
from vitalnest_ingest.validation import ChunkValidationError, validate_chunks

ROBOTS = "User-agent: *\nDisallow: /private/\n"
BODY = (
    "<h2>Key facts</h2><ul><li>Diabetes causes blindness, kidney failure and heart attacks.</li>"
    "<li>A healthy diet and regular physical activity help prevent type 2 diabetes.</li></ul>"
    "<h2>Overview</h2>Diabetes is a chronic disease that occurs when the pancreas does not produce enough "
    "insulin or when the body cannot effectively use the insulin it produces. Insulin is a hormone that "
    "regulates blood glucose. Raised blood glucose is a common effect of uncontrolled diabetes.\n"
    "<h2>Symptoms</h2><p>Symptoms include feeling very thirsty, urinating often, blurred vision and tiredness.</p>"
    "<table><tr><td>THIRD PARTY TABLE 99</td></tr></table><figure><img src='x.png'>FIGURE CAPTION</figure>"
    "<h2>References</h2><p>1) Some Institute. Third-party results. 2025.</p>"
)


def fact_sheet(title="\n\n\tDiabetes\n\n", body=BODY, canonical="https://www.who.int/news-room/fact-sheets/detail/diabetes"):
    return (
        f"<html><head><title>{title}</title>"
        f'<link rel="canonical" href="{canonical}" /></head><body>'
        '<header>SITE MENU</header><article class="sf-detail-body-wrapper" >'
        f"<div>{body}</div></article><footer>COOKIE FOOTER</footer></body></html>"
    )


# ---------- topic list ----------

def test_the_topic_list_is_large_unique_and_well_formed():
    slugs = who.all_slugs()
    assert len(slugs) > 100
    assert len(slugs) == len(set(slugs))
    for slug in slugs:
        assert pages.SLUG_PATTERN.match(slug), slug
    doc_ids = {re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-") for s in slugs}
    assert len(doc_ids) == len(slugs), "two fact sheets would share one document id"


def test_every_owner_chosen_category_has_at_least_one_fact_sheet():
    for category in [
        "Noncommunicable diseases", "Mental health", "Nutrition", "Infectious diseases", "Maternal and child health",
        "Neurological disorders", "Eye health", "Oral health", "Environmental health", "Women's health",
        "Healthy ageing", "Substance use", "Injuries and road safety", "Immunization",
        "Disability and rehabilitation", "Skin health", "Sexual health", "Adolescent health", "Hearing health",
        "Health emergencies", "Health promotion",
    ]:
        assert who.TOPICS.get(category), category


# ---------- parser ----------

def test_parse_gives_a_cited_document():
    doc = who.parse_fact_sheet(fact_sheet(), "diabetes", "2026-11-05")
    assert doc is not None
    assert (doc.doc_id, doc.source_name, doc.title) == ("who-diabetes", "WHO", "Diabetes")
    assert doc.url == "https://www.who.int/news-room/fact-sheets/detail/diabetes"
    assert doc.retrieved_at == "2026-11-05"
    assert "CC BY-NC-SA 3.0 IGO" in doc.licence and "not endorsed by WHO" in doc.licence
    assert doc.attribution == "Adapted from the World Health Organization"
    assert "Diabetes causes blindness" in doc.text and "Symptoms include feeling very thirsty" in doc.text


def test_parse_drops_page_furniture_tables_figures_and_references():
    text = who.parse_fact_sheet(fact_sheet(), "diabetes", "2026-11-05").text
    for unwanted in ["SITE MENU", "COOKIE FOOTER", "THIRD PARTY TABLE", "FIGURE CAPTION", "References", "Third-party results"]:
        assert unwanted not in text


@pytest.mark.parametrize("heading", ["<h2>References:</h2><p>1. A study.</p>", "<p>References: - A study. http://x</p>"])
def test_parse_cuts_references_headed_with_a_colon(heading):
    body = BODY.replace("<h2>References</h2><p>1) Some Institute. Third-party results. 2025.</p>", heading)
    text = who.parse_fact_sheet(fact_sheet(body=body), "diabetes", "x").text
    assert "A study" not in text and "References" not in text


def test_parse_keeps_text_that_merely_contains_the_word_references():
    body = BODY.replace("<h2>References</h2>", "<h2>Risk factors</h2><p>Family history references are common.</p><h2>References</h2>")
    text = who.parse_fact_sheet(fact_sheet(body=body), "diabetes", "2026-11-05").text
    assert "Family history references are common." in text


def test_parse_ignores_a_canonical_link_that_points_elsewhere():
    page = fact_sheet(canonical="https://evil.example/news-room/fact-sheets/detail/diabetes")
    assert who.parse_fact_sheet(page, "diabetes", "x").url == "https://www.who.int/news-room/fact-sheets/detail/diabetes"


def test_parse_builds_the_url_for_names_with_brackets():
    page = fact_sheet(canonical="")
    url = who.parse_fact_sheet(page, "influenza-(seasonal)", "x").url
    assert url == "https://www.who.int/news-room/fact-sheets/detail/influenza-(seasonal)"


@pytest.mark.parametrize(
    "html",
    ["<html><title>T</title><body>no article</body></html>", fact_sheet(body="<p>Too short.</p>"), fact_sheet(title="  ")],
)
def test_parse_returns_none_for_unusable_pages(html):
    assert who.parse_fact_sheet(html, "x", "2026-11-05") is None


def test_load_documents_reports_unusable_pages(tmp_path):
    (tmp_path / "diabetes.html").write_text(fact_sheet(), encoding="utf-8")
    (tmp_path / "broken.html").write_text("<html></html>", encoding="utf-8")
    documents, skipped = who.load_documents(tmp_path, "2026-11-05")
    assert [d.doc_id for d in documents] == ["who-diabetes"] and skipped == ["broken"]


def test_who_documents_chunk_like_any_other_source():
    chunks = chunk_document(who.parse_fact_sheet(fact_sheet(), "diabetes", "2026-11-05"))
    assert chunks and chunks[0].chunk_id == "who-diabetes-000"
    assert all(c.source_name == "WHO" and c.attribution and c.licence for c in chunks)


# ---------- fetcher ----------

def make_fetcher(tmp_path, handler, delay=0.0, sleeps=None):
    client = httpx.Client(transport=httpx.MockTransport(handler), headers={"User-Agent": pages.USER_AGENT})
    return pages.FactSheetFetcher(client, tmp_path, delay=delay, sleep=(sleeps.append if sleeps is not None else (lambda s: None)))


def site(requests, page=None, robots=ROBOTS):
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=robots)
        return httpx.Response(200, text=page if page is not None else fact_sheet(), headers={"content-type": "text/html; charset=utf-8"})

    return handler


def test_fetch_saves_the_page_and_a_second_call_uses_the_cache(tmp_path):
    requests: list[str] = []
    fetcher = make_fetcher(tmp_path, site(requests))
    path, downloaded = fetcher.fetch("diabetes")
    assert downloaded and path == tmp_path / "diabetes.html" and "Diabetes causes blindness" in path.read_text(encoding="utf-8")
    assert requests == ["https://www.who.int/robots.txt", "https://www.who.int/news-room/fact-sheets/detail/diabetes"]
    _, downloaded_again = fetcher.fetch("diabetes")
    assert not downloaded_again and len(requests) == 2


def test_overwrite_downloads_again(tmp_path):
    requests: list[str] = []
    fetcher = make_fetcher(tmp_path, site(requests))
    fetcher.fetch("diabetes")
    _, downloaded = fetcher.fetch("diabetes", overwrite=True)
    assert downloaded and len(requests) == 3  # robots.txt is read once


def test_requests_are_spaced_but_cache_hits_are_not_delayed(tmp_path):
    sleeps: list[float] = []
    fetcher = make_fetcher(tmp_path, site([]), delay=2.0, sleeps=sleeps)
    fetcher.fetch("diabetes")      # robots.txt, then the page: one pause between them
    fetcher.fetch("asthma")        # one more pause before the next request
    fetcher.fetch("diabetes")      # cached: no request, no pause
    assert sleeps == [2.0, 2.0]


def test_robots_txt_can_forbid_a_page(tmp_path):
    requests: list[str] = []
    fetcher = make_fetcher(tmp_path, site(requests, robots="User-agent: *\nDisallow: /news-room/\n"))
    with pytest.raises(pages.FetchRefused, match="robots.txt"):
        fetcher.fetch("diabetes")
    assert requests == ["https://www.who.int/robots.txt"] and not list(tmp_path.iterdir())


@pytest.mark.parametrize("slug", ["", "../etc/passwd", "a/b", "diabetes.html", "dia betes", "x?y=1", "https://evil.example/x", "-start"])
def test_bad_names_are_refused_before_any_request(tmp_path, slug):
    requests: list[str] = []
    fetcher = make_fetcher(tmp_path, site(requests))
    with pytest.raises(pages.FetchRefused):
        fetcher.fetch(slug)
    assert requests == []


def test_a_redirect_to_another_host_is_refused(tmp_path):
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=ROBOTS)
        return httpx.Response(302, headers={"location": "https://evil.example/news-room/fact-sheets/detail/diabetes"})

    with pytest.raises(pages.FetchRefused):
        make_fetcher(tmp_path, handler).fetch("diabetes")
    assert not list(tmp_path.iterdir())


def test_a_redirect_outside_the_fact_sheet_path_is_refused(tmp_path):
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=ROBOTS)
        return httpx.Response(302, headers={"location": "/health-topics/diabetes"})

    with pytest.raises(pages.FetchRefused):
        make_fetcher(tmp_path, handler).fetch("diabetes")


def test_a_redirect_to_another_fact_sheet_is_followed(tmp_path):
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=ROBOTS)
        if request.url.path.endswith("/old-name"):
            return httpx.Response(301, headers={"location": "/news-room/fact-sheets/detail/diabetes"})
        return httpx.Response(200, text=fact_sheet())

    path, downloaded = make_fetcher(tmp_path, handler).fetch("old-name")
    assert downloaded and path.name == "old-name.html"


def test_a_page_that_is_not_a_fact_sheet_is_not_saved(tmp_path):
    with pytest.raises(ValueError, match="does not look like a WHO fact sheet"):
        make_fetcher(tmp_path, site([], page="<html>Please enable JavaScript</html>")).fetch("diabetes")
    assert not list(tmp_path.iterdir())


def test_an_error_status_is_reported_and_nothing_is_saved(tmp_path):
    def handler(request):
        return httpx.Response(200, text=ROBOTS) if request.url.path == "/robots.txt" else httpx.Response(404)

    with pytest.raises(httpx.HTTPStatusError):
        make_fetcher(tmp_path, handler).fetch("no-such-sheet")
    assert not list(tmp_path.iterdir())


def test_an_oversized_page_is_stopped(tmp_path, monkeypatch):
    monkeypatch.setattr(pages, "MAX_BYTES", 1000)
    with pytest.raises(ValueError, match="too large"):
        make_fetcher(tmp_path, site([], page="x" * 5000)).fetch("diabetes")
    assert not list(tmp_path.iterdir())


# ---------- validation ----------

def make_chunk(**overrides) -> Chunk:
    values = dict(
        chunk_id="who-diabetes-000", doc_id="who-diabetes", source_name="WHO", title="Diabetes",
        url="https://www.who.int/news-room/fact-sheets/detail/diabetes", text="Diabetes is chronic.",
        retrieved_at="2026-11-05", licence=who.LICENCE, attribution=who.ATTRIBUTION,
    )
    values.update(overrides)
    return Chunk(**values)


def test_a_who_chunk_on_the_who_host_is_valid():
    validate_chunks([make_chunk()])


@pytest.mark.parametrize(
    "url",
    ["https://medlineplus.gov/diabetes.html", "http://www.who.int/x", "https://who.int.evil.example/x", "https://evil.example/www.who.int", ""],
)
def test_a_who_chunk_must_link_to_who(url):
    with pytest.raises(ChunkValidationError, match="url"):
        validate_chunks([make_chunk(url=url)])


def test_a_medlineplus_chunk_may_not_link_to_who():
    with pytest.raises(ChunkValidationError, match="url"):
        validate_chunks([make_chunk(source_name="MedlinePlus", url="https://www.who.int/news-room/fact-sheets/detail/diabetes")])


# ---------- CLI ----------

MEDLINE_XML = (
    '<?xml version="1.0"?><health-topics>'
    '<health-topic id="1" language="English" title="Asthma" url="https://medlineplus.gov/asthma.html">'
    "<full-summary>Asthma is a chronic lung disease that causes wheezing and shortness of breath.</full-summary>"
    "</health-topic></health-topics>"
)


def test_build_includes_saved_who_pages_and_reports_each_source(tmp_path, capsys):
    xml = tmp_path / "topics.xml"
    xml.write_text(MEDLINE_XML, encoding="utf-8")
    raw = tmp_path / "who"
    raw.mkdir()
    (raw / "diabetes.html").write_text(fact_sheet(), encoding="utf-8")
    out = tmp_path / "build"
    assert cli.main(["build", "--input", str(xml), "--output-dir", str(out), "--who-dir", str(raw), "--retrieved-at", "2026-11-05"]) == 0
    assert "MedlinePlus 1, WHO 1" in capsys.readouterr().out
    rows = [json.loads(line) for line in (out / "chunks.jsonl").read_text(encoding="utf-8").splitlines()]
    assert {row["source_name"] for row in rows} == {"MedlinePlus", "WHO"}
    validate_chunks([Chunk(**row) for row in rows])
    assert "wheezing" in (out / "bm25_index.json").read_text(encoding="utf-8")


def test_build_without_a_who_folder_still_builds_medlineplus_only(tmp_path, capsys):
    xml = tmp_path / "topics.xml"
    xml.write_text(MEDLINE_XML, encoding="utf-8")
    assert cli.main(["build", "--input", str(xml), "--output-dir", str(tmp_path / "b"), "--who-dir", str(tmp_path / "missing")]) == 0
    out = capsys.readouterr().out
    assert "MedlinePlus 1" in out and "WHO" not in out


def test_upload_source_filter_sends_only_the_chosen_source(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("PINECONE_API_KEY", raising=False)
    mixed = [make_chunk(), make_chunk(chunk_id="who-diabetes-001"), make_chunk(
        chunk_id="medlineplus-1-000", doc_id="medlineplus-1", source_name="MedlinePlus", url="https://medlineplus.gov/a.html")]
    path = tmp_path / "chunks.jsonl"
    path.write_text("\n".join(json.dumps(c.to_dict()) for c in mixed) + "\n", encoding="utf-8")
    assert cli.main(["upload", "--chunks", str(path), "--source", "WHO", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "2 chunks from 1 topics" in out and "WHO" in out and "MedlinePlus" not in out


def test_upload_source_filter_with_no_match_is_an_error(tmp_path, capsys):
    path = tmp_path / "chunks.jsonl"
    path.write_text(json.dumps(make_chunk().to_dict()) + "\n", encoding="utf-8")
    assert cli.main(["upload", "--chunks", str(path), "--source", "MedlinePlus", "--dry-run"]) == 1
    assert "No chunks from MedlinePlus" in capsys.readouterr().err


def test_fetch_who_reports_skipped_pages_and_uses_the_cache(tmp_path, monkeypatch, capsys):
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, text=ROBOTS)
        if request.url.path == "/robots.txt"
        else (httpx.Response(200, text=fact_sheet()) if request.url.path.endswith("/diabetes") else httpx.Response(404))
    )
    monkeypatch.setattr(pages, "make_client", lambda: httpx.Client(transport=transport, headers={"User-Agent": pages.USER_AGENT}))
    argv = ["fetch-who", "--output-dir", str(tmp_path), "--only", "diabetes", "gone", "--delay", "0"]
    assert cli.main(argv) == 0
    captured = capsys.readouterr()
    assert "1 downloaded, 0 already saved, 1 skipped" in captured.out and "skipped gone" in captured.err
    assert cli.main(argv) == 0
    assert "0 downloaded, 1 already saved, 1 skipped" in capsys.readouterr().out
