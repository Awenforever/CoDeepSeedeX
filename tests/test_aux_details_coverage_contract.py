
from __future__ import annotations

import importlib
from pathlib import Path

proxy_app = importlib.import_module("deepseek_responses_proxy.app")


def test_current_session_auxiliary_model_calls_returns_zero_object_when_absent(tmp_path: Path) -> None:
    store = proxy_app.SQLiteResponseStore(tmp_path / "usage.sqlite3")
    store.record_usage(
        response_id="r1",
        previous_response_id=None,
        model="deepseek-v4-pro",
        thinking_enabled=True,
        usage_numbers={
            "prompt_tokens": 21600,
            "completion_tokens": 31,
            "total_tokens": 21631,
            "cached_tokens": 21504,
            "reasoning_tokens": 37,
        },
        estimated_cost_usd=0.0,
        estimated_cost_source_amount=0.000596,
        estimated_cost_source_currency="CNY",
        purpose="primary",
        request_id="req1",
        session_id="s1",
    )

    tokens = proxy_app._weclaw_tokens_contract(store, profile="deepseek-thinking", session_id="s1")
    aux = tokens["auxiliary_model_calls"]

    assert aux["available"] is True
    assert aux["scope"] == "current_session"
    assert aux["ledger_scope"] == "current_session"
    assert aux["unit"] == "tokens"
    assert aux["total_tokens"] == 0
    assert aux["summary"]["total_tokens"] == 0
    assert aux["model_call_count"] == 0
    assert aux["reason"] == "no_auxiliary_model_call_in_current_session"


def test_prompt_subcategory_split_exposes_provider_coverage_and_delta(tmp_path: Path) -> None:
    store = proxy_app.SQLiteResponseStore(tmp_path / "usage.sqlite3")
    store.record_usage(
        response_id="r1",
        previous_response_id=None,
        model="deepseek-v4-pro",
        thinking_enabled=True,
        usage_numbers={
            "prompt_tokens": 21592,
            "completion_tokens": 39,
            "total_tokens": 21631,
            "cached_tokens": 21504,
            "reasoning_tokens": 37,
        },
        estimated_cost_usd=0.0,
        purpose="primary",
        request_id="req1",
        session_id="s1",
    )
    report = {
        "available": True,
        "session_id": "s1",
        "scope": "current_session",
        "tokenizer": {
            "available": True,
            "source_kind": "managed",
            "tokenizer_kind": "deepseek_official_current",
            "source": "test-tokenizer",
        },
        "summary": {"available": True, "total_content_tokens": 13545},
        "prompt_subcategory_split": {
            "available": True,
            "scope": "current_session",
            "session_id": "s1",
            "unit": "tokens",
            "is_estimated": True,
            "precision": "local_profile_tokenizer_estimate",
            "semantic_scope": "message_content_and_tool_call_arguments_after_dsproxy_payload_assembly",
            "categories": {
                "user": {"tokens": 3},
                "assistant_history": {"tokens": 0},
                "tool_output": {"tokens": 0},
                "system": {"tokens": 8285},
                "developer": {"tokens": 0},
                "compaction_summary": {"tokens": 0},
                "environment": {"tokens": 5257},
                "runtime_injected": {"tokens": 0},
                "other_prompt": {"tokens": 0},
            },
            "total_tokens": 13545,
            "latest_prompt_segmentation": {"available": True, "session_id": "s1"},
        },
    }

    tokens = proxy_app._weclaw_tokens_contract(
        store,
        profile="deepseek-thinking",
        profile_tokenizer_report=report,
        profile_model="deepseek-v4-pro",
        provider="deepseek",
        session_id="s1",
    )
    split = tokens["prompt_subcategory_split"]

    assert split["available"] is True
    assert split["scope"] == "current_session"
    assert split["session_id"] == "s1"
    assert split["categories_sum_tokens"] == 13545
    assert split["provider_reference_tokens"] == 21592
    assert split["provider_reference_field"] == "latest_primary_turn.summary.prompt_tokens"
    assert split["delta_tokens"] == 8047
    assert split["coverage_complete"] is False
    assert split["coverage_scope"] == "local_profile_tokenizer_message_content_only"
    assert split["coverage_basis"] == "message_content_and_tool_call_arguments_after_dsproxy_payload_assembly"
    assert split["delta_reason"] == "provider_prompt_tokens_include_chat_template_or_provider_overhead_not_assigned_to_prompt_subcategories"


def test_prompt_subcategory_split_marks_complete_when_local_sum_matches_provider_prompt(tmp_path: Path) -> None:
    store = proxy_app.SQLiteResponseStore(tmp_path / "usage.sqlite3")
    store.record_usage(
        response_id="r1",
        previous_response_id=None,
        model="deepseek-v4-flash",
        thinking_enabled=True,
        usage_numbers={"prompt_tokens": 11, "completion_tokens": 1, "total_tokens": 12, "cached_tokens": 0, "reasoning_tokens": 0},
        estimated_cost_usd=0.0,
        purpose="primary",
        request_id="req1",
        session_id="s1",
    )
    report = {
        "available": True,
        "session_id": "s1",
        "scope": "current_session",
        "tokenizer": {"available": True, "source_kind": "managed", "tokenizer_kind": "deepseek_official_current", "source": "test"},
        "summary": {"available": True, "total_content_tokens": 11},
        "prompt_subcategory_split": {
            "available": True,
            "scope": "current_session",
            "session_id": "s1",
            "unit": "tokens",
            "is_estimated": True,
            "precision": "local_profile_tokenizer_estimate",
            "semantic_scope": "message_content_and_tool_call_arguments_after_dsproxy_payload_assembly",
            "categories": {"user": {"tokens": 3}, "system": {"tokens": 8}},
            "total_tokens": 11,
        },
    }

    tokens = proxy_app._weclaw_tokens_contract(
        store,
        profile="deepseek-thinking",
        profile_tokenizer_report=report,
        profile_model="deepseek-v4-flash",
        provider="deepseek",
        session_id="s1",
    )
    split = tokens["prompt_subcategory_split"]

    assert split["categories_sum_tokens"] == 11
    assert split["provider_reference_tokens"] == 11
    assert split["delta_tokens"] == 0
    assert split["coverage_complete"] is True
    assert split["delta_reason"] is None
