from __future__ import annotations

from pathlib import Path
import uuid

import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from vibecoding_board.app import create_app
from vibecoding_board.config import ProxyConfig, dump_proxy_config, load_proxy_config


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
                    "models": ["gpt-4.1", "gpt-4o-mini"],
                    "timeout_seconds": 20,
                    "max_failures": 3,
                    "cooldown_seconds": 45,
                },
            ],
        }
    )


def write_config(tmp_path: Path, config: ProxyConfig | None = None) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(dump_proxy_config(config or build_config()), encoding="utf-8")
    return path


@pytest.fixture
def workspace_tmp_dir() -> Path:
    base_dir = Path.cwd() / "test-workspaces"
    base_dir.mkdir(exist_ok=True)
    path = base_dir / f"admin-{uuid.uuid4().hex}"
    path.mkdir()
    return path


def build_upstream_app() -> FastAPI:
    app = FastAPI()

    @app.post("/v1/chat/completions")
    async def chat_completions(request: Request):
        host = request.url.hostname
        payload = await request.json()
        return JSONResponse(
            {
                "id": "chatcmpl-admin",
                "object": "chat.completion",
                "model": payload["model"],
                "usage": {
                    "prompt_tokens": 7,
                    "completion_tokens": 2,
                    "total_tokens": 9,
                },
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": host},
                    }
                ],
            }
        )

    @app.post("/v1/responses")
    async def responses(request: Request):
        payload = await request.json()
        return JSONResponse(
            {
                "id": "resp-admin",
                "object": "response",
                "model": payload["model"],
                "usage": {
                    "input_tokens": 5,
                    "output_tokens": 3,
                    "total_tokens": 8,
                },
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": request.url.hostname}],
                    }
                ],
            }
        )

    return app


def test_dashboard_redacts_api_keys(workspace_tmp_dir: Path) -> None:
    app = create_app(write_config(workspace_tmp_dir), transport=httpx.ASGITransport(app=build_upstream_app()))

    with TestClient(app) as client:
        client.post(
            "/v1/chat/completions",
            json={"model": "gpt-4.1", "messages": [{"role": "user", "content": "hi"}]},
        )
        response = client.get("/admin/api/dashboard")

        assert response.status_code == 200
        payload = response.json()
        assert payload["primary_provider"] == "relay_a"
        assert all("api_key" not in provider for provider in payload["providers"])
        assert all(provider["has_api_key"] is True for provider in payload["providers"])
        assert payload["recent_requests"][0]["final_provider"] == "relay_a"
        assert payload["recent_requests"][0]["final_url"] == "https://relay-a.example.com/v1/chat/completions"
        assert payload["recent_requests"][0]["usage"]["total_tokens"] == 9
        assert payload["recent_requests"][0]["ttfb_ms"] is not None
        assert payload["stats"]["providers"][0]["provider_name"] == "relay_a"
        assert payload["stats"]["providers"][0]["served_requests"] == 1
        assert payload["stats"]["providers"][0]["total_tokens"] == 9
        assert payload["stats"]["global"]["total_tokens"] == 9


def test_promote_provider_writes_config_and_changes_routing(workspace_tmp_dir: Path) -> None:
    config_path = write_config(workspace_tmp_dir)
    app = create_app(config_path, transport=httpx.ASGITransport(app=build_upstream_app()))

    with TestClient(app) as client:
        initial = client.post(
            "/v1/chat/completions",
            json={"model": "gpt-4.1", "messages": [{"role": "user", "content": "hi"}]},
        )
        assert initial.json()["choices"][0]["message"]["content"] == "relay-a.example.com"

        promoted = client.post("/admin/api/providers/relay_b/promote")
        assert promoted.status_code == 200
        assert promoted.json()["dashboard"]["primary_provider"] == "relay_b"

        after = client.post(
            "/v1/chat/completions",
            json={"model": "gpt-4.1", "messages": [{"role": "user", "content": "hi"}]},
        )
        assert after.json()["choices"][0]["message"]["content"] == "relay-b.example.com"

    saved = load_proxy_config(config_path)
    assert [provider.name for provider in sorted(saved.providers, key=lambda p: p.priority)] == [
        "relay_b",
        "relay_a",
    ]


def test_update_provider_preserves_existing_api_key_when_blank(workspace_tmp_dir: Path) -> None:
    config_path = write_config(workspace_tmp_dir)
    app = create_app(config_path, transport=httpx.ASGITransport(app=build_upstream_app()))

    with TestClient(app) as client:
        response = client.put(
            "/admin/api/providers/relay_a",
            json={
                "name": "relay_a_renamed",
                "base_url": "https://relay-a-2.example.com/v1",
                "api_key": "",
                "enabled": True,
                "priority": 10,
                "models": ["gpt-4.1", "gpt-4o-mini"],
                "healthcheck_model": "gpt-4.1",
                "timeout_seconds": 15,
                "max_failures": 4,
                "cooldown_seconds": 50,
            },
        )

        assert response.status_code == 200
        providers = response.json()["dashboard"]["providers"]
        assert providers[0]["name"] == "relay_a_renamed"

    saved = load_proxy_config(config_path)
    renamed = next(provider for provider in saved.providers if provider.name == "relay_a_renamed")
    assert renamed.api_key == "key-a"
    assert renamed.base_url == "https://relay-a-2.example.com/v1"
    assert renamed.healthcheck_model == "gpt-4.1"


def test_update_provider_priority_writes_config_and_changes_routing(workspace_tmp_dir: Path) -> None:
    config_path = write_config(workspace_tmp_dir)
    app = create_app(config_path, transport=httpx.ASGITransport(app=build_upstream_app()))

    with TestClient(app) as client:
        initial = client.post(
            "/v1/chat/completions",
            json={"model": "gpt-4.1", "messages": [{"role": "user", "content": "hi"}]},
        )
        assert initial.json()["choices"][0]["message"]["content"] == "relay-a.example.com"

        updated = client.put(
            "/admin/api/providers/relay_b",
            json={
                "name": "relay_b",
                "base_url": "https://relay-b.example.com/v1",
                "api_key": "",
                "enabled": True,
                "priority": 5,
                "models": ["gpt-4.1", "gpt-4o-mini"],
                "healthcheck_model": None,
                "timeout_seconds": 20,
                "max_failures": 3,
                "cooldown_seconds": 45,
            },
        )

        assert updated.status_code == 200
        assert updated.json()["dashboard"]["primary_provider"] == "relay_b"

        after = client.post(
            "/v1/chat/completions",
            json={"model": "gpt-4.1", "messages": [{"role": "user", "content": "hi"}]},
        )
        assert after.json()["choices"][0]["message"]["content"] == "relay-b.example.com"

    saved = load_proxy_config(config_path)
    assert [provider.name for provider in sorted(saved.providers, key=lambda p: p.priority)] == [
        "relay_b",
        "relay_a",
    ]


def test_patch_provider_priority_writes_config_and_changes_routing(workspace_tmp_dir: Path) -> None:
    config_path = write_config(workspace_tmp_dir)
    app = create_app(config_path, transport=httpx.ASGITransport(app=build_upstream_app()))

    with TestClient(app) as client:
        initial = client.post(
            "/v1/chat/completions",
            json={"model": "gpt-4.1", "messages": [{"role": "user", "content": "hi"}]},
        )
        assert initial.json()["choices"][0]["message"]["content"] == "relay-a.example.com"

        updated = client.patch(
            "/admin/api/providers/relay_b/priority",
            json={"priority": 5},
        )

        assert updated.status_code == 200
        assert updated.json()["dashboard"]["primary_provider"] == "relay_b"

        after = client.post(
            "/v1/chat/completions",
            json={"model": "gpt-4.1", "messages": [{"role": "user", "content": "hi"}]},
        )
        assert after.json()["choices"][0]["message"]["content"] == "relay-b.example.com"

    saved = load_proxy_config(config_path)
    relay_b = next(provider for provider in saved.providers if provider.name == "relay_b")
    assert relay_b.priority == 5


def test_create_provider_writes_to_config(workspace_tmp_dir: Path) -> None:
    config_path = write_config(workspace_tmp_dir)
    app = create_app(config_path, transport=httpx.ASGITransport(app=build_upstream_app()))

    with TestClient(app) as client:
        response = client.post(
            "/admin/api/providers",
            json={
                "name": "relay_c",
                "base_url": "https://relay-c.example.com/v1",
                "api_key": "key-c",
                "enabled": True,
                "priority": 30,
                "models": ["*"],
                "healthcheck_model": "gpt-4o-mini",
                "timeout_seconds": 25,
                "max_failures": 2,
                "cooldown_seconds": 40,
            },
        )

        assert response.status_code == 200
        assert any(provider["name"] == "relay_c" for provider in response.json()["dashboard"]["providers"])

    saved = load_proxy_config(config_path)
    assert {provider.name for provider in saved.providers} == {"relay_a", "relay_b", "relay_c"}
    created = next(provider for provider in saved.providers if provider.name == "relay_c")
    assert created.healthcheck_model == "gpt-4o-mini"


def test_create_provider_returns_localized_message_when_locale_is_chinese(workspace_tmp_dir: Path) -> None:
    config_path = write_config(workspace_tmp_dir)
    app = create_app(config_path, transport=httpx.ASGITransport(app=build_upstream_app()))

    with TestClient(app) as client:
        response = client.post(
            "/admin/api/providers",
            headers={"x-admin-locale": "zh-CN"},
            json={
                "name": "relay_c",
                "base_url": "https://relay-c.example.com/v1",
                "api_key": "key-c",
                "enabled": True,
                "priority": 30,
                "models": ["*"],
                "healthcheck_model": "gpt-4o-mini",
                "timeout_seconds": 25,
                "max_failures": 2,
                "cooldown_seconds": 40,
            },
        )

        assert response.status_code == 200
        assert response.json()["message"] == "已添加 Provider relay_c。"


def test_delete_last_provider_is_rejected(workspace_tmp_dir: Path) -> None:
    config = ProxyConfig.model_validate(
        {
            "listen": {"host": "127.0.0.1", "port": 9000},
            "providers": [
                {
                    "name": "relay_only",
                    "base_url": "https://relay-only.example.com/v1",
                    "api_key": "key-only",
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
    app = create_app(write_config(workspace_tmp_dir, config), transport=httpx.ASGITransport(app=build_upstream_app()))

    with TestClient(app) as client:
        response = client.delete("/admin/api/providers/relay_only")

        assert response.status_code == 400
        assert "At least one provider" in response.json()["detail"]


def test_delete_last_provider_error_is_localized_when_locale_is_chinese(workspace_tmp_dir: Path) -> None:
    config = ProxyConfig.model_validate(
        {
            "listen": {"host": "127.0.0.1", "port": 9000},
            "providers": [
                {
                    "name": "relay_only",
                    "base_url": "https://relay-only.example.com/v1",
                    "api_key": "key-only",
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
    app = create_app(write_config(workspace_tmp_dir, config), transport=httpx.ASGITransport(app=build_upstream_app()))

    with TestClient(app) as client:
        response = client.delete(
            "/admin/api/providers/relay_only",
            headers={"x-admin-locale": "zh-CN"},
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "至少需要保留一个已配置的 Provider。"


def test_manual_healthcheck_updates_provider_state_without_logging_request(workspace_tmp_dir: Path) -> None:
    app = create_app(write_config(workspace_tmp_dir), transport=httpx.ASGITransport(app=build_upstream_app()))

    with TestClient(app) as client:
        response = client.post("/admin/api/providers/relay_a/healthcheck")

        assert response.status_code == 200
        payload = response.json()["dashboard"]
        provider = next(item for item in payload["providers"] if item["name"] == "relay_a")
        assert provider["healthcheck"]["ok"] is True
        assert provider["healthcheck"]["model"] == "gpt-4.1"
        assert payload["recent_requests"] == []


def test_healthcheck_requires_model_for_wildcard_provider(workspace_tmp_dir: Path) -> None:
    config = ProxyConfig.model_validate(
        {
            "listen": {"host": "127.0.0.1", "port": 9000},
            "providers": [
                {
                    "name": "relay_any",
                    "base_url": "https://relay-any.example.com/v1",
                    "api_key": "key-any",
                    "enabled": True,
                    "priority": 10,
                    "models": ["*"],
                    "timeout_seconds": 10,
                    "max_failures": 2,
                    "cooldown_seconds": 30,
                }
            ],
        }
    )
    app = create_app(write_config(workspace_tmp_dir, config), transport=httpx.ASGITransport(app=build_upstream_app()))

    with TestClient(app) as client:
        response = client.post("/admin/api/providers/relay_any/healthcheck")

        assert response.status_code == 400
        assert "healthcheck_model" in response.json()["detail"]
