from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Callable

from vibecoding_board.config import RuntimeProvider


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class ProviderState:
    provider: RuntimeProvider
    consecutive_failures: int = 0
    cooldown_until: datetime | None = None
    last_error: str | None = None
    last_failure_at: datetime | None = None
    last_success_at: datetime | None = None

    def is_available(self, now: datetime) -> bool:
        if not self.provider.enabled:
            return False
        return self.cooldown_until is None or now >= self.cooldown_until

    def supports_model(self, model: str) -> bool:
        return self.provider.supports_model(model)


@dataclass(slots=True)
class ProviderSnapshot:
    name: str
    base_url: str
    api_key: str
    enabled: bool
    priority: int
    timeout_seconds: float
    max_failures: int
    cooldown_seconds: float
    models: tuple[str, ...]
    supports_all_models: bool
    healthcheck_model: str | None
    consecutive_failures: int
    cooldown_until: datetime | None
    last_error: str | None
    last_failure_at: datetime | None
    last_success_at: datetime | None

    @classmethod
    def from_state(cls, state: ProviderState) -> "ProviderSnapshot":
        provider = state.provider
        return cls(
            name=provider.name,
            base_url=provider.base_url,
            api_key=provider.api_key,
            enabled=provider.enabled,
            priority=provider.priority,
            timeout_seconds=provider.timeout_seconds,
            max_failures=provider.max_failures,
            cooldown_seconds=provider.cooldown_seconds,
            models=provider.models,
            supports_all_models=provider.supports_all_models,
            healthcheck_model=provider.healthcheck_model,
            consecutive_failures=state.consecutive_failures,
            cooldown_until=state.cooldown_until,
            last_error=state.last_error,
            last_failure_at=state.last_failure_at,
            last_success_at=state.last_success_at,
        )


@dataclass(slots=True)
class ProviderRegistry:
    providers: list[RuntimeProvider]
    now_provider: Callable[[], datetime] = utc_now
    _states: dict[str, ProviderState] = field(init=False)
    _lock: asyncio.Lock = field(init=False, default_factory=asyncio.Lock)

    def __post_init__(self) -> None:
        self._states = {
            provider.name: ProviderState(provider=provider) for provider in self.providers
        }

    async def get_candidates(self, model: str) -> list[ProviderSnapshot]:
        async with self._lock:
            now = self.now_provider()
            states = [
                ProviderSnapshot.from_state(state)
                for state in self._states.values()
                if state.supports_model(model) and state.is_available(now)
            ]
        return sorted(states, key=lambda state: (state.priority, state.name))

    async def list_states(self) -> list[ProviderSnapshot]:
        async with self._lock:
            snapshots = [
                ProviderSnapshot.from_state(state) for state in self._states.values()
            ]
        return sorted(snapshots, key=lambda state: (state.priority, state.name))

    async def import_states(self, previous_states: list[ProviderSnapshot]) -> None:
        previous_map = {state.name: state for state in previous_states}
        async with self._lock:
            for name, state in self._states.items():
                previous = previous_map.get(name)
                if previous is None:
                    continue
                state.consecutive_failures = previous.consecutive_failures
                state.cooldown_until = previous.cooldown_until
                state.last_error = previous.last_error
                state.last_failure_at = previous.last_failure_at
                state.last_success_at = previous.last_success_at

    async def mark_success(self, provider_name: str) -> None:
        async with self._lock:
            state = self._states[provider_name]
            state.consecutive_failures = 0
            state.cooldown_until = None
            state.last_error = None
            state.last_success_at = self.now_provider()

    async def mark_retryable_failure(self, provider_name: str, error: str) -> None:
        async with self._lock:
            state = self._states[provider_name]
            now = self.now_provider()
            state.consecutive_failures += 1
            state.last_error = error
            state.last_failure_at = now
            if state.consecutive_failures >= state.provider.max_failures:
                state.cooldown_until = now + timedelta(seconds=state.provider.cooldown_seconds)

    async def get_state(self, provider_name: str) -> ProviderSnapshot:
        async with self._lock:
            return ProviderSnapshot.from_state(self._states[provider_name])
