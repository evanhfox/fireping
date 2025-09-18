from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncEngine

from app.db.tables import metadata, samples_tcp, samples_dns, targets_tcp, jobs_dns


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


async def init_schema(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(metadata.create_all)


async def insert_tcp_sample(engine: AsyncEngine, record: Dict[str, Any]) -> None:
    async with engine.begin() as conn:
        await conn.execute(insert(samples_tcp).values(record))


async def insert_dns_sample(engine: AsyncEngine, record: Dict[str, Any]) -> None:
    async with engine.begin() as conn:
        await conn.execute(insert(samples_dns).values(record))


async def fetch_tcp_samples_between(
    engine: AsyncEngine, start: datetime, end: datetime, host: Optional[str] = None
) -> List[Dict[str, Any]]:
    stmt = select(
        samples_tcp.c.ts,
        samples_tcp.c.host,
        samples_tcp.c.port,
        samples_tcp.c.latency_ms,
        samples_tcp.c.success,
    ).where(samples_tcp.c.ts >= start, samples_tcp.c.ts <= end)
    if host:
        stmt = stmt.where(samples_tcp.c.host == host)
    async with engine.begin() as conn:
        rows = (await conn.execute(stmt)).mappings().all()
    return [dict(r) for r in rows]


async def fetch_dns_samples_between(
    engine: AsyncEngine, start: datetime, end: datetime, fqdn: Optional[str] = None
) -> List[Dict[str, Any]]:
    stmt = select(
        samples_dns.c.ts,
        samples_dns.c.fqdn,
        samples_dns.c.record_type,
        samples_dns.c.resolver,
        samples_dns.c.latency_ms,
        samples_dns.c.rcode,
        samples_dns.c.success,
    ).where(samples_dns.c.ts >= start, samples_dns.c.ts <= end)
    if fqdn:
        stmt = stmt.where(samples_dns.c.fqdn == fqdn)
    async with engine.begin() as conn:
        rows = (await conn.execute(stmt)).mappings().all()
    return [dict(r) for r in rows]

