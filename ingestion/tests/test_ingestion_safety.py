"""Safety tests for the real fetch/build run: official source only, no overwrites, no corruption,
errors reported as messages (not tracebacks)."""
import json
from datetime import date
from pathlib import Path

import httpx
import pytest

from vitalnest_ingest import cli, fetching
from vitalnest_ingest.files import write_text_atomic

GOOD_XML = b'<?xml version="1.0"?><health-topics total="1"><health-topic id="1" title="T" url="u" language="English"><full-summary>&lt;p&gt;Body text.&lt;/p&gt;</full-summary></health-topic></health-topics>'
OFFICIAL = "https://medlineplus.gov/xml/mplus_topics_2026-10-29.xml"


def client_returning(response: httpx.Response | None = None, handler=None) -> httpx.Client:
    return httpx.Client(
        transport=httpx.MockTransport(handler or (lambda request: response)), follow_redirects=True
    )


# ---------- official source only ----------

@pytest.mark.parametrize(
    "url",
    [
        "http://medlineplus.gov/xml/mplus_topics_2026-10-29.xml",           # not HTTPS
        "https://evil.example/xml/mplus_topics_2026-10-29.xml",             # other host
        "https://medlineplus.gov.evil.example/xml/mplus_topics_2026-10-29.xml",  # look-alike host
        "https://user@medlineplus.gov@evil.example/x.xml",                  # credential trick
        "ftp://medlineplus.gov/xml/mplus_topics_2026-10-29.xml",
    ],
)
def test_only_https_medlineplus_urls_are_downloaded(tmp_path, url):
    called = []
    client = client_returning(handler=lambda request: called.append(request) or httpx.Response(200, content=GOOD_XML))
    with pytest.raises(ValueError, match="official"):
        fetching.download(client, url, tmp_path / "t.xml")
    assert called == [], "no request may be sent to a non-official URL"
    assert not (tmp_path / "t.xml").exists()


def test_redirect_to_another_host_is_rejected(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "medlineplus.gov":
            return httpx.Response(302, headers={"Location": "https://evil.example/topics.xml"})
        return httpx.Response(200, content=GOOD_XML)

    with pytest.raises(ValueError, match="official"):
        fetching.download(client_returning(handler=handler), OFFICIAL, tmp_path / "t.xml")
    assert not (tmp_path / "t.xml").exists()


# ---------- no overwrite, no corruption ----------

def test_existing_file_is_not_overwritten_by_default(tmp_path):
    target = tmp_path / "t.xml"
    target.write_bytes(b"original")
    with pytest.raises(FileExistsError):
        fetching.download(client_returning(httpx.Response(200, content=GOOD_XML)), OFFICIAL, target)
    assert target.read_bytes() == b"original"


def test_overwrite_must_be_explicit(tmp_path):
    target = tmp_path / "t.xml"
    target.write_bytes(b"original")
    fetching.download(client_returning(httpx.Response(200, content=GOOD_XML)), OFFICIAL, target, overwrite=True)
    assert target.read_bytes() == GOOD_XML


@pytest.mark.parametrize(
    "body",
    [b"", b"<html><body>Service unavailable</body></html>", b"not xml at all", b"<health-topics><broken"],
)
def test_bad_content_is_rejected_and_the_existing_file_survives(tmp_path, body):
    target = tmp_path / "t.xml"
    target.write_bytes(b"original")
    with pytest.raises(ValueError):
        fetching.download(client_returning(httpx.Response(200, content=body)), OFFICIAL, target, overwrite=True)
    assert target.read_bytes() == b"original"
    assert list(tmp_path.glob("*.part")) == []


def test_oversized_download_is_stopped(tmp_path, monkeypatch):
    monkeypatch.setattr(fetching, "MAX_BYTES", 100)
    with pytest.raises(ValueError, match="too large"):
        fetching.download(client_returning(httpx.Response(200, content=GOOD_XML)), OFFICIAL, tmp_path / "t.xml")
    assert list(tmp_path.iterdir()) == []


def test_atomic_write_keeps_the_old_file_if_the_swap_fails(tmp_path, monkeypatch):
    target = tmp_path / "out.txt"
    target.write_text("old", encoding="utf-8")

    def boom(self, other):
        raise OSError("disk problem")

    monkeypatch.setattr(Path, "replace", boom)
    with pytest.raises(OSError):
        write_text_atomic(target, "new")
    assert target.read_text(encoding="utf-8") == "old"
    assert [p.name for p in tmp_path.iterdir()] == ["out.txt"]


# ---------- CLI: errors become messages, outputs are protected ----------

def run(argv, capsys):
    code = cli.main(argv)
    return code, capsys.readouterr()


def test_fetch_failure_prints_a_message_and_returns_1(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "PROBE_PAUSE", 0)
    monkeypatch.setattr(fetching, "make_client", lambda: client_returning(httpx.Response(404)))
    code, out = run(["fetch", "--output-dir", str(tmp_path)], capsys)
    assert code == 1
    assert "Traceback" not in out.err
    assert "No MedlinePlus topics file" in out.err
    assert list(tmp_path.iterdir()) == []


def test_fetch_refuses_to_overwrite_an_existing_download(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "PROBE_PAUSE", 0)
    stamp = date.today().isoformat()
    monkeypatch.setattr(fetching, "make_client", lambda: client_returning(httpx.Response(200, content=GOOD_XML)))
    existing = tmp_path / f"mplus_topics_{stamp}.xml"
    existing.write_bytes(b"original")
    code, out = run(["fetch", "--output-dir", str(tmp_path)], capsys)
    assert code == 1
    assert "already exists" in out.err
    assert existing.read_bytes() == b"original"


def write_input(tmp_path, content: bytes = GOOD_XML) -> Path:
    path = tmp_path / "topics.xml"
    path.write_bytes(content)
    return path


def test_build_refuses_to_overwrite_existing_outputs(tmp_path, capsys):
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    (out_dir / "chunks.jsonl").write_text("keep me", encoding="utf-8")
    code, out = run(["build", "--input", str(write_input(tmp_path)), "--output-dir", str(out_dir)], capsys)
    assert code == 1
    assert "--force" in out.err
    assert (out_dir / "chunks.jsonl").read_text(encoding="utf-8") == "keep me"
    assert not (out_dir / "bm25_index.json").exists()


def test_build_force_replaces_outputs(tmp_path, capsys):
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    (out_dir / "chunks.jsonl").write_text("old", encoding="utf-8")
    code, _ = run(["build", "--input", str(write_input(tmp_path)), "--output-dir", str(out_dir), "--force"], capsys)
    assert code == 0
    assert json.loads((out_dir / "chunks.jsonl").read_text(encoding="utf-8").splitlines()[0])["title"] == "T"


@pytest.mark.parametrize(
    "content, expected",
    [
        (b"<health-topics><oops>", "Could not parse"),
        (b'<health-topics total="0"></health-topics>', "no usable topics"),
    ],
)
def test_build_failures_write_nothing_and_explain(tmp_path, capsys, content, expected):
    out_dir = tmp_path / "out"
    code, out = run(["build", "--input", str(write_input(tmp_path, content)), "--output-dir", str(out_dir)], capsys)
    assert code == 1
    assert expected in out.err
    assert "Traceback" not in out.err
    assert not out_dir.exists() or list(out_dir.iterdir()) == []


def test_build_with_missing_input_explains(tmp_path, capsys):
    code, out = run(["build", "--input", str(tmp_path / "nope.xml"), "--output-dir", str(tmp_path / "o")], capsys)
    assert code == 1
    assert "not found" in out.err.lower()
