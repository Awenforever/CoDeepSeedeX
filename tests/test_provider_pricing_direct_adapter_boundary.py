from __future__ import annotations

import importlib
import inspect
from typing import Any

proxy_app = importlib.import_module("codexchange_proxy.app")


class _FakePricingAdapter:
    official_pricing_url = "https://example.invalid/pricing"
    official_pricing_url_en = "https://example.invalid/pricing/en"

    def discount_window_from_pricing_text(self, text: str, **kwargs: Any) -> dict[str, Any]:
        return {"adapter": "fake", "text": text, "discount": True, "kwargs": sorted(kwargs)}

    def parse_official_pricing_html(self, text: str, *, include_metadata: bool = False, **kwargs: Any) -> dict[str, Any]:
        return {"adapter": "fake", "text": text, "include_metadata": include_metadata, "kwargs": sorted(kwargs)}


def test_provider_discount_window_wrapper_preserves_deepseek_legacy(monkeypatch) -> None:
    adapter = _FakePricingAdapter()

    def fake_get_provider_adapter(provider_id: str):
        assert provider_id == "deepseek"
        return adapter

    monkeypatch.setattr(proxy_app, "get_provider_adapter", fake_get_provider_adapter)

    expected = {
        "adapter": "fake",
        "text": "pricing text",
        "discount": True,
        "kwargs": ["clean_pricing_html_cell"],
    }
    assert proxy_app._provider_discount_window_from_text("deepseek", "pricing text") == expected
    assert proxy_app._deepseek_discount_window_from_text("pricing text") == expected


def test_provider_pricing_html_wrapper_preserves_deepseek_legacy(monkeypatch) -> None:
    adapter = _FakePricingAdapter()

    def fake_get_provider_adapter(provider_id: str):
        assert provider_id == "deepseek"
        return adapter

    monkeypatch.setattr(proxy_app, "get_provider_adapter", fake_get_provider_adapter)

    expected = {
        "adapter": "fake",
        "text": "<html/>",
        "include_metadata": True,
        "kwargs": ["clean_pricing_html_cell", "parse_pricing_cell_details"],
    }
    assert proxy_app._parse_provider_official_pricing_html("deepseek", "<html/>", include_metadata=True) == expected
    assert proxy_app._parse_deepseek_official_pricing_html("<html/>", include_metadata=True) == expected


def test_legacy_pricing_wrappers_delegate_to_provider_neutral_seams() -> None:
    discount_source = inspect.getsource(proxy_app._deepseek_discount_window_from_text)
    pricing_source = inspect.getsource(proxy_app._parse_deepseek_official_pricing_html)

    assert "_provider_discount_window_from_text" in discount_source
    assert "_parse_provider_official_pricing_html" in pricing_source
    assert 'get_provider_adapter("deepseek").discount_window_from_pricing_text' not in discount_source
    assert 'get_provider_adapter("deepseek").parse_official_pricing_html' not in pricing_source
