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
