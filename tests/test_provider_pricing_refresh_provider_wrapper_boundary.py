from __future__ import annotations

import inspect
import importlib

proxy_app = importlib.import_module("codexchange_proxy.app")


class _FakeRefreshAdapter:
    provider_id = "fake"
    official_pricing_url = "https://example.test/fake-pricing"

    def __init__(self) -> None:
        self.refresh_calls: list[dict] = []
        self.parse_calls: list[dict] = []

    def parse_official_pricing_html(self, text: str, *, include_metadata: bool, **kwargs):
        self.parse_calls.append(
            {
                "text": text,
                "include_metadata": include_metadata,
                "kwargs": sorted(kwargs),
            }
        )
        return {"fake-model": {"input_cache_hit": 1.0}, "__metadata__": {"provider": self.provider_id}}

    def refresh_pricing_from_official_docs(self, **kwargs):
        parsed = kwargs["parse_official_pricing_html"]("<html/>", include_metadata=True)
        self.refresh_calls.append({**kwargs, "parsed": parsed})
        return {
            "status": "ok",
            "provider": self.provider_id,
            "source_url": kwargs.get("source_url") or self.official_pricing_url,
            "parsed": parsed,
            "writes_cache": bool(kwargs.get("write_cache")),
        }


def test_provider_pricing_refresh_wrapper_dispatches_selected_provider(monkeypatch, tmp_path) -> None:
    adapter = _FakeRefreshAdapter()

    def fake_get_provider_adapter(provider_id: str):
        assert provider_id == "fake"
        return adapter

    monkeypatch.setattr(proxy_app, "get_provider_adapter", fake_get_provider_adapter)

    payload = proxy_app._refresh_provider_pricing_from_official_docs(
        "fake",
        model="fake-model",
        write_cache=True,
        cache_path=tmp_path / "pricing.json",
        timeout=3.5,
    )

    assert payload["status"] == "ok"
    assert payload["provider"] == "fake"
    assert payload["source_url"] == "https://example.test/fake-pricing"
    assert payload["writes_cache"] is True
    assert adapter.refresh_calls
    call = adapter.refresh_calls[0]
    assert call["model"] == "fake-model"
    assert call["source_url"] is None
    assert call["timeout"] == 3.5
    assert call["default_model"] == proxy_app.DEFAULT_MODEL
    assert callable(call["fetch_text_url"])
    assert callable(call["pricing_cache_path"])
    assert callable(call["write_pricing_cache_atomic"])
    assert adapter.parse_calls[0]["include_metadata"] is True


def test_legacy_deepseek_pricing_refresh_wrapper_delegates_to_provider_neutral_seam() -> None:
    source = inspect.getsource(proxy_app._refresh_deepseek_pricing_from_official_docs)
    assert "_refresh_provider_pricing_from_official_docs" in source
    assert 'get_provider_adapter("deepseek").refresh_pricing_from_official_docs' not in source


def test_pricing_daily_refresh_contract_uses_provider_neutral_refresh_seam() -> None:
    source = inspect.getsource(proxy_app._pricing_daily_refresh_contract)
    assert '_refresh_provider_pricing_from_official_docs(' in source
    assert '_refresh_deepseek_pricing_from_official_docs(' not in source


def test_cli_pricing_refresh_uses_provider_neutral_wrapper_and_help() -> None:
    cli_source = inspect.getsource(importlib.import_module("codexchange_proxy.cli"))
    assert "_refresh_provider_pricing_from_official_docs" in cli_source
    assert "_refresh_deepseek_pricing_from_official_docs" not in cli_source
    assert "official DeepSeek pricing HTML" not in cli_source
    assert 'pricing_refresh.add_argument("--provider", default="deepseek"' in cli_source
    assert 'pricing_refresh.add_argument("--source-url", default=None' in cli_source
    assert "https://api-docs.deepseek.com/zh-cn/quick_start/pricing/" not in cli_source
