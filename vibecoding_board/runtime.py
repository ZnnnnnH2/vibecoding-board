from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import asyncio

from vibecoding_board.config import PRIORITY_STEP, ConfigError, ProviderConfig, ProxyConfig, RetryPolicyConfig
from vibecoding_board.config_store import ConfigStore
from vibecoding_board.registry import ProviderRegistry, ProviderSnapshot, utc_now


class RuntimeMutationError(ValueError):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(slots=True, frozen=True)
class RuntimeSnapshot:
    config: ProxyConfig
    registry: ProviderRegistry
    reloaded_at: datetime
    config_path: Path


@dataclass(slots=True, frozen=True)
class HealthcheckSnapshot:
    provider_name: str
    checked_at: datetime | None
    ok: bool | None
    status_code: int | None
    latency_ms: int | None
    model: str | None
    error: str | None


class RuntimeManager:
    def __init__(self, config_path: str | Path) -> None:
        self.config_store = ConfigStore(config_path)
        self._mutation_lock = asyncio.Lock()
        self._health_lock = asyncio.Lock()
        self._runtime: RuntimeSnapshot | None = None
        self._healthchecks: dict[str, HealthcheckSnapshot] = {}

    async def initialize(self) -> RuntimeSnapshot:
        config = self.config_store.load()
        runtime = await self._build_runtime(config, previous=self._runtime)
        self._runtime = runtime
        return runtime

    def current(self) -> RuntimeSnapshot:
        if self._runtime is None:
            raise RuntimeMutationError("runtime is not initialized", status_code=500)
        return self._runtime

    async def dashboard(self) -> dict[str, object]:
        runtime = self.current()
        providers = await runtime.registry.list_states()
        healthchecks = await self._healthcheck_map([provider.name for provider in providers])
        return {
            "config_path": str(runtime.config_path),
            "listen_host": runtime.config.listen.host,
            "listen_port": runtime.config.listen.port,
            "primary_provider": runtime.config.primary_provider_name(),
            "reloaded_at": runtime.reloaded_at,
            "retry_policy": runtime.config.retry_policy.model_dump(mode="python"),
            "providers": [
                self._provider_to_public_dict(provider, healthchecks[provider.name])
                for provider in providers
            ],
        }

    async def record_healthcheck(
        self,
        provider_name: str,
        *,
        ok: bool,
        status_code: int | None,
        latency_ms: int | None,
        model: str | None,
        error: str | None,
    ) -> None:
        async with self._health_lock:
            self._healthchecks[provider_name] = HealthcheckSnapshot(
                provider_name=provider_name,
                checked_at=utc_now(),
                ok=ok,
                status_code=status_code,
                latency_ms=latency_ms,
                model=model,
                error=error,
            )

    async def add_provider(self, provider: ProviderConfig) -> RuntimeSnapshot:
        async with self._mutation_lock:
            config = self.current().config.model_copy(deep=True)
            providers = list(config.providers)
            providers.append(provider)
            updated = ProxyConfig(
                listen=config.listen.model_copy(deep=True),
                retry_policy=config.retry_policy.model_copy(deep=True),
                providers=providers,
            )
            return await self._persist_and_activate(updated)

    async def update_provider(
        self,
        current_name: str,
        updated_provider: ProviderConfig,
        *,
        preserve_api_key_when_blank: bool = True,
    ) -> RuntimeSnapshot:
        async with self._mutation_lock:
            config = self.current().config.model_copy(deep=True)
            providers = list(config.providers)
            index = self._find_provider_index(providers, current_name)
            existing = providers[index]
            api_key = updated_provider.api_key
            if preserve_api_key_when_blank and not api_key.strip():
                api_key = existing.api_key
            replacement = updated_provider.model_copy(
                update={
                    "api_key": api_key,
                }
            )
            providers[index] = replacement
            updated = ProxyConfig(
                listen=config.listen.model_copy(deep=True),
                retry_policy=config.retry_policy.model_copy(deep=True),
                providers=providers,
            )
            return await self._persist_and_activate(updated)

    async def update_provider_priority(
        self,
        provider_name: str,
        priority: int,
    ) -> RuntimeSnapshot:
        async with self._mutation_lock:
            config = self.current().config.model_copy(deep=True)
            providers = list(config.providers)
            index = self._find_provider_index(providers, provider_name)
            providers[index] = providers[index].model_copy(update={"priority": priority})
            updated = ProxyConfig(
                listen=config.listen.model_copy(deep=True),
                retry_policy=config.retry_policy.model_copy(deep=True),
                providers=providers,
            )
            return await self._persist_and_activate(updated)

    async def toggle_provider(self, provider_name: str) -> RuntimeSnapshot:
        async with self._mutation_lock:
            config = self.current().config.model_copy(deep=True)
            providers = list(config.providers)
            index = self._find_provider_index(providers, provider_name)
            current = providers[index]
            providers[index] = current.model_copy(update={"enabled": not current.enabled})
            updated = ProxyConfig(
                listen=config.listen.model_copy(deep=True),
                retry_policy=config.retry_policy.model_copy(deep=True),
                providers=providers,
            )
            return await self._persist_and_activate(updated)

    async def promote_provider(self, provider_name: str) -> RuntimeSnapshot:
        async with self._mutation_lock:
            config = self.current().config.model_copy(deep=True)
            providers = list(config.providers)
            index = self._find_provider_index(providers, provider_name)
            current_min = min(provider.priority for provider in providers)
            promoted = providers[index]
            providers[index] = promoted.model_copy(update={"priority": current_min - PRIORITY_STEP})
            updated = ProxyConfig(
                listen=config.listen.model_copy(deep=True),
                retry_policy=config.retry_policy.model_copy(deep=True),
                providers=providers,
            )
            return await self._persist_and_activate(updated)

    async def delete_provider(self, provider_name: str) -> RuntimeSnapshot:
        async with self._mutation_lock:
            config = self.current().config.model_copy(deep=True)
            providers = list(config.providers)
            if len(providers) == 1:
                raise RuntimeMutationError("At least one provider must remain configured.")
            index = self._find_provider_index(providers, provider_name)
            providers.pop(index)
            updated = ProxyConfig(
                listen=config.listen.model_copy(deep=True),
                retry_policy=config.retry_policy.model_copy(deep=True),
                providers=providers,
            )
            return await self._persist_and_activate(updated)

    async def update_retry_policy(self, retry_policy: RetryPolicyConfig) -> RuntimeSnapshot:
        async with self._mutation_lock:
            config = self.current().config.model_copy(deep=True)
            updated = ProxyConfig(
                listen=config.listen.model_copy(deep=True),
                retry_policy=retry_policy,
                providers=[provider.model_copy(deep=True) for provider in config.providers],
            )
            return await self._persist_and_activate(updated)

    async def _persist_and_activate(self, config: ProxyConfig) -> RuntimeSnapshot:
        runtime = await self._build_runtime(config, previous=self.current())
        self.config_store.save(config)
        self._runtime = runtime
        return runtime

    async def _build_runtime(
        self,
        config: ProxyConfig,
        *,
        previous: RuntimeSnapshot | None,
    ) -> RuntimeSnapshot:
        try:
            runtime_providers = [provider.to_runtime_provider() for provider in config.providers]
        except ConfigError as exc:
            raise RuntimeMutationError(str(exc)) from exc

        registry = ProviderRegistry(runtime_providers)
        if previous is not None:
            await registry.import_states(await previous.registry.list_states())
        return RuntimeSnapshot(
            config=config,
            registry=registry,
            reloaded_at=utc_now(),
            config_path=self.config_store.path,
        )

    async def _healthcheck_map(self, provider_names: list[str]) -> dict[str, HealthcheckSnapshot]:
        async with self._health_lock:
            return {
                provider_name: self._healthchecks.get(
                    provider_name,
                    HealthcheckSnapshot(
                        provider_name=provider_name,
                        checked_at=None,
                        ok=None,
                        status_code=None,
                        latency_ms=None,
                        model=None,
                        error=None,
                    ),
                )
                for provider_name in provider_names
            }

    @staticmethod
    def _provider_to_public_dict(
        provider: ProviderSnapshot,
        healthcheck: HealthcheckSnapshot,
    ) -> dict[str, object]:
        return {
            "name": provider.name,
            "base_url": provider.base_url,
            "enabled": provider.enabled,
            "priority": provider.priority,
            "timeout_seconds": provider.timeout_seconds,
            "max_failures": provider.max_failures,
            "cooldown_seconds": provider.cooldown_seconds,
            "models": list(provider.models),
            "supports_all_models": provider.supports_all_models,
            "healthcheck_model": provider.healthcheck_model,
            "consecutive_failures": provider.consecutive_failures,
            "cooldown_until": provider.cooldown_until,
            "last_error": provider.last_error,
            "last_failure_at": provider.last_failure_at,
            "last_success_at": provider.last_success_at,
            "has_api_key": bool(provider.api_key),
            "healthcheck": {
                "checked_at": healthcheck.checked_at,
                "ok": healthcheck.ok,
                "status_code": healthcheck.status_code,
                "latency_ms": healthcheck.latency_ms,
                "model": healthcheck.model,
                "error": healthcheck.error,
            },
        }

    @staticmethod
    def _next_priority(providers: list[ProviderConfig]) -> int:
        if not providers:
            return PRIORITY_STEP
        return max(provider.priority for provider in providers) + PRIORITY_STEP

    @staticmethod
    def _find_provider_index(providers: list[ProviderConfig], provider_name: str) -> int:
        for index, provider in enumerate(providers):
            if provider.name == provider_name:
                return index
        raise RuntimeMutationError(
            f"Provider {provider_name!r} does not exist.",
            status_code=404,
        )
