from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime
from statistics import mean
import uuid


DEFAULT_PENDING_STALE_AFTER_SECONDS = 30 * 60
DEFAULT_PENDING_PRUNE_AFTER_SECONDS = 6 * 60 * 60


@dataclass(slots=True, frozen=True)
class AttemptLogEntry:
    provider: str
    url: str
    outcome: str
    retryable: bool
    status_code: int | None
    provider_attempt: int
    next_action: str
    transport: str = "http"
    sticky: bool = False
    fallback_reason: str | None = None


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
    northbound_transport: str
    southbound_transport: str | None
    sticky_provider: str | None
    fallback_reason: str | None
    turn_state_token_present: bool
    turn_state_status: str | None
    final_provider: str | None
    final_url: str | None
    status_code: int | None
    duration_ms: int | None
    ttfb_ms: int | None
    state: str
    error: str | None
    usage: UsageLogEntry | None
    attempts: list[AttemptLogEntry]
    last_activity_at: datetime


class RequestLogStore:
    def __init__(
        self,
        capacity: int = 200,
        *,
        stale_after_seconds: float = DEFAULT_PENDING_STALE_AFTER_SECONDS,
        prune_after_seconds: float = DEFAULT_PENDING_PRUNE_AFTER_SECONDS,
    ) -> None:
        self.capacity = capacity
        self.stale_after_seconds = stale_after_seconds
        self.prune_after_seconds = prune_after_seconds
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
        northbound_transport: str = "http",
        sticky_provider: str | None = None,
        turn_state_token_present: bool = False,
        turn_state_status: str | None = None,
    ) -> str:
        now = datetime.now(UTC)
        entry = RequestLogEntry(
            id=uuid.uuid4().hex,
            created_at=now,
            endpoint=endpoint,
            request_kind=request_kind,
            model=model,
            stream=stream,
            northbound_transport=northbound_transport,
            southbound_transport=None,
            sticky_provider=sticky_provider,
            fallback_reason=None,
            turn_state_token_present=turn_state_token_present,
            turn_state_status=turn_state_status,
            final_provider=None,
            final_url=None,
            status_code=None,
            duration_ms=None,
            ttfb_ms=None,
            state="pending",
            error=None,
            usage=None,
            attempts=[],
            last_activity_at=now,
        )
        async with self._lock:
            self._pending_entries[entry.id] = entry
        return entry.id

    async def touch(self, entry_id: str, *, at: datetime | None = None) -> None:
        async with self._lock:
            entry = self._pending_entries.get(entry_id)
            if entry is not None:
                entry.last_activity_at = at or datetime.now(UTC)

    async def complete(
        self,
        entry_id: str,
        *,
        southbound_transport: str | None = "http",
        sticky_provider: str | None = None,
        fallback_reason: str | None = None,
        final_provider: str | None,
        final_url: str | None,
        status_code: int | None,
        duration_ms: int,
        ttfb_ms: int | None,
        state: str,
        error: str | None,
        usage: UsageLogEntry | None,
        attempts: list[AttemptLogEntry],
        turn_state_status: str | None = None,
    ) -> None:
        async with self._lock:
            entry = self._pending_entries.pop(entry_id, None)
            if entry is None:
                return
            entry.southbound_transport = southbound_transport
            entry.sticky_provider = sticky_provider if sticky_provider is not None else entry.sticky_provider
            entry.fallback_reason = fallback_reason
            entry.turn_state_status = turn_state_status if turn_state_status is not None else entry.turn_state_status
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

    async def list_entries(self, *, now: datetime | None = None) -> list[dict[str, object]]:
        current_time = now or datetime.now(UTC)
        async with self._lock:
            self._prune_expired_pending_locked(current_time)
            pending_entries = list(self._pending_entries.values())[::-1]
            entries = pending_entries + list(self._completed_entries)
        return [
            self._entry_to_payload(entry, now=current_time)
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
        now = datetime.now(UTC)
        async with self._lock:
            self._prune_expired_pending_locked(now)
            return len(self._pending_entries)

    def _entry_to_payload(self, entry: RequestLogEntry, *, now: datetime) -> dict[str, object]:
        state = entry.state
        duration_ms = entry.duration_ms
        error = entry.error
        if entry.state == "pending" and self._pending_is_stale(entry, now):
            state = "stale"
            duration_ms = int((now - entry.created_at).total_seconds() * 1000)
            error = error or self._stale_error_message()

        return {
            "id": entry.id,
            "created_at": entry.created_at,
            "endpoint": entry.endpoint,
            "request_kind": entry.request_kind,
            "model": entry.model,
            "stream": entry.stream,
            "northbound_transport": entry.northbound_transport,
            "southbound_transport": entry.southbound_transport,
            "sticky_provider": entry.sticky_provider,
            "fallback_reason": entry.fallback_reason,
            "turn_state_token_present": entry.turn_state_token_present,
            "turn_state_status": entry.turn_state_status,
            "final_provider": entry.final_provider,
            "final_url": entry.final_url,
            "status_code": entry.status_code,
            "duration_ms": duration_ms,
            "ttfb_ms": entry.ttfb_ms,
            "state": state,
            "error": error,
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
                    "transport": attempt.transport,
                    "sticky": attempt.sticky,
                    "fallback_reason": attempt.fallback_reason,
                }
                for attempt in entry.attempts
            ],
        }

    def _pending_is_stale(self, entry: RequestLogEntry, now: datetime) -> bool:
        return (now - entry.last_activity_at).total_seconds() >= self.stale_after_seconds

    def _prune_expired_pending_locked(self, now: datetime) -> None:
        expired_ids = [
            entry_id
            for entry_id, entry in self._pending_entries.items()
            if (now - entry.last_activity_at).total_seconds() >= self.prune_after_seconds
        ]
        for entry_id in expired_ids:
            self._pending_entries.pop(entry_id, None)

    def _stale_error_message(self) -> str:
        stale_minutes = max(1, int(self.stale_after_seconds // 60))
        return (
            f"No request activity recorded for more than {stale_minutes} minutes; "
            "marking this traffic row stale until it completes or expires."
        )
