from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
import json
from pathlib import Path

from vibecoding_board.request_log import UsageLogEntry


@dataclass(slots=True)
class ProviderTokenSummary:
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    requests: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "requests": self.requests,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> ProviderTokenSummary:
        return cls(
            input_tokens=int(data.get("input_tokens", 0)),
            output_tokens=int(data.get("output_tokens", 0)),
            total_tokens=int(data.get("total_tokens", 0)),
            requests=int(data.get("requests", 0)),
        )


class TokenLedger:
    """Persistent cumulative token counter.

    Unlike the hourly metrics store which trims old buckets, the ledger
    only accumulates. It survives process restarts and never resets
    automatically.
    """

    def __init__(
        self,
        path: str | Path,
        *,
        flush_interval_seconds: float = 10.0,
    ) -> None:
        self.path = Path(path).resolve()
        self.flush_interval_seconds = flush_interval_seconds
        self._input_tokens: int = 0
        self._output_tokens: int = 0
        self._total_tokens: int = 0
        self._total_requests: int = 0
        self._requests_with_usage: int = 0
        self._providers: dict[str, ProviderTokenSummary] = {}
        self._models: dict[str, ProviderTokenSummary] = {}
        self._updated_at: datetime | None = None
        self._dirty = False
        self._flush_task: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()

    def load(self) -> None:
        try:
            raw = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return

        self._input_tokens = int(data.get("input_tokens", 0))
        self._output_tokens = int(data.get("output_tokens", 0))
        self._total_tokens = int(data.get("total_tokens", 0))
        self._total_requests = int(data.get("total_requests", 0))
        self._requests_with_usage = int(data.get("requests_with_usage", 0))
        self._providers = {
            name: ProviderTokenSummary.from_dict(summary)
            for name, summary in (data.get("providers") or {}).items()
            if isinstance(name, str) and isinstance(summary, dict)
        }
        self._models = {
            name: ProviderTokenSummary.from_dict(summary)
            for name, summary in (data.get("models") or {}).items()
            if isinstance(name, str) and isinstance(summary, dict)
        }
        updated_at = data.get("updated_at")
        if updated_at:
            try:
                self._updated_at = datetime.fromisoformat(str(updated_at)).astimezone(UTC)
            except (ValueError, TypeError):
                pass

    async def close(self) -> None:
        if self._flush_task is not None:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
            self._flush_task = None
        await self.flush()

    async def record(
        self,
        *,
        model: str | None,
        provider: str | None,
        usage: UsageLogEntry | None,
    ) -> None:
        input_tokens = (usage.input_tokens or 0) if usage else 0
        output_tokens = (usage.output_tokens or 0) if usage else 0
        total_tokens = (usage.total_tokens or 0) if usage else 0

        async with self._lock:
            self._total_requests += 1
            if usage is not None:
                self._requests_with_usage += 1
                self._input_tokens += input_tokens
                self._output_tokens += output_tokens
                self._total_tokens += total_tokens

                if provider is not None:
                    ps = self._providers.setdefault(provider, ProviderTokenSummary())
                    ps.input_tokens += input_tokens
                    ps.output_tokens += output_tokens
                    ps.total_tokens += total_tokens
                    ps.requests += 1

                if model is not None:
                    ms = self._models.setdefault(model, ProviderTokenSummary())
                    ms.input_tokens += input_tokens
                    ms.output_tokens += output_tokens
                    ms.total_tokens += total_tokens
                    ms.requests += 1

            self._updated_at = datetime.now(UTC)
            self._dirty = True

        self._schedule_flush()

    async def snapshot(self) -> dict[str, object]:
        async with self._lock:
            return {
                "input_tokens": self._input_tokens,
                "output_tokens": self._output_tokens,
                "total_tokens": self._total_tokens,
                "total_requests": self._total_requests,
                "requests_with_usage": self._requests_with_usage,
                "updated_at": self._updated_at,
                "providers": {
                    name: summary.to_dict()
                    for name, summary in sorted(
                        self._providers.items(),
                        key=lambda item: -item[1].total_tokens,
                    )
                },
                "models": {
                    name: summary.to_dict()
                    for name, summary in sorted(
                        self._models.items(),
                        key=lambda item: -item[1].total_tokens,
                    )
                },
            }

    async def flush(self) -> None:
        async with self._lock:
            if not self._dirty:
                return
            payload = {
                "input_tokens": self._input_tokens,
                "output_tokens": self._output_tokens,
                "total_tokens": self._total_tokens,
                "total_requests": self._total_requests,
                "requests_with_usage": self._requests_with_usage,
                "updated_at": self._updated_at.isoformat() if self._updated_at else None,
                "providers": {
                    name: summary.to_dict()
                    for name, summary in self._providers.items()
                },
                "models": {
                    name: summary.to_dict()
                    for name, summary in self._models.items()
                },
            }
            serialized = json.dumps(payload, ensure_ascii=False, indent=2)
            self._dirty = False

        try:
            await asyncio.to_thread(self._write, serialized)
        except Exception:
            async with self._lock:
                self._dirty = True
            raise

    def _write(self, serialized: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(serialized, encoding="utf-8")
        tmp.replace(self.path)

    def _schedule_flush(self) -> None:
        if self._flush_task is None or self._flush_task.done():
            self._flush_task = asyncio.create_task(self._flush_after_delay())

    async def _flush_after_delay(self) -> None:
        try:
            await asyncio.sleep(self.flush_interval_seconds)
            await self.flush()
        except asyncio.CancelledError:
            raise
