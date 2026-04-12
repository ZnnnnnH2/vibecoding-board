from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from vibecoding_board.config import RuntimeProvider
from vibecoding_board.registry import ProviderRegistry


def make_provider(
    name: str,
    *,
    priority: int,
    models: list[str],
    always_alive: bool = False,
) -> RuntimeProvider:
    return RuntimeProvider(
        name=name,
        base_url=f"https://{name}.example.com/v1",
        api_key="test-key",
        enabled=True,
        always_alive=always_alive,
        priority=priority,
        models=tuple(models),
        healthcheck_model=None,
        timeout_seconds=10,
        max_failures=2,
        cooldown_seconds=30,
    )


@pytest.mark.anyio
async def test_registry_sorts_candidates_by_priority() -> None:
    registry = ProviderRegistry(
        [
            make_provider("relay_b", priority=20, models=["gpt-4.1"]),
            make_provider("relay_a", priority=10, models=["gpt-4.1"]),
            make_provider("relay_c", priority=30, models=["gpt-4o-mini"]),
        ]
    )

    candidates = await registry.get_candidates("gpt-4.1")

    assert [candidate.name for candidate in candidates] == ["relay_a", "relay_b"]


@pytest.mark.anyio
async def test_registry_opens_and_recovers_after_cooldown() -> None:
    class Clock:
        def __init__(self) -> None:
            self.value = datetime(2026, 4, 7, tzinfo=UTC)

        def tick(self, seconds: int) -> None:
            self.value += timedelta(seconds=seconds)

        def now(self) -> datetime:
            return self.value

    clock = Clock()

    registry = ProviderRegistry(
        [make_provider("relay_a", priority=10, models=["gpt-4.1"])],
        now_provider=clock.now,
    )

    await registry.mark_retryable_failure("relay_a", "timeout")
    await registry.mark_retryable_failure("relay_a", "timeout")

    assert await registry.get_candidates("gpt-4.1") == []

    clock.tick(31)
    candidates = await registry.get_candidates("gpt-4.1")

    assert [candidate.name for candidate in candidates] == ["relay_a"]

    await registry.mark_success("relay_a")
    state = await registry.get_state("relay_a")

    assert state.consecutive_failures == 0
    assert state.cooldown_until is None


@pytest.mark.anyio
async def test_registry_always_alive_provider_stays_available_after_failures() -> None:
    registry = ProviderRegistry(
        [make_provider("relay_a", priority=10, models=["gpt-4.1"], always_alive=True)]
    )

    await registry.mark_retryable_failure("relay_a", "timeout")
    await registry.mark_retryable_failure("relay_a", "timeout")

    candidates = await registry.get_candidates("gpt-4.1")
    state = await registry.get_state("relay_a")

    assert [candidate.name for candidate in candidates] == ["relay_a"]
    assert state.consecutive_failures == 2
    assert state.cooldown_until is None


@pytest.mark.anyio
async def test_registry_reapplies_future_cooldown_after_always_alive_is_removed() -> None:
    registry = ProviderRegistry(
        [make_provider("relay_a", priority=10, models=["gpt-4.1"], always_alive=True)]
    )
    await registry.mark_retryable_failure("relay_a", "timeout")
    await registry.mark_retryable_failure("relay_a", "timeout")

    previous_states = await registry.list_states()

    updated_registry = ProviderRegistry(
        [make_provider("relay_a", priority=10, models=["gpt-4.1"], always_alive=False)]
    )
    await updated_registry.import_states(previous_states)

    imported_state = await updated_registry.get_state("relay_a")
    assert imported_state.cooldown_until is None

    await updated_registry.mark_retryable_failure("relay_a", "timeout")
    final_state = await updated_registry.get_state("relay_a")

    assert final_state.consecutive_failures == 3
    assert final_state.cooldown_until is not None
