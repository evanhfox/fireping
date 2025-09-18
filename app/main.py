from contextlib import asynccontextmanager
from typing import AsyncIterator, Dict, Any

from fastapi import FastAPI
from app.routers.dns import router as dns_router
from app.routers.ping import router as ping_router
from app.routers.stream import router as stream_router
from app.routers.metrics import router as metrics_router
from app.routers.config import router as config_router
from app.routers.http_probe import router as http_router
from app.utils.event_bus import create_event_bus
from app.utils.ring_buffer import create_ring_buffer
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware
from starlette.staticfiles import StaticFiles
from app.services.scheduler import run_scheduler
from app.db.engine import create_engine_and_init
from app.db.repo import init_schema
import anyio
from app.middleware.auth import BasicAuthMiddleware


def create_app_state() -> Dict[str, Any]:
    return {
        "version": "0.1.0",
        "in_memory_store": {
            "started": False,
        },
        "event_bus": create_event_bus(),
        "ring_buffer": create_ring_buffer(),
    }


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.runtime = create_app_state()
    app.state.runtime["in_memory_store"]["started"] = True
    engine = await create_engine_and_init()
    await init_schema(engine)
    app.state.runtime["db_engine"] = engine
    async with anyio.create_task_group() as tg:
        tg.start_soon(run_scheduler, app)
        try:
            yield
        finally:
            tg.cancel_scope.cancel()
    app.state.runtime["in_memory_store"]["started"] = False


app = FastAPI(lifespan=lifespan)

# CORS can be tightened later; for now allow same-origin and localhost dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(BasicAuthMiddleware)


@app.get("/healthz")
async def healthz() -> JSONResponse:
    runtime = getattr(app.state, "runtime", {})
    body = {
        "ok": True,
        "version": runtime.get("version"),
        "started": runtime.get("in_memory_store", {}).get("started", False),
    }
    return JSONResponse(body)


app.include_router(dns_router)
app.include_router(ping_router)
app.include_router(stream_router)
app.include_router(metrics_router)
app.include_router(config_router)
app.include_router(http_router)

# Serve static frontend (fallback index.html)
app.mount("/", StaticFiles(directory="app/static", html=True), name="static")

