from codexchange_proxy.app import (
    _managed_tool_capability,
    _managed_tool_routing_instruction_message,
    _managed_tool_schema,
)


def test_managed_tool_routing_user_surface_is_provider_neutral() -> None:
    app_text = open("codexchange_proxy/app.py", encoding="utf-8").read()

    forbidden = [
        "DeepSeek/Codex third-party profile",
        "native_responses_tool_not_supported_by_deepseek_chat_completions",
        "routing_policy_native_only_but_deepseek_native_tool_unavailable",
    ]
    for needle in forbidden:
        assert needle not in app_text

    required = [
        "provider-routed Codex profile",
        "native_responses_hosted_tool_not_available_on_provider_routed_codex_profile",
        "routing_policy_native_only_but_native_responses_tool_unavailable",
    ]
    for needle in required:
        assert needle in app_text


def test_managed_tool_schema_descriptions_use_provider_routed_codex_wording() -> None:
    web_schema = _managed_tool_schema("web_search")
    image_schema = _managed_tool_schema("image_generation")

    descriptions = [
        web_schema["function"]["description"],
        image_schema["function"]["description"],
    ]
    for description in descriptions:
        assert "provider-routed Codex profile" in description
        assert "DeepSeek/Codex third-party profile" not in description


def test_managed_tool_capability_reasons_are_provider_neutral() -> None:
    web_capability = _managed_tool_capability("web_search")

    assert (
        web_capability["native_unavailable_reason"]
        == "native_responses_hosted_tool_not_available_on_provider_routed_codex_profile"
    )
    assert "deepseek" not in web_capability["native_unavailable_reason"].lower()


def test_managed_tool_instruction_message_uses_provider_routed_codex_wording() -> None:
    instruction = _managed_tool_routing_instruction_message([_managed_tool_schema("web_search")])

    assert instruction is not None
    content = instruction["content"]
    assert "provider-routed Codex profile" in content
    assert "DeepSeek/Codex third-party profile" not in content
