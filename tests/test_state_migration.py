from __future__ import annotations

import pytest

from vibecoding_board.responses_state import ResponsesStateStore
from vibecoding_board.turn_state import TurnStateStore


@pytest.mark.anyio
async def test_responses_state_renames_bound_provider() -> None:
    store = ResponsesStateStore()
    original = await store.bind_response(
        "resp-1",
        provider_name="relay_a",
        southbound_transport="http_sse",
    )
    await store.bind_response(
        "resp-2",
        provider_name="relay_b",
        southbound_transport="http",
    )

    migrated = await store.rename_provider("relay_a", "relay_renamed")

    renamed = await store.lookup_response("resp-1")
    untouched = await store.lookup_response("resp-2")
    assert migrated == 1
    assert renamed is not None
    assert renamed.provider_name == "relay_renamed"
    assert renamed.southbound_transport == original.southbound_transport
    assert renamed.created_at == original.created_at
    assert untouched is not None
    assert untouched.provider_name == "relay_b"


@pytest.mark.anyio
async def test_turn_state_renames_bound_provider_and_managed_session() -> None:
    class ManagedSession:
        provider_name = "relay_a"

    store = TurnStateStore(sweep_interval_seconds=0)
    entry = await store.issue(websocket=object())
    managed_session = ManagedSession()
    await store.bind_transport(
        entry.token,
        provider_name="relay_a",
        southbound_transport="websocket",
        managed_session=managed_session,
    )

    migrated = await store.rename_provider("relay_a", "relay_renamed")

    renamed = await store.lookup(entry.token)
    assert migrated == 1
    assert renamed is not None
    assert renamed.provider_name == "relay_renamed"
    assert managed_session.provider_name == "relay_renamed"
    await store.close()


@pytest.mark.anyio
async def test_turn_state_rename_ignores_unrelated_sessions() -> None:
    store = TurnStateStore(sweep_interval_seconds=0)
    entry = await store.issue(websocket=object())
    await store.bind_transport(
        entry.token,
        provider_name="relay_b",
        southbound_transport="http_sse",
        managed_session=None,
    )

    migrated = await store.rename_provider("relay_a", "relay_renamed")

    unchanged = await store.lookup(entry.token)
    assert migrated == 0
    assert unchanged is not None
    assert unchanged.provider_name == "relay_b"
    await store.close()
