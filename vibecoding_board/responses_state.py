from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(slots=True, frozen=True)
class ResponseAffinityRecord:
    response_id: str
    provider_name: str
    southbound_transport: str
    created_at: datetime


class ResponsesStateStore:
    def __init__(self, capacity: int = 2048) -> None:
        self.capacity = capacity
        self._entries: dict[str, ResponseAffinityRecord] = {}
        self._order: deque[tuple[str, datetime]] = deque()
        self._lock = asyncio.Lock()

    async def bind_response(
        self,
        response_id: str,
        *,
        provider_name: str,
        southbound_transport: str,
    ) -> ResponseAffinityRecord:
        record = ResponseAffinityRecord(
            response_id=response_id,
            provider_name=provider_name,
            southbound_transport=southbound_transport,
            created_at=datetime.now(UTC),
        )
        async with self._lock:
            self._entries[response_id] = record
            self._order.append((response_id, record.created_at))
            self._evict_locked()
        return record

    async def lookup_response(self, response_id: str) -> ResponseAffinityRecord | None:
        async with self._lock:
            return self._entries.get(response_id)

    async def rename_provider(self, old_name: str, new_name: str) -> int:
        migrated = 0
        async with self._lock:
            for response_id, record in list(self._entries.items()):
                if record.provider_name != old_name:
                    continue
                self._entries[response_id] = ResponseAffinityRecord(
                    response_id=record.response_id,
                    provider_name=new_name,
                    southbound_transport=record.southbound_transport,
                    created_at=record.created_at,
                )
                migrated += 1
        return migrated

    def _evict_locked(self) -> None:
        while len(self._entries) > self.capacity:
            response_id, created_at = self._order.popleft()
            current = self._entries.get(response_id)
            if current is None or current.created_at != created_at:
                continue
            self._entries.pop(response_id, None)
