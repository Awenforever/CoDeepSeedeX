import json
import sys
from pathlib import Path

import pytest

from codexchange_proxy.mcp_stdio import (
    StdioMCPServerConfig,
    call_stdio_mcp_tool,
)


def _write_fake_mcp_call_server(path: Path) -> None:
    path.write_text(
        r'''
import json
import sys

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
                "serverInfo": {"name": "fake-call-mcp", "version": "0.0.1"}
            }
        }), flush=True)
    elif method == "notifications/initialized":
        continue
    elif method == "tools/call":
        params = msg.get("params", {})
        print(json.dumps({
            "jsonrpc": "2.0",
            "id": msg["id"],
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": "called " + params.get("name", "")
                    }
                ],
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


def _write_fake_mcp_error_server(path: Path) -> None:
    path.write_text(
        r'''
import json
import sys

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
                "serverInfo": {"name": "fake-error-mcp", "version": "0.0.1"}
            }
        }), flush=True)
    elif method == "notifications/initialized":
        continue
    elif method == "tools/call":
        print(json.dumps({
            "jsonrpc": "2.0",
            "id": msg["id"],
            "error": {
                "code": -32000,
                "message": "tool failed"
            }
        }), flush=True)
''',
        encoding="utf-8",
    )


@pytest.mark.asyncio
async def test_call_stdio_mcp_tool_initializes_and_calls_tool(tmp_path):
    server = tmp_path / "fake_mcp_call_server.py"
    _write_fake_mcp_call_server(server)

    result = await call_stdio_mcp_tool(
        StdioMCPServerConfig(
            name="fake",
            command=sys.executable,
            args=[str(server)],
            env_vars=[],
            env={},
            startup_timeout_sec=5.0,
            tool_timeout_sec=5.0,
        ),
        tool_name="safe_tool",
        arguments={"q": "hello"},
        client_version="test-version",
        protocol_version="2025-03-26",
    )

    assert result["ok"] is True
    assert result["server"] == "fake"
    assert result["tool"] == "safe_tool"
    assert result["initialize"]["serverInfo"]["name"] == "fake-call-mcp"
    assert result["result"]["isError"] is False
    assert result["result"]["content"][0]["text"] == "called safe_tool"
    assert result["result"]["structuredContent"] == {
        "name": "safe_tool",
        "arguments": {"q": "hello"},
    }


@pytest.mark.asyncio
async def test_call_stdio_mcp_tool_reports_jsonrpc_error(tmp_path):
    server = tmp_path / "fake_mcp_error_server.py"
    _write_fake_mcp_error_server(server)

    result = await call_stdio_mcp_tool(
        StdioMCPServerConfig(
            name="fake",
            command=sys.executable,
            args=[str(server)],
            env_vars=[],
            env={},
            startup_timeout_sec=5.0,
            tool_timeout_sec=5.0,
        ),
        tool_name="failing_tool",
        arguments={},
    )

    assert result["ok"] is False
    assert result["server"] == "fake"
    assert result["tool"] == "failing_tool"
    assert result["error"] == "mcp_tool_call_failed"
    assert "tool failed" in result["message"]


@pytest.mark.asyncio
async def test_call_stdio_mcp_tool_reports_missing_command(tmp_path):
    result = await call_stdio_mcp_tool(
        StdioMCPServerConfig(
            name="missing",
            command=str(tmp_path / "missing-python"),
            args=[],
            env_vars=[],
            env={},
            startup_timeout_sec=1.0,
            tool_timeout_sec=1.0,
        ),
        tool_name="safe_tool",
        arguments={},
    )

    assert result["ok"] is False
    assert result["error"] == "mcp_command_not_found"
    assert result["tool"] == "safe_tool"
