
from __future__ import annotations

import json

from pathlib import Path

import importlib

proxy_app = importlib.import_module("codexchange_proxy.app")


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
    tokens = proxy_app._weclaw_tokens_contract(store, profile="cox", session_id="s2")
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
    dumped = json.dumps(guard, sort_keys=True)

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


def test_token_only_public_runtime_contract_filters_non_token_diagnostics_recursively() -> None:
    payload = {
        "runtime_payload_guard": {
            "unit": "tokens",
            "current_tokens": 42,
            "current_chars": 999,
            "compaction": {
                "unit": "tokens",
                "before_chars": 1000,
                "char_count": 1000,
                "tokens_removed": 12,
                "last_report": {
                    "compact_audit": {
                        "unit": "chars/messages",
                        "classifier_dry_run": {
                            "sections": {
                                "compaction_material": {"chars": 10},
                            },
                        },
                    },
                },
            },
        },
        "tokens": {
            "latest_prompt_segmentation": {
                "segments": [
                    {"index": 0, "token_count": 5, "char_count": 20, "content_chars": 20},
                ],
                "observable_payload": {
                    "components": {"messages_json": {"local_tokens": 5, "char_count": 20}},
                    "precision": "char_heuristic_estimate",
                },
            },
        },
    }
    cleaned = proxy_app._token_only_public_runtime_contract(payload)
    dumped = json.dumps(cleaned, sort_keys=True)

    assert cleaned["runtime_payload_guard"]["current_tokens"] == 42
    assert cleaned["runtime_payload_guard"]["compaction"]["tokens_removed"] == 12
    for forbidden in (
        "legacy_char_debug",
        "char_control_scope",
        "before_chars",
        "after_chars",
        "chars_removed",
        "trigger_chars",
        "target_chars",
        "max_context_chars",
        "current_chars",
        "char_count",
        "content_chars",
        '"chars"',
        "char_heuristic",
        "chars/messages",
    ):
        assert forbidden not in dumped
