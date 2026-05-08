import sys
from pathlib import Path

from fastapi.testclient import TestClient

from deepseek_responses_proxy.app import InMemoryResponseStore, create_app


class NoopDeepSeekClient:
    base_url = "https://api.deepseek.test"


def _client():
    return TestClient(create_app(deepseek_client=NoopDeepSeekClient(), store=InMemoryResponseStore()))


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
                "serverInfo": {"name": "fake-diagnostic-mcp", "version": "0.0.1"}
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
                "content": [{"type": "text", "text": "diagnostic called " + params.get("name", "")}],
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


def test_mcp_diagnostic_call_is_disabled_by_default(tmp_path, monkeypatch):
    config = tmp_path / "config.toml"
    config.write_text("", encoding="utf-8")

    monkeypatch.setenv("DEEPSEEK_PROXY_MCP_CONFIG_PATH", str(config))
    monkeypatch.delenv("DEEPSEEK_PROXY_MCP_DIAGNOSTIC_CALL", raising=False)

    response = _client().post(
        "/v1/proxy/mcp/diagnostic-call",
        json={"server": "fake", "tool": "safe_tool", "arguments": {"q": "hello"}},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is False
    assert data["enabled"] is False
    assert data["error"] == "mcp_diagnostic_call_disabled"
    assert data["tools_call_enabled"] is False


def test_mcp_diagnostic_call_requires_stdio_backend(tmp_path, monkeypatch):
    config = tmp_path / "config.toml"
    config.write_text("", encoding="utf-8")

    monkeypatch.setenv("DEEPSEEK_PROXY_MCP_CONFIG_PATH", str(config))
    monkeypatch.setenv("DEEPSEEK_PROXY_MCP_DIAGNOSTIC_CALL", "1")
    monkeypatch.setenv("DEEPSEEK_PROXY_MCP_EXECUTOR", "1")
    monkeypatch.setenv("DEEPSEEK_PROXY_MCP_READONLY_ALLOWLIST", "fake.safe_tool")
    monkeypatch.setenv("DEEPSEEK_PROXY_MCP_EXECUTOR_BACKEND", "none")

    response = _client().post(
        "/v1/proxy/mcp/diagnostic-call",
        json={"server": "fake", "tool": "safe_tool"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is False
    assert data["enabled"] is True
    assert data["error"] == "mcp_stdio_backend_disabled"


def test_mcp_diagnostic_call_keeps_write_denied(tmp_path, monkeypatch):
    config = tmp_path / "config.toml"
    config.write_text(
        """
[mcp_servers.fake]
command = "/tmp/does-not-matter"
args = []
""",
        encoding="utf-8",
    )

    monkeypatch.setenv("DEEPSEEK_PROXY_MCP_CONFIG_PATH", str(config))
    monkeypatch.setenv("DEEPSEEK_PROXY_MCP_DIAGNOSTIC_CALL", "1")
    monkeypatch.setenv("DEEPSEEK_PROXY_MCP_EXECUTOR", "1")
    monkeypatch.setenv("DEEPSEEK_PROXY_MCP_EXECUTOR_BACKEND", "stdio")
    monkeypatch.setenv("DEEPSEEK_PROXY_MCP_WRITE_ALLOWLIST", "fake.write_tool")

    response = _client().post(
        "/v1/proxy/mcp/diagnostic-call",
        json={"server": "fake", "tool": "write_tool"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is False
    assert data["error"] == "mcp_discovery_failed_before_call"
    assert data["mcp"]["permission"] == "codex"



def test_mcp_diagnostic_call_executes_readonly_stdio_tool(tmp_path, monkeypatch):
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
    monkeypatch.setenv("DEEPSEEK_PROXY_MCP_DIAGNOSTIC_CALL", "1")
    monkeypatch.setenv("DEEPSEEK_PROXY_MCP_EXECUTOR", "1")
    monkeypatch.setenv("DEEPSEEK_PROXY_MCP_EXECUTOR_BACKEND", "stdio")
    monkeypatch.setenv("DEEPSEEK_PROXY_MCP_READONLY_ALLOWLIST", "fake.safe_tool")

    response = _client().post(
        "/v1/proxy/mcp/diagnostic-call",
        json={"function_name": "mcp__fake__safe_tool", "arguments": {"q": "hello"}},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["enabled"] is True
    assert data["tools_call_enabled"] is True
    assert data["production_execution"] is False
    assert data["backend"] == "stdio"
    assert data["tool"] == "mcp__fake__safe_tool"
    assert data["mcp"]["server"] == "fake"
    assert data["mcp"]["permission"] == "codex"
    assert data["result"]["structuredContent"] == {
        "name": "safe_tool",
        "arguments": {"q": "hello"},
    }
