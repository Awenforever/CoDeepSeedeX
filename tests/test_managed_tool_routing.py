import json

import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from deepseek_responses_proxy.app import (
    DeepSeekClient,
    InMemoryResponseStore,
    _normalize_response_tool,
    create_app,
)


class FakeDeepSeekClient(DeepSeekClient):
    def __init__(self, responses):
        self.responses = list(responses)
        self.payloads = []

    async def chat_completions(self, payload):
        self.payloads.append(payload)
        if not self.responses:
            raise AssertionError("No fake DeepSeek response left")
        return self.responses.pop(0)


def text_response(text):
    return {
        "choices": [{"message": {"role": "assistant", "content": text}}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }


def tool_call_response(call_id, name, arguments):
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
                                "arguments": json.dumps(arguments),
                            },
                        }
                    ],
                }
            }
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }


def _normalize_with_report(tool):
    warnings = []
    report = {
        "decisions": [],
        "managed_tools_injected": [],
        "fallback_triggered": False,
        "fallback_reason": None,
        "provider": None,
    }
    normalized = _normalize_response_tool(tool, warnings, {}, report)
    return normalized, warnings, report


def test_native_web_search_maps_to_managed_tool_by_default(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_PROXY_WEB_SEARCH_ROUTING", raising=False)
    normalized, warnings, report = _normalize_with_report({"type": "web_search"})

    assert normalized["type"] == "function"
    assert normalized["function"]["name"] == "codeepseedex_web_search"
    assert any(item.get("mapped_to") == "codeepseedex_web_search" for item in warnings)
    assert report["fallback_triggered"] is True
    assert report["decisions"][0]["reason"] == "native_responses_tool_not_supported_by_deepseek_chat_completions"


def test_native_image_generation_maps_to_managed_tool_by_default(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_PROXY_IMAGE_GENERATION_ROUTING", raising=False)
    normalized, warnings, report = _normalize_with_report({"type": "image_generation"})

    assert normalized["type"] == "function"
    assert normalized["function"]["name"] == "codeepseedex_generate_image"
    assert any(item.get("mapped_to") == "codeepseedex_generate_image" for item in warnings)
    assert report["managed_tools_injected"] == ["codeepseedex_generate_image"]


def test_managed_tool_routing_policy_native_only_does_not_inject_managed_tool(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_PROXY_WEB_SEARCH_ROUTING", "native-only")
    normalized, warnings, report = _normalize_with_report({"type": "web_search"})

    assert normalized is None
    assert report["decisions"][0]["action"] == "not_mapped"
    assert report["decisions"][0]["policy"] == "native_only"
    assert any(item.get("reason") == "routing_policy_native_only_but_deepseek_native_tool_unavailable" for item in warnings)


def test_managed_tool_routing_policy_disabled_drops_native_tool_with_action(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_PROXY_IMAGE_GENERATION_ROUTING", "disabled")
    normalized, warnings, report = _normalize_with_report({"type": "image_generation"})

    assert normalized is None
    assert report["decisions"][0]["action"] == "ignored"
    assert report["decisions"][0]["reason"] == "routing_policy_disabled"
    assert report["decisions"][0]["recommended_action"]


@pytest.mark.asyncio
async def test_managed_web_search_tool_executes_and_second_model_call_receives_result(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DEEPSEEK_PROXY_TOOL_BRIDGE", "1")
    monkeypatch.setenv("DEEPSEEK_PROXY_AGENT_LIVENESS_GUARD", "0")
    monkeypatch.setenv("DEEPSEEK_PROXY_WEB_SEARCH_PROVIDER", "mock")

    fake = FakeDeepSeekClient(
        [
            tool_call_response("call_1", "codeepseedex_web_search", {"query": "managed route", "max_results": 1}),
            text_response("managed web summarized"),
        ]
    )
    app = create_app(deepseek_client=fake, store=InMemoryResponseStore())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/responses",
            json={
                "model": "deepseek-v4-pro",
                "input": "Search using the managed route.",
                "tools": [{"type": "web_search"}],
            },
        )

    assert response.status_code == 200
    assert response.json()["output_text"] == "managed web summarized"
    assert len(fake.payloads) == 2
    first_tool_names = [(tool.get("function") or {}).get("name") for tool in fake.payloads[0]["tools"]]
    assert "codeepseedex_web_search" in first_tool_names
    assert any(_MANAGED_MARKER in message.get("content", "") for message in fake.payloads[0]["messages"])

    tool_messages = [message for message in fake.payloads[1]["messages"] if message["role"] == "tool"]
    assert len(tool_messages) == 1
    result = json.loads(tool_messages[0]["content"])
    assert result["ok"] is True
    assert result["provider"] == "mock"
    assert result["query"] == "managed route"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        status_response = await client.get("/v1/proxy/tool-bridge/status")
    status_data = status_response.json()
    last_decision = status_data["tool_bridge"]["web_search"]["last_route_decision"]
    assert last_decision["managed_function_name"] == "codeepseedex_web_search"
    assert last_decision["action"] == "mapped_to_managed"

    routing = json.loads((tmp_path / ".debug" / "last_compat_warnings.json").read_text())
    assert any(item.get("mapped_to") == "codeepseedex_web_search" for item in routing)


@pytest.mark.asyncio
async def test_managed_image_generation_tool_executes_and_surfaces_image_evidence(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DEEPSEEK_PROXY_TOOL_BRIDGE", "1")
    monkeypatch.setenv("DEEPSEEK_PROXY_AGENT_LIVENESS_GUARD", "0")
    monkeypatch.setenv("DEEPSEEK_PROXY_IMAGE_PROVIDER", "mock")

    fake = FakeDeepSeekClient(
        [
            tool_call_response("call_1", "codeepseedex_generate_image", {"prompt": "managed image", "n": 1}),
            text_response("managed image summarized"),
        ]
    )
    app = create_app(deepseek_client=fake, store=InMemoryResponseStore())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/responses",
            json={
                "model": "deepseek-v4-pro",
                "input": "Generate an image using the managed route.",
                "tools": [{"type": "image_generation"}],
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert "managed image summarized" in data["output_text"]
    assert "Generated image result:" in data["output_text"]
    assert "Provider: mock" in data["output_text"]
    assert "Image 1 URL: https://example.com/mock-generated-image.png" in data["output_text"]


def test_tool_bridge_status_exposes_managed_tool_routing_registry(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_PROXY_WEB_SEARCH_PROVIDER", "mock")
    monkeypatch.setenv("DEEPSEEK_PROXY_IMAGE_PROVIDER", "mock")
    client = TestClient(create_app())

    data = client.get("/v1/proxy/tool-bridge/status").json()
    routing = data["tool_bridge"]["managed_tool_routing"]

    assert routing["enabled"] is True
    assert routing["capabilities"]["web_search"]["managed_function_name"] == "codeepseedex_web_search"
    assert routing["capabilities"]["image_generation"]["managed_function_name"] == "codeepseedex_generate_image"
    assert data["tool_bridge"]["web_search"]["routing_policy"] == "auto"
    assert data["tool_bridge"]["image_generation"]["routing_policy"] == "auto"


_MANAGED_MARKER = "[codeepseedex managed tool routing]"
