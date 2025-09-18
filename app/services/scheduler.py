import random
import time
from typing import Any, Dict, List

import anyio
from fastapi import FastAPI

from app.routers.ping import tcp_connect_latency
from app.routers.dns import DnsQueryRequest, resolve_dns


def default_targets() -> Dict[str, Any]:
    return {
        "tcp": [
            {"host": "1.1.1.1", "port": 443, "interval_sec": 5.0},
            {"host": "8.8.8.8", "port": 443, "interval_sec": 5.0},
        ],
        "dns": [
            {"fqdn": "example.com", "record_type": "A", "interval_sec": 5.0, "resolvers": ["1.1.1.1"]},
            {"fqdn": "google.com", "record_type": "A", "interval_sec": 5.0, "resolvers": ["8.8.8.8"]},
        ],
    }


async def _jittered_sleep(base_seconds: float) -> None:
    jitter = base_seconds * 0.1
    delay = base_seconds + random.uniform(-jitter, jitter)
    await anyio.sleep(max(0.5, delay))


async def _run_tcp_worker(app: FastAPI, target: Dict[str, Any]) -> None:
    host: str = target["host"]
    port: int = target.get("port", 443)
    interval: float = float(target.get("interval_sec", 5.0))
    bus = app.state.runtime["event_bus"]
    ring = app.state.runtime["ring_buffer"]
    publish = bus["publish"]
    while True:
        start = time.perf_counter()
        result = await tcp_connect_latency(host, port, timeout_sec=min(2.0, interval))
        event = {"type": "tcp_sample", "data": result.model_dump()}
        await publish(event)
        await ring["append"](event)
        elapsed = time.perf_counter() - start
        remaining = max(0.2, interval - elapsed)
        await _jittered_sleep(remaining)


async def _run_dns_worker(app: FastAPI, config: Dict[str, Any]) -> None:
    interval: float = float(config.get("interval_sec", 5.0))
    bus = app.state.runtime["event_bus"]
    ring = app.state.runtime["ring_buffer"]
    publish = bus["publish"]
    request = DnsQueryRequest(
        fqdn=config["fqdn"],
        record_type=config.get("record_type", "A"),
        resolvers=config.get("resolvers"),
        timeout_sec=min(2.0, interval),
    )
    while True:
        start = time.perf_counter()
        result = await resolve_dns(request)
        event = {"type": "dns_sample", "data": result.model_dump()}
        await publish(event)
        await ring["append"](event)
        elapsed = time.perf_counter() - start
        remaining = max(0.2, interval - elapsed)
        await _jittered_sleep(remaining)


async def run_scheduler(app: FastAPI) -> None:
    cfg = default_targets()
    async with anyio.create_task_group() as tg:
        for target in cfg["tcp"]:
            tg.start_soon(_run_tcp_worker, app, target)
        for config in cfg["dns"]:
            tg.start_soon(_run_dns_worker, app, config)

