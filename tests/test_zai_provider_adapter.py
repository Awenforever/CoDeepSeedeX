from __future__ import annotations

from codexchange_proxy.providers import ZaiProviderAdapter, canonical_provider_id, get_provider_adapter, provider_registry_status


def test_zai_native_adapters_are_registered() -> None:
    status = provider_registry_status()

    assert "zai" in status["supported_provider_ids"]
    assert "zai_coding" in status["supported_provider_ids"]
    assert status["aliases"]["zai"] == "zai"
    assert status["aliases"]["z.ai"] == "zai"
    assert status["aliases"]["glm"] == "zai"
    assert status["aliases"]["zai-coding"] == "zai_coding"
    assert status["aliases"]["z.ai-coding"] == "zai_coding"

    assert canonical_provider_id("zai") == "zai"
    assert canonical_provider_id("z.ai") == "zai"
    assert canonical_provider_id("glm") == "zai"
    assert canonical_provider_id("zai-coding") == "zai_coding"
    assert canonical_provider_id("z.ai-coding") == "zai_coding"


def test_zai_general_adapter_status_metadata() -> None:
    adapter = get_provider_adapter("zai")

    assert isinstance(adapter, ZaiProviderAdapter)
    assert adapter.provider_id == "zai"
    assert adapter.family == "zai"
    assert adapter.default_base_url == "https://api.z.ai/api/paas/v4"

    status = adapter.status_capabilities()
    assert status["provider_id"] == "zai"
    assert status["family"] == "zai"
    assert status["default_model"] == "glm-5.1"
    assert status["plan"] == "international general"
    assert status["endpoint_scope"] == "Z.AI Token API"
    assert "HTTP 429" in " ".join(status["capabilities"]["notes"])

    validation = adapter.validation_request()
    assert validation.path == "/models"
    assert validation.validation_method == "zai_openai_compatible_models"


def test_zai_coding_adapter_status_metadata() -> None:
    adapter = get_provider_adapter("zai-coding")

    assert isinstance(adapter, ZaiProviderAdapter)
    assert adapter.provider_id == "zai_coding"
    assert adapter.family == "zai"
    assert adapter.default_base_url == "https://api.z.ai/api/coding/paas/v4"

    status = adapter.status_capabilities()
    assert status["provider_id"] == "zai_coding"
    assert status["family"] == "zai"
    assert status["default_model"] == "glm-4.7"
    assert status["plan"] == "international Coding Plan"
    assert status["endpoint_scope"] == "Z.AI Coding Plan"

    validation = adapter.validation_request()
    assert validation.path == "/models"
    assert validation.validation_method == "zai_openai_compatible_models"
