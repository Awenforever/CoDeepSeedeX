from deepseek_responses_proxy.app import _normalize_response_tool


def test_custom_apply_patch_is_ignored_without_large_grammar_payload():
    warnings = []
    tool = {
        "type": "custom",
        "name": "apply_patch",
        "description": "Use the apply_patch tool to edit files.",
        "format": {
            "type": "grammar",
            "syntax": "lark",
            "definition": "very large grammar should not be copied into warnings",
        },
    }

    normalized = _normalize_response_tool(tool, warnings)

    assert normalized is None
    assert warnings == [
        {
            "kind": "ignored_custom_tool",
            "tool_type": "custom",
            "name": "apply_patch",
            "description": "Use the apply_patch tool to edit files.",
            "format": {
                "type": "grammar",
                "syntax": "lark",
            },
            "reason": "custom freeform tools are executed by Codex locally and are not forwarded to DeepSeek",
        }
    ]
    assert "definition" not in warnings[0]["format"]


def test_unknown_non_function_tool_remains_unsupported():
    warnings = []
    tool = {"type": "unknown_builtin", "name": "x"}

    normalized = _normalize_response_tool(tool, warnings)

    assert normalized is None
    assert warnings[0]["kind"] == "unsupported_tool_type"
    assert warnings[0]["tool_type"] == "unknown_builtin"
