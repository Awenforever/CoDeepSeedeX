from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _troubleshooting_text() -> str:
    return (ROOT / "TROUBLESHOOTING.md").read_text(encoding="utf-8")


def test_troubleshooting_lifecycle_examples_use_reasoning_as_primary() -> None:
    text = _troubleshooting_text()

    assert "cox status reasoning" in text
    assert "cox start reasoning" in text
    assert "cox stop reasoning" in text

    assert "cox status thinking" not in text
    assert "cox start thinking" not in text
    assert "cox stop thinking" not in text


def test_troubleshooting_missing_profile_guidance_is_provider_neutral() -> None:
    text = _troubleshooting_text()

    assert "codex --profile cox" in text
    assert "cox config status" in text
    assert "cox provider list" in text

    assert "codex --profile deepseek" not in text
    assert "configured DeepSeek profile" not in text
    assert "configured for the active CodeXchange provider/profile" in text
