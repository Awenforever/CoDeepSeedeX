from __future__ import annotations

from codexchange_proxy import cli


def test_zhipu_cli_config_uses_native_adapter_status() -> None:
    config = cli._model_api_provider_config("zhipu")
    row = cli._model_api_provider_adapter_status_row("zhipu")

    assert config["provider"] == "zhipu"
    assert config["adapter_provider_id"] == "zhipu"
    assert config["adapter_family"] == "zhipu"
    assert config["validation_method"] == "zhipu_openai_compatible_models"
    assert row["adapter_kind"] == "native"
    assert row["adapter_provider_id"] == "zhipu"
    assert row["adapter_family"] == "zhipu"


def test_zhipu_coding_cli_config_uses_native_adapter_status() -> None:
    config = cli._model_api_provider_config("zhipu-coding")
    row = cli._model_api_provider_adapter_status_row("zhipu-coding")

    assert config["provider"] == "zhipu_coding"
    assert config["adapter_provider_id"] == "zhipu_coding"
    assert config["adapter_family"] == "zhipu"
    assert config["base_url"] == "https://open.bigmodel.cn/api/coding/paas/v4"
    assert config["validation_method"] == "zhipu_openai_compatible_models"
    assert row["adapter_kind"] == "native"
    assert row["adapter_provider_id"] == "zhipu_coding"
    assert row["adapter_family"] == "zhipu"


def test_provider_adapter_matrix_marks_zhipu_as_native() -> None:
    rows = {row["provider"]: row for row in cli._model_api_provider_adapter_matrix()}
    summary = cli._model_api_provider_adapter_matrix_summary()

    assert rows["zhipu"]["adapter_kind"] == "native"
    assert rows["zhipu"]["adapter_provider_id"] == "zhipu"
    assert rows["zhipu"]["adapter_family"] == "zhipu"

    assert rows["zhipu-coding"]["adapter_kind"] == "native"
    assert rows["zhipu-coding"]["adapter_provider_id"] == "zhipu_coding"
    assert rows["zhipu-coding"]["adapter_family"] == "zhipu"

    assert summary["providers_total"] == 10
    assert summary["native_count"] == 8
    assert summary["generic_count"] == 2
    assert summary["native_providers"] == [
        "deepseek",
        "zhipu",
        "zhipu-coding",
        "zai",
        "zai-coding",
        "qwen-beijing",
        "qwen-singapore",
        "qwen-us",
    ]
    assert summary["generic_providers"] == [
        "kimi",
        "custom",
    ]


def test_adapter_matrix_display_marks_zhipu_as_native() -> None:
    display = cli._model_api_provider_adapter_matrix_display()

    assert "zhipu           native  zhipu              zhipu" in display
    assert "zhipu-coding    native  zhipu              zhipu_coding" in display
    assert "kimi            generic openai_compatible  openai_compatible" in display
    assert "zai             native  zai                zai" in display
