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


def test_context_contract_ignores_legacy_absolute_auto_compact_limit_and_derives_ratio() -> None:
    context = proxy_app._runtime_profile_context_contract(
        {
            "model_context_window": "1000000",
            "model_auto_compact_token_limit": "750000",
        },
        effective_model="deepseek-v4-flash",
    )

    policy = context["auto_compact_policy"]
    assert context["display_limit_tokens"] == 1_000_000
    assert context["model_context_window_tokens"] == 1_000_000
    assert context["model_auto_compact_token_limit"] == 900_000
    assert context["auto_compact_threshold_tokens"] == 900_000
    assert context["auto_compact_ratio"] == 0.9
    assert policy["needs_migration"] is False
    assert policy["status"] == "managed_expected_ratio"
    assert policy["observed_auto_compact_ratio"] == 0.9
    assert context["legacy_absolute_limit_ignored"]["ignored_value"] == 750_000
    assert context["legacy_absolute_limit_ignored"]["derived_value"] == 900_000
    assert context["limit_explanation"]["auto_compact_policy"]["needs_migration"] is False


def test_runtime_context_contract_ignores_absolute_env_threshold(monkeypatch, tmp_path: Path) -> None:
    codex_config = tmp_path / "codex.toml"
    codex_config.write_text(
        """
[profiles.deepseek]
model = "deepseek-v4-flash"
model_provider = "deepseek-proxy"
model_context_window = 1000000
model_auto_compact_token_limit = 750000
""".strip()
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("CODEX_CONFIG_FILE", str(codex_config))
    monkeypatch.setenv("DEEPSEEK_PROXY_AUTO_COMPACT_THRESHOLD_TOKENS", "750000")
    context = proxy_app._runtime_token_first_context_contract_for_payload(
        {"model": "deepseek-v4-flash"},
        active_profile="deepseek",
    )

    assert context["model_context_window_tokens"] == 1_000_000
    assert context["auto_compact_threshold_tokens"] == 900_000
    assert context["model_auto_compact_token_limit"] == 900_000
    assert context["auto_compact_ratio"] == 0.9
    assert context["auto_compact_policy"]["status"] == "managed_expected_ratio"
    assert context["legacy_absolute_limit_ignored"]["ignored_value"] == 750_000


def test_compaction_budget_exposes_strict_plan_token_field_names(tmp_path: Path, monkeypatch) -> None:
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

    budget = proxy_app._runtime_token_first_compaction_budget(
        messages=[{"role": "user", "content": "hello " * 30}],
        request_payload={"model": "deepseek-v4-flash"},
        config={},
        active_profile="deepseek",
    )

    assert budget["primary_control_unit"] == "tokens"
    assert budget["char_control_scope"] in {"fallback_debug_safety_only", "diagnostic_only_not_a_runtime_trigger"}
    assert budget["estimated_tokens_before_compact"] == budget["estimated_context_tokens"]
    assert budget["estimated_tokens_after_compact"] == budget["estimated_context_tokens"]
    assert budget["estimated_tokens_removed_by_compact"] == 0
    assert budget["auto_compact_threshold_tokens"] == 900


def test_compaction_contract_exposes_strict_plan_token_field_names() -> None:
    report = {
        "compacted": True,
        "reason": "token_first_triggered",
        "estimated_context_tokens": 950,
        "after_estimated_context_tokens": 500,
        "tokens_removed": 450,
        "auto_compact_threshold_tokens": 900,
        "model_auto_compact_token_limit": 900,
        "model_context_window_tokens": 1000,
        "auto_compact_ratio": 0.9,
        "runtime_trigger_source": "token_first",
        "policy_decision": {"token_budget": {"tokenizer": {"available": True}}},
    }

    contract = proxy_app._runtime_token_first_compaction_contract(report)

    assert contract["primary_control_unit"] == "tokens"
    assert contract["char_control_scope"] in {"fallback_debug_safety_only", "diagnostic_only_not_a_runtime_trigger"}
    assert contract["estimated_tokens_before_compact"] == 950
    assert contract["estimated_tokens_after_compact"] == 500
    assert contract["estimated_tokens_removed_by_compact"] == 450
    assert contract["trigger_tokens"] == 900
    assert contract["retention_ratio"] == 500 / 950


def test_unavailable_compaction_contract_still_exposes_strict_plan_token_field_names() -> None:
    contract = proxy_app._runtime_token_first_compaction_contract(None)

    assert contract["available"] is False
    assert contract["unit"] == "tokens"
    assert contract["primary_control_unit"] == "tokens"
    assert contract["char_control_scope"] in {"fallback_debug_safety_only", "diagnostic_only_not_a_runtime_trigger"}
    assert contract["estimated_tokens_before_compact"] is None
    assert contract["estimated_tokens_after_compact"] is None
    assert contract["estimated_tokens_removed_by_compact"] == 0
    assert contract["before_tokens"] is None
    assert contract["after_tokens"] is None
    assert contract["tokens_removed"] == 0
    assert contract["raw_content_exposed"] is False
    assert contract["redacted"] is True


def test_runtime_payload_guard_contract_is_token_only_visible_surface() -> None:
    report = {
        "compacted": False,
        "reason": "token_first_below_auto_compact_threshold",
        "estimated_context_tokens": 123,
        "after_estimated_context_tokens": 123,
        "auto_compact_threshold_tokens": 900,
        "model_auto_compact_token_limit": 900,
        "model_context_window_tokens": 1000,
        "auto_compact_ratio": 0.9,
        "runtime_trigger_source": "token_first",
        "before_chars": 10000,
        "after_chars": 9000,
        "policy_decision": {"token_budget": {"tokenizer": {"available": True}}},
    }
    guard = proxy_app._runtime_payload_guard_contract({"compaction": {"config": {}}}, compaction_report=report)
    assert guard["unit"] == "tokens"
    assert guard["current_tokens"] == 123
    assert "current_chars" not in guard
    assert guard["compaction"]["unit"] == "tokens"
    assert guard["compaction"]["trigger_tokens"] == 900
    assert "trigger_chars" not in guard["compaction"]
    assert guard["legacy_char_debug"]["scope"] == "diagnostic_only_not_a_runtime_trigger"
    assert guard["legacy_char_debug"]["control_disabled"] is True

def test_env_auto_compact_ratio_is_the_only_low_threshold_lab_control(monkeypatch, tmp_path: Path) -> None:
    codex_config = tmp_path / "codex.toml"
    codex_config.write_text(
        """
[profiles.deepseek]
model = "deepseek-v4-flash"
model_provider = "deepseek-proxy"
model_context_window = 1000000
model_auto_compact_token_limit = 900000
""".strip()
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("CODEX_CONFIG_FILE", str(codex_config))
    monkeypatch.setenv("DEEPSEEK_PROXY_AUTO_COMPACT_RATIO", "0.02")
    monkeypatch.setenv("DEEPSEEK_PROXY_AUTO_COMPACT_THRESHOLD_TOKENS", "10800")

    context = proxy_app._runtime_token_first_context_contract_for_payload(
        {"model": "deepseek-v4-flash"},
        active_profile="deepseek",
    )

    assert context["model_context_window_tokens"] == 1_000_000
    assert context["auto_compact_ratio"] == 0.02
    assert context["auto_compact_threshold_tokens"] == 20_000
    assert context["model_auto_compact_token_limit"] == 20_000
    assert context["legacy_absolute_limit_ignored"]["ignored_value"] == 10800
    assert context["legacy_absolute_limit_ignored"]["derived_value"] == 20_000
    assert context["auto_compact_policy"]["managed_expected_auto_compact_ratio"] == 0.02
    assert context["auto_compact_policy"]["managed_expected_auto_compact_threshold_tokens"] == 20_000

def test_runtime_token_compaction_status_reports_threshold_exceeded_skipped_without_negative_tokens() -> None:
    contract = proxy_app._runtime_token_first_compaction_contract(
        {
            "compacted": False,
            "reason": "too_few_messages",
            "estimated_context_tokens": 42572,
            "after_estimated_context_tokens": 42572,
            "auto_compact_threshold_tokens": 20000,
            "model_auto_compact_token_limit": 20000,
            "auto_compact_ratio": 0.02,
            "tokens_to_auto_compact": -22572,
            "runtime_trigger_source": "token_first",
        }
    )
    assert contract["status"] == "skipped"
    assert contract["reason"] == "too_few_messages"
    assert contract["threshold_exceeded"] is True
    assert contract["tokens_to_auto_compact"] == 0
    assert contract["tokens_until_auto_compact_threshold"] == 0
    assert contract["tokens_over_auto_compact_threshold"] == 22572
    assert contract["compacted"] is False


def test_weclaw_context_limit_explanation_uses_active_managed_ratio_text(monkeypatch) -> None:
    monkeypatch.setenv("DEEPSEEK_PROXY_AUTO_COMPACT_RATIO", "0.02")
    explanation = proxy_app._weclaw_context_limit_explanation(
        model_context_window=1_000_000,
        auto_compact_token_limit=20_000,
        effective_safe_window=0,
        model_catalog=None,
    )
    values = explanation["value_explanations"]
    assert "auto_compact_ratio=0.02" in values["auto_compact_token_limit"]
    assert "managed 2% ratio" in values["auto_compact_ratio"]
    assert "0.90" not in values["auto_compact_token_limit"]
    assert "0.90" not in values["auto_compact_ratio"]


def test_runtime_token_status_context_hides_char_config_from_primary_context() -> None:
    guard = proxy_app._runtime_payload_guard_contract(
        {
            "compaction": {"config": {"trigger_chars": 900000, "target_chars": 280000}, "last_report": {}},
            "trimming": {"config": {"max_context_chars": 1500000}, "last_report": {}},
        },
        compaction_report={
            "compacted": False,
            "reason": "too_few_messages",
            "estimated_context_tokens": 42572,
            "after_estimated_context_tokens": 42572,
            "auto_compact_threshold_tokens": 20000,
            "tokens_to_auto_compact": -22572,
        },
    )
    context = proxy_app._runtime_token_first_status_context(
        {
            "compaction": {"config": {"trigger_chars": 900000, "target_chars": 280000}, "last_report": {}},
            "trimming": {"config": {"max_context_chars": 1500000}, "last_report": {}},
        },
        guard,
    )
    assert context["unit"] == "tokens"
    assert "config" not in context["compaction"]
    assert context["compaction"]["tokens_to_auto_compact"] == 0
    assert context["compaction"]["tokens_over_auto_compact_threshold"] == 22572
    assert context["compaction"]["legacy_char_debug"]["config"]["trigger_chars"] == 900000
    assert context["legacy_char_debug"]["scope"] == "diagnostic_only_not_a_runtime_trigger"
