from deepseek_responses_proxy.app import _normalize_response_tool


def _mixed_namespace_tool():
    return {
        "type": "namespace",
        "name": "mcp__memory_router__",
        "tools": [
            {
                "type": "function",
                "name": "memory_list",
                "description": "List memories.",
                "parameters": {"type": "object", "properties": {}},
            },
            {
                "type": "function",
                "name": "memory_update",
                "description": "Update memory.",
                "parameters": {
                    "type": "object",
                    "properties": {"id": {"type": "integer"}},
                    "required": ["id"],
                },
            },
            {
                "type": "function",
                "name": "memory_remember",
                "description": "Remember memory.",
                "parameters": {"type": "object", "properties": {}},
            },
        ],
    }


def test_mcp_write_tools_are_not_forwarded_by_default(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_PROXY_FORWARD_MCP_READONLY_TOOLS", "1")
    monkeypatch.delenv("DEEPSEEK_PROXY_FORWARD_MCP_WRITE_TOOLS", raising=False)

    warnings = []
    mapping = {}
    normalized = _normalize_response_tool(_mixed_namespace_tool(), warnings, mapping)

    names = [(item.get("function") or {}).get("name") for item in normalized]
    assert names == ["mcp__memory_router__memory_list"]
    assert "mcp__memory_router__memory_update" not in mapping
    assert "mcp__memory_router__memory_remember" not in mapping


def test_mcp_write_tools_are_forwarded_only_with_write_flag(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_PROXY_FORWARD_MCP_READONLY_TOOLS", "1")
    monkeypatch.setenv("DEEPSEEK_PROXY_FORWARD_MCP_WRITE_TOOLS", "1")

    warnings = []
    mapping = {}
    normalized = _normalize_response_tool(_mixed_namespace_tool(), warnings, mapping)

    names = [(item.get("function") or {}).get("name") for item in normalized]
    assert names == [
        "mcp__memory_router__memory_list",
        "mcp__memory_router__memory_update",
        "mcp__memory_router__memory_remember",
    ]
    assert mapping["mcp__memory_router__memory_update"] == {
        "namespace": "mcp__memory_router__",
        "name": "memory_update",
        "forwarding_class": "write",
    }
    assert mapping["mcp__memory_router__memory_remember"] == {
        "namespace": "mcp__memory_router__",
        "name": "memory_remember",
        "forwarding_class": "write",
    }
