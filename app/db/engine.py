import os
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy import text


def _default_database_url() -> str:
    path = os.environ.get("DATABASE_FILE", os.path.join("data", "app.db"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return f"sqlite+aiosqlite:///{path}"


def get_database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    return _default_database_url()


async def create_engine_and_init() -> AsyncEngine:
    url = get_database_url()
    engine: AsyncEngine = create_async_engine(url, echo=False, pool_pre_ping=True)
    async with engine.begin() as conn:
        # SQLite tuning: WAL mode and reasonable sync settings
        if url.startswith("sqlite+"):
            await conn.execute(text("PRAGMA journal_mode=WAL"))
            await conn.execute(text("PRAGMA synchronous=NORMAL"))
            await conn.execute(text("PRAGMA temp_store=MEMORY"))
    return engine

