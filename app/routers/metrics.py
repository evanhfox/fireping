from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field
from app.db.repo import fetch_tcp_samples_between, fetch_dns_samples_between
from sqlalchemy import select
from app.db.tables import aggregates_tcp_1m, aggregates_dns_1m, aggregates_http_1m
from sqlalchemy.ext.asyncio import AsyncEngine


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


class RollupPoint(BaseModel):
    bucket: datetime
    count: int
    success_rate: float
    p50: Optional[float] = None
    p95: Optional[float] = None
    avg: Optional[float] = None


class RollupResponse(BaseModel):
    points: List[RollupPoint]


def _bucketize(ts: datetime, step: int) -> datetime:
    seconds = int(ts.timestamp())
    bucket = seconds - (seconds % step)
    return datetime.fromtimestamp(bucket, tz=timezone.utc)


def _quantiles(values: List[float], qs: List[float]) -> List[Optional[float]]:
    if not values:
        return [None for _ in qs]
    data = sorted(values)
    out: List[Optional[float]] = []
    for q in qs:
        idx = max(0, min(len(data) - 1, int(round(q * (len(data) - 1)))))
        out.append(data[idx])
    return out


@router.get("/tcp_rollup", response_model=RollupResponse)
async def tcp_rollup(
    request: Request,
    minutes: int = Query(60, ge=1, le=1440),
    step_sec: int = Query(60, ge=15, le=3600),
    host: Optional[str] = None,
) -> RollupResponse:
    end = datetime.now(timezone.utc)
    start = end - timedelta(minutes=minutes)
    engine = request.app.state.runtime.get("db_engine")
    rows = await fetch_tcp_samples_between(engine, start, end, host=host)
    buckets: Dict[datetime, Dict[str, Any]] = {}
    for r in rows:
        b = _bucketize(r["ts"], step_sec)
        entry = buckets.setdefault(b, {"lat": [], "ok": 0, "count": 0})
        entry["count"] += 1
        entry["ok"] += 1 if r["success"] else 0
        if r["success"]:
            entry["lat"].append(float(r["latency_ms"]))
    points: List[RollupPoint] = []
    for b in sorted(buckets.keys()):
        e = buckets[b]
        p50, p95 = _quantiles(e["lat"], [0.5, 0.95])
        avg = (sum(e["lat"]) / len(e["lat"])) if e["lat"] else None
        sr = e["ok"] / e["count"] if e["count"] else 0.0
        points.append(RollupPoint(bucket=b, count=e["count"], success_rate=sr, p50=p50, p95=p95, avg=avg))
    return RollupResponse(points=points)


@router.get("/summary")
async def summary(request: Request) -> Dict[str, Any]:
    engine: AsyncEngine = request.app.state.runtime.get("db_engine")
    end = datetime.now(timezone.utc)
    start = end - timedelta(minutes=10)
    async def _count(table):
        async with engine.begin() as conn:
            rows = (await conn.execute(select(table.c.count).where(table.c.bucket >= start))).all()
        return sum(r[0] for r in rows)
    tcp = await _count(aggregates_tcp_1m)
    dns = await _count(aggregates_dns_1m)
    http = await _count(aggregates_http_1m)
    return {"last_10m_samples": {"tcp": tcp, "dns": dns, "http": http}}


@router.get("/dns_rollup", response_model=RollupResponse)
async def dns_rollup(
    request: Request,
    minutes: int = Query(60, ge=1, le=1440),
    step_sec: int = Query(60, ge=15, le=3600),
    fqdn: Optional[str] = None,
) -> RollupResponse:
    end = datetime.now(timezone.utc)
    start = end - timedelta(minutes=minutes)
    engine = request.app.state.runtime.get("db_engine")
    rows = await fetch_dns_samples_between(engine, start, end, fqdn=fqdn)
    buckets: Dict[datetime, Dict[str, Any]] = {}
    for r in rows:
        b = _bucketize(r["ts"], step_sec)
        entry = buckets.setdefault(b, {"lat": [], "ok": 0, "count": 0})
        entry["count"] += 1
        entry["ok"] += 1 if r["success"] else 0
        if r["success"]:
            entry["lat"].append(float(r["latency_ms"]))
    points: List[RollupPoint] = []
    for b in sorted(buckets.keys()):
        e = buckets[b]
        p50, p95 = _quantiles(e["lat"], [0.5, 0.95])
        avg = (sum(e["lat"]) / len(e["lat"])) if e["lat"] else None
        sr = e["ok"] / e["count"] if e["count"] else 0.0
        points.append(RollupPoint(bucket=b, count=e["count"], success_rate=sr, p50=p50, p95=p95, avg=avg))
    return RollupResponse(points=points)

