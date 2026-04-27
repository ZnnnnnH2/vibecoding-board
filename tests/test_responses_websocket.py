from __future__ import annotations

import asyncio
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import socket
import tempfile
from threading import Event, Thread
import time
import uuid

import pytest
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient
import uvicorn
from websockets.sync.client import connect as websocket_connect_sync

from vibecoding_board import service as service_module
from vibecoding_board.app import create_app
from vibecoding_board.config import ProxyConfig, dump_proxy_config
from vibecoding_board.service import (
    BUFFER_OVERFLOW_TERMINAL_REASON,
    RESPONSES_WEBSOCKET_BETA,
    TURN_STATE_HEADER,
    WS_UNSUPPORTED_STATUS_CODES,
)


@dataclass(slots=True)
class ResponsesUpstreamState:
    ws_accepts: int = 0
    ws_requests: list[dict[str, object]] = field(default_factory=list)
    http_requests: list[dict[str, object]] = field(default_factory=list)
    ws_handshake_headers: list[dict[str, str]] = field(default_factory=list)
    first_delta_sent: Event = field(default_factory=Event)
    release_missed_delta: Event = field(default_factory=Event)
    missed_delta_sent: Event = field(default_factory=Event)
    release_completion: Event = field(default_factory=Event)


def build_provider_config(
    *,
    name: str,
    upstream_base_url: str,
    supports_responses_websocket: bool,
    priority: int = 10,
    timeout_seconds: float = 10,
) -> dict[str, object]:
    return {
        "name": name,
        "base_url": upstream_base_url,
        "api_key": f"key-{name}",
        "enabled": True,
        "priority": priority,
        "models": ["gpt-4.1"],
        "timeout_seconds": timeout_seconds,
        "max_failures": 2,
        "cooldown_seconds": 30,
        "supports_responses_websocket": supports_responses_websocket,
    }


def build_proxy_config(
    *providers: dict[str, object],
    responses_websocket_enabled: bool = True,
) -> ProxyConfig:
    return ProxyConfig.model_validate(
        {
            "listen": {"host": "127.0.0.1", "port": 9000},
            "responses_websocket": {"enabled": responses_websocket_enabled},
            "providers": list(providers),
        }
    )


def build_config(
    *,
    upstream_base_url: str,
    supports_responses_websocket: bool,
    timeout_seconds: float = 10,
) -> ProxyConfig:
    return build_proxy_config(
        build_provider_config(
            name="relay_a",
            upstream_base_url=upstream_base_url,
            supports_responses_websocket=supports_responses_websocket,
            timeout_seconds=timeout_seconds,
        )
    )


def write_config(tmp_path: Path, config: ProxyConfig) -> Path:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(dump_proxy_config(config), encoding="utf-8")
    return config_path


@pytest.fixture
def workspace_tmp_dir() -> Path:
    base_dir = (Path(__file__).resolve().parent / ".responses-ws-workspaces").resolve()
    base_dir.mkdir(parents=True, exist_ok=True)
    path = base_dir / f"responses-ws-{uuid.uuid4().hex}"
    path.mkdir()
    return path


def build_responses_websocket_upstream(state: ResponsesUpstreamState) -> FastAPI:
    app = FastAPI()

    @app.websocket("/v1/responses")
    async def responses_ws(websocket: WebSocket):
        state.ws_accepts += 1
        state.ws_handshake_headers.append({key.lower(): value for key, value in websocket.headers.items()})
        await websocket.accept()
        try:
            while True:
                raw_message = await websocket.receive_text()
                payload = json.loads(raw_message)
                state.ws_requests.append(payload)
                previous_response_id = payload.get("previous_response_id")
                response_id = "resp-2" if previous_response_id else "resp-1"
                delta = "turn-2" if previous_response_id else "turn-1"

                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "response.created",
                            "response": {"id": response_id, "model": payload["model"]},
                        }
                    )
                )
                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "response.output_text.delta",
                            "delta": delta,
                        }
                    )
                )
                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "response.completed",
                            "response": {
                                "id": response_id,
                                "model": payload["model"],
                                "usage": {
                                    "input_tokens": 5,
                                    "output_tokens": 3,
                                    "total_tokens": 8,
                                },
                            },
                        }
                    )
                )
        except WebSocketDisconnect:
            return

    return app


def build_resumable_responses_websocket_upstream(state: ResponsesUpstreamState) -> FastAPI:
    app = FastAPI()

    @app.websocket("/v1/responses")
    async def responses_ws(websocket: WebSocket):
        state.ws_accepts += 1
        state.ws_handshake_headers.append({key.lower(): value for key, value in websocket.headers.items()})
        await websocket.accept()
        try:
            while True:
                raw_message = await websocket.receive_text()
                payload = json.loads(raw_message)
                state.ws_requests.append(payload)

                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "response.created",
                            "response": {"id": "resp-live-1", "model": payload["model"]},
                        }
                    )
                )
                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "response.output_text.delta",
                            "delta": "turn-1a",
                        }
                    )
                )
                state.first_delta_sent.set()
                await asyncio.to_thread(state.release_missed_delta.wait, 5.0)
                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "response.output_text.delta",
                            "delta": "turn-1b",
                        }
                    )
                )
                state.missed_delta_sent.set()
                await asyncio.to_thread(state.release_completion.wait, 5.0)
                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "response.output_text.delta",
                            "delta": "turn-1c",
                        }
                    )
                )
                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "response.completed",
                            "response": {
                                "id": "resp-live-1",
                                "model": payload["model"],
                                "usage": {
                                    "input_tokens": 5,
                                    "output_tokens": 3,
                                    "total_tokens": 8,
                                },
                            },
                        }
                    )
                )
        except WebSocketDisconnect:
            return

    return app


def build_responses_http_only_upstream(state: ResponsesUpstreamState) -> FastAPI:
    app = FastAPI()

    @app.post("/v1/responses")
    async def responses(request: Request):
        payload = await request.json()
        state.http_requests.append(payload)
        response_number = len(state.http_requests)

        async def event_stream():
            yield (
                "data: "
                + json.dumps(
                    {
                        "type": "response.created",
                        "response": {"id": f"resp-http-{response_number}", "model": payload["model"]},
                    }
                )
                + "\n\n"
            ).encode("utf-8")
            yield (
                "data: "
                + json.dumps(
                    {
                        "type": "response.output_text.delta",
                        "delta": f"http-turn-{response_number}",
                    }
                )
                + "\n\n"
            ).encode("utf-8")
            yield (
                "data: "
                + json.dumps(
                    {
                        "type": "response.completed",
                        "response": {
                            "id": f"resp-http-{response_number}",
                            "model": payload["model"],
                            "usage": {
                                "input_tokens": 4,
                                "output_tokens": 2,
                                "total_tokens": 6,
                            },
                        },
                    }
                )
                + "\n\n"
            ).encode("utf-8")
            yield b"data: [DONE]\n\n"

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    return app


def receive_until_terminal(websocket) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    while True:
        event = json.loads(websocket.receive_text())
        events.append(event)
        if event["type"] in {"response.completed", "response.failed", "error"}:
            return events


def websocket_header_map(websocket) -> dict[str, str]:
    return {
        key.decode("latin-1").lower(): value.decode("latin-1")
        for key, value in (websocket.extra_headers or [])
    }


def test_responses_websocket_requires_global_manual_enable(
    workspace_tmp_dir: Path,
) -> None:
    app = create_app(
        write_config(
            workspace_tmp_dir,
            build_proxy_config(
                build_provider_config(
                    name="relay_a",
                    upstream_base_url="https://relay-a.example.com/v1",
                    supports_responses_websocket=True,
                ),
                responses_websocket_enabled=False,
            ),
        )
    )

    with TestClient(app) as client:
        with client.websocket_connect("/v1/responses") as websocket:
            event = json.loads(websocket.receive_text())

    assert event["type"] == "error"
    assert event["error"]["code"] == "responses_websocket_disabled"
    assert "Enable it in admin settings first" in event["error"]["message"]


def wait_for(predicate, *, timeout: float = 5.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("condition was not met before timeout")


def build_turn_client_metadata(turn_id: str) -> dict[str, str]:
    return {
        "x-codex-turn-metadata": json.dumps({"turn_id": turn_id}),
    }


@contextmanager
def run_uvicorn_app(app: FastAPI):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]

    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host="127.0.0.1",
            port=port,
            log_level="warning",
        )
    )
    thread = Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 5.0
    while time.time() < deadline:
        if getattr(server, "started", False):
            break
        time.sleep(0.02)
    if not getattr(server, "started", False):
        server.should_exit = True
        thread.join(timeout=5.0)
        raise RuntimeError("uvicorn test server did not start")

    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=5.0)


def test_responses_websocket_reuses_upstream_websocket_and_preserves_sticky_provider(
    workspace_tmp_dir: Path,
) -> None:
    upstream_state = ResponsesUpstreamState()
    upstream_app = build_responses_websocket_upstream(upstream_state)

    with run_uvicorn_app(upstream_app) as upstream_base_url:
        app = create_app(
            write_config(
                workspace_tmp_dir,
                build_config(
                    upstream_base_url=f"{upstream_base_url}/v1",
                    supports_responses_websocket=True,
                ),
            )
        )

        with TestClient(app) as client:
            with client.websocket_connect(
                "/v1/responses",
                headers={"openai-beta": RESPONSES_WEBSOCKET_BETA},
            ) as websocket:
                websocket.send_text(
                    json.dumps(
                        {
                            "type": "response.create",
                            "model": "gpt-4.1",
                            "input": "turn-1",
                        }
                    )
                )
                first_events = receive_until_terminal(websocket)
                assert first_events[0]["type"] == "response.created"
                assert first_events[0]["response"]["id"] == "resp-1"

                websocket.send_text(
                    json.dumps(
                        {
                            "type": "response.create",
                            "model": "gpt-4.1",
                            "previous_response_id": "resp-1",
                            "input": "turn-2",
                        }
                    )
                )
                second_events = receive_until_terminal(websocket)
                assert second_events[0]["type"] == "response.created"
                assert second_events[0]["response"]["id"] == "resp-2"

            dashboard = client.get("/admin/api/dashboard").json()

    assert upstream_state.ws_accepts == 1
    assert len(upstream_state.ws_requests) == 2
    assert upstream_state.ws_requests[1]["previous_response_id"] == "resp-1"
    assert dashboard["recent_requests"][0]["final_provider"] == "relay_a"


def test_responses_websocket_new_turn_without_previous_response_id_does_not_inherit_provider_pin(
    workspace_tmp_dir: Path,
) -> None:
    relay_a_state = ResponsesUpstreamState()
    relay_b_state = ResponsesUpstreamState()
    relay_a_app = build_responses_websocket_upstream(relay_a_state)
    relay_b_app = build_responses_websocket_upstream(relay_b_state)

    with run_uvicorn_app(relay_a_app) as relay_a_base_url, run_uvicorn_app(
        relay_b_app
    ) as relay_b_base_url:
        app = create_app(
            write_config(
                workspace_tmp_dir,
                build_proxy_config(
                    build_provider_config(
                        name="relay_a",
                        upstream_base_url=f"{relay_a_base_url}/v1",
                        supports_responses_websocket=True,
                        priority=10,
                    ),
                    build_provider_config(
                        name="relay_b",
                        upstream_base_url=f"{relay_b_base_url}/v1",
                        supports_responses_websocket=True,
                        priority=20,
                    ),
                ),
            )
        )

        with TestClient(app) as client:
            with client.websocket_connect(
                "/v1/responses",
                headers={"openai-beta": RESPONSES_WEBSOCKET_BETA},
            ) as websocket:
                websocket.send_text(
                    json.dumps(
                        {
                            "type": "response.create",
                            "model": "gpt-4.1",
                            "input": "turn-1",
                            "client_metadata": build_turn_client_metadata("turn-1"),
                        }
                    )
                )
                first_events = receive_until_terminal(websocket)
                assert first_events[0]["type"] == "response.created"

                relay_a_registry_state = (
                    app.state.service.runtime_manager.current().registry._states["relay_a"]
                )
                relay_a_registry_state.cooldown_until = datetime.now(UTC) + timedelta(seconds=60)
                relay_a_registry_state.consecutive_failures = (
                    relay_a_registry_state.provider.max_failures
                )
                relay_a_registry_state.last_error = "forced unavailable in test"

                websocket.send_text(
                    json.dumps(
                        {
                            "type": "response.create",
                            "model": "gpt-4.1",
                            "input": "turn-2",
                            "client_metadata": build_turn_client_metadata("turn-2"),
                        }
                    )
                )
                second_events = receive_until_terminal(websocket)
                assert second_events[0]["type"] == "response.created"

            dashboard = client.get("/admin/api/dashboard").json()

    assert relay_a_state.ws_accepts == 1
    assert relay_b_state.ws_accepts == 1
    assert len(relay_a_state.ws_requests) == 1
    assert len(relay_b_state.ws_requests) == 1
    assert relay_a_state.ws_requests[0]["client_metadata"] == build_turn_client_metadata("turn-1")
    assert relay_b_state.ws_requests[0]["client_metadata"] == build_turn_client_metadata("turn-2")
    assert dashboard["recent_requests"][0]["final_provider"] == "relay_b"


def test_responses_websocket_returns_error_when_upstream_websocket_transport_is_unsupported(
    workspace_tmp_dir: Path,
) -> None:
    upstream_state = ResponsesUpstreamState()
    upstream_app = build_responses_http_only_upstream(upstream_state)

    with run_uvicorn_app(upstream_app) as upstream_base_url:
        app = create_app(
            write_config(
                workspace_tmp_dir,
                build_config(
                    upstream_base_url=f"{upstream_base_url}/v1",
                    supports_responses_websocket=True,
                ),
            )
        )

        with TestClient(app) as client:
            with client.websocket_connect(
                "/v1/responses",
                headers={"openai-beta": RESPONSES_WEBSOCKET_BETA},
            ) as websocket:
                websocket.send_text(
                    json.dumps(
                        {
                            "type": "response.create",
                            "model": "gpt-4.1",
                            "input": "first",
                        }
                    )
                )
                event = json.loads(websocket.receive_text())

            dashboard = client.get("/admin/api/dashboard").json()

    assert event["type"] == "error"
    assert event["status"] == 503
    assert event["error"]["code"] == "upstream_unavailable"
    assert "websocket" in event["error"]["message"].lower()
    assert len(upstream_state.http_requests) == 0
    relay_a = next(provider for provider in dashboard["providers"] if provider["name"] == "relay_a")
    assert relay_a["ws_unsupported"] is True


def test_responses_websocket_returns_error_when_sticky_provider_is_unavailable(
    workspace_tmp_dir: Path,
) -> None:
    upstream_state = ResponsesUpstreamState()
    upstream_app = build_responses_websocket_upstream(upstream_state)

    with run_uvicorn_app(upstream_app) as upstream_base_url:
        app = create_app(
            write_config(
                workspace_tmp_dir,
                build_config(
                    upstream_base_url=f"{upstream_base_url}/v1",
                    supports_responses_websocket=True,
                ),
            )
        )

        with TestClient(app) as client:
            with client.websocket_connect(
                "/v1/responses",
                headers={"openai-beta": RESPONSES_WEBSOCKET_BETA},
            ) as websocket:
                websocket.send_text(
                    json.dumps(
                        {
                            "type": "response.create",
                            "model": "gpt-4.1",
                            "input": "first",
                        }
                    )
                )
                first_events = receive_until_terminal(websocket)
                assert first_events[0]["response"]["id"] == "resp-1"

            toggle = client.post("/admin/api/providers/relay_a/toggle")
            assert toggle.status_code == 200

            with client.websocket_connect(
                "/v1/responses",
                headers={"openai-beta": RESPONSES_WEBSOCKET_BETA},
            ) as websocket:
                websocket.send_text(
                    json.dumps(
                        {
                            "type": "response.create",
                            "model": "gpt-4.1",
                            "previous_response_id": "resp-1",
                            "input": "second",
                        }
                    )
                )
                event = json.loads(websocket.receive_text())

    assert event["type"] == "error"
    assert event["status"] == 409
    assert event["error"]["code"] == "response_context_unavailable"
    assert len(upstream_state.ws_requests) == 1


def test_responses_websocket_handshake_returns_turn_state_and_resumed_handshake_echoes_it(
    workspace_tmp_dir: Path,
) -> None:
    upstream_state = ResponsesUpstreamState()
    upstream_app = build_responses_websocket_upstream(upstream_state)

    with run_uvicorn_app(upstream_app) as upstream_base_url:
        app = create_app(
            write_config(
                workspace_tmp_dir,
                build_config(
                    upstream_base_url=f"{upstream_base_url}/v1",
                    supports_responses_websocket=True,
                ),
            )
        )

        with TestClient(app) as client:
            with client.websocket_connect(
                "/v1/responses",
                headers={"openai-beta": RESPONSES_WEBSOCKET_BETA},
            ) as websocket:
                turn_state_token = websocket_header_map(websocket)[TURN_STATE_HEADER]

            with client.websocket_connect(
                "/v1/responses",
                headers={
                    "openai-beta": RESPONSES_WEBSOCKET_BETA,
                    TURN_STATE_HEADER: turn_state_token,
                },
            ) as websocket:
                resumed_turn_state_token = websocket_header_map(websocket)[TURN_STATE_HEADER]

    assert resumed_turn_state_token == turn_state_token


def test_responses_websocket_reconnects_with_turn_state_and_only_forwards_new_events(
    workspace_tmp_dir: Path,
) -> None:
    upstream_state = ResponsesUpstreamState()
    upstream_app = build_resumable_responses_websocket_upstream(upstream_state)

    with run_uvicorn_app(upstream_app) as upstream_base_url:
        board_app = create_app(
            write_config(
                workspace_tmp_dir,
                build_config(
                    upstream_base_url=f"{upstream_base_url}/v1",
                    supports_responses_websocket=True,
                ),
            )
        )

        with run_uvicorn_app(board_app) as board_base_url:
            websocket_url = f"{board_base_url.replace('http://', 'ws://')}/v1/responses"
            with websocket_connect_sync(
                websocket_url,
                additional_headers={"openai-beta": RESPONSES_WEBSOCKET_BETA},
                open_timeout=5,
                close_timeout=1,
            ) as websocket:
                turn_state_token = websocket.response.headers[TURN_STATE_HEADER]
                assert turn_state_token
                websocket.send(
                    json.dumps(
                        {
                            "type": "response.create",
                            "model": "gpt-4.1",
                            "input": "turn-1",
                        }
                    )
                )
                first_event = json.loads(websocket.recv(timeout=5))

            assert first_event["type"] == "response.created"
            assert upstream_state.first_delta_sent.wait(timeout=5.0)
            wait_for(
                lambda: board_app.state.service.turn_state_store._entries[turn_state_token].attached_websocket is None
            )
            upstream_state.release_missed_delta.set()
            assert upstream_state.missed_delta_sent.wait(timeout=5.0)

            with websocket_connect_sync(
                websocket_url,
                additional_headers={
                    "openai-beta": RESPONSES_WEBSOCKET_BETA,
                    TURN_STATE_HEADER: turn_state_token,
                },
                open_timeout=5,
                close_timeout=1,
            ) as resumed_websocket:
                assert resumed_websocket.response.headers[TURN_STATE_HEADER] == turn_state_token
                upstream_state.release_completion.set()
                resumed_events = []
                while True:
                    event = json.loads(resumed_websocket.recv(timeout=5))
                    resumed_events.append(event)
                    if event["type"] in {"response.completed", "response.failed", "error"}:
                        break

    assert upstream_state.ws_accepts == 1
    assert len(upstream_state.ws_requests) == 1
    assert upstream_state.ws_handshake_headers[0].get(TURN_STATE_HEADER) is None
    assert resumed_events[-1]["type"] == "response.completed"
    assert any(event.get("delta") == "turn-1c" for event in resumed_events)


def test_responses_websocket_rejects_http_sse_resume_with_turn_state_error(
    workspace_tmp_dir: Path,
) -> None:
    upstream_state = ResponsesUpstreamState()
    upstream_app = build_responses_http_only_upstream(upstream_state)

    with run_uvicorn_app(upstream_app) as upstream_base_url:
        app = create_app(
            write_config(
                workspace_tmp_dir,
                build_config(
                    upstream_base_url=f"{upstream_base_url}/v1",
                    supports_responses_websocket=True,
                ),
            )
        )

        with TestClient(app) as client:
            with client.websocket_connect(
                "/v1/responses",
                headers={"openai-beta": RESPONSES_WEBSOCKET_BETA},
            ) as websocket:
                turn_state_token = websocket_header_map(websocket)[TURN_STATE_HEADER]
            wait_for(
                lambda: app.state.service.turn_state_store._entries[turn_state_token].attached_websocket is None
            )
            asyncio.run(
                app.state.service.turn_state_store.bind_transport(
                    turn_state_token,
                    provider_name="relay_a",
                    southbound_transport="http_sse",
                    managed_session=None,
                )
            )

            with client.websocket_connect(
                "/v1/responses",
                headers={
                    "openai-beta": RESPONSES_WEBSOCKET_BETA,
                    TURN_STATE_HEADER: turn_state_token,
                },
            ) as websocket:
                assert websocket_header_map(websocket)[TURN_STATE_HEADER] == turn_state_token
                event = json.loads(websocket.receive_text())

    assert event["type"] == "error"
    assert event["status"] == 409
    assert event["error"]["code"] == "turn_state_not_resumable"
    assert "HTTP/SSE upstream transport" in event["error"]["message"]
    assert len(upstream_state.http_requests) == 0


def test_responses_websocket_returns_error_for_invalid_or_expired_turn_state(
    workspace_tmp_dir: Path,
) -> None:
    upstream_state = ResponsesUpstreamState()
    upstream_app = build_responses_websocket_upstream(upstream_state)

    with run_uvicorn_app(upstream_app) as upstream_base_url:
        app = create_app(
            write_config(
                workspace_tmp_dir,
                build_config(
                    upstream_base_url=f"{upstream_base_url}/v1",
                    supports_responses_websocket=True,
                ),
            )
        )

        with TestClient(app) as client:
            with client.websocket_connect(
                "/v1/responses",
                headers={
                    "openai-beta": RESPONSES_WEBSOCKET_BETA,
                    TURN_STATE_HEADER: "missing-token",
                },
            ) as websocket:
                invalid_event = json.loads(websocket.receive_text())

            with client.websocket_connect(
                "/v1/responses",
                headers={"openai-beta": RESPONSES_WEBSOCKET_BETA},
            ) as websocket:
                turn_state_token = websocket_header_map(websocket)[TURN_STATE_HEADER]

            wait_for(
                lambda: app.state.service.turn_state_store._entries[turn_state_token].attached_websocket is None
            )
            expired_entry = app.state.service.turn_state_store._entries[turn_state_token]
            expired_entry.resume_deadline = datetime.now(UTC) - timedelta(seconds=1)

            with client.websocket_connect(
                "/v1/responses",
                headers={
                    "openai-beta": RESPONSES_WEBSOCKET_BETA,
                    TURN_STATE_HEADER: turn_state_token,
                },
            ) as websocket:
                expired_event = json.loads(websocket.receive_text())

    assert invalid_event["type"] == "error"
    assert invalid_event["status"] == 409
    assert invalid_event["error"]["code"] == "turn_state_invalid"
    assert invalid_event["error"]["message"] == "The websocket turn-state token is not valid on this proxy instance."
    assert expired_event["type"] == "error"
    assert expired_event["status"] == 409
    assert expired_event["error"]["code"] == "turn_state_expired"
    assert expired_event["error"]["message"] == "The websocket turn-state token has expired."


@dataclass(slots=True)
class OrderedUpstreamState:
    ws_accepts: int = 0
    ws_requests: list[dict[str, object]] = field(default_factory=list)
    ws_handshake_headers: list[dict[str, str]] = field(default_factory=list)
    first_delta_sent: Event = field(default_factory=Event)
    release_burst: Event = field(default_factory=Event)
    burst_sent: Event = field(default_factory=Event)
    release_completion: Event = field(default_factory=Event)
    burst_deltas: tuple[str, ...] = ("burst-0", "burst-1", "burst-2", "burst-3", "burst-4")
    tail_deltas: tuple[str, ...] = ("tail-0", "tail-1", "tail-2")


def build_ordered_resumable_upstream(state: OrderedUpstreamState) -> FastAPI:
    app = FastAPI()

    @app.websocket("/v1/responses")
    async def responses_ws(websocket: WebSocket):
        state.ws_accepts += 1
        state.ws_handshake_headers.append({k.lower(): v for k, v in websocket.headers.items()})
        await websocket.accept()
        try:
            while True:
                raw_message = await websocket.receive_text()
                payload = json.loads(raw_message)
                state.ws_requests.append(payload)

                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "response.created",
                            "response": {"id": "resp-order-1", "model": payload["model"]},
                        }
                    )
                )
                await websocket.send_text(
                    json.dumps({"type": "response.output_text.delta", "delta": "head"})
                )
                state.first_delta_sent.set()

                await asyncio.to_thread(state.release_burst.wait, 5.0)
                for delta in state.burst_deltas:
                    await websocket.send_text(
                        json.dumps({"type": "response.output_text.delta", "delta": delta})
                    )
                state.burst_sent.set()

                await asyncio.to_thread(state.release_completion.wait, 5.0)
                for delta in state.tail_deltas:
                    await websocket.send_text(
                        json.dumps({"type": "response.output_text.delta", "delta": delta})
                    )
                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "response.completed",
                            "response": {
                                "id": "resp-order-1",
                                "model": payload["model"],
                                "usage": {
                                    "input_tokens": 5,
                                    "output_tokens": 3,
                                    "total_tokens": 8,
                                },
                            },
                        }
                    )
                )
        except WebSocketDisconnect:
            return

    return app


def build_silent_upstream() -> FastAPI:
    app = FastAPI()

    @app.websocket("/v1/responses")
    async def responses_ws(websocket: WebSocket):
        await websocket.accept()
        try:
            await websocket.receive_text()
            stall = asyncio.Event()
            await stall.wait()
        except WebSocketDisconnect:
            return

    return app


def build_hang_after_created_upstream() -> FastAPI:
    app = FastAPI()

    @app.websocket("/v1/responses")
    async def responses_ws(websocket: WebSocket):
        await websocket.accept()
        try:
            raw_message = await websocket.receive_text()
            payload = json.loads(raw_message)
            await websocket.send_text(
                json.dumps(
                    {
                        "type": "response.created",
                        "response": {"id": "resp-idle-1", "model": payload["model"]},
                    }
                )
            )
            stall = asyncio.Event()
            await stall.wait()
        except WebSocketDisconnect:
            return

    return app


def build_binary_frame_upstream() -> FastAPI:
    app = FastAPI()

    @app.websocket("/v1/responses")
    async def responses_ws(websocket: WebSocket):
        await websocket.accept()
        try:
            await websocket.receive_text()
            await websocket.send_bytes(b"\x00\x01\x02binary")
            stall = asyncio.Event()
            await stall.wait()
        except WebSocketDisconnect:
            return

    return app


def test_websocket_unsupported_status_codes_exclude_transient_server_errors() -> None:
    assert 500 not in WS_UNSUPPORTED_STATUS_CODES
    assert 501 not in WS_UNSUPPORTED_STATUS_CODES
    assert 502 not in WS_UNSUPPORTED_STATUS_CODES
    assert 503 not in WS_UNSUPPORTED_STATUS_CODES
    assert 504 not in WS_UNSUPPORTED_STATUS_CODES
    assert 400 in WS_UNSUPPORTED_STATUS_CODES
    assert 403 in WS_UNSUPPORTED_STATUS_CODES
    assert 404 in WS_UNSUPPORTED_STATUS_CODES
    assert 405 in WS_UNSUPPORTED_STATUS_CODES
    assert 426 in WS_UNSUPPORTED_STATUS_CODES


def test_responses_websocket_resume_preserves_multi_frame_order(
    workspace_tmp_dir: Path,
) -> None:
    upstream_state = OrderedUpstreamState()
    upstream_app = build_ordered_resumable_upstream(upstream_state)

    with run_uvicorn_app(upstream_app) as upstream_base_url:
        board_app = create_app(
            write_config(
                workspace_tmp_dir,
                build_config(
                    upstream_base_url=f"{upstream_base_url}/v1",
                    supports_responses_websocket=True,
                ),
            )
        )

        with run_uvicorn_app(board_app) as board_base_url:
            websocket_url = f"{board_base_url.replace('http://', 'ws://')}/v1/responses"
            with websocket_connect_sync(
                websocket_url,
                additional_headers={"openai-beta": RESPONSES_WEBSOCKET_BETA},
                open_timeout=5,
                close_timeout=1,
            ) as websocket:
                turn_state_token = websocket.response.headers[TURN_STATE_HEADER]
                websocket.send(
                    json.dumps(
                        {
                            "type": "response.create",
                            "model": "gpt-4.1",
                            "input": "turn-1",
                        }
                    )
                )
                first_event = json.loads(websocket.recv(timeout=5))
                head_delta = json.loads(websocket.recv(timeout=5))

            assert first_event["type"] == "response.created"
            assert head_delta["delta"] == "head"
            assert upstream_state.first_delta_sent.wait(timeout=5.0)
            wait_for(
                lambda: board_app.state.service.turn_state_store._entries[turn_state_token].attached_websocket is None
            )
            upstream_state.release_burst.set()
            assert upstream_state.burst_sent.wait(timeout=5.0)

            with websocket_connect_sync(
                websocket_url,
                additional_headers={
                    "openai-beta": RESPONSES_WEBSOCKET_BETA,
                    TURN_STATE_HEADER: turn_state_token,
                },
                open_timeout=5,
                close_timeout=1,
            ) as resumed_websocket:
                assert resumed_websocket.response.headers[TURN_STATE_HEADER] == turn_state_token
                upstream_state.release_completion.set()
                resumed_events = []
                while True:
                    event = json.loads(resumed_websocket.recv(timeout=5))
                    resumed_events.append(event)
                    if event["type"] in {"response.completed", "response.failed", "error"}:
                        break

    assert upstream_state.ws_accepts == 1
    assert resumed_events[-1]["type"] == "response.completed"
    observed_deltas = [event["delta"] for event in resumed_events if event.get("type") == "response.output_text.delta"]
    expected_deltas = list(upstream_state.burst_deltas) + list(upstream_state.tail_deltas)
    assert observed_deltas == expected_deltas


def test_responses_websocket_first_frame_timeout_returns_error(
    workspace_tmp_dir: Path,
) -> None:
    upstream_app = build_silent_upstream()

    with run_uvicorn_app(upstream_app) as upstream_base_url:
        app = create_app(
            write_config(
                workspace_tmp_dir,
                build_config(
                    upstream_base_url=f"{upstream_base_url}/v1",
                    supports_responses_websocket=True,
                    timeout_seconds=2,
                ),
            )
        )

        with TestClient(app) as client:
            turn_state_token: str | None = None
            with client.websocket_connect(
                "/v1/responses",
                headers={"openai-beta": RESPONSES_WEBSOCKET_BETA},
            ) as websocket:
                turn_state_token = websocket_header_map(websocket)[TURN_STATE_HEADER]
                websocket.send_text(
                    json.dumps(
                        {
                            "type": "response.create",
                            "model": "gpt-4.1",
                            "input": "hello",
                        }
                    )
                )
                started = time.time()
                event = json.loads(websocket.receive_text())
                elapsed = time.time() - started

            dashboard = client.get("/admin/api/dashboard").json()

    assert event["type"] == "error"
    assert event["status"] == 503
    assert event["error"]["code"] == "upstream_unavailable"
    assert elapsed < 6.0
    relay_a = next(provider for provider in dashboard["providers"] if provider["name"] == "relay_a")
    assert relay_a["ws_unsupported"] is False


def test_responses_websocket_idle_timeout_returns_error(
    workspace_tmp_dir: Path,
) -> None:
    upstream_app = build_hang_after_created_upstream()

    with run_uvicorn_app(upstream_app) as upstream_base_url:
        app = create_app(
            write_config(
                workspace_tmp_dir,
                build_config(
                    upstream_base_url=f"{upstream_base_url}/v1",
                    supports_responses_websocket=True,
                    timeout_seconds=2,
                ),
            )
        )

        with TestClient(app) as client:
            with client.websocket_connect(
                "/v1/responses",
                headers={"openai-beta": RESPONSES_WEBSOCKET_BETA},
            ) as websocket:
                websocket.send_text(
                    json.dumps(
                        {
                            "type": "response.create",
                            "model": "gpt-4.1",
                            "input": "hello",
                        }
                    )
                )
                started = time.time()
                events: list[dict[str, object]] = []
                while True:
                    event = json.loads(websocket.receive_text())
                    events.append(event)
                    if event["type"] in {"response.completed", "response.failed", "error"}:
                        break
                elapsed = time.time() - started

            dashboard = client.get("/admin/api/dashboard").json()

    assert events[0]["type"] == "response.created"
    terminal = events[-1]
    assert terminal["type"] == "error"
    assert terminal["status"] == 503
    assert terminal["error"]["code"] == "upstream_unavailable"
    assert 1.5 <= elapsed < 8.0
    relay_a = next(provider for provider in dashboard["providers"] if provider["name"] == "relay_a")
    assert relay_a["ws_unsupported"] is False


def test_responses_websocket_binary_frame_is_rejected_with_error(
    workspace_tmp_dir: Path,
) -> None:
    upstream_app = build_binary_frame_upstream()

    with run_uvicorn_app(upstream_app) as upstream_base_url:
        app = create_app(
            write_config(
                workspace_tmp_dir,
                build_config(
                    upstream_base_url=f"{upstream_base_url}/v1",
                    supports_responses_websocket=True,
                    timeout_seconds=5,
                ),
            )
        )

        with TestClient(app) as client:
            with client.websocket_connect(
                "/v1/responses",
                headers={"openai-beta": RESPONSES_WEBSOCKET_BETA},
            ) as websocket:
                websocket.send_text(
                    json.dumps(
                        {
                            "type": "response.create",
                            "model": "gpt-4.1",
                            "input": "hello",
                        }
                    )
                )
                event = json.loads(websocket.receive_text())

            dashboard = client.get("/admin/api/dashboard").json()

    assert event["type"] == "error"
    assert event["status"] == 503
    assert event["error"]["code"] == "upstream_unavailable"
    relay_a = next(provider for provider in dashboard["providers"] if provider["name"] == "relay_a")
    assert relay_a["ws_unsupported"] is False


def test_signal_stop_releases_sender_loop_stuck_on_ready_event() -> None:
    """Regression for the Fix #1 leak: when a resumed attachment never reaches
    mark_client_ready, _signal_stop must still unblock the sender_loop so the
    ClientAttachment/WebSocket references can be garbage-collected."""

    async def run() -> None:
        # Stand up a minimal ManagedUpstreamWebSocketSession-like fixture by
        # directly driving a ClientAttachment through the session's helpers.
        from vibecoding_board.service import ManagedUpstreamWebSocketSession

        class _StubUpstream:
            async def recv(self):
                await asyncio.Event().wait()

            async def close(self):
                return None

        class _StubNorthbound:
            async def send_text(self, text):
                return None

        from vibecoding_board.responses_state import ResponsesStateStore
        from vibecoding_board.turn_state import TurnStateStore

        store = TurnStateStore(sweep_interval_seconds=0)
        entry = await store.issue(websocket=object())
        session = ManagedUpstreamWebSocketSession(
            turn_state_token=entry.token,
            provider_name="stub",
            url="ws://stub",
            websocket=_StubUpstream(),
            responses_state=ResponsesStateStore(),
            turn_state_store=store,
            idle_timeout_seconds=5.0,
        )
        try:
            # Attach with ready=False to mirror the resumed handoff that never
            # gets to mark_client_ready before the northbound handshake fails.
            await session.handoff_client(_StubNorthbound(), ready=False)
            attachment = session._attachment
            assert attachment is not None
            sender_task = attachment.sender_task
            assert sender_task is not None
            # Simulate the abort path: detach the client without ever setting
            # ready_event. Fix #1 guarantees the sender_loop exits promptly.
            await session.detach_client(attachment.websocket)
            try:
                await asyncio.wait_for(sender_task, timeout=1.0)
            except asyncio.TimeoutError:
                pytest.fail("sender_loop leaked — Fix #1 regression")
        finally:
            session._reader_task.cancel()
            await asyncio.gather(session._reader_task, return_exceptions=True)
            await store.close()

    asyncio.run(run())


def build_blocking_responses_websocket_upstream(state: "BlockingUpstreamState") -> FastAPI:
    app = FastAPI()

    @app.websocket("/v1/responses")
    async def responses_ws(websocket: WebSocket):
        state.ws_accepts += 1
        await websocket.accept()
        try:
            raw_message = await websocket.receive_text()
            payload = json.loads(raw_message)
            state.ws_requests.append(payload)
            await websocket.send_text(
                json.dumps(
                    {
                        "type": "response.created",
                        "response": {"id": "resp-block-1", "model": payload["model"]},
                    }
                )
            )
            await asyncio.to_thread(state.release_completion.wait, 5.0)
            await websocket.send_text(
                json.dumps(
                    {
                        "type": "response.completed",
                        "response": {
                            "id": "resp-block-1",
                            "model": payload["model"],
                            "usage": {
                                "input_tokens": 1,
                                "output_tokens": 1,
                                "total_tokens": 2,
                            },
                        },
                    }
                )
            )
        except WebSocketDisconnect:
            return

    return app


@dataclass(slots=True)
class BlockingUpstreamState:
    ws_accepts: int = 0
    ws_requests: list[dict[str, object]] = field(default_factory=list)
    release_completion: Event = field(default_factory=Event)


def test_client_pipelined_request_gets_error_event_without_dropping_stream(
    workspace_tmp_dir: Path,
) -> None:
    upstream_state = BlockingUpstreamState()
    upstream_app = build_blocking_responses_websocket_upstream(upstream_state)

    with run_uvicorn_app(upstream_app) as upstream_base_url:
        app = create_app(
            write_config(
                workspace_tmp_dir,
                build_config(
                    upstream_base_url=f"{upstream_base_url}/v1",
                    supports_responses_websocket=True,
                    timeout_seconds=10,
                ),
            )
        )

        with run_uvicorn_app(app) as board_base_url:
            websocket_url = f"{board_base_url.replace('http://', 'ws://')}/v1/responses"
            with websocket_connect_sync(
                websocket_url,
                additional_headers={"openai-beta": RESPONSES_WEBSOCKET_BETA},
                open_timeout=5,
                close_timeout=1,
            ) as websocket:
                websocket.send(
                    json.dumps(
                        {
                            "type": "response.create",
                            "model": "gpt-4.1",
                            "input": "turn-1",
                        }
                    )
                )
                first_event = json.loads(websocket.recv(timeout=5))
                assert first_event["type"] == "response.created"

                # Send a second response.create while the first is still being
                # streamed. Old code silently dropped it; Fix #2 must surface it
                # as a concurrent_request error without interrupting the stream.
                websocket.send(
                    json.dumps(
                        {
                            "type": "response.create",
                            "model": "gpt-4.1",
                            "input": "turn-2-pipelined",
                        }
                    )
                )

                observed: list[dict[str, object]] = []
                saw_concurrent_error = False
                deadline = time.time() + 5.0
                while time.time() < deadline:
                    if not saw_concurrent_error:
                        try:
                            event = json.loads(websocket.recv(timeout=0.5))
                        except TimeoutError:
                            continue
                        observed.append(event)
                        if (
                            event.get("type") == "error"
                            and event.get("error", {}).get("code") == "concurrent_request"
                        ):
                            saw_concurrent_error = True
                            upstream_state.release_completion.set()
                            continue
                    else:
                        event = json.loads(websocket.recv(timeout=2.0))
                        observed.append(event)
                        if event.get("type") == "response.completed":
                            break

    assert saw_concurrent_error, observed
    assert observed[-1]["type"] == "response.completed"
    # The pipelined request must not be forwarded to upstream.
    assert len(upstream_state.ws_requests) == 1


@dataclass(slots=True)
class BurstUpstreamState:
    ws_accepts: int = 0
    ws_requests: list[dict[str, object]] = field(default_factory=list)
    first_delta_sent: Event = field(default_factory=Event)
    release_burst: Event = field(default_factory=Event)
    burst_deltas_sent: int = 0
    burst_total: int = 64
    ws_closed: Event = field(default_factory=Event)


def build_burst_responses_websocket_upstream(state: BurstUpstreamState) -> FastAPI:
    app = FastAPI()

    @app.websocket("/v1/responses")
    async def responses_ws(websocket: WebSocket):
        state.ws_accepts += 1
        await websocket.accept()
        try:
            raw_message = await websocket.receive_text()
            payload = json.loads(raw_message)
            state.ws_requests.append(payload)
            await websocket.send_text(
                json.dumps(
                    {
                        "type": "response.created",
                        "response": {"id": "resp-burst-1", "model": payload["model"]},
                    }
                )
            )
            await websocket.send_text(
                json.dumps({"type": "response.output_text.delta", "delta": "head"})
            )
            state.first_delta_sent.set()
            await asyncio.to_thread(state.release_burst.wait, 5.0)
            for i in range(state.burst_total):
                try:
                    await websocket.send_text(
                        json.dumps(
                            {"type": "response.output_text.delta", "delta": f"burst-{i}"}
                        )
                    )
                except Exception:
                    break
                state.burst_deltas_sent = i + 1
        except WebSocketDisconnect:
            return
        finally:
            state.ws_closed.set()

    return app


def test_upstream_burst_during_disconnect_closes_session_after_buffer_overflow(
    workspace_tmp_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(service_module, "MAX_BUFFERED_FRAMES", 8)
    monkeypatch.setattr(service_module, "MAX_BUFFERED_BYTES", 4 * 1024 * 1024)

    upstream_state = BurstUpstreamState()
    upstream_app = build_burst_responses_websocket_upstream(upstream_state)

    with run_uvicorn_app(upstream_app) as upstream_base_url:
        board_app = create_app(
            write_config(
                workspace_tmp_dir,
                build_config(
                    upstream_base_url=f"{upstream_base_url}/v1",
                    supports_responses_websocket=True,
                    timeout_seconds=10,
                ),
            )
        )

        with run_uvicorn_app(board_app) as board_base_url:
            websocket_url = f"{board_base_url.replace('http://', 'ws://')}/v1/responses"
            with websocket_connect_sync(
                websocket_url,
                additional_headers={"openai-beta": RESPONSES_WEBSOCKET_BETA},
                open_timeout=5,
                close_timeout=1,
            ) as websocket:
                turn_state_token = websocket.response.headers[TURN_STATE_HEADER]
                websocket.send(
                    json.dumps(
                        {
                            "type": "response.create",
                            "model": "gpt-4.1",
                            "input": "turn-1",
                        }
                    )
                )
                first_event = json.loads(websocket.recv(timeout=5))
                head_delta = json.loads(websocket.recv(timeout=5))

            assert first_event["type"] == "response.created"
            assert head_delta["delta"] == "head"
            assert upstream_state.first_delta_sent.wait(timeout=5.0)
            wait_for(
                lambda: board_app.state.service.turn_state_store._entries[turn_state_token].attached_websocket is None
            )

            # Unleash the burst: upstream keeps sending until the buffer cap
            # triggers the abort path and closes the upstream socket.
            upstream_state.release_burst.set()
            assert upstream_state.ws_closed.wait(timeout=5.0)
            wait_for(
                lambda: board_app.state.service.turn_state_store._entries.get(turn_state_token) is not None
                and board_app.state.service.turn_state_store._entries[turn_state_token].terminal_reason
                == BUFFER_OVERFLOW_TERMINAL_REASON
            )

            with websocket_connect_sync(
                websocket_url,
                additional_headers={
                    "openai-beta": RESPONSES_WEBSOCKET_BETA,
                    TURN_STATE_HEADER: turn_state_token,
                },
                open_timeout=5,
                close_timeout=1,
            ) as resumed_websocket:
                event = json.loads(resumed_websocket.recv(timeout=5))

    assert event["type"] == "error"
    assert event["status"] == 409
    assert event["error"]["code"] == "turn_state_closed"
    assert upstream_state.ws_accepts == 1
    assert upstream_state.burst_deltas_sent <= upstream_state.burst_total


def test_orphan_turn_state_is_swept_without_further_activity(
    workspace_tmp_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Swap TurnStateStore defaults at construction time so the sweeper launched
    # during lifespan runs with test-sized intervals. The production defaults
    # (30s TTL + 5s sweep) would make this test too slow to be practical.
    from vibecoding_board.turn_state import TurnStateStore as _RealStore

    class _FastStore(_RealStore):
        def __init__(self) -> None:
            super().__init__(resume_ttl_seconds=1, sweep_interval_seconds=0.1)

    monkeypatch.setattr(service_module, "TurnStateStore", _FastStore)

    upstream_state = ResponsesUpstreamState()
    upstream_app = build_responses_websocket_upstream(upstream_state)

    with run_uvicorn_app(upstream_app) as upstream_base_url:
        app = create_app(
            write_config(
                workspace_tmp_dir,
                build_config(
                    upstream_base_url=f"{upstream_base_url}/v1",
                    supports_responses_websocket=True,
                ),
            )
        )

        with TestClient(app) as client:
            with client.websocket_connect(
                "/v1/responses",
                headers={"openai-beta": RESPONSES_WEBSOCKET_BETA},
            ) as websocket:
                turn_state_token = websocket_header_map(websocket)[TURN_STATE_HEADER]
                websocket.send_text(
                    json.dumps(
                        {
                            "type": "response.create",
                            "model": "gpt-4.1",
                            "input": "turn-1",
                        }
                    )
                )
                first_events = receive_until_terminal(websocket)
                assert first_events[-1]["type"] == "response.completed"

            wait_for(
                lambda: turn_state_token not in app.state.service.turn_state_store._entries,
                timeout=5.0,
            )

    assert upstream_state.ws_accepts == 1
