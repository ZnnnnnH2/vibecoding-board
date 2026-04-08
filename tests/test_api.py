from __future__ import annotations

from collections.abc import AsyncIterator
import json
from pathlib import Path
import uuid

import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.testclient import TestClient

from vibecoding_board.app import create_app
from vibecoding_board.config import ProxyConfig, dump_proxy_config


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


def write_config(tmp_path: Path, config: ProxyConfig | None = None) -> Path:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(dump_proxy_config(config or build_config()), encoding="utf-8")
    return config_path


@pytest.fixture
def workspace_tmp_dir() -> Path:
    base_dir = Path.cwd() / "test-workspaces"
    base_dir.mkdir(exist_ok=True)
    path = base_dir / f"api-{uuid.uuid4().hex}"
    path.mkdir()
    return path


def build_upstream_app() -> FastAPI:
    app = FastAPI()

    @app.post("/v1/chat/completions")
    async def chat_completions(request: Request):
        host = request.url.hostname
        payload = await request.json()
        stream = bool(payload.get("stream"))
        message = payload.get("messages", [{}])[0].get("content") if payload.get("messages") else None

        if message == "authfail":
            return JSONResponse(status_code=401, content={"error": {"message": "bad key"}})

        if host == "relay-a.example.com" and not stream:
            return JSONResponse(status_code=503, content={"error": "unavailable"})

        if host == "relay-a.example.com" and stream:
            async def broken_stream() -> AsyncIterator[bytes]:
                raise httpx.ReadTimeout("timeout before first chunk")
                yield b""

            return StreamingResponse(broken_stream(), media_type="text/event-stream")

        if host == "relay-b.example.com" and stream:
            async def ok_stream() -> AsyncIterator[bytes]:
                yield b'data: {"type":"response.output_text.delta","delta":"hello"}\n\n'
                yield b"data: [DONE]\n\n"

            return StreamingResponse(ok_stream(), media_type="text/event-stream")

        return JSONResponse(
            {
                "id": "chatcmpl-test",
                "object": "chat.completion",
                "model": payload["model"],
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"}}],
            }
        )

    @app.post("/v1/responses")
    async def responses(request: Request):
        payload = await request.json()
        return JSONResponse(
            {
                "id": "resp-test",
                "object": "response",
                "model": payload["model"],
                "output": [{"type": "message", "content": [{"type": "output_text", "text": "ok"}]}],
            }
        )

    return app


def test_non_stream_request_fails_over_to_next_provider(workspace_tmp_dir: Path) -> None:
    app = create_app(write_config(workspace_tmp_dir), transport=httpx.ASGITransport(app=build_upstream_app()))

    with TestClient(app) as client:
        response = client.post(
            "/v1/chat/completions",
            json={"model": "gpt-4.1", "messages": [{"role": "user", "content": "hi"}]},
        )

        assert response.status_code == 200
        assert response.json()["model"] == "gpt-4.1"


def test_stream_request_retries_before_first_chunk(workspace_tmp_dir: Path) -> None:
    app = create_app(write_config(workspace_tmp_dir), transport=httpx.ASGITransport(app=build_upstream_app()))

    with TestClient(app) as client:
        with client.stream(
            "POST",
            "/v1/chat/completions",
            json={"model": "gpt-4.1", "stream": True, "messages": [{"role": "user", "content": "hi"}]},
        ) as response:
            body = b"".join(response.iter_raw())

        assert response.status_code == 200
        assert b"response.output_text.delta" in body
        assert b"[DONE]" in body


def test_models_endpoint_returns_explicit_union(workspace_tmp_dir: Path) -> None:
    app = create_app(write_config(workspace_tmp_dir), transport=httpx.ASGITransport(app=build_upstream_app()))

    with TestClient(app) as client:
        response = client.get("/v1/models")

        assert response.status_code == 200
        payload = response.json()
        assert payload["object"] == "list"
        assert [item["id"] for item in payload["data"]] == ["gpt-4.1"]


def test_responses_endpoint_proxies_successfully(workspace_tmp_dir: Path) -> None:
    app = create_app(write_config(workspace_tmp_dir), transport=httpx.ASGITransport(app=build_upstream_app()))

    with TestClient(app) as client:
        response = client.post(
            "/v1/responses",
            json={"model": "gpt-4.1", "input": "hello"},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["object"] == "response"
        assert payload["model"] == "gpt-4.1"


def test_invalid_json_returns_openai_style_error(workspace_tmp_dir: Path) -> None:
    app = create_app(write_config(workspace_tmp_dir), transport=httpx.ASGITransport(app=build_upstream_app()))

    with TestClient(app) as client:
        response = client.post(
            "/v1/chat/completions",
            content=json.dumps(["not", "an", "object"]),
            headers={"content-type": "application/json"},
        )

        assert response.status_code == 400
        assert response.json()["error"]["code"] == "invalid_json"


def test_non_stream_non_retryable_response_is_logged_as_error(workspace_tmp_dir: Path) -> None:
    app = create_app(write_config(workspace_tmp_dir), transport=httpx.ASGITransport(app=build_upstream_app()))

    with TestClient(app) as client:
        response = client.post(
            "/v1/chat/completions",
            json={"model": "gpt-4.1", "messages": [{"role": "user", "content": "authfail"}]},
        )
        dashboard = client.get("/admin/api/dashboard").json()
        metrics = client.get("/admin/api/metrics?window=24h").json()

    assert response.status_code == 401
    assert response.json()["error"]["message"] == "bad key"
    assert dashboard["recent_requests"][0]["final_provider"] == "relay_a"
    assert dashboard["recent_requests"][0]["state"] == "error"
    assert dashboard["recent_requests"][0]["error"] == "bad key"
    assert dashboard["stats"]["global"]["served_requests"] == 1
    assert dashboard["stats"]["global"]["successful_requests"] == 0
    assert dashboard["stats"]["global"]["success_rate"] == 0.0
    states = {item["state"]: item["count"] for item in metrics["breakdowns"]["states"]}
    assert states["success"] == 0
    assert states["error"] == 1


def test_stream_non_retryable_response_is_logged_as_error_before_stream_starts(workspace_tmp_dir: Path) -> None:
    app = create_app(write_config(workspace_tmp_dir), transport=httpx.ASGITransport(app=build_upstream_app()))

    with TestClient(app) as client:
        with client.stream(
            "POST",
            "/v1/chat/completions",
            json={"model": "gpt-4.1", "stream": True, "messages": [{"role": "user", "content": "authfail"}]},
        ) as response:
            body = b"".join(response.iter_raw())
        dashboard = client.get("/admin/api/dashboard").json()
        metrics = client.get("/admin/api/metrics?window=24h").json()

    assert response.status_code == 401
    assert b"bad key" in body
    assert dashboard["recent_requests"][0]["final_provider"] == "relay_a"
    assert dashboard["recent_requests"][0]["state"] == "error"
    assert dashboard["stats"]["global"]["served_requests"] == 1
    assert dashboard["stats"]["global"]["successful_requests"] == 0
    states = {item["state"]: item["count"] for item in metrics["breakdowns"]["states"]}
    assert states["success"] == 0
    assert states["error"] == 1
