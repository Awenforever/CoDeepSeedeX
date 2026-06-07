from __future__ import annotations

import pytest
from fastapi import HTTPException

from deepseek_responses_proxy.app import DeepSeekClient, _build_chat_payload


class _FakeResponse:
    def __init__(self, status_code: int = 200, text: str = '{"choices":[{"message":{"content":"ok"}}]}') -> None:
        self.status_code = status_code
        self.text = text

    def json(self) -> dict:
        return {"choices": [{"message": {"content": "ok"}}]}


class _RecordingHTTPClient:
    def __init__(self, response: _FakeResponse | None = None) -> None:
        self.response = response or _FakeResponse()
        self.posts: list[dict] = []
        self.urls: list[str] = []

    async def post(self, url: str, json=None, headers=None):  # noqa: A002 - mirrors httpx argument name
        self.urls.append(url)
        self.posts.append(dict(json or {}))
        return self.response


def test_custom_openai_compatible_payload_strips_deepseek_only_params(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DEEPSEEK_PROXY_MODEL_PROVIDER", "custom")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://api.llm.exampleprovider.edu.cn/v1")

    payload = _build_chat_payload(
        model="example-chat-model",
        messages=[{"role": "user", "content": "hi"}],
        tools=None,
        reasoning_effort="max",
        request_payload={"prompt_cache_key": "sess-a", "max_output_tokens": 8},
    )

    assert payload["model"] == "example-chat-model"
    assert payload["max_tokens"] == 8
    assert "user_id" not in payload
    assert "thinking" not in payload
    assert "reasoning_effort" not in payload


def test_deepseek_official_payload_keeps_stable_cache_user_id(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DEEPSEEK_PROXY_MODEL_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")

    payload = _build_chat_payload(
        model="deepseek-v4-flash",
        messages=[{"role": "user", "content": "hi"}],
        tools=None,
        reasoning_effort="max",
        request_payload={"prompt_cache_key": "sess-a"},
    )

    assert payload["user_id"].startswith("codeepseedex_")
    assert "thinking" in payload
    assert payload["reasoning_effort"] == "max"


@pytest.mark.asyncio
async def test_custom_client_sanitizes_payload_and_reports_provider_host(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_PROXY_MODEL_PROVIDER", "custom")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://api.llm.exampleprovider.edu.cn/v1")
    fake_http = _RecordingHTTPClient(_FakeResponse(status_code=400, text='{"error":"unsupported user_id"}'))
    client = DeepSeekClient(api_key="sk-test", base_url="https://api.llm.exampleprovider.edu.cn/v1", http_client=fake_http)

    with pytest.raises(HTTPException) as exc_info:
        await client.chat_completions(
            {
                "model": "example-chat-model",
                "messages": [{"role": "user", "content": "hi"}],
                "user_id": "codeepseedex_test",
                "thinking": {"type": "enabled"},
                "reasoning_effort": "max",
                "max_tokens": 8,
            }
        )

    assert fake_http.posts
    sent = fake_http.posts[0]
    assert "user_id" not in sent
    assert "thinking" not in sent
    assert "reasoning_effort" not in sent
    assert sent["max_tokens"] == 8

    detail = exc_info.value.detail
    assert detail["upstream"] == "custom"
    assert detail["upstream_provider"] == "custom"
    assert detail["base_url_host"] == "api.llm.exampleprovider.edu.cn"
    assert detail["chat_compat_mode"] == "openai_compatible"
    assert detail["status_code"] == 400
