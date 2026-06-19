from __future__ import annotations

import importlib
from pathlib import Path


def test_remote_compact_guard_key_is_provider_neutral_in_source() -> None:
    source = Path("codexchange_proxy/app.py").read_text(encoding="utf-8")

    assert "expected_for_managed_deepseek_profile" not in source
    assert "expected_for_managed_provider_profile" in source


def test_remote_compact_guard_observation_uses_provider_neutral_key() -> None:
    proxy_app = importlib.import_module("codexchange_proxy.app")

    observation = proxy_app._codex_native_compact_observation([{"role": "user", "content": "hello"}])
    guard = observation["remote_compact_guard"]

    assert guard["expected_for_managed_provider_profile"] is False
    assert "expected_for_managed_deepseek_profile" not in guard


def test_remote_compact_guard_status_fallback_uses_provider_neutral_key() -> None:
    proxy_app = importlib.import_module("codexchange_proxy.app")

    status = proxy_app._codex_native_compact_status_from_report(None, profile="cox")
    guard = status["remote_compact_guard"]

    assert guard["expected_for_managed_provider_profile"] is False
    assert "expected_for_managed_deepseek_profile" not in guard
