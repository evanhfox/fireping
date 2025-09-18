from typing import Optional
import time

import httpx
from fastapi import APIRouter
from pydantic import BaseModel, Field


router = APIRouter(prefix="/api/http", tags=["http"])


class HttpProbeRequest(BaseModel):
    url: str
    timeout_sec: float = Field(5.0, ge=0.5, le=30.0)
    method: str = Field("GET")


class HttpProbeResponse(BaseModel):
    url: str
    method: str
    status_code: Optional[int]
    latency_ms: float
    tls_ms: Optional[float] = None
    success: bool
    error: Optional[str] = None


async def probe_http(url: str, method: str, timeout_sec: float) -> HttpProbeResponse:
    start = time.perf_counter()
    try:
        async with httpx.AsyncClient(http2=True, timeout=timeout_sec) as client:
            resp = await client.request(method, url)
        latency_ms = (time.perf_counter() - start) * 1000.0
        ok = 200 <= resp.status_code < 400
        return HttpProbeResponse(url=url, method=method, status_code=resp.status_code, latency_ms=latency_ms, success=ok)
    except Exception as exc:
        latency_ms = (time.perf_counter() - start) * 1000.0
        return HttpProbeResponse(url=url, method=method, status_code=None, latency_ms=latency_ms, success=False, error=str(exc))


@router.post("/probe", response_model=HttpProbeResponse)
async def http_probe(payload: HttpProbeRequest) -> HttpProbeResponse:
    return await probe_http(payload.url, payload.method, payload.timeout_sec)

