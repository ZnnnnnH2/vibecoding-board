from __future__ import annotations

import asyncio
import codecs
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
import json
import logging
from time import perf_counter
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx
from fastapi import Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, Response, StreamingResponse
from websockets.asyncio.client import connect as websocket_connect
from websockets.exceptions import ConnectionClosed, InvalidHandshake, InvalidStatus, InvalidUpgrade, WebSocketException

from vibecoding_board.admin_metrics import AdminMetricsStore
from vibecoding_board.config import ConfigError, RetryPolicyConfig
from vibecoding_board.request_log import AttemptLogEntry, RequestLogStore
from vibecoding_board.request_log import UsageLogEntry
from vibecoding_board.registry import ProviderRegistry, ProviderSnapshot
from vibecoding_board.responses_state import ResponsesStateStore
from vibecoding_board.runtime import RuntimeManager, RuntimeMutationError
from vibecoding_board.token_ledger import TokenLedger
from vibecoding_board.turn_state import TurnStateEntry, TurnStateStore


LOGGER = logging.getLogger(__name__)

HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "host",
    "content-length",
}

# Headers that describe the *encoding* of the body as received from upstream.
# httpx transparently decodes compressed responses when we access ``.content``
# or ``.aread()``, so forwarding the original ``content-encoding`` would tell
# the client to decompress bytes that are already plain. These must only be
# dropped on code paths that hand the decoded body back to the client.
CONTENT_ENCODING_HEADERS = {
    "content-encoding",
}

RETRYABLE_EXCEPTIONS = (
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.PoolTimeout,
    httpx.ReadError,
    httpx.ReadTimeout,
    httpx.RemoteProtocolError,
    httpx.WriteError,
    httpx.WriteTimeout,
)

RESPONSES_WEBSOCKET_BETA = "responses_websockets=2026-02-06"
RESPONSE_CREATE_EVENT = "response.create"
TERMINAL_RESPONSE_EVENT_TYPES = {"response.completed", "response.failed", "error"}
# Only persistent "protocol not supported" signals mark a provider as ws-unsupported.
# Transient 5xx are treated as retryable failures instead.
WS_UNSUPPORTED_STATUS_CODES = {400, 403, 404, 405, 426}
TURN_STATE_HEADER = "x-codex-turn-state"
TURN_METADATA_CLIENT_KEY = "x-codex-turn-metadata"
REQUEST_LOG_ACTIVITY_TOUCH_INTERVAL_SECONDS = 5.0

# Per-session caps on frames buffered toward the client (pending_frames during
# resume + attachment.queue while attached). Hitting either cap aborts the
# session with terminal_reason="buffer_overflow" — the client gets a normal
# turn_state_closed error on the next resume attempt.
MAX_BUFFERED_FRAMES = 10_000
MAX_BUFFERED_BYTES = 16 * 1024 * 1024
BUFFER_OVERFLOW_TERMINAL_REASON = "buffer_overflow"

_ATTACHMENT_SENTINEL: object = object()


class StickyRoutingError(ValueError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int = 409,
        code: str = "response_context_unavailable",
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code


class UpstreamWebSocketUnsupportedError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class BufferOverflowError(RuntimeError):
    """Raised when the client-bound frame buffer exceeds configured limits."""


@dataclass(slots=True)
class ResponseFlowResult:
    status_code: int | None
    state: str
    error: str | None
    usage: UsageLogEntry | None
    ttfb_ms: int | None
    southbound_transport: str


@dataclass(slots=True)
class AttemptResult:
    provider: str
    url: str
    outcome: str
    retryable: bool
    status_code: int | None = None
    provider_attempt: int = 1
    next_action: str = "failover_next_provider"
    transport: str = "http"
    sticky: bool = False
    fallback_reason: str | None = None


@dataclass(slots=True)
class ActiveUpstreamRequest:
    tracker: "ResponsesEventTracker"
    started_at: float
    result_future: asyncio.Future[ResponseFlowResult]
    detach_future: asyncio.Future[None]
    first_frame_future: asyncio.Future[None]
    ttfb_ms: int | None = None


@dataclass(slots=True)
class ClientAttachment:
    websocket: WebSocket
    queue: asyncio.Queue
    ready_event: asyncio.Event
    stopped: asyncio.Event
    sender_task: asyncio.Task | None = None


def build_error_response(
    *,
    message: str,
    status_code: int,
    error_type: str,
    code: str,
    attempts: list[AttemptResult] | None = None,
) -> JSONResponse:
    payload: dict[str, object] = {
        "error": {
            "message": message,
            "type": error_type,
            "code": code,
        }
    }
    if attempts:
        payload["attempts"] = [
            {
                "provider": attempt.provider,
                "url": attempt.url,
                "outcome": attempt.outcome,
                "retryable": attempt.retryable,
                "status_code": attempt.status_code,
                "provider_attempt": attempt.provider_attempt,
                "next_action": attempt.next_action,
            }
            for attempt in attempts
        ]
    return JSONResponse(status_code=status_code, content=payload)


def normalize_response_headers(
    headers: Mapping[str, str],
    *,
    drop_content_encoding: bool = False,
) -> dict[str, str]:
    excluded = HOP_BY_HOP_HEADERS | CONTENT_ENCODING_HEADERS if drop_content_encoding else HOP_BY_HOP_HEADERS
    return {
        key: value
        for key, value in headers.items()
        if key.lower() not in excluded
    }


def build_upstream_headers(
    incoming_headers: Mapping[str, str], provider: ProviderSnapshot
) -> dict[str, str]:
    headers = {
        key: value
        for key, value in incoming_headers.items()
        if key.lower() not in HOP_BY_HOP_HEADERS
        and key.lower() != "authorization"
        and key.lower() != TURN_STATE_HEADER
    }
    headers["authorization"] = f"Bearer {provider.api_key}"
    return headers


def build_direct_provider_headers(api_key: str) -> dict[str, str]:
    return {
        "authorization": f"Bearer {api_key}",
        "content-type": "application/json",
    }


def join_upstream_url(base_url: str, path: str) -> str:
    if base_url.endswith("/v1") and path.startswith("/v1/"):
        return f"{base_url}{path[len('/v1') :]}"
    return f"{base_url}{path}"


def build_upstream_url(provider: ProviderSnapshot, path: str) -> str:
    return join_upstream_url(provider.base_url, path)


def to_websocket_url(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.scheme == "https":
        scheme = "wss"
    elif parsed.scheme == "http":
        scheme = "ws"
    else:
        scheme = parsed.scheme
    return urlunsplit(parsed._replace(scheme=scheme))


def append_openai_beta(existing_value: str | None, token: str) -> str:
    values = [value.strip() for value in (existing_value or "").split(",") if value.strip()]
    if token not in values:
        values.append(token)
    return ", ".join(values)


def classify_status(status_code: int, retryable_status_codes: set[int]) -> str:
    if 200 <= status_code < 400:
        return "success"
    if status_code in retryable_status_codes:
        return "retryable"
    return "non_retryable"


class ManagedUpstreamWebSocketSession:
    def __init__(
        self,
        *,
        turn_state_token: str,
        provider_name: str,
        url: str,
        websocket: Any,
        responses_state: ResponsesStateStore,
        turn_state_store: TurnStateStore,
        idle_timeout_seconds: float,
    ) -> None:
        self.turn_state_token = turn_state_token
        self.provider_name = provider_name
        self.url = url
        self.websocket = websocket
        self.responses_state = responses_state
        self.turn_state_store = turn_state_store
        self.idle_timeout_seconds = idle_timeout_seconds
        self._attachment: ClientAttachment | None = None
        self._pending_frames: list[str] = []
        self._active_request: ActiveUpstreamRequest | None = None
        self._last_frame_at: float = perf_counter()
        self._buffered_bytes: int = 0
        self._buffer_overflow_triggered: bool = False
        self._lock = asyncio.Lock()
        self._reader_task = asyncio.create_task(self._reader_loop())

    @property
    def attached_websocket(self) -> WebSocket | None:
        attachment = self._attachment
        return attachment.websocket if attachment is not None else None

    async def handoff_client(
        self,
        websocket: WebSocket,
        *,
        ready: bool = True,
    ) -> ActiveUpstreamRequest | None:
        """Atomically swap the attached client. Returns the active request the
        previous client was serving (if any), so the caller can signal its
        detach_future and unwind the prior forward_request."""
        loop = asyncio.get_running_loop()
        stale_request: ActiveUpstreamRequest | None = None
        old_attachment: ClientAttachment | None = None
        async with self._lock:
            current = self._attachment
            if current is not None and current.websocket is websocket:
                if ready and not current.ready_event.is_set():
                    current.ready_event.set()
                return None
            if current is not None:
                old_attachment = current
                stale_request = self._active_request
            queue: asyncio.Queue = asyncio.Queue()
            for frame in self._pending_frames:
                queue.put_nowait(frame)
            self._pending_frames.clear()
            new_attachment = ClientAttachment(
                websocket=websocket,
                queue=queue,
                ready_event=asyncio.Event(),
                stopped=asyncio.Event(),
            )
            if ready:
                new_attachment.ready_event.set()
            new_attachment.sender_task = loop.create_task(self._sender_loop(new_attachment))
            self._attachment = new_attachment
        if old_attachment is not None:
            self._signal_stop(old_attachment)
        return stale_request

    async def attach_client(self, websocket: WebSocket) -> None:
        stale_request = await self.handoff_client(websocket, ready=True)
        if stale_request is not None and not stale_request.detach_future.done():
            stale_request.detach_future.set_result(None)

    async def mark_client_ready(self, websocket: WebSocket) -> None:
        async with self._lock:
            attachment = self._attachment
            if attachment is None or attachment.websocket is not websocket:
                return
            attachment.ready_event.set()

    async def detach_client(self, websocket: WebSocket) -> None:
        old_attachment: ClientAttachment | None = None
        active_request: ActiveUpstreamRequest | None = None
        async with self._lock:
            if self._attachment is not None and self._attachment.websocket is websocket:
                old_attachment = self._attachment
                self._attachment = None
                active_request = self._active_request
        if old_attachment is not None:
            self._signal_stop(old_attachment)
        if active_request is not None and not active_request.detach_future.done():
            active_request.detach_future.set_result(None)

    async def enqueue_frame_to_client(self, frame_text: str) -> None:
        """Insert a server-generated frame into the existing sender pipeline.

        Must be used for any out-of-band frame (e.g. a concurrent_request error)
        — writing directly to the Starlette websocket would race with the
        sender_loop and tear a frame apart.
        """
        frame_bytes = len(frame_text.encode("utf-8"))
        async with self._lock:
            if self._buffer_overflow_triggered:
                return
            self._buffered_bytes += frame_bytes
            attachment = self._attachment
            if attachment is not None:
                attachment.queue.put_nowait(frame_text)
            else:
                self._pending_frames.append(frame_text)

    async def forward_request(
        self,
        *,
        request_text: str,
        started_at: float,
    ) -> ResponseFlowResult:
        loop = asyncio.get_running_loop()
        active_request = ActiveUpstreamRequest(
            tracker=ResponsesEventTracker(
                provider_name=self.provider_name,
                southbound_transport="websocket",
                responses_state=self.responses_state,
            ),
            started_at=started_at,
            result_future=loop.create_future(),
            detach_future=loop.create_future(),
            first_frame_future=loop.create_future(),
        )
        async with self._lock:
            if self._active_request is not None:
                raise RuntimeError("upstream websocket request is already in progress")
            self._active_request = active_request
            self._last_frame_at = perf_counter()

        try:
            await self.websocket.send(request_text)
        except BaseException:
            async with self._lock:
                if self._active_request is active_request:
                    self._active_request = None
            raise

        timeout = self.idle_timeout_seconds
        try:
            done, _ = await asyncio.wait(
                {
                    active_request.first_frame_future,
                    active_request.result_future,
                    active_request.detach_future,
                },
                return_when=asyncio.FIRST_COMPLETED,
                timeout=timeout,
            )
            if not done:
                await self._on_forward_timeout(active_request, reason="first_frame_timeout")
                raise WebSocketException("upstream responses websocket first-frame timeout")
            if active_request.result_future in done:
                return active_request.result_future.result()
            if active_request.detach_future in done:
                raise WebSocketDisconnect()

            while True:
                done, _ = await asyncio.wait(
                    {active_request.result_future, active_request.detach_future},
                    return_when=asyncio.FIRST_COMPLETED,
                    timeout=timeout,
                )
                if active_request.result_future in done:
                    return active_request.result_future.result()
                if active_request.detach_future in done:
                    raise WebSocketDisconnect()
                async with self._lock:
                    idle_for = perf_counter() - self._last_frame_at
                if idle_for >= timeout:
                    await self._on_forward_timeout(active_request, reason="idle_timeout")
                    raise WebSocketException("upstream responses websocket idle timeout")
        finally:
            for fut in (
                active_request.first_frame_future,
                active_request.result_future,
                active_request.detach_future,
            ):
                if not fut.done():
                    fut.cancel()

    async def close(self) -> None:
        attachment: ClientAttachment | None
        async with self._lock:
            attachment = self._attachment
            self._attachment = None
        if attachment is not None:
            self._signal_stop(attachment)
            try:
                await asyncio.wait_for(attachment.stopped.wait(), timeout=1.0)
            except asyncio.TimeoutError:  # pragma: no cover - defensive
                sender_task = attachment.sender_task
                if sender_task is not None and not sender_task.done():
                    sender_task.cancel()
                    await asyncio.gather(sender_task, return_exceptions=True)
        try:
            await asyncio.wait_for(self.websocket.close(), timeout=1.0)
        except Exception:  # pragma: no cover - defensive
            LOGGER.debug("failed to close managed upstream websocket session", exc_info=True)
        try:
            await asyncio.wait_for(self._reader_task, timeout=1.0)
        except asyncio.TimeoutError:  # pragma: no cover - defensive
            self._reader_task.cancel()
            await asyncio.gather(self._reader_task, return_exceptions=True)
        except asyncio.CancelledError:  # pragma: no cover - defensive
            raise
        except Exception:  # pragma: no cover - defensive
            LOGGER.debug("reader task raised during session close", exc_info=True)

    def _signal_stop(self, attachment: ClientAttachment) -> None:
        # Unblock the sender loop even if it's still waiting on ready_event —
        # otherwise a resumed attachment that never reached mark_client_ready
        # would leak: the sentinel below can't wake a loop stuck on .wait().
        attachment.ready_event.set()
        try:
            attachment.queue.put_nowait(_ATTACHMENT_SENTINEL)
        except asyncio.QueueFull:  # pragma: no cover - unbounded queue
            pass

    async def _sender_loop(self, attachment: ClientAttachment) -> None:
        try:
            await attachment.ready_event.wait()
            while True:
                item = await attachment.queue.get()
                if item is _ATTACHMENT_SENTINEL:
                    return
                async with self._lock:
                    self._buffered_bytes = max(
                        0, self._buffered_bytes - len(item.encode("utf-8"))
                    )
                await attachment.websocket.send_text(item)
        except asyncio.CancelledError:
            raise
        except Exception:
            LOGGER.debug("client sender loop terminated", exc_info=True)
            await self._on_sender_error(attachment)
        finally:
            attachment.stopped.set()

    async def _on_sender_error(self, attachment: ClientAttachment) -> None:
        active_request: ActiveUpstreamRequest | None = None
        async with self._lock:
            if self._attachment is attachment:
                self._attachment = None
                active_request = self._active_request
        if active_request is not None and not active_request.detach_future.done():
            active_request.detach_future.set_result(None)

    async def _reader_loop(self) -> None:
        try:
            while True:
                raw_frame = await self.websocket.recv()
                frame_text = ProxyService._coerce_text_frame(raw_frame)
                payload = ProxyService._try_load_json_payload(frame_text)
                frame_bytes = len(frame_text.encode("utf-8"))

                active_request: ActiveUpstreamRequest | None
                attachment: ClientAttachment | None
                resolve_first_frame = False
                overflow = False
                async with self._lock:
                    active_request = self._active_request
                    attachment = self._attachment
                    self._last_frame_at = perf_counter()
                    if active_request is not None and active_request.ttfb_ms is None:
                        active_request.ttfb_ms = int((perf_counter() - active_request.started_at) * 1000)
                        resolve_first_frame = True
                    pending_count = len(self._pending_frames) + (
                        attachment.queue.qsize() if attachment is not None else 0
                    )
                    if (
                        not self._buffer_overflow_triggered
                        and (
                            pending_count + 1 > MAX_BUFFERED_FRAMES
                            or self._buffered_bytes + frame_bytes > MAX_BUFFERED_BYTES
                        )
                    ):
                        self._buffer_overflow_triggered = True
                        overflow = True
                    else:
                        self._buffered_bytes += frame_bytes
                        if attachment is not None:
                            attachment.queue.put_nowait(frame_text)
                        else:
                            self._pending_frames.append(frame_text)

                if overflow:
                    raise BufferOverflowError(
                        "client-bound buffer exceeded configured limits",
                    )

                if resolve_first_frame and active_request is not None and not active_request.first_frame_future.done():
                    active_request.first_frame_future.set_result(None)

                if payload is not None and active_request is not None:
                    await active_request.tracker.consume(payload)

                if payload is not None and active_request is not None and ProxyService._is_terminal_response_event(payload):
                    result = ResponseFlowResult(
                        status_code=active_request.tracker.status_code,
                        state=active_request.tracker.state,
                        error=active_request.tracker.error_message,
                        usage=active_request.tracker.usage,
                        ttfb_ms=active_request.ttfb_ms,
                        southbound_transport="websocket",
                    )
                    async with self._lock:
                        if self._active_request is active_request:
                            self._active_request = None
                    if not active_request.result_future.done():
                        active_request.result_future.set_result(result)
        except asyncio.CancelledError:
            raise
        except BufferOverflowError as exc:
            LOGGER.warning(
                "managed upstream websocket session aborted: %s", exc,
                extra={"provider": self.provider_name},
            )
            await self._abort_session(exc, terminal_reason=BUFFER_OVERFLOW_TERMINAL_REASON)
        except (ConnectionClosed, OSError, WebSocketException) as exc:
            await self._abort_session(exc, terminal_reason="closed")
        except Exception as exc:
            LOGGER.exception("upstream websocket reader crashed")
            await self._abort_session(exc, terminal_reason="closed")

    async def _abort_session(self, exc: BaseException, *, terminal_reason: str) -> None:
        await self.turn_state_store.mark_terminal(self.turn_state_token, terminal_reason)
        active_request: ActiveUpstreamRequest | None
        attachment: ClientAttachment | None
        async with self._lock:
            active_request = self._active_request
            attachment = self._attachment
            self._active_request = None
            self._attachment = None
            self._pending_frames.clear()
            self._buffered_bytes = 0
        if attachment is not None:
            self._signal_stop(attachment)
        if active_request is not None:
            if not active_request.result_future.done():
                active_request.result_future.set_exception(exc)
            if not active_request.detach_future.done():
                active_request.detach_future.set_result(None)
            if not active_request.first_frame_future.done():
                active_request.first_frame_future.cancel()
        # Proactively tear down the upstream TCP socket on overflow: otherwise
        # the producer keeps streaming into the void until idle_timeout.
        if terminal_reason == BUFFER_OVERFLOW_TERMINAL_REASON:
            try:
                await asyncio.wait_for(self.websocket.close(), timeout=1.0)
            except Exception:  # pragma: no cover - defensive
                LOGGER.debug(
                    "failed to close upstream websocket after buffer overflow",
                    exc_info=True,
                )

    async def _on_forward_timeout(self, active_request: ActiveUpstreamRequest, *, reason: str) -> None:
        async with self._lock:
            if self._active_request is active_request:
                self._active_request = None
        await self.turn_state_store.mark_terminal(self.turn_state_token, reason)
        try:
            await asyncio.wait_for(self.websocket.close(), timeout=1.0)
        except Exception:  # pragma: no cover - defensive
            LOGGER.debug("failed to close upstream websocket after timeout", exc_info=True)

class ProxyService:
    def __init__(
        self,
        *,
        runtime_manager: RuntimeManager,
        request_log_store: RequestLogStore,
        metrics_store: AdminMetricsStore,
        token_ledger: TokenLedger,
        client: httpx.AsyncClient,
        responses_state: ResponsesStateStore | None = None,
    ) -> None:
        self.runtime_manager = runtime_manager
        self.request_log_store = request_log_store
        self.metrics_store = metrics_store
        self.token_ledger = token_ledger
        self.client = client
        self.responses_state = responses_state or ResponsesStateStore()
        self.turn_state_store = TurnStateStore()

    async def start(self) -> None:
        await self.turn_state_store.start()

    async def close(self) -> None:
        await self.turn_state_store.close()

    async def rename_provider_references(self, old_name: str, new_name: str) -> None:
        await self.responses_state.rename_provider(old_name, new_name)
        await self.turn_state_store.rename_provider(old_name, new_name)

    async def run_provider_healthcheck(self, provider_name: str) -> dict[str, object]:
        runtime = self.runtime_manager.current()
        provider = next(
            (provider for provider in runtime.config.providers if provider.name == provider_name),
            None,
        )
        if provider is None:
            raise RuntimeMutationError(f"Provider {provider_name!r} does not exist.", status_code=404)

        try:
            runtime_provider = provider.to_runtime_provider()
        except ConfigError as exc:
            raise RuntimeMutationError(str(exc)) from exc

        model = runtime_provider.healthcheck_target_model()
        if not model:
            raise RuntimeMutationError(
                f"Provider {provider_name!r} needs 'healthcheck_model' because it is configured with wildcard models.",
            )

        url = join_upstream_url(runtime_provider.base_url, "/v1/chat/completions")
        stream = runtime.config.healthcheck.stream
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": "healthcheck"}],
            "max_tokens": 1,
            "stream": stream,
        }

        started_at = perf_counter()
        status_code: int | None = None
        ok = False
        error: str | None = None

        try:
            if stream:
                headers = build_direct_provider_headers(runtime_provider.api_key)
                headers["accept"] = "text/event-stream"
                request = self.client.build_request(
                    "POST",
                    url,
                    content=json.dumps(payload).encode("utf-8"),
                    headers=headers,
                    timeout=runtime_provider.timeout_seconds,
                )
                response = await self.client.send(request, stream=True)
                try:
                    status_code = response.status_code
                    if 200 <= response.status_code < 300:
                        ok, error = await self._validate_healthcheck_stream(response)
                    else:
                        error = await self._extract_upstream_error_message_from_stream(response)
                finally:
                    await response.aclose()
            else:
                response = await self.client.post(
                    url,
                    content=json.dumps(payload).encode("utf-8"),
                    headers=build_direct_provider_headers(runtime_provider.api_key),
                    timeout=runtime_provider.timeout_seconds,
                )
                status_code = response.status_code
                ok = 200 <= response.status_code < 300
                if not ok:
                    error = self._extract_upstream_error_message(response)
        except httpx.HTTPError as exc:
            error = str(exc)

        latency_ms = int((perf_counter() - started_at) * 1000)
        await self.runtime_manager.record_healthcheck(
            provider_name,
            ok=ok,
            status_code=status_code,
            latency_ms=latency_ms,
            stream=stream,
            model=model,
            error=error,
        )
        return {
            "provider_name": provider_name,
            "ok": ok,
            "status_code": status_code,
            "latency_ms": latency_ms,
            "stream": stream,
            "model": model,
            "error": error,
        }

    async def proxy_post(self, path: str, request: Request) -> Response:
        runtime = self.runtime_manager.current()
        body = await request.body()
        payload = self._load_json_payload(body)
        model = payload.get("model")
        if not isinstance(model, str) or not model.strip():
            return build_error_response(
                message="The request body must contain a non-empty 'model' field.",
                status_code=400,
                error_type="invalid_request_error",
                code="missing_model",
            )

        stream = bool(payload.get("stream"))
        request_kind = self._request_kind(path)
        try:
            candidates = await self._select_provider_candidates(
                path=path,
                model=model,
                payload=payload,
                registry=runtime.registry,
            )
        except StickyRoutingError as exc:
            return build_error_response(
                message=str(exc),
                status_code=exc.status_code,
                error_type="invalid_request_error",
                code=exc.code,
            )
        if not candidates:
            return build_error_response(
                message=f"No enabled upstream provider is configured for model {model!r}.",
                status_code=404,
                error_type="not_found_error",
                code="model_not_available",
            )

        sticky_provider = (
            candidates[0].name
            if path.endswith("/responses") and self._extract_previous_response_id(payload) is not None
            else None
        )
        log_id = await self.request_log_store.begin(
            endpoint=path,
            request_kind=request_kind,
            model=model,
            stream=stream,
            northbound_transport="http",
            sticky_provider=sticky_provider,
        )
        started_at = perf_counter()

        if stream:
            return await self._proxy_stream(
                path=path,
                body=body,
                incoming_headers=request.headers,
                model=model,
                candidates=candidates,
                registry=runtime.registry,
                retry_policy=runtime.config.retry_policy,
                log_id=log_id,
                started_at=started_at,
                sticky_provider=sticky_provider,
            )
        return await self._proxy_non_stream(
            path=path,
            body=body,
            incoming_headers=request.headers,
            model=model,
            candidates=candidates,
            registry=runtime.registry,
            retry_policy=runtime.config.retry_policy,
            log_id=log_id,
            started_at=started_at,
            sticky_provider=sticky_provider,
        )

    async def list_models(self) -> JSONResponse:
        models = self.runtime_manager.current().config.advertised_models()
        payload = {
            "object": "list",
            "data": [
                {
                    "id": model,
                    "object": "model",
                    "created": 0,
                    "owned_by": "vibecoding-board",
                }
                for model in models
            ],
        }
        return JSONResponse(content=payload)

    def health(self) -> JSONResponse:
        return JSONResponse(content={"status": "ok"})

    async def proxy_responses_websocket(self, websocket: WebSocket) -> None:
        if not self._responses_websocket_enabled():
            await websocket.accept()
            await self._send_responses_ws_error(
                websocket,
                message="Responses websocket is disabled on this proxy. Enable it in admin settings first.",
                status_code=403,
                code="responses_websocket_disabled",
            )
            await websocket.close(code=1000)
            return

        requested_token = self._extract_turn_state_token(websocket.headers)
        turn_state_status = "issued"

        if requested_token is None:
            turn_state_entry = await self.turn_state_store.issue(websocket=websocket)
            await websocket.accept(headers=self._turn_state_response_headers(turn_state_entry.token))
        else:
            attach_result = await self.turn_state_store.attach(requested_token, websocket=websocket)
            if attach_result.status != "resumed" or attach_result.entry is None:
                await websocket.accept()
                await self._send_turn_state_attach_error(websocket, attach_result.status)
                await websocket.close(code=1000)
                return
            turn_state_entry = attach_result.entry
            turn_state_status = "resumed"
            resume_error = self._resume_error_for_turn_state(turn_state_entry)
            stale_request: ActiveUpstreamRequest | None = None
            handoff_session: ManagedUpstreamWebSocketSession | None = None
            if resume_error is None and turn_state_entry.managed_session is not None:
                handoff_session = turn_state_entry.managed_session
                stale_request = await handoff_session.handoff_client(websocket, ready=False)
            try:
                await websocket.accept(headers=self._turn_state_response_headers(turn_state_entry.token))
            except BaseException:
                # Accept failed *after* we attached to the managed session. Undo
                # the handoff so the sender_loop tied to this websocket exits and
                # the turn-state entry goes back into the resume window.
                if handoff_session is not None:
                    await handoff_session.detach_client(websocket)
                await self.turn_state_store.detach(turn_state_entry.token, websocket=websocket)
                raise
            if resume_error is None and turn_state_entry.managed_session is not None:
                await turn_state_entry.managed_session.mark_client_ready(websocket)
                if stale_request is not None and not stale_request.detach_future.done():
                    stale_request.detach_future.set_result(None)
            if attach_result.previous_websocket is not None:
                try:
                    await attach_result.previous_websocket.close()
                except Exception:  # pragma: no cover - defensive
                    LOGGER.debug("failed to close stale northbound websocket", exc_info=True)
            if resume_error is not None:
                await self._send_responses_ws_error(
                    websocket,
                    message=resume_error["message"],
                    status_code=resume_error["status_code"],
                    code=resume_error["code"],
                )
                await websocket.close(code=1000)
                return

        try:
            while True:
                try:
                    message_text = await websocket.receive_text()
                except WebSocketDisconnect:
                    break

                started_at = perf_counter()
                try:
                    payload = self._load_json_payload(message_text.encode("utf-8"))
                except ValueError as exc:
                    await self._send_responses_ws_error(
                        websocket,
                        message=str(exc),
                        status_code=400,
                        code="invalid_json",
                    )
                    continue

                if payload.get("type") != RESPONSE_CREATE_EVENT:
                    await self._send_responses_ws_error(
                        websocket,
                        message="The websocket only accepts 'response.create' events.",
                        status_code=400,
                        code="invalid_event_type",
                    )
                    continue

                model = payload.get("model")
                if not isinstance(model, str) or not model.strip():
                    await self._send_responses_ws_error(
                        websocket,
                        message="The request body must contain a non-empty 'model' field.",
                        status_code=400,
                        code="missing_model",
                    )
                    continue

                turn_state_entry = await self._prepare_turn_state_for_request(
                    turn_state_entry=turn_state_entry,
                    request_payload=payload,
                )

                log_id = await self.request_log_store.begin(
                    endpoint="/v1/responses",
                    request_kind="response",
                    model=model,
                    stream=bool(payload.get("stream", True)),
                    northbound_transport="websocket",
                    sticky_provider=turn_state_entry.provider_name,
                    turn_state_token_present=True,
                    turn_state_status=turn_state_status,
                )
                try:
                    await self._proxy_responses_websocket_request(
                        websocket=websocket,
                        request_text=message_text,
                        request_payload=payload,
                        log_id=log_id,
                        started_at=started_at,
                        turn_state_entry=turn_state_entry,
                        turn_state_status=turn_state_status,
                    )
                except WebSocketDisconnect:
                    break
        finally:
            if turn_state_entry.managed_session is not None:
                await turn_state_entry.managed_session.detach_client(websocket)
            await self.turn_state_store.detach(turn_state_entry.token, websocket=websocket)

    async def _proxy_responses_websocket_request(
        self,
        *,
        websocket: WebSocket,
        request_text: str,
        request_payload: dict[str, object],
        log_id: str,
        started_at: float,
        turn_state_entry: TurnStateEntry,
        turn_state_status: str,
    ) -> None:
        turn_state_entry = await self._prepare_turn_state_for_request(
            turn_state_entry=turn_state_entry,
            request_payload=request_payload,
        )

        if turn_state_entry.terminal_reason is not None:
            await self._finalize_request(
                log_id,
                model=str(request_payload["model"]),
                southbound_transport=turn_state_entry.southbound_transport,
                sticky_provider=turn_state_entry.provider_name,
                turn_state_status="resume_closed",
                final_provider=turn_state_entry.provider_name,
                final_url=None,
                status_code=409,
                duration_ms=int((perf_counter() - started_at) * 1000),
                ttfb_ms=None,
                state="error",
                error="The websocket turn state is no longer resumable.",
                usage=None,
                attempts=[],
            )
            await self._send_responses_ws_error(
                websocket,
                message="The websocket turn state is no longer resumable.",
                status_code=409,
                code="turn_state_closed",
            )
            return

        runtime = self.runtime_manager.current()
        model = str(request_payload["model"])
        previous_response_id = self._extract_previous_response_id(request_payload)
        sticky = previous_response_id is not None or turn_state_entry.provider_name is not None
        attempts: list[AttemptResult] = []

        try:
            candidates = await self._select_responses_websocket_candidates(
                model=model,
                payload=request_payload,
                registry=runtime.registry,
                turn_state_entry=turn_state_entry,
            )
        except StickyRoutingError as exc:
            await self._finalize_request(
                log_id,
                model=model,
                southbound_transport=None,
                sticky_provider=turn_state_entry.provider_name,
                turn_state_status="provider_mismatch" if exc.code == "turn_state_provider_mismatch" else turn_state_status,
                final_provider=None,
                final_url=None,
                status_code=exc.status_code,
                duration_ms=int((perf_counter() - started_at) * 1000),
                ttfb_ms=None,
                state="error",
                error=str(exc),
                usage=None,
                attempts=[],
            )
            await self._send_responses_ws_error(
                websocket,
                message=str(exc),
                status_code=exc.status_code,
                code=exc.code,
            )
            return

        for provider in candidates:
            final_url = build_upstream_url(provider, "/v1/responses")
            try:
                result = await self._proxy_responses_via_upstream_websocket(
                    websocket=websocket,
                    request_text=request_text,
                    provider=provider,
                    started_at=started_at,
                    incoming_headers=websocket.headers,
                    turn_state_entry=turn_state_entry,
                )
            except UpstreamWebSocketUnsupportedError as exc:
                if hasattr(runtime.registry, "mark_ws_unsupported"):
                    await runtime.registry.mark_ws_unsupported(provider.name, str(exc))
                attempts.append(
                    AttemptResult(
                        provider=provider.name,
                        url=final_url,
                        outcome="websocket_unsupported",
                        retryable=False,
                        status_code=exc.status_code,
                        next_action="return_to_client" if sticky else "failover_next_provider",
                        transport="websocket",
                        sticky=sticky,
                    )
                )
                if sticky:
                    message = self._build_pinned_provider_message(
                        provider_name=provider.name,
                        previous_response_id=previous_response_id,
                        detail="the provider does not support Responses websocket transport.",
                    )
                    await self._finalize_request(
                        log_id,
                        model=model,
                        southbound_transport="websocket",
                        sticky_provider=provider.name if sticky else None,
                        turn_state_status=turn_state_status,
                        final_provider=provider.name,
                        final_url=final_url,
                        status_code=503,
                        duration_ms=int((perf_counter() - started_at) * 1000),
                        ttfb_ms=None,
                        state="error",
                        error=message,
                        usage=None,
                        attempts=self._to_attempt_logs(attempts),
                    )
                    await self._send_responses_ws_error(
                        websocket,
                        message=message,
                        status_code=503,
                        code="upstream_unavailable",
                    )
                    return
                continue
            except WebSocketDisconnect:
                await self._finalize_request(
                    log_id,
                    model=model,
                    southbound_transport=turn_state_entry.southbound_transport,
                    sticky_provider=provider.name if sticky else None,
                    turn_state_status=turn_state_status,
                    final_provider=provider.name,
                    final_url=final_url,
                    status_code=None,
                    duration_ms=int((perf_counter() - started_at) * 1000),
                    ttfb_ms=None,
                    state="interrupted",
                    error="client websocket disconnected",
                    usage=None,
                    attempts=self._to_attempt_logs(attempts),
                )
                raise
            except (ConnectionClosed, OSError, WebSocketException) as exc:
                await runtime.registry.mark_retryable_failure(
                    provider.name,
                    str(exc),
                    suppress_cooldown=sticky,
                )
                attempts.append(
                    AttemptResult(
                        provider=provider.name,
                        url=final_url,
                        outcome=type(exc).__name__,
                        retryable=True,
                        next_action="return_to_client" if sticky else "failover_next_provider",
                        transport="websocket",
                        sticky=sticky,
                    )
                )
                if sticky:
                    message = self._build_pinned_provider_message(
                        provider_name=provider.name,
                        previous_response_id=previous_response_id,
                        detail="the provider could not continue the websocket session.",
                    )
                    await self._finalize_request(
                        log_id,
                        model=model,
                        southbound_transport="websocket",
                        sticky_provider=provider.name if sticky else None,
                        turn_state_status=turn_state_status,
                        final_provider=provider.name,
                        final_url=final_url,
                        status_code=503,
                        duration_ms=int((perf_counter() - started_at) * 1000),
                        ttfb_ms=None,
                        state="error",
                        error=message,
                        usage=None,
                        attempts=self._to_attempt_logs(attempts),
                    )
                    await self._send_responses_ws_error(
                        websocket,
                        message=message,
                        status_code=503,
                        code="upstream_unavailable",
                    )
                    return
                continue
            else:
                if result.state == "success":
                    await runtime.registry.mark_success(provider.name)
                elif result.state == "interrupted":
                    await runtime.registry.mark_retryable_failure(
                        provider.name,
                        result.error or "interrupted",
                    )
                await self._finalize_request(
                    log_id,
                    model=model,
                    southbound_transport=result.southbound_transport,
                    sticky_provider=provider.name if sticky else None,
                    turn_state_status=turn_state_status,
                    final_provider=provider.name,
                    final_url=final_url,
                    status_code=result.status_code,
                    duration_ms=int((perf_counter() - started_at) * 1000),
                    ttfb_ms=result.ttfb_ms,
                    state=result.state,
                    error=result.error,
                    usage=result.usage,
                    attempts=self._to_attempt_logs(attempts),
                )
                return

        message = (
            self._build_pinned_provider_message(
                provider_name=turn_state_entry.provider_name or candidates[0].name,
                previous_response_id=previous_response_id,
                detail="the response could not be continued over websocket on its original provider.",
            )
            if sticky and candidates
            else (
                f"No websocket-capable upstream providers are currently available for model {model!r}."
                if not candidates
                else f"All websocket-capable upstream providers failed for model {model!r} before any websocket event was sent."
            )
        )
        await self._finalize_request(
            log_id,
            model=model,
            southbound_transport=None,
            sticky_provider=turn_state_entry.provider_name if sticky else None,
            turn_state_status=turn_state_status,
            final_provider=None,
            final_url=None,
            status_code=503,
            duration_ms=int((perf_counter() - started_at) * 1000),
            ttfb_ms=None,
            state="error",
            error=message,
            usage=None,
            attempts=self._to_attempt_logs(attempts),
        )
        await self._send_responses_ws_error(
            websocket,
            message=message,
            status_code=503,
            code="upstream_unavailable",
        )

    async def _proxy_responses_via_upstream_websocket(
        self,
        *,
        websocket: WebSocket,
        request_text: str,
        provider: ProviderSnapshot,
        started_at: float,
        incoming_headers: Mapping[str, str],
        turn_state_entry: TurnStateEntry,
    ) -> ResponseFlowResult:
        try:
            session = await self._get_or_open_turn_state_ws_session(
                provider=provider,
                incoming_headers=incoming_headers,
                turn_state_entry=turn_state_entry,
            )
            stale_request = await session.handoff_client(websocket)
            if stale_request is not None and not stale_request.detach_future.done():
                stale_request.detach_future.set_result(None)
            await self.turn_state_store.bind_transport(
                turn_state_entry.token,
                provider_name=provider.name,
                southbound_transport="websocket",
                managed_session=session,
            )
            forward_task = asyncio.create_task(
                session.forward_request(request_text=request_text, started_at=started_at)
            )
            disconnect_task = asyncio.create_task(
                self._watch_client_during_forward(websocket, session)
            )
            done, pending = await asyncio.wait(
                {forward_task, disconnect_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if disconnect_task in done:
                await session.detach_client(websocket)
                await self.turn_state_store.detach(turn_state_entry.token, websocket=websocket)
                try:
                    return await forward_task
                except WebSocketDisconnect:
                    raise
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            return await forward_task
        except (InvalidHandshake, InvalidStatus, InvalidUpgrade) as exc:
            if self._is_websocket_unsupported(exc):
                raise UpstreamWebSocketUnsupportedError(
                    f"Provider {provider.name!r} does not support Responses websocket transport.",
                    status_code=self._websocket_error_status_code(exc),
                ) from exc
            raise

    async def _watch_client_during_forward(
        self,
        websocket: WebSocket,
        session: "ManagedUpstreamWebSocketSession",
    ) -> None:
        """Watch the northbound socket while a forward_request is in flight.

        Returning means the client has disconnected — the caller tears down the
        managed session. A text frame received here is a pipelined
        `response.create` that would otherwise be silently dropped; surface it
        as a concurrent_request error injected into the sender queue so the
        in-flight stream keeps its ordering with the sender_loop.
        """
        concurrent_payload = json.dumps(
            self._build_responses_ws_error_event(
                message="A response.create was received while the previous request is still in progress.",
                status_code=409,
                code="concurrent_request",
            )
        )
        while True:
            message = await websocket.receive()
            message_type = message.get("type")
            if message_type == "websocket.disconnect":
                return
            if message_type == "websocket.receive":
                try:
                    await session.enqueue_frame_to_client(concurrent_payload)
                except Exception:  # pragma: no cover - defensive
                    LOGGER.debug(
                        "failed to enqueue concurrent_request error frame",
                        exc_info=True,
                    )

    async def _proxy_responses_via_http_sse(
        self,
        *,
        websocket: WebSocket,
        request_payload: dict[str, object],
        provider: ProviderSnapshot,
        started_at: float,
        incoming_headers: Mapping[str, str],
        turn_state_entry: TurnStateEntry,
    ) -> ResponseFlowResult:
        await self.turn_state_store.bind_transport(
            turn_state_entry.token,
            provider_name=provider.name,
            southbound_transport="http_sse",
            managed_session=None,
        )
        url = build_upstream_url(provider, "/v1/responses")
        headers = build_upstream_headers(incoming_headers, provider)
        headers["content-type"] = "application/json"
        headers["accept"] = "text/event-stream"
        payload = self._request_payload_to_http_responses_payload(request_payload)
        request = self.client.build_request(
            "POST",
            url,
            content=json.dumps(payload).encode("utf-8"),
            headers=headers,
            timeout=provider.timeout_seconds,
        )
        response = await self.client.send(request, stream=True)
        tracker = ResponsesEventTracker(
            provider_name=provider.name,
            southbound_transport="http_sse",
            responses_state=self.responses_state,
        )
        ttfb_ms: int | None = None
        try:
            if response.status_code >= 400:
                error_message = await self._extract_upstream_error_message_from_stream(response)
                await websocket.send_text(
                    json.dumps(
                        self._build_responses_ws_error_event(
                            message=error_message or f"Upstream returned status {response.status_code}.",
                            status_code=response.status_code,
                            code="upstream_error",
                        )
                    )
                )
                return ResponseFlowResult(
                    status_code=response.status_code,
                    state="error",
                    error=error_message,
                    usage=None,
                    ttfb_ms=int((perf_counter() - started_at) * 1000),
                    southbound_transport="http_sse",
                )

            event_lines: list[str] = []
            async for line in response.aiter_lines():
                if line == "":
                    payload_text = self._join_sse_event_payload(event_lines)
                    event_lines.clear()
                    if not payload_text or payload_text == "[DONE]":
                        continue
                    if ttfb_ms is None:
                        ttfb_ms = int((perf_counter() - started_at) * 1000)
                    payload_dict = self._try_load_json_payload(payload_text)
                    if payload_dict is not None:
                        await tracker.consume(payload_dict)
                        await websocket.send_text(json.dumps(payload_dict))
                        if self._is_terminal_response_event(payload_dict):
                            break
                    continue
                event_lines.append(line)

            if event_lines:
                payload_text = self._join_sse_event_payload(event_lines)
                if payload_text and payload_text != "[DONE]":
                    if ttfb_ms is None:
                        ttfb_ms = int((perf_counter() - started_at) * 1000)
                    payload_dict = self._try_load_json_payload(payload_text)
                    if payload_dict is not None:
                        await tracker.consume(payload_dict)
                        await websocket.send_text(json.dumps(payload_dict))

            return ResponseFlowResult(
                status_code=tracker.status_code,
                state=tracker.state,
                error=tracker.error_message,
                usage=tracker.usage,
                ttfb_ms=ttfb_ms,
                southbound_transport="http_sse",
            )
        finally:
            await response.aclose()

    async def _get_or_open_turn_state_ws_session(
        self,
        *,
        provider: ProviderSnapshot,
        incoming_headers: Mapping[str, str],
        turn_state_entry: TurnStateEntry,
    ) -> ManagedUpstreamWebSocketSession:
        existing = turn_state_entry.managed_session
        if existing is not None:
            if existing.provider_name != provider.name:
                raise RuntimeError("turn state provider mismatch")
            return existing

        url = to_websocket_url(build_upstream_url(provider, "/v1/responses"))
        websocket = await websocket_connect(
            url,
            additional_headers=self._build_upstream_websocket_headers(incoming_headers, provider),
            open_timeout=provider.timeout_seconds,
            close_timeout=provider.timeout_seconds,
            max_size=None,
        )
        session = ManagedUpstreamWebSocketSession(
            turn_state_token=turn_state_entry.token,
            provider_name=provider.name,
            url=url,
            websocket=websocket,
            responses_state=self.responses_state,
            turn_state_store=self.turn_state_store,
            idle_timeout_seconds=provider.timeout_seconds,
        )
        if turn_state_entry.attached_websocket is not None:
            await session.handoff_client(turn_state_entry.attached_websocket)
        return session

    async def _select_provider_candidates(
        self,
        *,
        path: str,
        model: str,
        payload: dict[str, object],
        registry: ProviderRegistry,
    ) -> list[ProviderSnapshot]:
        previous_response_id = self._extract_previous_response_id(payload) if path.endswith("/responses") else None
        if previous_response_id is None:
            return await registry.get_candidates(model)
        sticky_provider = await self._resolve_sticky_provider(
            previous_response_id=previous_response_id,
            model=model,
            registry=registry,
        )
        return [sticky_provider]

    async def _select_responses_websocket_candidates(
        self,
        *,
        model: str,
        payload: dict[str, object],
        registry: ProviderRegistry,
        turn_state_entry: TurnStateEntry,
    ) -> list[ProviderSnapshot]:
        previous_response_id = self._extract_previous_response_id(payload)
        if previous_response_id is not None:
            sticky_provider = await self._resolve_sticky_provider(
                previous_response_id=previous_response_id,
                model=model,
                registry=registry,
                required_transport="websocket",
            )
            if (
                turn_state_entry.provider_name is not None
                and sticky_provider.name != turn_state_entry.provider_name
            ):
                raise StickyRoutingError(
                    (
                        f"Turn state is pinned to provider {turn_state_entry.provider_name!r}, "
                        f"but response context {previous_response_id!r} is pinned to {sticky_provider.name!r}."
                    ),
                    code="turn_state_provider_mismatch",
                )
            if not self._provider_supports_responses_websocket(sticky_provider):
                raise StickyRoutingError(
                    (
                        f"Response context {previous_response_id!r} is pinned to provider "
                        f"{sticky_provider.name!r}, but that provider does not support "
                        "Responses websocket transport."
                    ),
                    code="response_context_not_resumable",
                )
            return [sticky_provider]
        if turn_state_entry.provider_name is not None:
            provider = await self._resolve_turn_state_provider(
                provider_name=turn_state_entry.provider_name,
                model=model,
                registry=registry,
            )
            if not self._provider_supports_responses_websocket(provider):
                raise StickyRoutingError(
                    (
                        f"Turn state is pinned to provider {provider.name!r}, but that "
                        "provider does not support Responses websocket transport."
                    ),
                    code="turn_state_not_resumable",
                )
            return [provider]
        candidates = await registry.get_candidates(model)
        return [
            provider
            for provider in candidates
            if self._provider_supports_responses_websocket(provider)
        ]

    async def _resolve_turn_state_provider(
        self,
        *,
        provider_name: str,
        model: str,
        registry: ProviderRegistry,
    ) -> ProviderSnapshot:
        try:
            provider = await registry.get_state(provider_name)
        except KeyError as exc:
            raise StickyRoutingError(
                f"Turn state is pinned to provider {provider_name!r}, but that provider no longer exists.",
                code="turn_state_provider_mismatch",
            ) from exc
        if not self._provider_can_serve_model(provider, model):
            raise StickyRoutingError(
                f"Turn state is pinned to provider {provider.name!r}, but that provider no longer serves model {model!r}.",
                code="turn_state_provider_mismatch",
            )
        if not self._provider_is_available(provider):
            raise StickyRoutingError(
                f"Turn state is pinned to provider {provider.name!r}, but that provider is currently unavailable.",
                code="turn_state_provider_mismatch",
            )
        return provider

    async def _resolve_sticky_provider(
        self,
        *,
        previous_response_id: str,
        model: str,
        registry: ProviderRegistry,
        required_transport: str | None = None,
    ) -> ProviderSnapshot:
        affinity = await self.responses_state.lookup_response(previous_response_id)
        if affinity is None:
            raise StickyRoutingError(
                f"Response context {previous_response_id!r} is not available on this proxy instance.",
            )
        if required_transport is not None and affinity.southbound_transport != required_transport:
            transport_label = "Responses websocket transport" if required_transport == "websocket" else required_transport
            raise StickyRoutingError(
                (
                    f"Response context {previous_response_id!r} is bound to "
                    f"{affinity.southbound_transport!r} and cannot be continued over "
                    f"{transport_label}."
                ),
                code="response_context_not_resumable",
            )
        try:
            provider = await registry.get_state(affinity.provider_name)
        except KeyError as exc:
            raise StickyRoutingError(
                f"Response context {previous_response_id!r} is pinned to provider {affinity.provider_name!r}, "
                "but that provider no longer exists.",
            ) from exc
        if not self._provider_can_serve_model(provider, model):
            raise StickyRoutingError(
                f"Response context {previous_response_id!r} is pinned to provider {provider.name!r}, "
                f"but that provider no longer serves model {model!r}.",
            )
        if not self._provider_is_available(provider):
            raise StickyRoutingError(
                f"Response context {previous_response_id!r} is pinned to provider {provider.name!r}, "
                "but that provider is currently unavailable.",
            )
        return provider

    @staticmethod
    def _provider_supports_responses_websocket(provider: ProviderSnapshot) -> bool:
        return bool(
            getattr(provider, "supports_responses_websocket", False)
            and not getattr(provider, "ws_unsupported", False)
        )

    def _responses_websocket_enabled(self) -> bool:
        return bool(
            getattr(
                self.runtime_manager.current().config.responses_websocket,
                "enabled",
                False,
            )
        )

    @staticmethod
    def _provider_can_serve_model(provider: ProviderSnapshot, model: str) -> bool:
        return provider.supports_all_models or model in provider.models

    @staticmethod
    def _provider_is_available(provider: ProviderSnapshot) -> bool:
        if not provider.enabled:
            return False
        if provider.always_alive:
            return True
        return provider.cooldown_until is None or provider.cooldown_until <= datetime.now(UTC)

    @staticmethod
    def _extract_turn_state_token(headers: Mapping[str, str]) -> str | None:
        value = headers.get(TURN_STATE_HEADER)
        if not isinstance(value, str):
            return None
        cleaned = value.strip()
        return cleaned or None

    @staticmethod
    def _turn_state_response_headers(token: str) -> list[tuple[bytes, bytes]]:
        return [(TURN_STATE_HEADER.encode("ascii"), token.encode("ascii"))]

    async def _send_turn_state_attach_error(self, websocket: WebSocket, status: str) -> None:
        error_map = {
            "expired": {
                "message": "The websocket turn-state token has expired.",
                "status_code": 409,
                "code": "turn_state_expired",
            },
            "invalid": {
                "message": "The websocket turn-state token is not valid on this proxy instance.",
                "status_code": 409,
                "code": "turn_state_invalid",
            },
        }
        error = error_map.get(status, error_map["invalid"])
        await self._send_responses_ws_error(
            websocket,
            message=error["message"],
            status_code=error["status_code"],
            code=error["code"],
        )

    @staticmethod
    def _resume_error_for_turn_state(turn_state_entry: TurnStateEntry) -> dict[str, object] | None:
        if turn_state_entry.terminal_reason is not None:
            return {
                "message": "The websocket turn state is already closed.",
                "status_code": 409,
                "code": "turn_state_closed",
            }
        if turn_state_entry.southbound_transport == "http_sse":
            return {
                "message": "This websocket turn is bound to an HTTP/SSE upstream transport and cannot be resumed.",
                "status_code": 409,
                "code": "turn_state_not_resumable",
            }
        if turn_state_entry.southbound_transport == "websocket" and turn_state_entry.managed_session is None:
            return {
                "message": "The websocket turn state is already closed.",
                "status_code": 409,
                "code": "turn_state_closed",
            }
        return None

    @staticmethod
    def _build_pinned_provider_message(
        *,
        provider_name: str,
        previous_response_id: str | None,
        detail: str,
    ) -> str:
        if previous_response_id is not None:
            return f"Response {previous_response_id!r} is pinned to provider {provider_name!r}, but {detail}"
        return f"Turn state is pinned to provider {provider_name!r}, but {detail}"

    async def _send_responses_ws_error(
        self,
        websocket: WebSocket,
        *,
        message: str,
        status_code: int,
        code: str,
    ) -> None:
        payload = json.dumps(
            self._build_responses_ws_error_event(
                message=message,
                status_code=status_code,
                code=code,
            )
        )
        try:
            await websocket.send_text(payload)
        except (WebSocketDisconnect, ConnectionClosed, RuntimeError, OSError):
            LOGGER.debug("client websocket closed before error event could be delivered")

    @staticmethod
    def _build_responses_ws_error_event(
        *,
        message: str,
        status_code: int,
        code: str,
    ) -> dict[str, object]:
        return {
            "type": "error",
            "status": status_code,
            "error": {
                "type": "invalid_request_error" if status_code < 500 else "server_error",
                "code": code,
                "message": message,
            },
        }

    @staticmethod
    def _build_upstream_websocket_headers(
        incoming_headers: Mapping[str, str],
        provider: ProviderSnapshot,
    ) -> dict[str, str]:
        headers = {
            key: value
            for key, value in incoming_headers.items()
            if key.lower() not in HOP_BY_HOP_HEADERS
            and key.lower() != "authorization"
            and key.lower() != TURN_STATE_HEADER
            and not key.lower().startswith("sec-websocket-")
        }
        headers["authorization"] = f"Bearer {provider.api_key}"
        headers["openai-beta"] = append_openai_beta(
            headers.get("openai-beta"),
            RESPONSES_WEBSOCKET_BETA,
        )
        return headers

    @staticmethod
    def _is_websocket_unsupported(exc: Exception) -> bool:
        if isinstance(exc, InvalidStatus):
            response = getattr(exc, "response", None)
            status_code = getattr(response, "status_code", None)
            return status_code in WS_UNSUPPORTED_STATUS_CODES
        return isinstance(exc, (InvalidHandshake, InvalidUpgrade))

    @staticmethod
    def _websocket_error_status_code(exc: Exception) -> int | None:
        response = getattr(exc, "response", None)
        status_code = getattr(response, "status_code", None)
        return int(status_code) if isinstance(status_code, int) else None

    @staticmethod
    def _extract_previous_response_id(payload: Mapping[str, object]) -> str | None:
        value = payload.get("previous_response_id")
        if not isinstance(value, str):
            return None
        cleaned = value.strip()
        return cleaned or None

    async def _prepare_turn_state_for_request(
        self,
        *,
        turn_state_entry: TurnStateEntry,
        request_payload: Mapping[str, object],
    ) -> TurnStateEntry:
        turn_id = self._extract_request_turn_id(request_payload)
        updated_entry = await self.turn_state_store.set_current_turn(
            turn_state_entry.token,
            turn_id=turn_id,
        )
        return updated_entry or turn_state_entry

    @staticmethod
    def _extract_request_turn_id(payload: Mapping[str, object]) -> str | None:
        client_metadata = payload.get("client_metadata")
        if not isinstance(client_metadata, Mapping):
            return None

        turn_metadata_raw: str | None = None
        for key, value in client_metadata.items():
            if not isinstance(key, str) or key.lower() != TURN_METADATA_CLIENT_KEY:
                continue
            if isinstance(value, str):
                turn_metadata_raw = value.strip()
            break

        if not turn_metadata_raw:
            return None

        try:
            turn_metadata = json.loads(turn_metadata_raw)
        except json.JSONDecodeError:
            return None
        if not isinstance(turn_metadata, Mapping):
            return None

        turn_id = turn_metadata.get("turn_id")
        if not isinstance(turn_id, str):
            return None
        cleaned = turn_id.strip()
        return cleaned or None

    @staticmethod
    def _request_payload_to_http_responses_payload(payload: Mapping[str, object]) -> dict[str, object]:
        http_payload = {
            key: value
            for key, value in payload.items()
            if key != "type"
        }
        http_payload["stream"] = True
        return http_payload

    @staticmethod
    def _coerce_text_frame(frame: Any) -> str:
        if isinstance(frame, str):
            return frame
        if isinstance(frame, (bytes, bytearray, memoryview)):
            raise WebSocketException("upstream websocket sent a binary frame; only text frames are supported")
        raise WebSocketException("upstream websocket frame must be text")

    @staticmethod
    def _try_load_json_payload(payload_text: str) -> dict[str, object] | None:
        try:
            payload = json.loads(payload_text)
        except json.JSONDecodeError:
            return None
        if isinstance(payload, dict):
            return payload
        return None

    @staticmethod
    def _join_sse_event_payload(lines: list[str]) -> str:
        return "\n".join(
            line.removeprefix("data:").strip()
            for line in lines
            if line.startswith("data:")
        ).strip()

    @staticmethod
    def _is_terminal_response_event(payload: Mapping[str, object]) -> bool:
        return payload.get("type") in TERMINAL_RESPONSE_EVENT_TYPES

    async def _proxy_non_stream(
        self,
        *,
        path: str,
        body: bytes,
        incoming_headers: Mapping[str, str],
        model: str,
        candidates: list[ProviderSnapshot],
        registry: ProviderRegistry,
        retry_policy: RetryPolicyConfig,
        log_id: str,
        started_at: float,
        sticky_provider: str | None,
    ) -> Response:
        attempts: list[AttemptResult] = []
        retryable_status_codes = retry_policy.retryable_status_set()
        max_same_provider_attempts = retry_policy.same_provider_retry_count + 1
        for provider in candidates:
            headers = build_upstream_headers(incoming_headers, provider)
            url = build_upstream_url(provider, path)
            provider_exhausted = False
            for provider_attempt in range(1, max_same_provider_attempts + 1):
                try:
                    response = await self.client.post(
                        url,
                        content=body,
                        headers=headers,
                        timeout=provider.timeout_seconds,
                    )
                except RETRYABLE_EXCEPTIONS as exc:
                    await registry.mark_retryable_failure(provider.name, str(exc))
                    attempts.append(
                        AttemptResult(
                            provider=provider.name,
                            url=url,
                            outcome=type(exc).__name__,
                            retryable=True,
                            provider_attempt=provider_attempt,
                            next_action="failover_next_provider",
                        )
                    )
                    LOGGER.warning("upstream request failed before response", extra={"provider": provider.name})
                    provider_exhausted = True
                    break

                status_kind = classify_status(response.status_code, retryable_status_codes)
                if status_kind == "retryable":
                    exhausted = provider_attempt >= max_same_provider_attempts
                    attempts.append(
                        AttemptResult(
                            provider=provider.name,
                            url=url,
                            outcome="status_retryable",
                            retryable=True,
                            status_code=response.status_code,
                            provider_attempt=provider_attempt,
                            next_action="failover_next_provider" if exhausted else "retry_same_provider",
                        )
                    )
                    LOGGER.warning(
                        "upstream returned retryable status",
                        extra={"provider": provider.name, "status_code": response.status_code},
                    )
                    if exhausted:
                        await registry.mark_exhausted_and_cooldown(
                            provider.name,
                            f"retryable status {response.status_code}",
                        )
                        provider_exhausted = True
                        break
                    await self._sleep_before_same_provider_retry(retry_policy.retry_interval_ms)
                    continue

                duration_ms = int((perf_counter() - started_at) * 1000)
                usage = self._extract_usage_from_response(response)
                state = "success" if status_kind == "success" else "error"
                error = None if state == "success" else self._extract_upstream_error_message(response)
                if state == "success":
                    await registry.mark_success(provider.name)
                    if path.endswith("/responses"):
                        await self._bind_response_id_from_bytes(
                            response.content,
                            provider_name=provider.name,
                            southbound_transport="http",
                        )
                await self._finalize_request(
                    log_id,
                    model=model,
                    southbound_transport="http",
                    sticky_provider=sticky_provider,
                    final_provider=provider.name,
                    final_url=url,
                    status_code=response.status_code,
                    duration_ms=duration_ms,
                    ttfb_ms=duration_ms,
                    state=state,
                    error=error,
                    usage=usage,
                    attempts=self._to_attempt_logs(attempts),
                )
                return Response(
                    content=response.content,
                    status_code=response.status_code,
                    headers=normalize_response_headers(
                        response.headers, drop_content_encoding=True
                    ),
                )

            if provider_exhausted:
                continue

        await self._finalize_request(
            log_id,
            model=model,
            southbound_transport=None,
            sticky_provider=sticky_provider,
            final_provider=None,
            final_url=None,
            status_code=503,
            duration_ms=int((perf_counter() - started_at) * 1000),
            ttfb_ms=None,
            state="error",
            error=f"All upstream providers failed for model {model!r}.",
            usage=None,
            attempts=self._to_attempt_logs(attempts),
        )
        return build_error_response(
            message=f"All upstream providers failed for model {model!r}.",
            status_code=503,
            error_type="service_unavailable_error",
            code="upstream_unavailable",
            attempts=attempts,
        )

    async def _proxy_stream(
        self,
        *,
        path: str,
        body: bytes,
        incoming_headers: Mapping[str, str],
        model: str,
        candidates: list[ProviderSnapshot],
        registry: ProviderRegistry,
        retry_policy: RetryPolicyConfig,
        log_id: str,
        started_at: float,
        sticky_provider: str | None,
    ) -> Response:
        attempts: list[AttemptResult] = []
        retryable_status_codes = retry_policy.retryable_status_set()
        max_same_provider_attempts = retry_policy.same_provider_retry_count + 1
        for provider in candidates:
            url = build_upstream_url(provider, path)
            provider_exhausted = False
            for provider_attempt in range(1, max_same_provider_attempts + 1):
                request = self.client.build_request(
                    "POST",
                    url,
                    content=body,
                    headers=build_upstream_headers(incoming_headers, provider),
                    timeout=provider.timeout_seconds,
                )
                try:
                    response = await self.client.send(
                        request,
                        stream=True,
                    )
                except RETRYABLE_EXCEPTIONS as exc:
                    await registry.mark_retryable_failure(provider.name, str(exc))
                    attempts.append(
                        AttemptResult(
                            provider=provider.name,
                            url=url,
                            outcome=type(exc).__name__,
                            retryable=True,
                            provider_attempt=provider_attempt,
                            next_action="failover_next_provider",
                        )
                    )
                    provider_exhausted = True
                    break

                status_kind = classify_status(response.status_code, retryable_status_codes)
                if status_kind == "retryable":
                    exhausted = provider_attempt >= max_same_provider_attempts
                    attempts.append(
                        AttemptResult(
                            provider=provider.name,
                            url=url,
                            outcome="status_retryable",
                            retryable=True,
                            status_code=response.status_code,
                            provider_attempt=provider_attempt,
                            next_action="failover_next_provider" if exhausted else "retry_same_provider",
                        )
                    )
                    await response.aclose()
                    if exhausted:
                        await registry.mark_exhausted_and_cooldown(
                            provider.name,
                            f"retryable status {response.status_code}",
                        )
                        provider_exhausted = True
                        break
                    await self._sleep_before_same_provider_retry(retry_policy.retry_interval_ms)
                    continue

                if status_kind == "non_retryable":
                    body_bytes = await response.aread()
                    await response.aclose()
                    duration_ms = int((perf_counter() - started_at) * 1000)
                    usage = self._extract_usage_from_bytes(body_bytes)
                    await self._finalize_request(
                        log_id,
                        model=model,
                        southbound_transport="http_sse",
                        sticky_provider=sticky_provider,
                        final_provider=provider.name,
                        final_url=url,
                        status_code=response.status_code,
                        duration_ms=duration_ms,
                        ttfb_ms=duration_ms,
                        state="error",
                        error=self._extract_upstream_error_message(response),
                        usage=usage,
                        attempts=self._to_attempt_logs(attempts),
                    )
                    return Response(
                        content=body_bytes,
                        status_code=response.status_code,
                        headers=normalize_response_headers(
                            response.headers, drop_content_encoding=True
                        ),
                    )

                stream_iterator = response.aiter_raw()
                try:
                    first_chunk = await anext(stream_iterator)
                    ttfb_ms = int((perf_counter() - started_at) * 1000)
                except StopAsyncIteration:
                    first_chunk = b""
                    ttfb_ms = int((perf_counter() - started_at) * 1000)
                except RETRYABLE_EXCEPTIONS as exc:
                    await registry.mark_retryable_failure(provider.name, str(exc))
                    attempts.append(
                        AttemptResult(
                            provider=provider.name,
                            url=url,
                            outcome=type(exc).__name__,
                            retryable=True,
                            provider_attempt=provider_attempt,
                            next_action="failover_next_provider",
                        )
                    )
                    await response.aclose()
                    provider_exhausted = True
                    break

                return StreamingResponse(
                    self._stream_response(
                        registry=registry,
                        provider=provider,
                        final_url=url,
                        response=response,
                        first_chunk=first_chunk,
                        stream_iterator=stream_iterator,
                        model=model,
                        log_id=log_id,
                        started_at=started_at,
                        ttfb_ms=ttfb_ms,
                        attempts=self._to_attempt_logs(attempts),
                        sticky_provider=sticky_provider,
                    ),
                    status_code=response.status_code,
                    headers=normalize_response_headers(response.headers),
                )

            if provider_exhausted:
                continue

        await self._finalize_request(
            log_id,
            model=model,
            southbound_transport=None,
            sticky_provider=sticky_provider,
            final_provider=None,
            final_url=None,
            status_code=503,
            duration_ms=int((perf_counter() - started_at) * 1000),
            ttfb_ms=None,
            state="error",
            error=f"All upstream providers failed for model {model!r} before streaming began.",
            usage=None,
            attempts=self._to_attempt_logs(attempts),
        )
        return build_error_response(
            message=f"All upstream providers failed for model {model!r} before streaming began.",
            status_code=503,
            error_type="service_unavailable_error",
            code="stream_upstream_unavailable",
            attempts=attempts,
        )

    async def _stream_response(
        self,
        *,
        registry: ProviderRegistry,
        provider: ProviderSnapshot,
        final_url: str,
        response: httpx.Response,
        first_chunk: bytes,
        stream_iterator: AsyncIterator[bytes],
        model: str,
        log_id: str,
        started_at: float,
        ttfb_ms: int | None,
        attempts: list[AttemptLogEntry],
        sticky_provider: str | None,
    ) -> AsyncIterator[bytes]:
        completed = False
        error_message: str | None = None
        usage: UsageLogEntry | None = None
        terminal_state: str | None = None
        terminal_status_code: int | None = None
        last_activity_touch = 0.0
        parser = StreamUsageParser()
        # aiter_raw() hands back the raw (possibly gzipped/deflated/br) bytes
        # as received from upstream. Parsing usage out of compressed bytes is
        # meaningless, and forwarding stays byte-exact regardless.
        upstream_encoding = response.headers.get("content-encoding", "").strip().lower()
        if upstream_encoding and upstream_encoding != "identity":
            parser.disable()

        async def touch_activity(*, force: bool = False) -> None:
            nonlocal last_activity_touch
            now = perf_counter()
            if force or now - last_activity_touch >= REQUEST_LOG_ACTIVITY_TOUCH_INTERVAL_SECONDS:
                last_activity_touch = now
                await self.request_log_store.touch(log_id)

        def apply_terminal_event() -> bool:
            nonlocal completed, error_message, terminal_state, terminal_status_code
            if parser.terminal_state is None:
                return False
            terminal_state = parser.terminal_state
            terminal_status_code = parser.terminal_status_code
            if terminal_state == "success":
                completed = True
                error_message = None
            else:
                error_message = parser.terminal_error_message or "Upstream stream returned an error event."
            return True

        try:
            if first_chunk:
                parser.feed(first_chunk)
                usage = parser.usage or usage
                await touch_activity(force=True)
                terminal_seen = apply_terminal_event()
                yield first_chunk
                if terminal_seen:
                    return
            async for chunk in stream_iterator:
                parser.feed(chunk)
                usage = parser.usage or usage
                await touch_activity()
                terminal_seen = apply_terminal_event()
                yield chunk
                if terminal_seen:
                    return
            parser.finish()
            usage = parser.usage or usage
            if apply_terminal_event():
                return
            completed = True
        except RETRYABLE_EXCEPTIONS as exc:
            await registry.mark_retryable_failure(provider.name, str(exc))
            error_message = str(exc)
            LOGGER.warning(
                "upstream stream interrupted after response start",
                extra={"provider": provider.name, "error": type(exc).__name__},
            )
        finally:
            # Close the upstream response as soon as the client-facing
            # generator is done — this is what releases the connection back
            # to the httpx pool. A failure here must NOT skip finalization,
            # otherwise the request is stuck in the log store as pending and
            # metrics never increment.
            try:
                await response.aclose()
            except Exception as exc:  # pragma: no cover - defensive
                LOGGER.warning(
                    "failed to close upstream stream response",
                    extra={"provider": provider.name, "error": type(exc).__name__},
                )
            if completed:
                await registry.mark_success(provider.name)
            state = terminal_state or ("success" if completed else "interrupted")
            await self._finalize_request(
                log_id,
                model=model,
                southbound_transport="http_sse",
                sticky_provider=sticky_provider,
                final_provider=provider.name,
                final_url=final_url,
                status_code=terminal_status_code or response.status_code,
                duration_ms=int((perf_counter() - started_at) * 1000),
                ttfb_ms=ttfb_ms,
                state=state,
                error=error_message,
                usage=usage,
                attempts=attempts,
            )

    async def _finalize_request(
        self,
        entry_id: str,
        *,
        model: str | None,
        southbound_transport: str | None = None,
        sticky_provider: str | None = None,
        fallback_reason: str | None = None,
        final_provider: str | None,
        final_url: str | None,
        status_code: int | None,
        duration_ms: int,
        ttfb_ms: int | None,
        state: str,
        error: str | None,
        usage: UsageLogEntry | None,
        attempts: list[AttemptLogEntry],
        turn_state_status: str | None = None,
    ) -> None:
        await self.request_log_store.complete(
            entry_id,
            southbound_transport=southbound_transport,
            sticky_provider=sticky_provider,
            fallback_reason=fallback_reason,
            turn_state_status=turn_state_status,
            final_provider=final_provider,
            final_url=final_url,
            status_code=status_code,
            duration_ms=duration_ms,
            ttfb_ms=ttfb_ms,
            state=state,
            error=error,
            usage=usage,
            attempts=attempts,
        )
        await self.metrics_store.record_request(
            final_provider=final_provider,
            state=state,
            duration_ms=duration_ms,
            ttfb_ms=ttfb_ms,
            usage=usage,
            attempts=attempts,
        )
        await self.token_ledger.record(
            model=model,
            provider=final_provider,
            usage=usage,
        )

    @staticmethod
    def _load_json_payload(body: bytes) -> dict[str, object]:
        try:
            payload = json.loads(body)
        except json.JSONDecodeError as exc:
            raise ValueError("request body must be valid JSON") from exc
        if not isinstance(payload, dict):
            raise ValueError("request body must be a JSON object")
        return payload

    @staticmethod
    def _to_attempt_logs(attempts: list[AttemptResult]) -> list[AttemptLogEntry]:
        return [
            AttemptLogEntry(
                provider=attempt.provider,
                url=attempt.url,
                outcome=attempt.outcome,
                retryable=attempt.retryable,
                status_code=attempt.status_code,
                provider_attempt=attempt.provider_attempt,
                next_action=attempt.next_action,
                transport=attempt.transport,
                sticky=attempt.sticky,
                fallback_reason=attempt.fallback_reason,
            )
            for attempt in attempts
        ]

    @staticmethod
    async def _sleep_before_same_provider_retry(retry_interval_ms: int) -> None:
        if retry_interval_ms <= 0:
            return
        await asyncio.sleep(retry_interval_ms / 1000)

    @staticmethod
    def _request_kind(path: str) -> str:
        if path.endswith("/chat/completions"):
            return "chat"
        if path.endswith("/responses"):
            return "response"
        return "request"

    @staticmethod
    def _extract_usage_from_response(response: httpx.Response) -> UsageLogEntry | None:
        return ProxyService._extract_usage_from_bytes(response.content)

    @staticmethod
    def _extract_usage_from_bytes(body: bytes) -> UsageLogEntry | None:
        try:
            payload = json.loads(body)
        except (TypeError, json.JSONDecodeError):
            return None
        return ProxyService._extract_usage_from_payload(payload)

    async def _bind_response_id_from_bytes(
        self,
        body: bytes,
        *,
        provider_name: str,
        southbound_transport: str,
    ) -> None:
        try:
            payload = json.loads(body)
        except (TypeError, json.JSONDecodeError):
            return
        if not isinstance(payload, dict):
            return
        response_id = payload.get("id")
        if not isinstance(response_id, str) or not response_id.strip():
            return
        await self.responses_state.bind_response(
            response_id.strip(),
            provider_name=provider_name,
            southbound_transport=southbound_transport,
        )

    @staticmethod
    def _extract_usage_from_payload(payload: Any) -> UsageLogEntry | None:
        usage_dict = ProxyService._find_usage_dict(payload)
        if usage_dict is None:
            return None

        input_tokens = ProxyService._coerce_int(
            usage_dict.get("input_tokens") or usage_dict.get("prompt_tokens")
        )
        output_tokens = ProxyService._coerce_int(
            usage_dict.get("output_tokens") or usage_dict.get("completion_tokens")
        )
        total_tokens = ProxyService._coerce_int(usage_dict.get("total_tokens"))
        if total_tokens is None and input_tokens is not None and output_tokens is not None:
            total_tokens = input_tokens + output_tokens
        if input_tokens is None and output_tokens is None and total_tokens is None:
            return None
        return UsageLogEntry(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
        )

    @staticmethod
    def _find_usage_dict(payload: Any) -> dict[str, Any] | None:
        if isinstance(payload, dict):
            usage = payload.get("usage")
            if isinstance(usage, dict):
                return usage
            for value in payload.values():
                found = ProxyService._find_usage_dict(value)
                if found is not None:
                    return found
        if isinstance(payload, list):
            for value in payload:
                found = ProxyService._find_usage_dict(value)
                if found is not None:
                    return found
        return None

    @staticmethod
    def _coerce_int(value: Any) -> int | None:
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        return None

    @staticmethod
    def _extract_upstream_error_message(response: httpx.Response) -> str | None:
        return ProxyService._extract_upstream_error_message_from_bytes(
            response.content,
            response.status_code,
        )

    @staticmethod
    def _extract_upstream_error_message_from_bytes(body: bytes, status_code: int) -> str | None:
        try:
            payload = json.loads(body)
        except (TypeError, json.JSONDecodeError):
            return f"Upstream returned status {status_code}."
        if isinstance(payload, dict):
            error = payload.get("error")
            if isinstance(error, dict) and isinstance(error.get("message"), str):
                return error["message"]
            if isinstance(error, str):
                return error
        return f"Upstream returned status {status_code}."

    @staticmethod
    async def _extract_upstream_error_message_from_stream(response: httpx.Response) -> str | None:
        return ProxyService._extract_upstream_error_message_from_bytes(
            await response.aread(),
            response.status_code,
        )

    @staticmethod
    async def _validate_healthcheck_stream(response: httpx.Response) -> tuple[bool, str | None]:
        try:
            async for chunk in response.aiter_raw():
                if chunk:
                    return True, None
        except httpx.HTTPError as exc:
            return False, str(exc)
        return False, "Upstream returned an empty stream."


class ResponsesEventTracker:
    def __init__(
        self,
        *,
        provider_name: str,
        southbound_transport: str,
        responses_state: ResponsesStateStore,
    ) -> None:
        self.provider_name = provider_name
        self.southbound_transport = southbound_transport
        self.responses_state = responses_state
        self.usage: UsageLogEntry | None = None
        self.state = "success"
        self.status_code = 200
        self.error_message: str | None = None

    async def consume(self, payload: Mapping[str, object]) -> None:
        await self._maybe_bind_response(payload)

        usage = ProxyService._extract_usage_from_payload(payload)
        if usage is not None:
            self.usage = usage

        event_type = payload.get("type")
        if event_type == "error":
            self.state = "error"
            self.status_code = self._coerce_status_code(payload.get("status"), default=500)
            self.error_message = self._extract_error_message(payload) or "Upstream websocket returned an error."
        elif event_type == "response.failed":
            self.state = "error"
            response = payload.get("response")
            response_map = response if isinstance(response, Mapping) else {}
            self.status_code = self._coerce_status_code(response_map.get("status"), default=500)
            self.error_message = (
                self._extract_error_message(response_map)
                or self._extract_error_message(payload)
                or "Upstream response failed."
            )
        elif event_type == "response.completed":
            self.state = "success"
            self.status_code = 200

    async def _maybe_bind_response(self, payload: Mapping[str, object]) -> None:
        response_id = self._extract_response_id(payload)
        if response_id is None:
            return
        await self.responses_state.bind_response(
            response_id,
            provider_name=self.provider_name,
            southbound_transport=self.southbound_transport,
        )

    @staticmethod
    def _extract_response_id(payload: Mapping[str, object]) -> str | None:
        response = payload.get("response")
        if isinstance(response, Mapping):
            response_id = response.get("id")
            if isinstance(response_id, str) and response_id.strip():
                return response_id.strip()
        response_id = payload.get("id")
        if isinstance(response_id, str) and response_id.strip():
            return response_id.strip()
        return None

    @staticmethod
    def _extract_error_message(payload: Mapping[str, object]) -> str | None:
        error = payload.get("error")
        if isinstance(error, Mapping):
            message = error.get("message")
            if isinstance(message, str) and message.strip():
                return message.strip()
        if isinstance(error, str) and error.strip():
            return error.strip()
        message = payload.get("message")
        if isinstance(message, str) and message.strip():
            return message.strip()
        return None

    @staticmethod
    def _coerce_status_code(value: object, *, default: int) -> int:
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        return default


class StreamUsageParser:
    """Extracts ``usage`` from a forwarded SSE stream.

    The parser is strictly opportunistic: it exists to populate metrics and
    must never corrupt forwarding. Any decode error, binary body, or
    content-encoding on the upstream response disables the parser and the
    proxy keeps streaming raw bytes unchanged.
    """

    def __init__(self) -> None:
        self._decoder = codecs.getincrementaldecoder("utf-8")()
        self._buffer = ""
        self._disabled = False
        self.usage: UsageLogEntry | None = None
        self.terminal_event_type: str | None = None
        self.terminal_status_code: int | None = None
        self.terminal_error_message: str | None = None

    def disable(self) -> None:
        self._disabled = True
        self._buffer = ""

    def feed(self, chunk: bytes) -> None:
        if self._disabled:
            return
        try:
            self._buffer += self._decoder.decode(chunk)
        except UnicodeDecodeError:
            LOGGER.debug("usage parser disabled after non-utf8 chunk")
            self.disable()
            return
        self._consume_buffer()

    def finish(self) -> None:
        if self._disabled:
            return
        try:
            self._buffer += self._decoder.decode(b"", final=True)
        except UnicodeDecodeError:
            LOGGER.debug("usage parser disabled on final flush")
            self.disable()
            return
        self._consume_buffer(final=True)

    def _consume_buffer(self, *, final: bool = False) -> None:
        separator = "\n\n"
        while separator in self._buffer:
            raw_event, self._buffer = self._buffer.split(separator, 1)
            self._consume_event(raw_event)
        if final and self._buffer.strip():
            self._consume_event(self._buffer)
            self._buffer = ""

    def _consume_event(self, raw_event: str) -> None:
        lines = [line.removeprefix("data:").strip() for line in raw_event.splitlines() if line.startswith("data:")]
        if not lines:
            return
        payload_text = "\n".join(lines).strip()
        if not payload_text or payload_text == "[DONE]":
            if payload_text == "[DONE]":
                self.terminal_event_type = "[DONE]"
                self.terminal_status_code = 200
            return
        try:
            payload = json.loads(payload_text)
        except json.JSONDecodeError:
            return
        usage = ProxyService._extract_usage_from_payload(payload)
        if usage is not None:
            self.usage = usage
        if not isinstance(payload, Mapping):
            return
        self._consume_terminal_event(payload)

    @property
    def terminal_state(self) -> str | None:
        if self.terminal_event_type is None:
            return None
        if self.terminal_event_type in {"error", "response.failed"}:
            return "error"
        return "success"

    def _consume_terminal_event(self, payload: Mapping[str, object]) -> None:
        event_type = payload.get("type")
        if event_type not in TERMINAL_RESPONSE_EVENT_TYPES:
            return
        self.terminal_event_type = str(event_type)
        if event_type == "error":
            self.terminal_status_code = ResponsesEventTracker._coerce_status_code(
                payload.get("status"),
                default=500,
            )
            self.terminal_error_message = (
                ResponsesEventTracker._extract_error_message(payload)
                or "Upstream stream returned an error event."
            )
            return
        if event_type == "response.failed":
            response = payload.get("response")
            response_map = response if isinstance(response, Mapping) else {}
            self.terminal_status_code = ResponsesEventTracker._coerce_status_code(
                response_map.get("status"),
                default=500,
            )
            self.terminal_error_message = (
                ResponsesEventTracker._extract_error_message(response_map)
                or ResponsesEventTracker._extract_error_message(payload)
                or "Upstream response failed."
            )
            return
        self.terminal_status_code = 200
