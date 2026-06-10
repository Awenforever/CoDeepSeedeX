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
    assert "最新闭合profile drift fail-closed guard检查点：`p2.19a23-profile-drift-failclosed-guard`" in zh_current
    assert "Latest closed profile drift fail-closed guard checkpoint: `p2.19a23-profile-drift-failclosed-guard`" in en_current
    assert "最新闭合status JSON与upstream model leakage检查点：`p2.19a21-status-json-and-upstream-model-leakage`" in zh_current
    assert "Latest closed status JSON and upstream model leakage checkpoint: `p2.19a21-status-json-and-upstream-model-leakage`" in en_current
    assert "最新闭合real-HOME profile model consistency检查点：`p2.19a19-real-home-profile-model-consistency`" in zh_current
    assert "Latest closed real-HOME profile model consistency checkpoint: `p2.19a19-real-home-profile-model-consistency`" in en_current
    assert "最新闭合wrapper path hygiene检查点：`p2.19a17-wrapper-path-hygiene`" in zh_current
    assert "Latest closed wrapper path hygiene checkpoint: `p2.19a17-wrapper-path-hygiene`" in en_current
    assert "最新闭合legacy threshold边界检查点：`p2.19a16-legacy-threshold-boundary`" in zh_current
    assert "Latest closed legacy threshold boundary checkpoint: `p2.19a16-legacy-threshold-boundary`" in en_current
    assert "最新闭合provider alias边界检查点：`p2.19a15-provider-alias-boundary`" in zh_current
    assert "Latest closed provider alias boundary checkpoint: `p2.19a15-provider-alias-boundary`" in en_current
    assert "最新闭合测试契约清理检查点：`p2.19a14-test-contract-pruning`" in zh_current
    assert "Latest closed test contract pruning checkpoint: `p2.19a14-test-contract-pruning`" in en_current

    # Current public Release contract after the p2.19a23 Release refresh.
    assert "Current public Release: `v0.4.3-alpha`" in en_current
    assert "Current public Release kind: ordinary GitHub Latest alpha Release, with `isPrerelease=false`" in en_current
    assert "Current public Release commit: `b11a1c4`" in en_current
    assert "GitHub Latest ordinary Release: `v0.4.3-alpha`" in en_current
    assert "GitHub Release state: `isDraft=false`, `isPrerelease=false`" in en_current
    assert "Public Release assets: `bootstrap.sh`, `install.sh`" in en_current
    assert "`bootstrap.sh` sha256: `257456d2724519bf94ad09f4dce038ac23e8fd5ab9da4b117f1ae637164590a4`" in en_current
    assert "`install.sh` sha256: `99a6abfd555646789e0a10ee28760f22d6fa150bdf946e020d9a1eb43594f070`" in en_current
    assert "Current internal development checkpoint: `p2.22a5-model-catalog-reasoning-presets-schema`" in en_current
    assert "Latest runtime checkpoint included in the public Release: `p2.21a4-codex-wrapper-nonfatal-split-profile`" in en_current
    assert "Latest closed documentation sync checkpoint: `p2.21a6-docs-public-tag-state-sync`" in en_current
    assert "Latest provider/profile abstraction checkpoint: `p2.20a2-provider-profile-primary-only-and-real-entry`" in en_current
    assert "Latest closed ghost audit tool checkpoint: `p2.19a23-profile-drift-failclosed-guard`" in en_current
    assert "Current public Release note synchronization checkpoint: `p2.21a4-codex-wrapper-nonfatal-split-profile`" in en_current
    assert "  - `v0.4.3-alpha = f8a6635`" in en_current
    assert "  - `v0.3.9-alpha = 82a4428`" in en_current

    assert "当前公开Release：`v0.4.3-alpha`" in zh_current
    assert "当前公开Release类型：GitHub Latest普通alpha Release，`isPrerelease=false`" in zh_current
    assert "当前公开Release提交：`b11a1c4`" in zh_current
    assert "GitHub Latest普通Release：`v0.4.3-alpha`" in zh_current
    assert "GitHub Release状态：`isDraft=false`，`isPrerelease=false`" in zh_current
    assert "Release资产：`bootstrap.sh`，`install.sh`" in zh_current
    assert "`bootstrap.sh` sha256：`257456d2724519bf94ad09f4dce038ac23e8fd5ab9da4b117f1ae637164590a4`" in zh_current
    assert "`install.sh` sha256：`99a6abfd555646789e0a10ee28760f22d6fa150bdf946e020d9a1eb43594f070`" in zh_current
    assert "当前内部开发检查点：`p2.22a5-model-catalog-reasoning-presets-schema`" in zh_current
    assert "当前公开Release包含的最新运行时检查点：`p2.21a4-codex-wrapper-nonfatal-split-profile`" in zh_current
    assert "最新闭合文档同步检查点：`p2.21a6-docs-public-tag-state-sync`" in zh_current
    assert "最新provider/profile抽象检查点：`p2.20a2-provider-profile-primary-only-and-real-entry`" in zh_current
    assert "最新闭合幽灵审计工具检查点：`p2.19a23-profile-drift-failclosed-guard`" in zh_current
    assert "当前公开Release note同步检查点：`p2.21a4-codex-wrapper-nonfatal-split-profile`" in zh_current
    assert "  - `v0.4.3-alpha = f8a6635`" in zh_current
    assert "  - `v0.3.9-alpha = 82a4428`" in zh_current

    # Removed stale contract assertions from the old pre-release/old-Latest period.
    stale_markers = [
        "Current public Release kind: " + "pre-release",
        "Current public Release commit: resolved from `v0.4.3-alpha` tag after publication",
        "GitHub Latest ordinary Release: `v0.4.0-" + "alpha`",
        "GitHub Release flags: `isDraft=false`, `isPrerelease=" + "true`",
        "  - `v0.4.3-alpha = resolved by release " + "tag`",
        "当前公开Release类型：" + "pre-release",
        "当前公开Release提交：发布后由`v0.4.3-alpha` tag解析",
        "GitHub Latest普通Release：`v0.4.0-" + "alpha`",
        "GitHub Release标志：`isDraft=false`，`isPrerelease=" + "true`",
        "  - `v0.4.3-alpha = resolved by release " + "tag`",
        "ab680ee",
    ]
    for stale in stale_markers:
        assert stale not in en_current
        assert stale not in zh_current

def test_tracked_release_note_document_is_not_maintained() -> None:
    assert not (ROOT / "docs" / "release-notes-v0.3.9-alpha.md").exists()
    assert not (ROOT / "docs" / ("release-notes-v0.4.0-" + "alpha.md")).exists()

    readme = _read("README.md")
    readme_zh = _read("README.zh-CN.md")
    forbidden = "docs/" + ("release-notes-v0.3.9-" + "alpha.md")
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


def test_p220a3_developer_handbook_records_subprocess_shell_builtin_rule() -> None:
    en = (ROOT / "docs" / "developer-handbook.md").read_text(encoding="utf-8")
    zh = (ROOT / "docs" / "developer-handbook.zh-CN.md").read_text(encoding="utf-8")
    assert "subprocess shell-builtin probe rule" in en
    assert "subprocess shell-builtin probe rule" in zh
    assert 'subprocess.run(["bash", "-lc", "command -v gh"], ...)' in en
    assert 'subprocess.run(["bash", "-lc", "command -v gh"], ...)' in zh
    assert 'subprocess.run(["command", "-v", "gh"], ...)' in en
    assert 'subprocess.run(["command", "-v", "gh"], ...)' in zh
    assert "FileNotFoundError" in en
    assert "FileNotFoundError" in zh
