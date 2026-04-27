from __future__ import annotations

from datetime import timedelta

import pytest

from vibecoding_board.request_log import AttemptLogEntry, RequestLogStore, UsageLogEntry


@pytest.mark.anyio
async def test_pending_requests_are_not_dropped_when_completed_queue_is_full() -> None:
    store = RequestLogStore(capacity=2)

    first = await store.begin(
        endpoint="/v1/chat/completions",
        request_kind="chat",
        model="gpt-4.1",
        stream=False,
    )
    second = await store.begin(
        endpoint="/v1/chat/completions",
        request_kind="chat",
        model="gpt-4.1",
        stream=False,
    )
    third = await store.begin(
        endpoint="/v1/chat/completions",
        request_kind="chat",
        model="gpt-4.1",
        stream=False,
    )

    entries = await store.list_entries()
    assert [entry["id"] for entry in entries] == [third, second, first]
    assert all(entry["state"] == "pending" for entry in entries)

    await store.complete(
        second,
        final_provider="relay_a",
        final_url="https://relay-a.example.com/v1/chat/completions",
        status_code=200,
        duration_ms=100,
        ttfb_ms=80,
        state="success",
        error=None,
        usage=UsageLogEntry(input_tokens=5, output_tokens=4, total_tokens=9),
        attempts=[],
    )
    await store.complete(
        third,
        final_provider="relay_b",
        final_url="https://relay-b.example.com/v1/chat/completions",
        status_code=200,
        duration_ms=120,
        ttfb_ms=90,
        state="success",
        error=None,
        usage=UsageLogEntry(input_tokens=6, output_tokens=5, total_tokens=11),
        attempts=[
            AttemptLogEntry(
                provider="relay_a",
                url="https://relay-a.example.com/v1/chat/completions",
                outcome="status_retryable",
                retryable=True,
                status_code=503,
                provider_attempt=1,
                next_action="failover_next_provider",
            )
        ],
    )

    still_pending = await store.list_entries()
    assert still_pending[0]["id"] == first
    assert still_pending[0]["state"] == "pending"

    await store.complete(
        first,
        final_provider="relay_a",
        final_url="https://relay-a.example.com/v1/chat/completions",
        status_code=200,
        duration_ms=95,
        ttfb_ms=70,
        state="success",
        error=None,
        usage=UsageLogEntry(input_tokens=4, output_tokens=3, total_tokens=7),
        attempts=[],
    )

    final_entries = await store.list_entries()
    assert [entry["id"] for entry in final_entries] == [first, third]
    assert all(entry["state"] == "success" for entry in final_entries)


@pytest.mark.anyio
async def test_aggregated_stats_ignore_pending_requests() -> None:
    store = RequestLogStore(capacity=5)
    completed = await store.begin(
        endpoint="/v1/chat/completions",
        request_kind="chat",
        model="gpt-4.1",
        stream=False,
    )
    pending = await store.begin(
        endpoint="/v1/chat/completions",
        request_kind="chat",
        model="gpt-4.1",
        stream=False,
    )

    await store.complete(
        completed,
        final_provider="relay_a",
        final_url="https://relay-a.example.com/v1/chat/completions",
        status_code=200,
        duration_ms=100,
        ttfb_ms=60,
        state="success",
        error=None,
        usage=UsageLogEntry(input_tokens=5, output_tokens=3, total_tokens=8),
        attempts=[],
    )

    stats = await store.aggregated_stats(["relay_a"])

    assert stats["global"]["served_requests"] == 1
    assert stats["global"]["total_tokens"] == 8

    entries = await store.list_entries()
    assert any(entry["id"] == pending and entry["state"] == "pending" for entry in entries)


@pytest.mark.anyio
async def test_pending_request_becomes_stale_after_inactivity() -> None:
    store = RequestLogStore(stale_after_seconds=1, prune_after_seconds=10)

    entry_id = await store.begin(
        endpoint="/v1/responses",
        request_kind="response",
        model="gpt-4.1",
        stream=True,
    )
    entry = (await store.list_entries())[0]
    stale_at = entry["created_at"] + timedelta(seconds=2)

    entries = await store.list_entries(now=stale_at)

    assert entries[0]["id"] == entry_id
    assert entries[0]["state"] == "stale"
    assert entries[0]["duration_ms"] >= 2000
    assert "No request activity" in entries[0]["error"]


@pytest.mark.anyio
async def test_touch_keeps_pending_request_active_until_it_goes_idle() -> None:
    store = RequestLogStore(stale_after_seconds=2, prune_after_seconds=10)

    entry_id = await store.begin(
        endpoint="/v1/responses",
        request_kind="response",
        model="gpt-4.1",
        stream=True,
    )
    entry = (await store.list_entries())[0]
    touched_at = entry["created_at"] + timedelta(seconds=3)
    await store.touch(entry_id, at=touched_at)

    active_entries = await store.list_entries(now=touched_at + timedelta(seconds=1))
    stale_entries = await store.list_entries(now=touched_at + timedelta(seconds=3))

    assert active_entries[0]["state"] == "pending"
    assert stale_entries[0]["state"] == "stale"


@pytest.mark.anyio
async def test_stale_request_can_still_complete_with_real_outcome() -> None:
    store = RequestLogStore(stale_after_seconds=1, prune_after_seconds=10)

    entry_id = await store.begin(
        endpoint="/v1/responses",
        request_kind="response",
        model="gpt-4.1",
        stream=True,
    )
    entry = (await store.list_entries())[0]
    stale_entries = await store.list_entries(now=entry["created_at"] + timedelta(seconds=2))
    assert stale_entries[0]["state"] == "stale"

    await store.complete(
        entry_id,
        final_provider="relay_a",
        final_url="https://relay-a.example.com/v1/responses",
        status_code=200,
        duration_ms=2500,
        ttfb_ms=200,
        state="success",
        error=None,
        usage=None,
        attempts=[],
    )

    entries = await store.list_entries()
    assert entries[0]["id"] == entry_id
    assert entries[0]["state"] == "success"
    assert entries[0]["duration_ms"] == 2500


@pytest.mark.anyio
async def test_expired_stale_request_is_pruned_from_pending_entries() -> None:
    store = RequestLogStore(stale_after_seconds=1, prune_after_seconds=2)

    await store.begin(
        endpoint="/v1/responses",
        request_kind="response",
        model="gpt-4.1",
        stream=True,
    )
    entry = (await store.list_entries())[0]

    entries = await store.list_entries(now=entry["created_at"] + timedelta(seconds=3))

    assert entries == []
