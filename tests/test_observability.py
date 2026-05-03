import pytest
from httpx import ASGITransport, AsyncClient

from deepseek_responses_proxy.app import InMemoryResponseStore, create_app


@pytest.mark.asyncio
async def test_healthz_returns_basic_status(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_THINKING", raising=False)

    app = create_app(store=InMemoryResponseStore())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/healthz")

    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "ok"
    assert data["version"]
    assert data["thinking"] == {"type": "disabled"}


@pytest.mark.asyncio
async def test_proxy_status_returns_runtime_metadata(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_THINKING", "enabled")

    app = create_app(store=InMemoryResponseStore())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/v1/proxy/status")

    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "ok"
    assert data["version"]
    assert data["model_default"] == "deepseek-v4-flash"
    assert data["thinking"] == {"type": "enabled"}
    assert data["thinking_enabled"] is True
    assert data["store"]["type"] == "InMemoryResponseStore"
    assert isinstance(data["started_at"], int)
    assert isinstance(data["uptime_seconds"], int)
    assert data["repair_count"] == 0
