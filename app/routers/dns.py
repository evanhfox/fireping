from typing import List, Optional
import time

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

try:
    import dns.resolver  # type: ignore
except Exception as exc:  # pragma: no cover
    dns = None


router = APIRouter(prefix="/api/dns", tags=["dns"])


class DnsQueryRequest(BaseModel):
    fqdn: str = Field(..., description="Fully qualified domain name to resolve")
    record_type: str = Field("A", description="DNS record type, e.g., A, AAAA, TXT")
    resolvers: Optional[List[str]] = Field(
        default=None, description="List of DNS resolver IPs; use system default if omitted"
    )
    timeout_sec: float = Field(2.0, ge=0.1, le=10.0)


class DnsAnswer(BaseModel):
    value: str


class DnsQueryResponse(BaseModel):
    fqdn: str
    record_type: str
    resolver: Optional[str]
    latency_ms: float
    rcode: Optional[str]
    success: bool
    answers: List[DnsAnswer]


async def resolve_dns(request: DnsQueryRequest) -> DnsQueryResponse:
    if dns is None:
        raise HTTPException(status_code=500, detail="dnspython is not installed")

    resolver = dns.resolver.Resolver()  # type: ignore[attr-defined]
    if request.resolvers:
        resolver.nameservers = request.resolvers
    resolver.lifetime = request.timeout_sec
    resolver.timeout = request.timeout_sec

    start = time.perf_counter()
    try:
        answer = await _resolve_async(resolver, request.fqdn, request.record_type)
    except dns.resolver.NXDOMAIN:  # type: ignore[attr-defined]
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        return DnsQueryResponse(
            fqdn=request.fqdn,
            record_type=request.record_type,
            resolver=resolver.nameservers[0] if resolver.nameservers else None,
            latency_ms=elapsed_ms,
            rcode="NXDOMAIN",
            success=False,
            answers=[],
        )
    except dns.resolver.Timeout:  # type: ignore[attr-defined]
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        return DnsQueryResponse(
            fqdn=request.fqdn,
            record_type=request.record_type,
            resolver=resolver.nameservers[0] if resolver.nameservers else None,
            latency_ms=elapsed_ms,
            rcode="TIMEOUT",
            success=False,
            answers=[],
        )
    except Exception as exc:  # pragma: no cover
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        raise HTTPException(status_code=500, detail=f"DNS error: {exc}") from exc

    elapsed_ms = (time.perf_counter() - start) * 1000.0
    records = [DnsAnswer(value=str(rdata)) for rdata in answer]
    return DnsQueryResponse(
        fqdn=request.fqdn,
        record_type=request.record_type,
        resolver=answer.response.nameserver if hasattr(answer.response, "nameserver") else None,  # type: ignore[attr-defined]
        latency_ms=elapsed_ms,
        rcode="NOERROR",
        success=True,
        answers=records,
    )


async def _resolve_async(resolver: "dns.resolver.Resolver", fqdn: str, record_type: str):  # type: ignore[name-defined]
    # dnspython is sync; run in thread to avoid blocking event loop
    import anyio

    def _blocking_query():
        return resolver.resolve(fqdn, record_type)

    return await anyio.to_thread.run_sync(_blocking_query)


@router.post("/query", response_model=DnsQueryResponse)
async def dns_query(payload: DnsQueryRequest, request: Request) -> DnsQueryResponse:
    result = await resolve_dns(payload)
    bus = request.app.state.runtime.get("event_bus")
    publish = bus["publish"]
    ring = request.app.state.runtime.get("ring_buffer")
    await publish({
        "type": "dns_sample",
        "data": result.model_dump(),
    })
    await ring["append"]({
        "type": "dns_sample",
        "data": result.model_dump(),
    })
    return result

