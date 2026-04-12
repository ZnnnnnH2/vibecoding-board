from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from vibecoding_board.admin_api import build_admin_router
from vibecoding_board.admin_metrics import AdminMetricsStore
from vibecoding_board.request_log import RequestLogStore
from vibecoding_board.runtime import RuntimeManager, RuntimeMutationError
from vibecoding_board.service import ProxyService, build_error_response


STATIC_ADMIN_DIR = Path(__file__).resolve().parent / "static" / "admin"

# Connection pool sized for a concurrent aggregation proxy. The defaults
# (max_connections=100, max_keepalive_connections=20) start queueing long
# before uvicorn/asyncio would, which caps throughput for no good reason.
UPSTREAM_POOL_LIMITS = httpx.Limits(
    max_connections=1000,
    max_keepalive_connections=200,
    keepalive_expiry=30.0,
)


def create_app(
    config_path: str | Path,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> FastAPI:
    config_path = Path(config_path).resolve()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        client = httpx.AsyncClient(
            timeout=None,
            transport=transport,
            follow_redirects=False,
            limits=UPSTREAM_POOL_LIMITS,
        )
        runtime_manager = RuntimeManager(config_path)
        request_log_store = RequestLogStore()
        metrics_store = AdminMetricsStore(config_path.parent / "data" / "metrics" / "admin_hourly.json")
        metrics_store.load()
        await runtime_manager.initialize()
        app.state.runtime_manager = runtime_manager
        app.state.request_log_store = request_log_store
        app.state.metrics_store = metrics_store
        app.state.service = ProxyService(
            runtime_manager=runtime_manager,
            request_log_store=request_log_store,
            metrics_store=metrics_store,
            client=client,
        )
        try:
            yield
        finally:
            await metrics_store.close()
            await client.aclose()

    app = FastAPI(title="vibecoding-board", version="0.1.0", lifespan=lifespan)

    app.include_router(build_admin_router())

    @app.get("/admin", include_in_schema=False)
    async def admin_redirect():
        return RedirectResponse(url="/admin/")

    @app.post("/v1/chat/completions")
    async def chat_completions(request: Request):
        return await app.state.service.proxy_post("/v1/chat/completions", request)

    @app.post("/v1/responses")
    async def responses(request: Request):
        return await app.state.service.proxy_post("/v1/responses", request)

    @app.get("/v1/models")
    async def list_models():
        return await app.state.service.list_models()

    @app.get("/healthz")
    async def healthz():
        return app.state.service.health()

    @app.exception_handler(ValueError)
    async def handle_value_error(_: Request, exc: ValueError):
        return build_error_response(
            message=str(exc),
            status_code=400,
            error_type="invalid_request_error",
            code="invalid_json",
        )

    @app.exception_handler(RuntimeMutationError)
    async def handle_runtime_error(_: Request, exc: RuntimeMutationError):
        return build_error_response(
            message=str(exc),
            status_code=exc.status_code,
            error_type="admin_error",
            code="admin_invalid_request",
        )

    if STATIC_ADMIN_DIR.exists():
        app.mount("/admin", StaticFiles(directory=STATIC_ADMIN_DIR, html=True), name="admin-ui")
    else:
        @app.get("/admin/", include_in_schema=False)
        async def admin_not_built():
            return HTMLResponse(
                "<html><body><h1>Admin UI not built</h1>"
                "<p>Run the frontend build to populate vibecoding_board/static/admin.</p>"
                "</body></html>",
                status_code=503,
            )

    return app


def create_app_from_config(
    config_path: str | Path,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> FastAPI:
    return create_app(config_path, transport=transport)
