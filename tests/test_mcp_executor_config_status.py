from pathlib import Path

from codexchange_proxy.app import (
    _codex_mcp_config_snapshot,
    _mcp_executor_status,
    _tool_bridge_status,
)


def test_codex_mcp_config_snapshot_parses_servers_and_tools(tmp_path, monkeypatch):
    config = tmp_path / "config.toml"
    config.write_text(
        '''
[mcp_servers.custom_server]
command = "/tmp/server-python"
args = ["server.py", "--mode", "stdio"]
env_vars = ["API_KEY_NAME"]
startup_timeout_sec = 20.0
tool_timeout_sec = 120.0

[mcp_servers.custom_server.env]
SECRET_VALUE = "do-not-surface-value"
PUBLIC_MODE = "test"

[mcp_servers.custom_server.tools.safe_tool]
approval_mode = "approve"

[mcp_servers.custom_server.tools.write_tool]
approval_mode = "manual"
''',
        encoding="utf-8",
    )

    monkeypatch.setenv("COX_MCP_CONFIG_PATH", str(config))
    snapshot = _codex_mcp_config_snapshot()

    assert snapshot["exists"] is True
    assert snapshot["error"] is None
    assert snapshot["server_count"] == 1

    server = snapshot["servers"]["custom_server"]
    assert server["command"] == "/tmp/server-python"
    assert server["args"] == ["server.py", "--mode", "stdio"]
    assert server["env_vars"] == ["API_KEY_NAME"]
    assert server["env_keys"] == ["PUBLIC_MODE", "SECRET_VALUE"]
    assert "do-not-surface-value" not in str(snapshot)
    assert server["tools"]["safe_tool"]["approval_mode"] == "approve"
    assert server["tools"]["write_tool"]["approval_mode"] == "manual"


def test_codex_mcp_config_snapshot_handles_missing_config(tmp_path, monkeypatch):
    missing = tmp_path / "missing.toml"
    monkeypatch.setenv("COX_MCP_CONFIG_PATH", str(missing))

    snapshot = _codex_mcp_config_snapshot()

    assert snapshot["exists"] is False
    assert snapshot["server_count"] == 0
    assert snapshot["servers"] == {}
    assert snapshot["error"] is None


def test_mcp_executor_status_reports_policy_and_config(tmp_path, monkeypatch):
    config = tmp_path / "config.toml"
    config.write_text(
        '''
[mcp_servers.memory_router]
command = "/tmp/python"
args = ["server.py"]

[mcp_servers.memory_router.tools.memory_query]
approval_mode = "approve"
''',
        encoding="utf-8",
    )

    monkeypatch.setenv("COX_MCP_CONFIG_PATH", str(config))
    monkeypatch.setenv("COX_MCP_EXECUTOR", "1")
    monkeypatch.setenv(
        "COX_MCP_READONLY_ALLOWLIST",
        "memory_router.memory_query,cheap_llm.cheap_router_status",
    )
    monkeypatch.setenv("COX_MCP_WRITE_ALLOWLIST", "memory_router.memory_remember")

    status = _mcp_executor_status()

    assert status["enabled"] is True
    assert status["policy"] == "codex"
    assert status["backend"]["type"] == "stdio"
    assert status["backend"]["production_execution"] is True
    assert status["readonly_allowlist"] == [
        "cheap_llm.cheap_router_status",
        "memory_router.memory_query",
    ]
    assert status["write_allowlist"] == ["memory_router.memory_remember"]
    assert status["codex_config"]["server_count"] == 1
    assert "memory_router" in status["codex_config"]["servers"]


def test_tool_bridge_status_includes_mcp_executor(tmp_path, monkeypatch):
    missing = tmp_path / "missing.toml"
    monkeypatch.setenv("COX_MCP_CONFIG_PATH", str(missing))
    monkeypatch.setenv("COX_MCP_POLICY", "off")
    monkeypatch.delenv("COX_MCP_EXECUTOR", raising=False)

    status = _tool_bridge_status()

    assert "mcp_executor" in status
    assert status["mcp_executor"]["enabled"] is False
    assert status["mcp_executor"]["codex_config"]["exists"] is False
