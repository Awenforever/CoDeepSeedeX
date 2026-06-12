from __future__ import annotations

import importlib

import pytest

cli = importlib.import_module("codexchange_proxy.cli")


def test_model_api_provider_config_uses_adapter_validation_for_deepseek() -> None:
    config = cli._model_api_provider_config("deepseek")

    assert config["provider"] == "deepseek"
    assert config["adapter_provider_id"] == "deepseek"
    assert config["adapter_family"] == "deepseek"
    assert config["wire_protocol"] == "openai_chat_completions"
    assert config["validation_method"] == "account_balance_probe"
    assert config["validation_path"] == "/user/balance"
    assert config["validation_http_method"] == "GET"
    assert config["adapter_capabilities"]["reasoning"] is True
    assert config["adapter_capabilities"]["account_balance"] is True


@pytest.mark.parametrize(
    "provider",
    ["custom", "kimi", "moonshot", "zhipu", "bigmodel", "zhipu-coding", "zai", "zai-coding", "qwen", "dashscope", "qwen-beijing", "qwen-singapore", "qwen-us"],
)
def test_model_api_provider_config_uses_openai_compatible_adapter_for_generic_routes(provider: str) -> None:
    config = cli._model_api_provider_config(provider)

    assert config["adapter_provider_id"] == "openai_compatible"
    assert config["adapter_family"] == "openai_compatible"
    assert config["wire_protocol"] == "openai_chat_completions"
    assert config["validation_method"] == "openai_compatible_models"
    assert config["validation_path"] == "/models"
    assert config["validation_http_method"] == "GET"
    assert config["adapter_capabilities"]["account_balance"] is False


def test_model_api_provider_validation_contract_is_adapter_backed() -> None:
    deepseek = cli._model_api_provider_validation_contract("deepseek")
    qwen = cli._model_api_provider_validation_contract("qwen")

    assert deepseek["adapter_provider_id"] == "deepseek"
    assert deepseek["validation_method"] == "account_balance_probe"
    assert deepseek["validation_path"] == "/user/balance"

    assert qwen["adapter_provider_id"] == "openai_compatible"
    assert qwen["validation_method"] == "openai_compatible_models"
    assert qwen["validation_path"] == "/models"


def test_unknown_model_api_provider_still_fails_closed() -> None:
    with pytest.raises(ValueError, match="unsupported_model_api_provider"):
        cli._model_api_provider_config("not-a-real-provider")


def test_xai_and_grok_aliases_exist_at_adapter_registry_level_only() -> None:
    from codexchange_proxy.providers import canonical_provider_id

    assert canonical_provider_id("xai") == "openai_compatible"
    assert canonical_provider_id("grok") == "openai_compatible"

    with pytest.raises(ValueError, match="unsupported_model_api_provider"):
        cli._model_api_provider_config("xai")
    with pytest.raises(ValueError, match="unsupported_model_api_provider"):
        cli._model_api_provider_config("grok")
