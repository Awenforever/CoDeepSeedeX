import json

import pytest
from httpx import ASGITransport, AsyncClient

from deepseek_responses_proxy.app import DeepSeekClient, InMemoryResponseStore, create_app


class FakeDeepSeekClient(DeepSeekClient):
    def __init__(self, responses):
        self.responses = list(responses)
        self.payloads = []

    async def chat_completions(self, payload):
        self.payloads.append(payload)
        if not self.responses:
            raise AssertionError("No fake DeepSeek response left")
        return self.responses.pop(0)


def deepseek_tool_call_response(*tool_calls):
    return {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": list(tool_calls),
                }
            }
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }


def deepseek_text_response(text="done"):
    return {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": text,
                }
            }
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }


def tool_call(call_id, name, args):
    return {
        "id": call_id,
        "type": "function",
        "function": {
            "name": name,
            "arguments": json.dumps(args),
        },
    }


@pytest.mark.asyncio
async def test_multiple_tool_calls_are_mapped_to_multiple_function_call_items():
    fake = FakeDeepSeekClient(
        [
            deepseek_tool_call_response(
                tool_call("call_1", "pwd", {}),
                tool_call("call_2", "list_files", {"path": "."}),
            )
        ]
    )
    app = create_app(deepseek_client=fake, store=InMemoryResponseStore())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/responses",
            json={
                "model": "deepseek-v4-flash",
                "input": "Use tools.",
                "tools": [
                    {
                        "type": "function",
                        "name": "pwd",
                        "description": "Return current directory.",
                        "parameters": {"type": "object", "properties": {}},
                    },
                    {
                        "type": "function",
                        "name": "list_files",
                        "description": "List files.",
                        "parameters": {
                            "type": "object",
                            "properties": {"path": {"type": "string"}},
                        },
                    },
                ],
            },
        )

    assert response.status_code == 200
    data = response.json()
    calls = [item for item in data["output"] if item["type"] == "function_call"]

    assert len(calls) == 2
    assert calls[0]["call_id"] == "call_1"
    assert calls[0]["name"] == "pwd"
    assert calls[1]["call_id"] == "call_2"
    assert calls[1]["name"] == "list_files"


@pytest.mark.asyncio
async def test_multiple_function_call_outputs_become_multiple_tool_messages():
    fake = FakeDeepSeekClient(
        [
            deepseek_tool_call_response(
                tool_call("call_1", "pwd", {}),
                tool_call("call_2", "list_files", {"path": "."}),
            ),
            deepseek_text_response("all tools received"),
        ]
    )
    app = create_app(deepseek_client=fake, store=InMemoryResponseStore())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first = await client.post(
            "/v1/responses",
            json={
                "model": "deepseek-v4-flash",
                "input": "Use tools.",
                "tools": [
                    {
                        "type": "function",
                        "name": "pwd",
                        "parameters": {"type": "object", "properties": {}},
                    },
                    {
                        "type": "function",
                        "name": "list_files",
                        "parameters": {"type": "object", "properties": {}},
                    },
                ],
            },
        )
        first_data = first.json()

        second = await client.post(
            "/v1/responses",
            json={
                "model": "deepseek-v4-flash",
                "previous_response_id": first_data["id"],
                "input": [
                    {
                        "type": "function_call_output",
                        "call_id": "call_1",
                        "output": "/home/kelvin/projects",
                    },
                    {
                        "type": "function_call_output",
                        "call_id": "call_2",
                        "output": "file_a\nfile_b",
                    },
                ],
            },
        )

    assert second.status_code == 200
    second_payload = fake.payloads[1]
    tool_messages = [m for m in second_payload["messages"] if m["role"] == "tool"]

    assert len(tool_messages) == 2
    assert tool_messages[0]["tool_call_id"] == "call_1"
    assert tool_messages[0]["content"] == "/home/kelvin/projects"
    assert tool_messages[1]["tool_call_id"] == "call_2"
    assert tool_messages[1]["content"] == "file_a\nfile_b"


@pytest.mark.asyncio
async def test_duplicate_function_call_input_is_filtered_when_previous_response_id_exists():
    fake = FakeDeepSeekClient(
        [
            deepseek_tool_call_response(tool_call("call_1", "pwd", {})),
            deepseek_text_response("received"),
        ]
    )
    app = create_app(deepseek_client=fake, store=InMemoryResponseStore())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first = await client.post(
            "/v1/responses",
            json={
                "model": "deepseek-v4-flash",
                "input": "Run pwd.",
                "tools": [
                    {
                        "type": "function",
                        "name": "pwd",
                        "parameters": {"type": "object", "properties": {}},
                    }
                ],
            },
        )
        first_data = first.json()

        second = await client.post(
            "/v1/responses",
            json={
                "model": "deepseek-v4-flash",
                "previous_response_id": first_data["id"],
                "input": [
                    {
                        "type": "function_call",
                        "call_id": "call_1",
                        "name": "pwd",
                        "arguments": "{}",
                    },
                    {
                        "type": "function_call_output",
                        "call_id": "call_1",
                        "output": "/tmp",
                    },
                ],
            },
        )

    assert second.status_code == 200
    second_payload = fake.payloads[1]
    assistant_tool_call_messages = [
        m for m in second_payload["messages"]
        if m["role"] == "assistant" and m.get("tool_calls")
    ]

    assert len(assistant_tool_call_messages) == 1
    assert assistant_tool_call_messages[0]["tool_calls"][0]["id"] == "call_1"


@pytest.mark.asyncio
async def test_empty_tool_output_is_preserved_as_empty_string():
    fake = FakeDeepSeekClient(
        [
            deepseek_tool_call_response(tool_call("call_1", "empty_tool", {})),
            deepseek_text_response("empty ok"),
        ]
    )
    app = create_app(deepseek_client=fake, store=InMemoryResponseStore())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first = await client.post(
            "/v1/responses",
            json={
                "model": "deepseek-v4-flash",
                "input": "Call empty tool.",
                "tools": [
                    {
                        "type": "function",
                        "name": "empty_tool",
                        "parameters": {"type": "object", "properties": {}},
                    }
                ],
            },
        )
        first_data = first.json()

        second = await client.post(
            "/v1/responses",
            json={
                "model": "deepseek-v4-flash",
                "previous_response_id": first_data["id"],
                "input": [
                    {
                        "type": "function_call_output",
                        "call_id": "call_1",
                        "output": "",
                    }
                ],
            },
        )

    assert second.status_code == 200
    second_payload = fake.payloads[1]
    tool_messages = [m for m in second_payload["messages"] if m["role"] == "tool"]

    assert tool_messages[0]["content"] == ""


@pytest.mark.asyncio
async def test_large_tool_output_is_preserved():
    large_output = "x" * 10000
    fake = FakeDeepSeekClient(
        [
            deepseek_tool_call_response(tool_call("call_1", "large_tool", {})),
            deepseek_text_response("large ok"),
        ]
    )
    app = create_app(deepseek_client=fake, store=InMemoryResponseStore())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first = await client.post(
            "/v1/responses",
            json={
                "model": "deepseek-v4-flash",
                "input": "Call large tool.",
                "tools": [
                    {
                        "type": "function",
                        "name": "large_tool",
                        "parameters": {"type": "object", "properties": {}},
                    }
                ],
            },
        )
        first_data = first.json()

        second = await client.post(
            "/v1/responses",
            json={
                "model": "deepseek-v4-flash",
                "previous_response_id": first_data["id"],
                "input": [
                    {
                        "type": "function_call_output",
                        "call_id": "call_1",
                        "output": large_output,
                    }
                ],
            },
        )

    assert second.status_code == 200
    second_payload = fake.payloads[1]
    tool_messages = [m for m in second_payload["messages"] if m["role"] == "tool"]

    assert tool_messages[0]["content"] == large_output


@pytest.mark.asyncio
async def test_dangling_tool_call_history_is_repaired_before_new_user_message():
    fake = FakeDeepSeekClient([deepseek_text_response("continued")])
    store = InMemoryResponseStore()
    app = create_app(deepseek_client=fake, store=store)

    previous_response = {
        "id": "resp_dangling",
        "object": "response",
        "created_at": 123,
        "status": "completed",
        "model": "deepseek-v4-flash",
        "previous_response_id": None,
        "output": [],
        "output_text": "",
        "usage": {},
    }
    dangling_history = [
        {"role": "user", "content": "Run pwd."},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [tool_call("call_1", "pwd", {})],
        },
    ]
    store.save(previous_response, dangling_history)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/responses",
            json={
                "model": "deepseek-v4-flash",
                "previous_response_id": "resp_dangling",
                "input": "Continue without a tool result.",
            },
        )

    assert response.status_code == 200

    sent_messages = fake.payloads[0]["messages"]
    assert sent_messages[1]["role"] == "assistant"
    assert sent_messages[1]["tool_calls"][0]["id"] == "call_1"
    assert sent_messages[2]["role"] == "tool"
    assert sent_messages[2]["tool_call_id"] == "call_1"
    assert "not completed" in sent_messages[2]["content"]
    assert sent_messages[3]["role"] == "user"
    assert sent_messages[3]["content"] == "Continue without a tool result."

    stored = store.get(response.json()["id"])
    assert stored is not None
    assert stored.chat_messages[2]["role"] == "tool"
    assert stored.chat_messages[2]["tool_call_id"] == "call_1"


@pytest.mark.asyncio
async def test_matching_tool_output_does_not_get_synthetic_repair_message():
    fake = FakeDeepSeekClient([deepseek_text_response("received")])
    store = InMemoryResponseStore()
    app = create_app(deepseek_client=fake, store=store)

    previous_response = {
        "id": "resp_tool_pending",
        "object": "response",
        "created_at": 123,
        "status": "completed",
        "model": "deepseek-v4-flash",
        "previous_response_id": None,
        "output": [],
        "output_text": "",
        "usage": {},
    }
    pending_history = [
        {"role": "user", "content": "Run pwd."},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [tool_call("call_1", "pwd", {})],
        },
    ]
    store.save(previous_response, pending_history)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/responses",
            json={
                "model": "deepseek-v4-flash",
                "previous_response_id": "resp_tool_pending",
                "input": [
                    {
                        "type": "function_call_output",
                        "call_id": "call_1",
                        "output": "/tmp",
                    }
                ],
            },
        )

    assert response.status_code == 200

    sent_messages = fake.payloads[0]["messages"]
    tool_messages = [m for m in sent_messages if m["role"] == "tool"]

    assert len(tool_messages) == 1
    assert tool_messages[0]["tool_call_id"] == "call_1"
    assert tool_messages[0]["content"] == "/tmp"
    assert "not completed" not in tool_messages[0]["content"]


@pytest.mark.asyncio
async def test_self_contained_tool_fragments_are_flattened_when_no_tools_are_available():
    fake = FakeDeepSeekClient([deepseek_text_response("weather summarized")])
    app = create_app(deepseek_client=fake, store=InMemoryResponseStore())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/responses",
            json={
                "model": "deepseek-v4-flash",
                "input": [
                    {
                        "type": "message",
                        "role": "user",
                        "content": [
                            {
                                "type": "input_text",
                                "text": "What is the weather?",
                            }
                        ],
                    },
                    {
                        "type": "function_call",
                        "call_id": "call_1",
                        "name": "get_weather",
                        "arguments": "{\"city\":\"Shanghai\"}",
                    },
                    {
                        "type": "function_call_output",
                        "call_id": "call_1",
                        "output": "{\"weather\":\"sunny\"}",
                    },
                ],
            },
        )

    assert response.status_code == 200

    sent_messages = fake.payloads[0]["messages"]

    assert all("tool_calls" not in message for message in sent_messages)
    assert all(message["role"] != "tool" for message in sent_messages)

    transcript = "\n".join(message.get("content", "") for message in sent_messages)
    assert "tool call transcript" in transcript
    assert "get_weather" in transcript
    assert "tool output transcript" in transcript
    assert '{"weather":"sunny"}' in transcript


@pytest.mark.asyncio
async def test_self_contained_tool_fragments_keep_protocol_when_tools_are_available():
    fake = FakeDeepSeekClient([deepseek_text_response("weather summarized")])
    app = create_app(deepseek_client=fake, store=InMemoryResponseStore())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/responses",
            json={
                "model": "deepseek-v4-flash",
                "tools": [
                    {
                        "type": "function",
                        "name": "get_weather",
                        "parameters": {"type": "object", "properties": {}},
                    }
                ],
                "input": [
                    {
                        "type": "message",
                        "role": "user",
                        "content": [
                            {
                                "type": "input_text",
                                "text": "What is the weather?",
                            }
                        ],
                    },
                    {
                        "type": "function_call",
                        "call_id": "call_1",
                        "name": "get_weather",
                        "arguments": "{\"city\":\"Shanghai\"}",
                    },
                    {
                        "type": "function_call_output",
                        "call_id": "call_1",
                        "output": "{\"weather\":\"sunny\"}",
                    },
                ],
            },
        )

    assert response.status_code == 200

    sent_messages = fake.payloads[0]["messages"]
    assert any(message.get("tool_calls") for message in sent_messages)
    assert any(message["role"] == "tool" for message in sent_messages)


@pytest.mark.asyncio
async def test_thinking_mode_flattens_completed_tool_fragments_even_when_tools_are_available(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_THINKING", "enabled")

    fake = FakeDeepSeekClient([deepseek_text_response("weather summarized")])
    app = create_app(deepseek_client=fake, store=InMemoryResponseStore())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/responses",
            json={
                "model": "deepseek-v4-flash",
                "tools": [
                    {
                        "type": "function",
                        "name": "get_weather",
                        "parameters": {"type": "object", "properties": {}},
                    }
                ],
                "input": [
                    {
                        "type": "message",
                        "role": "user",
                        "content": [
                            {
                                "type": "input_text",
                                "text": "What is the weather?",
                            }
                        ],
                    },
                    {
                        "type": "function_call",
                        "call_id": "call_1",
                        "name": "get_weather",
                        "arguments": "{\"city\":\"Shanghai\"}",
                    },
                    {
                        "type": "function_call_output",
                        "call_id": "call_1",
                        "output": "{\"weather\":\"sunny\"}",
                    },
                ],
            },
        )

    assert response.status_code == 200

    sent_payload = fake.payloads[0]
    sent_messages = sent_payload["messages"]

    assert sent_payload.get("tools")
    assert all("tool_calls" not in message for message in sent_messages)
    assert all(message["role"] != "tool" for message in sent_messages)

    transcript = "\n".join(message.get("content", "") for message in sent_messages)
    assert "tool call transcript" in transcript
    assert "get_weather" in transcript
    assert "tool output transcript" in transcript
    assert '{"weather":"sunny"}' in transcript
