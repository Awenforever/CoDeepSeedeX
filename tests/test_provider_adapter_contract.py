from __future__ import annotations

import pytest

from codexchange_proxy.providers import (
    DeepSeekProviderAdapter,
    OpenAICompatibleProviderAdapter,
    ProviderAdapter,
    ProviderRoute,
    canonical_provider_id,
    get_provider_adapter,
    provider_registry_status,
    supported_provider_ids,
)


def test_provider_registry_exposes_initial_adapter_contracts() -> None:
    status = provider_registry_status()
    assert status["available"] is True
    assert status["default_provider"] == "deepseek"
    assert "deepseek" in status["supported_provider_ids"]
    assert "openai_compatible" in status["supported_provider_ids"]
    assert "qwen_beijing" in status["supported_provider_ids"]
    assert "qwen_singapore" in status["supported_provider_ids"]
    assert "qwen_us" in status["supported_provider_ids"]
    assert canonical_provider_id("qwen") == "openai_compatible"
    assert canonical_provider_id("qwen-beijing") == "qwen_beijing"
    assert canonical_provider_id("qwen-singapore") == "qwen_singapore"
    assert canonical_provider_id("qwen-us") == "qwen_us"
    assert canonical_provider_id("kimi") == "openai_compatible"
    assert canonical_provider_id("zhipu") == "openai_compatible"
    assert canonical_provider_id("xai") == "openai_compatible"
    assert canonical_provider_id("grok") == "openai_compatible"


def test_provider_registry_returns_protocol_compatible_adapters() -> None:
    for provider_id in supported_provider_ids():
        adapter = get_provider_adapter(provider_id)
        assert isinstance(adapter, ProviderAdapter)
        capabilities = adapter.status_capabilities()["capabilities"]
        assert "streaming" in capabilities
        assert "tool_calls" in capabilities


def test_deepseek_adapter_normalizes_reasoning_and_preserves_provider_capabilities() -> None:
    adapter = DeepSeekProviderAdapter()
    assert adapter.normalize_reasoning_effort("xhigh") == "max"
    assert adapter.normalize_reasoning_effort("MAX") == "max"
    assert adapter.normalize_reasoning_effort("high") == "high"
    assert adapter.normalize_reasoning_effort("unknown") is None

    status = adapter.status_capabilities()
    assert status["provider_id"] == "deepseek"
    assert status["wire_protocol"] == "openai_chat_completions"
    assert status["capabilities"]["reasoning"] is True
    assert status["capabilities"]["pricing"] is True
    assert status["capabilities"]["account_balance"] is True
    assert status["capabilities"]["tokenizer"] is True


def test_deepseek_adapter_builds_chat_payload_and_preserves_reasoning_history() -> None:
    adapter = DeepSeekProviderAdapter()
    route = ProviderRoute(
        provider_id="deepseek",
        base_url="https://api.deepseek.com",
        model="deepseek-v4-flash",
        extra={"reasoning_effort": "xhigh"},
    )
    payload = adapter.build_chat_payload(
        route,
        {
            "messages": [{"role": "assistant", "content": "ok", "reasoning_content": "hidden"}],
            "stream": True,
        },
    )

    assert payload["model"] == "deepseek-v4-flash"
    assert payload["stream"] is True
    assert payload["reasoning_effort"] == "max"
    assert payload["messages"][0]["reasoning_content"] == "hidden"


def test_openai_compatible_adapter_removes_provider_specific_extensions() -> None:
    adapter = OpenAICompatibleProviderAdapter()
    route = ProviderRoute(
        provider_id="openai_compatible",
        base_url="https://example.invalid/v1",
        model="model-a",
    )
    payload = adapter.build_chat_payload(
        route,
        {
            "messages": [{"role": "assistant", "content": "ok", "reasoning_content": "hidden"}],
            "reasoning_effort": "max",
            "model_reasoning_effort": "xhigh",
            "temperature": 0.1,
        },
    )

    assert payload["model"] == "model-a"
    assert payload["temperature"] == 0.1
    assert "reasoning_effort" not in payload
    assert "model_reasoning_effort" not in payload
    assert "reasoning_content" not in payload["messages"][0]


def test_provider_adapters_parse_usage_contract() -> None:
    payload = {
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 3,
            "total_tokens": 13,
            "prompt_tokens_details": {"cached_tokens": 4},
            "completion_tokens_details": {"reasoning_tokens": 2},
        }
    }

    assert DeepSeekProviderAdapter().parse_usage(payload) == {
        "prompt_tokens": 10,
        "completion_tokens": 3,
        "total_tokens": 13,
        "cached_tokens": 4,
        "prompt_cache_hit_tokens": 4,
        "prompt_cache_miss_tokens": 6,
        "reasoning_tokens": 2,
    }
    assert OpenAICompatibleProviderAdapter().parse_usage(payload) == {
        "prompt_tokens": 10,
        "completion_tokens": 3,
        "total_tokens": 13,
        "cached_tokens": 4,
        "prompt_cache_hit_tokens": 4,
        "prompt_cache_miss_tokens": 6,
        "reasoning_tokens": 2,
    }


def test_unknown_provider_adapter_fails_closed() -> None:
    with pytest.raises(ValueError, match="unsupported_provider_adapter"):
        get_provider_adapter("not-a-real-provider")
