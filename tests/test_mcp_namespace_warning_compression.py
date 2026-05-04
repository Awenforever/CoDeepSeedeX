from deepseek_responses_proxy.app import _normalize_response_tool


def test_mcp_namespace_warning_is_compressed_without_full_schema():
    warnings = []
    tool = {
        "type": "namespace",
        "name": "mcp__cheap_llm__",
        "description": "Tools in the mcp__cheap_llm__ namespace.",
        "tools": [
            {
                "type": "function",
                "name": "cheap_ask",
                "description": "Delegate a small task.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "prompt": {"type": "string"},
                    },
                },
            },
            {
                "type": "function",
                "name": "cheap_read_file",
                "description": "Read and summarize a local file.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string"},
                        "instruction": {"type": "string"},
                    },
                },
            },
        ],
    }

    normalized = _normalize_response_tool(tool, warnings)

    assert normalized is None
    assert warnings == [
        {
            "kind": "ignored_mcp_namespace",
            "tool_type": "namespace",
            "namespace": "mcp__cheap_llm__",
            "tool_count": 2,
            "tool_names": ["cheap_ask", "cheap_read_file"],
            "reason": "MCP tools are owned by Codex local MCP runtime and are not forwarded to DeepSeek",
        }
    ]
    assert "tool" not in warnings[0]
    assert "parameters" not in str(warnings[0])


def test_non_mcp_unknown_namespace_still_records_full_unsupported_tool():
    warnings = []
    tool = {
        "type": "namespace",
        "namespace": "unknown_namespace_for_test",
        "tools": [{"type": "function", "name": "x"}],
    }

    normalized = _normalize_response_tool(tool, warnings)

    assert normalized is None
    assert warnings[0]["kind"] == "unsupported_tool_namespace"
    assert warnings[0]["namespace"] == "unknown_namespace_for_test"
    assert warnings[0]["tool"] == tool
