from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

RELEASE_BOOTSTRAP = "https://github.com/Awenforever/CoDeepSeedeX/releases/latest/download/bootstrap.sh"
RELEASE_INSTALL = "https://github.com/Awenforever/CoDeepSeedeX/releases/latest/download/install.sh"
TAGGED_RAW_BOOTSTRAP = "https://raw.githubusercontent.com/Awenforever/CoDeepSeedeX/${tag}/bootstrap.sh"
TAGGED_RAW_INSTALL = "https://raw.githubusercontent.com/Awenforever/CoDeepSeedeX/${fallback_ref}/scripts/install.sh"
TAGGED_GITHUB_RAW_BOOTSTRAP = "https://github.com/Awenforever/CoDeepSeedeX/raw/refs/tags/${tag}/bootstrap.sh"
TAGGED_GITHUB_RAW_INSTALL = "https://github.com/Awenforever/CoDeepSeedeX/raw/refs/tags/${fallback_ref}/scripts/install.sh"
TAGGED_CDN_BOOTSTRAP = "https://cdn.jsdelivr.net/gh/Awenforever/CoDeepSeedeX@${tag}/bootstrap.sh"
TAGGED_FASTLY_BOOTSTRAP = "https://fastly.jsdelivr.net/gh/Awenforever/CoDeepSeedeX@${tag}/bootstrap.sh"


def text(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_release_bootstrap_workflow_validates_assets_without_auto_release() -> None:
    workflow = text(".github/workflows/release-bootstrap.yml")

    assert "workflow_dispatch:" in workflow
    assert "contents: read" in workflow
    assert "test -s bootstrap.sh" in workflow
    assert "test -s scripts/install.sh" in workflow
    assert "bash -n bootstrap.sh" in workflow
    assert "bash -n scripts/install.sh" in workflow

    forbidden = [
        "push:",
        "tags:",
        "\"v*\"",
        "contents: write",
        "gh release create",
        "gh release edit",
        "gh release upload",
        "--clobber",
        "--latest",
        "softprops/action-gh-release",
        "ncipollo/release-action",
        "actions/create-release",
    ]
    for marker in forbidden:
        assert marker not in workflow


def test_docs_prefer_release_latest_bootstrap_with_latest_tag_fallbacks() -> None:
    for rel in ["README.md", "README.zh-CN.md", "TROUBLESHOOTING.md", "docs/developer-handbook.zh-CN.md"]:
        data = text(rel)
        assert RELEASE_BOOTSTRAP in data

    for rel in ["README.md", "README.zh-CN.md", "TROUBLESHOOTING.md", "docs/developer-handbook.zh-CN.md"]:
        data = text(rel)
        assert "releases/latest" in data
        assert "refs/tags/${tag}/bootstrap.sh" in data or "@${tag}/bootstrap.sh" in data
        assert "@master/bootstrap.sh" not in data
        assert "refs/heads/master/bootstrap.sh" not in data
def test_bootstrap_prefers_release_install_asset_before_latest_tag_fallbacks() -> None:
    data = text("bootstrap.sh")

    assert f'INSTALLER_URL="${{DEEPSEEK_PROXY_INSTALLER_URL:-{RELEASE_INSTALL}}}"' in data
    assert "LATEST_RELEASE_API_URL=" in data
    assert "resolve_install_ref()" in data
    assert TAGGED_RAW_INSTALL in data
    assert TAGGED_GITHUB_RAW_INSTALL in data
    assert data.index(RELEASE_INSTALL) < data.index("resolve_install_ref()")
    assert "latest Release tag shallow git clone fallback" in data
    assert "master/scripts/install.sh" not in data
    assert "refs/heads/master/scripts/install.sh" not in data
