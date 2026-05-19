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

def test_developer_handbook_current_release_state_is_synced_to_latest_release_note_node() -> None:
    en = _read("docs/developer-handbook.md")
    zh = _read("docs/developer-handbook.zh-CN.md")

    en_current = en.split("## 3. Key file map", 1)[0]
    zh_current = zh.split("## 3. 关键文件地图", 1)[0]

    assert "Current public Release commit: `80bb0ea`" in en_current
    assert "p2.10a81-handbook-current-state-sync" in en_current
    assert "p2.10a71-docs-prerelease-notes = 6ea67b2" not in en_current

    assert "当前公开Release提交：`80bb0ea`" in zh_current
    assert "p2.10a81-handbook-current-state-sync" in zh_current
    assert "p2.10a71-docs-prerelease-notes = 6ea67b2" not in zh_current

    assert "docs/release-notes-v0.3.9-alpha.md" in en_current
    assert "docs/release-notes-v0.3.9-alpha.md" in zh_current
