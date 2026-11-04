from fastapi import APIRouter

from app.config.settings import APP_VERSION

router = APIRouter()


@router.get("/health")
def health() -> dict:
    """Public liveness check. Touches no external service."""
    return {"status": "ok", "version": APP_VERSION}
