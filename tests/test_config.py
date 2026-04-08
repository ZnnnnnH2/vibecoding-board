from __future__ import annotations

import pytest

from vibecoding_board.config import ProxyConfig


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
