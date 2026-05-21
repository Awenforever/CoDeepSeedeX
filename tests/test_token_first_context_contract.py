from __future__ import annotations

import json
from pathlib import Path

import importlib

from deepseek_responses_proxy.cli import main

proxy_app = importlib.import_module("deepseek_responses_proxy.app")


def test_runtime_context_window_displays_full_model_window_and_separate_auto_threshold() -> None:
    context = proxy_app._runtime_profile_context_contract(
        {
            "model_context_window": "1000000",
            "model_auto_compact_token_limit": "900000",
        },
        effective_model="deepseek-v4-flash",
    )

    assert context["display_limit_tokens"] == 1_000_000
    assert context["effective_safe_window_tokens"] == 1_000_000
    assert context["model_context_window_tokens"] == 1_000_000
    assert context["auto_compact_token_limit"] == 900_000
    assert context["auto_compact_threshold_tokens"] == 900_000
    assert context["auto_compact_ratio"] == 0.9
    assert context["limit_explanation"]["display_limit_source"] == "codex_profile.model_context_window"
    assert context["limit_explanation"]["display_limit_tokens"] == 1_000_000
    assert context["limit_explanation"]["auto_compact_ratio"] == 0.9


def test_context_used_ratio_uses_full_context_window_not_auto_compact_threshold() -> None:
    tokens = {
        "latest_primary_turn": {
            "available": True,
            "request_id": "req_ctx",
            "summary": {
                "prompt_tokens": 1000,
                "completion_tokens": 20,
                "total_tokens": 1020,
            },
        },
    }
    context = proxy_app._weclaw_context_window_with_usage_estimate(
        {"display_limit_tokens": 1_000_000, "auto_compact_token_limit": 900_000},
        tokens,
    )

    assert context["used_tokens"] == 1000
    assert context["used_ratio"] == 0.001
    assert context["remaining_tokens_estimate"] == 999_000


def test_cli_install_profile_derives_auto_compact_threshold_from_ratio(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "codex.toml"

    assert main([
        "install-codex-profile",
        "--path",
        str(config_path),
        "--dry-run",
    ]) == 0

    result = json.loads(capsys.readouterr().out)
    assert result["context_window_tokens"] == 1_000_000
    assert result["auto_compact_ratio"] == 0.9
    assert result["auto_compact_token_limit"] == 900_000
    assert result["auto_compact_token_limit_source"] == "derived_from_context_window_tokens_and_auto_compact_ratio"
    assert "model_context_window = 1000000" in result["config_preview"]
    assert "model_auto_compact_token_limit = 900000" in result["config_preview"]


def test_cli_legacy_auto_compact_token_limit_argument_is_ignored_in_favor_of_ratio(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "codex.toml"

    assert main([
        "install-codex-profile",
        "--path",
        str(config_path),
        "--auto-compact-token-limit",
        "750000",
        "--dry-run",
    ]) == 0

    result = json.loads(capsys.readouterr().out)
    assert result["auto_compact_ratio"] == 0.9
    assert result["auto_compact_token_limit"] == 900_000
    assert result["ignored_legacy_auto_compact_token_limit"] == 750_000
    assert "model_auto_compact_token_limit = 900000" in result["config_preview"]


def test_runtime_token_first_compaction_budget_uses_profile_threshold(tmp_path: Path, monkeypatch) -> None:
    codex_config = tmp_path / "codex.toml"
    codex_config.write_text(
        """
[profiles.deepseek]
model = "deepseek-v4-flash"
model_provider = "deepseek-proxy"
model_context_window = 1000
model_auto_compact_token_limit = 900
""".strip()
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("CODEX_CONFIG_FILE", str(codex_config))
    monkeypatch.delenv("DEEPSEEK_PROXY_AUTO_COMPACT_THRESHOLD_TOKENS", raising=False)
    budget = proxy_app._runtime_token_first_compaction_budget(
        messages=[{"role": "user", "content": "hello " * 100}],
        request_payload={"model": "deepseek-v4-flash"},
        config={},
    )

    assert budget["available"] is True
    assert budget["unit"] == "tokens"
    assert budget["runtime_trigger_source"] == "token_first"
    assert budget["model_context_window_tokens"] == 1000
    assert budget["auto_compact_threshold_tokens"] == 900
    assert isinstance(budget["estimated_context_tokens"], int)
    assert budget["tokens_to_auto_compact"] == 900 - budget["estimated_context_tokens"]


def test_context_contract_flags_legacy_auto_compact_ratio() -> None:
    context = proxy_app._runtime_profile_context_contract(
        {
            "model_context_window": "1000000",
            "model_auto_compact_token_limit": "750000",
        },
        effective_model="deepseek-v4-flash",
    )

    policy = context["auto_compact_policy"]
    assert context["auto_compact_ratio"] == 0.75
    assert policy["needs_migration"] is True
    assert policy["observed_auto_compact_ratio"] == 0.75
    assert policy["managed_expected_auto_compact_threshold_tokens"] == 900000
    assert policy["display_label"] == "legacy 75%→90%"
    assert policy["short_action"] == "repair profile"
    assert policy["action"]
    assert context["limit_explanation"]["auto_compact_policy"]["needs_migration"] is True
    assert any(item["field"] == "model_auto_compact_token_limit" for item in context["conflicts"])
