import random
import time
from typing import Any, Dict, List
from datetime import datetime, timezone

import anyio
from fastapi import HTTPException

from app.routers.ping import tcp_connect_latency, TcpPingResponse
from app.routers.dns import resolve_dns, DnsQueryRequest, DnsQueryResponse
from app.db.repo import insert_tcp_sample, insert_dns_sample


def _jitter_seconds(base: float, pct: float = 0.15) -> float:
    delta = base * pct
    return base + random.uniform(-delta, +delta)


def default_ping_targets() -> List[Dict[str, Any]]:
    return [
        {"host": "1.1.1.1", "port": 443, "interval_sec": 5.0},
        {"host": "8.8.8.8", "port": 443, "interval_sec": 5.0},
        {"host": "google.com", "port": 443, "interval_sec": 5.0},
    ]


def default_dns_jobs() -> List[Dict[str, Any]]:
    return [
        {"fqdn": "google.com", "record_type": "A", "resolvers": ["1.1.1.1", "8.8.8.8"], "interval_sec": 5.0},
        {"fqdn": "cloudflare.com", "record_type": "A", "resolvers": ["1.1.1.1", "8.8.8.8"], "interval_sec": 5.0},
    ]


async def _publish_and_buffer(app, event_type: str, data: Dict[str, Any]) -> None:
    bus = app.state.runtime.get("event_bus")
    ring = app.state.runtime.get("ring_buffer")
    await bus["publish"]({"type": event_type, "data": data})
    await ring["append"]({"type": event_type, "data": data})


async def _run_ping_loop(app, host: str, port: int, interval_sec: float) -> None:
    while True:
        started = time.perf_counter()
        result: TcpPingResponse = await tcp_connect_latency(host, port, timeout_sec=min(2.0, interval_sec))
        data = result.model_dump()
        await _publish_and_buffer(app, "tcp_sample", data)
        engine = app.state.runtime.get("db_engine")
        if engine:
            record = {
                "ts": datetime.now(timezone.utc),
                "target_id": None,
                "host": data["host"],
                "port": data["port"],
                "latency_ms": data["latency_ms"],
                "success": data["success"],
            }
            await insert_tcp_sample(engine, record)
        elapsed = time.perf_counter() - started
        sleep_s = max(0.05, _jitter_seconds(interval_sec) - elapsed)
        await anyio.sleep(sleep_s)


async def _run_dns_loop(app, fqdn: str, record_type: str, resolvers: List[str], interval_sec: float) -> None:
    while True:
        started = time.perf_counter()
        try:
            req = DnsQueryRequest(fqdn=fqdn, record_type=record_type, resolvers=resolvers)
            result: DnsQueryResponse = await resolve_dns(req)
        except HTTPException as exc:
            # Map to a standard error response
            result = DnsQueryResponse(
                fqdn=fqdn,
                record_type=record_type,
                resolver=resolvers[0] if resolvers else None,
                latency_ms=0.0,
                rcode="ERROR",
                success=False,
                answers=[],
            )
        data = result.model_dump()
        await _publish_and_buffer(app, "dns_sample", data)
        engine = app.state.runtime.get("db_engine")
        if engine:
            record = {
                "ts": datetime.now(timezone.utc),
                "job_id": None,
                "fqdn": data["fqdn"],
                "record_type": data["record_type"],
                "resolver": data.get("resolver"),
                "latency_ms": data["latency_ms"],
                "rcode": data.get("rcode"),
                "success": data["success"],
            }
            await insert_dns_sample(engine, record)
        elapsed = time.perf_counter() - started
        sleep_s = max(0.05, _jitter_seconds(interval_sec) - elapsed)
        await anyio.sleep(sleep_s)


async def start_scheduler(app, task_group: anyio.abc.TaskGroup) -> None:
    # Watch in-memory config version and restart workers on change
    last_version: int | None = None
    while True:
        cfg = app.state.runtime.setdefault("config", {
            "version": 1,
            "tcp": default_ping_targets(),
            "dns": default_dns_jobs(),
        })
        if cfg["version"] != last_version:
            last_version = cfg["version"]
            # Cancel previous child tasks by restarting our child group
            async with anyio.create_task_group() as child:
                for target in cfg.get("tcp", []):
                    child.start_soon(_run_ping_loop, app, target["host"], target["port"], float(target["interval_sec"]))
                for job in cfg.get("dns", []):
                    child.start_soon(
                        _run_dns_loop,
                        app,
                        job["fqdn"],
                        job.get("record_type", "A"),
                        list(job.get("resolvers", [])),
                        float(job["interval_sec"]),
                    )
                # Sleep until config changes
                while True:
                    await anyio.sleep(1.0)
                    current = app.state.runtime.get("config", cfg)
                    if current.get("version") != last_version:
                        child.cancel_scope.cancel()
                        break


