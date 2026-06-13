from __future__ import annotations

from codexchange_proxy import cli


def test_kimi_cli_config_uses_native_adapter_status() -> None:
    config = cli._model_api_provider_config("kimi")
    row = cli._model_api_provider_adapter_status_row("kimi")

    assert config["provider"] == "kimi"
    assert config["adapter_provider_id"] == "kimi"
    assert config["adapter_family"] == "kimi"
    assert config["base_url"] == "https://api.moonshot.ai/v1"
    assert config["model"] == "kimi-latest"
    assert config["validation_method"] == "kimi_openai_compatible_models"
    assert row["adapter_kind"] == "native"
    assert row["adapter_provider_id"] == "kimi"
    assert row["adapter_family"] == "kimi"


def test_moonshot_cli_alias_uses_native_adapter_status() -> None:
    config = cli._model_api_provider_config("moonshot")
    row = cli._model_api_provider_adapter_status_row("moonshot")

    assert config["provider"] == "kimi"
    assert config["adapter_provider_id"] == "kimi"
    assert config["adapter_family"] == "kimi"
    assert config["validation_method"] == "kimi_openai_compatible_models"
    assert row["adapter_kind"] == "native"
    assert row["adapter_provider_id"] == "kimi"
    assert row["adapter_family"] == "kimi"


def test_provider_adapter_matrix_marks_kimi_as_native() -> None:
    rows = {row["provider"]: row for row in cli._model_api_provider_adapter_matrix()}
    summary = cli._model_api_provider_adapter_matrix_summary()

    assert rows["kimi"]["adapter_kind"] == "native"
    assert rows["kimi"]["adapter_provider_id"] == "kimi"
    assert rows["kimi"]["adapter_family"] == "kimi"

    assert summary["providers_total"] == 10
    assert summary["native_count"] == 9
    assert summary["generic_count"] == 1
    assert summary["native_providers"] == [
        "deepseek",
        "kimi",
        "zhipu",
        "zhipu-coding",
        "zai",
        "zai-coding",
        "qwen-beijing",
        "qwen-singapore",
        "qwen-us",
    ]
    assert summary["generic_providers"] == ["custom"]


def test_adapter_matrix_display_marks_kimi_as_native() -> None:
    display = cli._model_api_provider_adapter_matrix_display()

    assert "kimi            native  kimi               kimi" in display
    assert "custom          generic openai_compatible  openai_compatible" in display


def test_moonshot_hyphen_alias_uses_native_adapter_status() -> None:
    config = cli._model_api_provider_config("moonshot-ai")
    row = cli._model_api_provider_adapter_status_row("moonshot-ai")

    assert config["provider"] == "kimi"
    assert config["adapter_provider_id"] == "kimi"
    assert config["adapter_family"] == "kimi"
    assert config["validation_method"] == "kimi_openai_compatible_models"
    assert row["adapter_kind"] == "native"
    assert row["adapter_provider_id"] == "kimi"
    assert row["adapter_family"] == "kimi"
