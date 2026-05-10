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




def test_long_session_observability_report_aggregates_trace_files(monkeypatch, tmp_path):
    trace_dir = tmp_path / "traces"
    monkeypatch.setenv("DEEPSEEK_PROXY_DEBUG_TRACE", "1")
    monkeypatch.setenv("DEEPSEEK_PROXY_DEBUG_DIR", str(trace_dir))

    proxy_app._debug_trace_event(
        "resp_one",
        "context_budget_breakdown",
        chat_payload_chars=1000,
        message_count=10,
    )
    proxy_app._debug_trace_event(
        "resp_one",
        "flattened_tool_transcript_semantic_payload_compaction_applied",
        applied=False,
        mode="dry_run",
        reason="semantic_payload_compaction_mode_not_enabled",
        compacted_count=0,
        chars_removed=0,
    )
    proxy_app._debug_trace_event(
        "resp_two",
        "context_budget_breakdown",
        chat_payload_chars=2400,
        message_count=20,
    )
    proxy_app._debug_trace_event(
        "resp_two",
        "tool_output_budget_breakdown",
        function_call_output_chars=5000,
    )
    proxy_app._debug_trace_event(
        "resp_two",
        "upstream_call_finished",
        purpose="primary",
        usage={"prompt_tokens": 2500},
    )

    report = proxy_app._long_session_observability_report(limit=10, mode="aggregate")

    assert report["mode"] == "aggregate"
    assert report["trace_file_count"] == 2
    assert report["aggregate"]["scanned_trace_file_count"] == 2
    assert report["trace_event_count"] == 5
    assert report["response_count"] == 2
    assert report["context_budget"]["event_count"] == 2
    assert report["context_budget"]["latest_chars"] == 2400
    assert report["context_budget"]["growth_chars"] == 1400
    assert report["semantic_payload"]["event_count"] == 1
    assert report["tool_output_budget"]["event_count"] == 1
    assert report["primary_usage"]["latest_prompt_tokens"] == 2500
    assert report["recommendation"] == "continue_dry_run_observation"


def test_long_session_observability_report_latest_mode_uses_latest_trace(monkeypatch, tmp_path):
    trace_dir = tmp_path / "traces"
    monkeypatch.setenv("DEEPSEEK_PROXY_DEBUG_TRACE", "1")
    monkeypatch.setenv("DEEPSEEK_PROXY_DEBUG_DIR", str(trace_dir))

    proxy_app._debug_trace_event("resp_one", "context_budget_breakdown", chat_payload_chars=1000)
    proxy_app._debug_trace_event("resp_two", "context_budget_breakdown", chat_payload_chars=2400)

    report = proxy_app._long_session_observability_report(limit=10, mode="latest")

    assert report["mode"] == "latest"
    assert report["trace_file_count"] == 1
    assert report["trace_event_count"] == 1
    assert report["response_count"] == 1
    assert report["context_budget"]["latest_chars"] == 2400


def test_long_session_observability_from_events_summarizes_trends():
    events = [
        {"event": "context_budget_breakdown", "chat_payload_chars": 1000, "message_count": 10},
        {"event": "tool_output_budget_breakdown", "truncated_event": False},
        {
            "event": "flattened_tool_transcript_semantic_payload_compaction_applied",
            "applied": False,
            "mode": "dry_run",
            "reason": "semantic_payload_compaction_mode_not_enabled",
            "compacted_count": 0,
            "chars_removed": 0,
        },
        {
            "event": "upstream_call_finished",
            "purpose": "primary",
            "usage": {"prompt_tokens": 1200},
        },
        {"event": "context_budget_breakdown", "chat_payload_chars": 2400, "message_count": 20},
        {
            "event": "flattened_tool_transcript_semantic_payload_compaction_applied",
            "applied": True,
            "mode": "enabled",
            "compacted_count": 1,
            "chars_removed": 400,
        },
        {
            "event": "upstream_call_finished",
            "purpose": "primary",
            "usage": {"prompt_tokens": 2500},
        },
    ]

    report = proxy_app._long_session_observability_from_events(events, limit=50)

    assert report["status"] == "ok"
    assert report["kind"] == "runtime_long_session_observability"
    assert report["trace_event_count"] == 7
    assert report["context_budget"]["event_count"] == 2
    assert report["context_budget"]["latest_chars"] == 2400
    assert report["context_budget"]["max_chars"] == 2400
    assert report["context_budget"]["growth_chars"] == 1400
    assert report["semantic_payload"]["event_count"] == 2
    assert report["semantic_payload"]["applied_count"] == 1
    assert report["semantic_payload"]["compacted_count"] == 1
    assert report["semantic_payload"]["chars_removed"] == 400
    assert report["primary_usage"]["latest_prompt_tokens"] == 2500
    assert report["recommendation"] == "monitor_limited_enabled_session"


def test_long_session_observability_summarizes_tool_output_trim_events():
    events = [
        {"event": "context_budget_breakdown", "chat_payload_chars": 1000},
        {
            "event": "tool_output_trim_applied",
            "mode": "dry_run",
            "effective_mode": "dry_run",
            "enabled": False,
            "applied": False,
            "reason": "trim_mode_not_enabled",
            "trimmed_item_count": 0,
            "chars_removed": 0,
            "targets": [],
        },
        {
            "event": "tool_output_trim_applied",
            "mode": "enabled",
            "effective_mode": "enabled",
            "enabled": True,
            "applied": True,
            "reason": "enabled",
            "trimmed_item_count": 2,
            "chars_removed": 1117203,
            "targets": [
                {
                    "category": "image_payload",
                    "tool_name": "view_image",
                    "estimated_remove_chars": 1117000,
                },
                {
                    "category": "shell_command",
                    "tool_name": "exec_command",
                    "estimated_remove_chars": 203,
                },
            ],
        },
        {
            "event": "upstream_call_finished",
            "purpose": "primary",
            "usage": {"prompt_tokens": 2500},
        },
    ]

    report = proxy_app._long_session_observability_from_events(events, limit=50)

    assert report["tool_output_trim"]["event_count"] == 2
    assert report["tool_output_trim"]["enabled_event_count"] == 1
    assert report["tool_output_trim"]["applied_count"] == 1
    assert report["tool_output_trim"]["chars_removed"] == 1117203
    assert report["tool_output_trim"]["trimmed_item_count"] == 2
    assert report["tool_output_trim"]["target_trace_count"] == 2
    assert report["tool_output_trim"]["image_payload_trim_count"] == 1
    assert report["tool_output_trim"]["by_category"]["image_payload"]["trimmed_item_count"] == 1
    assert report["tool_output_trim"]["by_category"]["image_payload"]["estimated_remove_chars"] == 1117000
    assert report["tool_output_trim"]["by_category"]["shell_command"]["trimmed_item_count"] == 1
    assert report["recommendation"] == "monitor_limited_enabled_session"


def test_long_session_observability_recommends_fixing_canary_when_blocked():
    events = [
        {"event": "context_budget_breakdown", "chat_payload_chars": 1000},
        {
            "event": "flattened_tool_transcript_semantic_payload_compaction_applied",
            "applied": False,
            "reason": "semantic_payload_canary_guard_blocked_enabled",
        },
    ]

    report = proxy_app._long_session_observability_from_events(events, limit=10)

    assert report["semantic_payload"]["blocked_count"] == 1
    assert report["recommendation"] == "keep_dry_run_or_fix_canary"


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



def test_tool_output_image_payload_category_and_policy(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_PROXY_TOOL_OUTPUT_IMAGE_PAYLOAD_MAX_ITEM_CHARS", "2000")
    monkeypatch.setenv("DEEPSEEK_PROXY_TOOL_OUTPUT_IMAGE_PAYLOAD_KEEP_HEAD_CHARS", "80")
    monkeypatch.setenv("DEEPSEEK_PROXY_TOOL_OUTPUT_IMAGE_PAYLOAD_KEEP_TAIL_CHARS", "80")

    image_output = "IMAGE-BEGIN\\n" + ("0123456789" * 800) + "\\nIMAGE-END"
    input_items = [
        {
            "type": "function_call",
            "id": "call_image",
            "call_id": "call_image",
            "name": "view_image",
            "arguments": "{}",
        },
        {
            "type": "function_call_output",
            "call_id": "call_image",
            "output": image_output,
        },
    ]

    budget = proxy_app._tool_output_budget_breakdown(input_items)
    policy = budget["policy_dry_run"]

    assert budget["largest_outputs"][0]["tool_name"] == "view_image"
    assert budget["largest_outputs"][0]["category"] == "image_payload"
    assert policy["would_trim"] is True
    assert policy["targets"][0]["category"] == "image_payload"
    assert policy["targets"][0]["policy_name"] == "image_payload"
    assert policy["targets"][0]["estimated_remove_chars"] > 0


def test_tool_output_image_payload_enabled_trims_copy(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_PROXY_TOOL_OUTPUT_TRIM_MODE", "enabled")
    monkeypatch.setenv("DEEPSEEK_PROXY_TOOL_OUTPUT_IMAGE_PAYLOAD_MAX_ITEM_CHARS", "2000")
    monkeypatch.setenv("DEEPSEEK_PROXY_TOOL_OUTPUT_IMAGE_PAYLOAD_KEEP_HEAD_CHARS", "80")
    monkeypatch.setenv("DEEPSEEK_PROXY_TOOL_OUTPUT_IMAGE_PAYLOAD_KEEP_TAIL_CHARS", "80")

    image_output = "IMAGE-BEGIN\\n" + ("abcdef" * 2000) + "\\nIMAGE-END"
    input_items = [
        {
            "type": "function_call",
            "id": "call_image",
            "call_id": "call_image",
            "name": "view_image",
            "arguments": "{}",
        },
        {
            "type": "function_call_output",
            "call_id": "call_image",
            "output": image_output,
        },
    ]

    trimmed, report = proxy_app._apply_tool_output_safe_trimming(input_items)

    assert trimmed is not input_items
    assert input_items[1]["output"] == image_output
    assert trimmed[1]["output"] != image_output
    assert "[tool output trimmed by CoDeepSeedeX]" in trimmed[1]["output"]
    assert "tool_name: view_image" in trimmed[1]["output"]
    assert "category: image_payload" in trimmed[1]["output"]
    assert report["trimmed_item_count"] == 1
    assert report["targets"][0]["tool_name"] == "view_image"
    assert report["targets"][0]["category"] == "image_payload"



def test_tool_output_trimming_can_classify_before_previous_response_filter(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_PROXY_TOOL_OUTPUT_TRIM_MODE", "enabled")
    monkeypatch.setenv("DEEPSEEK_PROXY_TOOL_OUTPUT_IMAGE_PAYLOAD_MAX_ITEM_CHARS", "12000")

    image_output = "IMAGE-BEGIN\\n" + ("abcdef" * 6000) + "\\nIMAGE-END"
    input_items = [
        {"type": "function_call", "call_id": "call_image", "name": "view_image", "arguments": "{}"},
        {"type": "function_call_output", "call_id": "call_image", "output": image_output},
    ]

    trimmed, report = proxy_app._apply_tool_output_safe_trimming(input_items)
    filtered = [item for item in trimmed if item.get("type") != "function_call"]

    assert report["applied"] is True
    assert report["targets"][0]["category"] == "image_payload"
    assert report["targets"][0]["tool_name"] == "view_image"
    assert len(filtered) == 1
    assert filtered[0]["type"] == "function_call_output"
    assert "[tool output trimmed by CoDeepSeedeX]" in filtered[0]["output"]
    assert "category: image_payload" in filtered[0]["output"]


def test_tool_output_image_policy_does_not_affect_shell_below_shell_policy(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_PROXY_TOOL_OUTPUT_TRIM_MODE", "enabled")
    monkeypatch.setenv("DEEPSEEK_PROXY_TOOL_OUTPUT_IMAGE_PAYLOAD_MAX_ITEM_CHARS", "2000")
    monkeypatch.setenv("DEEPSEEK_PROXY_TOOL_OUTPUT_IMAGE_PAYLOAD_KEEP_HEAD_CHARS", "80")
    monkeypatch.setenv("DEEPSEEK_PROXY_TOOL_OUTPUT_IMAGE_PAYLOAD_KEEP_TAIL_CHARS", "80")

    shell_output = "Traceback (most recent call last):\\n" + ("shell-log\\n" * 300)
    input_items = [
        {
            "type": "function_call",
            "id": "call_shell",
            "call_id": "call_shell",
            "name": "exec_command",
            "arguments": "{}",
        },
        {
            "type": "function_call_output",
            "call_id": "call_shell",
            "output": shell_output,
        },
    ]

    trimmed, report = proxy_app._apply_tool_output_safe_trimming(input_items)

    assert trimmed[1]["output"] == shell_output
    assert report["trimmed_item_count"] == 0
    assert report["targets"] == []


def test_debug_trace_none_mode_preserves_largest_outputs_metadata(monkeypatch, tmp_path):
    trace_dir = tmp_path / "traces"
    monkeypatch.setenv("DEEPSEEK_PROXY_DEBUG_TRACE", "1")
    monkeypatch.setenv("DEEPSEEK_PROXY_DEBUG_DIR", str(trace_dir))
    monkeypatch.setenv("DEEPSEEK_PROXY_DEBUG_CONTENT", "none")

    proxy_app._debug_trace_event(
        "resp_tool_budget",
        "tool_output_budget_breakdown",
        largest_outputs=[
            {
                "index": 13,
                "call_id": "call_large",
                "tool_name": "shell",
                "item_chars": 41290,
                "output_chars": 41000,
                "exceeds_warn_item_chars": True,
            }
        ],
    )

    event = json.loads((trace_dir / "trace-resp_tool_budget.jsonl").read_text(encoding="utf-8"))
    assert isinstance(event["largest_outputs"], list)
    assert event["largest_outputs"][0]["call_id"] == "call_large"
    assert event["largest_outputs"][0]["tool_name"] == "shell"
    assert event["largest_outputs"][0]["item_chars"] == 41290


def test_tool_output_trim_dry_run_estimates_item_and_total_savings(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_PROXY_TOOL_OUTPUT_TRIM_MODE", "dry_run")
    monkeypatch.setenv("DEEPSEEK_PROXY_TOOL_OUTPUT_MAX_ITEM_CHARS", "100")
    monkeypatch.setenv("DEEPSEEK_PROXY_TOOL_OUTPUT_MAX_TOTAL_CHARS", "180")
    monkeypatch.setenv("DEEPSEEK_PROXY_TOOL_OUTPUT_KEEP_HEAD_CHARS", "20")
    monkeypatch.setenv("DEEPSEEK_PROXY_TOOL_OUTPUT_KEEP_TAIL_CHARS", "20")
    monkeypatch.setenv("DEEPSEEK_PROXY_TOOL_OUTPUT_TRIM_NOTICE_CHARS", "20")
    monkeypatch.setenv("DEEPSEEK_PROXY_TOOL_OUTPUT_TRIM_MAX_TARGETS", "5")

    input_items = [
        {
            "type": "function_call",
            "call_id": "call_1",
            "name": "write_stdin",
            "arguments": "{}",
        },
        {
            "type": "function_call_output",
            "call_id": "call_1",
            "output": "x" * 220,
        },
        {
            "type": "function_call",
            "call_id": "call_2",
            "name": "exec_command",
            "arguments": "{}",
        },
        {
            "type": "function_call_output",
            "call_id": "call_2",
            "output": "y" * 160,
        },
    ]

    budget = proxy_app._tool_output_budget_breakdown(input_items)
    dry_run = budget["trim_dry_run"]

    assert dry_run["mode"] == "dry_run"
    assert dry_run["applied"] is False
    assert dry_run["would_trim"] is True
    assert dry_run["would_trim_item_count"] >= 2
    assert dry_run["would_remove_chars_estimate"] > 0
    assert dry_run["estimated_total_output_chars_after"] < dry_run["estimated_total_output_chars_before"]
    assert dry_run["target_total_output_chars"] == 180
    assert "unmet_total_budget_chars" in dry_run
    assert "total_budget_reachable" in dry_run
    assert "trimmed_to_item_cap_chars" in dry_run
    assert dry_run["targets"][0]["estimated_remove_chars"] > 0
    assert dry_run["targets"][0]["trim_reason"] in {
        "item_exceeds_max_item_chars",
        "total_output_exceeds_max_total_chars",
    }


def test_debug_trace_none_mode_preserves_trim_dry_run_mode(monkeypatch, tmp_path):
    trace_dir = tmp_path / "traces"
    monkeypatch.setenv("DEEPSEEK_PROXY_DEBUG_TRACE", "1")
    monkeypatch.setenv("DEEPSEEK_PROXY_DEBUG_DIR", str(trace_dir))
    monkeypatch.setenv("DEEPSEEK_PROXY_DEBUG_CONTENT", "none")

    proxy_app._debug_trace_event(
        "resp_trim_dry_run",
        "tool_output_budget_breakdown",
        trim_dry_run={
            "mode": "dry_run",
            "applied": False,
            "would_trim": True,
            "unmet_total_budget_chars": 37216,
            "total_budget_reachable": False,
        },
    )

    event = json.loads((trace_dir / "trace-resp_trim_dry_run.jsonl").read_text(encoding="utf-8"))
    assert event["trim_dry_run"]["mode"] == "dry_run"
    assert event["trim_dry_run"]["unmet_total_budget_chars"] == 37216
    assert event["trim_dry_run"]["total_budget_reachable"] is False


def test_tool_output_policy_dry_run_classifies_generic_tool_names(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_PROXY_TOOL_OUTPUT_POLICY_MAX_TOTAL_CHARS", "500")
    monkeypatch.setenv("DEEPSEEK_PROXY_TOOL_OUTPUT_POLICY_MAX_TARGETS", "10")

    input_items = [
        {
            "type": "function_call",
            "call_id": "call_shell",
            "name": "exec_command",
            "arguments": "{}",
        },
        {
            "type": "function_call_output",
            "call_id": "call_shell",
            "output": "s" * 9500,
        },
        {
            "type": "function_call",
            "call_id": "call_stdin",
            "name": "write_stdin",
            "arguments": "{}",
        },
        {
            "type": "function_call_output",
            "call_id": "call_stdin",
            "output": "i" * 7000,
        },
        {
            "type": "function_call",
            "call_id": "call_unknown",
            "name": "vendor_specific_tool",
            "arguments": "{}",
        },
        {
            "type": "function_call_output",
            "call_id": "call_unknown",
            "output": "u" * 13000,
        },
    ]

    budget = proxy_app._tool_output_budget_breakdown(input_items)
    policy = budget["policy_dry_run"]

    categories = {item["call_id"]: item["category"] for item in budget["largest_outputs"]}
    assert categories["call_shell"] == "shell_command"
    assert categories["call_stdin"] == "interactive_shell"
    assert categories["call_unknown"] == "unknown"

    assert policy["enabled"] is True
    assert policy["applied"] is False
    assert policy["would_trim"] is True
    assert policy["category_counts"]["shell_command"] == 1
    assert policy["category_counts"]["interactive_shell"] == 1
    assert policy["category_counts"]["unknown"] == 1
    assert "shell_command" in policy["policies"]
    assert "interactive_shell" in policy["policies"]
    assert policy["targets"]
    assert all("category" in item for item in policy["targets"])
    assert all("policy_name" in item for item in policy["targets"])


def test_tool_output_policy_dry_run_event_stays_compact(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_PROXY_TOOL_OUTPUT_POLICY_MAX_TOTAL_CHARS", "80000")
    monkeypatch.setenv("DEEPSEEK_PROXY_TOOL_OUTPUT_POLICY_MAX_TARGETS", "20")

    input_items = []
    for index in range(80):
        call_id = f"call_{index}"
        input_items.append({
            "type": "function_call",
            "call_id": call_id,
            "name": "exec_command" if index % 2 else "write_stdin",
            "arguments": "{}",
        })
        input_items.append({
            "type": "function_call_output",
            "call_id": call_id,
            "output": "x" * (3000 + index * 100),
        })

    budget = proxy_app._tool_output_budget_breakdown(input_items)
    encoded = json.dumps(budget, ensure_ascii=False, separators=(",", ":"))

    assert "policy_dry_run" in budget
    assert budget["policy_dry_run"]["policies"]
    assert len(budget["policy_dry_run"]["targets"]) <= 20
    assert len(budget["largest_outputs"]) <= budget["config"]["largest_items"]
    assert len(encoded) < 8000


def test_tool_output_safe_trimming_default_dry_run_does_not_change_input(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_PROXY_TOOL_OUTPUT_TRIM_MODE", "dry_run")
    input_items = [
        {
            "type": "function_call",
            "call_id": "call_1",
            "name": "exec_command",
            "arguments": "{}",
        },
        {
            "type": "function_call_output",
            "call_id": "call_1",
            "output": "x" * 20000,
        },
    ]

    trimmed, report = proxy_app._apply_tool_output_safe_trimming(input_items)

    assert trimmed is input_items
    assert report["enabled"] is False
    assert report["applied"] is False
    assert report["reason"] == "trim_mode_not_enabled"
    assert input_items[1]["output"] == "x" * 20000


def test_tool_output_safe_trimming_enabled_trims_only_function_call_output(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_PROXY_TOOL_OUTPUT_TRIM_MODE", "enabled")
    monkeypatch.setenv("DEEPSEEK_PROXY_TOOL_OUTPUT_SHELL_COMMAND_MAX_ITEM_CHARS", "1000")
    monkeypatch.setenv("DEEPSEEK_PROXY_TOOL_OUTPUT_SHELL_COMMAND_KEEP_HEAD_CHARS", "20")
    monkeypatch.setenv("DEEPSEEK_PROXY_TOOL_OUTPUT_SHELL_COMMAND_KEEP_TAIL_CHARS", "30")
    monkeypatch.setenv("DEEPSEEK_PROXY_TOOL_OUTPUT_SHELL_COMMAND_NOTICE_CHARS", "128")

    input_items = [
        {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": "keep this"}],
        },
        {
            "type": "function_call",
            "call_id": "call_shell",
            "name": "exec_command",
            "arguments": "{\"cmd\":\"long\"}",
        },
        {
            "type": "function_call_output",
            "call_id": "call_shell",
            "output": "A" * 5000 + "TAIL",
        },
    ]

    trimmed, report = proxy_app._apply_tool_output_safe_trimming(input_items)

    assert trimmed is not input_items
    assert input_items[2]["output"] == "A" * 5000 + "TAIL"
    assert report["enabled"] is True
    assert report["applied"] is True
    assert report["trimmed_item_count"] == 1
    assert report["chars_removed"] > 0
    assert report["targets"][0]["category"] == "shell_command"
    assert trimmed[0] == input_items[0]
    assert trimmed[1] == input_items[1]
    assert "[tool output trimmed by CoDeepSeedeX]" in trimmed[2]["output"]
    assert "--- kept head ---" in trimmed[2]["output"]
    assert "--- kept tail ---" in trimmed[2]["output"]
    assert trimmed[2]["output"].endswith("TAIL")


def test_tool_output_safe_trimming_handles_non_list_input(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_PROXY_TOOL_OUTPUT_TRIM_MODE", "enabled")

    trimmed, report = proxy_app._apply_tool_output_safe_trimming("plain input")

    assert trimmed == "plain input"
    assert report["applied"] is False
    assert report["reason"] == "input_not_list"


def test_history_growth_breakdown_classifies_flattened_tool_transcripts():
    messages = [
        {"role": "system", "content": "developer instructions"},
        {"role": "user", "content": "plain question"},
        {
            "role": "user",
            "content": "assistant_requested_tool_calls:\n- tool_call_id: call_1\n  name: exec_command\n\ntool_outputs:\n- tool_call_id: call_1\n  content: long output",
        },
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call_2",
                    "type": "function",
                    "function": {"name": "exec_command", "arguments": "{\"cmd\":\"pytest\"}"},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "call_2", "content": "pytest output"},
    ]

    input_items = [
        {"type": "message", "role": "user", "content": "hello"},
        {"type": "function_call", "call_id": "call_1", "name": "exec_command", "arguments": "{}"},
        {"type": "function_call_output", "call_id": "call_1", "output": "output"},
    ]

    report = proxy_app._history_growth_breakdown(
        messages,
        input_value=input_items,
        previous_response_id="resp_previous",
    )

    assert report["previous_response_id_present"] is True
    assert report["message_count"] == 5
    assert report["history_categories"]["flattened_tool_transcript"]["count"] == 1
    assert report["history_categories"]["assistant_tool_call_message"]["count"] == 1
    assert report["history_categories"]["tool_protocol_message"]["count"] == 1
    assert report["history_categories"]["plain_user_message"]["count"] == 1
    assert report["history_categories"]["system_or_developer"]["count"] == 1
    assert report["assistant_tool_call_count"] == 1
    assert report["assistant_tool_arguments_chars"] > 0
    assert report["input_item_type_counts"]["function_call_output"] == 1
    assert report["largest_messages"]


def test_debug_trace_none_mode_preserves_largest_messages_metadata(monkeypatch, tmp_path):
    trace_dir = tmp_path / "traces"
    monkeypatch.setenv("DEEPSEEK_PROXY_DEBUG_TRACE", "1")
    monkeypatch.setenv("DEEPSEEK_PROXY_DEBUG_DIR", str(trace_dir))
    monkeypatch.setenv("DEEPSEEK_PROXY_DEBUG_CONTENT", "none")

    proxy_app._debug_trace_event(
        "resp_history_growth",
        "history_growth_breakdown",
        largest_messages=[
            {
                "index": 164,
                "role": "user",
                "history_category": "flattened_tool_transcript",
                "chars": 16669,
            }
        ],
    )

    event = json.loads((trace_dir / "trace-resp_history_growth.jsonl").read_text(encoding="utf-8"))
    assert isinstance(event["largest_messages"], list)
    assert event["largest_messages"][0]["role"] == "user"
    assert event["largest_messages"][0]["history_category"] == "flattened_tool_transcript"
    assert event["largest_messages"][0]["chars"] == 16669


def test_flattened_tool_transcript_compaction_dry_run_estimates_savings(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_PROXY_FLATTENED_TOOL_COMPACTION_PRESERVE_RECENT_MESSAGES", "1")
    monkeypatch.setenv("DEEPSEEK_PROXY_FLATTENED_TOOL_COMPACTION_MIN_MESSAGE_CHARS", "100")
    monkeypatch.setenv("DEEPSEEK_PROXY_FLATTENED_TOOL_COMPACTION_SUMMARY_CHARS", "50")
    monkeypatch.setenv("DEEPSEEK_PROXY_FLATTENED_TOOL_COMPACTION_TARGETS", "5")

    old_flattened = {
        "role": "user",
        "content": (
            "assistant_requested_tool_calls:\n"
            "- tool_call_id: call_old\n"
            "tool_outputs:\n"
            "- tool_call_id: call_old\n"
            "content: " + ("x" * 1000)
        ),
    }
    recent_flattened = {
        "role": "user",
        "content": (
            "assistant_requested_tool_calls:\n"
            "- tool_call_id: call_recent\n"
            "tool_outputs:\n"
            "- tool_call_id: call_recent\n"
            "content: " + ("y" * 1000)
        ),
    }

    messages = [
        {"role": "developer", "content": "system"},
        old_flattened,
        {"role": "assistant", "content": "answer"},
        recent_flattened,
    ]

    report = proxy_app._flattened_tool_transcript_compaction_dry_run(messages)

    assert report["enabled"] is True
    assert report["applied"] is False
    assert report["strategy"] == "flattened_tool_transcript_summary_dry_run"
    assert report["flattened_message_count"] == 2
    assert report["candidate_count"] == 1
    assert report["retained_recent_flattened_count"] == 1
    assert report["would_compact"] is True
    assert report["would_compact_count"] == 1
    assert report["would_remove_chars_estimate"] > 0
    assert report["estimated_messages_chars_after"] < report["estimated_messages_chars_before"]
    assert report["targets"][0]["history_category"] == "flattened_tool_transcript"
    assert report["targets"][0]["role"] == "user"


def test_flattened_tool_transcript_compaction_dry_run_can_be_disabled(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_PROXY_FLATTENED_TOOL_COMPACTION_DRY_RUN", "0")
    messages = [
        {
            "role": "user",
            "content": "assistant_requested_tool_calls:\ntool_outputs:\n" + ("x" * 1000),
        }
    ]

    report = proxy_app._flattened_tool_transcript_compaction_dry_run(messages)

    assert report["enabled"] is False
    assert report["applied"] is False
    assert report["would_compact"] is False
    assert report["targets"] == []


def test_flattened_tool_transcript_semantic_audit_classifies_types_and_risks(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_PROXY_FLATTENED_TOOL_SEMANTIC_AUDIT_TARGETS", "10")

    passed_test = {
        "role": "user",
        "content": (
            "assistant_requested_tool_calls:\n"
            "tool_outputs:\n"
            "===== pytest =====\n"
            "....\n"
            "4 passed in 0.10s\n"
        ),
    }
    stacktrace = {
        "role": "user",
        "content": (
            "assistant_requested_tool_calls:\n"
            "tool_outputs:\n"
            "Traceback (most recent call last):\n"
            "AssertionError: expected true\n"
        ),
    }
    chatty_terminal = {
        "role": "user",
        "content": (
            "assistant_requested_tool_calls:\n"
            "tool_outputs:\n"
            "\n• Running cd repo && pytest\n"
            "\n• Ran git status\n"
            "\n✔ You approved codex to always run commands\n"
        ),
    }

    report = proxy_app._flattened_tool_transcript_semantic_audit(
        [
            {"role": "developer", "content": "system"},
            passed_test,
            stacktrace,
            chatty_terminal,
        ]
    )

    assert report["enabled"] is True
    assert report["applied"] is False
    assert report["strategy"] == "flattened_tool_transcript_semantic_audit"
    assert report["flattened_message_count"] == 3
    assert report["semantic_types"]["test_output"]["count"] == 1
    assert report["semantic_types"]["stacktrace"]["count"] == 1
    assert report["semantic_types"]["chatty_terminal"]["count"] == 1
    assert report["semantic_risks"]["low"]["count"] == 1
    assert report["semantic_risks"]["medium"]["count"] == 1
    assert report["semantic_risks"]["high"]["count"] == 1
    assert report["retention_marker_counts"]["pytest summary"] == 1
    assert report["retention_marker_counts"]["Traceback"] == 1
    assert report["retention_marker_counts"]["AssertionError"] == 1
    assert report["targets"][0]["semantic_risk"] == "high"


def test_flattened_tool_transcript_semantic_audit_can_be_disabled(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_PROXY_FLATTENED_TOOL_SEMANTIC_AUDIT", "0")

    report = proxy_app._flattened_tool_transcript_semantic_audit(
        [
            {
                "role": "user",
                "content": "assistant_requested_tool_calls:\ntool_outputs:\npytest\n1 passed in 0.01s",
            }
        ]
    )

    assert report["enabled"] is False
    assert report["applied"] is False
    assert report["flattened_message_count"] == 0
    assert report["targets"] == []


def test_debug_trace_none_mode_preserves_semantic_audit_targets(monkeypatch, tmp_path):
    trace_dir = tmp_path / "traces"
    monkeypatch.setenv("DEEPSEEK_PROXY_DEBUG_TRACE", "1")
    monkeypatch.setenv("DEEPSEEK_PROXY_DEBUG_DIR", str(trace_dir))
    monkeypatch.setenv("DEEPSEEK_PROXY_DEBUG_CONTENT", "none")

    proxy_app._debug_trace_event(
        "resp_semantic_audit",
        "flattened_tool_transcript_semantic_audit",
        targets=[
            {
                "index": 7,
                "role": "user",
                "history_category": "flattened_tool_transcript",
                "chars": 4096,
                "text_chars": 4000,
                "semantic_type": "stacktrace",
                "semantic_risk": "medium",
                "retention_markers": ["Traceback", "AssertionError"],
            }
        ],
    )

    event = json.loads((trace_dir / "trace-resp_semantic_audit.jsonl").read_text(encoding="utf-8"))
    assert isinstance(event["targets"], list)
    assert event["targets"][0]["semantic_type"] == "stacktrace"
    assert event["targets"][0]["semantic_risk"] == "medium"
    assert event["targets"][0]["retention_markers"] == ["Traceback", "AssertionError"]


def test_flattened_tool_transcript_semantic_policy_dry_run_recommends_actions(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_PROXY_FLATTENED_TOOL_SEMANTIC_POLICY_TARGETS", "10")
    monkeypatch.setenv("DEEPSEEK_PROXY_FLATTENED_TOOL_SEMANTIC_POLICY_SUMMARY_CHARS", "200")

    passed_test = {
        "role": "user",
        "content": (
            "assistant_requested_tool_calls:\n"
            "tool_outputs:\n"
            "===== pytest =====\n"
            "....\n"
            "4 passed in 0.10s\n"
            + ("x" * 1000)
        ),
    }
    stacktrace = {
        "role": "user",
        "content": (
            "assistant_requested_tool_calls:\n"
            "tool_outputs:\n"
            "Traceback (most recent call last):\n"
            "AssertionError: expected true\n"
        ),
    }
    chatty_terminal = {
        "role": "user",
        "content": (
            "assistant_requested_tool_calls:\n"
            "tool_outputs:\n"
            "\n• Running cd repo && pytest\n"
            "\n• Ran git status\n"
            "\n✔ You approved codex to always run commands\n"
        ),
    }

    report = proxy_app._flattened_tool_transcript_semantic_compaction_policy_dry_run(
        [
            {"role": "developer", "content": "system"},
            passed_test,
            stacktrace,
            chatty_terminal,
        ]
    )

    assert report["enabled"] is True
    assert report["applied"] is False
    assert report["strategy"] == "flattened_tool_transcript_semantic_compaction_policy_dry_run"
    assert report["flattened_message_count"] == 3
    assert report["candidate_count"] == 3
    assert report["eligible_compaction_count"] == 1
    assert report["structure_only_count"] == 1
    assert report["preserve_count"] == 1
    assert report["would_compact"] is True
    assert report["would_compact_count"] == 1
    assert report["would_remove_chars_estimate"] > 0
    assert report["estimated_messages_chars_after"] < report["estimated_messages_chars_before"]
    assert report["policy_decisions"]["compact"] == 1
    assert report["policy_decisions"]["structure_only"] == 1
    assert report["policy_decisions"]["preserve"] == 1
    assert report["targets"][0]["recommended_action"] == "compact_test_output_summary"
    assert report["targets"][1]["recommended_action"] == "structure_preserving_summary_dry_run_only"
    assert report["targets"][2]["recommended_action"] == "preserve_high_risk_transcript"


def test_flattened_tool_transcript_semantic_policy_dry_run_can_be_disabled(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_PROXY_FLATTENED_TOOL_SEMANTIC_POLICY_DRY_RUN", "0")

    report = proxy_app._flattened_tool_transcript_semantic_compaction_policy_dry_run(
        [
            {
                "role": "user",
                "content": "assistant_requested_tool_calls:\ntool_outputs:\npytest\n1 passed in 0.01s",
            }
        ]
    )

    assert report["enabled"] is False
    assert report["applied"] is False
    assert report["candidate_count"] == 0
    assert report["targets"] == []


def test_debug_trace_none_mode_preserves_semantic_policy_targets(monkeypatch, tmp_path):
    trace_dir = tmp_path / "traces"
    monkeypatch.setenv("DEEPSEEK_PROXY_DEBUG_TRACE", "1")
    monkeypatch.setenv("DEEPSEEK_PROXY_DEBUG_DIR", str(trace_dir))
    monkeypatch.setenv("DEEPSEEK_PROXY_DEBUG_CONTENT", "none")

    proxy_app._debug_trace_event(
        "resp_semantic_policy",
        "flattened_tool_transcript_semantic_policy_dry_run",
        targets=[
            {
                "index": 3,
                "role": "user",
                "history_category": "flattened_tool_transcript",
                "chars": 2048,
                "semantic_type": "test_output",
                "semantic_risk": "low",
                "retention_markers": ["pytest summary"],
                "policy_decision": "compact",
                "recommended_action": "compact_test_output_summary",
                "compression_strategy": "pytest_passed_summary_with_tail",
                "estimated_after_chars": 200,
                "estimated_remove_chars": 1848,
            }
        ],
    )

    event = json.loads((trace_dir / "trace-resp_semantic_policy.jsonl").read_text(encoding="utf-8"))
    assert isinstance(event["targets"], list)
    assert event["targets"][0]["semantic_type"] == "test_output"
    assert event["targets"][0]["semantic_risk"] == "low"
    assert event["targets"][0]["policy_decision"] == "compact"
    assert event["targets"][0]["recommended_action"] == "compact_test_output_summary"
    assert event["targets"][0]["compression_strategy"] == "pytest_passed_summary_with_tail"
    assert event["targets"][0]["retention_markers"] == ["pytest summary"]





def test_semantic_compaction_request_trace_event_order_is_stable():
    from pathlib import Path

    source = Path(proxy_app.__file__).read_text(encoding="utf-8")
    start = source.index("response_id = _response_id()")
    request_section = source[start : start + 40000]

    expected_order = [
        "flattened_tool_transcript_semantic_audit",
        "flattened_tool_transcript_semantic_policy_dry_run",
        "flattened_tool_transcript_semantic_payload_compaction_applied",
        "flattened_tool_transcript_payload_compaction_applied",
        "context_budget_breakdown",
    ]

    positions = {name: request_section.index(name) for name in expected_order}
    assert [positions[name] for name in expected_order] == sorted(positions.values())


def test_semantic_compaction_default_environment_is_safe(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_PROXY_FLATTENED_TOOL_SEMANTIC_AUDIT", raising=False)
    monkeypatch.delenv("DEEPSEEK_PROXY_FLATTENED_TOOL_SEMANTIC_POLICY_DRY_RUN", raising=False)
    monkeypatch.delenv("DEEPSEEK_PROXY_FLATTENED_TOOL_SEMANTIC_PAYLOAD_COMPACTION_MODE", raising=False)
    monkeypatch.delenv("DEEPSEEK_PROXY_FLATTENED_TOOL_SEMANTIC_PAYLOAD_CANARY_GUARD", raising=False)
    monkeypatch.delenv("DEEPSEEK_PROXY_FLATTENED_TOOL_SEMANTIC_PAYLOAD_CANARY_ALLOW_ENABLED", raising=False)
    monkeypatch.delenv("DEEPSEEK_PROXY_FLATTENED_TOOL_SEMANTIC_PAYLOAD_CANARY_REQUIRE_LOCAL_INVARIANTS", raising=False)

    payload_config = proxy_app._flattened_tool_semantic_payload_compaction_env_config()
    canary_config = proxy_app._semantic_payload_canary_env_config()
    enabled_guard = proxy_app._semantic_payload_canary_guard_for_mode("enabled")

    assert payload_config["mode"] == "dry_run"
    assert canary_config["guard_enabled"] is True
    assert canary_config["allow_enabled"] is False
    assert canary_config["require_local_invariants"] is True
    assert enabled_guard["allowed"] is False
    assert "semantic_payload_canary_allow_enabled_not_set" in enabled_guard["blockers"]


def test_semantic_payload_compaction_enabled_mutates_only_payload_copy(monkeypatch):
    from copy import deepcopy

    monkeypatch.setenv("DEEPSEEK_PROXY_FLATTENED_TOOL_SEMANTIC_PAYLOAD_COMPACTION_MODE", "enabled")
    monkeypatch.setenv("DEEPSEEK_PROXY_FLATTENED_TOOL_SEMANTIC_PAYLOAD_CANARY_ALLOW_ENABLED", "1")
    monkeypatch.setenv("DEEPSEEK_PROXY_FLATTENED_TOOL_SEMANTIC_PAYLOAD_COMPACTION_PRESERVE_RECENT_MESSAGES", "1")
    monkeypatch.setenv("DEEPSEEK_PROXY_FLATTENED_TOOL_SEMANTIC_PAYLOAD_COMPACTION_MIN_MESSAGE_CHARS", "100")
    monkeypatch.setenv("DEEPSEEK_PROXY_FLATTENED_TOOL_SEMANTIC_PAYLOAD_COMPACTION_SUMMARY_CHARS", "900")

    messages = proxy_app._semantic_compaction_selftest_messages()
    original_messages = deepcopy(messages)

    compacted, report = proxy_app._apply_flattened_tool_transcript_semantic_payload_compaction(messages)

    assert report["applied"] is True
    assert report["effective_mode"] == "enabled"
    assert compacted is not messages
    assert messages == original_messages
    assert compacted != original_messages
    assert "[semantic flattened tool transcript compacted by CoDeepSeedeX]" in compacted[1]["content"]
    assert original_messages[1]["content"] == messages[1]["content"]


def test_semantic_payload_canary_blocks_enabled_without_allow(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_PROXY_FLATTENED_TOOL_SEMANTIC_PAYLOAD_COMPACTION_MODE", "enabled")
    monkeypatch.delenv("DEEPSEEK_PROXY_FLATTENED_TOOL_SEMANTIC_PAYLOAD_CANARY_ALLOW_ENABLED", raising=False)
    monkeypatch.setenv("DEEPSEEK_PROXY_FLATTENED_TOOL_SEMANTIC_PAYLOAD_COMPACTION_PRESERVE_RECENT_MESSAGES", "1")
    monkeypatch.setenv("DEEPSEEK_PROXY_FLATTENED_TOOL_SEMANTIC_PAYLOAD_COMPACTION_MIN_MESSAGE_CHARS", "100")

    messages = proxy_app._semantic_compaction_selftest_messages()
    compacted, report = proxy_app._apply_flattened_tool_transcript_semantic_payload_compaction(messages)

    assert compacted is messages
    assert report["applied"] is False
    assert report["enabled"] is False
    assert report["effective_mode"] == "dry_run"
    assert report["reason"] == "semantic_payload_canary_guard_blocked_enabled"
    assert report["canary_guard"]["allowed"] is False
    assert "semantic_payload_canary_allow_enabled_not_set" in report["canary_guard"]["blockers"]


def test_semantic_payload_canary_allows_enabled_with_allow(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_PROXY_FLATTENED_TOOL_SEMANTIC_PAYLOAD_COMPACTION_MODE", "enabled")
    monkeypatch.setenv("DEEPSEEK_PROXY_FLATTENED_TOOL_SEMANTIC_PAYLOAD_CANARY_ALLOW_ENABLED", "1")
    monkeypatch.setenv("DEEPSEEK_PROXY_FLATTENED_TOOL_SEMANTIC_PAYLOAD_COMPACTION_PRESERVE_RECENT_MESSAGES", "1")
    monkeypatch.setenv("DEEPSEEK_PROXY_FLATTENED_TOOL_SEMANTIC_PAYLOAD_COMPACTION_MIN_MESSAGE_CHARS", "100")
    monkeypatch.setenv("DEEPSEEK_PROXY_FLATTENED_TOOL_SEMANTIC_PAYLOAD_COMPACTION_SUMMARY_CHARS", "900")

    messages = proxy_app._semantic_compaction_selftest_messages()
    compacted, report = proxy_app._apply_flattened_tool_transcript_semantic_payload_compaction(messages)

    assert compacted is not messages
    assert report["applied"] is True
    assert report["enabled"] is True
    assert report["effective_mode"] == "enabled"
    assert report["canary_guard"]["allowed"] is True
    assert report["compacted_count"] == 1


def test_semantic_compaction_selftest_report_passes(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_PROXY_FLATTENED_TOOL_SEMANTIC_PAYLOAD_COMPACTION_MODE", "dry_run")

    report = proxy_app._semantic_compaction_selftest_report()

    assert report["status"] == "ok"
    assert report["kind"] == "semantic_compaction_selftest"
    assert report["audit"]["flattened_message_count"] == 4
    assert report["policy_dry_run"]["would_compact"] is True
    assert report["payload_dry_run"]["applied"] is False
    assert report["payload_enabled_simulation"]["applied"] is True
    assert report["payload_enabled_simulation"]["compacted_count"] == 1
    assert report["assertions"]["original_messages_unchanged"] is True
    assert report["assertions"]["low_risk_test_output_compacted"] is True
    assert report["assertions"]["medium_stacktrace_preserved"] is True
    assert report["assertions"]["high_chatty_terminal_preserved"] is True
    assert report["assertions"]["recent_low_risk_preserved"] is True
    assert report["synthetic_rollout"]["safe_to_enable_payload_compaction"] is True


def test_flattened_tool_semantic_payload_compaction_default_does_not_change_messages(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_PROXY_FLATTENED_TOOL_SEMANTIC_PAYLOAD_COMPACTION_MODE", "dry_run")
    messages = [
        {
            "role": "user",
            "content": (
                "assistant_requested_tool_calls:\n"
                "tool_outputs:\n"
                "===== pytest =====\n"
                "4 passed in 0.10s\n"
                + ("x" * 5000)
            ),
        }
    ]

    compacted, report = proxy_app._apply_flattened_tool_transcript_semantic_payload_compaction(messages)

    assert compacted is messages
    assert report["enabled"] is False
    assert report["applied"] is False
    assert report["reason"] == "semantic_payload_compaction_mode_not_enabled"
    assert messages[0]["content"].endswith("x" * 5000)


def test_flattened_tool_semantic_payload_compaction_enabled_only_compacts_low_risk_copy(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_PROXY_FLATTENED_TOOL_SEMANTIC_PAYLOAD_COMPACTION_MODE", "enabled")
    monkeypatch.setenv("DEEPSEEK_PROXY_FLATTENED_TOOL_SEMANTIC_PAYLOAD_CANARY_ALLOW_ENABLED", "1")
    monkeypatch.setenv("DEEPSEEK_PROXY_FLATTENED_TOOL_SEMANTIC_PAYLOAD_COMPACTION_PRESERVE_RECENT_MESSAGES", "1")
    monkeypatch.setenv("DEEPSEEK_PROXY_FLATTENED_TOOL_SEMANTIC_PAYLOAD_COMPACTION_MIN_MESSAGE_CHARS", "100")
    monkeypatch.setenv("DEEPSEEK_PROXY_FLATTENED_TOOL_SEMANTIC_PAYLOAD_COMPACTION_SUMMARY_CHARS", "900")

    low_risk_test = (
        "assistant_requested_tool_calls:\n"
        "tool_outputs:\n"
        "===== pytest =====\n"
        "....\n"
        "4 passed in 0.10s\n"
        + ("x" * 5000)
    )
    medium_stacktrace = (
        "assistant_requested_tool_calls:\n"
        "tool_outputs:\n"
        "Traceback (most recent call last):\n"
        "AssertionError: expected true\n"
        + ("y" * 5000)
    )
    high_chatty = (
        "assistant_requested_tool_calls:\n"
        "tool_outputs:\n"
        "\n• Running cd repo && pytest\n"
        "\n• Ran git status\n"
        "\n✔ You approved codex to always run commands\n"
        + ("z" * 5000)
    )
    recent_low_risk = (
        "assistant_requested_tool_calls:\n"
        "tool_outputs:\n"
        "===== pytest =====\n"
        "1 passed in 0.01s\n"
        + ("r" * 5000)
    )
    messages = [
        {"role": "developer", "content": "system"},
        {"role": "user", "content": low_risk_test},
        {"role": "user", "content": medium_stacktrace},
        {"role": "user", "content": high_chatty},
        {"role": "user", "content": recent_low_risk},
    ]

    compacted, report = proxy_app._apply_flattened_tool_transcript_semantic_payload_compaction(messages)

    assert compacted is not messages
    assert messages[1]["content"] == low_risk_test
    assert messages[2]["content"] == medium_stacktrace
    assert messages[3]["content"] == high_chatty
    assert messages[4]["content"] == recent_low_risk

    assert report["enabled"] is True
    assert report["applied"] is True
    assert report["reason"] == "enabled"
    assert report["strategy"] == "flattened_tool_transcript_semantic_policy_payload_compaction"
    assert report["flattened_message_count"] == 4
    assert report["candidate_count"] == 3
    assert report["eligible_policy_count"] == 1
    assert report["skipped_policy_count"] == 2
    assert report["retained_recent_flattened_count"] == 1
    assert report["compacted_count"] == 1
    assert report["chars_removed"] > 0

    assert "[semantic flattened tool transcript compacted by CoDeepSeedeX]" in compacted[1]["content"]
    assert "recommended_action: compact_test_output_summary" in compacted[1]["content"]
    assert "4 passed in 0.10s" in compacted[1]["content"]
    assert compacted[2]["content"] == medium_stacktrace
    assert compacted[3]["content"] == high_chatty
    assert compacted[4]["content"] == recent_low_risk

    assert report["targets"][0]["recommended_action"] == "compact_test_output_summary"
    assert report["targets"][0]["semantic_type"] == "test_output"
    assert report["targets"][0]["semantic_risk"] == "low"


def test_flattened_tool_semantic_payload_compaction_non_list_fallback(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_PROXY_FLATTENED_TOOL_SEMANTIC_PAYLOAD_COMPACTION_MODE", "enabled")

    compacted, report = proxy_app._apply_flattened_tool_transcript_semantic_payload_compaction("not messages")

    assert compacted == "not messages"
    assert report["applied"] is False
    assert report["reason"] == "messages_not_list"


def test_flattened_tool_payload_compaction_default_does_not_change_messages(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_PROXY_FLATTENED_TOOL_PAYLOAD_COMPACTION_MODE", "dry_run")
    messages = [
        {
            "role": "user",
            "content": "assistant_requested_tool_calls:\ntool_outputs:\n" + ("x" * 5000),
        }
    ]

    compacted, report = proxy_app._apply_flattened_tool_transcript_payload_compaction(messages)

    assert compacted is messages
    assert report["enabled"] is False
    assert report["applied"] is False
    assert report["reason"] == "payload_compaction_mode_not_enabled"
    assert messages[0]["content"].endswith("x" * 5000)


def test_flattened_tool_payload_compaction_enabled_changes_only_copy(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_PROXY_FLATTENED_TOOL_PAYLOAD_COMPACTION_MODE", "enabled")
    monkeypatch.setenv("DEEPSEEK_PROXY_FLATTENED_TOOL_PAYLOAD_COMPACTION_PRESERVE_RECENT_MESSAGES", "1")
    monkeypatch.setenv("DEEPSEEK_PROXY_FLATTENED_TOOL_PAYLOAD_COMPACTION_MIN_MESSAGE_CHARS", "100")
    monkeypatch.setenv("DEEPSEEK_PROXY_FLATTENED_TOOL_PAYLOAD_COMPACTION_SUMMARY_CHARS", "700")

    old_content = "assistant_requested_tool_calls:\ntool_outputs:\n" + ("x" * 5000)
    recent_content = "assistant_requested_tool_calls:\ntool_outputs:\n" + ("y" * 5000)
    messages = [
        {"role": "developer", "content": "system"},
        {"role": "user", "content": old_content},
        {"role": "assistant", "content": "answer"},
        {"role": "user", "content": recent_content},
    ]

    compacted, report = proxy_app._apply_flattened_tool_transcript_payload_compaction(messages)

    assert compacted is not messages
    assert messages[1]["content"] == old_content
    assert messages[3]["content"] == recent_content
    assert report["enabled"] is True
    assert report["applied"] is True
    assert report["reason"] == "enabled"
    assert report["compacted_count"] == 1
    assert report["retained_recent_flattened_count"] == 1
    assert report["chars_removed"] > 0
    assert "[flattened tool transcript compacted by CoDeepSeedeX]" in compacted[1]["content"]
    assert compacted[3]["content"] == recent_content


def test_flattened_tool_payload_compaction_non_list_fallback(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_PROXY_FLATTENED_TOOL_PAYLOAD_COMPACTION_MODE", "enabled")

    compacted, report = proxy_app._apply_flattened_tool_transcript_payload_compaction("not messages")

    assert compacted == "not messages"
    assert report["applied"] is False
    assert report["reason"] == "messages_not_list"
