from deepseek_responses_proxy.app import (
    _mcp_executor_denied_result,
    _mcp_executor_policy_decision,
    _parse_mcp_proxy_tool_name,
)


def test_parse_mcp_proxy_tool_name_is_generic():
    parsed = _parse_mcp_proxy_tool_name("mcp__arbitrary_server__arbitrary_tool")

    assert parsed == {
        "server": "arbitrary_server",
        "name": "arbitrary_tool",
        "namespace": "mcp__arbitrary_server__",
        "function_name": "mcp__arbitrary_server__arbitrary_tool",
        "policy_key": "arbitrary_server.arbitrary_tool",
    }


def test_parse_mcp_proxy_tool_name_rejects_non_mcp_names():
    assert _parse_mcp_proxy_tool_name("proxy_status") is None
    assert _parse_mcp_proxy_tool_name("mcp__missing_tool") is None
    assert _parse_mcp_proxy_tool_name("") is None


def test_mcp_executor_is_disabled_by_default(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_PROXY_MCP_POLICY", "off")
    monkeypatch.delenv("DEEPSEEK_PROXY_MCP_EXECUTOR", raising=False)
    monkeypatch.setenv("DEEPSEEK_PROXY_MCP_READONLY_ALLOWLIST", "memory_router.memory_query")

    decision = _mcp_executor_policy_decision("mcp__memory_router__memory_query")

    assert decision["ok"] is False
    assert decision["kind"] == "mcp_executor_disabled"
    assert decision["policy"] == "off"



def test_mcp_executor_allows_any_server_tool_when_explicitly_allowlisted(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_PROXY_MCP_POLICY", "allowlist")
    monkeypatch.setenv("DEEPSEEK_PROXY_MCP_EXECUTOR", "1")
    monkeypatch.setenv("DEEPSEEK_PROXY_MCP_READONLY_ALLOWLIST", "custom_server.safe_tool")

    decision = _mcp_executor_policy_decision("mcp__custom_server__safe_tool")

    assert decision["ok"] is True
    assert decision["kind"] == "allowed_readonly"
    assert decision["permission"] == "readonly"
    assert decision["policy"] == "allowlist"
    assert decision["server"] == "custom_server"
    assert decision["name"] == "safe_tool"
    assert decision["policy_key"] == "custom_server.safe_tool"



def test_mcp_executor_does_not_special_case_memory_router(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_PROXY_MCP_POLICY", "allowlist")
    monkeypatch.setenv("DEEPSEEK_PROXY_MCP_EXECUTOR", "1")
    monkeypatch.setenv("DEEPSEEK_PROXY_MCP_READONLY_ALLOWLIST", "cheap_llm.cheap_router_status")

    memory_decision = _mcp_executor_policy_decision("mcp__memory_router__memory_query")
    cheap_decision = _mcp_executor_policy_decision("mcp__cheap_llm__cheap_router_status")

    assert memory_decision["ok"] is False
    assert memory_decision["kind"] == "mcp_tool_not_allowed"
    assert memory_decision["policy"] == "allowlist"

    assert cheap_decision["ok"] is True
    assert cheap_decision["kind"] == "allowed_readonly"
    assert cheap_decision["permission"] == "readonly"
    assert cheap_decision["policy"] == "allowlist"



def test_mcp_executor_write_allowlist_is_still_denied_by_default(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_PROXY_MCP_POLICY", "allowlist")
    monkeypatch.setenv("DEEPSEEK_PROXY_MCP_EXECUTOR", "1")
    monkeypatch.setenv("DEEPSEEK_PROXY_MCP_WRITE_ALLOWLIST", "memory_router.memory_remember")

    decision = _mcp_executor_policy_decision("mcp__memory_router__memory_remember")

    assert decision["ok"] is True
    assert decision["kind"] == "allowed_write"
    assert decision["permission"] == "write"
    assert decision["policy"] == "allowlist"



def test_mcp_executor_denied_result_is_structured(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_PROXY_MCP_POLICY", "allowlist")
    monkeypatch.setenv("DEEPSEEK_PROXY_MCP_EXECUTOR", "1")
    monkeypatch.delenv("DEEPSEEK_PROXY_MCP_READONLY_ALLOWLIST", raising=False)
    monkeypatch.delenv("DEEPSEEK_PROXY_MCP_WRITE_ALLOWLIST", raising=False)

    result = _mcp_executor_denied_result("mcp__unknown__tool")

    assert result["ok"] is False
    assert result["error"] == "mcp_tool_not_allowed"
    assert result["mcp"]["server"] == "unknown"
    assert result["mcp"]["name"] == "tool"


import json
import pytest

from deepseek_responses_proxy.app import _run_chat_with_tool_bridge


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


def _payloads_with_tool_messages(payloads):
    return [
        payload
        for payload in payloads
        if any(message.get("role") == "tool" for message in payload.get("messages", []))
    ]


@pytest.mark.asyncio
async def test_mcp_tool_call_is_handled_by_proxy_bridge_as_structured_denial(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DEEPSEEK_PROXY_TOOL_BRIDGE", "1")
    monkeypatch.setenv("DEEPSEEK_PROXY_AGENT_LIVENESS_GUARD", "0")
    monkeypatch.setenv("DEEPSEEK_PROXY_MCP_POLICY", "allowlist")
    monkeypatch.setenv("DEEPSEEK_PROXY_MCP_EXECUTOR", "1")
    monkeypatch.setenv("DEEPSEEK_PROXY_MCP_EXECUTOR_BACKEND", "none")
    monkeypatch.setenv("DEEPSEEK_PROXY_MCP_READONLY_ALLOWLIST", "memory_router.memory_query")

    fake = FakeDeepSeekClient(
        [
            _response(
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_memory",
                            "type": "function",
                            "function": {
                                "name": "mcp__memory_router__memory_query",
                                "arguments": json.dumps({"query": "test"}),
                            },
                        }
                    ],
                }
            ),
            _response({"role": "assistant", "content": "I received a structured MCP denial."}),
        ]
    )

    deepseek_response, history = await _run_chat_with_tool_bridge(
        deepseek_client=fake,
        chat_payload={
            "model": "deepseek-v4-pro",
            "messages": [{"role": "user", "content": "check memory"}],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "mcp__memory_router__memory_query",
                        "parameters": {"type": "object", "properties": {}},
                    },
                }
            ],
        },
        messages_for_deepseek=[{"role": "user", "content": "check memory"}],
        history_messages=[{"role": "user", "content": "check memory"}],
        model="deepseek-v4-pro",
        deepseek_tools=[
            {
                "type": "function",
                "function": {
                    "name": "mcp__memory_router__memory_query",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ],
        reasoning_effort=None,
        request_payload={},
    )

    assert deepseek_response["choices"][0]["message"]["content"] == "I received a structured MCP denial."
    tool_payloads = _payloads_with_tool_messages(fake.payloads)
    assert len(tool_payloads) == 1
    tool_messages = [m for m in tool_payloads[0]["messages"] if m.get("role") == "tool"]
    assert len(tool_messages) == 1
    result = json.loads(tool_messages[0]["content"])
    assert result["ok"] is False
    assert result["tool"] == "mcp__memory_router__memory_query"
    assert result["error"] == "mcp_executor_backend_unavailable"
    assert result["mcp"]["server"] == "memory_router"
    assert result["mcp"]["permission"] == "readonly"
    assert history[-1]["role"] == "tool"


@pytest.mark.asyncio
@pytest.mark.asyncio
async def test_mcp_write_tool_call_is_denied_even_when_write_allowlisted(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DEEPSEEK_PROXY_TOOL_BRIDGE", "1")
    monkeypatch.setenv("DEEPSEEK_PROXY_AGENT_LIVENESS_GUARD", "0")
    monkeypatch.setenv("DEEPSEEK_PROXY_MCP_POLICY", "allowlist")
    monkeypatch.setenv("DEEPSEEK_PROXY_MCP_EXECUTOR", "1")
    monkeypatch.setenv("DEEPSEEK_PROXY_MCP_EXECUTOR_BACKEND", "none")
    monkeypatch.setenv("DEEPSEEK_PROXY_MCP_WRITE_ALLOWLIST", "memory_router.memory_remember")

    fake = FakeDeepSeekClient(
        [
            _response(
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_write",
                            "type": "function",
                            "function": {
                                "name": "mcp__memory_router__memory_remember",
                                "arguments": json.dumps({"text": "persist this"}),
                            },
                        }
                    ],
                }
            ),
            _response({"role": "assistant", "content": "Write backend unavailable."}),
        ]
    )

    deepseek_response, _history = await _run_chat_with_tool_bridge(
        deepseek_client=fake,
        chat_payload={
            "model": "deepseek-v4-pro",
            "messages": [{"role": "user", "content": "remember this"}],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "mcp__memory_router__memory_remember",
                        "parameters": {"type": "object", "properties": {}},
                    },
                }
            ],
        },
        messages_for_deepseek=[{"role": "user", "content": "remember this"}],
        history_messages=[{"role": "user", "content": "remember this"}],
        model="deepseek-v4-pro",
        deepseek_tools=[
            {
                "type": "function",
                "function": {
                    "name": "mcp__memory_router__memory_remember",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ],
        reasoning_effort=None,
        request_payload={},
    )

    assert deepseek_response["choices"][0]["message"]["content"] == "Write backend unavailable."
    tool_payloads = _payloads_with_tool_messages(fake.payloads)
    assert len(tool_payloads) == 1
    tool_messages = [m for m in tool_payloads[0]["messages"] if m.get("role") == "tool"]
    result = json.loads(tool_messages[0]["content"])
    assert result["ok"] is False
    assert result["error"] == "mcp_executor_backend_unavailable"
    assert result["mcp"]["permission"] == "write"


@pytest.mark.asyncio
@pytest.mark.asyncio
async def test_mcp_readonly_allowed_tool_executes_via_injected_backend(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DEEPSEEK_PROXY_TOOL_BRIDGE", "1")
    monkeypatch.setenv("DEEPSEEK_PROXY_AGENT_LIVENESS_GUARD", "0")
    monkeypatch.setenv("DEEPSEEK_PROXY_MCP_POLICY", "allowlist")
    monkeypatch.setenv("DEEPSEEK_PROXY_MCP_EXECUTOR", "1")
    monkeypatch.setenv("DEEPSEEK_PROXY_MCP_READONLY_ALLOWLIST", "custom_server.safe_tool")

    from deepseek_responses_proxy.app import _set_mcp_executor_backend_for_tests

    calls = []

    async def fake_backend(*, server, tool, arguments, decision):
        calls.append(
            {
                "server": server,
                "tool": tool,
                "arguments": arguments,
                "decision": decision,
            }
        )
        return {
            "answer": "fake result",
            "received": arguments,
        }

    _set_mcp_executor_backend_for_tests(fake_backend)
    try:
        fake = FakeDeepSeekClient(
            [
                _response(
                    {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_custom",
                                "type": "function",
                                "function": {
                                    "name": "mcp__custom_server__safe_tool",
                                    "arguments": json.dumps({"q": "hello"}),
                                },
                            }
                        ],
                    }
                ),
                _response({"role": "assistant", "content": "Fake MCP result consumed."}),
            ]
        )

        deepseek_response, history = await _run_chat_with_tool_bridge(
            deepseek_client=fake,
            chat_payload={
                "model": "deepseek-v4-pro",
                "messages": [{"role": "user", "content": "use custom mcp"}],
                "tools": [
                    {
                        "type": "function",
                        "function": {
                            "name": "mcp__custom_server__safe_tool",
                            "parameters": {"type": "object", "properties": {}},
                        },
                    }
                ],
            },
            messages_for_deepseek=[{"role": "user", "content": "use custom mcp"}],
            history_messages=[{"role": "user", "content": "use custom mcp"}],
            model="deepseek-v4-pro",
            deepseek_tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "mcp__custom_server__safe_tool",
                        "parameters": {"type": "object", "properties": {}},
                    },
                }
            ],
            reasoning_effort=None,
            request_payload={},
        )
    finally:
        _set_mcp_executor_backend_for_tests(None)

    assert deepseek_response["choices"][0]["message"]["content"] == "Fake MCP result consumed."
    assert calls == [
        {
            "server": "custom_server",
            "tool": "safe_tool",
            "arguments": {"q": "hello"},
            "decision": {
                "ok": True,
                "kind": "allowed_readonly",
                "permission": "readonly",
                "policy": "allowlist",
                "server": "custom_server",
                "name": "safe_tool",
                "namespace": "mcp__custom_server__",
                "function_name": "mcp__custom_server__safe_tool",
                "policy_key": "custom_server.safe_tool",
            },
        }
    ]

    tool_payloads = _payloads_with_tool_messages(fake.payloads)
    assert len(tool_payloads) == 1
    tool_messages = [m for m in tool_payloads[0]["messages"] if m.get("role") == "tool"]
    result = json.loads(tool_messages[0]["content"])
    assert result["ok"] is True
    assert result["tool"] == "mcp__custom_server__safe_tool"
    assert result["mcp"]["server"] == "custom_server"
    assert result["mcp"]["permission"] == "readonly"
    assert result["result"] == {"answer": "fake result", "received": {"q": "hello"}}
    assert history[-1]["role"] == "tool"



@pytest.mark.asyncio
async def test_mcp_backend_exception_returns_structured_tool_error(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DEEPSEEK_PROXY_TOOL_BRIDGE", "1")
    monkeypatch.setenv("DEEPSEEK_PROXY_AGENT_LIVENESS_GUARD", "0")
    monkeypatch.setenv("DEEPSEEK_PROXY_MCP_EXECUTOR", "1")
    monkeypatch.setenv("DEEPSEEK_PROXY_MCP_READONLY_ALLOWLIST", "custom_server.safe_tool")

    from deepseek_responses_proxy.app import _set_mcp_executor_backend_for_tests

    async def failing_backend(*, server, tool, arguments, decision):
        raise RuntimeError("boom")

    _set_mcp_executor_backend_for_tests(failing_backend)
    try:
        fake = FakeDeepSeekClient(
            [
                _response(
                    {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_custom",
                                "type": "function",
                                "function": {
                                    "name": "mcp__custom_server__safe_tool",
                                    "arguments": json.dumps({"q": "hello"}),
                                },
                            }
                        ],
                    }
                ),
                _response({"role": "assistant", "content": "Handled backend failure."}),
            ]
        )

        deepseek_response, _history = await _run_chat_with_tool_bridge(
            deepseek_client=fake,
            chat_payload={
                "model": "deepseek-v4-pro",
                "messages": [{"role": "user", "content": "use custom mcp"}],
                "tools": [
                    {
                        "type": "function",
                        "function": {
                            "name": "mcp__custom_server__safe_tool",
                            "parameters": {"type": "object", "properties": {}},
                        },
                    }
                ],
            },
            messages_for_deepseek=[{"role": "user", "content": "use custom mcp"}],
            history_messages=[{"role": "user", "content": "use custom mcp"}],
            model="deepseek-v4-pro",
            deepseek_tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "mcp__custom_server__safe_tool",
                        "parameters": {"type": "object", "properties": {}},
                    },
                }
            ],
            reasoning_effort=None,
            request_payload={},
        )
    finally:
        _set_mcp_executor_backend_for_tests(None)

    assert deepseek_response["choices"][0]["message"]["content"] == "Handled backend failure."
    tool_payloads = _payloads_with_tool_messages(fake.payloads)
    assert len(tool_payloads) == 1
    tool_messages = [m for m in tool_payloads[0]["messages"] if m.get("role") == "tool"]
    result = json.loads(tool_messages[0]["content"])
    assert result["ok"] is False
    assert result["error"] == "mcp_executor_backend_failed"
    assert result["message"] == "boom"
    assert result["mcp"]["server"] == "custom_server"
