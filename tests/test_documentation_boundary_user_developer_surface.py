from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
USER_DOCS = ["README.md", "README.zh-CN.md", "TROUBLESHOOTING.md"]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_root_user_docs_do_not_contain_maintainer_sections_or_old_release_fallback():
    forbidden = [
        "Maintainer notes",
        "Maintainer documentation",
        "Maintainer-only workflow notes",
        "release tag fallback",
        "Release tag fallback",
        "v0.3.8-alpha",
        "docs/development-log.md",
        "docs/developer-handbook.md",
        "docs/developer-handbook.zh-CN.md",
    ]
    for path in USER_DOCS:
        text = _read(path)
        for marker in forbidden:
            assert marker not in text, f"{marker!r} leaked into user-facing {path}"


def test_root_readme_install_fallback_uses_tag_variable_for_release_entrypoint_contract():
    for path in ["README.md", "README.zh-CN.md"]:
        text = _read(path)
        assert 'tag="v0.4.41-alpha"' in text
        assert "${tag}" in text
        assert "/raw/refs/tags/${tag}/bootstrap.sh" in text


def test_developer_docs_have_a_dedicated_index():
    text = _read("docs/README.md")
    assert "# Developer documentation" in text
    assert "developer-handbook.md" in text
    assert "provider-adapter-contract.md" in text
    assert "TROUBLESHOOTING.md" in text
