
from __future__ import annotations

import importlib
from pathlib import Path

proxy_app = importlib.import_module("deepseek_responses_proxy.app")


def _record_primary_usage(store: object, *, prompt_tokens: int, total_tokens: int, session_id: str = "s1") -> None:
    store.record_usage(
        response_id="r1",
        previous_response_id=None,
        model="deepseek-v4-pro",
        thinking_enabled=True,
        usage_numbers={
            "prompt_tokens": prompt_tokens,
            "completion_tokens": max(0, total_tokens - prompt_tokens),
            "total_tokens": total_tokens,
            "cached_tokens": 0,
            "reasoning_tokens": 0,
        },
        estimated_cost_usd=0.0,
        purpose="primary",
        request_id="req1",
        session_id=session_id,
    )


def test_prompt_reconciliation_exposes_unexplained_provider_delta_without_assigning_to_other(tmp_path: Path) -> None:
    store = proxy_app.SQLiteResponseStore(tmp_path / "usage.sqlite3")
    _record_primary_usage(store, prompt_tokens=21592, total_tokens=21631)

    report = {
        "available": True,
        "session_id": "s1",
        "scope": "current_session",
        "tokenizer": {"available": True, "source_kind": "managed", "tokenizer_kind": "deepseek_official_current", "source": "test"},
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
            "latest_prompt_segmentation": {
                "available": True,
                "session_id": "s1",
                "total_prompt_tokens_profile_tokenizer": 13545,
                "segments": [
                    {"index": 0, "category": "system", "source": "system", "role": "system", "char_count": 1234, "token_count": 8285, "sha256": "s", "preview": "sys"},
                    {"index": 1, "category": "environment", "source": "environment", "role": "user", "char_count": 567, "token_count": 5257, "sha256": "e", "preview": "env"},
                    {"index": 2, "category": "user", "source": "codex_request", "role": "user", "char_count": 2, "token_count": 3, "sha256": "u", "preview": "ok"},
                ],
            },
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
    reconciliation = tokens["prompt_reconciliation"]

    assert split["categories_sum_tokens"] == 13545
    assert split["provider_reference_tokens"] == 21592
    assert split["delta_tokens"] == 8047
    assert split["coverage_complete"] is False

    assert reconciliation["available"] is True
    assert reconciliation["scope"] == "current_session"
    assert reconciliation["session_id"] == "s1"
    assert reconciliation["request_id"] == "req1"
    assert reconciliation["provider_prompt_tokens"] == 21592
    assert reconciliation["provider_total_tokens"] == 21631
    assert reconciliation["local_categories_sum_tokens"] == 13545
    assert reconciliation["local_full_observed_prompt_tokens"] == 13545
    assert reconciliation["delta_tokens"] == 8047
    assert reconciliation["delta_breakdown"]["unclassified_observed_segments_tokens"] == 0
    assert reconciliation["delta_breakdown"]["unknown_tokens"] == 8047
    assert reconciliation["delta_status"] == "unexplained_after_observable_payload_accounting"
    assert reconciliation["is_accounting_suspect"] is True
    assert reconciliation["recommended_action"] == "run_prompt_reconciliation_trace"
    assert reconciliation["prompt_segment_audit"]["segment_categories_sum_tokens"] == 13545
    assert reconciliation["prompt_segment_audit"]["unclassified_segments"] == []


def test_prompt_reconciliation_distinguishes_unclassified_observed_segments_from_unknown_provider_delta(tmp_path: Path) -> None:
    store = proxy_app.SQLiteResponseStore(tmp_path / "usage.sqlite3")
    _record_primary_usage(store, prompt_tokens=10, total_tokens=12)

    report = {
        "available": True,
        "session_id": "s1",
        "scope": "current_session",
        "tokenizer": {"available": True, "source_kind": "managed", "tokenizer_kind": "deepseek_official_current", "source": "test"},
        "summary": {"available": True, "total_content_tokens": 8},
        "prompt_subcategory_split": {
            "available": True,
            "scope": "current_session",
            "session_id": "s1",
            "unit": "tokens",
            "is_estimated": True,
            "precision": "local_profile_tokenizer_estimate",
            "semantic_scope": "message_content_and_tool_call_arguments_after_dsproxy_payload_assembly",
            "categories": {"user": {"tokens": 5}},
            "total_tokens": 8,
            "latest_prompt_segmentation": {
                "available": True,
                "session_id": "s1",
                "total_prompt_tokens_profile_tokenizer": 8,
                "segments": [
                    {"index": 0, "category": "user", "source": "codex_request", "role": "user", "char_count": 2, "token_count": 5, "sha256": "u", "preview": "ok"},
                    {"index": 1, "category": "unclassified", "source": "unknown", "role": "user", "char_count": 9, "token_count": 3, "sha256": "x", "preview": "unknown"},
                ],
            },
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
    reconciliation = tokens["prompt_reconciliation"]

    assert reconciliation["local_categories_sum_tokens"] == 5
    assert reconciliation["local_full_observed_prompt_tokens"] == 8
    assert reconciliation["provider_prompt_tokens"] == 10
    assert reconciliation["delta_tokens"] == 5
    assert reconciliation["delta_breakdown"]["unclassified_observed_segments_tokens"] == 3
    assert reconciliation["delta_breakdown"]["unknown_tokens"] == 2
    assert reconciliation["delta_status"] == "explained_by_observable_payload_accounting"
    assert reconciliation["is_accounting_suspect"] is False
    assert reconciliation["prompt_segment_audit"]["unclassified_segments_tokens"] == 3
    assert len(reconciliation["prompt_segment_audit"]["unclassified_segments"]) == 1


def test_prompt_reconciliation_marks_complete_when_provider_prompt_matches_local_categories(tmp_path: Path) -> None:
    store = proxy_app.SQLiteResponseStore(tmp_path / "usage.sqlite3")
    _record_primary_usage(store, prompt_tokens=11, total_tokens=12)

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
            "latest_prompt_segmentation": {
                "available": True,
                "session_id": "s1",
                "total_prompt_tokens_profile_tokenizer": 11,
                "segments": [
                    {"index": 0, "category": "system", "source": "system", "role": "system", "char_count": 20, "token_count": 8, "sha256": "s", "preview": "sys"},
                    {"index": 1, "category": "user", "source": "codex_request", "role": "user", "char_count": 2, "token_count": 3, "sha256": "u", "preview": "ok"},
                ],
            },
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
    reconciliation = tokens["prompt_reconciliation"]

    assert reconciliation["provider_prompt_tokens"] == 11
    assert reconciliation["local_categories_sum_tokens"] == 11
    assert reconciliation["local_full_observed_prompt_tokens"] == 11
    assert reconciliation["delta_tokens"] == 0
    assert reconciliation["delta_status"] == "explained"
    assert reconciliation["is_accounting_suspect"] is False
    assert reconciliation["can_provider_prompt_tokens_be_fully_decomposed_to_details"] is True


def test_prompt_reconciliation_explains_delta_with_observable_tool_schema_payload(tmp_path: Path) -> None:
    store = proxy_app.SQLiteResponseStore(tmp_path / "usage.sqlite3")
    _record_primary_usage(store, prompt_tokens=21600, total_tokens=21631)

    report = {
        "available": True,
        "session_id": "s1",
        "scope": "current_session",
        "tokenizer": {"available": True, "source_kind": "managed", "tokenizer_kind": "deepseek_official_current", "source": "test"},
        "summary": {"available": True, "total_content_tokens": 13500},
        "prompt_subcategory_split": {
            "available": True,
            "scope": "current_session",
            "session_id": "s1",
            "unit": "tokens",
            "is_estimated": True,
            "precision": "local_profile_tokenizer_estimate",
            "semantic_scope": "message_content_and_tool_call_arguments_after_dsproxy_payload_assembly",
            "categories": {"system": {"tokens": 8200}, "environment": {"tokens": 5295}, "user": {"tokens": 5}, "other_prompt": {"tokens": 0}},
            "total_tokens": 13500,
            "observable_payload": {
                "available": True,
                "semantic_prompt_candidate_tokens": 21600,
                "full_payload_json_tokens": 21880,
                "components": {
                    "message_content": {"local_tokens": 13500},
                    "tools_schema": {"local_tokens": 8100},
                    "tool_choice": {"local_tokens": 0},
                    "response_format": {"local_tokens": 0},
                    "request_options": {"local_tokens": 12},
                    "messages_json": {"local_tokens": 13620},
                },
            },
            "latest_prompt_segmentation": {
                "available": True,
                "session_id": "s1",
                "total_prompt_tokens_profile_tokenizer": 13500,
                "observable_payload": {
                    "available": True,
                    "semantic_prompt_candidate_tokens": 21600,
                    "full_payload_json_tokens": 21880,
                    "components": {
                        "message_content": {"local_tokens": 13500},
                        "tools_schema": {"local_tokens": 8100},
                        "tool_choice": {"local_tokens": 0},
                        "response_format": {"local_tokens": 0},
                        "request_options": {"local_tokens": 12},
                        "messages_json": {"local_tokens": 13620},
                    },
                },
                "segments": [
                    {"index": 0, "category": "system", "source": "system", "role": "system", "char_count": 20, "token_count": 8200, "sha256": "s", "preview": "sys"},
                    {"index": 1, "category": "environment", "source": "environment", "role": "user", "char_count": 20, "token_count": 5295, "sha256": "e", "preview": "env"},
                    {"index": 2, "category": "user", "source": "codex_request", "role": "user", "char_count": 2, "token_count": 5, "sha256": "u", "preview": "ok"},
                ],
            },
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
    reconciliation = tokens["prompt_reconciliation"]

    assert reconciliation["provider_prompt_tokens"] == 21600
    assert reconciliation["local_categories_sum_tokens"] == 13500
    assert reconciliation["local_full_observed_prompt_tokens"] == 21600
    assert reconciliation["delta_tokens"] == 8100
    assert reconciliation["delta_breakdown"]["tools_schema_tokens"] == 8100
    assert reconciliation["delta_breakdown"]["unknown_tokens"] == 0
    assert reconciliation["delta_status"] == "explained_by_observable_payload_accounting"
    assert reconciliation["root_cause_status"] == "tool_schema_and_message_protocol_overhead"
    assert reconciliation["dominant_observable_delta_source"] == "tools_schema"
    assert reconciliation["is_accounting_suspect"] is False


def test_details_origin_breakdown_exposes_sources_without_classified_subtotal(tmp_path: Path) -> None:
    store = proxy_app.SQLiteResponseStore(tmp_path / "usage.sqlite3")
    _record_primary_usage(store, prompt_tokens=21614, total_tokens=21653)

    report = {
        "available": True,
        "session_id": "s1",
        "scope": "current_session",
        "tokenizer": {"available": True, "source_kind": "managed", "tokenizer_kind": "deepseek_official_current", "source": "test"},
        "summary": {"available": True, "total_content_tokens": 13563},
        "prompt_subcategory_split": {
            "available": True,
            "scope": "current_session",
            "session_id": "s1",
            "unit": "tokens",
            "is_estimated": True,
            "precision": "local_profile_tokenizer_estimate",
            "semantic_scope": "message_content_and_tool_call_arguments_after_dsproxy_payload_assembly",
            "categories": {
                "user": {"tokens": 15},
                "assistant_history": {"tokens": 6},
                "user_history": {"tokens": 0},
                "tool_output": {"tokens": 0},
                "system": {"tokens": 8280},
                "developer": {"tokens": 0},
                "compaction_summary": {"tokens": 0},
                "environment": {"tokens": 5262},
                "runtime_injected": {"tokens": 0},
                "other_prompt": {"tokens": 0},
            },
            "total_tokens": 13563,
            "observable_payload": {
                "available": True,
                "semantic_prompt_candidate_tokens": 20938,
                "full_payload_json_tokens": 21637,
                "components": {
                    "message_content": {"local_tokens": 13563},
                    "messages_json": {"local_tokens": 14229},
                    "tools_schema": {"local_tokens": 7375},
                    "tool_choice": {"local_tokens": 0},
                    "response_format": {"local_tokens": 0},
                    "request_options": {"local_tokens": 30},
                },
            },
            "latest_prompt_segmentation": {
                "available": True,
                "session_id": "s1",
                "total_prompt_tokens_profile_tokenizer": 13563,
                "observable_payload": {
                    "available": True,
                    "semantic_prompt_candidate_tokens": 20938,
                    "full_payload_json_tokens": 21637,
                    "components": {
                        "message_content": {"local_tokens": 13563},
                        "messages_json": {"local_tokens": 14229},
                        "tools_schema": {"local_tokens": 7375},
                        "tool_choice": {"local_tokens": 0},
                        "response_format": {"local_tokens": 0},
                        "request_options": {"local_tokens": 30},
                    },
                },
                "segments": [
                    {"index": 0, "category": "system", "source": "system", "role": "system", "char_count": 20, "token_count": 8280, "sha256": "s", "preview": "sys"},
                    {"index": 1, "category": "environment", "source": "environment", "role": "user", "char_count": 20, "token_count": 5262, "sha256": "e", "preview": "env"},
                    {"index": 2, "category": "assistant_history", "source": "history", "role": "assistant", "char_count": 3, "token_count": 6, "sha256": "h", "preview": "old"},
                    {"index": 3, "category": "user", "source": "codex_request", "role": "user", "char_count": 2, "token_count": 15, "sha256": "u", "preview": "ok"},
                ],
            },
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
    reconciliation = tokens["prompt_reconciliation"]
    origin = reconciliation["details_origin_breakdown"]
    components = origin["components"]

    assert origin["should_display_classified_total"] is False
    assert "classified" not in origin["display_order"]
    assert components["user"]["tokens"] == 15
    assert components["history"]["tokens"] == 6
    assert components["system"]["tokens"] == 8280
    assert components["environment"]["tokens"] == 5262
    assert components["tools_schema"]["tokens"] == 7375
    assert components["message_protocol_overhead"]["tokens"] == 676
    assert components["provider_residual"]["abs_tokens"] <= origin["provider_residual_tolerance_tokens"]

    assert reconciliation["delta_tokens"] == 8051
    assert reconciliation["delta_status"] == "explained_by_observable_payload_accounting"
    assert reconciliation["root_cause_status"] == "tool_schema_and_message_protocol_overhead"
    assert reconciliation["dominant_observable_delta_source"] == "tools_schema"
    assert reconciliation["is_accounting_suspect"] is False


def test_details_origin_breakdown_unavailable_when_only_provider_residual_exists(tmp_path: Path) -> None:
    store = proxy_app.SQLiteResponseStore(tmp_path / "usage.sqlite3")
    _record_primary_usage(store, prompt_tokens=21600, total_tokens=21700)

    report = {
        "available": True,
        "session_id": "s1",
        "scope": "current_session",
        "tokenizer": {"available": True, "source_kind": "managed", "tokenizer_kind": "deepseek_official_current", "source": "test"},
        "summary": {"available": False, "reason": "no_observed_prompt"},
        "prompt_subcategory_split": {
            "available": False,
            "scope": "current_session",
            "session_id": "s1",
            "unit": "tokens",
            "precision": "local_profile_tokenizer_estimate",
            "reason": "profile_tokenizer_available_but_no_observed_prompt",
            "action": "send one model request through this route",
            "categories": {},
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

    origin = tokens["prompt_reconciliation"]["details_origin_breakdown"]
    assert origin["available"] is False
    assert origin["reason"] == "profile_tokenizer_available_but_no_observed_prompt"
    assert origin["provider_residual_display_allowed"] is False
    assert origin["origin_non_residual_tokens"] == 0
    assert origin["components"]["provider_residual"]["tokens"] == 21600
