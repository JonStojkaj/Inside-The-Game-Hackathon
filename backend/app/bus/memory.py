"""M3 event bus, in-memory implementation (Azure Event Hubs implements the same interface)."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import AsyncIterator
from typing import Any, Protocol

CLOSED = object()  # sentinel published on close()


class EventBus(Protocol):
    async def publish(self, topic: str, message: Any) -> None: ...
    def subscribe(self, topic: str) -> AsyncIterator[Any]: ...
    async def close(self) -> None: ...


class InMemoryBus:
    def __init__(self, maxsize: int = 10_000) -> None:
        self._queues: dict[str, list[asyncio.Queue]] = defaultdict(list)
        self._maxsize = maxsize

    async def publish(self, topic: str, message: Any) -> None:
        for queue in self._queues[topic]:
            await queue.put(message)

    def subscribe(self, topic: str) -> AsyncIterator[Any]:
        # register now, so nothing published before the first read is lost
        queue: asyncio.Queue = asyncio.Queue(self._maxsize)
        self._queues[topic].append(queue)
        return self._drain(topic, queue)

    async def _drain(self, topic: str, queue: asyncio.Queue) -> AsyncIterator[Any]:
        try:
            while (message := await queue.get()) is not CLOSED:
                yield message
        finally:
            self._queues[topic].remove(queue)

    async def close(self) -> None:
        for queues in self._queues.values():
            for queue in queues:
                await queue.put(CLOSED)
