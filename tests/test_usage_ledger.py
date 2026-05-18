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
    assert event["route"] == "non_thinking"
    assert event["pricing_model"] == "deepseek-v4-flash"
    assert event["pricing_currency"] == "USD"
    assert event["pricing_unit"] == "per_million_tokens"
    assert event["pricing_input_cache_hit"] == 0.0028

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


def _record_usage_event(
    store,
    *,
    response_id,
    created_at,
    model="deepseek-v4-flash",
    thinking_enabled=False,
    prompt_tokens=100,
    completion_tokens=10,
    total_tokens=110,
    cached_tokens=20,
    reasoning_tokens=0,
    estimated_cost_usd=0.001,
    purpose="final",
    call_index=None,
    request_id=None,
    requested_model=None,
    effective_model=None,
    upstream_model=None,
):
    store.record_usage(
        response_id=response_id,
        previous_response_id=None,
        model=model,
        thinking_enabled=thinking_enabled,
        usage_numbers={
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "cached_tokens": cached_tokens,
            "reasoning_tokens": reasoning_tokens,
        },
        estimated_cost_usd=estimated_cost_usd,
        purpose=purpose,
        call_index=call_index,
        request_id=request_id,
        requested_model=requested_model,
        effective_model=effective_model,
        upstream_model=upstream_model,
    )

    with store._connect() as conn:
        conn.execute(
            "UPDATE usage_events SET created_at = ? WHERE response_id = ?",
            (created_at, response_id),
        )


def test_usage_events_can_filter_by_time_thinking_and_model(tmp_path):
    store = SQLiteResponseStore(tmp_path / "usage.sqlite3")

    _record_usage_event(
        store,
        response_id="stable_old",
        created_at=100,
        thinking_enabled=False,
        model="deepseek-v4-flash",
    )
    _record_usage_event(
        store,
        response_id="thinking_mid",
        created_at=200,
        thinking_enabled=True,
        model="deepseek-v4-flash",
        reasoning_tokens=33,
    )
    _record_usage_event(
        store,
        response_id="thinking_other_model",
        created_at=300,
        thinking_enabled=True,
        model="other-model",
    )
    _record_usage_event(
        store,
        response_id="stable_new",
        created_at=400,
        thinking_enabled=False,
        model="deepseek-v4-flash",
    )

    events = store.usage_events(
        limit=10,
        since=150,
        until=350,
        thinking=True,
        model="deepseek-v4-flash",
    )

    assert [event["response_id"] for event in events] == ["thinking_mid"]
    assert events[0]["thinking_enabled"] == 1
    assert events[0]["reasoning_tokens"] == 33


def test_usage_summary_can_filter_by_time_thinking_and_model(tmp_path):
    store = SQLiteResponseStore(tmp_path / "usage.sqlite3")

    _record_usage_event(
        store,
        response_id="stable_old",
        created_at=100,
        thinking_enabled=False,
        model="deepseek-v4-flash",
        prompt_tokens=100,
        completion_tokens=10,
        total_tokens=110,
        cached_tokens=20,
        reasoning_tokens=0,
        estimated_cost_usd=0.001,
    )
    _record_usage_event(
        store,
        response_id="thinking_mid",
        created_at=200,
        thinking_enabled=True,
        model="deepseek-v4-flash",
        prompt_tokens=200,
        completion_tokens=20,
        total_tokens=220,
        cached_tokens=40,
        reasoning_tokens=12,
        estimated_cost_usd=0.002,
    )
    _record_usage_event(
        store,
        response_id="thinking_new",
        created_at=300,
        thinking_enabled=True,
        model="deepseek-v4-flash",
        prompt_tokens=300,
        completion_tokens=30,
        total_tokens=330,
        cached_tokens=60,
        reasoning_tokens=18,
        estimated_cost_usd=0.003,
    )
    _record_usage_event(
        store,
        response_id="other_model",
        created_at=300,
        thinking_enabled=True,
        model="other-model",
        prompt_tokens=999,
        completion_tokens=999,
        total_tokens=1998,
        cached_tokens=0,
        reasoning_tokens=999,
        estimated_cost_usd=9.999,
    )

    summary = store.usage_summary(
        since=150,
        until=350,
        thinking=True,
        model="deepseek-v4-flash",
    )

    assert summary["request_count"] == 2
    assert summary["prompt_tokens"] == 500
    assert summary["completion_tokens"] == 50
    assert summary["total_tokens"] == 550
    assert summary["cached_tokens"] == 100
    assert summary["reasoning_tokens"] == 30
    assert abs(summary["estimated_cost_usd"] - 0.005) < 1e-12


@pytest.mark.asyncio
async def test_usage_endpoints_accept_filters(tmp_path):
    store = SQLiteResponseStore(tmp_path / "usage.sqlite3")
    app = create_app(deepseek_client=UsageDeepSeekClient(), store=store)

    _record_usage_event(
        store,
        response_id="stable_old",
        created_at=100,
        thinking_enabled=False,
        model="deepseek-v4-flash",
    )
    _record_usage_event(
        store,
        response_id="thinking_mid",
        created_at=200,
        thinking_enabled=True,
        model="deepseek-v4-flash",
        prompt_tokens=200,
        completion_tokens=20,
        total_tokens=220,
        cached_tokens=40,
        reasoning_tokens=12,
        estimated_cost_usd=0.002,
    )
    _record_usage_event(
        store,
        response_id="thinking_other_model",
        created_at=300,
        thinking_enabled=True,
        model="other-model",
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        summary_response = await client.get(
            "/v1/proxy/usage/summary",
            params={
                "since": 150,
                "until": 250,
                "thinking": "true",
                "model": "deepseek-v4-flash",
            },
        )
        events_response = await client.get(
            "/v1/proxy/usage",
            params={
                "limit": 10,
                "since": 150,
                "until": 250,
                "thinking": "true",
                "model": "deepseek-v4-flash",
            },
        )
        bad_range_response = await client.get(
            "/v1/proxy/usage/summary",
            params={
                "since": 300,
                "until": 200,
            },
        )

    assert summary_response.status_code == 200
    summary_data = summary_response.json()
    assert summary_data["filters"] == {
        "since": 150,
        "until": 250,
        "thinking": True,
        "model": "deepseek-v4-flash",
    }
    assert summary_data["summary"]["request_count"] == 1
    assert summary_data["summary"]["prompt_tokens"] == 200

    assert events_response.status_code == 200
    events_data = events_response.json()
    assert events_data["filters"]["thinking"] is True
    assert [event["response_id"] for event in events_data["usage_events"]] == ["thinking_mid"]

    assert bad_range_response.status_code == 400



def _usage_deepseek_tool_call_response(call_id: str, name: str, arguments: dict) -> dict:
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
                                "arguments": __import__("json").dumps(arguments),
                            },
                        }
                    ],
                }
            }
        ],
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 1,
            "total_tokens": 11,
        },
    }


class UsageSequenceDeepSeekClient(DeepSeekClient):
    def __init__(self, responses):
        self.responses = list(responses)

    async def chat_completions(self, payload):
        if not self.responses:
            raise AssertionError("unexpected extra chat_completions call")
        return self.responses.pop(0)


@pytest.mark.asyncio
async def test_usage_records_internal_tool_bridge_call_purposes(tmp_path, monkeypatch):
    for key in [
        "DEEPSEEK_PROXY_MODEL",
        "DEEPSEEK_PROXY_FORCE_MODEL",
        "DEEPSEEK_MODEL",
    ]:
        monkeypatch.delenv(key, raising=False)

    store = SQLiteResponseStore(tmp_path / "usage.sqlite3")
    app = create_app(
        deepseek_client=UsageSequenceDeepSeekClient(
            [
                _usage_deepseek_tool_call_response("call_1", "proxy_echo", {"value": "hello"}),
                {
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": "echo complete",
                            }
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 20,
                        "completion_tokens": 2,
                        "total_tokens": 22,
                    },
                },
            ]
        ),
        store=store,
    )

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
    response_id = response.json()["id"]
    events = store.usage_events(limit=10)

    assert [event["purpose"] for event in events] == ["tool_bridge", "primary"]
    assert {event["response_id"] for event in events} == {response_id}
    assert {event["request_id"] for event in events} == {response_id}
    assert [event["call_index"] for event in events] == [1, 0]
    assert all(event["requested_model"] == "deepseek-v4-pro" for event in events)
    assert all(event["effective_model"] == "deepseek-v4-pro" for event in events)
    assert all(event["upstream_model"] == "deepseek-v4-pro" for event in events)

    summary = store.usage_summary(purpose="tool_bridge")
    assert summary["request_count"] == 1
    assert summary["prompt_tokens"] == 20


def test_usage_events_include_attribution_fields_and_filter_by_purpose(tmp_path):
    store = SQLiteResponseStore(tmp_path / "usage.sqlite3")
    _record_usage_event(
        store,
        response_id="resp_attr",
        created_at=500,
        model="deepseek-v4-flash",
        purpose="liveness_judge",
        call_index=3,
        request_id="resp_attr",
        requested_model="v4-flash-no-thinking",
        effective_model="deepseek-v4-flash",
        upstream_model="deepseek-v4-flash",
    )

    events = store.usage_events(purpose="liveness_judge")
    assert len(events) == 1
    event = events[0]
    assert event["purpose"] == "liveness_judge"
    assert event["call_index"] == 3
    assert event["request_id"] == "resp_attr"
    assert event["requested_model"] == "v4-flash-no-thinking"
    assert event["effective_model"] == "deepseek-v4-flash"
    assert event["upstream_model"] == "deepseek-v4-flash"

    assert store.usage_summary(purpose="liveness_judge")["request_count"] == 1
    assert store.usage_summary(purpose="primary")["request_count"] == 0
