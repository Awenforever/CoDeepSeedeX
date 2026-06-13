from __future__ import annotations

from codexchange_proxy.providers import KimiProviderAdapter, canonical_provider_id, get_provider_adapter, provider_registry_status


def test_kimi_native_adapter_is_registered() -> None:
    status = provider_registry_status()

    assert "kimi" in status["supported_provider_ids"]
    assert status["aliases"]["kimi"] == "kimi"
    assert status["aliases"]["moonshot"] == "kimi"
    assert status["aliases"]["moonshot-ai"] == "kimi"
    assert status["aliases"]["moonshot_ai"] == "kimi"

    assert canonical_provider_id("kimi") == "kimi"
    assert canonical_provider_id("moonshot") == "kimi"
    assert canonical_provider_id("moonshot-ai") == "kimi"


def test_kimi_adapter_status_metadata() -> None:
    adapter = get_provider_adapter("kimi")

    assert isinstance(adapter, KimiProviderAdapter)
    assert adapter.provider_id == "kimi"
    assert adapter.family == "kimi"
    assert adapter.default_base_url == "https://api.moonshot.ai/v1"

    status = adapter.status_capabilities()
    assert status["provider_id"] == "kimi"
    assert status["family"] == "kimi"
    assert status["default_model"] == "kimi-latest"
    assert status["endpoint_scope"] == "Moonshot OpenAI-compatible API"
    assert "HTTP 401" in " ".join(status["capabilities"]["notes"])

    validation = adapter.validation_request()
    assert validation.path == "/models"
    assert validation.validation_method == "kimi_openai_compatible_models"


def test_moonshot_alias_uses_kimi_adapter() -> None:
    adapter = get_provider_adapter("moonshot")

    assert isinstance(adapter, KimiProviderAdapter)
    assert adapter.provider_id == "kimi"
    assert adapter.family == "kimi"
