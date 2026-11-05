"""CDC page ingestion tests: parser, copyright rule, reviewed list, polite fetcher, validation, CLI. All offline."""
import json

import httpx
import pytest

from vitalnest_ingest import cdc, cli, pages
from vitalnest_ingest.chunking import chunk_document
from vitalnest_ingest.models import Chunk
from vitalnest_ingest.validation import ChunkValidationError, validate_chunks

ROBOTS = "User-agent: *\nDisallow: /travel/\n"
CONTENT = (
    "<h1>Diabetes Basics</h1><p>Jan. 2, 2026</p><a href='/es/'>Español</a>"
    "<h2>Key points</h2><ul><li>Diabetes is a chronic health condition that affects how your body turns food into energy.</li>"
    "<li>There are three main types of diabetes: type 1, type 2, and gestational diabetes.</li></ul>"
    "<h2>Symptoms</h2><p>Common symptoms include feeling very thirsty, urinating often, blurred vision, tiredness and "
    "slow-healing sores. Many people with type 2 diabetes have no symptoms for years, so testing matters.</p>"
    "<table><tr><td>THIRD PARTY TABLE 99</td></tr></table><figure><img src='x.png'>FIGURE CAPTION</figure>"
    "<h2>Treatment</h2><p>Treatment depends on the type of diabetes and may include healthy eating, activity and medicine.</p>"
    "<p>For Everyone</p><p>Download</p><h2>Get email updates</h2><p>Sign up for Diabetes Insider.</p><p>Content Source:</p><p>National Center</p><p>Sources and Page Info Print Share</p><p>Facebook LinkedIn Twitter Syndicate</p>"
)


def page(content=CONTENT, title="Diabetes Basics | Diabetes | CDC", canonical="https://www.cdc.gov/diabetes/about/index.html"):
    return (
        f"<html><head><title>{title}</title><link rel=\"canonical\" href=\"{canonical}\"/></head><body>"
        f'<header>SITE MENU</header><main class="container cdc-main">{content}</main><footer>FOOTER LINKS</footer></body></html>'
    )


# ---------- parser ----------

def test_parse_gives_a_cited_document():
    doc = cdc.parse_page(page(), "diabetes/about/index.html", "2026-11-05")
    assert (doc.doc_id, doc.source_name, doc.title) == ("cdc-diabetes-about-index", "CDC", "Diabetes Basics")
    assert doc.url == "https://www.cdc.gov/diabetes/about/index.html"
    assert doc.attribution == "Content from the Centers for Disease Control and Prevention"
    assert "not endorsed by CDC" in doc.licence and doc.retrieved_at == "2026-11-05"
    assert "Common symptoms include feeling very thirsty" in doc.text


def test_parse_drops_furniture_tables_figures_dates_and_the_tail():
    text = cdc.parse_page(page(), "diabetes/about/index.html", "x").text
    for unwanted in ["SITE MENU", "FOOTER LINKS", "THIRD PARTY TABLE", "FIGURE CAPTION", "Jan. 2, 2026", "Español",
                     "For Everyone", "Download", "Sources and Page Info", "Facebook LinkedIn", "Get email updates", "Sign up for Diabetes Insider", "Content Source", "National Center"]:
        assert unwanted not in text
    assert "Treatment depends on the type of diabetes" in text


@pytest.mark.parametrize(
    "notice",
    ["© 2024 Some Publisher", "&copy; 2024 Some Publisher", "Copyright 2024 Some Publisher", "Image used with permission from X",
     "Reprinted with permission of the author", "COPYRIGHT NOTICE"],
)
def test_a_page_with_a_copyright_or_permission_notice_is_skipped(notice):
    with pytest.raises(cdc.Skipped, match="copyright"):
        cdc.parse_page(page(CONTENT + f"<p>{notice}</p>"), "diabetes/about/index.html", "x")


def test_a_copyright_notice_outside_the_main_content_does_not_matter():
    html = page().replace("<footer>FOOTER LINKS</footer>", "<footer>Copyright information for the whole site</footer>")
    assert cdc.parse_page(html, "diabetes/about/index.html", "x").title == "Diabetes Basics"


@pytest.mark.parametrize(
    "html, reason",
    [
        ("<html><title>T</title><body>no main</body></html>", "no main content"),
        (page("<p>Too short.</p>"), "too little text"),
        (page(title="Page Not Found | CDC"), "no usable title"),
        (page(title=" | CDC"), "no usable title"),
    ],
)
def test_unusable_pages_are_skipped_with_a_reason(html, reason):
    with pytest.raises(cdc.Skipped, match=reason):
        cdc.parse_page(html, "x/y.html", "x")


def test_a_canonical_link_to_another_site_is_ignored():
    html = page(canonical="https://evil.example/diabetes/about/index.html")
    assert cdc.parse_page(html, "diabetes/about/index.html", "x").url == "https://www.cdc.gov/diabetes/about/index.html"


def test_an_early_resources_heading_does_not_cut_the_page_short():
    content = "<h2>Resources</h2><p>Early heading text that matters a lot to readers.</p>" + CONTENT
    text = cdc.parse_page(page(content), "diabetes/about/index.html", "x").text
    assert "Early heading text that matters" in text and "Treatment depends" in text


def test_cdc_documents_chunk_like_any_other_source():
    chunks = chunk_document(cdc.parse_page(page(), "diabetes/about/index.html", "2026-11-05"))
    assert chunks and chunks[0].chunk_id == "cdc-diabetes-about-index-000"
    assert all(c.source_name == "CDC" and c.attribution and c.licence for c in chunks)


def test_load_documents_reports_skipped_pages_with_reasons(tmp_path):
    (tmp_path / "diabetes__about__index.html").write_text(page(), encoding="utf-8")
    (tmp_path / "x__copyrighted.html").write_text(page(CONTENT + "<p>© Someone</p>"), encoding="utf-8")
    documents, skipped = cdc.load_documents(tmp_path, "2026-11-05")
    assert [d.doc_id for d in documents] == ["cdc-diabetes-about-index"]
    assert list(skipped) == ["x/copyrighted.html"] and "copyright" in skipped["x/copyrighted.html"]


# ---------- reviewed list ----------

def test_the_page_list_ignores_comments_and_blanks_and_dedupes(tmp_path):
    path = tmp_path / "list.txt"
    path.write_text("# diabetes\ndiabetes/about/index.html  # basics\n\nasthma/about/index.html\ndiabetes/about/index.html\n", encoding="utf-8")
    assert cdc.load_page_list(path) == ["diabetes/about/index.html", "asthma/about/index.html"]


@pytest.mark.parametrize("line", ["https://www.cdc.gov/x.html", "../x.html", "a/b", "A/b.html", "a//b.html", "a__b.html"])
def test_a_bad_line_in_the_page_list_is_an_error_naming_the_line(tmp_path, line):
    path = tmp_path / "list.txt"
    path.write_text(f"ok/page.html\n{line}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="line 2"):
        cdc.load_page_list(path)


def test_the_real_reviewed_list_is_valid_and_not_tiny():
    from pathlib import Path

    listing = Path(__file__).resolve().parents[1] / "cdc_pages.txt"
    if not listing.exists():
        pytest.skip("reviewed list not created yet")
    keys = cdc.load_page_list(listing)
    assert len(keys) >= 50
    ids = {k.removesuffix(".html").replace("/", "-") for k in keys}
    assert len(ids) == len(keys), "two pages would share one document id"


# ---------- fetcher ----------

def make_fetcher(tmp_path, handler, delay=0.0, sleeps=None):
    client = httpx.Client(transport=httpx.MockTransport(handler), headers={"User-Agent": pages.USER_AGENT})
    return pages.CdcFetcher(client, tmp_path, delay=delay, sleep=(sleeps.append if sleeps is not None else (lambda s: None)))


def site(requests, html=None, robots=ROBOTS):
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=robots)
        return httpx.Response(200, text=html if html is not None else page())

    return handler


def test_fetch_saves_under_a_flat_name_and_then_uses_the_cache(tmp_path):
    requests: list[str] = []
    fetcher = make_fetcher(tmp_path, site(requests))
    path, downloaded = fetcher.fetch("diabetes/about/index.html")
    assert downloaded and path == tmp_path / "diabetes__about__index.html"
    assert requests == ["https://www.cdc.gov/robots.txt", "https://www.cdc.gov/diabetes/about/index.html"]
    assert fetcher.fetch("diabetes/about/index.html") == (path, False) and len(requests) == 2


def test_requests_are_spaced(tmp_path):
    sleeps: list[float] = []
    make_fetcher(tmp_path, site([]), delay=2.0, sleeps=sleeps).fetch("diabetes/about/index.html")
    assert sleeps == [2.0]


def test_robots_txt_can_forbid_a_page(tmp_path):
    requests: list[str] = []
    fetcher = make_fetcher(tmp_path, site(requests, robots="User-agent: *\nDisallow: /travel/\n"))
    with pytest.raises(pages.FetchRefused, match="robots.txt"):
        fetcher.fetch("travel/page.html")
    assert requests == ["https://www.cdc.gov/robots.txt"]


@pytest.mark.parametrize("key", ["", "../x.html", "a/../b.html", "a__b.html", "Diabetes/About.html", "x.pdf", "x", "/x.html", "https://evil.example/x.html"])
def test_bad_paths_are_refused_before_any_request(tmp_path, key):
    requests: list[str] = []
    with pytest.raises(pages.FetchRefused):
        make_fetcher(tmp_path, site(requests)).fetch(key)
    assert requests == []


def test_a_redirect_to_another_host_is_refused(tmp_path):
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=ROBOTS)
        return httpx.Response(302, headers={"location": "https://evil.example/x.html"})

    with pytest.raises(pages.FetchRefused):
        make_fetcher(tmp_path, handler).fetch("diabetes/about/index.html")
    assert not list(tmp_path.iterdir())


def test_a_redirect_into_a_path_robots_txt_forbids_is_refused(tmp_path):
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=ROBOTS)
        return httpx.Response(301, headers={"location": "/travel/page.html"})

    with pytest.raises(pages.FetchRefused, match="robots.txt"):
        make_fetcher(tmp_path, handler).fetch("diabetes/about/index.html")


def test_a_redirect_to_another_cdc_page_is_followed(tmp_path):
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=ROBOTS)
        if request.url.path.endswith("/old.html"):
            return httpx.Response(301, headers={"location": "/diabetes/about/index.html"})
        return httpx.Response(200, text=page())

    path, downloaded = make_fetcher(tmp_path, handler).fetch("diabetes/old.html")
    assert downloaded and path.name == "diabetes__old.html"


def test_a_page_that_is_not_a_cdc_page_is_not_saved(tmp_path):
    with pytest.raises(ValueError, match="does not look like a CDC page"):
        make_fetcher(tmp_path, site([], html="<html>Please enable JavaScript</html>")).fetch("diabetes/about/index.html")
    assert not list(tmp_path.iterdir())


def test_a_missing_page_is_reported_and_nothing_is_saved(tmp_path):
    def handler(request):
        return httpx.Response(200, text=ROBOTS) if request.url.path == "/robots.txt" else httpx.Response(404)

    with pytest.raises(httpx.HTTPStatusError):
        make_fetcher(tmp_path, handler).fetch("nope/page.html")
    assert not list(tmp_path.iterdir())


# ---------- validation ----------

def make_chunk(**overrides) -> Chunk:
    values = dict(
        chunk_id="cdc-diabetes-about-index-000", doc_id="cdc-diabetes-about-index", source_name="CDC", title="Diabetes Basics",
        url="https://www.cdc.gov/diabetes/about/index.html", text="Diabetes is chronic.", retrieved_at="2026-11-05",
        licence=cdc.LICENCE, attribution=cdc.ATTRIBUTION,
    )
    values.update(overrides)
    return Chunk(**values)


def test_a_cdc_chunk_on_the_cdc_host_is_valid():
    validate_chunks([make_chunk()])


@pytest.mark.parametrize("url", ["https://www.who.int/x", "http://www.cdc.gov/x.html", "https://cdc.gov.evil.example/x.html", "https://evil.example/www.cdc.gov", ""])
def test_a_cdc_chunk_must_link_to_cdc(url):
    with pytest.raises(ChunkValidationError, match="url"):
        validate_chunks([make_chunk(url=url)])


def test_a_who_chunk_may_not_link_to_cdc():
    with pytest.raises(ChunkValidationError, match="url"):
        validate_chunks([make_chunk(source_name="WHO", url="https://www.cdc.gov/diabetes/about/index.html")])


# ---------- CLI ----------

MEDLINE_XML = (
    '<?xml version="1.0"?><health-topics>'
    '<health-topic id="1" language="English" title="Asthma" url="https://medlineplus.gov/asthma.html">'
    "<full-summary>Asthma is a chronic lung disease that causes wheezing and shortness of breath.</full-summary>"
    "</health-topic></health-topics>"
)


def test_build_includes_saved_cdc_pages_and_names_skipped_ones(tmp_path, capsys):
    raw = tmp_path / "raw"
    (raw / "cdc").mkdir(parents=True)
    xml = raw / "topics.xml"
    xml.write_text(MEDLINE_XML, encoding="utf-8")
    (raw / "cdc" / "diabetes__about__index.html").write_text(page(), encoding="utf-8")
    (raw / "cdc" / "bad__page.html").write_text(page(CONTENT + "<p>© Someone</p>"), encoding="utf-8")
    out = tmp_path / "build"
    assert cli.main(["build", "--input", str(xml), "--output-dir", str(out), "--retrieved-at", "2026-11-05"]) == 0
    captured = capsys.readouterr()
    assert "CDC 1, MedlinePlus 1" in captured.out and "Skipped CDC page bad/page.html: page has a copyright" in captured.err
    rows = [json.loads(line) for line in (out / "chunks.jsonl").read_text(encoding="utf-8").splitlines()]
    assert {row["source_name"] for row in rows} == {"MedlinePlus", "CDC"}
    validate_chunks([Chunk(**row) for row in rows])


def test_fetch_cdc_reads_the_list_reports_skips_and_uses_the_cache(tmp_path, monkeypatch, capsys):
    listing = tmp_path / "list.txt"
    listing.write_text("diabetes/about/index.html\ngone/page.html\n", encoding="utf-8")

    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=ROBOTS)
        return httpx.Response(200, text=page()) if request.url.path.startswith("/diabetes") else httpx.Response(404)

    monkeypatch.setattr(pages, "make_client", lambda: httpx.Client(transport=httpx.MockTransport(handler), headers={"User-Agent": pages.USER_AGENT}))
    argv = ["fetch-cdc", "--list", str(listing), "--output-dir", str(tmp_path / "cdc"), "--delay", "0"]
    assert cli.main(argv) == 0
    captured = capsys.readouterr()
    assert "1 downloaded, 0 already saved, 1 skipped" in captured.out and "skipped gone/page.html" in captured.err
    assert cli.main(argv) == 0
    assert "0 downloaded, 1 already saved, 1 skipped" in capsys.readouterr().out


def test_fetch_cdc_with_a_bad_list_is_a_clear_error(tmp_path, capsys):
    listing = tmp_path / "list.txt"
    listing.write_text("../etc/passwd\n", encoding="utf-8")
    assert cli.main(["fetch-cdc", "--list", str(listing), "--output-dir", str(tmp_path / "cdc")]) == 1
    assert "line 1" in capsys.readouterr().err
