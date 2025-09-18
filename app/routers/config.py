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
    http: List[Dict[str, Any]] = []


def _get_config(app) -> Dict[str, Any]:
    cfg = app.state.runtime.setdefault("config", {
        "version": 1,
        "tcp": [
            {"id": "cf-1.1.1.1", "host": "1.1.1.1", "port": 443, "interval_sec": 5.0},
            {"id": "ggl-8.8.8.8", "host": "8.8.8.8", "port": 443, "interval_sec": 5.0},
        ],
        "dns": [
            {"id": "dns-google", "fqdn": "google.com", "record_type": "A", "resolvers": ["1.1.1.1", "8.8.8.8"], "interval_sec": 5.0},
        ],
        "http": [
            {"id": "http-google", "url": "https://www.google.com", "method": "GET", "interval_sec": 10.0},
        ],
    })
    # Normalize: assign IDs if missing (scheduler defaults may omit them)
    tcp = []
    for i, t in enumerate(cfg.get("tcp", [])):
        if "id" not in t or not t["id"]:
            t = dict(t)
            t["id"] = f"tcp-{t.get('host','host')}-{t.get('port','0')}-{i}"
        tcp.append(t)
    dns = []
    for i, d in enumerate(cfg.get("dns", [])):
        if "id" not in d or not d["id"]:
            d = dict(d)
            d["id"] = f"dns-{d.get('fqdn','name')}-{i}"
        dns.append(d)
    http = []
    for i, h in enumerate(cfg.get("http", [])):
        if "id" not in h or not h["id"]:
            h = dict(h)
            h["id"] = f"http-{h.get('method','GET')}-{i}"
        http.append(h)
    cfg["tcp"], cfg["dns"], cfg["http"] = tcp, dns, http
    return cfg


@router.get("/state", response_model=ConfigState)
async def get_state(request: Request) -> ConfigState:
    cfg = _get_config(request.app)
    # Validate/normalize to model instances to guarantee IDs exist
    tcp = [TcpTarget(**t) for t in cfg.get("tcp", [])]
    dns = [DnsJob(**d) for d in cfg.get("dns", [])]
    http = cfg.get("http", [])
    return ConfigState(version=cfg["version"], tcp=tcp, dns=dns, http=http)


@router.post("/tcp", response_model=ConfigState)
async def add_tcp(request: Request, target: TcpTarget) -> ConfigState:
    cfg = _get_config(request.app)
    if any(t["id"] == target.id for t in cfg["tcp"]):
        raise HTTPException(status_code=409, detail="TCP target id exists")
    cfg["tcp"].append(target.model_dump())
    cfg["version"] += 1
    return ConfigState(version=cfg["version"], tcp=cfg["tcp"], dns=cfg["dns"], http=cfg.get("http", []))


@router.delete("/tcp/{target_id}", response_model=ConfigState)
async def delete_tcp(request: Request, target_id: str) -> ConfigState:
    cfg = _get_config(request.app)
    before = len(cfg["tcp"])
    cfg["tcp"] = [t for t in cfg["tcp"] if t["id"] != target_id]
    if len(cfg["tcp"]) == before:
        raise HTTPException(status_code=404, detail="Not found")
    cfg["version"] += 1
    return ConfigState(version=cfg["version"], tcp=cfg["tcp"], dns=cfg["dns"], http=cfg.get("http", []))


@router.post("/dns", response_model=ConfigState)
async def add_dns(request: Request, job: DnsJob) -> ConfigState:
    cfg = _get_config(request.app)
    if any(j["id"] == job.id for j in cfg["dns"]):
        raise HTTPException(status_code=409, detail="DNS job id exists")
    cfg["dns"].append(job.model_dump())
    cfg["version"] += 1
    return ConfigState(version=cfg["version"], tcp=cfg["tcp"], dns=cfg["dns"], http=cfg.get("http", []))


@router.delete("/dns/{job_id}", response_model=ConfigState)
async def delete_dns(request: Request, job_id: str) -> ConfigState:
    cfg = _get_config(request.app)
    before = len(cfg["dns"])
    cfg["dns"] = [j for j in cfg["dns"] if j["id"] != job_id]
    if len(cfg["dns"]) == before:
        raise HTTPException(status_code=404, detail="Not found")
    cfg["version"] += 1
    return ConfigState(version=cfg["version"], tcp=cfg["tcp"], dns=cfg["dns"], http=cfg.get("http", []))


class HttpJob(BaseModel):
    id: str
    url: str
    method: str = "GET"
    interval_sec: float = Field(10.0, ge=0.5, le=120.0)


@router.post("/http", response_model=ConfigState)
async def add_http(request: Request, job: HttpJob) -> ConfigState:
    cfg = _get_config(request.app)
    http = cfg.setdefault("http", [])
    if any(j["id"] == job.id for j in http):
        raise HTTPException(status_code=409, detail="HTTP job id exists")
    http.append(job.model_dump())
    cfg["version"] += 1
    return ConfigState(version=cfg["version"], tcp=cfg["tcp"], dns=cfg["dns"], http=http)


@router.delete("/http/{job_id}", response_model=ConfigState)
async def delete_http(request: Request, job_id: str) -> ConfigState:
    cfg = _get_config(request.app)
    http = cfg.setdefault("http", [])
    before = len(http)
    cfg["http"] = [j for j in http if j["id"] != job_id]
    if len(cfg["http"]) == before:
        raise HTTPException(status_code=404, detail="Not found")
    cfg["version"] += 1
    return ConfigState(version=cfg["version"], tcp=cfg["tcp"], dns=cfg["dns"], http=cfg["http"])

