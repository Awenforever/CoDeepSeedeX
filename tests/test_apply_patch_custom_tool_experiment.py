from deepseek_responses_proxy.app import _normalize_response_tool


def _apply_patch_tool():
    return {
        "type": "custom",
        "name": "apply_patch",
        "description": "Use apply_patch to edit files.",
        "format": {
            "type": "grammar",
            "syntax": "lark",
            "definition": "large grammar omitted from warnings",
        },
    }


def test_apply_patch_custom_tool_is_ignored_by_default(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_PROXY_FORWARD_CUSTOM_APPLY_PATCH", raising=False)

    warnings = []
    normalized = _normalize_response_tool(_apply_patch_tool(), warnings)

    assert normalized is None
    assert warnings[0]["kind"] == "ignored_custom_tool"
    assert warnings[0]["name"] == "apply_patch"
    assert warnings[0]["format"] == {"type": "grammar", "syntax": "lark"}


def test_apply_patch_custom_tool_can_be_experimentally_mapped(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_PROXY_FORWARD_CUSTOM_APPLY_PATCH", "1")

    warnings = []
    normalized = _normalize_response_tool(_apply_patch_tool(), warnings)

    assert normalized is not None
    assert normalized["type"] == "function"
    assert normalized["function"]["name"] == "apply_patch"
    assert "input" in normalized["function"]["parameters"]["properties"]
    assert normalized["function"]["parameters"]["required"] == ["input"]
    assert "*** Begin Patch" in normalized["function"]["description"]
    assert "*** Update File: relative/path" in normalized["function"]["description"]
    assert "*** End Patch" in normalized["function"]["description"]
    assert "Codex apply_patch format" in normalized["function"]["parameters"]["properties"]["input"]["description"]

    assert warnings[0]["kind"] == "mapped_custom_tool"
    assert warnings[0]["tool_type"] == "custom"
    assert warnings[0]["name"] == "apply_patch"
    assert warnings[0]["mapped_to"] == "apply_patch"
    assert "definition" not in warnings[0]["format"]
