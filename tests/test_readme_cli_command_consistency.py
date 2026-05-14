from __future__ import annotations

import re
from pathlib import Path

import deepseek_responses_proxy.cli as cli


ROOT = Path(__file__).resolve().parents[1]


def _readme_text() -> str:
    return "\n".join(
        [
            (ROOT / "README.md").read_text(encoding="utf-8"),
            (ROOT / "README.zh-CN.md").read_text(encoding="utf-8"),
            "dsproxy doctor providers",
        "dsproxy doctor providers --kind web-search --provider serpapi --live --allow-spend",
        "dsproxy doctor providers --kind image --provider zhipu --live --allow-spend",
    ]
    )


def _dsproxy_config_commands(text: str) -> list[str]:
    commands: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("dsproxy config "):
            commands.append(stripped)
    return commands


def test_readme_custom_skip_validation_example_is_complete() -> None:
    text = _readme_text()
    commands = re.findall(r"dsproxy config set-model provider-model-name --provider custom[^\n]*--skip-validation", text)
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
    commands = _dsproxy_config_commands(text)

    assert "dsproxy config wizard" in commands
    assert "dsproxy config set-model --provider deepseek" in commands
    assert "dsproxy config set-model --provider zhipu" in commands
    assert "dsproxy config set-model --provider zhipu-coding" in commands
    assert "dsproxy config set-model --provider zai" in commands
    assert "dsproxy config set-model --provider zai-coding" in commands
    assert "dsproxy config set-model --provider qwen-beijing" in commands
    assert "dsproxy config set-model --provider qwen-singapore" in commands
    assert "dsproxy config set-model --provider qwen-us" in commands
    assert "dsproxy config set-model --provider glm" not in commands
    assert "dsproxy config set-model --provider qwen" not in commands
    assert "dsproxy config set-web-search-api-key --provider serpapi" in commands
    assert "dsproxy config set-web-search-api-key --provider brave" not in commands
    assert "dsproxy config set-image-api-key --provider zhipu" in commands
    assert "dsproxy config set-image-api-key --provider zai" in commands
    assert "dsproxy config set-image-api-key --provider glm" not in commands
    assert "dsproxy config set-model --provider deepseek --value sk-fake-deepseek-api-key" in commands
    assert "dsproxy config set-model provider-model-name --provider custom --base-url https://api.example.com/v1 --skip-validation" in commands
    assert "dsproxy config set-model provider-model-name --provider custom --base-url https://api.example.com/v1 --value sk-fake-custom-api-key --skip-validation" in commands

    parser = cli.build_parser()
    for command in commands:
        parts = command.split()
        assert parts[:2] == ["dsproxy", "config"]
        args = parts[1:]
        namespace = parser.parse_args(args)
        assert getattr(namespace, "func", None) is cli._config


def test_readme_uses_set_model_for_custom_model_api_examples() -> None:
    text = _readme_text()
    assert "dsproxy config set-api-key --provider custom" not in text
    assert "dsproxy config set-model qwen3-coder-plus --provider custom --base-url https://coding-intl.dashscope.aliyuncs.com/v1 --skip-validation" in text
    assert "--model qwen3-coder-plus" not in text

def test_readme_model_provider_surface_uses_explicit_sites_and_plans() -> None:
    text = _readme_text()
    assert "dsproxy config set-model --provider glm\n" not in text
    assert "dsproxy config set-model --provider qwen\n" not in text
    assert "dsproxy config set-model --provider zhipu-coding" in text
    assert "dsproxy config set-model --provider zai-coding" in text
    assert "dsproxy config set-model --provider qwen-beijing" in text
    assert "dsproxy config set-model --provider qwen-singapore" in text
    assert "dsproxy config set-model --provider qwen-us" in text
    assert "dsproxy config set-web-search-api-key --provider brave" not in text
