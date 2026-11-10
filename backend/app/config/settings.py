import os
from pathlib import Path

APP_VERSION = "0.0.1"

_DEFAULT_BM25_INDEX = Path(__file__).resolve().parents[1] / "data" / "bm25_index.json"


def claude_model() -> str:
    """The Claude model (decision: Haiku 5.5, fast and cheap for short grounded answers). Override with CLAUDE_MODEL."""
    return os.environ.get("CLAUDE_MODEL", "claude-haiku-5-5")


def no_context_min_dense_score() -> float:
    """Below this best cosine score the question is treated as not covered by the sources, and Claude is
    not called. Set by the T16 evaluation (evaluation/results): the lowest score of an answerable question
    was 0.853 and the highest of an unanswerable one 0.838, so 0.845 is the midpoint of the gap."""
    return float(os.environ.get("NO_CONTEXT_MIN_DENSE_SCORE", "0.845"))


def claude_max_tokens() -> int:
    """Output cap per answer (decision: cost control). It also covers the model's thinking tokens,
    so it is above the ~600 the answer itself needs."""
    return int(os.environ.get("CLAUDE_MAX_TOKENS", "1200"))


def bm25_index_path() -> Path:
    """Where the ingestion script's BM25 index is copied for deployment (see ingestion/README.md)."""
    return Path(os.environ.get("BM25_INDEX_PATH", str(_DEFAULT_BM25_INDEX)))


def allowed_origin() -> str:
    """Frontend origin allowed by CORS. Set with ALLOWED_ORIGIN on the host (the Vercel address); defaults to local Vite."""
    return os.environ.get("ALLOWED_ORIGIN", "http://localhost:5173")


def cognito_region() -> str:
    return os.environ.get("COGNITO_REGION", "ap-south-1")


def cognito_user_pool_id() -> str | None:
    return os.environ.get("COGNITO_USER_POOL_ID")


def cognito_client_id() -> str | None:
    return os.environ.get("COGNITO_CLIENT_ID")


def rate_limit_per_minute() -> int:
    return int(os.environ.get("RATE_LIMIT_PER_MINUTE", "6"))


def rate_limit_per_day() -> int:
    return int(os.environ.get("RATE_LIMIT_PER_DAY", "60"))


def rate_limit_global_per_day() -> int:
    """Overall cap on questions per rolling 24 hours: a spending guard (about $0.0007 per question)."""
    return int(os.environ.get("RATE_LIMIT_GLOBAL_PER_DAY", "1500"))
