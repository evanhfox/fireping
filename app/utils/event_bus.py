import asyncio
from collections import deque
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Deque, Dict, List, MutableSet, Tuple


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_event_bus(max_recent_events: int = 500) -> Dict[str, Any]:
    subscribers: MutableSet[asyncio.Queue] = set()
    recent_events: Deque[Dict[str, Any]] = deque(maxlen=max_recent_events)
    lock = asyncio.Lock()

    async def publish(event: Dict[str, Any]) -> None:
        # Attach server timestamp if not present
        if "ts" not in event:
            event["ts"] = utc_now_iso()
        async with lock:
            recent_events.append(event)
            queues: List[asyncio.Queue] = list(subscribers)
        for queue in queues:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                # Drop if consumer is too slow
                pass

    async def subscribe(with_replay: bool = True) -> AsyncIterator[Dict[str, Any]]:
        queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
        async with lock:
            subscribers.add(queue)
            snapshot: List[Dict[str, Any]] = list(recent_events) if with_replay else []
        for event in snapshot:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                break
        try:
            while True:
                item = await queue.get()
                yield item
        finally:
            async with lock:
                subscribers.discard(queue)

    return {
        "publish": publish,
        "subscribe": subscribe,
    }

