from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field


router = APIRouter(prefix="/api/config", tags=["config"])


class TcpTarget(BaseModel):
    id: str
    host: str
    port: int = 443
    interval_sec: float = Field(5.0, ge=0.5, le=60.0)


class DnsJob(BaseModel):
    id: str
    fqdn: str
    record_type: str = "A"
    resolvers: Optional[List[str]] = None
    interval_sec: float = Field(5.0, ge=0.5, le=60.0)


class ConfigState(BaseModel):
    version: int
    tcp: List[TcpTarget]
    dns: List[DnsJob]


def _get_config(app) -> Dict[str, Any]:
    return app.state.runtime.setdefault("config", {
        "version": 1,
        "tcp": [
            {"id": "cf-1.1.1.1", "host": "1.1.1.1", "port": 443, "interval_sec": 5.0},
            {"id": "ggl-8.8.8.8", "host": "8.8.8.8", "port": 443, "interval_sec": 5.0},
        ],
        "dns": [
            {"id": "dns-google", "fqdn": "google.com", "record_type": "A", "resolvers": ["1.1.1.1", "8.8.8.8"], "interval_sec": 5.0},
        ],
    })


@router.get("/state", response_model=ConfigState)
async def get_state(request: Request) -> ConfigState:
    cfg = _get_config(request.app)
    return ConfigState(version=cfg["version"], tcp=cfg["tcp"], dns=cfg["dns"])


@router.post("/tcp", response_model=ConfigState)
async def add_tcp(request: Request, target: TcpTarget) -> ConfigState:
    cfg = _get_config(request.app)
    if any(t["id"] == target.id for t in cfg["tcp"]):
        raise HTTPException(status_code=409, detail="TCP target id exists")
    cfg["tcp"].append(target.model_dump())
    cfg["version"] += 1
    return ConfigState(version=cfg["version"], tcp=cfg["tcp"], dns=cfg["dns"])


@router.delete("/tcp/{target_id}", response_model=ConfigState)
async def delete_tcp(request: Request, target_id: str) -> ConfigState:
    cfg = _get_config(request.app)
    before = len(cfg["tcp"])
    cfg["tcp"] = [t for t in cfg["tcp"] if t["id"] != target_id]
    if len(cfg["tcp"]) == before:
        raise HTTPException(status_code=404, detail="Not found")
    cfg["version"] += 1
    return ConfigState(version=cfg["version"], tcp=cfg["tcp"], dns=cfg["dns"])


@router.post("/dns", response_model=ConfigState)
async def add_dns(request: Request, job: DnsJob) -> ConfigState:
    cfg = _get_config(request.app)
    if any(j["id"] == job.id for j in cfg["dns"]):
        raise HTTPException(status_code=409, detail="DNS job id exists")
    cfg["dns"].append(job.model_dump())
    cfg["version"] += 1
    return ConfigState(version=cfg["version"], tcp=cfg["tcp"], dns=cfg["dns"])


@router.delete("/dns/{job_id}", response_model=ConfigState)
async def delete_dns(request: Request, job_id: str) -> ConfigState:
    cfg = _get_config(request.app)
    before = len(cfg["dns"])
    cfg["dns"] = [j for j in cfg["dns"] if j["id"] != job_id]
    if len(cfg["dns"]) == before:
        raise HTTPException(status_code=404, detail="Not found")
    cfg["version"] += 1
    return ConfigState(version=cfg["version"], tcp=cfg["tcp"], dns=cfg["dns"])

