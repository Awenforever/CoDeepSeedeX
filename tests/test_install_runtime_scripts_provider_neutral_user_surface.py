from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_SCRIPT = ROOT / "scripts" / "install-runtime-scripts.sh"


def test_deprecated_runtime_script_points_to_reasoning_entrypoints() -> None:
    text = RUNTIME_SCRIPT.read_text(encoding="utf-8")

    assert "install-runtime-scripts.sh is deprecated." in text
    assert "cox start reasoning" in text
    assert "cox stop reasoning" in text
    assert "cox status reasoning" in text
    assert "reasoning and standard" in text


def test_deprecated_runtime_script_does_not_recommend_thinking_entrypoints() -> None:
    text = RUNTIME_SCRIPT.read_text(encoding="utf-8")

    assert "cox start thinking" not in text
    assert "cox stop thinking" not in text
    assert "cox status thinking" not in text
