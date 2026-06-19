from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_readme_weclaw_backend_is_provider_routed_codex_surface() -> None:
    readme = read("README.md")
    readme_zh = read("README.zh-CN.md")

    assert "provider-routed Codex runtime backend for `weclaw_dev`" in readme
    assert "DeepSeek/Codex runtime backend" not in readme

    assert "provider-routed Codex运行后端" in readme_zh
    assert "DeepSeek/Codex运行后端" not in readme_zh


def test_readme_weclaw_tokenizer_guidance_is_provider_profile_scoped() -> None:
    readme = read("README.md")
    readme_zh = read("README.zh-CN.md")

    assert "local provider/profile tokenizer estimates for Details" in readme
    assert "local DeepSeek profile-tokenizer estimates for Details" not in readme

    assert "provider/profile tokenizer估算" in readme_zh
    assert "基于本地DeepSeekprofile tokenizer的Details估算" not in readme_zh
