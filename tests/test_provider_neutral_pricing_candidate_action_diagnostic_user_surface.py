from __future__ import annotations

import importlib
from pathlib import Path

proxy_app = importlib.import_module("codexchange_proxy.app")


def test_pricing_single_write_candidate_invalid_action_is_provider_neutral(monkeypatch, tmp_path):
    def fake_activation_contract(provider_id, *, activate, mode, provider_path):
        return {
            "activation_ready": True,
            "activation_contract_valid": True,
            "provider": provider_id,
            "adapter_provider_id": "deepseek",
            "requested_mode": "provider_owned",
            "candidate_writer": "unexpected_writer",
            "candidate_path": str(tmp_path / "pricing.json"),
        }

    monkeypatch.setattr(
        proxy_app,
        "_provider_pricing_refresh_writer_activation_contract",
        fake_activation_contract,
    )

    result = proxy_app._provider_pricing_refresh_writer_single_write_execution(
        "deepseek",
        activate=True,
        mode="provider_owned",
        provider_path=tmp_path / "pricing.json",
    )

    assert result["status"] == "error"
    assert result["reason"] == "provider_pricing_refresh_single_write_candidate_invalid"
    assert result["action"] == (
        "re-run the explicit activation contract with an explicit "
        "provider-owned pricing path"
    )
    assert "DeepSeek" not in result["action"]


def test_pricing_single_write_candidate_invalid_source_does_not_expose_deepseek_path():
    source = Path(proxy_app.__file__).read_text(encoding="utf-8")

    assert "provider-owned pricing path" in source
    assert "DeepSeek path" not in source
