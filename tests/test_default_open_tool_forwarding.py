from codexchange_proxy.app import (
    _mcp_tutorial_tool_names,
    _mcp_write_tool_names,
    _normalize_response_tool,
)


def _normalize(tool):
    warnings = []
    mapping = {}
    normalized = _normalize_response_tool(tool, warnings, mapping)
    return normalized, warnings, mapping


def _namespace_tool(namespace, tool_names):
    if isinstance(tool_names, str):
        tool_names = [tool_names]
    return {
        "type": "namespace",
        "name": namespace,
        "tools": [
            {
                "type": "function",
                "name": tool_name,
                "description": f"{tool_name} test tool",
                "parameters": {"type": "object", "properties": {}},
            }
            for tool_name in tool_names
        ],
    }


def _function_names(normalized):
    if isinstance(normalized, list):
        return [(item.get("function") or {}).get("name") for item in normalized]
    return [(normalized.get("function") or {}).get("name")]


def _disable_all_mcp(monkeypatch):
    monkeypatch.setenv("COX_FORWARD_MCP_READONLY_TOOLS", "0")
    monkeypatch.setenv("COX_FORWARD_MCP_WRITE_TOOLS", "0")
    monkeypatch.setenv("COX_FORWARD_MCP_TUTORIAL_TOOLS", "0")


def _enable_default_mcp(monkeypatch):
    monkeypatch.delenv("COX_FORWARD_MCP_READONLY_TOOLS", raising=False)
    monkeypatch.delenv("COX_FORWARD_MCP_WRITE_TOOLS", raising=False)
    monkeypatch.delenv("COX_FORWARD_MCP_TUTORIAL_TOOLS", raising=False)


def test_apply_patch_maps_by_default(monkeypatch):
    monkeypatch.delenv("COX_FORWARD_CUSTOM_APPLY_PATCH", raising=False)

    normalized, warnings, mapping = _normalize({
        "type": "custom",
        "name": "apply_patch",
        "description": "Apply a patch.",
    })

    assert normalized["type"] == "function"
    assert normalized["function"]["name"] == "apply_patch"
    assert "input" in normalized["function"]["parameters"]["properties"]
    assert mapping == {}
    assert "apply_patch" in str(warnings)
    assert "mapped" in str(warnings)


def test_apply_patch_can_be_disabled(monkeypatch):
    monkeypatch.setenv("COX_FORWARD_CUSTOM_APPLY_PATCH", "0")

    normalized, warnings, mapping = _normalize({
        "type": "custom",
        "name": "apply_patch",
        "description": "Apply a patch.",
    })

    assert normalized is None
    assert mapping == {}
    assert any(item["kind"] == "ignored_custom_tool" for item in warnings)


def test_readonly_mcp_maps_by_default(monkeypatch):
    _enable_default_mcp(monkeypatch)

    normalized, warnings, mapping = _normalize(
        _namespace_tool("mcp__cheap_llm__", "cheap_router_status")
    )

    assert "mcp__cheap_llm__cheap_router_status" in _function_names(normalized)
    assert mapping["mcp__cheap_llm__cheap_router_status"] == {
        "namespace": "mcp__cheap_llm__",
        "name": "cheap_router_status",
    }
    assert any(item["kind"] == "mapped_mcp_namespace" for item in warnings)


def test_readonly_mcp_can_be_disabled(monkeypatch):
    _disable_all_mcp(monkeypatch)

    normalized, warnings, mapping = _normalize(
        _namespace_tool("mcp__cheap_llm__", "cheap_router_status")
    )

    assert normalized is None
    assert mapping == {}
    assert any(item["kind"] == "ignored_mcp_namespace" for item in warnings)


def test_write_mcp_maps_by_default(monkeypatch):
    _enable_default_mcp(monkeypatch)

    write_names = sorted(_mcp_write_tool_names())
    assert write_names

    normalized, warnings, mapping = _normalize(
        _namespace_tool("mcp__memory_router__", write_names)
    )

    names = _function_names(normalized)
    assert names
    assert any(name.startswith("mcp__memory_router__") for name in names)

    for mapped_name in names:
        assert mapped_name in mapping
        assert mapping[mapped_name]["namespace"] == "mcp__memory_router__"

    assert any(item["kind"] == "mapped_mcp_namespace" for item in warnings)


def test_write_mcp_can_be_disabled(monkeypatch):
    _disable_all_mcp(monkeypatch)

    write_names = sorted(_mcp_write_tool_names())
    assert write_names

    normalized, warnings, mapping = _normalize(
        _namespace_tool("mcp__memory_router__", write_names)
    )

    assert normalized is None
    assert mapping == {}
    assert any(item["kind"] == "ignored_mcp_namespace" for item in warnings)


def test_tutorial_mcp_maps_by_default(monkeypatch):
    _enable_default_mcp(monkeypatch)

    tutorial_names = sorted(_mcp_tutorial_tool_names())
    assert tutorial_names

    normalized, warnings, mapping = _normalize(
        _namespace_tool("mcp__follow_online_tutorial__", tutorial_names)
    )

    names = _function_names(normalized)
    assert names
    assert any(name.startswith("mcp__follow_online_tutorial__") for name in names)

    for mapped_name in names:
        assert mapped_name in mapping
        assert mapping[mapped_name]["namespace"] == "mcp__follow_online_tutorial__"

    assert any(item["kind"] == "mapped_mcp_namespace" for item in warnings)


def test_tutorial_mcp_can_be_disabled(monkeypatch):
    _disable_all_mcp(monkeypatch)

    tutorial_names = sorted(_mcp_tutorial_tool_names())
    assert tutorial_names

    normalized, warnings, mapping = _normalize(
        _namespace_tool("mcp__follow_online_tutorial__", tutorial_names)
    )

    assert normalized is None
    assert mapping == {}
    assert any(item["kind"] == "ignored_mcp_namespace" for item in warnings)
