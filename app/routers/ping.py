from typing import Optional
import socket
import time

import anyio
from fastapi import APIRouter, Request
from pydantic import BaseModel, Field


router = APIRouter(prefix="/api/ping", tags=["ping"])


class TcpPingRequest(BaseModel):
    host: str = Field(..., description="Hostname or IP to connect to")
    port: int = Field(443, ge=1, le=65535)
    timeout_sec: float = Field(2.0, ge=0.1, le=10.0)


class TcpPingResponse(BaseModel):
    host: str
    port: int
    latency_ms: float
    success: bool
    error: Optional[str] = None


async def tcp_connect_latency(host: str, port: int, timeout_sec: float) -> TcpPingResponse:
    start = time.perf_counter()
    try:
        await anyio.wait_for(_connect(host, port), timeout=timeout_sec)
    except Exception as exc:
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        return TcpPingResponse(host=host, port=port, latency_ms=elapsed_ms, success=False, error=str(exc))

    elapsed_ms = (time.perf_counter() - start) * 1000.0
    return TcpPingResponse(host=host, port=port, latency_ms=elapsed_ms, success=True)


async def _connect(host: str, port: int) -> None:
    family = socket.AF_UNSPEC
    addrinfos = await anyio.to_thread.run_sync(socket.getaddrinfo, host, port, family, socket.SOCK_STREAM)
    last_exc: Optional[BaseException] = None
    for family, socktype, proto, _, sockaddr in addrinfos:
        try:
            stream = await anyio.connect_tcp(sockaddr[0], sockaddr[1])
            await stream.aclose()
            return
        except BaseException as exc:  # try next addr
            last_exc = exc
            continue
    if last_exc is None:
        raise RuntimeError("No addresses resolved")
    raise last_exc


@router.post("/tcp", response_model=TcpPingResponse)
async def ping_tcp(payload: TcpPingRequest, request: Request) -> TcpPingResponse:
    result = await tcp_connect_latency(payload.host, payload.port, payload.timeout_sec)
    bus = request.app.state.runtime.get("event_bus")
    publish = bus["publish"]
    await publish({
        "type": "tcp_sample",
        "data": result.model_dump(),
    })
    return result

