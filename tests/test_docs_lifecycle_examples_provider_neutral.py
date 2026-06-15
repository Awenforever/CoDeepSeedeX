from __future__ import annotations

from pathlib import Path


README_FILES = [Path("README.md"), Path("README.zh-CN.md")]


def test_readme_lifecycle_examples_use_standard_and_reasoning_as_primary() -> None:
    for path in README_FILES:
        text = path.read_text(encoding="utf-8")

        assert "cox start standard" in text
        assert "cox start reasoning" in text
        assert "cox status standard" in text
        assert "cox status reasoning" in text
        assert "cox stop standard" in text
        assert "cox stop reasoning" in text
        assert "cox status reasoning --weclaw-json" in text

        assert "cox start thinking" not in text
        assert "cox status thinking" not in text
        assert "cox stop thinking" not in text
        assert "cox status thinking --weclaw-json" not in text


def test_handbook_keeps_thinking_only_as_legacy_compatibility_text() -> None:
    handbook = Path("docs/developer-handbook.md").read_text(encoding="utf-8")
    handbook_zh = Path("docs/developer-handbook.zh-CN.md").read_text(encoding="utf-8")

    assert "cox status reasoning --json" in handbook
    assert "cox status --json reasoning" in handbook
    assert "legacy `cox status thinking --json`" in handbook
    assert "must remain accepted" in handbook

    assert "cox status reasoning --json" in handbook_zh
    assert "cox status --json reasoning" in handbook_zh
    assert "legacy `cox status thinking --json`" in handbook_zh
    assert "必须继续兼容接受" in handbook_zh
