import json

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from deepseek_responses_proxy.app import DeepSeekClient, InMemoryResponseStore, create_app


class UpstreamErrorClient(DeepSeekClient):
    def __init__(self, exc):
        self.exc = exc

    async def chat_completions(self, payload):
        raise self.exc


class InvalidJSONClient(DeepSeekClient):
    async def chat_completions(self, payload):
        return {"choices": [{"message": {"role": "assistant", "content": "ok"}}]}


class MalformedDeepSeekClient(DeepSeekClient):
    async def chat_completions(self, payload):
        return {"unexpected": "shape"}


def make_http_status_error(status_code, body):
    request = httpx.Request("POST", "https://api.deepseek.com/chat/completions")
    response = httpx.Response(
        status_code,
        request=request,
        content=json.dumps(body).encode("utf-8"),
        headers={"content-type": "application/json"},
    )
    return httpx.HTTPStatusError(
        f"Client error '{status_code}'",
        request=request,
        response=response,
    )


@pytest.mark.asyncio
async def test_upstream_400_is_returned_as_clean_error_response():
    exc = make_http_status_error(
        400,
        {
            "error": {
                "message": "invalid request body",
                "type": "invalid_request_error",
                "code": "invalid_request_error",
            }
        },
    )
    app = create_app(deepseek_client=UpstreamErrorClient(exc), store=InMemoryResponseStore())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/responses",
            json={
                "model": "deepseek-v4-flash",
                "input": "Reply exactly: ok",
            },
        )

    assert response.status_code in {400, 502}
    detail = response.json()["detail"]
    assert detail["upstream"] == "deepseek"
    assert detail["status_code"] == 400
    assert "invalid request body" in detail["body"]


@pytest.mark.asyncio
async def test_upstream_429_is_returned_as_clean_error_response():
    exc = make_http_status_error(
        429,
        {
            "error": {
                "message": "rate limited",
                "type": "rate_limit_error",
                "code": "rate_limit_error",
            }
        },
    )
    app = create_app(deepseek_client=UpstreamErrorClient(exc), store=InMemoryResponseStore())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/responses",
            json={
                "model": "deepseek-v4-flash",
                "input": "Reply exactly: ok",
            },
        )

    assert response.status_code in {429, 502}
    detail = response.json()["detail"]
    assert detail["upstream"] == "deepseek"
    assert detail["status_code"] == 429
    assert "rate limited" in detail["body"]


@pytest.mark.asyncio
async def test_upstream_timeout_is_returned_as_504():
    request = httpx.Request("POST", "https://api.deepseek.com/chat/completions")
    exc = httpx.TimeoutException("upstream timeout", request=request)
    app = create_app(deepseek_client=UpstreamErrorClient(exc), store=InMemoryResponseStore())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/responses",
            json={
                "model": "deepseek-v4-flash",
                "input": "Reply exactly: ok",
            },
        )

    assert response.status_code == 504
    detail = response.json()["detail"]
    assert detail["upstream"] == "deepseek"
    assert detail["error_type"] == "timeout"


@pytest.mark.asyncio
async def test_upstream_network_error_is_returned_as_502():
    request = httpx.Request("POST", "https://api.deepseek.com/chat/completions")
    exc = httpx.ConnectError("connection failed", request=request)
    app = create_app(deepseek_client=UpstreamErrorClient(exc), store=InMemoryResponseStore())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/responses",
            json={
                "model": "deepseek-v4-flash",
                "input": "Reply exactly: ok",
            },
        )

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert detail["upstream"] == "deepseek"
    assert detail["error_type"] == "network"


@pytest.mark.asyncio
async def test_malformed_deepseek_response_is_returned_as_502():
    app = create_app(deepseek_client=MalformedDeepSeekClient(), store=InMemoryResponseStore())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/responses",
            json={
                "model": "deepseek-v4-flash",
                "input": "Reply exactly: ok",
            },
        )

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert "invalid DeepSeek response" in str(detail)


@pytest.mark.asyncio
async def test_error_response_does_not_expose_python_traceback():
    exc = make_http_status_error(
        400,
        {
            "error": {
                "message": "invalid request body",
                "type": "invalid_request_error",
            }
        },
    )
    app = create_app(deepseek_client=UpstreamErrorClient(exc), store=InMemoryResponseStore())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/responses",
            json={
                "model": "deepseek-v4-flash",
                "input": "Reply exactly: ok",
            },
        )

    body = response.text
    assert "Traceback" not in body
    assert "File " not in body
