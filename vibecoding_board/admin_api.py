from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from vibecoding_board.admin_i18n import admin_message, resolve_admin_locale, translate_admin_error
from vibecoding_board.config import HealthcheckConfig, ProviderConfig, RetryPolicyConfig
from vibecoding_board.request_log import RequestLogStore
from vibecoding_board.runtime import RuntimeManager, RuntimeMutationError


class ProviderCreatePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    base_url: str
    api_key: str
    enabled: bool = True
    always_alive: bool = False
    priority: int | None = None
    models: list[str] = Field(min_length=1)
    healthcheck_model: str | None = None
    timeout_seconds: float = Field(default=60.0, gt=0)
    max_failures: int = Field(default=3, ge=1)
    cooldown_seconds: float = Field(default=30.0, ge=0)

    def to_provider_config(self, *, default_priority: int) -> ProviderConfig:
        return ProviderConfig(
            name=self.name,
            base_url=self.base_url,
            api_key=self.api_key,
            enabled=self.enabled,
            always_alive=self.always_alive,
            priority=self.priority if self.priority is not None else default_priority,
            models=self.models,
            healthcheck_model=self.healthcheck_model,
            timeout_seconds=self.timeout_seconds,
            max_failures=self.max_failures,
            cooldown_seconds=self.cooldown_seconds,
        )


class ProviderUpdatePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    base_url: str
    api_key: str | None = None
    enabled: bool = True
    always_alive: bool = False
    priority: int | None = None
    models: list[str] = Field(min_length=1)
    healthcheck_model: str | None = None
    timeout_seconds: float = Field(default=60.0, gt=0)
    max_failures: int = Field(default=3, ge=1)
    cooldown_seconds: float = Field(default=30.0, ge=0)

    def to_provider_config(
        self,
        *,
        default_priority: int,
        existing_api_key: str,
    ) -> ProviderConfig:
        api_key = (self.api_key or "").strip() or existing_api_key
        return ProviderConfig(
            name=self.name,
            base_url=self.base_url,
            api_key=api_key,
            enabled=self.enabled,
            always_alive=self.always_alive,
            priority=self.priority if self.priority is not None else default_priority,
            models=self.models,
            healthcheck_model=self.healthcheck_model,
            timeout_seconds=self.timeout_seconds,
            max_failures=self.max_failures,
            cooldown_seconds=self.cooldown_seconds,
        )


class ProviderPriorityUpdatePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    priority: int


class RetryPolicyUpdatePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    retryable_status_codes: list[int]
    same_provider_retry_count: int = Field(ge=0)
    retry_interval_ms: int = Field(ge=0)

    def to_retry_policy_config(self) -> RetryPolicyConfig:
        return RetryPolicyConfig(
            retryable_status_codes=self.retryable_status_codes,
            same_provider_retry_count=self.same_provider_retry_count,
            retry_interval_ms=self.retry_interval_ms,
        )


class HealthcheckUpdatePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stream: bool

    def to_healthcheck_config(self) -> HealthcheckConfig:
        return HealthcheckConfig(stream=self.stream)


def build_admin_router() -> APIRouter:
    router = APIRouter(prefix="/admin/api", tags=["admin"])

    def get_manager(request: Request) -> RuntimeManager:
        return request.app.state.runtime_manager

    def get_request_log_store(request: Request) -> RequestLogStore:
        return request.app.state.request_log_store

    async def build_dashboard_payload(
        manager: RuntimeManager,
        request_log_store: RequestLogStore,
    ) -> dict[str, object]:
        dashboard = await manager.dashboard()
        dashboard["recent_requests"] = await request_log_store.list_entries()
        dashboard["stats"] = await request_log_store.aggregated_stats(
            [provider["name"] for provider in dashboard["providers"]]
        )
        return dashboard

    async def mutation_response(
        manager: RuntimeManager,
        request_log_store: RequestLogStore,
        message: str,
    ) -> dict[str, object]:
        return {
            "message": message,
            "dashboard": await build_dashboard_payload(manager, request_log_store),
        }

    @router.get("/dashboard")
    async def dashboard(request: Request):
        return await build_dashboard_payload(
            get_manager(request),
            get_request_log_store(request),
        )

    @router.get("/metrics")
    async def metrics(
        request: Request,
        window: Literal["24h", "7d"] = "24h",
    ):
        return await request.app.state.metrics_store.metrics_payload(window=window)

    @router.patch("/retry-policy")
    async def update_retry_policy(payload: RetryPolicyUpdatePayload, request: Request):
        locale = resolve_admin_locale(request)
        manager = get_manager(request)
        request_log_store = get_request_log_store(request)
        try:
            await manager.update_retry_policy(payload.to_retry_policy_config())
        except RuntimeMutationError as exc:
            raise HTTPException(
                status_code=exc.status_code,
                detail=translate_admin_error(locale, str(exc)),
            ) from exc
        return await mutation_response(
            manager,
            request_log_store,
            admin_message(locale, "updated_retry_policy"),
        )

    @router.patch("/healthcheck-settings")
    async def update_healthcheck_settings(payload: HealthcheckUpdatePayload, request: Request):
        locale = resolve_admin_locale(request)
        manager = get_manager(request)
        request_log_store = get_request_log_store(request)
        try:
            await manager.update_healthcheck(payload.to_healthcheck_config())
        except RuntimeMutationError as exc:
            raise HTTPException(
                status_code=exc.status_code,
                detail=translate_admin_error(locale, str(exc)),
            ) from exc
        return await mutation_response(
            manager,
            request_log_store,
            admin_message(locale, "updated_healthcheck_settings"),
        )

    @router.post("/providers")
    async def create_provider(payload: ProviderCreatePayload, request: Request):
        locale = resolve_admin_locale(request)
        manager = get_manager(request)
        request_log_store = get_request_log_store(request)
        current = manager.current().config
        provider = payload.to_provider_config(
            default_priority=max(p.priority for p in current.providers) + 10
        )
        try:
            await manager.add_provider(provider)
        except RuntimeMutationError as exc:
            raise HTTPException(
                status_code=exc.status_code,
                detail=translate_admin_error(locale, str(exc)),
            ) from exc
        return await mutation_response(
            manager,
            request_log_store,
            admin_message(locale, "added_provider", provider=provider.name),
        )

    @router.put("/providers/{provider_name}")
    async def update_provider(
        provider_name: str,
        payload: ProviderUpdatePayload,
        request: Request,
    ):
        locale = resolve_admin_locale(request)
        manager = get_manager(request)
        request_log_store = get_request_log_store(request)
        current = manager.current().config
        existing = next((provider for provider in current.providers if provider.name == provider_name), None)
        if existing is None:
            raise HTTPException(
                status_code=404,
                detail=admin_message(locale, "provider_not_found", provider=provider_name),
            )

        replacement = payload.to_provider_config(
            default_priority=existing.priority,
            existing_api_key=existing.api_key,
        )
        try:
            await manager.update_provider(provider_name, replacement)
        except RuntimeMutationError as exc:
            raise HTTPException(
                status_code=exc.status_code,
                detail=translate_admin_error(locale, str(exc)),
            ) from exc
        return await mutation_response(
            manager,
            request_log_store,
            admin_message(locale, "updated_provider", provider=provider_name),
        )

    @router.patch("/providers/{provider_name}/priority")
    async def update_provider_priority(
        provider_name: str,
        payload: ProviderPriorityUpdatePayload,
        request: Request,
    ):
        locale = resolve_admin_locale(request)
        manager = get_manager(request)
        request_log_store = get_request_log_store(request)
        try:
            await manager.update_provider_priority(provider_name, payload.priority)
        except RuntimeMutationError as exc:
            raise HTTPException(
                status_code=exc.status_code,
                detail=translate_admin_error(locale, str(exc)),
            ) from exc
        return await mutation_response(
            manager,
            request_log_store,
            admin_message(locale, "updated_priority", provider=provider_name),
        )

    @router.post("/providers/{provider_name}/promote")
    async def promote_provider(provider_name: str, request: Request):
        locale = resolve_admin_locale(request)
        manager = get_manager(request)
        request_log_store = get_request_log_store(request)
        try:
            await manager.promote_provider(provider_name)
        except RuntimeMutationError as exc:
            raise HTTPException(
                status_code=exc.status_code,
                detail=translate_admin_error(locale, str(exc)),
            ) from exc
        return await mutation_response(
            manager,
            request_log_store,
            admin_message(locale, "promoted_provider", provider=provider_name),
        )

    @router.post("/providers/{provider_name}/toggle")
    async def toggle_provider(provider_name: str, request: Request):
        locale = resolve_admin_locale(request)
        manager = get_manager(request)
        request_log_store = get_request_log_store(request)
        try:
            await manager.toggle_provider(provider_name)
        except RuntimeMutationError as exc:
            raise HTTPException(
                status_code=exc.status_code,
                detail=translate_admin_error(locale, str(exc)),
            ) from exc
        return await mutation_response(
            manager,
            request_log_store,
            admin_message(locale, "toggled_provider", provider=provider_name),
        )

    @router.post("/providers/{provider_name}/always-alive/toggle")
    async def toggle_provider_always_alive(provider_name: str, request: Request):
        locale = resolve_admin_locale(request)
        manager = get_manager(request)
        request_log_store = get_request_log_store(request)
        try:
            await manager.toggle_provider_always_alive(provider_name)
        except RuntimeMutationError as exc:
            raise HTTPException(
                status_code=exc.status_code,
                detail=translate_admin_error(locale, str(exc)),
            ) from exc
        return await mutation_response(
            manager,
            request_log_store,
            admin_message(locale, "toggled_provider_always_alive", provider=provider_name),
        )

    @router.post("/providers/{provider_name}/healthcheck")
    async def healthcheck_provider(provider_name: str, request: Request):
        locale = resolve_admin_locale(request)
        manager = get_manager(request)
        request_log_store = get_request_log_store(request)
        try:
            result = await request.app.state.service.run_provider_healthcheck(provider_name)
        except RuntimeMutationError as exc:
            raise HTTPException(
                status_code=exc.status_code,
                detail=translate_admin_error(locale, str(exc)),
            ) from exc
        message_key = "healthcheck_passed" if result["ok"] else "healthcheck_failed"
        return await mutation_response(
            manager,
            request_log_store,
            admin_message(locale, message_key, provider=provider_name),
        )

    @router.delete("/providers/{provider_name}")
    async def delete_provider(provider_name: str, request: Request):
        locale = resolve_admin_locale(request)
        manager = get_manager(request)
        request_log_store = get_request_log_store(request)
        try:
            await manager.delete_provider(provider_name)
        except RuntimeMutationError as exc:
            raise HTTPException(
                status_code=exc.status_code,
                detail=translate_admin_error(locale, str(exc)),
            ) from exc
        return await mutation_response(
            manager,
            request_log_store,
            admin_message(locale, "deleted_provider", provider=provider_name),
        )

    return router
