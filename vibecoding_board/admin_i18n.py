from __future__ import annotations

import re
from typing import Literal

from fastapi import Request


AdminLocale = Literal["en", "zh-CN"]

_MESSAGES: dict[AdminLocale, dict[str, str]] = {
    "en": {
        "added_provider": "Added provider {provider}.",
        "updated_provider": "Updated provider {provider}.",
        "updated_priority": "Updated priority for {provider}.",
        "updated_retry_policy": "Updated retry policy.",
        "updated_healthcheck_settings": "Updated manual healthcheck settings.",
        "promoted_provider": "Promoted provider {provider}.",
        "toggled_provider": "Toggled provider {provider}.",
        "healthcheck_passed": "Health check passed for {provider}.",
        "healthcheck_failed": "Health check failed for {provider}.",
        "deleted_provider": "Deleted provider {provider}.",
        "provider_not_found": "Provider {provider!r} does not exist.",
        "at_least_one_provider": "At least one provider must remain configured.",
        "runtime_not_initialized": "Runtime is not initialized.",
        "healthcheck_model_required": "Provider {provider!r} needs 'healthcheck_model' because it is configured with wildcard models.",
        "name_empty": "Name must not be empty.",
        "base_url_empty": "Base URL must not be empty.",
        "api_key_empty": "API key must not be empty.",
        "models_empty": "Models must contain at least one entry.",
        "provider_names_unique": "Provider names must be unique.",
    },
    "zh-CN": {
        "added_provider": "已添加 Provider {provider}。",
        "updated_provider": "已更新 Provider {provider}。",
        "updated_priority": "已更新 Provider {provider} 的优先级。",
        "updated_retry_policy": "已更新重试策略。",
        "updated_healthcheck_settings": "已更新手动健康检查设置。",
        "promoted_provider": "已将 Provider {provider} 提升为主路由。",
        "toggled_provider": "已切换 Provider {provider} 的启用状态。",
        "healthcheck_passed": "Provider {provider} 的健康检查已通过。",
        "healthcheck_failed": "Provider {provider} 的健康检查失败。",
        "deleted_provider": "已删除 Provider {provider}。",
        "provider_not_found": "Provider {provider!r} 不存在。",
        "at_least_one_provider": "至少需要保留一个已配置的 Provider。",
        "runtime_not_initialized": "运行时尚未初始化。",
        "healthcheck_model_required": "Provider {provider!r} 使用了通配模型，必须配置 'healthcheck_model'。",
        "name_empty": "名称不能为空。",
        "base_url_empty": "Base URL 不能为空。",
        "api_key_empty": "API Key 不能为空。",
        "models_empty": "模型列表至少需要一个条目。",
        "provider_names_unique": "Provider 名称必须唯一。",
    },
}

_PROVIDER_NOT_FOUND_RE = re.compile(r"^Provider '(.+)' does not exist\.$")
_HEALTHCHECK_MODEL_REQUIRED_RE = re.compile(
    r"^Provider '(.+)' needs 'healthcheck_model' because it is configured with wildcard models\.$"
)

_EXACT_MESSAGE_KEYS = {
    "At least one provider must remain configured.": "at_least_one_provider",
    "runtime is not initialized": "runtime_not_initialized",
    "name must not be empty": "name_empty",
    "base_url must not be empty": "base_url_empty",
    "api_key must not be empty": "api_key_empty",
    "models must contain at least one entry": "models_empty",
    "provider names must be unique": "provider_names_unique",
}


def resolve_admin_locale(request: Request) -> AdminLocale:
    locale_hint = (
        request.headers.get("x-admin-locale")
        or request.headers.get("accept-language")
        or "en"
    ).lower()
    if locale_hint.startswith("zh"):
        return "zh-CN"
    return "en"


def admin_message(locale: AdminLocale, key: str, **kwargs: object) -> str:
    return _MESSAGES[locale][key].format(**kwargs)


def translate_admin_error(locale: AdminLocale, message: str) -> str:
    key = _EXACT_MESSAGE_KEYS.get(message)
    if key is not None:
        return admin_message(locale, key)

    provider_match = _PROVIDER_NOT_FOUND_RE.match(message)
    if provider_match is not None:
        return admin_message(locale, "provider_not_found", provider=provider_match.group(1))

    healthcheck_match = _HEALTHCHECK_MODEL_REQUIRED_RE.match(message)
    if healthcheck_match is not None:
        return admin_message(
            locale,
            "healthcheck_model_required",
            provider=healthcheck_match.group(1),
        )

    return message
