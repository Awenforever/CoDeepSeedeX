from __future__ import annotations

from fastapi.testclient import TestClient

from codexchange_proxy.app import create_app


def test_models_endpoint_owned_by_uses_configured_provider(monkeypatch):
    monkeypatch.setenv("COX_MODEL_PROVIDER", "custom")
    client = TestClient(create_app())

    response = client.get("/v1/models")

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]
    assert payload["data"][0]["owned_by"] == "custom"


def test_models_endpoint_owner_is_not_hardcoded_deepseek_when_provider_changes(monkeypatch):
    monkeypatch.setenv("COX_MODEL_PROVIDER", "qwen")
    client = TestClient(create_app())

    payload = client.get("/v1/models").json()

    assert payload["data"][0]["owned_by"] == "qwen"
    assert payload["data"][0]["owned_by"] != "deepseek"
