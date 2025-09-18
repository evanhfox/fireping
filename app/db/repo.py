from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import insert
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

