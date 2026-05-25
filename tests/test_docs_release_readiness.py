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

    assert "Current public Release: `v0.3.9-alpha`" in en_current
    assert "Current public Release commit: `82a4428`" in en_current
    assert "Current internal development checkpoint: `p2.14a6-routing-policy-cli-doctor`" in en_current
    assert "Latest closed documentation sync checkpoint: `p2.14a6-routing-policy-cli-doctor`" in en_current
    assert "Current public Release note synchronization checkpoint: `p2.13a5-token-first-trim-profile-scoped-report`" in en_current
    assert "  - `v0.3.9-alpha = 82a4428`" in en_current

    assert "当前公开Release：`v0.3.9-alpha`" in zh_current
    assert "当前公开Release提交：`82a4428`" in zh_current
    assert "当前内部开发检查点：`p2.14a6-routing-policy-cli-doctor`" in zh_current
    assert "最新闭合文档同步检查点：`p2.14a6-routing-policy-cli-doctor`" in zh_current
    assert "当前公开Release note同步检查点：`p2.13a5-token-first-trim-profile-scoped-report`" in zh_current
    assert "  - `v0.3.9-alpha = 82a4428`" in zh_current
    assert "ab680ee" not in zh_current
def test_tracked_release_note_document_is_not_maintained() -> None:
    assert not (ROOT / "docs" / "release-notes-v0.3.9-alpha.md").exists()

    readme = _read("README.md")
    readme_zh = _read("README.zh-CN.md")
    forbidden = "docs/" + "release-notes-v0.3.9-alpha.md"
    assert forbidden not in readme
    assert forbidden not in readme_zh
    assert "v0.3.9-alpha Latest" not in readme
    assert "v0.3.9-alpha Latest" not in readme_zh

    en = _read("docs/developer-handbook.md")
    zh = _read("docs/developer-handbook.zh-CN.md")
    log = _read("docs/development-log.md")
    for text in (en, zh, log):
        bad_placeholder = "the tracked " + "v0.3.9-alpha Release-note document"
        assert bad_placeholder not in text
        assert "docs/" + "release-notes-v0.3.9-alpha.md" not in text
