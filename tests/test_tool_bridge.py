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


def deepseek_text_response(text="done"):
    return {
        "choices": [{"message": {"role": "assistant", "content": text}}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }


def deepseek_tool_call_response(call_id, name, args):
    return {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": call_id,
                            "type": "function",
                            "function": {
                                "name": name,
                                "arguments": json.dumps(args),
                            },
                        }
                    ],
                }
            }
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }


@pytest.mark.asyncio
async def test_proxy_echo_tool_call_is_executed_and_final_response_is_returned(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_PROXY_TOOL_BRIDGE", "1")

    fake = FakeDeepSeekClient(
        [
            deepseek_tool_call_response("call_1", "proxy_echo", {"value": "hello"}),
            deepseek_text_response("echo complete"),
        ]
    )
    app = create_app(deepseek_client=fake, store=InMemoryResponseStore())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/responses",
            json={
                "model": "deepseek-v4-pro",
                "input": "Use proxy_echo.",
                "tools": [
                    {
                        "type": "function",
                        "name": "proxy_echo",
                        "parameters": {
                            "type": "object",
                            "properties": {"value": {"type": "string"}},
                            "required": ["value"],
                        },
                    }
                ],
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["output_text"] == "echo complete"
    assert len(fake.payloads) == 2

    second_messages = fake.payloads[1]["messages"]
    tool_messages = [m for m in second_messages if m["role"] == "tool"]
    assert len(tool_messages) == 1
    tool_result = json.loads(tool_messages[0]["content"])
    assert tool_result["ok"] is True
    assert tool_result["tool"] == "proxy_echo"
    assert tool_result["value"] == "hello"


@pytest.mark.asyncio
async def test_unknown_proxy_tool_returns_structured_tool_error(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_PROXY_TOOL_BRIDGE", "1")

    fake = FakeDeepSeekClient(
        [
            deepseek_tool_call_response("call_1", "proxy_missing", {"value": "x"}),
            deepseek_text_response("missing handled"),
        ]
    )
    app = create_app(deepseek_client=fake, store=InMemoryResponseStore())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/responses",
            json={
                "model": "deepseek-v4-pro",
                "input": "Use proxy_missing.",
                "tools": [
                    {
                        "type": "function",
                        "name": "proxy_missing",
                        "parameters": {"type": "object", "properties": {}},
                    }
                ],
            },
        )

    assert response.status_code == 200
    assert response.json()["output_text"] == "missing handled"

    tool_messages = [m for m in fake.payloads[1]["messages"] if m["role"] == "tool"]
    result = json.loads(tool_messages[0]["content"])
    assert result["ok"] is False
    assert result["tool"] == "proxy_missing"
    assert result["error"] == "unsupported_proxy_tool"


@pytest.mark.asyncio
async def test_tool_bridge_can_be_disabled(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_PROXY_TOOL_BRIDGE", "0")

    fake = FakeDeepSeekClient(
        [
            deepseek_tool_call_response("call_1", "proxy_echo", {"value": "hello"}),
        ]
    )
    app = create_app(deepseek_client=fake, store=InMemoryResponseStore())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/responses",
            json={
                "model": "deepseek-v4-pro",
                "input": "Use proxy_echo.",
                "tools": [
                    {
                        "type": "function",
                        "name": "proxy_echo",
                        "parameters": {"type": "object", "properties": {}},
                    }
                ],
            },
        )

    assert response.status_code == 200
    data = response.json()
    calls = [item for item in data["output"] if item["type"] == "function_call"]
    assert len(calls) == 1
    assert calls[0]["name"] == "proxy_echo"
    assert len(fake.payloads) == 1


@pytest.mark.asyncio
async def test_non_proxy_tool_calls_keep_existing_function_call_output_behavior(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_PROXY_TOOL_BRIDGE", "1")

    fake = FakeDeepSeekClient(
        [
            deepseek_tool_call_response("call_1", "get_weather", {"city": "Shanghai"}),
        ]
    )
    app = create_app(deepseek_client=fake, store=InMemoryResponseStore())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/responses",
            json={
                "model": "deepseek-v4-pro",
                "input": "Use get_weather.",
                "tools": [
                    {
                        "type": "function",
                        "name": "get_weather",
                        "parameters": {"type": "object", "properties": {}},
                    }
                ],
            },
        )

    assert response.status_code == 200
    data = response.json()
    calls = [item for item in data["output"] if item["type"] == "function_call"]
    assert len(calls) == 1
    assert calls[0]["name"] == "get_weather"
    assert len(fake.payloads) == 1
