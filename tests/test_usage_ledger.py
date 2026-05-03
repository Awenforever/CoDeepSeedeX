import pytest
from httpx import ASGITransport, AsyncClient

from deepseek_responses_proxy.app import DeepSeekClient, SQLiteResponseStore, create_app


class UsageDeepSeekClient(DeepSeekClient):
    async def chat_completions(self, payload):
        return {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "ok",
                    }
                }
            ],
            "usage": {
                "prompt_tokens": 1000,
                "completion_tokens": 500,
                "total_tokens": 1500,
                "prompt_tokens_details": {
                    "cached_tokens": 200,
                },
                "completion_tokens_details": {
                    "reasoning_tokens": 123,
                },
            },
        }


@pytest.mark.asyncio
async def test_usage_is_recorded_in_sqlite_store(tmp_path):
    store = SQLiteResponseStore(tmp_path / "usage.sqlite3")
    app = create_app(deepseek_client=UsageDeepSeekClient(), store=store)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/responses",
            json={
                "model": "deepseek-v4-flash",
                "input": "Reply exactly: ok",
            },
        )

    assert response.status_code == 200

    events = store.usage_events()
    assert len(events) == 1

    event = events[0]
    assert event["model"] == "deepseek-v4-flash"
    assert event["prompt_tokens"] == 1000
    assert event["completion_tokens"] == 500
    assert event["total_tokens"] == 1500
    assert event["cached_tokens"] == 200
    assert event["reasoning_tokens"] == 123

    # cost = (200 * 0.0028 + 800 * 0.14 + 500 * 0.28) / 1_000_000
    expected = (200 * 0.0028 + 800 * 0.14 + 500 * 0.28) / 1_000_000
    assert abs(event["estimated_cost_usd"] - expected) < 1e-12


@pytest.mark.asyncio
async def test_usage_summary_endpoint_returns_totals(tmp_path):
    store = SQLiteResponseStore(tmp_path / "usage.sqlite3")
    app = create_app(deepseek_client=UsageDeepSeekClient(), store=store)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first = await client.post(
            "/v1/responses",
            json={"model": "deepseek-v4-flash", "input": "one"},
        )
        second = await client.post(
            "/v1/responses",
            json={"model": "deepseek-v4-flash", "input": "two"},
        )
        summary = await client.get("/v1/proxy/usage/summary")
        events = await client.get("/v1/proxy/usage?limit=10")

    assert first.status_code == 200
    assert second.status_code == 200

    assert summary.status_code == 200
    data = summary.json()
    assert data["status"] == "ok"
    assert data["summary"]["request_count"] == 2
    assert data["summary"]["prompt_tokens"] == 2000
    assert data["summary"]["completion_tokens"] == 1000
    assert data["summary"]["total_tokens"] == 3000
    assert data["summary"]["cached_tokens"] == 400
    assert data["summary"]["reasoning_tokens"] == 246
    assert data["summary"]["estimated_cost_usd"] > 0
    assert "deepseek-v4-flash" in data["pricing_usd_per_1m"]

    assert events.status_code == 200
    events_data = events.json()
    assert len(events_data["usage_events"]) == 2
