from __future__ import annotations

import importlib
import inspect

proxy_app = importlib.import_module("codexchange_proxy.app")


def test_provider_neutral_reasoning_wrapper_preserves_deepseek_behavior() -> None:
    assert proxy_app._normalize_provider_reasoning_effort("deepseek", "xhigh") == "max"
    assert proxy_app._normalize_provider_reasoning_effort("deepseek", "high") == "high"
    assert proxy_app._normalize_provider_reasoning_effort("deepseek", "minimal") is None
    assert proxy_app._normalize_provider_reasoning_effort("deepseek", "xhigh") == proxy_app._normalize_deepseek_reasoning_effort("xhigh")


def test_provider_neutral_usage_wrapper_preserves_deepseek_behavior() -> None:
    payload = {
        "usage": {
            "prompt_tokens": 11,
            "completion_tokens": 7,
            "total_tokens": 18,
            "prompt_cache_hit_tokens": 3,
            "prompt_cache_miss_tokens": 8,
            "reasoning_tokens": 4,
        }
    }
    assert proxy_app._extract_provider_usage_numbers("deepseek", payload) == proxy_app._extract_usage_numbers(payload)


def test_provider_neutral_usage_wrapper_preserves_legacy_cache_fields() -> None:
    payload = {
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 2,
            "total_tokens": 12,
            "cached_tokens": 3,
            "reasoning_tokens": 5,
        }
    }

    usage = proxy_app._extract_provider_usage_numbers("deepseek", payload)

    assert usage == proxy_app._extract_usage_numbers(payload)
    assert usage["cached_tokens"] == 3
    assert usage["prompt_cache_hit_tokens"] == 3
    assert usage["prompt_cache_miss_tokens"] == 7
    assert usage["reasoning_tokens"] == 5


def test_provider_neutral_usage_wrapper_preserves_cache_clamping() -> None:
    payload = {
        "usage": {
            "prompt_tokens": 5,
            "completion_tokens": 1,
            "total_tokens": 6,
            "cached_tokens": 99,
            "prompt_cache_miss_tokens": 99,
        }
    }

    usage = proxy_app._extract_provider_usage_numbers("deepseek", payload)

    assert usage == proxy_app._extract_usage_numbers(payload)
    assert usage["cached_tokens"] == 5
    assert usage["prompt_cache_hit_tokens"] == 5
    assert usage["prompt_cache_miss_tokens"] == 0


def test_provider_neutral_usage_wrapper_fills_cache_miss_fallback() -> None:
    payload = {"usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7}}

    usage = proxy_app._extract_provider_usage_numbers("deepseek", payload)

    assert usage == proxy_app._extract_usage_numbers(payload)
    assert usage["cached_tokens"] == 0
    assert usage["prompt_cache_hit_tokens"] == 0
    assert usage["prompt_cache_miss_tokens"] == 5
    assert usage["reasoning_tokens"] == 0


def test_legacy_chat_compat_wrappers_delegate_to_provider_neutral_seams() -> None:
    reasoning_source = inspect.getsource(proxy_app._normalize_deepseek_reasoning_effort)
    usage_source = inspect.getsource(proxy_app._extract_usage_numbers)

    assert "_normalize_provider_reasoning_effort" in reasoning_source
    assert "_extract_provider_usage_numbers" in usage_source
    assert 'get_provider_adapter("deepseek").normalize_reasoning_effort' not in reasoning_source
    assert 'get_provider_adapter("deepseek").parse_usage' not in usage_source
