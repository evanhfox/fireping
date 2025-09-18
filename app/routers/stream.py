from typing import AsyncIterator, Callable, Dict, Any
import json

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse


router = APIRouter(prefix="/api/stream", tags=["stream"])


async def sse_event_generator(subscribe: Callable[..., AsyncIterator[Dict[str, Any]]]) -> AsyncIterator[bytes]:
    async for event in subscribe(with_replay=True):
        payload = json.dumps(event, separators=(",", ":"))
        line = f"data: {payload}\n\n"
        yield line.encode("utf-8")


@router.get("/events")
async def events(request: Request) -> StreamingResponse:
    bus = request.app.state.runtime.get("event_bus")
    subscribe = bus["subscribe"]
    generator = sse_event_generator(subscribe)
    return StreamingResponse(generator, media_type="text/event-stream")

