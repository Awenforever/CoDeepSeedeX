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
    assert budget["token_accounting_scope"] == "normalized_compaction_messages_only"
    assert "char_control_scope" not in budget
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
    assert "char_control_scope" not in contract
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
    assert "char_control_scope" not in contract
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
    dumped = json.dumps(guard, sort_keys=True)

    assert guard["unit"] == "tokens"
    assert guard["current_tokens"] == 123
    assert guard["compaction"]["unit"] == "tokens"
    assert guard["compaction"]["trigger_tokens"] == 900
    assert "current_chars" not in dumped
    assert "trigger_chars" not in dumped
    assert "legacy_char_debug" not in dumped


def test_env_auto_compact_ratio_is_ignored_for_managed_runtime_contract(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DEEPSEEK_PROXY_AUTO_COMPACT_RATIO", "0.02")

    codex_home = tmp_path / "codex"
    codex_home.mkdir()
    config_path = codex_home / "config.toml"
    config_path.write_text(
        "[profiles.deepseek]\n"
        "model = \"deepseek-v4-flash\"\n"
        "model_provider = \"deepseek-proxy\"\n"
        "model_context_window = 1000000\n"
        "model_auto_compact_token_limit = 900000\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("CODEX_HOME", str(codex_home))

    context = proxy_app._runtime_token_first_context_contract_for_payload(
        {"model": "deepseek-v4-flash"},
        active_profile="deepseek",
    )

    assert context["model_context_window_tokens"] == 1_000_000
    assert context["auto_compact_ratio"] == 0.9
    assert context["model_auto_compact_token_limit"] == 900_000
    assert context["auto_compact_policy"]["managed_expected_auto_compact_ratio"] == 0.9
    assert context["legacy_absolute_limit_ignored"] is None
    assert context["legacy_ratio_override_ignored"]["available"] is True
    assert context["legacy_ratio_override_ignored"]["managed_value"] == 0.9
    assert context["legacy_ratio_override_ignored"]["available"] is True
    assert context["legacy_ratio_override_ignored"]["managed_value"] == 0.9

def test_runtime_token_compaction_status_reports_threshold_exceeded_skipped_without_negative_tokens() -> None:
    contract = proxy_app._runtime_token_first_compaction_contract(
        {
            "compacted": False,
            "reason": "too_few_messages",
            "estimated_context_tokens": 42572,
            "after_estimated_context_tokens": 42572,
            "auto_compact_threshold_tokens": 20000,
            "model_auto_compact_token_limit": 900000,
            "auto_compact_ratio": 0.9,
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
        auto_compact_token_limit=900_000,
        effective_safe_window=0,
        model_catalog=None,
    )
    values = explanation["value_explanations"]
    assert "auto_compact_ratio=0.9" in values["auto_compact_token_limit"]
    assert "managed 90% ratio" in values["auto_compact_ratio"]
    assert "auto_compact_ratio=0.9" in values["auto_compact_token_limit"]
    assert "managed 90% ratio" in values["auto_compact_ratio"]



def test_runtime_token_status_context_hides_legacy_non_token_config_from_primary_context() -> None:
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
    dumped = json.dumps(context, sort_keys=True)

    assert context["unit"] == "tokens"
    assert "config" not in context["compaction"]
    assert context["compaction"]["tokens_to_auto_compact"] == 0
    assert context["compaction"]["tokens_over_auto_compact_threshold"] == 22572
    assert "legacy_char_debug" not in dumped
    assert "trigger_chars" not in dumped
    assert "max_context_chars" not in dumped

def test_compaction_budget_does_not_count_raw_responses_input(tmp_path: Path, monkeypatch) -> None:
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
    messages = [{"role": "user", "content": "hello world"}]
    huge_raw_input = "x" * 1_000_000
    request_payload = {
        "model": "deepseek-v4-flash",
        "input": [{"type": "function_call_output", "output": huge_raw_input}],
        "tools": [{"type": "function", "function": {"name": "noop", "description": huge_raw_input}}],
    }

    budget = proxy_app._runtime_token_first_compaction_budget(
        messages=messages,
        request_payload=request_payload,
        config={},
        active_profile="deepseek",
    )
    expected = proxy_app._runtime_token_first_payload_token_estimate(
        proxy_app._runtime_token_first_payload_for_messages(messages, request_payload=request_payload)
    )["estimated_tokens"]

    assert budget["estimated_context_tokens"] == expected
    assert budget["estimated_context_tokens"] < 1000
    assert budget["token_accounting_scope"] == "normalized_compaction_messages_only"


def test_token_only_public_runtime_contract_strips_legacy_non_token_fields() -> None:
    value = {
        "unit": "tokens",
        "current_tokens": 10,
        "legacy_char_debug": {"scope": "diagnostic_only_not_a_runtime_trigger"},
        "char_control_scope": "diagnostic_only_not_a_runtime_trigger",
        "compaction": {
            "unit": "tokens",
            "current_tokens": 10,
            "before_chars": 100,
            "after_chars": 20,
            "chars_removed": 80,
        },
    }
    public = proxy_app._token_only_public_runtime_contract(value)
    dumped = json.dumps(public, sort_keys=True)

    assert public["unit"] == "tokens"
    assert public["current_tokens"] == 10
    assert public["compaction"]["current_tokens"] == 10
    assert "legacy_char_debug" not in dumped
    assert "char_control_scope" not in dumped
    assert "before_chars" not in dumped
    assert "after_chars" not in dumped
    assert "chars_removed" not in dumped
