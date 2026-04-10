from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


ENV_PREFIX = "env:"
PRIORITY_STEP = 10
DEFAULT_RETRYABLE_STATUS_CODES = (429, 500, 502, 503, 504)


class ConfigError(ValueError):
    pass


@dataclass(slots=True, frozen=True)
class RuntimeProvider:
    name: str
    base_url: str
    api_key: str
    enabled: bool
    priority: int
    models: tuple[str, ...]
    healthcheck_model: str | None
    timeout_seconds: float
    max_failures: int
    cooldown_seconds: float

    def supports_model(self, model: str) -> bool:
        return "*" in self.models or model in self.models

    def advertised_models(self) -> list[str]:
        return [model for model in self.models if model != "*"]

    @property
    def supports_all_models(self) -> bool:
        return "*" in self.models

    def healthcheck_target_model(self) -> str | None:
        if self.supports_all_models:
            return self.healthcheck_model
        return self.models[0] if self.models else None


class ListenConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    host: str = "127.0.0.1"
    port: int = 9000


class RetryPolicyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    retryable_status_codes: list[int] = Field(
        default_factory=lambda: list(DEFAULT_RETRYABLE_STATUS_CODES)
    )
    same_provider_retry_count: int = Field(default=0, ge=0)
    retry_interval_ms: int = Field(default=0, ge=0)

    @field_validator("retryable_status_codes")
    @classmethod
    def normalize_retryable_status_codes(cls, value: list[int]) -> list[int]:
        normalized = sorted({int(status_code) for status_code in value})
        invalid = [status_code for status_code in normalized if status_code < 400 or status_code > 599]
        if invalid:
            raise ValueError("retryable_status_codes must contain only HTTP status codes from 400 to 599")
        return normalized

    def retryable_status_set(self) -> set[int]:
        return set(self.retryable_status_codes)


class ProviderConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    base_url: str
    api_key: str
    enabled: bool = True
    priority: int = 100
    models: list[str] = Field(min_length=1)
    healthcheck_model: str | None = None
    timeout_seconds: float = Field(default=60.0, gt=0)
    max_failures: int = Field(default=3, ge=1)
    cooldown_seconds: float = Field(default=30.0, ge=0)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("name must not be empty")
        return cleaned

    @field_validator("base_url")
    @classmethod
    def normalize_base_url(cls, value: str) -> str:
        cleaned = value.strip().rstrip("/")
        if not cleaned:
            raise ValueError("base_url must not be empty")
        return cleaned

    @field_validator("api_key")
    @classmethod
    def validate_api_key(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("api_key must not be empty")
        return cleaned

    @field_validator("healthcheck_model")
    @classmethod
    def normalize_healthcheck_model(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @field_validator("models")
    @classmethod
    def normalize_models(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value if item.strip()]
        if not cleaned:
            raise ValueError("models must contain at least one entry")
        if "*" in cleaned:
            return ["*"]
        return cleaned

    def supports_model(self, model: str) -> bool:
        return "*" in self.models or model in self.models

    @property
    def supports_all_models(self) -> bool:
        return "*" in self.models

    def advertised_models(self) -> list[str]:
        return [model for model in self.models if model != "*"]

    def resolve_api_key(self) -> str:
        if self.api_key.startswith(ENV_PREFIX):
            env_name = self.api_key[len(ENV_PREFIX) :].strip()
            if not env_name:
                raise ConfigError("api_key env reference must include a variable name")
            resolved = os.getenv(env_name)
            if not resolved:
                raise ConfigError(f"environment variable {env_name!r} is not set")
            return resolved
        return self.api_key

    def to_runtime_provider(self) -> RuntimeProvider:
        return RuntimeProvider(
            name=self.name,
            base_url=self.base_url,
            api_key=self.resolve_api_key(),
            enabled=self.enabled,
            priority=self.priority,
            models=tuple(self.models),
            healthcheck_model=self.healthcheck_model,
            timeout_seconds=self.timeout_seconds,
            max_failures=self.max_failures,
            cooldown_seconds=self.cooldown_seconds,
        )


class ProxyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    listen: ListenConfig = Field(default_factory=ListenConfig)
    retry_policy: RetryPolicyConfig = Field(default_factory=RetryPolicyConfig)
    providers: list[ProviderConfig] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_names(self) -> "ProxyConfig":
        names = [provider.name for provider in self.providers]
        if len(names) != len(set(names)):
            raise ValueError("provider names must be unique")
        return self

    def advertised_models(self) -> list[str]:
        models = {
            model
            for provider in self.providers
            if provider.enabled
            for model in provider.advertised_models()
        }
        return sorted(models)

    def primary_provider_name(self) -> str | None:
        enabled = [provider for provider in self.providers if provider.enabled]
        if not enabled:
            return None
        primary = sorted(enabled, key=lambda provider: (provider.priority, provider.name))[0]
        return primary.name

    def normalized(self) -> "ProxyConfig":
        ordered = sorted(
            self.providers,
            key=lambda provider: (provider.priority, provider.name),
            reverse=True,
        )
        priorities = {
            provider.name: PRIORITY_STEP - (index * PRIORITY_STEP)
            for index, provider in enumerate(ordered)
        }
        providers = [
            provider.model_copy(update={"priority": priorities[provider.name]})
            for provider in self.providers
        ]
        return self.model_copy(update={"providers": providers})


def load_proxy_config(path: str | Path) -> ProxyConfig:
    config_path = Path(path)
    try:
        raw_content = config_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ConfigError(f"config file not found: {config_path}") from exc

    data = yaml.safe_load(raw_content) or {}
    if not isinstance(data, dict):
        raise ConfigError("config file must contain a top-level mapping")

    try:
        return ProxyConfig.model_validate(data)
    except Exception as exc:  # pragma: no cover
        raise ConfigError(f"invalid config: {exc}") from exc


def dump_proxy_config(config: ProxyConfig) -> str:
    data = config.model_dump(mode="python", exclude_none=True)
    return yaml.safe_dump(
        data,
        sort_keys=False,
        allow_unicode=False,
        default_flow_style=False,
    )


def dump_example_config() -> dict[str, Any]:
    return {
        "listen": {"host": "127.0.0.1", "port": 9000},
        "retry_policy": {
            "retryable_status_codes": list(DEFAULT_RETRYABLE_STATUS_CODES),
            "same_provider_retry_count": 0,
            "retry_interval_ms": 0,
        },
        "providers": [
            {
                "name": "relay_a",
                "base_url": "https://relay-a.example.com/v1",
                "api_key": "env:RELAY_A_API_KEY",
                "enabled": True,
                "priority": 10,
                "models": ["gpt-4.1", "gpt-4o-mini"],
                "timeout_seconds": 60,
                "max_failures": 3,
                "cooldown_seconds": 30,
            },
            {
                "name": "relay_b",
                "base_url": "https://relay-b.example.com/v1",
                "api_key": "env:RELAY_B_API_KEY",
                "enabled": True,
                "priority": 20,
                "models": ["*"],
                "healthcheck_model": "gpt-4o-mini",
                "timeout_seconds": 60,
                "max_failures": 3,
                "cooldown_seconds": 30,
            },
        ],
    }
