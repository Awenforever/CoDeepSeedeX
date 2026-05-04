import json

from deepseek_responses_proxy.app import _repair_tool_call_message_order


def test_repair_moves_later_tool_output_next_to_matching_assistant_call():
    messages = [
        {"role": "user", "content": "start"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "exec_command", "arguments": "{}"},
                }
            ],
        },
        {"role": "user", "content": "latest reminder"},
        {"role": "tool", "tool_call_id": "call_1", "content": "done"},
    ]

    repaired, changed = _repair_tool_call_message_order(messages)

    assert changed is True
    assert repaired[1]["role"] == "assistant"
    assert repaired[2]["role"] == "tool"
    assert repaired[2]["tool_call_id"] == "call_1"
    assert repaired[3]["role"] == "user"
    assert repaired[3]["content"] == "latest reminder"


def test_repair_inserts_synthetic_tool_output_when_missing():
    messages = [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call_missing",
                    "type": "function",
                    "function": {"name": "exec_command", "arguments": "{}"},
                }
            ],
        },
        {"role": "user", "content": "continue"},
    ]

    repaired, changed = _repair_tool_call_message_order(messages)

    assert changed is True
    assert repaired[0]["role"] == "assistant"
    assert repaired[1]["role"] == "tool"
    assert repaired[1]["tool_call_id"] == "call_missing"

    payload = json.loads(repaired[1]["content"])
    assert payload["ok"] is False
    assert payload["error"] == "missing_tool_result_repaired"
    assert repaired[2]["role"] == "user"
