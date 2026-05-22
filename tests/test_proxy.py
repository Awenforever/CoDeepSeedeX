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
    assert transport.requests[0]["model"] == "deepseek-v4-pro"
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


@pytest.mark.asyncio
async def test_semantic_payload_enabled_compacts_real_responses_route_payload_and_status(monkeypatch, client_factory):
    monkeypatch.setenv("DEEPSEEK_THINKING", "enabled")
    monkeypatch.setenv("DEEPSEEK_PROXY_FLATTENED_TOOL_SEMANTIC_PAYLOAD_COMPACTION_MODE", "enabled")
    monkeypatch.setenv("DEEPSEEK_PROXY_FLATTENED_TOOL_SEMANTIC_PAYLOAD_CANARY_ALLOW_ENABLED", "1")
    monkeypatch.setenv("DEEPSEEK_PROXY_FLATTENED_TOOL_SEMANTIC_PAYLOAD_COMPACTION_PRESERVE_RECENT_MESSAGES", "0")
    monkeypatch.setenv("DEEPSEEK_PROXY_FLATTENED_TOOL_SEMANTIC_PAYLOAD_COMPACTION_MIN_MESSAGE_CHARS", "100")
    monkeypatch.setenv("DEEPSEEK_PROXY_FLATTENED_TOOL_SEMANTIC_PAYLOAD_COMPACTION_SUMMARY_CHARS", "900")

    client, transport = await client_factory(
        [
            {
                "id": "chatcmpl_semantic_tool",
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "",
                            "tool_calls": [
                                {
                                    "id": "call_semantic",
                                    "type": "function",
                                    "function": {
                                        "name": "run_tests",
                                        "arguments": "{}",
                                    },
                                }
                            ],
                        }
                    }
                ],
                "usage": {"prompt_tokens": 8, "completion_tokens": 6, "total_tokens": 14},
            },
            {
                "id": "chatcmpl_semantic_final",
                "choices": [{"message": {"role": "assistant", "content": "done"}}],
                "usage": {"prompt_tokens": 14, "completion_tokens": 4, "total_tokens": 18},
            },
        ]
    )

    first = await client.post(
        "/v1/responses",
        json={
            "input": "Run test suite",
            "tools": [
                {
                    "type": "function",
                    "name": "run_tests",
                    "description": "Run tests",
                    "parameters": {"type": "object", "properties": {}},
                }
            ],
        },
    )
    assert first.status_code == 200
    first_body = first.json()

    long_pytest_output = (
        "===== pytest =====\n"
        "collected 123 items\n"
        + ("." * 200)
        + "\n123 passed in 0.42s\n"
        + ("X" * 5000)
    )
    second = await client.post(
        "/v1/responses",
        json={
            "previous_response_id": first_body["id"],
            "input": [
                {
                    "type": "function_call_output",
                    "call_id": "call_semantic",
                    "output": long_pytest_output,
                }
            ],
        },
    )
    assert second.status_code == 200
    assert second.json()["output_text"] == "done"

    assert len(transport.requests) == 2
    second_upstream_messages = transport.requests[1]["messages"]
    second_upstream_serialized = json.dumps(second_upstream_messages, ensure_ascii=False)

    assert transport.requests[1]["thinking"] == {"type": "enabled"}
    assert "[semantic flattened tool transcript compacted by CoDeepSeedeX]" in second_upstream_serialized
    assert "semantic_type: test_output" in second_upstream_serialized
    assert "semantic_risk: low" in second_upstream_serialized
    assert "123 passed in 0.42s" in second_upstream_serialized
    assert "original SQLite history is unchanged" in second_upstream_serialized
    assert "X" * 2000 not in second_upstream_serialized

    status = await client.get("/v1/proxy/status")
    assert status.status_code == 200
    semantic = status.json()["semantic_compaction"]
    payload_event = semantic["latest"]["semantic_payload_compaction"]

    assert semantic["rollout"]["runtime_state"] == "enabled_monitoring"
    assert semantic["rollout"]["enabled_monitoring_healthy"] is True
    assert semantic["rollout"]["latest_payload_mode"] == "enabled"
    assert semantic["rollout"]["latest_payload_applied"] is True
    assert semantic["rollout"]["latest_payload_canary_allowed"] is True
    assert semantic["rollout"]["blockers"] == []

    assert payload_event["present"] is True
    assert payload_event["mode"] == "enabled"
    assert payload_event["effective_mode"] == "enabled"
    assert payload_event["applied"] is True
    assert payload_event["reason"] == "enabled"
    assert payload_event["compacted_count"] == 1
    assert payload_event["tokens_removed"] > 0
    assert payload_event["chars_removed"] > 0
    assert payload_event["semantic_type_counts"]["test_output"] == 1
    assert payload_event["risk_counts"]["low"] == 1
    assert payload_event["policy_decisions"]["compact"] == 1
    assert payload_event["canary_guard"]["allowed"] is True

    top_target = payload_event["top_target"]
    assert top_target["semantic_type"] == "test_output"
    assert top_target["semantic_plan_type"] == "pytest_success"
    assert top_target["semantic_risk"] == "low"
    assert top_target["policy_decision"] == "compact"
    assert top_target["safe_payload_mutation_allowed"] is True
    assert top_target["source"] == "semantic_payload_safety_core_v1"
    assert top_target["tokens_removed"] > 0


@pytest.mark.asyncio
async def test_semantic_payload_enabled_real_route_surfaces_weclaw_display_contract(monkeypatch, client_factory):
    monkeypatch.setenv("DEEPSEEK_THINKING", "enabled")
    monkeypatch.setenv("DEEPSEEK_PROXY_FLATTENED_TOOL_SEMANTIC_PAYLOAD_COMPACTION_MODE", "enabled")
    monkeypatch.setenv("DEEPSEEK_PROXY_FLATTENED_TOOL_SEMANTIC_PAYLOAD_CANARY_ALLOW_ENABLED", "1")
    monkeypatch.setenv("DEEPSEEK_PROXY_FLATTENED_TOOL_SEMANTIC_PAYLOAD_COMPACTION_PRESERVE_RECENT_MESSAGES", "0")
    monkeypatch.setenv("DEEPSEEK_PROXY_FLATTENED_TOOL_SEMANTIC_PAYLOAD_COMPACTION_MIN_MESSAGE_CHARS", "100")
    monkeypatch.setenv("DEEPSEEK_PROXY_FLATTENED_TOOL_SEMANTIC_PAYLOAD_COMPACTION_SUMMARY_CHARS", "900")

    client, transport = await client_factory(
        [
            {
                "id": "chatcmpl_semantic_tool_weclaw",
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "",
                            "tool_calls": [
                                {
                                    "id": "call_semantic_weclaw",
                                    "type": "function",
                                    "function": {
                                        "name": "run_tests",
                                        "arguments": "{}",
                                    },
                                }
                            ],
                        }
                    }
                ],
                "usage": {"prompt_tokens": 8, "completion_tokens": 6, "total_tokens": 14},
            },
            {
                "id": "chatcmpl_semantic_final_weclaw",
                "choices": [{"message": {"role": "assistant", "content": "done"}}],
                "usage": {"prompt_tokens": 14, "completion_tokens": 4, "total_tokens": 18},
            },
        ]
    )

    first = await client.post(
        "/v1/responses",
        json={
            "input": "Run test suite",
            "tools": [
                {
                    "type": "function",
                    "name": "run_tests",
                    "description": "Run tests",
                    "parameters": {"type": "object", "properties": {}},
                }
            ],
        },
    )
    assert first.status_code == 200
    first_body = first.json()

    long_pytest_output = (
        "===== pytest =====\n"
        "collected 321 items\n"
        + ("." * 200)
        + "\n321 passed in 0.73s\n"
        + ("Y" * 6000)
    )
    second = await client.post(
        "/v1/responses",
        json={
            "previous_response_id": first_body["id"],
            "input": [
                {
                    "type": "function_call_output",
                    "call_id": "call_semantic_weclaw",
                    "output": long_pytest_output,
                }
            ],
        },
    )
    assert second.status_code == 200
    assert second.json()["output_text"] == "done"

    assert len(transport.requests) == 2
    second_upstream_serialized = json.dumps(transport.requests[1]["messages"], ensure_ascii=False)
    assert "[semantic flattened tool transcript compacted by CoDeepSeedeX]" in second_upstream_serialized
    assert "321 passed in 0.73s" in second_upstream_serialized
    assert "Y" * 2000 not in second_upstream_serialized

    weclaw_response = await client.get("/v1/proxy/weclaw/status?profile=deepseek-thinking&include_balance=false")
    assert weclaw_response.status_code == 200
    weclaw = weclaw_response.json()

    semantic = weclaw["semantic_compaction"]
    display = semantic["display"]
    runtime_semantic = weclaw["context_window"]["runtime"]["semantic_compaction"]

    assert runtime_semantic["display"] == display
    assert display["available"] is True
    assert display["display_contract_version"] == 1
    assert display["status"] == "applied"
    assert display["mode"] == "enabled"
    assert display["effective_mode"] == "enabled"
    assert display["runtime_state"] == "enabled_monitoring"
    assert display["enabled_monitoring_healthy"] is True
    assert display["applied"] is True
    assert display["applied_count"] == 1
    assert display["tokens_before"] > display["tokens_after"]
    assert display["tokens_removed"] > 0
    dumped_display = json.dumps(display, sort_keys=True)
    assert "chars_before" not in dumped_display
    assert "chars_after" not in dumped_display
    assert "chars_removed" not in dumped_display
    assert display["type_counts"]["test_output"] == 1
    assert display["type_counts"].get("unknown", 0) >= 1
    assert display["type_actions"]["compact"] == 1
    assert display["recommended_actions"]["compact_test_output_summary"] == 1
    assert display["risk_counts"]["low"] == 1
    assert display["blockers"] == []
    assert display["raw_content_exposed"] is False
    assert display["redacted"] is True

    last_event = display["last_event"]
    assert last_event["reason"] == "enabled"
    assert last_event["raw_content_exposed"] is False
    assert last_event["redacted"] is True
    assert last_event["top_target"]["semantic_type"] == "test_output"
    assert last_event["top_target"]["semantic_plan_type"] == "pytest_success"
    assert last_event["top_target"]["semantic_risk"] == "low"
    assert last_event["top_target"]["safe_payload_mutation_allowed"] is True
    assert last_event["top_target"]["source"] == "semantic_payload_safety_core_v1"

    assert all(
        item["path"] != "semantic_compaction.rollout"
        for item in weclaw["diagnostics"]["degraded_fields"]
    )



@pytest.mark.asyncio
async def test_request_model_overrides_env_proxy_model_by_default(monkeypatch, client_factory):
    monkeypatch.setenv("DEEPSEEK_PROXY_MODEL", "deepseek-v4-pro")

    client, transport = await client_factory(
        [
            {
                "id": "chatcmpl_model_override",
                "choices": [{"message": {"role": "assistant", "content": "ok"}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            }
        ]
    )

    response = await client.post(
        "/v1/responses",
        json={
            "model": "deepseek-v4-flash",
            "input": "Reply exactly: ok",
        },
    )

    assert response.status_code == 200
    assert transport.requests[0]["model"] == "deepseek-v4-flash"



@pytest.mark.asyncio
async def test_env_proxy_model_can_force_override_request_model(monkeypatch, client_factory):
    monkeypatch.setenv("DEEPSEEK_PROXY_MODEL", "deepseek-v4-pro")
    monkeypatch.setenv("DEEPSEEK_PROXY_FORCE_MODEL", "1")

    client, transport = await client_factory(
        [
            {
                "id": "chatcmpl_force_model_override",
                "choices": [{"message": {"role": "assistant", "content": "ok"}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            }
        ]
    )

    response = await client.post(
        "/v1/responses",
        json={
            "model": "deepseek-v4-flash",
            "input": "Reply exactly: ok",
        },
    )

    assert response.status_code == 200
    assert transport.requests[0]["model"] == "deepseek-v4-pro"


@pytest.mark.asyncio
async def test_responses_options_are_mapped_to_deepseek_payload(client_factory):
    client, transport = await client_factory(
        [
            {
                "id": "chatcmpl_options",
                "choices": [{"message": {"role": "assistant", "content": "ok"}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            }
        ]
    )

    response = await client.post(
        "/v1/responses",
        json={
            "model": "deepseek-v4-pro",
            "input": "Reply exactly: ok",
            "max_output_tokens": 64,
            "temperature": 0.2,
            "top_p": 0.9,
            "response_format": {"type": "json_object"},
        },
    )

    assert response.status_code == 200
    upstream = transport.requests[0]
    assert upstream["max_tokens"] == 64
    assert upstream["temperature"] == 0.2
    assert upstream["top_p"] == 0.9
    assert upstream["response_format"] == {"type": "json_object"}


@pytest.mark.asyncio
async def test_unsupported_tools_are_recorded_to_debug_file(tmp_path, monkeypatch, client_factory):
    monkeypatch.chdir(tmp_path)

    client, transport = await client_factory(
        [
            {
                "id": "chatcmpl_unsupported_tools",
                "choices": [{"message": {"role": "assistant", "content": "ok"}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            }
        ]
    )

    response = await client.post(
        "/v1/responses",
        json={
            "model": "deepseek-v4-pro",
            "input": "Reply exactly: ok",
            "tools": [
                {"type": "web_search"},
                {"type": "image_generation"},
                {"type": "namespace", "namespace": "deepseek_proxy_account"},
            ],
        },
    )

    assert response.status_code == 200

    tool_names = [
        (tool.get("function") or {}).get("name")
        for tool in transport.requests[0].get("tools", [])
    ]
    assert "proxy_web_search" in tool_names

    warnings_path = tmp_path / ".debug" / "last_compat_warnings.json"
    warnings = json.loads(warnings_path.read_text(encoding="utf-8"))

    assert warnings[0] == {
        "kind": "mapped_tool_type",
        "tool_type": "web_search",
        "mapped_to": "proxy_web_search",
    }

    assert {
        "kind": "mapped_tool_type",
        "tool_type": "image_generation",
        "mapped_to": "proxy_image_generate",
    } in warnings

    unsupported = [
        item for item in warnings if item.get("kind", "").startswith("unsupported")
    ]
    assert unsupported == []

    mapped_namespaces = [
        item for item in warnings if item.get("kind") == "mapped_tool_namespace"
    ]
    assert mapped_namespaces
    assert mapped_namespaces[0]["namespace"] == "deepseek_proxy_account"
    assert {
        "proxy_status",
        "proxy_usage_summary",
        "proxy_usage_events",
        "proxy_balance",
    }.issubset(set(mapped_namespaces[0]["mapped_to"]))
