import json
import sys
from pathlib import Path

import pytest

from tests.test_mcp_executor_gated import FakeDeepSeekClient, _payloads_with_tool_messages, _response

from deepseek_responses_proxy.app import (
    _mcp_executor_policy_decision,
    _mcp_executor_status,
    _run_chat_with_tool_bridge,
)


def _write_fake_mcp_server(path: Path) -> None:
    path.write_text(
        r'''
import json
import sys

TOOLS = [
    {
        "name": "write_tool",
        "description": "A fake write-capable tool.",
        "inputSchema": {"type": "object", "properties": {"value": {"type": "string"}}}
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
                "serverInfo": {"name": "fake-codex-policy-mcp", "version": "0.0.1"}
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


def test_codex_policy_is_default_and_allows_mcp_tool(monkeypatch, tmp_path):
    monkeypatch.delenv("DEEPSEEK_PROXY_MCP_POLICY", raising=False)
    monkeypatch.delenv("DEEPSEEK_PROXY_MCP_EXECUTOR", raising=False)
    monkeypatch.delenv("DEEPSEEK_PROXY_MCP_EXECUTOR_BACKEND", raising=False)
    monkeypatch.delenv("DEEPSEEK_PROXY_MCP_READONLY_ALLOWLIST", raising=False)
    monkeypatch.delenv("DEEPSEEK_PROXY_MCP_WRITE_ALLOWLIST", raising=False)

    config = tmp_path / "config.toml"
    config.write_text("", encoding="utf-8")
    monkeypatch.setenv("DEEPSEEK_PROXY_MCP_CONFIG_PATH", str(config))

    decision = _mcp_executor_policy_decision("mcp__fake__write_tool")
    status = _mcp_executor_status()

    assert decision["ok"] is True
    assert decision["kind"] == "allowed_codex_config"
    assert decision["permission"] == "codex"
    assert decision["policy"] == "codex"

    assert status["enabled"] is True
    assert status["policy"] == "codex"
    assert status["backend"]["type"] == "stdio"
    assert status["backend"]["production_execution"] is True


def test_off_policy_disables_mcp_executor(monkeypatch, tmp_path):
    config = tmp_path / "config.toml"
    config.write_text("", encoding="utf-8")
    monkeypatch.setenv("DEEPSEEK_PROXY_MCP_CONFIG_PATH", str(config))
    monkeypatch.setenv("DEEPSEEK_PROXY_MCP_POLICY", "off")

    decision = _mcp_executor_policy_decision("mcp__fake__safe_tool")
    status = _mcp_executor_status()

    assert decision["ok"] is False
    assert decision["kind"] == "mcp_executor_disabled"
    assert status["enabled"] is False
    assert status["policy"] == "off"
    assert status["backend"]["production_execution"] is False


def test_allowlist_policy_allows_write_allowlisted_tool(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_PROXY_MCP_POLICY", "allowlist")
    monkeypatch.setenv("DEEPSEEK_PROXY_MCP_EXECUTOR", "1")
    monkeypatch.setenv("DEEPSEEK_PROXY_MCP_WRITE_ALLOWLIST", "fake.write_tool")

    decision = _mcp_executor_policy_decision("mcp__fake__write_tool")

    assert decision["ok"] is True
    assert decision["kind"] == "allowed_write"
    assert decision["permission"] == "write"
    assert decision["policy"] == "allowlist"


@pytest.mark.asyncio
async def test_codex_policy_executes_configured_write_tool_without_allowlist(tmp_path, monkeypatch):
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

[mcp_servers.fake.tools.write_tool]
approval_mode = "approve"
''',
        encoding="utf-8",
    )

    monkeypatch.setenv("DEEPSEEK_PROXY_MCP_CONFIG_PATH", str(config))
    monkeypatch.setenv("DEEPSEEK_PROXY_TOOL_BRIDGE", "1")
    monkeypatch.setenv("DEEPSEEK_PROXY_AGENT_LIVENESS_GUARD", "0")
    monkeypatch.delenv("DEEPSEEK_PROXY_MCP_POLICY", raising=False)
    monkeypatch.delenv("DEEPSEEK_PROXY_MCP_EXECUTOR", raising=False)
    monkeypatch.delenv("DEEPSEEK_PROXY_MCP_EXECUTOR_BACKEND", raising=False)
    monkeypatch.delenv("DEEPSEEK_PROXY_MCP_READONLY_ALLOWLIST", raising=False)
    monkeypatch.delenv("DEEPSEEK_PROXY_MCP_WRITE_ALLOWLIST", raising=False)

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
                                "arguments": json.dumps({"value": "hello"}),
                            },
                        }
                    ],
                }
            ),
            _response({"role": "assistant", "content": "Codex policy MCP result consumed."}),
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
                        "name": "mcp__fake__write_tool",
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
                    "name": "mcp__fake__write_tool",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ],
        reasoning_effort=None,
        request_payload={},
    )

    assert deepseek_response["choices"][0]["message"]["content"] == "Codex policy MCP result consumed."

    tool_payloads = _payloads_with_tool_messages(fake.payloads)
    result = json.loads([m for m in tool_payloads[0]["messages"] if m.get("role") == "tool"][0]["content"])

    assert result["ok"] is True
    assert result["mcp"]["permission"] == "codex"
    assert result["result"]["structuredContent"] == {
        "name": "write_tool",
        "arguments": {"value": "hello"},
    }
