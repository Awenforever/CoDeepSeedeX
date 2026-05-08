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
    monkeypatch.delenv("DEEPSEEK_PROXY_MCP_EXECUTOR", raising=False)
    monkeypatch.setenv("DEEPSEEK_PROXY_MCP_READONLY_ALLOWLIST", "memory_router.memory_query")

    decision = _mcp_executor_policy_decision("mcp__memory_router__memory_query")

    assert decision["ok"] is False
    assert decision["kind"] == "mcp_executor_disabled"
    assert decision["server"] == "memory_router"
    assert decision["name"] == "memory_query"


def test_mcp_executor_allows_any_server_tool_when_explicitly_allowlisted(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_PROXY_MCP_EXECUTOR", "1")
    monkeypatch.setenv("DEEPSEEK_PROXY_MCP_READONLY_ALLOWLIST", "custom_server.safe_tool")

    decision = _mcp_executor_policy_decision("mcp__custom_server__safe_tool")

    assert decision["ok"] is True
    assert decision["kind"] == "allowed_readonly"
    assert decision["permission"] == "readonly"
    assert decision["policy_key"] == "custom_server.safe_tool"


def test_mcp_executor_does_not_special_case_memory_router(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_PROXY_MCP_EXECUTOR", "1")
    monkeypatch.setenv("DEEPSEEK_PROXY_MCP_READONLY_ALLOWLIST", "cheap_llm.cheap_router_status")

    memory_decision = _mcp_executor_policy_decision("mcp__memory_router__memory_query")
    cheap_decision = _mcp_executor_policy_decision("mcp__cheap_llm__cheap_router_status")

    assert memory_decision["ok"] is False
    assert memory_decision["kind"] == "mcp_tool_not_allowed"
    assert cheap_decision["ok"] is True
    assert cheap_decision["kind"] == "allowed_readonly"


def test_mcp_executor_write_allowlist_is_still_denied_by_default(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_PROXY_MCP_EXECUTOR", "1")
    monkeypatch.setenv("DEEPSEEK_PROXY_MCP_WRITE_ALLOWLIST", "memory_router.memory_remember")

    decision = _mcp_executor_policy_decision("mcp__memory_router__memory_remember")

    assert decision["ok"] is False
    assert decision["kind"] == "mcp_write_denied"
    assert decision["permission"] == "write"


def test_mcp_executor_denied_result_is_structured(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_PROXY_MCP_EXECUTOR", "1")
    monkeypatch.delenv("DEEPSEEK_PROXY_MCP_READONLY_ALLOWLIST", raising=False)

    result = _mcp_executor_denied_result("mcp__unknown__tool")

    assert result["ok"] is False
    assert result["error"] == "mcp_tool_not_allowed"
    assert result["mcp"] == {
        "server": "unknown",
        "name": "tool",
        "namespace": "mcp__unknown__",
        "policy_key": "unknown.tool",
    }

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
    monkeypatch.setenv("DEEPSEEK_PROXY_MCP_EXECUTOR", "1")
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
async def test_mcp_write_tool_call_is_denied_even_when_write_allowlisted(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DEEPSEEK_PROXY_TOOL_BRIDGE", "1")
    monkeypatch.setenv("DEEPSEEK_PROXY_AGENT_LIVENESS_GUARD", "0")
    monkeypatch.setenv("DEEPSEEK_PROXY_MCP_EXECUTOR", "1")
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
            _response({"role": "assistant", "content": "Write denied."}),
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

    assert deepseek_response["choices"][0]["message"]["content"] == "Write denied."
    tool_payloads = _payloads_with_tool_messages(fake.payloads)
    assert len(tool_payloads) == 1
    tool_messages = [m for m in tool_payloads[0]["messages"] if m.get("role") == "tool"]
    result = json.loads(tool_messages[0]["content"])
    assert result["ok"] is False
    assert result["error"] == "mcp_write_denied"
    assert result["mcp"]["permission"] == "write"
