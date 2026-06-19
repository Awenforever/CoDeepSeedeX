from __future__ import annotations

import importlib


proxy_app = importlib.import_module("codexchange_proxy.app")


def test_missing_profile_tokenizer_action_uses_explicit_provider(monkeypatch, tmp_path):
    monkeypatch.setenv("COX_TOKENIZER_RESOURCE_DIR", str(tmp_path))
    monkeypatch.delenv("COX_PROFILE_TOKENIZER_JSON", raising=False)
    monkeypatch.delenv("COX_CUSTOM_TOKENIZER_JSON", raising=False)

    contract = proxy_app._profile_tokenizer_contract("deepseek-v4-pro", "custom")

    assert contract["provider"] == "custom"
    assert contract["reason"] == "profile_tokenizer_json_not_found"
    assert contract["action"] == (
        "run cox tokenizer sync custom --json or set COX_CUSTOM_TOKENIZER_JSON"
    )
    assert "sync deepseek" not in contract["action"].lower()


def test_empty_profile_tokenizer_report_reuses_provider_specific_action(monkeypatch, tmp_path):
    monkeypatch.setenv("COX_TOKENIZER_RESOURCE_DIR", str(tmp_path))
    monkeypatch.delenv("COX_PROFILE_TOKENIZER_JSON", raising=False)
    monkeypatch.delenv("COX_CUSTOM_TOKENIZER_JSON", raising=False)

    report = proxy_app._profile_tokenizer_unavailable_report(
        profile="custom",
        model="deepseek-v4-pro",
        provider="custom",
    )

    assert report["summary"]["action"] == (
        "run cox tokenizer sync custom --json or set COX_CUSTOM_TOKENIZER_JSON"
    )
    assert "sync deepseek" not in report["summary"]["action"].lower()


def test_missing_tokenizer_contract_status_action_uses_provider_placeholder():
    split = proxy_app._weclaw_prompt_subcategory_split_contract()

    assert split["action"] == (
        "run cox tokenizer status <provider> --json and verify the running route exposes tokenizer_contract"
    )
    assert "status deepseek" not in split["action"].lower()
