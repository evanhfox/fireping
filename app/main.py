from contextlib import asynccontextmanager
from typing import AsyncIterator, Dict, Any

from fastapi import FastAPI
from app.routers.dns import router as dns_router
from app.routers.ping import router as ping_router
from app.routers.stream import router as stream_router
from app.utils.event_bus import create_event_bus
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware


def create_app_state() -> Dict[str, Any]:
    return {
        "version": "0.1.0",
        "in_memory_store": {
            "started": False,
        },
        "event_bus": create_event_bus(),
    }


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.runtime = create_app_state()
    app.state.runtime["in_memory_store"]["started"] = True
    try:
        yield
    finally:
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

