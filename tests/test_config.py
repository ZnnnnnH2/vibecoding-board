from __future__ import annotations

import pytest

from vibecoding_board.config import ProxyConfig, dump_proxy_config


def test_provider_priorities_are_normalized_from_ten_descending() -> None:
    config = ProxyConfig.model_validate(
        {
            "listen": {"host": "127.0.0.1", "port": 9000},
            "providers": [
                {
                    "name": "relay_b",
                    "base_url": "https://relay-b.example.com/v1",
                    "api_key": "key-b",
                    "enabled": True,
                    "priority": 20,
                    "models": ["gpt-4.1"],
                    "timeout_seconds": 10,
                    "max_failures": 2,
                    "cooldown_seconds": 30,
                },
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
                    "name": "relay_c",
                    "base_url": "https://relay-c.example.com/v1",
                    "api_key": "key-c",
                    "enabled": True,
                    "priority": 30,
                    "models": ["gpt-4.1"],
                    "timeout_seconds": 10,
                    "max_failures": 2,
                    "cooldown_seconds": 30,
                },
            ],
        }
    )

    normalized = config.normalized()

    assert [provider.priority for provider in normalized.providers] == [0, -10, 10]
    assert normalized.primary_provider_name() == "relay_a"


def test_retry_policy_status_codes_are_normalized() -> None:
    config = ProxyConfig.model_validate(
        {
            "listen": {"host": "127.0.0.1", "port": 9000},
            "retry_policy": {
                "retryable_status_codes": [503, 500, 503, 429],
                "same_provider_retry_count": 2,
                "retry_interval_ms": 300,
            },
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

    assert config.retry_policy.retryable_status_codes == [429, 500, 503]


def test_retry_policy_rejects_invalid_status_code() -> None:
    with pytest.raises(ValueError, match="retryable_status_codes"):
        ProxyConfig.model_validate(
            {
                "listen": {"host": "127.0.0.1", "port": 9000},
                "retry_policy": {
                    "retryable_status_codes": [200, 503],
                    "same_provider_retry_count": 1,
                    "retry_interval_ms": 100,
                },
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


def test_provider_always_alive_defaults_false_and_round_trips_when_enabled() -> None:
    default_config = ProxyConfig.model_validate(
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
    enabled_config = ProxyConfig.model_validate(
        {
            "listen": {"host": "127.0.0.1", "port": 9000},
            "providers": [
                {
                    "name": "relay_a",
                    "base_url": "https://relay-a.example.com/v1",
                    "api_key": "key-a",
                    "enabled": True,
                    "always_alive": True,
                    "priority": 10,
                    "models": ["gpt-4.1"],
                    "timeout_seconds": 10,
                    "max_failures": 2,
                    "cooldown_seconds": 30,
                }
            ],
        }
    )

    assert default_config.providers[0].always_alive is False
    assert enabled_config.providers[0].always_alive is True
    assert "always_alive: true" in dump_proxy_config(enabled_config)
