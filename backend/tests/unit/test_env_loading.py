"""Local secrets loading for the backend: where it looks, what it never does."""
import os
from pathlib import Path

from app.config.env import default_env_paths, load_env_files


def write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_values_are_loaded_but_the_shell_wins(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("PINECONE_API_KEY", "from-the-shell")
    path = write(tmp_path / ".env", "ANTHROPIC_API_KEY=abc\nPINECONE_API_KEY=from-the-file\n")
    result = load_env_files([path])
    assert os.environ["ANTHROPIC_API_KEY"] == "abc"
    assert os.environ["PINECONE_API_KEY"] == "from-the-shell"
    assert result == [(path, ["ANTHROPIC_API_KEY"])]  # names only, never values


def test_comments_quotes_and_bad_lines_are_handled(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    path = write(tmp_path / ".env", '# note\nbad line\nexport ANTHROPIC_API_KEY = "quoted"\n')
    load_env_files([path])
    assert os.environ["ANTHROPIC_API_KEY"] == "quoted"


def test_missing_files_are_fine(tmp_path):
    assert load_env_files([tmp_path / "nope.env"]) == []


def test_the_search_list_never_includes_the_backend_folder():
    """backend/ is what `sam build` packages for Lambda, so a key file there would be shipped to AWS."""
    paths = default_env_paths()
    assert paths, "there must be at least one default location"
    backend_dir = Path(__file__).resolve().parents[2]
    assert not any(backend_dir in p.resolve().parents for p in paths)
    names = [str(p).replace("\\", "/") for p in paths]
    assert any(n.endswith("ingestion/.env") for n in names)
    assert any(n.endswith(".vitalnest.env") for n in names)


def test_nothing_is_read_when_running_on_lambda(tmp_path, monkeypatch):
    """On AWS the keys come from Secrets Manager (T13); local files must never be consulted."""
    monkeypatch.setenv("AWS_LAMBDA_FUNCTION_NAME", "vitalnest-api")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    path = write(tmp_path / ".env", "ANTHROPIC_API_KEY=should-not-load\n")
    assert load_env_files([path]) == []
    assert "ANTHROPIC_API_KEY" not in os.environ
