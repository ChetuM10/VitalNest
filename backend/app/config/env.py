"""Load secrets from a local .env file into the environment (local development only).

Rules, each covered by a test:
- a variable already set in the shell always wins; earlier files win over later ones;
- values are never printed, logged or returned (only variable names are reported);
- nothing is read on AWS Lambda, where keys come from Secrets Manager instead;
- the backend/ folder is never searched: `sam build` packages that folder into the Lambda zip, so
  a key file there would be shipped to AWS.

Search order: ingestion/.env, then ~/.vitalnest.env (outside the project, so OneDrive does not sync it).
"""
import os
import re
from pathlib import Path

_NAME = re.compile(r"^[A-Z_][A-Z0-9_]*$")
_REPO_ROOT = Path(__file__).resolve().parents[3]


def default_env_paths() -> list[Path]:
    return [_REPO_ROOT / "ingestion" / ".env", Path.home() / ".vitalnest.env"]


def _parse(text: str):
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        name, separator, value = line.partition("=")
        name, value = name.strip(), value.strip()
        if not separator or not _NAME.match(name):
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if value:
            yield name, value


def load_env_files(paths: list[Path] | None = None) -> list[tuple[Path, list[str]]]:
    """Returns [(file, [names set from it])] for files that exist. Never returns values."""
    if os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
        return []
    loaded: list[tuple[Path, list[str]]] = []
    for path in default_env_paths() if paths is None else paths:
        if not path.is_file():
            continue
        names: list[str] = []
        for name, value in _parse(path.read_text(encoding="utf-8")):
            if name not in os.environ:
                os.environ[name] = value
                names.append(name)
        loaded.append((path, names))
    return loaded
