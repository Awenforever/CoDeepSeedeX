from __future__ import annotations

from pathlib import Path


def test_development_log_runtime_terms_use_provider_neutral_surface() -> None:
    text = Path("docs/development-log.md").read_text(encoding="utf-8")

    legacy_phrases = [
        "starts the thinking proxy",
        "DeepSeek/Codex third-party profiles",
        "local stable/thinking proxy processes",
        "matching stable/thinking proxy route",
    ]
    for phrase in legacy_phrases:
        assert phrase not in text

    expected_phrases = [
        "starts the matching CodeXchange reasoning runtime",
        "native Responses web/image tools on provider-routed Codex profiles",
        "local standard/reasoning runtime processes",
        "matching standard/reasoning runtime route",
    ]
    for phrase in expected_phrases:
        assert phrase in text
