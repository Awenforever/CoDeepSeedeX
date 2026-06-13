from __future__ import annotations

from codexchange_proxy import cli


def test_zai_cli_config_uses_native_adapter_status() -> None:
    config = cli._model_api_provider_config("zai")
    row = cli._model_api_provider_adapter_status_row("zai")

    assert config["provider"] == "zai"
    assert config["adapter_provider_id"] == "zai"
    assert config["adapter_family"] == "zai"
    assert config["base_url"] == "https://api.z.ai/api/paas/v4"
    assert config["model"] == "glm-5.1"
    assert config["validation_method"] == "zai_openai_compatible_models"
    assert row["adapter_kind"] == "native"
    assert row["adapter_provider_id"] == "zai"
    assert row["adapter_family"] == "zai"


def test_zai_coding_cli_config_uses_native_adapter_status() -> None:
    config = cli._model_api_provider_config("zai-coding")
    row = cli._model_api_provider_adapter_status_row("zai-coding")

    assert config["provider"] == "zai_coding"
    assert config["adapter_provider_id"] == "zai_coding"
    assert config["adapter_family"] == "zai"
    assert config["base_url"] == "https://api.z.ai/api/coding/paas/v4"
    assert config["model"] == "glm-4.7"
    assert config["validation_method"] == "zai_openai_compatible_models"
    assert row["adapter_kind"] == "native"
    assert row["adapter_provider_id"] == "zai_coding"
    assert row["adapter_family"] == "zai"


def test_zai_adapter_aliases_are_native_for_registry_and_cli() -> None:
    aliases = {
        "z.ai": "zai",
        "glm": "zai",
        "zai-coding": "zai_coding",
        "z.ai-coding": "zai_coding",
    }

    for alias, adapter_id in aliases.items():
        config = cli._model_api_provider_config(alias)
        row = cli._model_api_provider_adapter_status_row(alias)
        assert config["adapter_provider_id"] == adapter_id
        assert config["adapter_family"] == "zai"
        assert row["adapter_kind"] == "native"


def test_provider_adapter_matrix_marks_zai_as_native() -> None:
    rows = {row["provider"]: row for row in cli._model_api_provider_adapter_matrix()}
    summary = cli._model_api_provider_adapter_matrix_summary()

    assert rows["zai"]["adapter_kind"] == "native"
    assert rows["zai"]["adapter_provider_id"] == "zai"
    assert rows["zai"]["adapter_family"] == "zai"

    assert rows["zai-coding"]["adapter_kind"] == "native"
    assert rows["zai-coding"]["adapter_provider_id"] == "zai_coding"
    assert rows["zai-coding"]["adapter_family"] == "zai"

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


def test_adapter_matrix_display_marks_zai_as_native() -> None:
    display = cli._model_api_provider_adapter_matrix_display()

    assert "zai             native  zai                zai" in display
    assert "zai-coding      native  zai                zai_coding" in display
    assert "kimi            native  kimi               kimi" in display
    assert "custom          generic openai_compatible  openai_compatible" in display
