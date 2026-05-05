from deepseek_responses_proxy.app import (
    _deepseek_message_to_output_items,
    _normalize_response_tool,
)


def _mcp_namespace_tool():
    return {
        "type": "namespace",
        "name": "mcp__cheap_llm__",
        "tools": [
            {
                "type": "function",
                "name": "cheap_router_status",
                "description": "Return router status.",
                "parameters": {"type": "object", "properties": {}},
            },
            {
                "type": "function",
                "name": "router_add_model",
                "description": "Add model.",
                "parameters": {"type": "object", "properties": {}},
            },
        ],
    }


def test_mcp_namespace_is_ignored_by_default(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_PROXY_FORWARD_MCP_READONLY_TOOLS", raising=False)

    warnings = []
    mapping = {}
    normalized = _normalize_response_tool(_mcp_namespace_tool(), warnings, mapping)

    assert normalized is None
    assert mapping == {}
    assert warnings[0]["kind"] == "ignored_mcp_namespace"


def test_mcp_readonly_namespace_builds_mapping(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_PROXY_FORWARD_MCP_READONLY_TOOLS", "1")

    warnings = []
    mapping = {}
    normalized = _normalize_response_tool(_mcp_namespace_tool(), warnings, mapping)

    assert isinstance(normalized, list)
    assert len(normalized) == 1
    assert normalized[0]["function"]["name"] == "mcp__cheap_llm__cheap_router_status"
    assert mapping == {
        "mcp__cheap_llm__cheap_router_status": {
            "namespace": "mcp__cheap_llm__",
            "name": "cheap_router_status",
        }
    }
    assert warnings[0]["kind"] == "mapped_mcp_namespace"


def test_mcp_tool_call_output_item_restores_namespace():
    message = {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {
                "id": "call_mcp",
                "type": "function",
                "function": {
                    "name": "mcp__cheap_llm__cheap_router_status",
                    "arguments": "{}",
                },
            }
        ],
    }
    mapping = {
        "mcp__cheap_llm__cheap_router_status": {
            "namespace": "mcp__cheap_llm__",
            "name": "cheap_router_status",
        }
    }

    output_items = _deepseek_message_to_output_items(message, mapping)

    assert output_items == [
        {
            "id": output_items[0]["id"],
            "type": "function_call",
            "call_id": "call_mcp",
            "name": "cheap_router_status",
            "arguments": "{}",
            "namespace": "mcp__cheap_llm__",
        }
    ]
