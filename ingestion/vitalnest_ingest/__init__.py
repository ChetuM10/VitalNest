"""Standalone ingestion script. It reuses the backend's tokenizer so the BM25 index and the API
always split text the same way, so the backend folder is put on the import path."""
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2] / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.append(str(_BACKEND))
