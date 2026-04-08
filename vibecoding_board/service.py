from __future__ import annotations

import codecs
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
import json
import logging
from time import perf_counter
from typing import Any

import httpx
from fastapi import Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from vibecoding_board.admin_metrics import AdminMetricsStore
from vibecoding_board.config import ConfigError
from vibecoding_board.request_log import AttemptLogEntry, RequestLogStore
from vibecoding_board.request_log import UsageLogEntry
from vibecoding_board.registry import ProviderRegistry, ProviderSnapshot
from vibecoding_board.runtime import RuntimeManager, RuntimeMutationError


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

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
NON_RETRYABLE_STATUS_CODES = {400, 401, 403, 404}
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


@dataclass(slots=True)
class AttemptResult:
    provider: str
    url: str
    outcome: str
    retryable: bool
    status_code: int | None = None


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
            }
            for attempt in attempts
        ]
    return JSONResponse(status_code=status_code, content=payload)


def normalize_response_headers(headers: Mapping[str, str]) -> dict[str, str]:
    return {
        key: value
        for key, value in headers.items()
        if key.lower() not in HOP_BY_HOP_HEADERS
    }


def build_upstream_headers(
    incoming_headers: Mapping[str, str], provider: ProviderSnapshot
) -> dict[str, str]:
    headers = {
        key: value
        for key, value in incoming_headers.items()
        if key.lower() not in HOP_BY_HOP_HEADERS and key.lower() != "authorization"
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


def classify_status(status_code: int) -> str:
    if status_code in RETRYABLE_STATUS_CODES:
        return "retryable"
    if status_code in NON_RETRYABLE_STATUS_CODES:
        return "non_retryable"
    if 200 <= status_code < 400:
        return "success"
    return "non_retryable"


class ProxyService:
    def __init__(
        self,
        *,
        runtime_manager: RuntimeManager,
        request_log_store: RequestLogStore,
        metrics_store: AdminMetricsStore,
        client: httpx.AsyncClient,
    ) -> None:
        self.runtime_manager = runtime_manager
        self.request_log_store = request_log_store
        self.metrics_store = metrics_store
        self.client = client

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
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": "healthcheck"}],
            "max_tokens": 1,
            "stream": False,
        }

        started_at = perf_counter()
        status_code: int | None = None
        ok = False
        error: str | None = None

        try:
            response = await self.client.post(
                url,
                content=json.dumps(payload).encode("utf-8"),
                headers=build_direct_provider_headers(runtime_provider.api_key),
                timeout=runtime_provider.timeout_seconds,
            )
            status_code = response.status_code
            ok = 200 <= response.status_code < 300
            if not ok:
                error = self._extract_response_error_message(response)
        except httpx.HTTPError as exc:
            error = str(exc)

        latency_ms = int((perf_counter() - started_at) * 1000)
        await self.runtime_manager.record_healthcheck(
            provider_name,
            ok=ok,
            status_code=status_code,
            latency_ms=latency_ms,
            model=model,
            error=error,
        )
        return {
            "provider_name": provider_name,
            "ok": ok,
            "status_code": status_code,
            "latency_ms": latency_ms,
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
        candidates = await runtime.registry.get_candidates(model)
        if not candidates:
            return build_error_response(
                message=f"No enabled upstream provider is configured for model {model!r}.",
                status_code=404,
                error_type="not_found_error",
                code="model_not_available",
            )

        log_id = await self.request_log_store.begin(
            endpoint=path,
            request_kind=request_kind,
            model=model,
            stream=stream,
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
                log_id=log_id,
                started_at=started_at,
            )
        return await self._proxy_non_stream(
            path=path,
            body=body,
            incoming_headers=request.headers,
            model=model,
            candidates=candidates,
            registry=runtime.registry,
            log_id=log_id,
            started_at=started_at,
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

    async def _proxy_non_stream(
        self,
        *,
        path: str,
        body: bytes,
        incoming_headers: Mapping[str, str],
        model: str,
        candidates: list[ProviderSnapshot],
        registry: ProviderRegistry,
        log_id: str,
        started_at: float,
    ) -> Response:
        attempts: list[AttemptResult] = []
        for provider in candidates:
            headers = build_upstream_headers(incoming_headers, provider)
            url = build_upstream_url(provider, path)
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
                    )
                )
                LOGGER.warning("upstream request failed before response", extra={"provider": provider.name})
                continue

            status_kind = classify_status(response.status_code)
            if status_kind == "retryable":
                await registry.mark_retryable_failure(provider.name, f"retryable status {response.status_code}")
                attempts.append(
                    AttemptResult(
                        provider=provider.name,
                        url=url,
                        outcome="status_retryable",
                        retryable=True,
                        status_code=response.status_code,
                    )
                )
                LOGGER.warning(
                    "upstream returned retryable status",
                    extra={"provider": provider.name, "status_code": response.status_code},
                )
                continue

            await registry.mark_success(provider.name)
            duration_ms = int((perf_counter() - started_at) * 1000)
            usage = self._extract_usage_from_response(response)
            await self._finalize_request(
                log_id,
                final_provider=provider.name,
                final_url=url,
                status_code=response.status_code,
                duration_ms=duration_ms,
                ttfb_ms=duration_ms,
                state="success",
                error=None,
                usage=usage,
                attempts=self._to_attempt_logs(attempts),
            )
            return Response(
                content=response.content,
                status_code=response.status_code,
                headers=normalize_response_headers(response.headers),
            )

        await self._finalize_request(
            log_id,
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
        log_id: str,
        started_at: float,
    ) -> Response:
        attempts: list[AttemptResult] = []
        for provider in candidates:
            url = build_upstream_url(provider, path)
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
                    )
                )
                continue

            status_kind = classify_status(response.status_code)
            if status_kind == "retryable":
                await registry.mark_retryable_failure(provider.name, f"retryable status {response.status_code}")
                attempts.append(
                    AttemptResult(
                        provider=provider.name,
                        url=url,
                        outcome="status_retryable",
                        retryable=True,
                        status_code=response.status_code,
                    )
                )
                await response.aclose()
                continue

            if status_kind == "non_retryable":
                body_bytes = await response.aread()
                await registry.mark_success(provider.name)
                await response.aclose()
                duration_ms = int((perf_counter() - started_at) * 1000)
                usage = self._extract_usage_from_bytes(body_bytes)
                await self._finalize_request(
                    log_id,
                    final_provider=provider.name,
                    final_url=url,
                    status_code=response.status_code,
                    duration_ms=duration_ms,
                    ttfb_ms=duration_ms,
                    state="success",
                    error=None,
                    usage=usage,
                    attempts=self._to_attempt_logs(attempts),
                )
                return Response(
                    content=body_bytes,
                    status_code=response.status_code,
                    headers=normalize_response_headers(response.headers),
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
                    )
                )
                await response.aclose()
                continue

            return StreamingResponse(
                self._stream_response(
                    registry=registry,
                    provider=provider,
                    final_url=url,
                    response=response,
                    first_chunk=first_chunk,
                    stream_iterator=stream_iterator,
                    log_id=log_id,
                    started_at=started_at,
                    ttfb_ms=ttfb_ms,
                    attempts=self._to_attempt_logs(attempts),
                ),
                status_code=response.status_code,
                headers=normalize_response_headers(response.headers),
            )

        await self._finalize_request(
            log_id,
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
        log_id: str,
        started_at: float,
        ttfb_ms: int | None,
        attempts: list[AttemptLogEntry],
    ) -> AsyncIterator[bytes]:
        completed = False
        error_message: str | None = None
        usage: UsageLogEntry | None = None
        parser = StreamUsageParser()
        try:
            if first_chunk:
                parser.feed(first_chunk)
                usage = parser.usage or usage
                yield first_chunk
            async for chunk in stream_iterator:
                parser.feed(chunk)
                usage = parser.usage or usage
                yield chunk
            parser.finish()
            usage = parser.usage or usage
            completed = True
        except RETRYABLE_EXCEPTIONS as exc:
            await registry.mark_retryable_failure(provider.name, str(exc))
            error_message = str(exc)
            LOGGER.warning(
                "upstream stream interrupted after response start",
                extra={"provider": provider.name, "error": type(exc).__name__},
            )
        finally:
            await response.aclose()
            if completed:
                await registry.mark_success(provider.name)
            await self._finalize_request(
                log_id,
                final_provider=provider.name,
                final_url=final_url,
                status_code=response.status_code,
                duration_ms=int((perf_counter() - started_at) * 1000),
                ttfb_ms=ttfb_ms,
                state="success" if completed else "interrupted",
                error=error_message,
                usage=usage,
                attempts=attempts,
            )

    async def _finalize_request(
        self,
        entry_id: str,
        *,
        final_provider: str | None,
        final_url: str | None,
        status_code: int | None,
        duration_ms: int,
        ttfb_ms: int | None,
        state: str,
        error: str | None,
        usage: UsageLogEntry | None,
        attempts: list[AttemptLogEntry],
    ) -> None:
        await self.request_log_store.complete(
            entry_id,
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
            )
            for attempt in attempts
        ]

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
    def _extract_response_error_message(response: httpx.Response) -> str | None:
        try:
            payload = response.json()
        except json.JSONDecodeError:
            return f"Health check returned status {response.status_code}."
        if isinstance(payload, dict):
            error = payload.get("error")
            if isinstance(error, dict) and isinstance(error.get("message"), str):
                return error["message"]
            if isinstance(error, str):
                return error
        return f"Health check returned status {response.status_code}."


class StreamUsageParser:
    def __init__(self) -> None:
        self._decoder = codecs.getincrementaldecoder("utf-8")()
        self._buffer = ""
        self.usage: UsageLogEntry | None = None

    def feed(self, chunk: bytes) -> None:
        self._buffer += self._decoder.decode(chunk)
        self._consume_buffer()

    def finish(self) -> None:
        self._buffer += self._decoder.decode(b"", final=True)
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
            return
        try:
            payload = json.loads(payload_text)
        except json.JSONDecodeError:
            return
        usage = ProxyService._extract_usage_from_payload(payload)
        if usage is not None:
            self.usage = usage
