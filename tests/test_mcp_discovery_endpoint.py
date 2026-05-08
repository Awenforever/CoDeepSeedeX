import sys
from pathlib import Path

from fastapi.testclient import TestClient

from deepseek_responses_proxy.app import InMemoryResponseStore, create_app


class NoopDeepSeekClient:
    base_url = "https://api.deepseek.test"


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


def _client():
    return TestClient(create_app(deepseek_client=NoopDeepSeekClient(), store=InMemoryResponseStore()))


def test_mcp_discovery_endpoint_is_disabled_by_default(tmp_path, monkeypatch):
    config = tmp_path / "config.toml"
    config.write_text(
        '''
[mcp_servers.missing_server]
command = "/tmp/does-not-exist"
args = []
''',
        encoding="utf-8",
    )

    monkeypatch.setenv("DEEPSEEK_PROXY_MCP_CONFIG_PATH", str(config))
    monkeypatch.delenv("DEEPSEEK_PROXY_MCP_DISCOVERY", raising=False)

    response = _client().get("/v1/proxy/mcp/discovery")

    assert response.status_code == 200
    data = response.json()
    assert data["enabled"] is False
    assert data["reason"] == "disabled"
    assert data["codex_config"]["server_count"] == 1
    assert data["selected_servers"] == []
    assert data["discovery_runs"] == {}


def test_mcp_discovery_endpoint_discovers_fake_stdio_server(tmp_path, monkeypatch):
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

[mcp_servers.fake.env]
SECRET_VALUE = "must-not-leak"

[mcp_servers.fake.tools.safe_tool]
approval_mode = "approve"
''',
        encoding="utf-8",
    )

    monkeypatch.setenv("DEEPSEEK_PROXY_MCP_CONFIG_PATH", str(config))
    monkeypatch.setenv("DEEPSEEK_PROXY_MCP_DISCOVERY", "1")

    response = _client().get("/v1/proxy/mcp/discovery")

    assert response.status_code == 200
    data = response.json()
    assert data["enabled"] is True
    assert data["reason"] == "completed"
    assert data["selected_servers"] == ["fake"]
    assert "must-not-leak" not in response.text

    run = data["discovery_runs"]["fake"]
    assert run["ok"] is True
    assert run["tool_count"] == 1
    assert run["tools"][0]["name"] == "safe_tool"
    assert run["tools"][0]["inputSchema"]["properties"]["q"]["type"] == "string"


def test_mcp_discovery_endpoint_respects_server_filter(tmp_path, monkeypatch):
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

[mcp_servers.missing]
command = "/tmp/does-not-exist"
args = []
''',
        encoding="utf-8",
    )

    monkeypatch.setenv("DEEPSEEK_PROXY_MCP_CONFIG_PATH", str(config))
    monkeypatch.setenv("DEEPSEEK_PROXY_MCP_DISCOVERY", "1")
    monkeypatch.setenv("DEEPSEEK_PROXY_MCP_DISCOVERY_SERVERS", "fake")

    response = _client().get("/v1/proxy/mcp/discovery")

    assert response.status_code == 200
    data = response.json()
    assert data["selected_servers"] == ["fake"]
    assert set(data["discovery_runs"]) == {"fake"}
    assert data["discovery_runs"]["fake"]["ok"] is True


def test_tool_bridge_status_reports_discovery_config(tmp_path, monkeypatch):
    config = tmp_path / "config.toml"
    config.write_text("", encoding="utf-8")

    monkeypatch.setenv("DEEPSEEK_PROXY_MCP_CONFIG_PATH", str(config))
    monkeypatch.setenv("DEEPSEEK_PROXY_MCP_DISCOVERY", "1")
    monkeypatch.setenv("DEEPSEEK_PROXY_MCP_DISCOVERY_SERVERS", "fake,other")

    response = _client().get("/v1/proxy/tool-bridge/status")

    assert response.status_code == 200
    discovery = response.json()["tool_bridge"]["mcp_executor"]["discovery"]
    assert discovery["enabled"] is True
    assert discovery["auto_run_in_status"] is False
    assert discovery["tools_call_enabled"] is False
    assert discovery["production_execution"] is False
    assert discovery["server_filter"] == ["fake", "other"]
