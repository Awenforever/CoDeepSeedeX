from __future__ import annotations

from codexchange_proxy.providers import ZhipuProviderAdapter, canonical_provider_id, get_provider_adapter, provider_registry_status


def test_zhipu_native_adapters_are_registered() -> None:
    status = provider_registry_status()

    assert "zhipu" in status["supported_provider_ids"]
    assert "zhipu_coding" in status["supported_provider_ids"]
    assert status["aliases"]["zhipu"] == "zhipu"
    assert status["aliases"]["zhipu-coding"] == "zhipu_coding"
    assert status["aliases"]["bigmodel"] == "zhipu"
    assert status["aliases"]["bigmodel-coding"] == "zhipu_coding"

    assert canonical_provider_id("zhipu") == "zhipu"
    assert canonical_provider_id("zhipu-coding") == "zhipu_coding"
    assert canonical_provider_id("bigmodel") == "zhipu"
    assert canonical_provider_id("bigmodel-coding") == "zhipu_coding"


def test_zhipu_general_adapter_status_metadata() -> None:
    adapter = get_provider_adapter("zhipu")

    assert isinstance(adapter, ZhipuProviderAdapter)
    assert adapter.provider_id == "zhipu"
    assert adapter.family == "zhipu"
    assert adapter.default_base_url == "https://open.bigmodel.cn/api/paas/v4"

    status = adapter.status_capabilities()
    assert status["provider_id"] == "zhipu"
    assert status["family"] == "zhipu"
    assert status["default_model"] == "glm-5.1"
    assert status["plan"] == "domestic general"
    assert status["endpoint_scope"] == "BigModel Token API"

    validation = adapter.validation_request()
    assert validation.path == "/models"
    assert validation.validation_method == "zhipu_openai_compatible_models"


def test_zhipu_coding_adapter_status_metadata() -> None:
    adapter = get_provider_adapter("zhipu-coding")

    assert isinstance(adapter, ZhipuProviderAdapter)
    assert adapter.provider_id == "zhipu_coding"
    assert adapter.family == "zhipu"
    assert adapter.default_base_url == "https://open.bigmodel.cn/api/coding/paas/v4"

    status = adapter.status_capabilities()
    assert status["provider_id"] == "zhipu_coding"
    assert status["family"] == "zhipu"
    assert status["default_model"] == "glm-5.1"
    assert status["plan"] == "domestic Coding Plan"
    assert status["endpoint_scope"] == "BigModel Coding Plan"

    validation = adapter.validation_request()
    assert validation.path == "/models"
    assert validation.validation_method == "zhipu_openai_compatible_models"
