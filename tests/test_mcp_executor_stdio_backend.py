import json
import sys
from pathlib import Path

import pytest

from tests.test_mcp_executor_gated import FakeDeepSeekClient, _payloads_with_tool_messages, _response

from deepseek_responses_proxy.app import _run_chat_with_tool_bridge


def _write_fake_mcp_server(path: Path) -> None:
    path.write_text(
        r'''
import json
import sys

TOOLS = [
    {
        "name": "safe_tool",
        "description": "A fake readonly tool.",
        "inputSchema": {"type": "object", "properties": {"q": {"type": "string"}}}
    }
]

for line in sys.stdin:
    msg = json.loads(line)
    method = msg.get("method")
    if method == "initialize":
        print(json.dumps({
            "jsonrpc": "2.0",
            "id": msg["id"],
            "result": {
                "protocolVersion": msg.get("params", {}).get("protocolVersion"),
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "fake-stdio-backend", "version": "0.0.1"}
            }
        }), flush=True)
    elif method == "notifications/initialized":
        continue
    elif method == "tools/list":
        print(json.dumps({
            "jsonrpc": "2.0",
            "id": msg["id"],
            "result": {"tools": TOOLS}
        }), flush=True)
    elif method == "tools/call":
        params = msg.get("params", {})
        print(json.dumps({
            "jsonrpc": "2.0",
            "id": msg["id"],
            "result": {
                "content": [{"type": "text", "text": "called " + params.get("name", "")}],
                "isError": False,
                "structuredContent": {
                    "name": params.get("name"),
                    "arguments": params.get("arguments", {})
                }
            }
        }), flush=True)
''',
        encoding="utf-8",
    )


@pytest.mark.asyncio
async def test_stdio_backend_executes_readonly_allowlisted_mcp_tool(tmp_path, monkeypatch):
    server = tmp_path / "fake_mcp_server.py"
    _write_fake_mcp_server(server)

    config = tmp_path / "config.toml"
    config.write_text(
        f'''
[mcp_servers.fake]
command = "{sys.executable}"
args = ["{server}"]
startup_timeout_sec = 5.0
tool_timeout_sec = 5.0

[mcp_servers.fake.tools.safe_tool]
approval_mode = "approve"
''',
        encoding="utf-8",
    )

    monkeypatch.setenv("DEEPSEEK_PROXY_MCP_CONFIG_PATH", str(config))
    monkeypatch.setenv("DEEPSEEK_PROXY_TOOL_BRIDGE", "1")
    monkeypatch.setenv("DEEPSEEK_PROXY_AGENT_LIVENESS_GUARD", "0")
    monkeypatch.setenv("DEEPSEEK_PROXY_MCP_EXECUTOR", "1")
    monkeypatch.setenv("DEEPSEEK_PROXY_MCP_EXECUTOR_BACKEND", "stdio")
    monkeypatch.setenv("DEEPSEEK_PROXY_MCP_READONLY_ALLOWLIST", "fake.safe_tool")

    fake = FakeDeepSeekClient(
        [
            _response(
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_safe",
                            "type": "function",
                            "function": {
                                "name": "mcp__fake__safe_tool",
                                "arguments": json.dumps({"q": "hello"}),
                            },
                        }
                    ],
                }
            ),
            _response({"role": "assistant", "content": "Readonly MCP result consumed."}),
        ]
    )

    deepseek_response, history = await _run_chat_with_tool_bridge(
        deepseek_client=fake,
        chat_payload={
            "model": "deepseek-v4-pro",
            "messages": [{"role": "user", "content": "use fake mcp"}],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "mcp__fake__safe_tool",
                        "parameters": {"type": "object", "properties": {}},
                    },
                }
            ],
        },
        messages_for_deepseek=[{"role": "user", "content": "use fake mcp"}],
        history_messages=[{"role": "user", "content": "use fake mcp"}],
        model="deepseek-v4-pro",
        deepseek_tools=[
            {
                "type": "function",
                "function": {
                    "name": "mcp__fake__safe_tool",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ],
        reasoning_effort=None,
        request_payload={},
    )

    assert deepseek_response["choices"][0]["message"]["content"] == "Readonly MCP result consumed."

    tool_payloads = _payloads_with_tool_messages(fake.payloads)
    assert len(tool_payloads) == 1
    tool_messages = [m for m in tool_payloads[0]["messages"] if m.get("role") == "tool"]
    result = json.loads(tool_messages[0]["content"])

    assert result["ok"] is True
    assert result["tool"] == "mcp__fake__safe_tool"
    assert result["mcp"]["server"] == "fake"
    assert result["mcp"]["permission"] == "readonly"
    assert result["result"]["structuredContent"] == {
        "name": "safe_tool",
        "arguments": {"q": "hello"},
    }
    assert result["discovery"]["ok"] is True
    assert history[-1]["role"] == "tool"


@pytest.mark.asyncio
async def test_stdio_backend_refuses_tool_not_discovered(tmp_path, monkeypatch):
    server = tmp_path / "fake_mcp_server.py"
    _write_fake_mcp_server(server)

    config = tmp_path / "config.toml"
    config.write_text(
        f'''
[mcp_servers.fake]
command = "{sys.executable}"
args = ["{server}"]
startup_timeout_sec = 5.0
tool_timeout_sec = 5.0

[mcp_servers.fake.tools.missing_tool]
approval_mode = "approve"
''',
        encoding="utf-8",
    )

    monkeypatch.setenv("DEEPSEEK_PROXY_MCP_CONFIG_PATH", str(config))
    monkeypatch.setenv("DEEPSEEK_PROXY_TOOL_BRIDGE", "1")
    monkeypatch.setenv("DEEPSEEK_PROXY_AGENT_LIVENESS_GUARD", "0")
    monkeypatch.setenv("DEEPSEEK_PROXY_MCP_EXECUTOR", "1")
    monkeypatch.setenv("DEEPSEEK_PROXY_MCP_EXECUTOR_BACKEND", "stdio")
    monkeypatch.setenv("DEEPSEEK_PROXY_MCP_READONLY_ALLOWLIST", "fake.missing_tool")

    fake = FakeDeepSeekClient(
        [
            _response(
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_missing",
                            "type": "function",
                            "function": {
                                "name": "mcp__fake__missing_tool",
                                "arguments": "{}",
                            },
                        }
                    ],
                }
            ),
            _response({"role": "assistant", "content": "Missing MCP tool handled."}),
        ]
    )

    deepseek_response, _history = await _run_chat_with_tool_bridge(
        deepseek_client=fake,
        chat_payload={
            "model": "deepseek-v4-pro",
            "messages": [{"role": "user", "content": "use fake mcp"}],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "mcp__fake__missing_tool",
                        "parameters": {"type": "object", "properties": {}},
                    },
                }
            ],
        },
        messages_for_deepseek=[{"role": "user", "content": "use fake mcp"}],
        history_messages=[{"role": "user", "content": "use fake mcp"}],
        model="deepseek-v4-pro",
        deepseek_tools=[
            {
                "type": "function",
                "function": {
                    "name": "mcp__fake__missing_tool",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ],
        reasoning_effort=None,
        request_payload={},
    )

    assert deepseek_response["choices"][0]["message"]["content"] == "Missing MCP tool handled."
    tool_payloads = _payloads_with_tool_messages(fake.payloads)
    result = json.loads([m for m in tool_payloads[0]["messages"] if m.get("role") == "tool"][0]["content"])
    assert result["ok"] is False
    assert result["error"] == "mcp_tool_not_discovered"
    assert result["discovery"]["tool_names"] == ["safe_tool"]


@pytest.mark.asyncio
async def test_stdio_backend_keeps_write_tools_denied(tmp_path, monkeypatch):
    config = tmp_path / "config.toml"
    config.write_text(
        '''
[mcp_servers.fake]
command = "/tmp/does-not-matter"
args = []
''',
        encoding="utf-8",
    )

    monkeypatch.setenv("DEEPSEEK_PROXY_MCP_CONFIG_PATH", str(config))
    monkeypatch.setenv("DEEPSEEK_PROXY_TOOL_BRIDGE", "1")
    monkeypatch.setenv("DEEPSEEK_PROXY_AGENT_LIVENESS_GUARD", "0")
    monkeypatch.setenv("DEEPSEEK_PROXY_MCP_EXECUTOR", "1")
    monkeypatch.setenv("DEEPSEEK_PROXY_MCP_EXECUTOR_BACKEND", "stdio")
    monkeypatch.setenv("DEEPSEEK_PROXY_MCP_WRITE_ALLOWLIST", "fake.write_tool")

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
                                "name": "mcp__fake__write_tool",
                                "arguments": "{}",
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
            "messages": [{"role": "user", "content": "write via mcp"}],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "mcp__fake__write_tool",
                        "parameters": {"type": "object", "properties": {}},
                    },
                }
            ],
        },
        messages_for_deepseek=[{"role": "user", "content": "write via mcp"}],
        history_messages=[{"role": "user", "content": "write via mcp"}],
        model="deepseek-v4-pro",
        deepseek_tools=[
            {
                "type": "function",
                "function": {
                    "name": "mcp__fake__write_tool",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ],
        reasoning_effort=None,
        request_payload={},
    )

    assert deepseek_response["choices"][0]["message"]["content"] == "Write denied."
    tool_payloads = _payloads_with_tool_messages(fake.payloads)
    result = json.loads([m for m in tool_payloads[0]["messages"] if m.get("role") == "tool"][0]["content"])
    assert result["ok"] is False
    assert result["error"] == "mcp_write_denied"
