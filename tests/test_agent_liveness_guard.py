import json
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from deepseek_responses_proxy.app import (
    _build_chat_payload,
    _assistant_message_needs_liveness_guard,
    _run_chat_with_tool_bridge,
    create_app,
)


class FakeDeepSeekClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.payloads = []

    async def chat_completions(self, payload):
        self.payloads.append(payload)
        if not self.responses:
            raise AssertionError("unexpected extra chat_completions call")
        return self.responses.pop(0)


def _response(message):
    return {
        "choices": [{"message": message}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }


def test_liveness_intent_detector_only_matches_unfinished_tool_intent():
    assert _assistant_message_needs_liveness_guard(
        {
            "role": "assistant",
            "content": "uiautomator2 connected successfully. Now let me try more — wake the screen, dump UI, and test a real action:",
        },
        tools_available=True,
    )

    assert not _assistant_message_needs_liveness_guard(
        {"role": "assistant", "content": "Done. The repository is clean and all tests passed."},
        tools_available=True,
    )

    assert not _assistant_message_needs_liveness_guard(
        {"role": "assistant", "content": "Now let me summarize the result for you."},
        tools_available=True,
    )

    assert _assistant_message_needs_liveness_guard(
        {
            "role": "assistant",
            "content": "dumpsys 没返回内容。换用 uiautomator2 直接检查当前状态并截图：",
        },
        tools_available=True,
    )

    assert _assistant_message_needs_liveness_guard(
        {
            "role": "assistant",
            "content": "WeChat is open. Capture one final screenshot:",
        },
        tools_available=True,
    )

    assert not _assistant_message_needs_liveness_guard(
        {"role": "assistant", "content": "Now let me run tests:", "tool_calls": [{"id": "x"}]},
        tools_available=True,
    )

    assert not _assistant_message_needs_liveness_guard(
        {"role": "assistant", "content": "Now let me run tests:"},
        tools_available=False,
    )


@pytest.mark.asyncio
async def test_liveness_guard_reasks_and_surfaces_local_codex_tool_call(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DEEPSEEK_PROXY_AGENT_LIVENESS_GUARD", "1")
    monkeypatch.setenv("DEEPSEEK_PROXY_AGENT_LIVENESS_MAX_RETRIES", "1")

    fake = FakeDeepSeekClient(
        [
            _response(
                {
                    "role": "assistant",
                    "content": "uiautomator2 connected successfully. Now let me try more — wake the screen, dump UI, and test a real action:",
                }
            ),
            _response(
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call_shell",
                            "type": "function",
                            "function": {
                                "name": "shell",
                                "arguments": json.dumps({"cmd": "echo ok"}),
                            },
                        }
                    ],
                }
            ),
        ]
    )

    deepseek_response, history = await _run_chat_with_tool_bridge(
        deepseek_client=fake,
        chat_payload={
            "model": "deepseek-v4-pro",
            "messages": [{"role": "user", "content": "test device"}],
            "tools": [{"type": "function", "function": {"name": "shell", "parameters": {}}}],
        },
        messages_for_deepseek=[{"role": "user", "content": "test device"}],
        history_messages=[{"role": "user", "content": "test device"}],
        model="deepseek-v4-pro",
        deepseek_tools=[{"type": "function", "function": {"name": "shell", "parameters": {}}}],
        reasoning_effort=None,
        request_payload={},
    )

    assert len(fake.payloads) == 2
    assert "Codex agent-loop protocol correction" in json.dumps(fake.payloads[1], ensure_ascii=False)
    assert deepseek_response["choices"][0]["message"]["tool_calls"][0]["function"]["name"] == "shell"
    assert history == [{"role": "user", "content": "test device"}]

    report = json.loads(Path(".debug/agent_liveness_guard_report.json").read_text(encoding="utf-8"))
    assert report["triggered"] is True
    assert report["retry_count"] == 1
    assert report["final_has_tool_calls"] is True
    assert report["final_tool_call_count"] == 1
    assert report["retry_attempts"][0]["response_has_tool_calls"] is True
    assert report["retry_attempts"][0]["response_tool_names"] == ["shell"]


@pytest.mark.asyncio
async def test_liveness_retry_without_tool_call_returns_pre_retry_response(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DEEPSEEK_PROXY_AGENT_LIVENESS_GUARD", "1")
    monkeypatch.setenv("DEEPSEEK_PROXY_AGENT_LIVENESS_MAX_RETRIES", "1")

    pre_retry_text = (
        "uiautomator2 connected successfully. Now let me try more — "
        "wake the screen, dump UI, and test a real action:"
    )
    leaked_retry_text = "B — no tool needed. This was already the final answer."

    fake = FakeDeepSeekClient(
        [
            _response({"role": "assistant", "content": pre_retry_text}),
            _response({"role": "assistant", "content": leaked_retry_text}),
        ]
    )

    deepseek_response, history = await _run_chat_with_tool_bridge(
        deepseek_client=fake,
        chat_payload={
            "model": "deepseek-v4-pro",
            "messages": [{"role": "user", "content": "check device"}],
            "tools": [{"type": "function", "function": {"name": "shell", "parameters": {}}}],
        },
        messages_for_deepseek=[{"role": "user", "content": "check device"}],
        history_messages=[{"role": "user", "content": "check device"}],
        model="deepseek-v4-pro",
        deepseek_tools=[{"type": "function", "function": {"name": "shell", "parameters": {}}}],
        reasoning_effort=None,
        request_payload={},
    )

    assert len(fake.payloads) == 2
    assert deepseek_response["choices"][0]["message"]["content"] == pre_retry_text
    assert history == [{"role": "user", "content": "check device"}]

    report = json.loads(Path(".debug/agent_liveness_guard_report.json").read_text(encoding="utf-8"))
    assert report["triggered"] is True
    assert report["retry_count"] == 1
    assert report["final_has_tool_calls"] is False
    assert report["retry_attempts"][0]["response_has_tool_calls"] is False
    assert report["retry_attempts"][0]["response_content_preview"] == leaked_retry_text
    assert "retry_without_tool_call_returned_pre_retry_response" in report["guard_reason"]



@pytest.mark.asyncio
async def test_liveness_guard_does_not_reask_final_answer(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DEEPSEEK_PROXY_AGENT_LIVENESS_GUARD", "1")

    fake = FakeDeepSeekClient(
        [
            _response({"role": "assistant", "content": "Done. All requested checks are complete."}),
        ]
    )

    deepseek_response, _history = await _run_chat_with_tool_bridge(
        deepseek_client=fake,
        chat_payload={
            "model": "deepseek-v4-pro",
            "messages": [{"role": "user", "content": "summarize"}],
            "tools": [{"type": "function", "function": {"name": "shell", "parameters": {}}}],
        },
        messages_for_deepseek=[{"role": "user", "content": "summarize"}],
        history_messages=[{"role": "user", "content": "summarize"}],
        model="deepseek-v4-pro",
        deepseek_tools=[{"type": "function", "function": {"name": "shell", "parameters": {}}}],
        reasoning_effort=None,
        request_payload={},
    )

    assert len(fake.payloads) == 1
    assert deepseek_response["choices"][0]["message"]["content"].startswith("Done")

    report = json.loads(Path(".debug/agent_liveness_guard_report.json").read_text(encoding="utf-8"))
    assert report["triggered"] is False
    assert report["retry_count"] == 0
    assert report["final_has_tool_calls"] is False


@pytest.mark.asyncio
async def test_proxy_status_reports_agent_liveness(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DEEPSEEK_PROXY_AGENT_LIVENESS_GUARD", "1")
    monkeypatch.setenv("DEEPSEEK_PROXY_AGENT_LIVENESS_MAX_RETRIES", "2")

    debug_dir = Path(".debug")
    debug_dir.mkdir()
    (debug_dir / "agent_liveness_guard_report.json").write_text(
        json.dumps(
            {
                "version": "test-version",
                "enabled": True,
                "triggered": True,
                "retry_count": 1,
                "max_retries": 2,
                "tools_available": True,
                "round_index": 1,
                "guard_reason": "assistant_narrated_tool_intent_without_tool_call",
                "final_has_tool_calls": True,
                "final_tool_call_count": 1,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    app = create_app()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/v1/proxy/status")

    assert response.status_code == 200
    data = response.json()

    assert data["version"].startswith("v")
    assert data["agent_liveness"]["config"]["enabled"] is True
    assert data["agent_liveness"]["config"]["max_retries"] == 2
    assert data["agent_liveness"]["judge"]["config"]["upstream_model"] == "deepseek-v4-flash"
    assert data["agent_liveness"]["judge"]["config"]["thinking"] == {"type": "disabled"}
    assert data["agent_liveness"]["tool_protocol"]["config"]["enabled"] is True
    assert data["agent_liveness"]["last_report"]["exists"] is True
    assert data["agent_liveness"]["last_report"]["triggered"] is True
    assert data["agent_liveness"]["last_report"]["retry_count"] == 1
    assert data["agent_liveness"]["last_report"]["final_has_tool_calls"] is True



def test_codex_tool_protocol_instruction_is_injected_for_tool_requests(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_PROXY_CODEX_TOOL_PROTOCOL_INSTRUCTION", "1")

    payload = _build_chat_payload(
        model="deepseek-v4-pro",
        messages=[{"role": "user", "content": "check device"}],
        tools=[{"type": "function", "function": {"name": "shell", "parameters": {}}}],
        reasoning_effort=None,
        request_payload={},
    )

    serialized = json.dumps(payload, ensure_ascii=False)
    assert "[deepseek-proxy codex tool protocol]" in serialized
    assert "emit a tool_call" in serialized


def test_codex_tool_protocol_instruction_is_not_duplicated(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_PROXY_CODEX_TOOL_PROTOCOL_INSTRUCTION", "1")

    messages = [
        {
            "role": "system",
            "content": "[deepseek-proxy codex tool protocol]\nexisting",
        },
        {"role": "user", "content": "check device"},
    ]
    payload = _build_chat_payload(
        model="deepseek-v4-pro",
        messages=messages,
        tools=[{"type": "function", "function": {"name": "shell", "parameters": {}}}],
        reasoning_effort=None,
        request_payload={},
    )

    serialized = json.dumps(payload, ensure_ascii=False)
    assert serialized.count("[deepseek-proxy codex tool protocol]") == 1


@pytest.mark.asyncio
async def test_liveness_judge_triggers_retry_when_heuristic_misses(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DEEPSEEK_PROXY_AGENT_LIVENESS_GUARD", "1")
    monkeypatch.setenv("DEEPSEEK_PROXY_AGENT_LIVENESS_MAX_RETRIES", "2")
    monkeypatch.setenv("DEEPSEEK_PROXY_AGENT_LIVENESS_JUDGE_ENABLED", "1")
    monkeypatch.setenv("DEEPSEEK_PROXY_AGENT_LIVENESS_JUDGE_MODEL", "v4-flash-no-thinking")

    fake = FakeDeepSeekClient(
        [
            _response(
                {
                    "role": "assistant",
                    "content": (
                        "INJECT_EVENTS 仍然被阻止。使用 WeChat URL scheme 或 intent "
                        "直接跳转到通讯录/好友申请页面，同时验证 keyevent 是否可行。"
                    ),
                }
            ),
            _response(
                {
                    "role": "assistant",
                    "content": json.dumps(
                        {
                            "decision": "needs_tool_call",
                            "confidence": 0.92,
                            "reason": "The assistant describes environment actions but emitted no tool call.",
                            "candidate_trigger_phrases": [
                                "使用 WeChat URL scheme",
                                "验证 keyevent 是否可行",
                            ],
                        },
                        ensure_ascii=False,
                    ),
                }
            ),
            _response(
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call_shell",
                            "type": "function",
                            "function": {
                                "name": "shell",
                                "arguments": json.dumps({"cmd": "echo ok"}),
                            },
                        }
                    ],
                }
            ),
        ]
    )

    deepseek_response, _history = await _run_chat_with_tool_bridge(
        deepseek_client=fake,
        chat_payload={
            "model": "deepseek-v4-pro",
            "messages": [{"role": "user", "content": "accept wechat friend"}],
            "tools": [{"type": "function", "function": {"name": "shell", "parameters": {}}}],
        },
        messages_for_deepseek=[{"role": "user", "content": "accept wechat friend"}],
        history_messages=[{"role": "user", "content": "accept wechat friend"}],
        model="deepseek-v4-pro",
        deepseek_tools=[{"type": "function", "function": {"name": "shell", "parameters": {}}}],
        reasoning_effort=None,
        request_payload={},
    )

    assert len(fake.payloads) == 3
    assert fake.payloads[1]["model"] == "deepseek-v4-flash"
    assert fake.payloads[1]["thinking"] == {"type": "disabled"}
    assert deepseek_response["choices"][0]["message"]["tool_calls"][0]["function"]["name"] == "shell"

    report = json.loads(Path(".debug/agent_liveness_guard_report.json").read_text(encoding="utf-8"))
    assert report["triggered"] is True
    assert report["retry_count"] == 1
    assert report["guard_reason"] == "judge_needs_tool_call"
    assert report["judge_attempts"][0]["decision"] == "needs_tool_call"
    assert "使用 WeChat URL scheme" in report["judge_attempts"][0]["candidate_trigger_phrases"]
    assert report["retry_attempts"][0]["response_has_tool_calls"] is True


@pytest.mark.asyncio
async def test_liveness_retry_without_tool_call_does_not_retry_again(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DEEPSEEK_PROXY_AGENT_LIVENESS_GUARD", "1")
    monkeypatch.setenv("DEEPSEEK_PROXY_AGENT_LIVENESS_MAX_RETRIES", "2")
    monkeypatch.setenv("DEEPSEEK_PROXY_DEBUG_TRACE", "1")
    monkeypatch.setenv("DEEPSEEK_PROXY_DEBUG_DIR", str(tmp_path / "traces"))
    monkeypatch.setenv("DEEPSEEK_PROXY_DEBUG_CONTENT", "none")

    pre_retry_text = (
        "I found the device. Now let me inspect the UI and run the next shell command."
    )
    retry_text = (
        "I still need to inspect the UI and then run the shell command, but no tool call was emitted."
    )

    fake = FakeDeepSeekClient(
        [
            _response({"role": "assistant", "content": pre_retry_text}),
            _response({"role": "assistant", "content": retry_text}),
        ]
    )

    deepseek_response, history = await _run_chat_with_tool_bridge(
        deepseek_client=fake,
        chat_payload={
            "model": "deepseek-v4-pro",
            "messages": [{"role": "user", "content": "inspect device"}],
            "tools": [{"type": "function", "function": {"name": "shell", "parameters": {}}}],
        },
        messages_for_deepseek=[{"role": "user", "content": "inspect device"}],
        history_messages=[{"role": "user", "content": "inspect device"}],
        model="deepseek-v4-pro",
        deepseek_tools=[{"type": "function", "function": {"name": "shell", "parameters": {}}}],
        reasoning_effort=None,
        request_payload={},
        response_id="resp_liveness_policy",
    )

    assert len(fake.payloads) == 2
    assert deepseek_response["choices"][0]["message"]["content"] == pre_retry_text
    assert history == [{"role": "user", "content": "inspect device"}]

    report = json.loads(Path(".debug/agent_liveness_guard_report.json").read_text(encoding="utf-8"))
    assert report["triggered"] is True
    assert report["retry_count"] == 1
    assert report["retry_attempts"][0]["response_has_tool_calls"] is False
    assert report["guard_reason"] == (
        "retry_without_tool_call_no_further_retry"
        "_retry_without_tool_call_returned_pre_retry_response"
    )

    trace = Path("traces/trace-resp_liveness_policy.jsonl").read_text(encoding="utf-8")
    events = [json.loads(line) for line in trace.splitlines()]
    decisions = [event for event in events if event["event"] == "liveness_guard_decision"]
    assert decisions
    assert decisions[-1]["should_retry"] is False
    assert decisions[-1]["guard_reason"] == "retry_without_tool_call_no_further_retry"


def test_user_tool_control_policy_taxonomy_counterexamples():
    from deepseek_responses_proxy.app import _build_user_tool_control_policy_report

    shell_tool = [{"type": "function", "function": {"name": "shell", "parameters": {}}}]
    status_tool = [{"type": "function", "function": {"name": "proxy_status", "parameters": {}}}]

    explicit = _build_user_tool_control_policy_report(
        [
            {
                "type": "message",
                "role": "user",
                "content": "不要继续执行命令，先解释为什么要这么做",
            }
        ],
        shell_tool,
    )
    assert explicit["user_signal"] == "explicit_tool_stop"
    assert explicit["decision_if_enabled"] == "would_suppress_tools"
    assert explicit["policy_is_dry_run_only"] is True

    answer_first = _build_user_tool_control_policy_report(
        [
            {
                "type": "message",
                "role": "user",
                "content": "先回答我这个问题，不要急着往下做",
            }
        ],
        status_tool,
    )
    assert answer_first["user_signal"] == "answer_or_explain_only"
    assert answer_first["decision_if_enabled"] == "would_suppress_tools"

    ambiguous = _build_user_tool_control_policy_report(
        [{"type": "message", "role": "user", "content": "停一下"}],
        status_tool,
    )
    assert ambiguous["user_signal"] == "ambiguous_stop"
    assert ambiguous["decision_if_enabled"] == "observe_only"

    quoted = _build_user_tool_control_policy_report(
        [
            {
                "type": "message",
                "role": "user",
                "content": "帮我解释这句：“不要继续执行命令”是什么意思",
            }
        ],
        shell_tool,
    )
    assert quoted["user_signal"] == "quoted_or_meta_stop_discussion"
    assert quoted["decision_if_enabled"] == "allow_tools"

    negated = _build_user_tool_control_policy_report(
        [
            {
                "type": "message",
                "role": "user",
                "content": "不是让你停止执行，继续运行目标测试",
            }
        ],
        shell_tool,
    )
    assert negated["user_signal"] == "negated_stop"
    assert negated["decision_if_enabled"] == "allow_tools"


def test_liveness_guard_does_not_treat_pause_and_explain_as_tool_intent():
    from deepseek_responses_proxy.app import _assistant_message_needs_liveness_guard

    assert not _assistant_message_needs_liveness_guard(
        {
            "role": "assistant",
            "content": "接下来我将暂停执行任务，并且先向你解释清楚。",
        },
        tools_available=True,
    )

    assert not _assistant_message_needs_liveness_guard(
        {
            "role": "assistant",
            "content": "你要求我不要继续执行命令，所以我先解释当前判断。",
        },
        tools_available=True,
    )

    assert not _assistant_message_needs_liveness_guard(
        {
            "role": "assistant",
            "content": "I will pause tool execution and explain first.",
        },
        tools_available=True,
    )

    assert _assistant_message_needs_liveness_guard(
        {
            "role": "assistant",
            "content": "Now let me inspect the UI and run the next shell command:",
        },
        tools_available=True,
    )


def test_user_tool_control_policy_answer_first_sequencing():
    from deepseek_responses_proxy.app import _build_user_tool_control_policy_report

    shell_tool = [{"type": "function", "function": {"name": "shell", "parameters": {}}}]

    only = _build_user_tool_control_policy_report(
        [{"type": "message", "role": "user", "content": "先解释清楚。"}],
        shell_tool,
    )
    assert only["user_signal"] == "answer_or_explain_only"
    assert only["decision_if_enabled"] == "would_suppress_tools"

    ordered_cn = _build_user_tool_control_policy_report(
        [{"type": "message", "role": "user", "content": "先解释原因，然后继续执行测试。"}],
        shell_tool,
    )
    assert ordered_cn["user_signal"] == "ordered_explain_then_continue"
    assert ordered_cn["decision_if_enabled"] == "split_turn_required"

    ordered_en = _build_user_tool_control_policy_report(
        [{"type": "message", "role": "user", "content": "Explain first, then run the command."}],
        shell_tool,
    )
    assert ordered_en["user_signal"] == "ordered_explain_then_continue"
    assert ordered_en["decision_if_enabled"] == "split_turn_required"

    ambiguous = _build_user_tool_control_policy_report(
        [{"type": "message", "role": "user", "content": "先解释一下，然后看情况继续。"}],
        shell_tool,
    )
    assert ambiguous["user_signal"] == "ambiguous_answer_first"
    assert ambiguous["decision_if_enabled"] == "would_require_confirmation"


def test_user_tool_control_policy_combination_regressions():
    from deepseek_responses_proxy.app import _build_user_tool_control_policy_report

    shell_tool = [{"type": "function", "function": {"name": "shell", "parameters": {}}}]

    ordered = _build_user_tool_control_policy_report(
        [{"type": "message", "role": "user", "content": "先解释，再处理目标测试。"}],
        shell_tool,
    )
    assert ordered["user_signal"] == "ordered_explain_then_continue"
    assert ordered["decision_if_enabled"] == "split_turn_required"

    quoted_cn = _build_user_tool_control_policy_report(
        [{"type": "message", "role": "user", "content": "日志里出现“不要调用工具”是什么意思。"}],
        shell_tool,
    )
    assert quoted_cn["user_signal"] == "quoted_or_meta_stop_discussion"
    assert quoted_cn["decision_if_enabled"] == "allow_tools"

    quoted_en = _build_user_tool_control_policy_report(
        [{"type": "message", "role": "user", "content": "What does \"do not use tools\" mean?"}],
        shell_tool,
    )
    assert quoted_en["user_signal"] == "quoted_or_meta_stop_discussion"
    assert quoted_en["decision_if_enabled"] == "allow_tools"

    classify_en = _build_user_tool_control_policy_report(
        [{"type": "message", "role": "user", "content": "If I say \"do not run commands\", how would you classify it?"}],
        shell_tool,
    )
    assert classify_en["user_signal"] == "quoted_or_meta_stop_discussion"
    assert classify_en["decision_if_enabled"] == "allow_tools"


def test_user_tool_control_enabled_turn_control_removes_tools(monkeypatch):
    from deepseek_responses_proxy.app import (
        _apply_user_tool_control_policy_to_tools,
        _build_user_tool_control_policy_report,
    )

    shell_tool = [{"type": "function", "function": {"name": "shell", "parameters": {}}}]

    monkeypatch.setenv("DEEPSEEK_PROXY_USER_TOOL_CONTROL_POLICY_MODE", "enabled")
    report = _build_user_tool_control_policy_report(
        [{"type": "message", "role": "user", "content": "不要继续执行命令，先解释原因。"}],
        shell_tool,
    )
    effective_tools, applied = _apply_user_tool_control_policy_to_tools(report, shell_tool)

    assert effective_tools is None
    assert applied["active"] is True
    assert applied["policy_applied"] is True
    assert applied["effective_mode"] == "enabled"
    assert applied["tools_removed_from_upstream"] == ["shell"]
    assert applied["effective_tool_names"] == []


def test_user_tool_control_dry_run_does_not_remove_tools(monkeypatch):
    from deepseek_responses_proxy.app import (
        _apply_user_tool_control_policy_to_tools,
        _build_user_tool_control_policy_report,
    )

    shell_tool = [{"type": "function", "function": {"name": "shell", "parameters": {}}}]

    monkeypatch.setenv("DEEPSEEK_PROXY_USER_TOOL_CONTROL_POLICY_MODE", "dry_run")
    report = _build_user_tool_control_policy_report(
        [{"type": "message", "role": "user", "content": "不要继续执行命令，先解释原因。"}],
        shell_tool,
    )
    effective_tools, applied = _apply_user_tool_control_policy_to_tools(report, shell_tool)

    assert effective_tools == shell_tool
    assert applied["active"] is False
    assert applied["policy_applied"] is False
    assert applied["policy_is_dry_run_only"] is True
    assert applied["tools_removed_from_upstream"] == []


def test_user_tool_control_enabled_split_turn_removes_tools(monkeypatch):
    from deepseek_responses_proxy.app import (
        _apply_user_tool_control_policy_to_tools,
        _build_user_tool_control_policy_report,
    )

    shell_tool = [{"type": "function", "function": {"name": "shell", "parameters": {}}}]

    monkeypatch.setenv("DEEPSEEK_PROXY_USER_TOOL_CONTROL_POLICY_MODE", "enabled")
    report = _build_user_tool_control_policy_report(
        [{"type": "message", "role": "user", "content": "先解释原因，然后继续执行测试。"}],
        shell_tool,
    )
    effective_tools, applied = _apply_user_tool_control_policy_to_tools(report, shell_tool)

    assert report["user_signal"] == "ordered_explain_then_continue"
    assert report["decision_if_enabled"] == "split_turn_required"
    assert effective_tools is None
    assert applied["active"] is True
    assert applied["tools_removed_from_upstream"] == ["shell"]


def test_user_tool_control_enabled_ambiguous_stop_does_not_remove_tools(monkeypatch):
    from deepseek_responses_proxy.app import (
        _apply_user_tool_control_policy_to_tools,
        _build_user_tool_control_policy_report,
    )

    proxy_status_tool = [{"type": "function", "function": {"name": "proxy_status", "parameters": {}}}]

    monkeypatch.setenv("DEEPSEEK_PROXY_USER_TOOL_CONTROL_POLICY_MODE", "enabled")
    report = _build_user_tool_control_policy_report(
        [{"type": "message", "role": "user", "content": "停一下。"}],
        proxy_status_tool,
    )
    effective_tools, applied = _apply_user_tool_control_policy_to_tools(report, proxy_status_tool)

    assert report["user_signal"] == "ambiguous_stop"
    assert report["decision_if_enabled"] == "observe_only"
    assert effective_tools == proxy_status_tool
    assert applied["active"] is False
    assert applied["policy_applied"] is False


def test_user_tool_control_suppressed_response_replaces_tool_call():
    from deepseek_responses_proxy.app import _user_tool_control_suppressed_deepseek_response

    response = {
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {"name": "proxy_time", "arguments": "{}"},
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ]
    }
    report = {
        "user_signal": "explicit_tool_stop",
        "decision_if_enabled": "would_suppress_tools",
    }
    suppressed = _user_tool_control_suppressed_deepseek_response(
        response,
        report,
        response["choices"][0]["message"]["tool_calls"],
    )

    message = suppressed["choices"][0]["message"]
    assert message["role"] == "assistant"
    assert "No tool calls were run" in message["content"]
    assert "proxy_time" in message["content"]
    assert "tool_calls" not in message
    assert suppressed["choices"][0]["finish_reason"] == "stop"


def test_user_tool_control_enabled_removes_auto_injected_tools_too(monkeypatch):
    from deepseek_responses_proxy.app import (
        _apply_user_tool_control_policy_to_tools,
        _build_user_tool_control_policy_report,
    )

    tools = [
        {"type": "function", "function": {"name": "shell", "parameters": {}}},
        {"type": "function", "function": {"name": "proxy_echo", "parameters": {}}},
        {"type": "function", "function": {"name": "proxy_time", "parameters": {}}},
    ]

    monkeypatch.setenv("DEEPSEEK_PROXY_USER_TOOL_CONTROL_POLICY_MODE", "enabled")
    report = _build_user_tool_control_policy_report(
        [
            {
                "type": "message",
                "role": "user",
                "content": "不要继续执行命令，先解释原因。",
            }
        ],
        tools,
    )
    effective_tools, applied = _apply_user_tool_control_policy_to_tools(report, tools)

    assert effective_tools is None
    assert applied["active"] is True
    assert applied["policy_applied"] is True
    assert applied["original_tool_names"] == ["shell", "proxy_echo", "proxy_time"]
    assert applied["tools_removed_from_upstream"] == ["shell", "proxy_echo", "proxy_time"]
    assert applied["effective_tool_names"] == []


def test_user_tool_command_risk_report_classifies_shell_destructive_dry_run():
    import json
    from deepseek_responses_proxy.app import _build_user_tool_command_risk_report

    report = _build_user_tool_command_risk_report(
        [
            {
                "id": "call_shell",
                "type": "function",
                "function": {
                    "name": "shell",
                    "arguments": json.dumps({"cmd": "rm -rf /tmp/demo"}),
                },
            }
        ],
        phase="test",
        response_id="resp_test",
    )

    assert report["mode"] == "dry_run"
    assert report["active"] is False
    assert report["max_command_risk"] == "C2_routine_side_effect"
    assert report["decision_if_enabled"] == "allow_routine_side_effect"
    assert report["proxy_gate_scope"] == "C4_only_future_gate"
    assert report["codex_is_default_sandbox_boundary"] is True
    assert report["tool_calls"][0]["tool_name"] == "shell"
    assert report["tool_calls"][0]["command_risk"] == "C2_routine_side_effect"
    assert "routine_tmp_cleanup" in report["tool_calls"][0]["candidates"][0]["reasons"]


def test_user_tool_command_risk_report_classifies_apply_patch_update_dry_run():
    import json
    from deepseek_responses_proxy.app import _build_user_tool_command_risk_report

    patch = "*** Begin Patch\\n*** Update File: deepseek_responses_proxy/app.py\\n@@\\n-old\\n+new\\n*** End Patch"
    report = _build_user_tool_command_risk_report(
        [
            {
                "id": "call_patch",
                "type": "function",
                "function": {
                    "name": "apply_patch",
                    "arguments": json.dumps({"input": patch}),
                },
            }
        ],
        phase="test",
    )

    assert report["max_command_risk"] == "C2_routine_side_effect"
    assert report["decision_if_enabled"] == "allow_routine_side_effect"
    assert report["tool_calls"][0]["tool_name_risk"] == "R3_capable_requires_command_audit"
    assert report["tool_calls"][0]["command_risk"] == "C2_routine_side_effect"


def test_user_tool_command_risk_report_observes_readonly_shell_command():
    import json
    from deepseek_responses_proxy.app import _build_user_tool_command_risk_report

    report = _build_user_tool_command_risk_report(
        [
            {
                "id": "call_shell",
                "type": "function",
                "function": {
                    "name": "shell",
                    "arguments": json.dumps({"cmd": "cat README.md | head -n 5"}),
                },
            }
        ],
        phase="test",
    )

    assert report["max_command_risk"] == "C1_readonly_or_unknown"
    assert report["decision_if_enabled"] == "observe_only"
    assert report["tool_calls"][0]["command_risk"] == "C1_readonly_or_unknown"


def test_tool_name_policy_marks_shell_aliases_and_apply_patch_as_command_audit():
    from deepseek_responses_proxy.app import _classify_tool_name_risk_for_policy

    assert _classify_tool_name_risk_for_policy("run_shell") == "R3_capable_requires_command_audit"
    assert _classify_tool_name_risk_for_policy("execute_command") == "R3_capable_requires_command_audit"
    assert _classify_tool_name_risk_for_policy("apply_patch") == "R3_capable_requires_command_audit"


def test_user_tool_command_risk_report_classifies_c4_catastrophic_rm_drive():
    import json
    from deepseek_responses_proxy.app import _build_user_tool_command_risk_report

    report = _build_user_tool_command_risk_report(
        [
            {
                "id": "call_shell",
                "type": "function",
                "function": {
                    "name": "shell",
                    "arguments": json.dumps({"cmd": "rm -rf /mnt/d/*"}),
                },
            }
        ],
        phase="test",
    )

    assert report["max_command_risk"] == "C4_catastrophic_or_out_of_sandbox"
    assert report["decision_if_enabled"] == "would_require_c4_confirmation"
    assert report["tool_calls"][0]["codex_sandbox_boundary"] is False
    assert "catastrophic_rm_root_home_or_drive" in report["tool_calls"][0]["candidates"][0]["reasons"]


def test_user_tool_command_risk_report_classifies_write_file_as_codex_governed_not_proxy_blocked():
    import json
    from deepseek_responses_proxy.app import _build_user_tool_command_risk_report

    report = _build_user_tool_command_risk_report(
        [
            {
                "id": "call_write",
                "type": "function",
                "function": {
                    "name": "write_file",
                    "arguments": json.dumps({"path": "docs/new.md", "content": "hello"}),
                },
            }
        ],
        phase="test",
    )

    assert report["max_command_risk"] == "C3_codex_governed_destructive"
    assert report["decision_if_enabled"] == "allow_codex_governed"
    assert report["tool_calls"][0]["tool_name_risk"] == "R3_destructive_or_overwrite"
    assert report["tool_calls"][0]["codex_sandbox_boundary"] is True


def test_user_tool_command_risk_report_c4_gate_fields_trigger_only_for_c4():
    import json
    from deepseek_responses_proxy.app import _build_user_tool_command_risk_report

    safe_report = _build_user_tool_command_risk_report(
        [
            {
                "id": "call_tmp",
                "type": "function",
                "function": {
                    "name": "shell",
                    "arguments": json.dumps({"cmd": "rm -rf /tmp/demo"}),
                },
            },
            {
                "id": "call_patch",
                "type": "function",
                "function": {
                    "name": "apply_patch",
                    "arguments": json.dumps(
                        {
                            "input": "*** Begin Patch\n*** Update File: deepseek_responses_proxy/app.py\n*** End Patch"
                        }
                    ),
                },
            },
        ],
        phase="test",
    )

    assert safe_report["max_command_risk"] == "C2_routine_side_effect"
    assert safe_report["c4_gate_mode"] == "dry_run_fields_only"
    assert safe_report["c4_gate_triggered"] is False
    assert safe_report["c4_gate_action"] == "allow"
    assert safe_report["c4_gate_tool_call_ids"] == []
    assert safe_report["c4_gate_confirmation_required"] is False
    assert safe_report["c4_gate_resume_supported"] is False
    assert safe_report["c4_gate_effective"] is False

    c4_report = _build_user_tool_command_risk_report(
        [
            {
                "id": "call_c4",
                "type": "function",
                "function": {
                    "name": "shell",
                    "arguments": json.dumps({"cmd": "rm -rf /mnt/d/*"}),
                },
            }
        ],
        phase="test",
    )

    assert c4_report["max_command_risk"] == "C4_catastrophic_or_out_of_sandbox"
    assert c4_report["decision_if_enabled"] == "would_require_c4_confirmation"
    assert c4_report["c4_gate_mode"] == "dry_run_fields_only"
    assert c4_report["c4_gate_triggered"] is True
    assert c4_report["c4_gate_action"] == "would_suppress_and_explain"
    assert c4_report["c4_gate_tool_call_ids"] == ["call_c4"]
    assert c4_report["c4_gate_tool_names"] == ["shell"]
    assert "catastrophic_rm_root_home_or_drive" in c4_report["c4_gate_reasons"]
    assert c4_report["c4_gate_confirmation_required"] is True
    assert c4_report["c4_gate_resume_supported"] is False
    assert c4_report["c4_gate_effective"] is False
    assert c4_report["c4_gate_argument_previews"][0]["tool_call_id"] == "call_c4"


def test_user_tool_command_risk_report_c3_remains_codex_governed_not_c4_gate():
    import json
    from deepseek_responses_proxy.app import _build_user_tool_command_risk_report

    report = _build_user_tool_command_risk_report(
        [
            {
                "id": "call_write",
                "type": "function",
                "function": {
                    "name": "write_file",
                    "arguments": json.dumps({"path": "docs/new.md", "content": "hello"}),
                },
            }
        ],
        phase="test",
    )

    assert report["max_command_risk"] == "C3_codex_governed_destructive"
    assert report["decision_if_enabled"] == "allow_codex_governed"
    assert report["c4_gate_triggered"] is False
    assert report["c4_gate_action"] == "allow"
    assert report["c4_gate_confirmation_required"] is False
    assert report["c4_gate_effective"] is False


def test_user_tool_command_risk_enabled_c4_suppresses_deepseek_response(monkeypatch):
    import json
    from deepseek_responses_proxy.app import (
        _build_user_tool_command_risk_report,
        _user_tool_command_risk_should_suppress_tool_calls,
        _user_tool_command_risk_suppressed_deepseek_response,
    )

    monkeypatch.setenv("DEEPSEEK_PROXY_COMMAND_RISK_POLICY_MODE", "enabled")
    report = _build_user_tool_command_risk_report(
        [
            {
                "id": "call_c4",
                "type": "function",
                "function": {
                    "name": "shell",
                    "arguments": json.dumps({"cmd": "rm -rf /mnt/d/*"}),
                },
            }
        ],
        phase="test",
    )

    assert _user_tool_command_risk_should_suppress_tool_calls(report) is True
    assert report["c4_gate_triggered"] is True
    assert report["c4_gate_effective"] is False

    report["active"] = True
    report["c4_gate_effective"] = True
    report["c4_gate_action"] = "suppress_and_explain"

    response = {
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": "call_c4",
                            "type": "function",
                            "function": {
                                "name": "shell",
                                "arguments": json.dumps({"cmd": "rm -rf /mnt/d/*"}),
                            },
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ]
    }

    suppressed = _user_tool_command_risk_suppressed_deepseek_response(response, report)
    message = suppressed["choices"][0]["message"]
    assert message["role"] == "assistant"
    assert "tool_calls" not in message
    assert "已阻止C4级高风险工具调用" in message["content"]
    assert "不支持通过“继续”自动恢复执行" in message["content"]
    assert suppressed["choices"][0]["finish_reason"] == "stop"


def test_user_tool_command_risk_dry_run_c4_does_not_suppress(monkeypatch):
    import json
    from deepseek_responses_proxy.app import (
        _build_user_tool_command_risk_report,
        _user_tool_command_risk_should_suppress_tool_calls,
    )

    monkeypatch.setenv("DEEPSEEK_PROXY_COMMAND_RISK_POLICY_MODE", "dry_run")
    report = _build_user_tool_command_risk_report(
        [
            {
                "id": "call_c4",
                "type": "function",
                "function": {
                    "name": "shell",
                    "arguments": json.dumps({"cmd": "rm -rf /mnt/d/*"}),
                },
            }
        ],
        phase="test",
    )

    assert report["max_command_risk"] == "C4_catastrophic_or_out_of_sandbox"
    assert report["c4_gate_triggered"] is True
    assert report["c4_gate_effective"] is False
    assert _user_tool_command_risk_should_suppress_tool_calls(report) is False


def test_user_tool_command_risk_enabled_c3_does_not_suppress(monkeypatch):
    import json
    from deepseek_responses_proxy.app import (
        _build_user_tool_command_risk_report,
        _user_tool_command_risk_should_suppress_tool_calls,
    )

    monkeypatch.setenv("DEEPSEEK_PROXY_COMMAND_RISK_POLICY_MODE", "enabled")
    report = _build_user_tool_command_risk_report(
        [
            {
                "id": "call_write",
                "type": "function",
                "function": {
                    "name": "write_file",
                    "arguments": json.dumps({"path": "docs/new.md", "content": "hello"}),
                },
            }
        ],
        phase="test",
    )

    assert report["max_command_risk"] == "C3_codex_governed_destructive"
    assert report["c4_gate_triggered"] is False
    assert report["c4_gate_action"] == "allow"
    assert _user_tool_command_risk_should_suppress_tool_calls(report) is False


async def test_run_chat_with_tool_bridge_enabled_c4_suppresses_before_tool_execution(monkeypatch, tmp_path):
    import importlib
    import json

    app = importlib.import_module("deepseek_responses_proxy.app")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DEEPSEEK_PROXY_COMMAND_RISK_POLICY_MODE", "enabled")
    monkeypatch.setenv("DEEPSEEK_PROXY_TOOL_BRIDGE", "1")
    monkeypatch.setenv("DEEPSEEK_PROXY_TOOL_MAX_ROUNDS", "1")

    async def fake_chat_completions_with_usage(**kwargs):
        return {
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "tool_calls": [
                            {
                                "id": "call_c4",
                                "type": "function",
                                "function": {
                                    "name": "shell",
                                    "arguments": json.dumps({"cmd": "rm -rf /mnt/d/*"}),
                                },
                            }
                        ],
                    },
                    "finish_reason": "tool_calls",
                }
            ]
        }

    async def forbidden_execute_proxy_tool_call(*args, **kwargs):
        raise AssertionError("C4 gate should suppress before proxy tool execution")

    monkeypatch.setattr(app, "_chat_completions_with_usage", fake_chat_completions_with_usage)
    monkeypatch.setattr(app, "_execute_proxy_tool_call", forbidden_execute_proxy_tool_call)

    response, history = await app._run_chat_with_tool_bridge(
        deepseek_client=object(),
        chat_payload={"messages": []},
        messages_for_deepseek=[],
        history_messages=[],
        model="deepseek-test",
        deepseek_tools=[{"type": "function", "function": {"name": "shell", "parameters": {}}}],
        reasoning_effort=None,
        request_payload={"model": "deepseek-test"},
        response_id="resp_test",
    )

    assert history == []
    message = response["choices"][0]["message"]
    assert message["role"] == "assistant"
    assert "tool_calls" not in message
    assert "已阻止C4级高风险工具调用" in message["content"]

    report_path = tmp_path / ".debug" / "user_tool_command_risk_report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["mode"] == "enabled"
    assert report["active"] is True
    assert report["c4_gate_triggered"] is True
    assert report["c4_gate_effective"] is True
    assert report["c4_gate_action"] == "suppress_and_explain"
    assert report["c4_gate_resume_supported"] is False
