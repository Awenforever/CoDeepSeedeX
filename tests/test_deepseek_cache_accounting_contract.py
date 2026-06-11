from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from codexchange_proxy.app import DeepSeekClient, SQLiteResponseStore, create_app, _build_chat_payload


class CacheUsageDeepSeekClient(DeepSeekClient):
    async def chat_completions(self, payload):
        return {
            "choices": [{"message": {"role": "assistant", "content": "ok"}}],
            "usage": {
                "prompt_tokens": 1000,
                "prompt_cache_hit_tokens": 900,
                "prompt_cache_miss_tokens": 100,
                "completion_tokens": 50,
                "total_tokens": 1050,
            },
        }


@pytest.mark.asyncio
async def test_deepseek_cache_hit_miss_fields_are_recorded_and_exposed(tmp_path):
    store = SQLiteResponseStore(tmp_path / "usage.sqlite3")
    app = create_app(deepseek_client=CacheUsageDeepSeekClient(), store=store)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/responses",
            json={"model": "deepseek-v4-flash", "input": "ok", "prompt_cache_key": "sess-a"},
        )
        status = await client.get("/v1/proxy/weclaw/status?profile=deepseek&session_id=sess-a")

    assert response.status_code == 200
    event = store.usage_events(limit=1)[0]
    assert event["cached_tokens"] == 900
    assert event["prompt_cache_hit_tokens"] == 900
    assert event["prompt_cache_miss_tokens"] == 100

    summary = store.usage_summary(session_id="sess-a")
    assert summary["prompt_cache_hit_tokens"] == 900
    assert summary["prompt_cache_miss_tokens"] == 100

    data = status.json()
    assert data["tokens"]["cache"]["session"]["prompt_cache_hit_tokens"] == 900
    assert data["tokens"]["cache"]["session"]["prompt_cache_miss_tokens"] == 100
    assert data["tokens"]["cache"]["last_turn"]["cache_hit_ratio"] == pytest.approx(0.9)
    assert data["cost"]["cost_uses_provider_cache_hit_miss_tokens"] is True
    assert data["cost"]["provider_cache"]["session"]["prompt_cache_hit_tokens"] == 900


def test_deepseek_payload_sets_stable_user_id_and_canonicalizes_tools(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    request_payload = {"prompt_cache_key": "sess-a"}
    tools = [
        {"function": {"parameters": {"properties": {"b": {"type": "string"}, "a": {"type": "string"}}, "type": "object"}, "name": "ztool"}, "type": "function"},
        {"type": "function", "function": {"name": "atool", "parameters": {"type": "object", "properties": {"x": {"type": "string"}}}}},
    ]
    first = _build_chat_payload(model="deepseek-v4-flash", messages=[{"role": "user", "content": "x"}], tools=tools, request_payload=request_payload)
    second = _build_chat_payload(model="deepseek-v4-flash", messages=[{"role": "user", "content": "x"}], tools=list(reversed(tools)), request_payload=request_payload)

    assert first["user_id"].startswith("codexchange_")
    assert first["user_id"] == second["user_id"]
    assert [tool["function"]["name"] for tool in first["tools"]] == ["atool", "ztool"]
    assert first["tools"] == second["tools"]
    assert first["tool_choice"] == "auto"
