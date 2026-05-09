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
