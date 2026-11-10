import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import chat, health, me
from app.api.rate_limit import build_rate_limiter
from app.api.schemas import PAYLOAD_TOO_LARGE
from app.chat.factory import build_chat_service
from app.config.settings import allowed_origin, bm25_index_path
from app.llm.claude import LLMError
from app.retrieval.bm25 import Bm25Index
from app.retrieval.types import RetrievalError

logger = logging.getLogger("vitalnest")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load the BM25 index once at startup; the server then keeps it in memory.

    A missing file only logs a warning, so /v1/health still works before ingestion has run.
    A file that exists but is corrupt stops the app: serving with a broken index would be worse.
    """
    path = bm25_index_path()
    if path.exists():
        app.state.bm25 = Bm25Index.load(path)
    else:
        logger.warning("BM25 index not found at %s; keyword search is unavailable", path)
        app.state.bm25 = None
    app.state.chat_service = build_chat_service(app.state.bm25)
    yield


def _error_body(code: str, message: str) -> dict:
    return {"error": {"code": code, "message": message}}


def _describe(error: dict) -> str:
    """Field path plus Pydantic's message. Never includes the submitted value, which may be health data."""
    path = ".".join(str(part) for part in error["loc"] if part != "body")
    return f"{path}: {error['msg']}" if path else error["msg"]


def create_app() -> FastAPI:
    app = FastAPI(title="VitalNest API", docs_url=None, redoc_url=None, lifespan=lifespan)
    app.state.rate_limiter = build_rate_limiter()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[allowed_origin()],
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
        expose_headers=["Retry-After"],
    )

    @app.exception_handler(HTTPException)
    async def http_error(_: Request, exc: HTTPException) -> JSONResponse:
        detail = exc.detail if isinstance(exc.detail, dict) else {"code": "error", "message": str(exc.detail)}
        return JSONResponse(
            _error_body(detail["code"], detail["message"]), status_code=exc.status_code, headers=exc.headers
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        errors = exc.errors()
        message = _describe(errors[0]) if errors else "Request validation failed."
        if any(error["type"] == PAYLOAD_TOO_LARGE for error in errors):
            return JSONResponse(_error_body(PAYLOAD_TOO_LARGE, message), status_code=413)
        return JSONResponse(_error_body("validation_error", message), status_code=422)

    @app.exception_handler(RetrievalError)
    async def retrieval_error(_: Request, exc: RetrievalError) -> JSONResponse:
        return JSONResponse(_error_body("upstream_error", "The search service is unavailable."), status_code=502)

    @app.exception_handler(LLMError)
    async def llm_error(_: Request, exc: LLMError) -> JSONResponse:
        return JSONResponse(_error_body(exc.code, str(exc)), status_code=504 if exc.code == "timeout" else 502)

    for module in (health, me, chat):
        app.include_router(module.router, prefix="/v1")
    return app


app = create_app()
