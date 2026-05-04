from deepseek_responses_proxy.app import (
    _input_items_to_messages,
    _repair_tool_call_message_order,
)


def test_consecutive_function_calls_are_coalesced_into_one_assistant_message():
    items = [
        {
            "type": "function_call",
            "call_id": "call_readme",
            "name": "exec_command",
            "arguments": "{\"cmd\": \"cat README.md\"}",
        },
        {
            "type": "function_call",
            "call_id": "call_sample",
            "name": "exec_command",
            "arguments": "{\"cmd\": \"cat sample.py\"}",
        },
        {
            "type": "function_call_output",
            "call_id": "call_readme",
            "output": "README",
        },
        {
            "type": "function_call_output",
            "call_id": "call_sample",
            "output": "sample",
        },
    ]

    messages = _input_items_to_messages(items)

    assert len(messages) == 3
    assert messages[0]["role"] == "assistant"
    assert [tc["id"] for tc in messages[0]["tool_calls"]] == [
        "call_readme",
        "call_sample",
    ]
    assert messages[1]["role"] == "tool"
    assert messages[1]["tool_call_id"] == "call_readme"
    assert messages[2]["role"] == "tool"
    assert messages[2]["tool_call_id"] == "call_sample"

    repaired, changed = _repair_tool_call_message_order(messages)
    assert changed is False
    assert repaired == messages


def test_function_call_groups_are_separated_by_text_items():
    items = [
        {
            "type": "function_call",
            "call_id": "call_1",
            "name": "exec_command",
            "arguments": "{}",
        },
        {"type": "message", "role": "assistant", "content": "done"},
        {
            "type": "function_call",
            "call_id": "call_2",
            "name": "exec_command",
            "arguments": "{}",
        },
    ]

    messages = _input_items_to_messages(items)

    assert messages[0]["role"] == "assistant"
    assert len(messages[0]["tool_calls"]) == 1
    assert messages[1]["role"] == "assistant"
    assert messages[1]["content"] == "done"
    assert messages[2]["role"] == "assistant"
    assert len(messages[2]["tool_calls"]) == 1
