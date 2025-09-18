from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel


router = APIRouter(prefix="/api/metrics", tags=["metrics"])


class Sample(BaseModel):
    type: str
    data: Dict[str, Any]
    ts: Optional[str] = None


class SamplesResponse(BaseModel):
    items: List[Sample]


@router.get("/recent", response_model=SamplesResponse)
async def recent(request: Request, limit: int = Query(500, ge=1, le=5000)) -> SamplesResponse:
    ring = request.app.state.runtime.get("ring_buffer")
    snapshot = await ring["snapshot"](limit)
    items: List[Sample] = [Sample(**entry) for entry in snapshot]
    return SamplesResponse(items=items)

