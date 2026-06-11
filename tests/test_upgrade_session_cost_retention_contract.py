
from __future__ import annotations

import importlib
from pathlib import Path

proxy_app = importlib.import_module("codexchange_proxy.app")
proxy_cli = importlib.import_module("codexchange_proxy.cli")


def test_upgrade_same_public_version_skip_helper_matches_weclaw_semantics() -> None:
    assert proxy_cli._should_skip_same_public_version_upgrade(
        current_public_version="v0.3.9-alpha",
        current_public_commit="abc1234",
        target_ref="v0.3.9-alpha",
        target_commit="abc1234",
    ) is True
    assert proxy_cli._should_skip_same_public_version_upgrade(
        current_public_version="v0.3.9-alpha",
        current_public_commit="abc1234",
        target_ref="v0.3.9-alpha",
        target_commit="def5678",
    ) is False
    assert proxy_cli._should_skip_same_public_version_upgrade(
        current_public_version="v0.3.9-alpha",
        current_public_commit="unknown",
        target_ref="v0.3.9-alpha",
        target_commit="def5678",
    ) is False
    assert proxy_cli._should_skip_same_public_version_upgrade(
        current_public_version="v0.3.9-alpha",
        current_public_commit="abc1234",
        target_ref="v0.3.9-alpha",
        target_commit="abc1234",
        force=True,
    ) is False


def test_current_session_cost_contract_uses_tokens_session_not_profile_route(tmp_path: Path) -> None:
    store = proxy_app.SQLiteResponseStore(tmp_path / "usage.sqlite3")
    store.record_usage(
        response_id="r1",
        previous_response_id=None,
        model="deepseek-v4-pro",
        thinking_enabled=True,
        usage_numbers={"prompt_tokens": 100, "completion_tokens": 5, "total_tokens": 105, "cached_tokens": 20, "reasoning_tokens": 0},
        estimated_cost_usd=0.0,
        estimated_cost_source_amount=0.0014,
        estimated_cost_source_currency="CNY",
        estimated_cost_display_amount=0.0014,
        estimated_cost_display_currency="CNY",
        purpose="primary",
        request_id="req1",
        session_id="s1",
    )
    store.record_usage(
        response_id="r2",
        previous_response_id="r1",
        model="deepseek-v4-pro",
        thinking_enabled=True,
        usage_numbers={"prompt_tokens": 50, "completion_tokens": 1, "total_tokens": 51, "cached_tokens": 10, "reasoning_tokens": 0},
        estimated_cost_usd=0.0,
        estimated_cost_source_amount=0.0004,
        estimated_cost_source_currency="CNY",
        estimated_cost_display_amount=0.0004,
        estimated_cost_display_currency="CNY",
        purpose="liveness_judge",
        request_id="req1",
        session_id="s1",
    )
    store.record_usage(
        response_id="old",
        previous_response_id=None,
        model="deepseek-v4-pro",
        thinking_enabled=True,
        usage_numbers={"prompt_tokens": 999, "completion_tokens": 1, "total_tokens": 1000, "cached_tokens": 0, "reasoning_tokens": 0},
        estimated_cost_usd=0.0,
        estimated_cost_source_amount=9.0,
        estimated_cost_source_currency="CNY",
        estimated_cost_display_amount=9.0,
        estimated_cost_display_currency="CNY",
        purpose="primary",
        request_id="old",
        session_id="old-session",
    )

    tokens = proxy_app._weclaw_tokens_contract(store, profile="cox", session_id="s1")
    pricing = {"available": True, "display_currency": "CNY", "is_stale": False, "source": "test"}
    cost = proxy_app._weclaw_cost_contract(tokens, pricing, None)

    assert cost["available"] is True
    assert cost["scope"] == "current_session"
    assert cost["session"]["available"] is True
    assert cost["session"]["scope"] == "current_session"
    assert abs(cost["session"]["estimated_cost"] - 0.0018) < 1e-12
    assert abs(cost["last_turn_estimated_cost"] - 0.0014) < 1e-12
    assert abs(cost["auxiliary_estimated_cost"] - 0.0004) < 1e-12
    assert abs(cost["total_estimated_cost"] - 0.0018) < 1e-12
    assert cost["profile_route_estimated_cost"] > cost["session_estimated_cost"]


def test_current_session_cost_unavailable_without_session_id(tmp_path: Path) -> None:
    store = proxy_app.SQLiteResponseStore(tmp_path / "usage.sqlite3")
    store.record_usage(
        response_id="r1",
        previous_response_id=None,
        model="deepseek-v4-pro",
        thinking_enabled=True,
        usage_numbers={"prompt_tokens": 100, "completion_tokens": 5, "total_tokens": 105, "cached_tokens": 20, "reasoning_tokens": 0},
        estimated_cost_usd=0.0,
        estimated_cost_source_amount=0.0014,
        estimated_cost_source_currency="CNY",
        estimated_cost_display_amount=0.0014,
        estimated_cost_display_currency="CNY",
        purpose="primary",
        request_id="req1",
        session_id="s1",
    )
    tokens = proxy_app._weclaw_tokens_contract(store, profile="cox")
    cost = proxy_app._weclaw_cost_contract(tokens, {"available": True, "display_currency": "CNY", "is_stale": False}, None)
    assert cost["available"] is False
    assert cost["scope"] == "unavailable"
    assert cost["session"]["available"] is False
    assert cost["session_estimated_cost"] is None
    assert cost["profile_route_estimated_cost"] is not None


def test_prompt_segmentation_is_not_reused_across_sessions(tmp_path: Path) -> None:
    store = proxy_app.SQLiteResponseStore(tmp_path / "usage.sqlite3")
    store.record_usage(
        response_id="r-new",
        previous_response_id=None,
        model="deepseek-v4-pro",
        thinking_enabled=True,
        usage_numbers={"prompt_tokens": 120, "completion_tokens": 5, "total_tokens": 125, "cached_tokens": 10, "reasoning_tokens": 0},
        estimated_cost_usd=0.0,
        estimated_cost_source_amount=0.001,
        estimated_cost_source_currency="CNY",
        purpose="primary",
        request_id="req-new",
        session_id="new-session",
    )
    old_report = {
        "available": True,
        "session_id": "old-session",
        "tokenizer": {"available": True, "source_kind": "managed", "tokenizer_kind": "deepseek", "source": "test"},
        "summary": {"available": True},
        "prompt_subcategory_split": {
            "available": True,
            "categories": {"user": {"tokens": 999}},
            "latest_prompt_segmentation": {"available": True, "session_id": "old-session"},
        },
    }

    tokens = proxy_app._weclaw_tokens_contract(
        store,
        profile="cox",
        profile_tokenizer_report=old_report,
        profile_model="deepseek-v4-pro",
        provider="deepseek",
        session_id="new-session",
    )

    split = tokens["prompt_subcategory_split"]
    assert split["available"] is False
    assert split["reason"] == "session_scoped_prompt_segmentation_not_observed"
    assert split["session_id"] == "new-session"
    assert split["observed_session_id"] == "old-session"



def test_runtime_payload_guard_progress_is_information_retention() -> None:
    guard = proxy_app._runtime_payload_guard_contract(
        {
            "compaction": {"config": {"enabled": True, "policy": "adaptive", "trigger_chars": 1000, "target_chars": 400, "keep_recent_messages": 24}, "last_report": {}},
            "trimming": {"config": {"max_context_chars": 2000, "max_tool_output_chars": 120000, "keep_recent_messages": 24}, "last_report": {}},
        },
        compaction_report={"before_chars": 1000, "after_chars": 250, "chars_removed": 750, "observed_at": "2026-05-19T00:00:00Z", "policy_decision": {"effective_trigger_chars": 1000, "effective_target_chars": 400}, "compacted": True},
        trimming_report={"before_chars": 800, "after_chars": 600, "chars_removed": 200, "max_context_chars": 2000, "observed_at": "2026-05-19T00:00:01Z", "trimmed": True},
    )
    dumped = repr(guard)

    assert guard["unit"] == "tokens"
    assert guard["current_tokens"] is None
    assert guard["compaction"]["unit"] == "tokens"
    assert guard["compaction"]["available"] is False
    assert guard["trimming"]["unit"] == "tokens"
    assert guard["trimming"]["available"] is False
    assert "legacy_char_debug" not in dumped
    assert "char_control_scope" not in dumped
    assert "before_chars" not in dumped
    assert "after_chars" not in dumped
    assert "chars_removed" not in dumped
    assert "trigger_chars" not in dumped
    assert "target_chars" not in dumped
    assert "max_context_chars" not in dumped
