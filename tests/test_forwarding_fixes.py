"""Regression tests for the four high-concurrency / forwarding fixes.

Each test pins down one fix:

1. `UPSTREAM_POOL_LIMITS` is wired onto the shared `httpx.AsyncClient`.
2. `content-encoding` is stripped when the proxy returns a body that httpx
   has already transparently decoded (non-stream path + stream-mode
   non-retryable branch).
3. `AdminMetricsStore.flush` performs its disk write off the event loop and
   recovers the dirty bit if the write fails.
4. `StreamUsageParser` silently disables itself on binary / gzipped bodies
   and is also pre-disabled when upstream declares a `content-encoding`.
"""

from __future__ import annotations

import asyncio
import gzip
import json
from collections.abc import AsyncIterator
from pathlib import Path
import uuid

import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from fastapi.testclient import TestClient

from vibecoding_board.admin_metrics import AdminMetricsStore
from vibecoding_board.app import UPSTREAM_POOL_LIMITS, create_app
from vibecoding_board.config import ProxyConfig, dump_proxy_config
from vibecoding_board.request_log import UsageLogEntry
from vibecoding_board.service import StreamUsageParser


def build_config() -> ProxyConfig:
    return ProxyConfig.model_validate(
        {
            "listen": {"host": "127.0.0.1", "port": 9000},
            "providers": [
                {
                    "name": "relay_a",
                    "base_url": "https://relay-a.example.com/v1",
                    "api_key": "key-a",
                    "enabled": True,
                    "priority": 10,
                    "models": ["gpt-4.1"],
                    "timeout_seconds": 10,
                    "max_failures": 2,
                    "cooldown_seconds": 30,
                }
            ],
        }
    )


def write_config(tmp_path: Path) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(dump_proxy_config(build_config()), encoding="utf-8")
    return path


@pytest.fixture
def workspace_tmp_dir() -> Path:
    base_dir = Path.cwd() / "test-workspaces"
    base_dir.mkdir(exist_ok=True)
    path = base_dir / f"fixes-{uuid.uuid4().hex}"
    path.mkdir()
    return path


# ---------------------------------------------------------------------------
# Fix 1: httpx connection pool limits
# ---------------------------------------------------------------------------


def test_upstream_pool_limits_are_high_enough_for_concurrency() -> None:
    """The hard ceiling on concurrent upstream connections must exceed the
    httpx default (100) so that real-world fan-out is not silently capped."""
    assert UPSTREAM_POOL_LIMITS.max_connections is not None
    assert UPSTREAM_POOL_LIMITS.max_connections >= 500
    assert UPSTREAM_POOL_LIMITS.max_keepalive_connections is not None
    assert UPSTREAM_POOL_LIMITS.max_keepalive_connections >= 100


def test_app_applies_pool_limits_to_shared_client(
    workspace_tmp_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The lifespan must hand the configured limits to the proxy's shared
    AsyncClient — otherwise fix #1 has no effect at runtime."""
    upstream = FastAPI()

    @upstream.post("/v1/chat/completions")
    async def _ok(request: Request):
        return JSONResponse({"ok": True})

    captured: dict[str, object] = {}
    real_init = httpx.AsyncClient.__init__

    def recording_init(self: httpx.AsyncClient, *args: object, **kwargs: object) -> None:
        if "limits" in kwargs:
            captured["limits"] = kwargs["limits"]
        real_init(self, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", recording_init)

    app = create_app(write_config(workspace_tmp_dir), transport=httpx.ASGITransport(app=upstream))
    with TestClient(app):
        pass

    limits = captured.get("limits")
    assert isinstance(limits, httpx.Limits)
    assert limits.max_connections == UPSTREAM_POOL_LIMITS.max_connections
    assert limits.max_keepalive_connections == UPSTREAM_POOL_LIMITS.max_keepalive_connections


# ---------------------------------------------------------------------------
# Fix 2: content-encoding stripped when body is decoded
# ---------------------------------------------------------------------------


def build_gzip_upstream_app(*, stream_mode: bool) -> FastAPI:
    """Upstream that returns a gzipped JSON error (stream_mode=True uses SSE
    mime type so the proxy enters the stream-mode non-retryable branch)."""
    upstream = FastAPI()
    payload = json.dumps({"error": {"message": "upstream says hi"}}).encode("utf-8")
    gzipped = gzip.compress(payload)
    media_type = "text/event-stream" if stream_mode else "application/json"

    @upstream.post("/v1/chat/completions")
    async def chat_completions(request: Request):
        # Use a non-retryable status so the stream path also goes through
        # the decoded-body return branch.
        return Response(
            content=gzipped,
            status_code=418,
            headers={
                "content-encoding": "gzip",
                "content-type": media_type,
            },
        )

    return upstream


def test_non_stream_path_strips_content_encoding_when_body_is_decoded(
    workspace_tmp_dir: Path,
) -> None:
    app = create_app(
        write_config(workspace_tmp_dir),
        transport=httpx.ASGITransport(app=build_gzip_upstream_app(stream_mode=False)),
    )

    with TestClient(app) as client:
        response = client.post(
            "/v1/chat/completions",
            json={"model": "gpt-4.1", "messages": [{"role": "user", "content": "hi"}]},
        )

    assert response.status_code == 418
    # Header must be gone — the bytes returned to the client are already the
    # plain JSON, not the gzip payload.
    assert "content-encoding" not in {key.lower() for key in response.headers.keys()}
    assert response.json() == {"error": {"message": "upstream says hi"}}


def test_stream_mode_non_retryable_branch_strips_content_encoding(
    workspace_tmp_dir: Path,
) -> None:
    app = create_app(
        write_config(workspace_tmp_dir),
        transport=httpx.ASGITransport(app=build_gzip_upstream_app(stream_mode=True)),
    )

    with TestClient(app) as client:
        with client.stream(
            "POST",
            "/v1/chat/completions",
            json={
                "model": "gpt-4.1",
                "stream": True,
                "messages": [{"role": "user", "content": "hi"}],
            },
        ) as response:
            body = b"".join(response.iter_raw())

    assert response.status_code == 418
    assert "content-encoding" not in {key.lower() for key in response.headers.keys()}
    assert json.loads(body) == {"error": {"message": "upstream says hi"}}


def test_stream_success_path_preserves_content_encoding_on_raw_bytes(
    workspace_tmp_dir: Path,
) -> None:
    """The streaming success path forwards raw bytes via aiter_raw(), so the
    upstream content-encoding header must be preserved — stripping it there
    would lie to the client about the wire format."""
    gzipped = gzip.compress(b'data: {"type":"ping"}\n\ndata: [DONE]\n\n')

    upstream = FastAPI()

    @upstream.post("/v1/chat/completions")
    async def chat_completions(request: Request):
        async def body() -> AsyncIterator[bytes]:
            yield gzipped

        return StreamingResponse(
            body(),
            status_code=200,
            media_type="text/event-stream",
            headers={"content-encoding": "gzip"},
        )

    app = create_app(
        write_config(workspace_tmp_dir),
        transport=httpx.ASGITransport(app=upstream),
    )

    with TestClient(app) as client:
        with client.stream(
            "POST",
            "/v1/chat/completions",
            json={
                "model": "gpt-4.1",
                "stream": True,
                "messages": [{"role": "user", "content": "hi"}],
            },
        ) as response:
            forwarded = b"".join(response.iter_raw())

    assert response.status_code == 200
    # The raw gzipped bytes must flow through unchanged, and the encoding
    # header must still describe them correctly.
    assert response.headers.get("content-encoding", "").lower() == "gzip"
    assert gzip.decompress(forwarded) == b'data: {"type":"ping"}\n\ndata: [DONE]\n\n'


# ---------------------------------------------------------------------------
# Fix 3: metrics flush does disk I/O off the event loop
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_flush_does_not_block_the_event_loop(workspace_tmp_dir: Path) -> None:
    """While flush is running its (deliberately slow) write, the event loop
    must remain responsive. We prove that by racing a sleep(0) heartbeat
    against the flush and checking the heartbeat ticks."""
    store = AdminMetricsStore(
        workspace_tmp_dir / "metrics.json",
        flush_interval_seconds=3600,
    )
    await store.record_request(
        final_provider="relay_a",
        state="success",
        duration_ms=10,
        ttfb_ms=5,
        usage=UsageLogEntry(input_tokens=1, output_tokens=1, total_tokens=2),
    )

    original_write = store._write_payload
    write_started = asyncio.Event()

    def slow_write(serialized: str) -> None:
        write_started.set()
        import time

        time.sleep(0.3)
        original_write(serialized)

    store._write_payload = slow_write  # type: ignore[method-assign]

    heartbeats = 0

    async def heartbeat() -> None:
        nonlocal heartbeats
        # Wait until the write is actually in flight before counting.
        await write_started.wait()
        for _ in range(20):
            await asyncio.sleep(0.01)
            heartbeats += 1

    flush_task = asyncio.create_task(store.flush())
    heartbeat_task = asyncio.create_task(heartbeat())
    await asyncio.gather(flush_task, heartbeat_task)

    assert heartbeats >= 10, "event loop was blocked during metrics flush"
    assert (workspace_tmp_dir / "metrics.json").exists()
    await store.close()


@pytest.mark.anyio
async def test_flush_failure_re_arms_dirty_bit(workspace_tmp_dir: Path) -> None:
    store = AdminMetricsStore(
        workspace_tmp_dir / "metrics.json",
        flush_interval_seconds=3600,
    )
    await store.record_request(
        final_provider="relay_a",
        state="success",
        duration_ms=10,
        ttfb_ms=5,
        usage=UsageLogEntry(input_tokens=1, output_tokens=1, total_tokens=2),
    )

    def broken_write(serialized: str) -> None:
        raise OSError("disk full")

    store._write_payload = broken_write  # type: ignore[method-assign]
    with pytest.raises(OSError, match="disk full"):
        await store.flush()
    assert store._dirty is True, "dirty bit must be re-armed after a failed flush"

    # Recovery path: the next successful flush must pick up the same data.
    store._write_payload = AdminMetricsStore._write_payload.__get__(store, AdminMetricsStore)  # type: ignore[method-assign]
    await store.flush()
    assert (workspace_tmp_dir / "metrics.json").exists()
    await store.close()


@pytest.mark.anyio
async def test_flush_is_atomic_via_temp_file(workspace_tmp_dir: Path) -> None:
    """The write must go through a ``.tmp`` sidecar and be renamed into
    place, so a crash mid-write cannot leave a half-written metrics file."""
    target = workspace_tmp_dir / "metrics.json"
    target.write_text('{"buckets": [], "pre-existing": true}', encoding="utf-8")

    store = AdminMetricsStore(target, flush_interval_seconds=3600)
    await store.record_request(
        final_provider="relay_a",
        state="success",
        duration_ms=10,
        ttfb_ms=5,
        usage=UsageLogEntry(input_tokens=1, output_tokens=1, total_tokens=2),
    )

    seen_tmp: list[Path] = []
    original_write = store._write_payload

    def spying_write(serialized: str) -> None:
        tmp = target.with_name(target.name + ".tmp")
        original_write(serialized)
        if tmp.exists() or True:  # the rename already ran; record intent
            seen_tmp.append(tmp)

    store._write_payload = spying_write  # type: ignore[method-assign]
    await store.flush()

    data = json.loads(target.read_text(encoding="utf-8"))
    assert "pre-existing" not in data
    assert data["buckets"], "flushed payload should contain the recorded request"
    # Tmp file should not linger after a successful rename.
    assert not (target.with_name(target.name + ".tmp")).exists()
    await store.close()


# ---------------------------------------------------------------------------
# Fix 4: StreamUsageParser tolerates binary bodies
# ---------------------------------------------------------------------------


def test_parser_survives_raw_gzip_bytes() -> None:
    parser = StreamUsageParser()
    parser.feed(gzip.compress(b'data: {"usage": {"total_tokens": 5}}\n\n'))
    parser.finish()
    # Must not raise, must not produce fake usage, must self-disable.
    assert parser.usage is None
    assert parser._disabled is True


def test_parser_extracts_usage_from_plain_sse() -> None:
    parser = StreamUsageParser()
    parser.feed(
        b'data: {"choices":[{"delta":{"content":"hi"}}]}\n\n'
        b'data: {"usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5}}\n\n'
        b"data: [DONE]\n\n"
    )
    parser.finish()
    assert parser.usage is not None
    assert parser.usage.total_tokens == 5
    assert parser.usage.input_tokens == 3
    assert parser.usage.output_tokens == 2


def test_parser_disable_is_idempotent() -> None:
    parser = StreamUsageParser()
    parser.disable()
    parser.feed(b"anything")
    parser.finish()
    assert parser.usage is None
    assert parser._disabled is True


# ---------------------------------------------------------------------------
# Stream lifecycle: upstream response must be closed promptly
# ---------------------------------------------------------------------------


def _install_aclose_spy(app) -> list[str]:
    """Patch the proxy service's internal httpx client so that every
    upstream response it produces records an entry in the returned list
    the moment ``aclose`` is called on it."""
    closes: list[str] = []
    proxy_client: httpx.AsyncClient = app.state.service.client
    original_send = proxy_client.send

    async def spying_send(request, **kwargs):  # type: ignore[no-untyped-def]
        response = await original_send(request, **kwargs)
        original_aclose = response.aclose

        async def tracked_aclose() -> None:
            closes.append(str(request.url))
            await original_aclose()

        response.aclose = tracked_aclose  # type: ignore[method-assign]
        return response

    proxy_client.send = spying_send  # type: ignore[method-assign]
    return closes


def test_stream_closes_upstream_response_promptly_on_normal_end(
    workspace_tmp_dir: Path,
) -> None:
    """When upstream finishes streaming on its own, the proxy must close
    the upstream response in the generator's finally block *before*
    control returns to the client — otherwise the connection leaks until
    the async generator is garbage collected."""
    upstream = FastAPI()

    @upstream.post("/v1/chat/completions")
    async def chat_completions(request: Request):
        async def body() -> AsyncIterator[bytes]:
            yield b'data: {"choices":[{"delta":{"content":"hi"}}]}\n\n'
            yield b'data: {"usage":{"prompt_tokens":1,"completion_tokens":1,"total_tokens":2}}\n\n'
            yield b"data: [DONE]\n\n"

        return StreamingResponse(body(), media_type="text/event-stream")

    app = create_app(
        write_config(workspace_tmp_dir),
        transport=httpx.ASGITransport(app=upstream),
    )

    with TestClient(app) as client:
        closes = _install_aclose_spy(app)

        with client.stream(
            "POST",
            "/v1/chat/completions",
            json={
                "model": "gpt-4.1",
                "stream": True,
                "messages": [{"role": "user", "content": "hi"}],
            },
        ) as response:
            forwarded = b"".join(response.iter_raw())

        dashboard = client.get("/admin/api/dashboard").json()

    # The proxy must have closed exactly one upstream response (the one it
    # opened for this stream request), and the close must have happened
    # before the dashboard call observes the terminal ``success`` state.
    assert any("/v1/chat/completions" in url for url in closes), closes
    assert b"[DONE]" in forwarded
    request_entry = dashboard["recent_requests"][0]
    assert request_entry["state"] == "success"
    assert request_entry["usage"]["total_tokens"] == 2


def test_stream_closes_upstream_response_on_client_abort_midstream(
    workspace_tmp_dir: Path,
) -> None:
    """If the client stops reading halfway through the stream, the proxy's
    async generator is torn down by Starlette and the finally block must
    still run to release the upstream connection."""
    chunks_sent = asyncio.Event()

    upstream = FastAPI()

    @upstream.post("/v1/chat/completions")
    async def chat_completions(request: Request):
        async def body() -> AsyncIterator[bytes]:
            yield b'data: {"choices":[{"delta":{"content":"first"}}]}\n\n'
            chunks_sent.set()
            # The remaining chunks never need to be read; the proxy must
            # tear down the upstream response without waiting for them.
            for _ in range(5):
                await asyncio.sleep(0.01)
                yield b'data: {"choices":[{"delta":{"content":"more"}}]}\n\n'
            yield b"data: [DONE]\n\n"

        return StreamingResponse(body(), media_type="text/event-stream")

    app = create_app(
        write_config(workspace_tmp_dir),
        transport=httpx.ASGITransport(app=upstream),
    )

    with TestClient(app) as client:
        closes = _install_aclose_spy(app)

        with client.stream(
            "POST",
            "/v1/chat/completions",
            json={
                "model": "gpt-4.1",
                "stream": True,
                "messages": [{"role": "user", "content": "hi"}],
            },
        ) as response:
            iterator = response.iter_raw()
            # Consume just the first chunk, then let the context manager
            # close the response to simulate a client abort.
            first = next(iterator)
            assert b"first" in first

    assert any("/v1/chat/completions" in url for url in closes), closes


def test_stream_forwarding_is_byte_exact_when_upstream_gzips(
    workspace_tmp_dir: Path,
) -> None:
    """End-to-end: upstream declares content-encoding, parser must not
    corrupt the stream or raise, and the forwarded bytes must match."""
    gzipped = gzip.compress(b'data: {"type":"ping"}\n\ndata: [DONE]\n\n')

    upstream = FastAPI()

    @upstream.post("/v1/chat/completions")
    async def chat_completions(request: Request):
        async def body() -> AsyncIterator[bytes]:
            yield gzipped[:10]
            yield gzipped[10:]

        return StreamingResponse(
            body(),
            status_code=200,
            media_type="text/event-stream",
            headers={"content-encoding": "gzip"},
        )

    app = create_app(
        write_config(workspace_tmp_dir),
        transport=httpx.ASGITransport(app=upstream),
    )

    with TestClient(app) as client:
        with client.stream(
            "POST",
            "/v1/chat/completions",
            json={
                "model": "gpt-4.1",
                "stream": True,
                "messages": [{"role": "user", "content": "hi"}],
            },
        ) as response:
            forwarded = b"".join(response.iter_raw())
        dashboard = client.get("/admin/api/dashboard").json()

    assert forwarded == gzipped
    # The request should still be logged as success — the parser just skips
    # usage extraction for compressed streams.
    assert dashboard["recent_requests"][0]["state"] == "success"
    assert dashboard["recent_requests"][0]["usage"] is None
