from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

RELEASE_BOOTSTRAP = "https://github.com/Awenforever/CoDeepSeedeX/releases/latest/download/bootstrap.sh"
RELEASE_INSTALL = "https://github.com/Awenforever/CoDeepSeedeX/releases/latest/download/install.sh"
RAW_BOOTSTRAP = "https://raw.githubusercontent.com/Awenforever/CoDeepSeedeX/master/bootstrap.sh"
RAW_INSTALL = "https://raw.githubusercontent.com/Awenforever/CoDeepSeedeX/master/scripts/install.sh"
GITHUB_RAW_BOOTSTRAP = "https://github.com/Awenforever/CoDeepSeedeX/raw/refs/heads/master/bootstrap.sh"
GITHUB_RAW_INSTALL = "https://github.com/Awenforever/CoDeepSeedeX/raw/refs/heads/master/scripts/install.sh"
CDN_BOOTSTRAP = "https://cdn.jsdelivr.net/gh/Awenforever/CoDeepSeedeX@master/bootstrap.sh"
FASTLY_BOOTSTRAP = "https://fastly.jsdelivr.net/gh/Awenforever/CoDeepSeedeX@master/bootstrap.sh"


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


def test_docs_prefer_release_latest_bootstrap_with_fallbacks() -> None:
    for rel in ["README.md", "README.zh-CN.md", "OPERATIONS.md", "TROUBLESHOOTING.md"]:
        data = text(rel)
        assert RELEASE_BOOTSTRAP in data

    for rel in ["README.md", "README.zh-CN.md", "OPERATIONS.md"]:
        data = text(rel)
        assert data.index(RELEASE_BOOTSTRAP) < data.index(RAW_BOOTSTRAP)
        assert GITHUB_RAW_BOOTSTRAP in data
        assert CDN_BOOTSTRAP in data
        assert FASTLY_BOOTSTRAP in data


def test_bootstrap_prefers_release_install_asset_before_raw_fallbacks() -> None:
    data = text("bootstrap.sh")

    assert f'INSTALLER_URL="${{DEEPSEEK_PROXY_INSTALLER_URL:-{RELEASE_INSTALL}}}"' in data
    assert f'ALT_INSTALLER_URL="${{DEEPSEEK_PROXY_ALT_INSTALLER_URL:-{RAW_INSTALL}}}"' in data
    assert f'THIRD_INSTALLER_URL="${{DEEPSEEK_PROXY_THIRD_INSTALLER_URL:-{GITHUB_RAW_INSTALL}}}"' in data
    assert data.index(RELEASE_INSTALL) < data.index(RAW_INSTALL) < data.index(GITHUB_RAW_INSTALL)
    assert "Trying shallow git clone fallback." in data
