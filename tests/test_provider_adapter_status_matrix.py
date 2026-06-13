from __future__ import annotations

from codexchange_proxy import cli


def test_model_api_provider_adapter_matrix_marks_native_and_generic_providers() -> None:
    matrix = cli._model_api_provider_adapter_matrix()
    rows = {row["provider"]: row for row in matrix}

    assert rows["deepseek"]["adapter_kind"] == "native"
    assert rows["deepseek"]["adapter_provider_id"] == "deepseek"
    assert rows["deepseek"]["adapter_family"] == "deepseek"

    assert rows["qwen-beijing"]["adapter_kind"] == "native"
    assert rows["qwen-beijing"]["adapter_provider_id"] == "qwen_beijing"
    assert rows["qwen-beijing"]["adapter_family"] == "qwen"

    assert rows["qwen-singapore"]["adapter_kind"] == "native"
    assert rows["qwen-singapore"]["adapter_provider_id"] == "qwen_singapore"
    assert rows["qwen-singapore"]["adapter_family"] == "qwen"

    assert rows["qwen-us"]["adapter_kind"] == "native"
    assert rows["qwen-us"]["adapter_provider_id"] == "qwen_us"
    assert rows["qwen-us"]["adapter_family"] == "qwen"

    for provider in ("kimi", "zai", "zai-coding", "custom"):
        assert rows[provider]["adapter_kind"] == "generic"
        assert rows[provider]["adapter_provider_id"] == "openai_compatible"
        assert rows[provider]["adapter_family"] == "openai_compatible"


def test_model_api_provider_adapter_matrix_summary_is_stable() -> None:
    summary = cli._model_api_provider_adapter_matrix_summary()

    assert summary["providers_total"] == 10
    assert summary["native_count"] == 6
    assert summary["generic_count"] == 4
    assert summary["native_providers"] == [
        "deepseek",
        "zhipu",
        "zhipu-coding",
        "qwen-beijing",
        "qwen-singapore",
        "qwen-us",
    ]
    assert summary["generic_providers"] == [
        "kimi",
        "zai",
        "zai-coding",
        "custom",
    ]


def test_model_api_config_status_exposes_current_adapter_and_matrix() -> None:
    status = cli._model_api_config_status(
        values={
            "COX_MODEL_PROVIDER": "qwen_beijing",
            "COX_MODEL": "qwen-plus",
            "COX_MODEL_API_BASE_URL": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "COX_MODEL_API_KEY": "sk-test",
        }
    )

    assert status["provider"] == "qwen_beijing"
    assert status["adapter_kind"] == "native"
    assert status["adapter_is_native"] is True
    assert status["adapter_is_generic"] is False
    assert status["adapter_status"]["adapter_provider_id"] == "qwen_beijing"
    assert status["adapter_status"]["adapter_family"] == "qwen"

    matrix = {row["provider"]: row for row in status["adapter_matrix"]}
    assert matrix["qwen-beijing"]["adapter_kind"] == "native"
    assert matrix["kimi"]["adapter_kind"] == "generic"
    assert status["adapter_matrix_summary"]["native_count"] == 6
    assert status["adapter_matrix_summary"]["generic_count"] == 4


def test_ambiguous_qwen_aliases_remain_generic_in_matrix_helpers() -> None:
    for provider in ("qwen", "dashscope"):
        row = cli._model_api_provider_adapter_status_row(provider)

        assert row["canonical_provider"] == "qwen_singapore"
        assert row["adapter_provider_id"] == "openai_compatible"
        assert row["adapter_family"] == "openai_compatible"
        assert row["adapter_kind"] == "generic"
        assert row["selection_warning"]
