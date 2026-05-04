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


@pytest.mark.asyncio
async def test_web_search_tool_is_mapped_to_proxy_web_search(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DEEPSEEK_PROXY_TOOL_BRIDGE", "1")

    fake = FakeDeepSeekClient([deepseek_text_response("search tool available")])
    app = create_app(deepseek_client=fake, store=InMemoryResponseStore())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/responses",
            json={
                "model": "deepseek-v4-pro",
                "input": "Search if needed.",
                "tools": [{"type": "web_search"}],
            },
        )

    assert response.status_code == 200
    tool_names = [
        (tool.get("function") or {}).get("name")
        for tool in fake.payloads[0].get("tools", [])
    ]
    assert "proxy_web_search" in tool_names

    warnings = json.loads((tmp_path / ".debug" / "last_compat_warnings.json").read_text())
    assert warnings == [
        {
            "kind": "mapped_tool_type",
            "tool_type": "web_search",
            "mapped_to": "proxy_web_search",
        }
    ]


@pytest.mark.asyncio
async def test_proxy_web_search_mock_provider_executes(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_PROXY_TOOL_BRIDGE", "1")
    monkeypatch.setenv("DEEPSEEK_PROXY_WEB_SEARCH_PROVIDER", "mock")

    fake = FakeDeepSeekClient(
        [
            deepseek_tool_call_response(
                "call_1",
                "proxy_web_search",
                {"query": "deepseek proxy", "max_results": 2},
            ),
            deepseek_text_response("search summarized"),
        ]
    )
    app = create_app(deepseek_client=fake, store=InMemoryResponseStore())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/responses",
            json={
                "model": "deepseek-v4-pro",
                "input": "Search the web.",
                "tools": [{"type": "web_search"}],
            },
        )

    assert response.status_code == 200
    assert response.json()["output_text"] == "search summarized"

    tool_messages = [m for m in fake.payloads[1]["messages"] if m["role"] == "tool"]
    assert len(tool_messages) == 1
    result = json.loads(tool_messages[0]["content"])
    assert result["ok"] is True
    assert result["provider"] == "mock"
    assert result["query"] == "deepseek proxy"
    assert result["results"][0]["title"].startswith("Mock search result")


@pytest.mark.asyncio
async def test_proxy_web_search_missing_serpapi_key_returns_structured_error(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_PROXY_TOOL_BRIDGE", "1")
    monkeypatch.setenv("DEEPSEEK_PROXY_WEB_SEARCH_PROVIDER", "serpapi")
    monkeypatch.delenv("SERPAPI_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_PROXY_SERPAPI_API_KEY", raising=False)

    fake = FakeDeepSeekClient(
        [
            deepseek_tool_call_response(
                "call_1",
                "proxy_web_search",
                {"query": "deepseek proxy"},
            ),
            deepseek_text_response("missing key handled"),
        ]
    )
    app = create_app(deepseek_client=fake, store=InMemoryResponseStore())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/responses",
            json={
                "model": "deepseek-v4-pro",
                "input": "Search the web.",
                "tools": [{"type": "web_search"}],
            },
        )

    assert response.status_code == 200
    assert response.json()["output_text"] == "missing key handled"

    tool_messages = [m for m in fake.payloads[1]["messages"] if m["role"] == "tool"]
    result = json.loads(tool_messages[0]["content"])
    assert result["ok"] is False
    assert result["provider"] == "serpapi"
    assert result["error"] == "missing_api_key"


@pytest.mark.asyncio
async def test_deepseek_proxy_account_namespace_is_mapped_while_image_generation_is_mapped(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    fake = FakeDeepSeekClient([deepseek_text_response("unsupported recorded")])
    app = create_app(deepseek_client=fake, store=InMemoryResponseStore())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/responses",
            json={
                "model": "deepseek-v4-pro",
                "input": "Do not use tools.",
                "tools": [
                    {"type": "image_generation"},
                    {"type": "namespace", "namespace": "deepseek_proxy_account"},
                ],
            },
        )

    assert response.status_code == 200

    tool_names = [
        (tool.get("function") or {}).get("name")
        for tool in fake.payloads[0].get("tools", [])
    ]
    assert "proxy_image_generate" in tool_names

    warnings = json.loads((tmp_path / ".debug" / "last_compat_warnings.json").read_text())
    assert warnings[0] == {
        "kind": "mapped_tool_type",
        "tool_type": "image_generation",
        "mapped_to": "proxy_image_generate",
    }
    unsupported = [
        item for item in warnings if item.get("kind") == "unsupported_tool_type"
    ]
    assert unsupported == []


@pytest.mark.asyncio
async def test_image_generation_tool_is_mapped_to_proxy_image_generate(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DEEPSEEK_PROXY_TOOL_BRIDGE", "1")

    fake = FakeDeepSeekClient([deepseek_text_response("image tool available")])
    app = create_app(deepseek_client=fake, store=InMemoryResponseStore())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/responses",
            json={
                "model": "deepseek-v4-pro",
                "input": "Generate an image if needed.",
                "tools": [{"type": "image_generation"}],
            },
        )

    assert response.status_code == 200
    tool_names = [
        (tool.get("function") or {}).get("name")
        for tool in fake.payloads[0].get("tools", [])
    ]
    assert "proxy_image_generate" in tool_names

    warnings = json.loads((tmp_path / ".debug" / "last_compat_warnings.json").read_text())
    assert warnings == [
        {
            "kind": "mapped_tool_type",
            "tool_type": "image_generation",
            "mapped_to": "proxy_image_generate",
        }
    ]


@pytest.mark.asyncio
async def test_proxy_image_generate_mock_provider_executes(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_PROXY_TOOL_BRIDGE", "1")
    monkeypatch.setenv("DEEPSEEK_PROXY_IMAGE_PROVIDER", "mock")

    fake = FakeDeepSeekClient(
        [
            deepseek_tool_call_response(
                "call_1",
                "proxy_image_generate",
                {"prompt": "a cute orange cat", "size": "1024x1024", "n": 1},
            ),
            deepseek_text_response("image summarized"),
        ]
    )
    app = create_app(deepseek_client=fake, store=InMemoryResponseStore())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/responses",
            json={
                "model": "deepseek-v4-pro",
                "input": "Generate an image.",
                "tools": [{"type": "image_generation"}],
            },
        )

    assert response.status_code == 200
    output_text = response.json()["output_text"]
    assert "image summarized" in output_text
    assert "Generated image result:" in output_text
    assert "Provider: mock" in output_text
    assert "Image 1 URL: https://example.com/mock-generated-image.png" in output_text

    tool_messages = [m for m in fake.payloads[1]["messages"] if m["role"] == "tool"]
    assert len(tool_messages) == 1
    result = json.loads(tool_messages[0]["content"])
    assert result["ok"] is True
    assert result["provider"] == "mock"
    assert result["prompt"] == "a cute orange cat"
    assert result["images"][0]["url"] == "https://example.com/mock-generated-image.png"


@pytest.mark.asyncio
async def test_proxy_image_generate_missing_glm_key_returns_structured_error(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_PROXY_TOOL_BRIDGE", "1")
    monkeypatch.setenv("DEEPSEEK_PROXY_IMAGE_PROVIDER", "glm")
    monkeypatch.delenv("DEEPSEEK_PROXY_IMAGE_API_KEY", raising=False)
    monkeypatch.delenv("ZAI_API_KEY", raising=False)
    monkeypatch.delenv("ZHIPUAI_API_KEY", raising=False)
    monkeypatch.delenv("ZHIPU_API_KEY", raising=False)
    monkeypatch.delenv("GLM_API_KEY", raising=False)

    fake = FakeDeepSeekClient(
        [
            deepseek_tool_call_response(
                "call_1",
                "proxy_image_generate",
                {"prompt": "a cat"},
            ),
            deepseek_text_response("missing image key handled"),
        ]
    )
    app = create_app(deepseek_client=fake, store=InMemoryResponseStore())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/responses",
            json={
                "model": "deepseek-v4-pro",
                "input": "Generate an image.",
                "tools": [{"type": "image_generation"}],
            },
        )

    assert response.status_code == 200
    assert response.json()["output_text"] == "missing image key handled"

    tool_messages = [m for m in fake.payloads[1]["messages"] if m["role"] == "tool"]
    result = json.loads(tool_messages[0]["content"])
    assert result["ok"] is False
    assert result["provider"] == "glm"
    assert result["error"] == "missing_api_key"


@pytest.mark.asyncio
async def test_proxy_image_generate_result_is_surfaced_in_output_text(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_PROXY_TOOL_BRIDGE", "1")
    monkeypatch.setenv("DEEPSEEK_PROXY_IMAGE_PROVIDER", "mock")

    fake = FakeDeepSeekClient(
        [
            deepseek_tool_call_response(
                "call_1",
                "proxy_image_generate",
                {"prompt": "a cat", "size": "1024x1024", "n": 1},
            ),
            deepseek_text_response("Image generated."),
        ]
    )
    app = create_app(deepseek_client=fake, store=InMemoryResponseStore())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/responses",
            json={
                "model": "deepseek-v4-pro",
                "input": "Generate an image.",
                "tools": [{"type": "image_generation"}],
            },
        )

    assert response.status_code == 200
    data = response.json()

    assert "Image generated." in data["output_text"]
    assert "Generated image result:" in data["output_text"]
    assert "Provider: mock" in data["output_text"]
    assert "Model: mock-image" in data["output_text"]
    assert "Prompt: a cat" in data["output_text"]
    assert "Image 1 URL: https://example.com/mock-generated-image.png" in data["output_text"]

@pytest.mark.asyncio
async def test_proxy_image_generate_mock_download_creates_local_artifact(monkeypatch, tmp_path):
    from pathlib import Path

    monkeypatch.setenv("DEEPSEEK_PROXY_TOOL_BRIDGE", "1")
    monkeypatch.setenv("DEEPSEEK_PROXY_IMAGE_PROVIDER", "mock")
    monkeypatch.setenv("DEEPSEEK_PROXY_IMAGE_DOWNLOAD", "1")
    monkeypatch.setenv("DEEPSEEK_PROXY_IMAGE_OUTPUT_DIR", str(tmp_path / "images"))

    fake = FakeDeepSeekClient(
        [
            deepseek_tool_call_response(
                "call_1",
                "proxy_image_generate",
                {"prompt": "a local artifact test", "size": "1024x1024", "n": 1},
            ),
            deepseek_text_response("Image generated with local artifact."),
        ]
    )
    app = create_app(deepseek_client=fake, store=InMemoryResponseStore())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/responses",
            json={
                "model": "deepseek-v4-pro",
                "input": "Generate an image.",
                "tools": [{"type": "image_generation"}],
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert "Generated image result:" in data["output_text"]
    assert "Image 1 URL: https://example.com/mock-generated-image.png" in data["output_text"]
    assert "Image 1 local path:" in data["output_text"]
    assert "Image 1 file URI: file://" in data["output_text"]

    tool_messages = [m for m in fake.payloads[1]["messages"] if m["role"] == "tool"]
    assert len(tool_messages) == 1

    result = json.loads(tool_messages[0]["content"])
    image = result["images"][0]

    assert image["url"] == "https://example.com/mock-generated-image.png"
    assert image["downloaded"] is True
    assert image["file_path"]
    assert image["local_path"] == image["file_path"]
    assert image["file_uri"].startswith("file://")

    local_path = Path(image["file_path"])
    assert local_path.exists()
    assert local_path.read_bytes().startswith(b"\x89PNG")

