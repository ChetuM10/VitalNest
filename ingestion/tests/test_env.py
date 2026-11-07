"""Tests for loading a local .env file (used by the command-line entry points, never by library code)."""
import os

from vitalnest_ingest.env import load_env_files


def write(path, text):
    path.write_text(text, encoding="utf-8")
    return path


def test_values_are_loaded_into_the_environment(tmp_path, monkeypatch):
    monkeypatch.delenv("PINECONE_API_KEY", raising=False)
    path = write(tmp_path / ".env", "PINECONE_API_KEY=abc123\n")
    load_env_files([path])
    assert os.environ["PINECONE_API_KEY"] == "abc123"


def test_an_existing_environment_variable_wins_over_the_file(tmp_path, monkeypatch):
    monkeypatch.setenv("PINECONE_API_KEY", "from-the-shell")
    load_env_files([write(tmp_path / ".env", "PINECONE_API_KEY=from-the-file\n")])
    assert os.environ["PINECONE_API_KEY"] == "from-the-shell"


def test_earlier_files_win_over_later_ones(tmp_path, monkeypatch):
    monkeypatch.delenv("PINECONE_API_KEY", raising=False)
    first = write(tmp_path / "one.env", "PINECONE_API_KEY=first\n")
    second = write(tmp_path / "two.env", "PINECONE_API_KEY=second\n")
    load_env_files([first, second])
    assert os.environ["PINECONE_API_KEY"] == "first"


def test_comments_blank_lines_quotes_and_spaces_are_handled(tmp_path, monkeypatch):
    monkeypatch.delenv("PINECONE_API_KEY", raising=False)
    monkeypatch.delenv("OTHER_SETTING", raising=False)
    text = '# my keys\n\n  PINECONE_API_KEY = "quoted-value"  \nOTHER_SETTING=\'single\'\n'
    load_env_files([write(tmp_path / ".env", text)])
    assert os.environ["PINECONE_API_KEY"] == "quoted-value"
    assert os.environ["OTHER_SETTING"] == "single"


def test_malformed_lines_are_ignored_not_fatal(tmp_path, monkeypatch):
    monkeypatch.delenv("PINECONE_API_KEY", raising=False)
    text = "not a setting\n=novalue\nlower case=x\nPINECONE_API_KEY=ok\n"
    load_env_files([write(tmp_path / ".env", text)])
    assert os.environ["PINECONE_API_KEY"] == "ok"
    assert "lower case" not in os.environ


def test_empty_values_are_not_set(tmp_path, monkeypatch):
    monkeypatch.delenv("PINECONE_API_KEY", raising=False)
    load_env_files([write(tmp_path / ".env", "PINECONE_API_KEY=\n")])
    assert "PINECONE_API_KEY" not in os.environ


def test_missing_files_are_fine(tmp_path):
    assert load_env_files([tmp_path / "nope.env"]) == []


def test_it_reports_names_never_values(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("PINECONE_API_KEY", raising=False)
    path = write(tmp_path / ".env", "PINECONE_API_KEY=super-secret-value\n")
    result = load_env_files([path])
    assert result == [(path, ["PINECONE_API_KEY"])]
    assert "super-secret-value" not in repr(result)
    assert "super-secret-value" not in capsys.readouterr().out


def test_the_default_search_includes_the_ingestion_folder_and_the_home_folder():
    from vitalnest_ingest import env

    names = [str(p) for p in env.default_env_paths()]
    assert any(n.endswith("ingestion\\.env") or n.endswith("ingestion/.env") for n in names)
    assert any(n.endswith(".vitalnest.env") for n in names)


def test_secret_files_are_ignored_by_git_and_an_example_exists():
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    ignored = (root / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert ".env" in ignored and "*.env" in ignored
    example = (root / "ingestion" / ".env.example").read_text(encoding="utf-8")
    assert "PINECONE_API_KEY=" in example
    assert "pcsk_" not in example  # an example must never contain a real-looking key
