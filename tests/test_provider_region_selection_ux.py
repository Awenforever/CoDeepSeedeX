from __future__ import annotations

import json

from codexchange_proxy import cli


def test_qwen_region_providers_expose_region_metadata() -> None:
    beijing = cli._model_api_provider_config("qwen-beijing")
    singapore = cli._model_api_provider_config("qwen-singapore")
    us = cli._model_api_provider_config("qwen-us")

    assert beijing["region"] == "Beijing"
    assert beijing["region_code"] == "cn-beijing"
    assert beijing["endpoint_scope"] == "domestic DashScope"
    assert singapore["region"] == "Singapore"
    assert singapore["region_code"] == "ap-southeast-1"
    assert us["region"] == "US Virginia"
    assert us["region_code"] == "us-east-1"


def test_qwen_ambiguous_alias_warns_to_choose_explicit_region() -> None:
    config = cli._model_api_provider_config("qwen")

    assert config["provider"] == "qwen_singapore"
    assert "selection_warning" in config
    assert "qwen-beijing" in config["selection_warning"]
    assert "qwen-singapore" in config["selection_warning"]
    assert "qwen-us" in config["selection_warning"]


def test_qwen_validation_401_hint_mentions_selected_provider_region(monkeypatch) -> None:
    class FakeResponse:
        status = 401

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b'{"error":"Unauthorized"}'

    def fake_urlopen(request, timeout=10.0):
        return FakeResponse()

    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)

    result = cli._validate_model_api_key(
        "qwen-singapore",
        "sk-test",
        base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        timeout=1.0,
    )

    assert result["status"] == "error"
    assert result["http_status"] == 401
    assert any("selected provider region" in hint for hint in result["diagnostic_hints"])


def test_custom_base_url_rejects_chat_completions_endpoint() -> None:
    problem = cli._custom_model_api_base_url_problem("https://api.example.com/v1/chat/completions")

    assert problem is not None
    assert problem["error"] == "custom_model_base_url_must_be_api_root"
    assert problem["suggested_base_url"] == "https://api.example.com/v1"


def test_set_model_rejects_custom_chat_completions_base_url(tmp_path, capsys) -> None:
    rc = cli.main(
        [
            "config",
            "set-model",
            "custom-model",
            "--provider",
            "custom",
            "--base-url",
            "https://api.example.com/v1/chat/completions",
            "--value",
            "sk-test",
            "--env-file",
            str(tmp_path / "env"),
            "--skip-validation",
        ]
    )

    assert rc == 1
    output = json.loads(capsys.readouterr().out)
    assert output["error"] == "custom_model_base_url_must_be_api_root"
    assert output["suggested_base_url"] == "https://api.example.com/v1"
