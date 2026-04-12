from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime
from statistics import mean
import uuid


@dataclass(slots=True, frozen=True)
class AttemptLogEntry:
    provider: str
    url: str
    outcome: str
    retryable: bool
    status_code: int | None
    provider_attempt: int
    next_action: str


@dataclass(slots=True, frozen=True)
class UsageLogEntry:
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None


@dataclass(slots=True)
class RequestLogEntry:
    id: str
    created_at: datetime
    endpoint: str
    request_kind: str
    model: str
    stream: bool
    final_provider: str | None
    final_url: str | None
    status_code: int | None
    duration_ms: int | None
    ttfb_ms: int | None
    state: str
    error: str | None
    usage: UsageLogEntry | None
    attempts: list[AttemptLogEntry]


class RequestLogStore:
    def __init__(self, capacity: int = 200) -> None:
        self.capacity = capacity
        self._completed_entries: deque[RequestLogEntry] = deque(maxlen=capacity)
        self._pending_entries: dict[str, RequestLogEntry] = {}
        self._lock = asyncio.Lock()

    async def begin(
        self,
        *,
        endpoint: str,
        request_kind: str,
        model: str,
        stream: bool,
    ) -> str:
        entry = RequestLogEntry(
            id=uuid.uuid4().hex,
            created_at=datetime.now(UTC),
            endpoint=endpoint,
            request_kind=request_kind,
            model=model,
            stream=stream,
            final_provider=None,
            final_url=None,
            status_code=None,
            duration_ms=None,
            ttfb_ms=None,
            state="pending",
            error=None,
            usage=None,
            attempts=[],
        )
        async with self._lock:
            self._pending_entries[entry.id] = entry
        return entry.id

    async def complete(
        self,
        entry_id: str,
        *,
        final_provider: str | None,
        final_url: str | None,
        status_code: int | None,
        duration_ms: int,
        ttfb_ms: int | None,
        state: str,
        error: str | None,
        usage: UsageLogEntry | None,
        attempts: list[AttemptLogEntry],
    ) -> None:
        async with self._lock:
            entry = self._pending_entries.pop(entry_id, None)
            if entry is None:
                return
            entry.final_provider = final_provider
            entry.final_url = final_url
            entry.status_code = status_code
            entry.duration_ms = duration_ms
            entry.ttfb_ms = ttfb_ms
            entry.state = state
            entry.error = error
            entry.usage = usage
            entry.attempts = attempts
            self._completed_entries.appendleft(entry)

    async def list_entries(self) -> list[dict[str, object]]:
        async with self._lock:
            pending_entries = list(self._pending_entries.values())[::-1]
            entries = pending_entries + list(self._completed_entries)
        return [
            {
                "id": entry.id,
                "created_at": entry.created_at,
                "endpoint": entry.endpoint,
                "request_kind": entry.request_kind,
                "model": entry.model,
                "stream": entry.stream,
                "final_provider": entry.final_provider,
                "final_url": entry.final_url,
                "status_code": entry.status_code,
                "duration_ms": entry.duration_ms,
                "ttfb_ms": entry.ttfb_ms,
                "state": entry.state,
                "error": entry.error,
                "usage": (
                    {
                        "input_tokens": entry.usage.input_tokens,
                        "output_tokens": entry.usage.output_tokens,
                        "total_tokens": entry.usage.total_tokens,
                    }
                    if entry.usage
                    else None
                ),
                "attempts": [
                    {
                        "provider": attempt.provider,
                        "url": attempt.url,
                        "outcome": attempt.outcome,
                        "retryable": attempt.retryable,
                        "status_code": attempt.status_code,
                        "provider_attempt": attempt.provider_attempt,
                        "next_action": attempt.next_action,
                    }
                    for attempt in entry.attempts
                ],
            }
            for entry in entries
        ]

    async def aggregated_stats(self, provider_names: list[str]) -> dict[str, object]:
        async with self._lock:
            entries = list(self._completed_entries)

        provider_stats = [
            self._build_provider_stats(
                provider_name,
                [entry for entry in entries if entry.final_provider == provider_name],
            )
            for provider_name in provider_names
        ]

        return {
            "global": self._build_provider_stats("all", entries),
            "providers": provider_stats,
        }

    @staticmethod
    def _build_provider_stats(provider_name: str, entries: list[RequestLogEntry]) -> dict[str, object]:
        served_requests = len(entries)
        successful_requests = len([entry for entry in entries if entry.state == "success"])
        duration_values = [entry.duration_ms for entry in entries if entry.duration_ms is not None]
        ttfb_values = [entry.ttfb_ms for entry in entries if entry.ttfb_ms is not None]
        input_tokens = sum(
            entry.usage.input_tokens or 0
            for entry in entries
            if entry.usage is not None
        )
        output_tokens = sum(
            entry.usage.output_tokens or 0
            for entry in entries
            if entry.usage is not None
        )
        total_tokens = sum(
            entry.usage.total_tokens or 0
            for entry in entries
            if entry.usage is not None
        )
        requests_with_usage = len([entry for entry in entries if entry.usage is not None])

        return {
            "provider_name": provider_name,
            "served_requests": served_requests,
            "successful_requests": successful_requests,
            "success_rate": round(successful_requests / served_requests, 4) if served_requests else None,
            "average_duration_ms": round(mean(duration_values), 2) if duration_values else None,
            "average_ttfb_ms": round(mean(ttfb_values), 2) if ttfb_values else None,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
            "requests_with_usage": requests_with_usage,
        }

    async def pending_count(self) -> int:
        async with self._lock:
            return len(self._pending_entries)
