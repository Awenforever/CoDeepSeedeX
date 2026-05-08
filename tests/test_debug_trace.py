import importlib
import json
from pathlib import Path

proxy_app = importlib.import_module("deepseek_responses_proxy.app")


def test_debug_trace_disabled_by_default(monkeypatch, tmp_path):
    monkeypatch.delenv("DEEPSEEK_PROXY_DEBUG_TRACE", raising=False)
    monkeypatch.setenv("DEEPSEEK_PROXY_DEBUG_DIR", str(tmp_path / "traces"))

    proxy_app._debug_trace_event("resp_disabled", "request_received", payload={"input": "hello"})

    assert not (tmp_path / "traces").exists()
    status = proxy_app._debug_trace_status()
    assert status["enabled"] is False
    assert status["trace_count"] == 0


def test_debug_trace_none_mode_summarizes_without_raw_content(monkeypatch, tmp_path):
    trace_dir = tmp_path / "traces"
    monkeypatch.setenv("DEEPSEEK_PROXY_DEBUG_TRACE", "1")
    monkeypatch.setenv("DEEPSEEK_PROXY_DEBUG_DIR", str(trace_dir))
    monkeypatch.setenv("DEEPSEEK_PROXY_DEBUG_CONTENT", "none")

    proxy_app._debug_trace_event(
        "resp_unit",
        "request_received",
        payload={"input": "secret-ish content should not appear verbatim"},
        message_count=12,
        before_chars=3456,
        compacted=False,
        reason="not_triggered",
        usage={
            "prompt_tokens": 100,
            "completion_tokens": 20,
            "cached_tokens": 80,
            "reasoning_tokens": 5,
            "total_tokens": 120,
        },
    )

    trace_file = trace_dir / "trace-resp_unit.jsonl"
    assert trace_file.exists()
    raw = trace_file.read_text(encoding="utf-8")
    assert "secret-ish content" not in raw

    event = json.loads(raw.splitlines()[0])
    assert event["event"] == "request_received"
    assert event["response_id"] == "resp_unit"
    assert event["version"] == proxy_app.PROXY_VERSION
    assert event["payload"]["input"]["label"] == "input"
    assert event["payload"]["input"]["type"] == "str"
    assert event["payload"]["input"]["chars"] > 0
    assert event["message_count"] == 12
    assert event["before_chars"] == 3456
    assert event["compacted"] is False
    assert event["reason"] == "not_triggered"
    assert event["usage"]["prompt_tokens"] == 100
    assert event["usage"]["cached_tokens"] == 80


def test_debug_trace_preview_mode_redacts_secret_like_keys(monkeypatch, tmp_path):
    trace_dir = tmp_path / "traces"
    monkeypatch.setenv("DEEPSEEK_PROXY_DEBUG_TRACE", "1")
    monkeypatch.setenv("DEEPSEEK_PROXY_DEBUG_DIR", str(trace_dir))
    monkeypatch.setenv("DEEPSEEK_PROXY_DEBUG_CONTENT", "preview")

    proxy_app._debug_trace_event(
        "resp_preview",
        "upstream_call_started",
        headers={"Authorization": "Bearer should-not-leak"},
        payload={"messages": [{"role": "user", "content": "hello"}]},
    )

    raw = (trace_dir / "trace-resp_preview.jsonl").read_text(encoding="utf-8")
    assert "should-not-leak" not in raw
    assert "Bearer should-not-leak" not in raw

    event = json.loads(raw.splitlines()[0])
    assert event["headers"]["Authorization"] == "[redacted]"
    assert event["payload"]["messages"]["label"] == "messages"


def test_debug_trace_latest_returns_recent_events(monkeypatch, tmp_path):
    trace_dir = tmp_path / "traces"
    monkeypatch.setenv("DEEPSEEK_PROXY_DEBUG_TRACE", "1")
    monkeypatch.setenv("DEEPSEEK_PROXY_DEBUG_DIR", str(trace_dir))
    monkeypatch.setenv("DEEPSEEK_PROXY_DEBUG_CONTENT", "none")

    proxy_app._debug_trace_event("resp_latest", "request_received", payload={"input": "a"})
    proxy_app._debug_trace_event("resp_latest", "response_envelope_built", output_item_count=1)

    latest = proxy_app._debug_trace_latest(limit=10)
    assert latest["status"] == "ok"
    assert latest["trace_path"].endswith("trace-resp_latest.jsonl")
    assert [event["event"] for event in latest["events"]] == [
        "request_received",
        "response_envelope_built",
    ]

    status = proxy_app._debug_trace_status()
    assert status["enabled"] is True
    assert status["trace_count"] == 1
    assert status["latest"]["response_id"] == "resp_latest"


def test_debug_trace_sanitizes_response_id(monkeypatch, tmp_path):
    trace_dir = tmp_path / "traces"
    monkeypatch.setenv("DEEPSEEK_PROXY_DEBUG_TRACE", "1")
    monkeypatch.setenv("DEEPSEEK_PROXY_DEBUG_DIR", str(trace_dir))
    monkeypatch.setenv("DEEPSEEK_PROXY_DEBUG_CONTENT", "none")

    proxy_app._debug_trace_event("resp/unsafe value", "request_received")

    files = sorted(path.name for path in trace_dir.glob("trace-*.jsonl"))
    assert files == ["trace-resp_unsafe_value.jsonl"]

def test_debug_trace_none_mode_preserves_compaction_metadata(monkeypatch, tmp_path):
    trace_dir = tmp_path / "traces"
    monkeypatch.setenv("DEEPSEEK_PROXY_DEBUG_TRACE", "1")
    monkeypatch.setenv("DEEPSEEK_PROXY_DEBUG_DIR", str(trace_dir))
    monkeypatch.setenv("DEEPSEEK_PROXY_DEBUG_CONTENT", "none")

    proxy_app._debug_trace_event(
        "resp_compaction",
        "compaction_finished",
        compacted=True,
        reason="adaptive_triggered",
        policy="adaptive",
        before_chars=1234567,
        after_chars=345678,
        chars_removed=888889,
        message_count_before=88,
        message_count_after=25,
        policy_decision={
            "policy": "adaptive",
            "should_compact": True,
            "reason": "adaptive_triggered",
            "effective_trigger_chars": 900000,
            "effective_target_chars": 350000,
        },
    )

    event = json.loads((trace_dir / "trace-resp_compaction.jsonl").read_text(encoding="utf-8"))
    assert event["event"] == "compaction_finished"
    assert event["compacted"] is True
    assert event["reason"] == "adaptive_triggered"
    assert event["policy"] == "adaptive"
    assert event["before_chars"] == 1234567
    assert event["after_chars"] == 345678
    assert event["chars_removed"] == 888889
    assert event["policy_decision"]["should_compact"] is True
    assert event["policy_decision"]["effective_trigger_chars"] == 900000


def test_context_budget_breakdown_splits_tools_messages_and_compaction():
    request_payload = {
        "input": [{"role": "user", "content": "hello"}],
        "tools": [{"type": "function", "function": {"name": "raw_tool"}}],
    }
    deepseek_tools = [{"type": "function", "function": {"name": "normalized_tool"}}]
    messages_before = [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "answer"},
    ]
    messages_after = messages_before[1:]
    messages_for_deepseek = messages_after + [{"role": "tool", "content": "tool-output"}]
    chat_payload = {
        "model": "deepseek-v4-flash",
        "messages": messages_for_deepseek,
        "tools": deepseek_tools,
    }
    report = {
        "compacted": False,
        "reason": "not_triggered",
        "policy": "adaptive",
        "before_chars": 1000,
        "after_chars": 1000,
        "chars_removed": None,
        "message_count_before": 3,
        "message_count_after": 2,
        "policy_decision": {
            "effective_trigger_chars": 1250000,
            "effective_target_chars": 750000,
            "emergency_chars": 1380000,
            "min_new_chars": 250000,
            "min_turns": 4,
            "growth": {"turns_since_last_compaction": 3},
        },
    }

    budget = proxy_app._context_budget_breakdown(
        request_payload=request_payload,
        input_value=request_payload["input"],
        messages_before_compaction=messages_before,
        messages_after_compaction=messages_after,
        messages_for_deepseek=messages_for_deepseek,
        deepseek_tools=deepseek_tools,
        chat_payload=chat_payload,
        context_compaction_report=report,
    )

    assert budget["raw_tool_count"] == 1
    assert budget["normalized_tool_count"] == 1
    assert budget["chat_payload_tool_count"] == 1
    assert budget["messages_before_compaction"]["message_count"] == 3
    assert budget["messages_before_compaction"]["roles"]["system"]["count"] == 1
    assert budget["messages_for_deepseek"]["roles"]["tool"]["count"] == 1
    assert budget["compaction"]["reason"] == "not_triggered"
    assert budget["compaction"]["effective_trigger_chars"] == 1250000


def test_tool_output_budget_breakdown_identifies_largest_outputs(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_PROXY_TOOL_OUTPUT_BUDGET_LARGEST_ITEMS", "2")
    monkeypatch.setenv("DEEPSEEK_PROXY_TOOL_OUTPUT_WARN_ITEM_CHARS", "100")
    monkeypatch.setenv("DEEPSEEK_PROXY_TOOL_OUTPUT_WARN_TOTAL_CHARS", "150")

    input_items = [
        {
            "type": "function_call",
            "call_id": "call_1",
            "name": "shell",
            "arguments": "{\"cmd\":\"pytest\"}",
        },
        {
            "type": "function_call_output",
            "call_id": "call_1",
            "output": "x" * 200,
        },
        {
            "type": "function_call",
            "call_id": "call_2",
            "name": "read_file",
            "arguments": "{\"path\":\"a.txt\"}",
        },
        {
            "type": "function_call_output",
            "call_id": "call_2",
            "output": "small",
        },
    ]

    budget = proxy_app._tool_output_budget_breakdown(input_items)

    assert budget["function_call_count"] == 2
    assert budget["function_call_output_count"] == 2
    assert budget["function_call_output_chars"] > 200
    assert budget["function_call_output_payload_chars"] > 200
    assert budget["large_output_count"] >= 1
    assert budget["total_output_exceeds_warn_total"] is True
    assert budget["largest_outputs"][0]["call_id"] == "call_1"
    assert budget["largest_outputs"][0]["tool_name"] == "shell"
    assert budget["largest_outputs"][0]["exceeds_warn_item_chars"] is True
    assert len(budget["largest_outputs"]) == 2
