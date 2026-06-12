from __future__ import annotations

from codexchange_proxy.providers import QwenProviderAdapter, get_provider_adapter, provider_registry_status


def test_qwen_region_adapters_are_registered() -> None:
    status = provider_registry_status()

    assert "qwen_beijing" in status["supported_provider_ids"]
    assert "qwen_singapore" in status["supported_provider_ids"]
    assert "qwen_us" in status["supported_provider_ids"]

    assert status["aliases"]["qwen-beijing"] == "qwen_beijing"
    assert status["aliases"]["qwen-singapore"] == "qwen_singapore"
    assert status["aliases"]["qwen-us"] == "qwen_us"


def test_qwen_region_adapter_status_metadata() -> None:
    adapter = get_provider_adapter("qwen-beijing")

    assert isinstance(adapter, QwenProviderAdapter)
    assert adapter.provider_id == "qwen_beijing"
    assert adapter.family == "qwen"
    assert adapter.wire_protocol == "openai_chat_completions"

    status = adapter.status_capabilities()
    assert status["provider_id"] == "qwen_beijing"
    assert status["family"] == "qwen"
    assert status["region"] == "Beijing"
    assert status["region_code"] == "cn-beijing"
    assert status["endpoint_scope"] == "domestic DashScope"
    assert status["default_model"] == "qwen-plus"


def test_qwen_adapter_keeps_openai_compatible_payload_behavior() -> None:
    adapter = get_provider_adapter("qwen-singapore")

    payload = adapter.sanitize_chat_payload(
        {
            "model": "qwen-plus",
            "reasoning_effort": "max",
            "model_reasoning_effort": "xhigh",
            "messages": [
                {"role": "assistant", "content": "ok", "reasoning_content": "hidden"},
                {"role": "user", "content": "hello"},
            ],
        }
    )

    assert "reasoning_effort" not in payload
    assert "model_reasoning_effort" not in payload
    assert "reasoning_content" not in payload["messages"][0]


def test_qwen_validation_request_is_models_probe() -> None:
    adapter = get_provider_adapter("qwen-us")
    request = adapter.validation_request()

    assert request.method == "GET"
    assert request.path == "/models"
    assert request.validation_method == "qwen_openai_compatible_models"
