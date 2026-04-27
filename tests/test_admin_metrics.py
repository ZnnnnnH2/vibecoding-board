from __future__ import annotations

import json
from pathlib import Path
import shutil
import uuid

import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from vibecoding_board.app import create_app
from vibecoding_board.admin_metrics import AdminMetricsStore
from vibecoding_board.config import ProxyConfig, dump_proxy_config
from vibecoding_board.request_log import AttemptLogEntry


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
                    "models": ["gpt-4.1", "gpt-4o-mini"],
                    "timeout_seconds": 10,
                    "max_failures": 2,
                    "cooldown_seconds": 30,
                }
            ],
        }
    )


def build_failover_config() -> ProxyConfig:
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
                },
                {
                    "name": "relay_b",
                    "base_url": "https://relay-b.example.com/v1",
                    "api_key": "key-b",
                    "enabled": True,
                    "priority": 20,
                    "models": ["gpt-4.1"],
                    "timeout_seconds": 10,
                    "max_failures": 2,
                    "cooldown_seconds": 30,
                },
            ],
        }
    )


def write_config(tmp_path: Path) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(dump_proxy_config(build_config()), encoding="utf-8")
    return path


def write_failover_config(tmp_path: Path) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(dump_proxy_config(build_failover_config()), encoding="utf-8")
    return path


@pytest.fixture
def workspace_tmp_dir() -> Path:
    base_dir = Path.cwd() / "metrics-test-workspaces"
    base_dir.mkdir(exist_ok=True)
    path = base_dir / f"metrics-{uuid.uuid4().hex}"
    path.mkdir()
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def build_upstream_app() -> FastAPI:
    app = FastAPI()

    @app.post("/v1/chat/completions")
    async def chat_completions(request: Request):
        payload = await request.json()
        return JSONResponse(
            {
                "id": "chatcmpl-metrics",
                "object": "chat.completion",
                "model": payload["model"],
                "usage": {
                    "prompt_tokens": 7,
                    "completion_tokens": 2,
                    "total_tokens": 9,
                },
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"}}],
            }
        )

    @app.post("/v1/responses")
    async def responses(request: Request):
        payload = await request.json()
        return JSONResponse(
            {
                "id": "resp-metrics",
                "object": "response",
                "model": payload["model"],
                "usage": {
                    "input_tokens": 5,
                    "output_tokens": 3,
                    "total_tokens": 8,
                },
                "output": [{"type": "message", "content": [{"type": "output_text", "text": "ok"}]}],
            }
        )

    return app


def build_failover_upstream_app() -> FastAPI:
    app = FastAPI()

    @app.post("/v1/chat/completions")
    async def chat_completions(request: Request):
        host = request.headers.get("host", "")
        if host.startswith("relay-a.example.com"):
            return JSONResponse({"error": {"message": "try next"}}, status_code=503)
        return JSONResponse(
            {
                "id": "chatcmpl-failover-metrics",
                "object": "chat.completion",
                "model": "gpt-4.1",
                "usage": {
                    "prompt_tokens": 7,
                    "completion_tokens": 2,
                    "total_tokens": 9,
                },
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"}}],
            }
        )

    return app


def test_metrics_endpoint_returns_hourly_series_and_breakdowns(workspace_tmp_dir: Path) -> None:
    app = create_app(write_config(workspace_tmp_dir), transport=httpx.ASGITransport(app=build_upstream_app()))

    with TestClient(app) as client:
        client.post(
            "/v1/chat/completions",
            json={"model": "gpt-4.1", "messages": [{"role": "user", "content": "hi"}]},
        )
        client.post(
            "/v1/responses",
            json={"model": "gpt-4o-mini", "input": "hello"},
        )

        response = client.get("/admin/api/metrics?window=24h")

        assert response.status_code == 200
        payload = response.json()
        assert payload["window"] == "24h"
        assert payload["summary"]["requests"] == 2
        assert payload["summary"]["total_tokens"] == 17
        assert payload["summary"]["success_rate"] == 1.0
        assert len(payload["timeseries"]["requests"]) == 24
        assert any(point["value"] == 2 for point in payload["timeseries"]["requests"])
        assert any(point["value"] == 17 for point in payload["timeseries"]["tokens"])
        assert payload["breakdowns"]["providers"][0]["provider_name"] == "relay_a"
        assert payload["breakdowns"]["providers"][0]["requests"] == 2
        states = {item["state"]: item["count"] for item in payload["breakdowns"]["states"]}
        assert states["success"] == 2
        assert states["interrupted"] == 0
        assert states["error"] == 0


def test_metrics_endpoint_counts_failover_attempts(workspace_tmp_dir: Path) -> None:
    app = create_app(
        write_failover_config(workspace_tmp_dir),
        transport=httpx.ASGITransport(app=build_failover_upstream_app()),
    )

    with TestClient(app) as client:
        proxied = client.post(
            "/v1/chat/completions",
            json={"model": "gpt-4.1", "messages": [{"role": "user", "content": "hi"}]},
        )
        response = client.get("/admin/api/metrics?window=24h")

    assert proxied.status_code == 200
    payload = response.json()
    assert payload["summary"]["requests"] == 1
    assert payload["summary"]["failover_requests"] == 1
    assert payload["summary"]["failover_next_provider_count"] == 1
    assert payload["summary"]["retryable_error_count"] == 1
    assert any(point["value"] == 1 for point in payload["timeseries"]["failover_requests"])
    next_actions = {item["next_action"]: item["count"] for item in payload["breakdowns"]["next_actions"]}
    assert next_actions["failover_next_provider"] == 1


@pytest.mark.anyio
async def test_metrics_store_persists_failover_attempt_counts(workspace_tmp_dir: Path) -> None:
    store = AdminMetricsStore(workspace_tmp_dir / "metrics.json", flush_interval_seconds=3600)
    await store.record_request(
        final_provider="relay_b",
        state="success",
        duration_ms=10,
        ttfb_ms=5,
        usage=None,
        attempts=[
            AttemptLogEntry(
                provider="relay_a",
                url="https://relay-a.example.com/v1/chat/completions",
                outcome="status_503",
                retryable=True,
                status_code=503,
                provider_attempt=1,
                next_action="failover_next_provider",
            ),
            AttemptLogEntry(
                provider="relay_b",
                url="https://relay-b.example.com/v1/chat/completions",
                outcome="success",
                retryable=False,
                status_code=200,
                provider_attempt=1,
                next_action="return_to_client",
            ),
        ],
    )

    await store.flush()
    store = AdminMetricsStore(workspace_tmp_dir / "metrics.json", flush_interval_seconds=3600)
    store.load()
    payload = await store.metrics_payload(window="24h")

    assert payload["summary"]["failover_requests"] == 1
    assert payload["summary"]["failover_next_provider_count"] == 1
    assert payload["summary"]["retryable_error_count"] == 1
    await store.close()


def test_metrics_store_persists_hourly_file_on_shutdown(workspace_tmp_dir: Path) -> None:
    config_path = write_config(workspace_tmp_dir)
    app = create_app(config_path, transport=httpx.ASGITransport(app=build_upstream_app()))

    with TestClient(app) as client:
        client.post(
            "/v1/chat/completions",
            json={"model": "gpt-4.1", "messages": [{"role": "user", "content": "hi"}]},
        )

    metrics_path = config_path.parent / "data" / "metrics" / "admin_hourly.json"
    assert metrics_path.exists()

    payload = json.loads(metrics_path.read_text(encoding="utf-8"))
    assert payload["buckets"]
    assert payload["buckets"][-1]["requests"] >= 1
