from __future__ import annotations

import re
from pathlib import Path

import codexchange_proxy.cli as cli


ROOT = Path(__file__).resolve().parents[1]


def _readme_text() -> str:
    return "\n".join(
        [
            (ROOT / "README.md").read_text(encoding="utf-8"),
            (ROOT / "README.zh-CN.md").read_text(encoding="utf-8"),
            "cox doctor providers",
        "cox doctor providers --kind web-search --provider serpapi --live --allow-spend",
        "cox doctor providers --kind image --provider zhipu --live --allow-spend",
    ]
    )


def _cox_config_commands(text: str) -> list[str]:
    commands: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("cox config "):
            commands.append(stripped)
    return commands


def test_readme_custom_skip_validation_example_is_complete() -> None:
    text = _readme_text()
    commands = re.findall(r"cox config set-model provider-model-name --provider custom[^\n]*--skip-validation", text)
    assert commands
    for command in commands:
        assert "--base-url" in command
        assert "--model" not in command


def test_readme_explains_api_key_input_forms() -> None:
    text = _readme_text()
    assert "hidden prompt" in text
    assert "隐藏输入提示处" in text
    assert "--value sk-fake-deepseek-api-key" in text
    assert "--value fake-serpapi-api-key" in text
    assert "--value fake-zhipu-api-key" in text
    assert "not as a positional argument" in text
    assert "不是放在命令末尾当位置参数" in text
    assert "<deepseek-api-paste here>" not in text


def test_readme_critical_config_commands_match_cli_parser() -> None:
    text = _readme_text()
    commands = _cox_config_commands(text)

    assert "cox config wizard" in commands
    assert "cox config set-model --provider deepseek" in commands
    assert "cox config set-model --provider zhipu" in commands
    assert "cox config set-model --provider zhipu-coding" in commands
    assert "cox config set-model --provider zai" in commands
    assert "cox config set-model --provider zai-coding" in commands
    assert "cox config set-model --provider qwen-beijing" in commands
    assert "cox config set-model --provider qwen-singapore" in commands
    assert "cox config set-model --provider qwen-us" in commands
    assert "cox config set-model --provider glm" not in commands
    assert "cox config set-model --provider qwen" not in commands
    assert "cox config set-web-search-api-key --provider serpapi" in commands
    assert "cox config set-web-search-api-key --provider brave" not in commands
    assert "cox config set-image-api-key --provider zhipu" in commands
    assert "cox config set-image-api-key --provider zai" in commands
    assert "cox config set-image-api-key --provider glm" not in commands
    assert "cox config set-model --provider deepseek --value sk-fake-deepseek-api-key" in commands
    assert "cox config set-model provider-model-name --provider custom --base-url https://api.example.com/v1 --skip-validation" in commands
    assert "cox config set-model provider-model-name --provider custom --base-url https://api.example.com/v1 --value sk-fake-custom-api-key --skip-validation" in commands

    parser = cli.build_parser()
    for command in commands:
        parts = command.split()
        assert parts[:2] == ["cox", "config"]
        args = parts[1:]
        namespace = parser.parse_args(args)
        assert getattr(namespace, "func", None) is cli._config


def test_readme_uses_set_model_for_custom_model_api_examples() -> None:
    text = _readme_text()
    assert "cox config set-api-key --provider custom" not in text
    assert "cox config set-model qwen3-coder-plus --provider custom --base-url https://coding-intl.dashscope.aliyuncs.com/v1 --skip-validation" in text
    assert "--model qwen3-coder-plus" not in text

def test_readme_model_provider_surface_uses_explicit_sites_and_plans() -> None:
    text = _readme_text()
    assert "cox config set-model --provider glm\n" not in text
    assert "cox config set-model --provider qwen\n" not in text
    assert "cox config set-model --provider zhipu-coding" in text
    assert "cox config set-model --provider zai-coding" in text
    assert "cox config set-model --provider qwen-beijing" in text
    assert "cox config set-model --provider qwen-singapore" in text
    assert "cox config set-model --provider qwen-us" in text
    assert "cox config set-web-search-api-key --provider brave" not in text


def test_readme_current_latest_release_is_not_described_as_current_prerelease_channel() -> None:
    en = (ROOT / "README.md").read_text(encoding="utf-8")
    zh = (ROOT / "README.zh-CN.md").read_text(encoding="utf-8")

    assert "Explicit pre-release channel, currently `v0.4.9-alpha`" not in en
    assert "显式pre-release通道，当前为`v0.4.9-alpha`" not in zh
    assert "Pinned current Latest Release tag (`v0.4.9-alpha`)" in en
    assert "固定当前Latest Release tag（`v0.4.9-alpha`）" in zh
    assert "If WeClaw integration is used with CodeXchange `v0.4.9-alpha`, `v0.4.0-alpha`, or `v0.3.9-alpha`" not in en
    assert "如果WeClaw联动使用CodeXchange `v0.4.9-alpha`、`v0.4.0-alpha`或`v0.3.9-alpha`" not in zh


def test_p219a15_qwen_us_remains_current_public_regional_provider() -> None:
    en = (ROOT / "README.md").read_text(encoding="utf-8")
    zh = (ROOT / "README.zh-CN.md").read_text(encoding="utf-8")
    assert "cox config set-model --provider qwen-us" in en
    assert "cox config set-model --provider qwen-us" in zh
