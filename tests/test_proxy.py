from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx
import pytest

from deepseek_responses_proxy.app import DeepSeekClient, InMemoryResponseStore, create_app


class SequenceTransport(httpx.AsyncBaseTransport):
    def __init__(self, responses: list[dict]):
        self._responses = responses
        self.requests: list[dict] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(json.loads(request.content.decode("utf-8")))
        if not self._responses:
            raise AssertionError("No mock DeepSeek response left")
        payload = self._responses.pop(0)
        return httpx.Response(200, json=payload, request=request)


@pytest.fixture
async def client_factory() -> AsyncIterator:
    clients: list[httpx.AsyncClient] = []

    async def _make(deepseek_payloads: list[dict]) -> tuple[httpx.AsyncClient, SequenceTransport]:
        transport = SequenceTransport(deepseek_payloads)
        deepseek_http = httpx.AsyncClient(transport=transport)
        app = create_app(
            deepseek_client=DeepSeekClient(api_key="test", base_url="https://example.deepseek", http_client=deepseek_http),
            store=InMemoryResponseStore(),
        )
        client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver")
        clients.extend([client, deepseek_http])
        return client, transport

    yield _make

    for client in clients:
        await client.aclose()


@pytest.mark.asyncio
async def test_pure_text_response(client_factory):
    client, transport = await client_factory(
        [
            {
                "id": "chatcmpl_1",
                "choices": [{"message": {"role": "assistant", "content": "Hello from DeepSeek"}}],
                "usage": {"prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 7},
            }
        ]
    )

    response = await client.post("/v1/responses", json={"input": "Hi"})
    assert response.status_code == 200
    body = response.json()
    assert body["output_text"] == "Hello from DeepSeek"
    assert body["output"][0]["type"] == "message"
    assert transport.requests[0]["model"] == "deepseek-v4-flash"
    assert transport.requests[0]["thinking"] == {"type": "disabled"}
    assert transport.requests[0]["messages"] == [{"role": "user", "content": "Hi"}]

    fetched = await client.get(f"/v1/responses/{body['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == body["id"]


@pytest.mark.asyncio
async def test_tool_call_is_mapped_to_function_call_output_item(client_factory):
    client, transport = await client_factory(
        [
            {
                "id": "chatcmpl_tool",
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "",
                            "tool_calls": [
                                {
                                    "id": "call_123",
                                    "type": "function",
                                    "function": {
                                        "name": "lookup_weather",
                                        "arguments": "{\"city\":\"Shanghai\"}",
                                    },
                                }
                            ],
                        }
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            }
        ]
    )

    response = await client.post(
        "/v1/responses",
        json={
            "input": "Check weather",
            "tools": [
                {
                    "type": "function",
                    "name": "lookup_weather",
                    "description": "Weather lookup",
                    "parameters": {"type": "object", "properties": {"city": {"type": "string"}}},
                }
            ],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["output"][0]["type"] == "function_call"
    assert body["output"][0]["call_id"] == "call_123"
    assert body["output"][0]["name"] == "lookup_weather"
    assert transport.requests[0]["tools"][0]["function"]["name"] == "lookup_weather"


@pytest.mark.asyncio
async def test_previous_response_with_function_call_output_preserves_assistant_tool_call_message(client_factory):
    client, transport = await client_factory(
        [
            {
                "id": "chatcmpl_tool",
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "",
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {
                                        "name": "lookup_weather",
                                        "arguments": "{\"city\":\"Shanghai\"}",
                                    },
                                }
                            ],
                        }
                    }
                ],
                "usage": {"prompt_tokens": 8, "completion_tokens": 6, "total_tokens": 14},
            },
            {
                "id": "chatcmpl_final",
                "choices": [{"message": {"role": "assistant", "content": "It is sunny."}}],
                "usage": {"prompt_tokens": 14, "completion_tokens": 4, "total_tokens": 18},
            },
        ]
    )

    first = await client.post(
        "/v1/responses",
        json={
            "input": "What is the weather?",
            "tools": [
                {
                    "type": "function",
                    "name": "lookup_weather",
                    "parameters": {"type": "object", "properties": {"city": {"type": "string"}}},
                }
            ],
        },
    )
    assert first.status_code == 200
    first_body = first.json()

    second = await client.post(
        "/v1/responses",
        json={
            "previous_response_id": first_body["id"],
            "input": [
                {
                    "type": "function_call_output",
                    "call_id": "call_1",
                    "output": {"weather": "sunny"},
                }
            ],
        },
    )
    assert second.status_code == 200
    second_body = second.json()
    assert second_body["output_text"] == "It is sunny."

    second_request_messages = transport.requests[1]["messages"]
    assert second_request_messages[0] == {"role": "user", "content": "What is the weather?"}
    assert second_request_messages[1]["role"] == "assistant"
    assert second_request_messages[1]["tool_calls"][0]["id"] == "call_1"
    assert second_request_messages[2] == {
        "role": "tool",
        "tool_call_id": "call_1",
        "content": "{\"weather\": \"sunny\"}",
    }
