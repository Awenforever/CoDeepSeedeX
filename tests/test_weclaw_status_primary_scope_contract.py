
from __future__ import annotations

from pathlib import Path

import importlib

proxy_app = importlib.import_module("deepseek_responses_proxy.app")


def test_usage_events_support_session_id_filter(tmp_path: Path) -> None:
    store = proxy_app.SQLiteResponseStore(tmp_path / "usage.sqlite3")
    store.record_usage(
        response_id="r1",
        previous_response_id=None,
        model="deepseek-v4-flash",
        thinking_enabled=True,
        usage_numbers={"prompt_tokens": 100, "completion_tokens": 5, "total_tokens": 105, "cached_tokens": 80, "reasoning_tokens": 0},
        estimated_cost_usd=0.0,
        purpose="primary",
        request_id="req1",
        session_id="s1",
    )
    store.record_usage(
        response_id="r2",
        previous_response_id="r1",
        model="deepseek-v4-flash",
        thinking_enabled=True,
        usage_numbers={"prompt_tokens": 200, "completion_tokens": 5, "total_tokens": 205, "cached_tokens": 100, "reasoning_tokens": 0},
        estimated_cost_usd=0.0,
        purpose="primary",
        request_id="req2",
        session_id="s2",
    )
    assert store.usage_summary(thinking=True, session_id="s1")["prompt_tokens"] == 100
    assert store.usage_summary(thinking=True, session_id="s2")["prompt_tokens"] == 200
    assert store.usage_events(thinking=True, session_id="s2")[0]["session_id"] == "s2"


def test_weclaw_tokens_contract_separates_latest_primary_from_auxiliary(tmp_path: Path) -> None:
    store = proxy_app.SQLiteResponseStore(tmp_path / "usage.sqlite3")
    store.record_usage(
        response_id="r2",
        previous_response_id=None,
        model="deepseek-v4-flash",
        thinking_enabled=True,
        usage_numbers={"prompt_tokens": 200, "completion_tokens": 5, "total_tokens": 205, "cached_tokens": 100, "reasoning_tokens": 0},
        estimated_cost_usd=0.0,
        purpose="primary",
        request_id="req2",
        session_id="s2",
    )
    store.record_usage(
        response_id="r2",
        previous_response_id=None,
        model="deepseek-v4-flash",
        thinking_enabled=True,
        usage_numbers={"prompt_tokens": 50, "completion_tokens": 1, "total_tokens": 51, "cached_tokens": 40, "reasoning_tokens": 0},
        estimated_cost_usd=0.0,
        purpose="liveness_judge",
        request_id="req2",
        session_id="s2",
    )
    tokens = proxy_app._weclaw_tokens_contract(store, profile="deepseek-thinking", session_id="s2")
    assert tokens["session"]["available"] is True
    assert tokens["session"]["summary"]["prompt_tokens"] == 250
    assert tokens["latest_primary_turn"]["summary"]["prompt_tokens"] == 200
    assert tokens["latest_any_model_call"]["summary"]["prompt_tokens"] == 250
    assert tokens["latest_auxiliary_call"]["summary"]["prompt_tokens"] == 50
    assert tokens["last_turn"]["summary"]["prompt_tokens"] == 200
    context = proxy_app._weclaw_context_window_with_usage_estimate({"display_limit_tokens": 1000}, tokens)
    assert context["used_tokens"] == 200
    assert context["latest_upstream_prompt_tokens"]["purpose"] == "primary"


def test_runtime_payload_guard_progress_fields() -> None:
    guard = proxy_app._runtime_payload_guard_contract(
        {
            "compaction": {"config": {"enabled": True, "policy": "adaptive", "trigger_chars": 900000, "target_chars": 280000}, "last_report": {}},
            "trimming": {"config": {"max_context_chars": 1500000, "keep_recent_messages": 24}, "last_report": {}},
        },
        compaction_report={"before_chars": 120000, "after_chars": 80000, "chars_removed": 40000, "policy_decision": {"effective_trigger_chars": 900000}, "compacted": True},
        trimming_report={"before_chars": 95000, "after_chars": 90000, "chars_removed": 5000, "max_context_chars": 1500000, "trimmed": True},
    )
    assert guard["compaction"]["progress_numerator_chars"] == 120000
    assert guard["compaction"]["progress_denominator_chars"] == 900000
    assert guard["compaction"]["progress_basis"] == "raw_uncompressed_current_chars_over_trigger_chars"
    assert guard["trimming"]["progress_numerator_chars"] == 95000
    assert guard["trimming"]["progress_basis"] == "raw_uncompressed_current_chars_over_max_context_chars"
