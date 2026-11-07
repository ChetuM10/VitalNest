from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask

from app.api.errors import api_error
from app.api.rate_limit import limit_chat
from app.api.schemas import ChatRequest
from app.chat.service import ChatService

router = APIRouter()


def get_chat_service(request: Request) -> ChatService | None:
    return getattr(request.app.state, "chat_service", None)


@router.post("/chat")
async def chat(
    body: ChatRequest,
    _limit: None = Depends(limit_chat),
    service: ChatService | None = Depends(get_chat_service),
) -> StreamingResponse:
    """Answer a health question from the trusted sources, streamed as Server-Sent Events."""
    if service is None:
        raise api_error(503, "service_unavailable", "The chat service is not available right now.")
    plan = await service.prepare(body)  # search or Claude failures raise here: a normal 502/504
    return StreamingResponse(
        plan.events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        background=BackgroundTask(plan.close),  # also closes the Claude stream if the client leaves early
    )
