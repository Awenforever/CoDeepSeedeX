
from __future__ import annotations

import json
import importlib
from pathlib import Path

proxy_app = importlib.import_module("deepseek_responses_proxy.app")


def test_deepseek_zh_pricing_parser_exposes_pro_discount_metadata() -> None:
    html = """
    <table>
    <tr><td>模型</td><td>deepseek-v4-flash</td><td>deepseek-v4-pro</td></tr>
    <tr><td>百万tokens输入（缓存命中）</td><td>0.02元</td><td>0.025元（2.5折）<del>0.1元</del></td></tr>
    <tr><td>百万tokens输入（缓存未命中）</td><td>1元</td><td>3元（2.5折）<del>12元</del></td></tr>
    <tr><td>百万tokens输出</td><td>2元</td><td>6元（2.5折）<del>24元</del></td></tr>
    </table>
    <p>当前 deepseek-v4-pro 模型 2.5 折，优惠期延长至北京时间 2026/05/31 23:59。</p>
    """
    parsed = proxy_app._parse_deepseek_official_pricing_html(html, include_metadata=True)

    assert parsed["deepseek-v4-flash"] == {
        "input_cache_hit": 0.02,
        "input_cache_miss": 1.0,
        "output": 2.0,
    }
    assert parsed["deepseek-v4-pro"] == {
        "input_cache_hit": 0.025,
        "input_cache_miss": 3.0,
        "output": 6.0,
    }

    metadata = parsed["__model_metadata__"]["deepseek-v4-pro"]
    assert metadata["original_prices"] == {
        "input_cache_hit": 0.1,
        "input_cache_miss": 12.0,
        "output": 24.0,
    }
    assert metadata["discount"]["available"] is True
    assert metadata["discount"]["label"] == "2.5折"
    assert metadata["discount"]["discount_rate"] == 0.25
    assert metadata["discount"]["valid_until"] == "2026-05-31T23:59:00+08:00"
    assert metadata["discount"]["validity_confidence"] == "official_note"


def test_bundled_pricing_snapshot_uses_effective_cny_prices_and_discount_metadata() -> None:
    pricing_path = Path("config/pricing.json")
    pricing = json.loads(pricing_path.read_text(encoding="utf-8"))

    assert pricing["__metadata__"]["currency"] == "CNY"
    assert pricing["__metadata__"]["source_kind"] == "bundled_official_docs_snapshot"
    assert pricing["__metadata__"]["primary_locale"] == "zh-cn"

    assert pricing["deepseek-v4-pro"] == {
        "input_cache_hit": 0.025,
        "input_cache_miss": 3.0,
        "output": 6.0,
    }
    assert pricing["__model_metadata__"]["deepseek-v4-pro"]["original_prices"]["output"] == 24.0
    assert pricing["__model_metadata__"]["deepseek-v4-pro"]["discount"]["valid_until"] == "2026-05-31T23:59:00+08:00"


def test_weclaw_pricing_contract_exposes_bundled_current_and_original_prices(monkeypatch) -> None:
    pricing_path = Path("config/pricing.json").resolve()
    monkeypatch.setenv("DEEPSEEK_PROXY_MODEL", "deepseek-v4-pro")
    monkeypatch.setenv("DEEPSEEK_PROXY_PRICING_PATH", str(pricing_path))
    contract = proxy_app._weclaw_pricing_contract("deepseek-v4-pro", display_currency="CNY")

    assert contract["source_currency"] == "CNY"
    assert contract["prices_display"]["input_cache_hit"] == 0.025
    assert contract["prices_display"]["input_cache_miss"] == 3.0
    assert contract["prices_display"]["output"] == 6.0
    assert contract["effective_prices"]["output"] == 6.0
    assert contract["original_prices"]["output"] == 24.0
    assert contract["discount"]["available"] is True
    assert contract["discount_valid_until"] == "2026-05-31T23:59:00+08:00"
    assert contract["prices_source"]["price_semantics"] == "current_effective_price"
