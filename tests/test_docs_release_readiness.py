from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def test_docs_do_not_describe_model_api_as_deepseek_only() -> None:
    zh = _read("README.zh-CN.md")
    assert "当前主要面向DeepSeek官方V4 API模型名" not in zh
    assert "OpenAI兼容的model API provider" in zh
    assert "Kimi/Moonshot" in zh
    assert "Qwen/DashScope" in zh


def test_operations_uses_current_dsproxy_config_command_name() -> None:
    ops = _read("docs/developer-handbook.zh-CN.md")
    assert "dsproxy-config" not in ops
    assert "dsproxy config set-model deepseek-v4-pro" in ops
