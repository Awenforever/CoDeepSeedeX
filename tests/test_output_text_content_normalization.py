import json

from deepseek_responses_proxy.app import (
    _deepseek_message_to_output_items,
    _input_items_to_messages,
)


def _message_text(output_items):
    message = next(item for item in output_items if item.get("type") == "message")
    return message["content"][0]["text"]


def test_input_message_output_text_content_is_plain_text():
    messages = _input_items_to_messages([
        {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": "done"}],
        }
    ])

    assert messages[0]["content"] == "done"


def test_input_message_input_text_content_is_plain_text():
    messages = _input_items_to_messages([
        {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": "hello"}],
        }
    ])

    assert messages[0]["content"] == "hello"


def test_deepseek_output_list_content_is_plain_output_text():
    output_items = _deepseek_message_to_output_items({
        "role": "assistant",
        "content": [{"type": "output_text", "text": "done"}],
    })

    assert _message_text(output_items) == "done"


def test_deepseek_output_json_encoded_content_is_plain_output_text():
    output_items = _deepseek_message_to_output_items({
        "role": "assistant",
        "content": json.dumps([{"type": "output_text", "text": "done"}]),
    })

    assert _message_text(output_items) == "done"


def test_function_call_output_is_unchanged():
    output_items = _deepseek_message_to_output_items({
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": "proxy_time", "arguments": "{}"},
            }
        ],
    })

    assert output_items[0]["type"] == "function_call"
    assert output_items[0]["name"] == "proxy_time"
    assert output_items[0]["call_id"] == "call_1"
    assert output_items[0]["arguments"] == "{}"


def test_mcp_namespace_function_call_output_is_unchanged():
    output_items = _deepseek_message_to_output_items(
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "mcp__cheap_llm__cheap_router_status",
                        "arguments": "{}",
                    },
                }
            ],
        },
        {
            "mcp__cheap_llm__cheap_router_status": {
                "namespace": "mcp__cheap_llm__",
                "name": "cheap_router_status",
            }
        },
    )

    assert output_items[0]["type"] == "function_call"
    assert output_items[0]["name"] == "cheap_router_status"
    assert output_items[0]["namespace"] == "mcp__cheap_llm__"
    assert output_items[0]["call_id"] == "call_1"
    assert output_items[0]["arguments"] == "{}"
