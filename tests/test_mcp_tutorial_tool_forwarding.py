from deepseek_responses_proxy.app import _normalize_response_tool


def _tutorial_namespace_tool():
    return {
        "type": "namespace",
        "name": "mcp__follow_online_tutorial__",
        "tools": [
            {"type": "function", "name": "start_tutorial_run", "parameters": {"type": "object", "properties": {}}},
            {"type": "function", "name": "search_instructions", "parameters": {"type": "object", "properties": {}}},
            {"type": "function", "name": "read_source", "parameters": {"type": "object", "properties": {}}},
            {"type": "function", "name": "make_execution_plan", "parameters": {"type": "object", "properties": {}}},
            {"type": "function", "name": "revise_plan", "parameters": {"type": "object", "properties": {}}},
            {"type": "function", "name": "synthesize_options", "parameters": {"type": "object", "properties": {}}},
            {"type": "function", "name": "evaluate_sources", "parameters": {"type": "object", "properties": {}}},
            {"type": "function", "name": "record_feedback", "parameters": {"type": "object", "properties": {}}},
            {"type": "function", "name": "final_report", "parameters": {"type": "object", "properties": {}}},
        ],
    }


def test_tutorial_tools_are_not_forwarded_by_default(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_PROXY_FORWARD_MCP_TUTORIAL_TOOLS", "0")

    warnings = []
    mapping = {}
    normalized = _normalize_response_tool(_tutorial_namespace_tool(), warnings, mapping)

    assert normalized is None
    assert mapping == {}
    assert warnings[0]["kind"] == "ignored_mcp_namespace"


def test_tutorial_tools_are_forwarded_with_flag(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_PROXY_FORWARD_MCP_TUTORIAL_TOOLS", "1")

    warnings = []
    mapping = {}
    normalized = _normalize_response_tool(_tutorial_namespace_tool(), warnings, mapping)

    names = [(item.get("function") or {}).get("name") for item in normalized]
    assert names == [
        "mcp__follow_online_tutorial__start_tutorial_run",
        "mcp__follow_online_tutorial__search_instructions",
        "mcp__follow_online_tutorial__read_source",
        "mcp__follow_online_tutorial__make_execution_plan",
        "mcp__follow_online_tutorial__revise_plan",
        "mcp__follow_online_tutorial__synthesize_options",
        "mcp__follow_online_tutorial__evaluate_sources",
        "mcp__follow_online_tutorial__record_feedback",
        "mcp__follow_online_tutorial__final_report",
    ]
    assert mapping["mcp__follow_online_tutorial__search_instructions"] == {
        "namespace": "mcp__follow_online_tutorial__",
        "name": "search_instructions",
        "forwarding_class": "tutorial",
    }
    assert warnings[0]["kind"] == "mapped_mcp_namespace"
