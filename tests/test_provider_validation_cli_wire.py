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
    ["custom", "kimi", "moonshot", "qwen", "dashscope"],
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

def test_model_api_provider_config_uses_qwen_native_adapters_for_concrete_regions() -> None:
    beijing = cli._model_api_provider_config("qwen-beijing")
    singapore = cli._model_api_provider_config("qwen-singapore")
    us = cli._model_api_provider_config("qwen-us")

    assert beijing["adapter_provider_id"] == "qwen_beijing"
    assert beijing["adapter_family"] == "qwen"
    assert beijing["validation_method"] == "qwen_openai_compatible_models"

    assert singapore["adapter_provider_id"] == "qwen_singapore"
    assert singapore["adapter_family"] == "qwen"
    assert singapore["validation_method"] == "qwen_openai_compatible_models"

    assert us["adapter_provider_id"] == "qwen_us"
    assert us["adapter_family"] == "qwen"
    assert us["validation_method"] == "qwen_openai_compatible_models"


def test_zhipu_native_provider_validation_contract_is_adapter_backed() -> None:
    general = cli._model_api_provider_validation_contract("zhipu")
    coding = cli._model_api_provider_validation_contract("zhipu-coding")

    assert general["adapter_provider_id"] == "zhipu"
    assert general["adapter_family"] == "zhipu"
    assert general["validation_method"] == "zhipu_openai_compatible_models"
    assert coding["adapter_provider_id"] == "zhipu_coding"
    assert coding["adapter_family"] == "zhipu"
    assert coding["validation_method"] == "zhipu_openai_compatible_models"


def test_zai_native_provider_validation_contract_is_adapter_backed() -> None:
    general = cli._model_api_provider_validation_contract("zai")
    coding = cli._model_api_provider_validation_contract("zai-coding")

    assert general["adapter_provider_id"] == "zai"
    assert general["adapter_family"] == "zai"
    assert general["validation_method"] == "zai_openai_compatible_models"
    assert coding["adapter_provider_id"] == "zai_coding"
    assert coding["adapter_family"] == "zai"
    assert coding["validation_method"] == "zai_openai_compatible_models"
