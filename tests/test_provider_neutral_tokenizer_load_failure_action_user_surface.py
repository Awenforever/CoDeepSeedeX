from __future__ import annotations

import importlib


proxy_app = importlib.import_module("codexchange_proxy.app")


def test_profile_tokenizer_load_failure_action_is_provider_neutral(monkeypatch):
    monkeypatch.setenv("COX_MODEL_PROVIDER", "custom")

    monkeypatch.setattr(
        proxy_app,
        "_profile_tokenizer_contract",
        lambda model, provider=None: {
            "available": True,
            "tokenizer_kind": "custom",
            "source": "custom_provider_tokenizer_json",
            "path": "/tmp/missing-provider-tokenizer.json",
        },
    )

    def boom(contract):
        raise RuntimeError("synthetic tokenizer load failure")

    monkeypatch.setattr(proxy_app, "_load_profile_tokenizer", boom)

    report = proxy_app._profile_tokenizer_report_for_messages(
        [{"role": "user", "content": "hello"}],
        profile="custom",
        model="custom-model",
        provider="custom",
    )

    action = report["tokenizer"]["action"]
    assert "DeepSeek" not in action
    assert "provider tokenizer.json" in action
    assert report["provider"] == "custom"
