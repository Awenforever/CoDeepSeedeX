from __future__ import annotations

import asyncio
import json

import importlib

from codexchange_proxy import cli

app_module = importlib.import_module("codexchange_proxy.app")


class _FakeResponse:
    def __init__(self, status: int, payload: dict[str, object]):
        self.status = status
        self._raw = json.dumps(payload).encode("utf-8")
        self.headers = {"Content-Type": "application/json"}

    def read(self) -> bytes:
        return self._raw

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


def test_validation_accepts_http_200_provider_error_body(monkeypatch):
    def fake_urlopen(req, timeout):
        return _FakeResponse(200, {"error": {"code": "invalid_request", "message": "missing prompt"}})

    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)

    result = cli._validation_http_json(
        provider="zai",
        kind="image_generation",
        method="POST",
        url="https://api.z.ai/api/paas/v4/images/generations",
        endpoint="https://api.z.ai/api/paas/v4/images/generations",
        headers={"Authorization": "Bearer fake"},
        payload={},
        timeout=1.0,
        ok_statuses=(400, 422),
        allow_provider_error_body=True,
        require_provider_error_body=True,
        validation_method="non_generation_auth_probe",
        may_consume_quota=False,
        validation_strength="auth_probe",
        functional_probe=False,
    )

    assert result["ok"] is True
    assert result["status"] == "ok"
    assert result["http_status"] == 200
    assert result["provider_error_accepted"] is True
    assert result["functional_validation"] == "not_performed"


def test_qwen_image_unsupported_region_returns_static_status():
    result = cli._validate_image_api_key("qwen_image_us", "fake-key", timeout=1.0)

    assert result["ok"] is False
    assert result["status"] == "region_model_unavailable"
    assert result["error"] == "qwen_image_region_model_unavailable"
    assert result["region"] == "US Virginia"
    assert result["validation_strength"] == "static_region_capability"
    assert result["functional_validation"] == "not_performed"


def test_qwen_image_region_aliases_and_endpoints():
    assert cli._canonical_probe_image_provider("qwen_image") == "qwen_image"
    assert cli._canonical_probe_image_provider("qwen-image-singapore") == "qwen_image_singapore"
    assert cli._canonical_probe_image_provider("qwen-image-us") == "qwen_image_us"

    endpoint, body, headers = cli._provider_probe_image_payload("qwen_image_singapore", "tiny smoke test")
    assert endpoint == "https://dashscope-intl.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
    assert headers["Content-Type"] == "application/json"


def test_runtime_qwen_image_unavailable_region_short_circuits(monkeypatch):
    monkeypatch.setenv("COX_IMAGE_PROVIDER", "qwen_image_us")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "fake-key")

    result = asyncio.run(app_module._dashscope_qwen_image_generate({"prompt": "tiny smoke test"}))

    assert result["ok"] is False
    assert result["error"] == "qwen_image_region_model_unavailable"
    assert result["region"] == "US Virginia"


def test_readme_qwen_image_regions_documented():
    readme = open("README.md", encoding="utf-8").read()
    readme_zh = open("README.zh-CN.md", encoding="utf-8").read()

    assert "qwen_image_beijing" in readme
    assert "qwen_image_singapore" in readme
    assert "US Virginia" in readme
    assert "Germany Frankfurt" in readme
    assert "qwen_image_beijing" in readme_zh
    assert "qwen_image_singapore" in readme_zh
    assert "美国弗吉尼亚" in readme_zh
    assert "德国法兰克福" in readme_zh
