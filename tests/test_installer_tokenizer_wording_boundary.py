from __future__ import annotations

from pathlib import Path


def test_installer_tokenizer_sync_wording_is_provider_neutral() -> None:
    text = Path("scripts/install.sh").read_text(encoding="utf-8")

    assert "DeepSeek tokenizer resource sync planned" not in text
    assert "DeepSeek tokenizer resource synced" not in text
    assert "DeepSeek tokenizer resource sync failed" not in text

    assert "Provider tokenizer resource sync planned: deepseek" in text
    assert "Provider tokenizer resource synced: deepseek" in text
    assert "Provider tokenizer resource sync failed for deepseek" in text


def test_installer_keeps_deepseek_tokenizer_command_compatibility() -> None:
    text = Path("scripts/install.sh").read_text(encoding="utf-8")

    assert "cox tokenizer sync deepseek --json" in text
