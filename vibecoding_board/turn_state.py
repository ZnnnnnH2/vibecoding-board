from __future__ import annotations

import asyncio
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any


@dataclass(slots=True)
class TurnStateEntry:
    token: str
    created_at: datetime
    current_turn_id: str | None = None
    provider_name: str | None = None
    southbound_transport: str | None = None
    managed_session: Any | None = None
    attached_websocket: Any | None = None
    resume_deadline: datetime | None = None
    terminal_reason: str | None = None


@dataclass(slots=True, frozen=True)
class TurnStateAttachResult:
    status: str
    entry: TurnStateEntry | None = None
    previous_websocket: Any | None = None


class TurnStateStore:
    def __init__(
        self,
        *,
        resume_ttl_seconds: int = 30,
        sweep_interval_seconds: float = 5.0,
    ) -> None:
        self._resume_ttl = timedelta(seconds=resume_ttl_seconds)
        self._sweep_interval = sweep_interval_seconds
        self._entries: dict[str, TurnStateEntry] = {}
        self._lock = asyncio.Lock()
        self._sweep_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Start the background sweeper. Safe to call multiple times."""
        if self._sweep_task is not None and not self._sweep_task.done():
            return
        if self._sweep_interval <= 0:
            return
        self._sweep_task = asyncio.create_task(self._sweep_loop())

    async def _sweep_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(self._sweep_interval)
                try:
                    await self._evict_expired()
                except Exception:  # pragma: no cover - defensive
                    pass
        except asyncio.CancelledError:
            raise

    async def issue(self, *, websocket: Any) -> TurnStateEntry:
        await self._evict_expired()
        entry = TurnStateEntry(
            token=secrets.token_urlsafe(24),
            created_at=datetime.now(UTC),
            attached_websocket=websocket,
        )
        async with self._lock:
            self._entries[entry.token] = entry
        return entry

    async def attach(self, token: str, *, websocket: Any) -> TurnStateAttachResult:
        expired_sessions: list[Any] = []
        async with self._lock:
            entry = self._entries.get(token)
            if entry is None:
                expired_sessions.extend(self._evict_expired_locked())
                result = TurnStateAttachResult(status="invalid")
            elif (
                entry.attached_websocket is None
                and entry.resume_deadline is not None
                and entry.resume_deadline <= datetime.now(UTC)
            ):
                self._entries.pop(token, None)
                if entry.managed_session is not None:
                    expired_sessions.append(entry.managed_session)
                result = TurnStateAttachResult(status="expired")
            else:
                expired_sessions.extend(self._evict_expired_locked())
                previous_websocket = entry.attached_websocket if entry.attached_websocket is not websocket else None
                entry.attached_websocket = websocket
                entry.resume_deadline = None
                result = TurnStateAttachResult(
                    status="resumed",
                    entry=entry,
                    previous_websocket=previous_websocket,
                )
        await self._close_sessions(expired_sessions)
        return result

    async def lookup(self, token: str) -> TurnStateEntry | None:
        await self._evict_expired()
        async with self._lock:
            return self._entries.get(token)

    async def bind_transport(
        self,
        token: str,
        *,
        provider_name: str,
        southbound_transport: str,
        managed_session: Any | None,
    ) -> TurnStateEntry | None:
        async with self._lock:
            entry = self._entries.get(token)
            if entry is None:
                return None
            entry.provider_name = provider_name
            entry.southbound_transport = southbound_transport
            entry.managed_session = managed_session
            entry.terminal_reason = None
            return entry

    async def set_current_turn(
        self,
        token: str,
        *,
        turn_id: str | None,
    ) -> TurnStateEntry | None:
        if not turn_id:
            return await self.lookup(token)

        session_to_close: Any | None = None
        async with self._lock:
            entry = self._entries.get(token)
            if entry is None:
                return None
            if entry.current_turn_id == turn_id:
                return entry
            session_to_close = entry.managed_session
            entry.current_turn_id = turn_id
            entry.provider_name = None
            entry.southbound_transport = None
            entry.managed_session = None
            entry.terminal_reason = None

        await self._close_session(session_to_close)
        async with self._lock:
            entry = self._entries.get(token)
            if entry is None:
                return None
            entry.terminal_reason = None
            return entry

    async def mark_terminal(self, token: str, reason: str) -> TurnStateEntry | None:
        async with self._lock:
            entry = self._entries.get(token)
            if entry is None:
                return None
            entry.terminal_reason = reason
            return entry

    async def clear_terminal(self, token: str) -> TurnStateEntry | None:
        async with self._lock:
            entry = self._entries.get(token)
            if entry is None:
                return None
            entry.terminal_reason = None
            return entry

    async def rename_provider(self, old_name: str, new_name: str) -> int:
        migrated = 0
        async with self._lock:
            for entry in self._entries.values():
                if entry.provider_name != old_name:
                    continue
                entry.provider_name = new_name
                if entry.managed_session is not None:
                    provider_name = getattr(entry.managed_session, "provider_name", None)
                    if provider_name == old_name:
                        setattr(entry.managed_session, "provider_name", new_name)
                migrated += 1
        return migrated

    async def detach(self, token: str, *, websocket: Any) -> TurnStateEntry | None:
        expired_sessions: list[Any] = []
        async with self._lock:
            expired_sessions.extend(self._evict_expired_locked())
            entry = self._entries.get(token)
            if entry is not None and entry.attached_websocket is websocket:
                entry.attached_websocket = None
                entry.resume_deadline = datetime.now(UTC) + self._resume_ttl
        await self._close_sessions(expired_sessions)
        return entry

    async def remove(self, token: str) -> TurnStateEntry | None:
        async with self._lock:
            entry = self._entries.pop(token, None)
        if entry is not None:
            await self._close_session(entry.managed_session)
        return entry

    async def close(self) -> None:
        sweep_task = self._sweep_task
        self._sweep_task = None
        if sweep_task is not None and not sweep_task.done():
            sweep_task.cancel()
            await asyncio.gather(sweep_task, return_exceptions=True)
        async with self._lock:
            entries = list(self._entries.values())
            self._entries.clear()
        await self._close_sessions([entry.managed_session for entry in entries])

    async def _evict_expired(self) -> None:
        expired_sessions: list[Any] = []
        async with self._lock:
            expired_sessions.extend(self._evict_expired_locked())
        await self._close_sessions(expired_sessions)

    def _evict_expired_locked(self) -> list[Any]:
        now = datetime.now(UTC)
        expired_tokens = [
            token
            for token, entry in self._entries.items()
            if entry.attached_websocket is None
            and entry.resume_deadline is not None
            and entry.resume_deadline <= now
        ]
        sessions: list[Any] = []
        for token in expired_tokens:
            entry = self._entries.pop(token, None)
            if entry is not None and entry.managed_session is not None:
                sessions.append(entry.managed_session)
        return sessions

    async def _close_sessions(self, sessions: list[Any]) -> None:
        closed_ids: set[int] = set()
        for session in sessions:
            session_id = id(session)
            if session is None or session_id in closed_ids:
                continue
            closed_ids.add(session_id)
            await self._close_session(session)

    @staticmethod
    async def _close_session(session: Any) -> None:
        if session is None:
            return
        close = getattr(session, "close", None)
        if close is None:
            return
        result = close()
        if asyncio.iscoroutine(result):
            await result
