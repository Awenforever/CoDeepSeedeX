import json
import os
import sys
from pathlib import Path

import pytest

from codexchange_proxy.mcp_stdio import (
    StdioMCPServerConfig,
    build_mcp_process_env,
    discover_stdio_mcp_tools,
)


def _write_fake_mcp_server(path: Path) -> None:
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
                "serverInfo": {"name": "fake-mcp", "version": "0.0.1"}
            }
        }), flush=True)
    elif method == "notifications/initialized":
        continue
    elif method == "tools/list":
        print(json.dumps({
            "jsonrpc": "2.0",
            "id": msg["id"],
            "result": {
                "tools": [
                    {
                        "name": "safe_tool",
                        "description": "A fake safe tool.",
                        "inputSchema": {"type": "object", "properties": {"q": {"type": "string"}}}
                    }
                ]
            }
        }), flush=True)
''',
        encoding="utf-8",
    )


def test_build_mcp_process_env_uses_selected_env_vars(monkeypatch):
    monkeypatch.setenv("VISIBLE_KEY", "visible")
    monkeypatch.setenv("HIDDEN_KEY", "hidden")

    env = build_mcp_process_env(
        StdioMCPServerConfig(
            name="fake",
            command=sys.executable,
            args=[],
            env_vars=["VISIBLE_KEY"],
            env={"LOCAL_ONLY": "yes"},
            startup_timeout_sec=1.0,
            tool_timeout_sec=1.0,
        )
    )

    assert env["VISIBLE_KEY"] == "visible"
    assert env["LOCAL_ONLY"] == "yes"
    assert "HIDDEN_KEY" not in env


@pytest.mark.asyncio
async def test_discover_stdio_mcp_tools_initializes_and_lists_tools(tmp_path):
    server = tmp_path / "fake_mcp_server.py"
    _write_fake_mcp_server(server)

    result = await discover_stdio_mcp_tools(
        StdioMCPServerConfig(
            name="fake",
            command=sys.executable,
            args=[str(server)],
            env_vars=[],
            env={},
            startup_timeout_sec=5.0,
            tool_timeout_sec=5.0,
        ),
        client_version="test-version",
        protocol_version="2025-03-26",
    )

    assert result["ok"] is True
    assert result["server"] == "fake"
    assert result["tool_count"] == 1
    assert result["tools"][0]["name"] == "safe_tool"
    assert result["tools"][0]["inputSchema"]["properties"]["q"]["type"] == "string"
    assert result["initialize"]["serverInfo"]["name"] == "fake-mcp"


@pytest.mark.asyncio
async def test_discover_stdio_mcp_tools_reports_missing_command(tmp_path):
    result = await discover_stdio_mcp_tools(
        StdioMCPServerConfig(
            name="missing",
            command=str(tmp_path / "missing-python"),
            args=[],
            env_vars=[],
            env={},
            startup_timeout_sec=1.0,
            tool_timeout_sec=1.0,
        )
    )

    assert result["ok"] is False
    assert result["error"] == "mcp_command_not_found"
    assert result["tools"] == []
