import importlib

app = importlib.import_module("codexchange_proxy.app")


def _pytest_success_with_negated_failure_words(extra_chars: int = 5000) -> str:
    return (
        "assistant_requested_tool_calls:\n"
        "tool_outputs:\n"
        "===== pytest =====\n"
        "============================= test session starts =============================\n"
        "platform linux -- Python 3.11.9, pytest-8.3.5\n"
        "collected 4 items\n"
        "tests/test_semantic_probe.py::test_case_001 PASSED [25%]\n"
        "tests/test_semantic_probe.py::test_case_002 PASSED [50%]\n"
        "tests/test_semantic_probe.py::test_case_003 PASSED [75%]\n"
        "tests/test_semantic_probe.py::test_case_004 PASSED [100%]\n"
        "============================= 4 passed in 0.10s =============================\n"
        "pytest_success_marker: all tests passed, no failures, no traceback, no diff, no patch\n"
        + ("x" * extra_chars)
    )


def test_negated_failure_words_do_not_turn_pytest_success_into_failure() -> None:
    text = _pytest_success_with_negated_failure_words()
    semantic_type = app._classify_flattened_tool_transcript_semantic_type(text)
    markers = app._flattened_tool_transcript_retention_markers(text)
    risk = app._flattened_tool_transcript_semantic_risk(
        semantic_type,
        markers,
        text_chars=len(text),
    )
    plan_type = app._semantic_payload_plan_type_alias(semantic_type, markers, text)

    target = {
        "index": 1,
        "role": "user",
        "history_category": "flattened_tool_transcript",
        "chars": len(text),
        "text_chars": len(text),
        "semantic_type": semantic_type,
        "semantic_plan_type": plan_type,
        "semantic_risk": risk,
        "risk_level": risk,
        "retention_markers": markers,
    }
    decision = app._semantic_compaction_policy_for_flattened_tool_target(
        target,
        summary_chars=900,
    )

    assert semantic_type == "test_output"
    assert "FAILED" not in markers
    assert "Traceback" not in markers
    assert risk == "low"
    assert plan_type == "pytest_success"
    assert decision["policy_decision"] == "compact"
    assert decision["recommended_action"] == "compact_test_output_summary"
    assert app._semantic_payload_safety_core_allows_compaction(decision) is True


def test_semantic_payload_compacts_old_low_risk_pytest_success(monkeypatch) -> None:
    monkeypatch.setenv("COX_FLATTENED_TOOL_SEMANTIC_PAYLOAD_CANARY_ALLOW_ENABLED", "1")
    monkeypatch.setenv("COX_FLATTENED_TOOL_SEMANTIC_PAYLOAD_COMPACTION_MODE", "enabled")
    monkeypatch.setenv("COX_FLATTENED_TOOL_SEMANTIC_PAYLOAD_COMPACTION_PRESERVE_RECENT_MESSAGES", "20")
    monkeypatch.setenv("COX_FLATTENED_TOOL_SEMANTIC_PAYLOAD_COMPACTION_MIN_MESSAGE_CHARS", "100")
    monkeypatch.setenv("COX_FLATTENED_TOOL_SEMANTIC_PAYLOAD_COMPACTION_SUMMARY_CHARS", "900")

    old_low_risk = {
        "role": "user",
        "content": _pytest_success_with_negated_failure_words(extra_chars=8000),
    }
    messages = [
        {"role": "user", "content": "ordinary instruction before tool output"},
        old_low_risk,
    ]
    for i in range(23):
        messages.append({"role": "user", "content": f"recent ordinary user message {i:02d}"})

    compacted_messages, report = app._apply_flattened_tool_transcript_semantic_payload_compaction(messages)

    assert compacted_messages is not messages
    assert report["applied"] is True
    assert report["compacted_count"] == 1
    assert report["candidate_count"] >= 1
    assert report["eligible_policy_count"] == 1
    assert report["tokens_removed"] > 0
    assert report["semantic_plan_types"] == {"pytest_success": 1}
    assert report["risk_counts"] == {"low": 1}
    assert "[semantic flattened tool transcript compacted by CodeXchange]" in compacted_messages[1]["content"]
    assert "semantic_risk: low" in compacted_messages[1]["content"]
