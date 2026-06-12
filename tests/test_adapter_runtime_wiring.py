from __future__ import annotations

from typing import Any, Mapping
import importlib

proxy_app = importlib.import_module("codexchange_proxy.app")
from codexchange_proxy.providers import DeepSeekProviderAdapter, OpenAICompatibleProviderAdapter, ProviderCapabilities


class FakeRuntimeAdapter:
    provider_id = "fake"
    family = "openai_compatible"
    wire_protocol = "openai_chat_completions"
    default_base_url = "https://example.invalid/v1"
    api_key_env_names = ("COX_MODEL_API_KEY",)
    capabilities = ProviderCapabilities(reasoning=True, response_reasoning_field="reasoning_content")

    def __init__(self) -> None:
        self.parse_usage_calls: list[Mapping[str, Any]] = []
        self.sanitize_calls: list[Mapping[str, Any]] = []
        self.reasoning_text_calls: list[Mapping[str, Any]] = []

    def normalize_reasoning_effort(self, value: object) -> str | None:
        return "adapter-normalized"

    def parse_usage(self, upstream_payload: Mapping[str, Any]) -> dict[str, int]:
        self.parse_usage_calls.append(upstream_payload)
        return {
            "prompt_tokens": 7,
            "completion_tokens": 3,
            "total_tokens": 10,
            "cached_tokens": 2,
            "prompt_cache_hit_tokens": 2,
            "prompt_cache_miss_tokens": 5,
            "reasoning_tokens": 1,
        }

    def sanitize_chat_payload(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        self.sanitize_calls.append(payload)
        cleaned = dict(payload)
        cleaned["adapter_seen"] = True
        return cleaned

    def message_reasoning_text(self, message: Mapping[str, Any]) -> str:
        self.reasoning_text_calls.append(message)
        return "adapter reasoning"


def test_legacy_reasoning_effort_wrapper_uses_deepseek_adapter() -> None:
    assert proxy_app._normalize_deepseek_reasoning_effort("xhigh") == "max"
    assert proxy_app._normalize_deepseek_reasoning_effort("minimal") is None


def test_usage_number_wrapper_uses_provider_adapter(monkeypatch) -> None:
    fake = FakeRuntimeAdapter()
    monkeypatch.setattr(proxy_app, "get_provider_adapter", lambda provider=None: fake)

    usage = proxy_app._extract_usage_numbers({"usage": {"prompt_tokens": 999}})

    assert fake.parse_usage_calls
    assert usage == {
        "prompt_tokens": 7,
        "completion_tokens": 3,
        "total_tokens": 10,
        "cached_tokens": 2,
        "prompt_cache_hit_tokens": 2,
        "prompt_cache_miss_tokens": 5,
        "reasoning_tokens": 1,
    }


def test_message_reasoning_text_wrapper_uses_provider_adapter(monkeypatch) -> None:
    fake = FakeRuntimeAdapter()
    monkeypatch.setattr(proxy_app, "get_provider_adapter", lambda provider=None: fake)

    assert proxy_app._deepseek_message_reasoning_text({"reasoning_content": "old"}) == "adapter reasoning"
    assert fake.reasoning_text_calls


def test_chat_payload_sanitizer_invokes_configured_adapter(monkeypatch) -> None:
    fake = FakeRuntimeAdapter()
    monkeypatch.setattr(proxy_app, "get_provider_adapter", lambda provider=None: fake)
    monkeypatch.setattr(proxy_app, "_configured_model_provider", lambda: "fake")
    monkeypatch.setenv("COX_CHAT_COMPAT_MODE", "deepseek")

    payload = proxy_app._sanitize_chat_payload_for_upstream(
        {"model": "m", "messages": [{"role": "user", "content": "hi"}], "stream": False}
    )

    assert fake.sanitize_calls
    assert payload["model"] == "m"


def test_deepseek_adapter_usage_contract_includes_cache_miss_tokens() -> None:
    payload = {
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 2,
            "total_tokens": 12,
            "prompt_tokens_details": {"cached_tokens": 4},
            "completion_tokens_details": {"reasoning_tokens": 1},
        }
    }
    usage = DeepSeekProviderAdapter().parse_usage(payload)

    assert usage["cached_tokens"] == 4
    assert usage["prompt_cache_hit_tokens"] == 4
    assert usage["prompt_cache_miss_tokens"] == 6
    assert usage["reasoning_tokens"] == 1


def test_openai_compatible_adapter_usage_contract_includes_cache_miss_tokens() -> None:
    payload = {"usage": {"prompt_tokens": 9, "completion_tokens": 1, "prompt_tokens_details": {"cached_tokens": 3}}}
    usage = OpenAICompatibleProviderAdapter().parse_usage(payload)

    assert usage["total_tokens"] == 10
    assert usage["cached_tokens"] == 3
    assert usage["prompt_cache_hit_tokens"] == 3
    assert usage["prompt_cache_miss_tokens"] == 6


def test_deepseek_adapter_preserves_reasoning_content_for_request_history() -> None:
    adapter = DeepSeekProviderAdapter()
    payload = adapter.sanitize_chat_payload(
        {"messages": [{"role": "assistant", "content": "ok", "reasoning_content": "kept"}]}
    )

    assert payload["messages"][0]["reasoning_content"] == "kept"
