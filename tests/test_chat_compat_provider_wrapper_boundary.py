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

def test_provider_chat_capability_profile_preserves_deepseek_mode_contract(monkeypatch) -> None:
    monkeypatch.delenv("COX_CHAT_COMPAT_MODE", raising=False)
    monkeypatch.delenv("COX_CHAT_SUPPORTS_DEEPSEEK_EXTENSIONS", raising=False)

    profile = proxy_app._provider_chat_capability_profile("deepseek", compat_mode="deepseek")

    assert profile["provider"] == "deepseek"
    assert profile["chat_compat_mode"] == "deepseek"
    assert profile["supports_deepseek_extensions"] is True
    assert profile["allow_all_params"] is True
    assert "reasoning_effort" not in profile["drop_params"]


def test_provider_chat_capability_profile_drops_deepseek_extensions_for_custom_openai_mode(monkeypatch) -> None:
    monkeypatch.delenv("COX_CHAT_COMPAT_MODE", raising=False)
    monkeypatch.delenv("COX_CHAT_SUPPORTS_DEEPSEEK_EXTENSIONS", raising=False)

    class FakeAdapter:
        class capabilities:
            reasoning = False
            response_reasoning_field = None

    profile = proxy_app._provider_chat_capability_profile(
        "custom",
        adapter=FakeAdapter(),
        compat_mode="openai_compatible",
    )

    assert profile["provider"] == "custom"
    assert profile["chat_compat_mode"] == "openai_compatible"
    assert profile["supports_deepseek_extensions"] is False
    assert "reasoning_effort" in profile["drop_params"]
    assert "thinking" in profile["drop_params"]


def test_provider_chat_payload_sanitizer_invokes_adapter_before_capability_filter(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    class FakeAdapter:
        class capabilities:
            reasoning = False
            response_reasoning_field = None

        def sanitize_chat_payload(self, payload):
            calls.append(dict(payload))
            cleaned = dict(payload)
            cleaned["adapter_added_param"] = "drop-me"
            cleaned["reasoning_effort"] = "high"
            return cleaned

    monkeypatch.setattr(proxy_app, "_chat_profile_provider_adapter", lambda provider_id=None: FakeAdapter())

    payload = {
        "model": "custom-model",
        "messages": [],
        "temperature": 0.2,
        "reasoning_effort": "low",
    }

    cleaned = proxy_app._sanitize_provider_chat_payload_for_upstream("custom", payload)

    assert calls == [payload]
    assert cleaned["model"] == "custom-model"
    assert cleaned["messages"] == []
    assert cleaned["temperature"] == 0.2
    assert "reasoning_effort" not in cleaned
    assert "adapter_added_param" not in cleaned


def test_legacy_chat_capability_wrappers_delegate_to_provider_neutral_seams() -> None:
    compat_source = inspect.getsource(proxy_app._chat_payload_compat_mode)
    extension_source = inspect.getsource(proxy_app._chat_payload_supports_deepseek_extensions)
    profile_source = inspect.getsource(proxy_app._chat_capability_profile)
    sanitize_source = inspect.getsource(proxy_app._sanitize_chat_payload_for_upstream)

    assert "return _provider_chat_payload_compat_mode(" in compat_source
    assert "return _provider_chat_payload_supports_deepseek_extensions(" in extension_source
    assert "return _provider_chat_capability_profile(" in profile_source
    assert "return _sanitize_provider_chat_payload_for_upstream(" in sanitize_source
