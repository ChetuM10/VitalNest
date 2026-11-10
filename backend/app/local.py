"""Local development entry point:  uvicorn app.local:app --app-dir backend

Loads keys from ingestion/.env or ~/.vitalnest.env first, and uses the keyword index that the ingestion
build wrote, if there is one. Never used when hosted (Render starts app.main).
"""
import os
from pathlib import Path

from app.config.env import load_env_files

load_env_files()
os.environ.setdefault("LOCAL_DEV_AUTH", "1")  # local only: accept the Vite proxy's fake identity (set 0 to test real tokens)

_BUILT_INDEX = Path(__file__).resolve().parents[2] / "ingestion" / "data" / "build" / "bm25_index.json"
if _BUILT_INDEX.exists():
    os.environ.setdefault("BM25_INDEX_PATH", str(_BUILT_INDEX))

from app.main import create_app  # noqa: E402  (must come after the keys and paths are set)

app = create_app()
