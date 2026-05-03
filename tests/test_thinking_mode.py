import pytest
from httpx import ASGITransport, AsyncClient

from deepseek_responses_proxy.app import DeepSeekClient, InMemoryResponseStore, create_app


class RecordingDeepSeekClient(DeepSeekClient):
    def __init__(self, response):
        self.response = response
        self.payloads = []

    async def chat_completions(self, payload):
        self.payloads.append(payload)
        return self.response


def deepseek_response_with_reasoning():
    return {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "ok",
                    "reasoning_content": "private reasoning state",
                }
            }
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }


@pytest.mark.asyncio
async def test_thinking_disabled_by_default(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_THINKING", raising=False)

    fake = RecordingDeepSeekClient(deepseek_response_with_reasoning())
    app = create_app(deepseek_client=fake, store=InMemoryResponseStore())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/responses",
            json={
                "model": "deepseek-v4-flash",
                "input": "Reply exactly: ok",
            },
        )

    assert response.status_code == 200
    assert fake.payloads[0]["thinking"] == {"type": "disabled"}


@pytest.mark.asyncio
async def test_thinking_enabled_by_env(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_THINKING", "enabled")

    fake = RecordingDeepSeekClient(deepseek_response_with_reasoning())
    app = create_app(deepseek_client=fake, store=InMemoryResponseStore())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/responses",
            json={
                "model": "deepseek-v4-flash",
                "input": "Reply exactly: ok",
            },
        )

    assert response.status_code == 200
    assert fake.payloads[0]["thinking"] == {"type": "enabled"}


@pytest.mark.asyncio
async def test_reasoning_content_is_saved_in_assistant_history(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_THINKING", "enabled")

    store = InMemoryResponseStore()
    fake = RecordingDeepSeekClient(deepseek_response_with_reasoning())
    app = create_app(deepseek_client=fake, store=store)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/responses",
            json={
                "model": "deepseek-v4-flash",
                "input": "Reply exactly: ok",
            },
        )

    assert response.status_code == 200
    response_id = response.json()["id"]
    stored = store.get(response_id)

    assert stored is not None
    assert stored.chat_messages[-1]["role"] == "assistant"
    assert stored.chat_messages[-1]["reasoning_content"] == "private reasoning state"


@pytest.mark.asyncio
async def test_thinking_enabled_adds_empty_reasoning_content_when_missing(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_THINKING", "enabled")

    response_without_reasoning = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "ok",
                }
            }
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }

    store = InMemoryResponseStore()
    fake = RecordingDeepSeekClient(response_without_reasoning)
    app = create_app(deepseek_client=fake, store=store)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/responses",
            json={
                "model": "deepseek-v4-flash",
                "input": "Reply exactly: ok",
            },
        )

    assert response.status_code == 200
    stored = store.get(response.json()["id"])

    assert stored is not None
    assert stored.chat_messages[-1]["role"] == "assistant"
    assert "reasoning_content" in stored.chat_messages[-1]
    assert stored.chat_messages[-1]["reasoning_content"] == ""


@pytest.mark.asyncio
async def test_thinking_enabled_adds_reasoning_content_to_request_assistant_messages(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_THINKING", "enabled")

    response = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "final",
                    "reasoning_content": "new reasoning",
                }
            }
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }

    fake = RecordingDeepSeekClient(response)
    app = create_app(deepseek_client=fake, store=InMemoryResponseStore())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        result = await client.post(
            "/v1/responses",
            json={
                "model": "deepseek-v4-flash",
                "input": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [
                            {
                                "type": "output_text",
                                "text": "ok",
                            }
                        ],
                    },
                    {
                        "type": "message",
                        "role": "user",
                        "content": [
                            {
                                "type": "input_text",
                                "text": "continue",
                            }
                        ],
                    },
                ],
            },
        )

    assert result.status_code == 200

    assistant_messages = [
        msg for msg in fake.payloads[0]["messages"]
        if msg["role"] == "assistant"
    ]

    assert assistant_messages
    assert all("reasoning_content" in msg for msg in assistant_messages)
    assert assistant_messages[0]["reasoning_content"] == ""
