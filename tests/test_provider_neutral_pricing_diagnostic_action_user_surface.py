from __future__ import annotations

from pathlib import Path


APP_SOURCE = Path("codexchange_proxy/app.py").read_text(encoding="utf-8")


def test_pricing_reasoning_output_action_is_provider_neutral():
    assert (
        "treat provider completion_tokens as billable output tokens unless the configured provider "
        "exposes separate reasoning output pricing"
    ) in APP_SOURCE
    assert "unless DeepSeek exposes separate reasoning output pricing" not in APP_SOURCE


def test_pricing_refresh_action_is_provider_neutral():
    assert (
        "run cox pricing refresh --json to fetch and validate the configured provider pricing source; "
        "add --write-cache to persist it"
    ) in APP_SOURCE
    assert "official DeepSeek pricing HTML" not in APP_SOURCE
