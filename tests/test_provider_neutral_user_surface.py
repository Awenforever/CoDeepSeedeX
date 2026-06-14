from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

USER_SURFACE_FILES = [
    "README.md",
    "README.zh-CN.md",
    "TROUBLESHOOTING.md",
    "bootstrap.sh",
    "scripts/install.sh",
    "codexchange_proxy/cli.py",
]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_codexchange_public_surface_is_not_deepseek_as_product() -> None:
    forbidden = [
        "Codex × DeepSeek local Responses proxy",
        "DeepSeek local Responses proxy",
        "DeepSeek-only proxy",
        "DeepSeek Thinking Responses Proxy",
        "DeepSeek Thinking profile",
    ]
    combined = "\n".join(read(rel) for rel in USER_SURFACE_FILES)
    for marker in forbidden:
        assert marker not in combined


def test_deepseek_remains_allowed_as_provider_example() -> None:
    readme = read("README.md")
    assert "cox config set-model --provider deepseek" in readme
    assert "provider-backed profiles" in readme.lower()


def test_public_release_tag_is_synchronized_to_v048() -> None:
    for rel in [
        "README.md",
        "README.zh-CN.md",
        "docs/developer-handbook.md",
        "docs/developer-handbook.zh-CN.md",
        "scripts/install.sh",
        "codexchange_proxy/app.py",
        "tests/test_cli.py",
        "tests/test_version_metadata.py",
        "tests/test_docs_release_readiness.py",
    ]:
        assert "v0.4.13-alpha" in read(rel)
