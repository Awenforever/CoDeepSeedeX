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
    assert "Current public Release commit: `v0.3.9-alpha tag target after Release closeout`" in en_current
    assert "Current internal development checkpoint: `p2.12a12-clean-release-highlights`" in en_current
    assert "Latest closed documentation sync checkpoint: `p2.12a12-clean-release-highlights`" in en_current
    assert "Current public Release note synchronization checkpoint: `p2.12a12-clean-release-highlights`" in en_current
    assert "  - `v0.3.9-alpha = release-closeout tag target`" in en_current

    assert "当前公开Release：`v0.3.9-alpha`" in zh_current
    assert "当前公开Release提交：`release-closeout tag target`" in zh_current
    assert "当前内部开发检查点：`p2.12a12-clean-release-highlights`" in zh_current
    assert "最新闭合文档同步检查点：`p2.12a12-clean-release-highlights`" in zh_current
    assert "当前公开Release note同步检查点：`p2.12a12-clean-release-highlights`" in zh_current
    assert "  - `v0.3.9-alpha = release-closeout tag target`" in zh_current
    assert "ab680ee" not in zh_current

def test_release_notes_are_clean_user_facing_highlights() -> None:
    body = _read("docs/release-notes-v0.3.9-alpha.md")
    lower = body.lower()

    required = [
        "requires `weclaw_dev >= v0.1.9-alpha`",
        "highlights since v0.3.8-alpha",
        "weclaw status and details are now dsproxy-owned",
        "current-session token and cost accounting",
        "provider usage remains authoritative",
        "prompt cache hit/miss accounting",
        "model context window",
        "`auto_compact_ratio = 0.90`",
        "token-first compact and trim",
        "runtime payload reports are persisted",
        "semantic payload compaction",
        "successful pytest output containing negated phrases",
        "codex profile compatibility",
        "deepseek pricing and cost display are cny-first",
        "same-version commit-aware upgrade",
        "bootstrap.sh` and `install.sh",
    ]
    for marker in required:
        assert marker in lower

    forbidden = [
        "# CoDeepSeedeX v0.3.9-alpha release notes",
        "Changes since the previous published v0.3.9-alpha build",
        "Fixes since the previous published v0.3.9-alpha build",
        "Validation for this Release update",
        "Cumulative v0.3.9-alpha coverage retained from earlier builds",
        "Final Plan closure / tests and docs contract",
        "Pricing daily refresh contract",
        "Pricing owned refresh contract",
        "Semantic payload compaction production validation",
        "Internal marker:",
        "p2.10a",
        "p2.11",
        "p2.12",
        "run_ok",
        "focused tests",
        "full test",
    ]
    for marker in forbidden:
        assert marker not in body
