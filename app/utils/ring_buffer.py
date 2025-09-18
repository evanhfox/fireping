import asyncio
from collections import deque
from typing import Any, Deque, Dict, List, Optional


def create_ring_buffer(maxlen: int = 2000) -> Dict[str, Any]:
    buffer: Deque[Dict[str, Any]] = deque(maxlen=maxlen)
    lock = asyncio.Lock()

    async def append(item: Dict[str, Any]) -> None:
        async with lock:
            buffer.append(item)

    async def snapshot(limit: Optional[int] = None) -> List[Dict[str, Any]]:
        async with lock:
            data = list(buffer)
        if limit is not None:
            return data[-limit:]
        return data

    async def clear() -> None:
        async with lock:
            buffer.clear()

    return {
        "append": append,
        "snapshot": snapshot,
        "clear": clear,
    }

