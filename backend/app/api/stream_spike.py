"""Streaming compatibility spike (temporary).

Emits timed SSE events so we can see whether API Gateway + Lambda Web Adapter deliver them
incrementally. Removed once the real /v1/chat streaming endpoint exists (T11).
"""
import asyncio
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from app.api.identity import gateway_identity
from app.api.sse import sse

router = APIRouter()


async def _events(count: int, delay_ms: int) -> AsyncIterator[str]:
    for index in range(count):
        yield sse("token", {"index": index, "text": f"chunk {index}"})
        await asyncio.sleep(delay_ms / 1000)
    yield sse("done", {})


@router.get("/stream-spike")
async def stream_spike(
    count: int = Query(default=5, ge=1, le=50),
    delay_ms: int = Query(default=500, ge=0, le=2000),
    _identity: dict = Depends(gateway_identity),
) -> StreamingResponse:
    return StreamingResponse(
        _events(count, delay_ms),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
