from __future__ import annotations

import asyncio
from pathlib import Path
import uuid

import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

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
    path = base_dir / f"concurrency-{uuid.uuid4().hex}"
    path.mkdir()
    return path


def build_upstream_app() -> FastAPI:
    app = FastAPI()

    @app.post("/v1/chat/completions")
    async def chat_completions(request: Request):
        payload = await request.json()
        await asyncio.sleep(0.05)
        return JSONResponse(
            {
                "id": "chatcmpl-concurrency",
                "object": "chat.completion",
                "model": payload["model"],
                "usage": {
                    "prompt_tokens": 1,
                    "completion_tokens": 1,
                    "total_tokens": 2,
                },
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"}}],
            }
        )

    return app


@pytest.mark.anyio
async def test_concurrent_requests_keep_dashboard_and_metrics_consistent(workspace_tmp_dir: Path) -> None:
    app = create_app(
        write_config(workspace_tmp_dir),
        transport=httpx.ASGITransport(app=build_upstream_app()),
    )

    transport = httpx.ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            responses = await asyncio.gather(
                *[
                    client.post(
                        "/v1/chat/completions",
                        json={
                            "model": "gpt-4.1",
                            "messages": [{"role": "user", "content": f"hello-{index}"}],
                        },
                    )
                    for index in range(20)
                ]
            )
            dashboard = (await client.get("/admin/api/dashboard")).json()
            metrics = (await client.get("/admin/api/metrics?window=24h")).json()

    assert all(response.status_code == 200 for response in responses)
    assert len(dashboard["recent_requests"]) == 20
    assert dashboard["stats"]["global"]["served_requests"] == 20
    assert dashboard["stats"]["global"]["successful_requests"] == 20
    assert dashboard["stats"]["global"]["total_tokens"] == 40
    assert metrics["summary"]["requests"] == 20
    assert metrics["summary"]["total_tokens"] == 40
    states = {item["state"]: item["count"] for item in metrics["breakdowns"]["states"]}
    assert states["success"] == 20
    assert states["interrupted"] == 0
    assert states["error"] == 0
