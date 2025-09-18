from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import anyio
from sqlalchemy import select, insert
from sqlalchemy.ext.asyncio import AsyncEngine

from app.db.tables import samples_tcp, samples_dns, samples_http, aggregates_tcp_1m, aggregates_dns_1m, aggregates_http_1m


def _bucketize(ts: datetime, step: int) -> datetime:
    seconds = int(ts.timestamp())
    bucket = seconds - (seconds % step)
    return datetime.fromtimestamp(bucket, tz=timezone.utc)


def _quantiles(values: List[float], qs: List[float]) -> List[float | None]:
    if not values:
        return [None for _ in qs]
    data = sorted(values)
    out: List[float | None] = []
    for q in qs:
        idx = max(0, min(len(data) - 1, int(round(q * (len(data) - 1)))))
        out.append(data[idx])
    return out


async def _rollup_table(engine: AsyncEngine, src, key_fields: List[str], dest, since: datetime) -> None:
    async with engine.begin() as conn:
        rows = (await conn.execute(select(src).where(src.c.ts >= since))).mappings().all()
    buckets: Dict[tuple, Dict[str, Any]] = {}
    for r in rows:
        bucket = _bucketize(r["ts"], 60)
        key = tuple([bucket] + [r[k] for k in key_fields])
        entry = buckets.setdefault(key, {"lat": [], "ok": 0, "count": 0})
        entry["count"] += 1
        entry["ok"] += 1 if r["success"] else 0
        if r["success"]:
            entry["lat"].append(float(r["latency_ms"]))
    values = []
    for key, e in buckets.items():
        p50, p95 = _quantiles(e["lat"], [0.5, 0.95])
        avg = (sum(e["lat"]) / len(e["lat"])) if e["lat"] else None
        record = {
            "bucket": key[0],
            key_fields[0]: key[1],
        }
        if len(key_fields) > 1:
            record[key_fields[1]] = key[2]
        if len(key_fields) > 2:
            record[key_fields[2]] = key[3]
        record.update({
            "count": e["count"],
            "success_count": e["ok"],
            "p50": p50,
            "p95": p95,
            "avg": avg,
            "min": min(e["lat"]) if e["lat"] else None,
            "max": max(e["lat"]) if e["lat"] else None,
        })
        values.append(record)
    if values:
        async with engine.begin() as conn:
            await conn.execute(insert(dest).prefix_with("OR REPLACE").values(values))


async def run_maintenance(app, interval_sec: float = 60.0, retention_days: int = 14) -> None:
    engine: AsyncEngine = app.state.runtime.get("db_engine")
    if not engine:
        return
    while True:
        try:
            now = datetime.now(timezone.utc)
            # Rollups (compute for last 2 hours)
            window = now - timedelta(hours=2)
            await _rollup_table(engine, samples_tcp, ["host", "port"], aggregates_tcp_1m, window)
            await _rollup_table(engine, samples_dns, ["fqdn", "resolver"], aggregates_dns_1m, window)
            await _rollup_table(engine, samples_http, ["url", "method"], aggregates_http_1m, window)
            # Retention pruning
            from app.db.repo import prune_retention
            await prune_retention(engine, older_than=now - timedelta(days=retention_days))
        except Exception:
            # Best-effort maintenance
            pass
        await anyio.sleep(interval_sec)

