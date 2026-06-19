from __future__ import annotations

from pathlib import Path


def test_gitignore_runtime_comment_is_provider_neutral() -> None:
    text = Path(".gitignore").read_text(encoding="utf-8")
    assert "# CodeXchange runtime files" in text
    assert "# Thinking proxy runtime files" not in text
