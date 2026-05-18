import json

from deepseek_responses_proxy.app import (
    DEFAULT_MODEL_PRICING_USD_PER_1M,
    _estimate_cost_usd,
    _load_model_pricing_usd_per_1m,
)


def test_load_pricing_from_config_file(monkeypatch, tmp_path):
    pricing_path = tmp_path / "pricing.json"
    pricing_path.write_text(
        json.dumps(
            {
                "deepseek-v4-flash": {
                    "input_cache_hit": 1.0,
                    "input_cache_miss": 2.0,
                    "output": 3.0,
                }
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("DEEPSEEK_PROXY_PRICING_PATH", str(pricing_path))

    pricing = _load_model_pricing_usd_per_1m()

    assert pricing == {
        "deepseek-v4-flash": {
            "input_cache_hit": 1.0,
            "input_cache_miss": 2.0,
            "output": 3.0,
        }
    }


def test_missing_pricing_config_falls_back_to_default(monkeypatch, tmp_path):
    monkeypatch.setenv("DEEPSEEK_PROXY_PRICING_PATH", str(tmp_path / "missing.json"))

    pricing = _load_model_pricing_usd_per_1m()

    assert pricing == DEFAULT_MODEL_PRICING_USD_PER_1M


def test_invalid_pricing_config_falls_back_to_default(monkeypatch, tmp_path):
    pricing_path = tmp_path / "pricing.json"
    pricing_path.write_text("not valid json", encoding="utf-8")

    monkeypatch.setenv("DEEPSEEK_PROXY_PRICING_PATH", str(pricing_path))

    pricing = _load_model_pricing_usd_per_1m()

    assert pricing == DEFAULT_MODEL_PRICING_USD_PER_1M


def test_estimate_cost_uses_external_pricing_config(monkeypatch, tmp_path):
    pricing_path = tmp_path / "pricing.json"
    pricing_path.write_text(
        json.dumps(
            {
                "deepseek-v4-flash": {
                    "input_cache_hit": 1.0,
                    "input_cache_miss": 10.0,
                    "output": 100.0,
                }
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("DEEPSEEK_PROXY_PRICING_PATH", str(pricing_path))

    cost = _estimate_cost_usd(
        "deepseek-v4-flash",
        {
            "prompt_tokens": 100,
            "cached_tokens": 40,
            "completion_tokens": 2,
            "total_tokens": 102,
            "reasoning_tokens": 0,
        },
    )

    expected = (40 * 1.0 + 60 * 10.0 + 2 * 100.0) / 1_000_000
    assert abs(cost - expected) < 1e-12

def test_weclaw_pricing_contract_exposes_round3_refresh_fields(monkeypatch, tmp_path):
    from deepseek_responses_proxy.app import _weclaw_pricing_contract

    pricing_path = tmp_path / "pricing.json"
    pricing_path.write_text(
        json.dumps(
            {
                "deepseek-v4-flash": {
                    "input_cache_hit": 1.0,
                    "input_cache_miss": 2.0,
                    "output": 3.0,
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("DEEPSEEK_PROXY_PRICING_PATH", str(pricing_path))

    pricing = _weclaw_pricing_contract("deepseek-v4-flash")

    assert pricing["available"] is True
    assert pricing["source_url"] is None
    assert pricing["source_kind"] == "external_config"
    assert "ttl_seconds" in pricing
    assert pricing["refresh"]["available"] is True
    assert pricing["refresh"]["action"]
    assert pricing["refresh"]["write_cache_requires_flag"] == "--write-cache"
    assert pricing["official_reference_url"] == "https://api-docs.deepseek.com/zh-cn/quick_start/pricing/"
    assert pricing["pricing_source_state"]["must_display_source_label"] is True


OFFICIAL_PRICING_HTML_SAMPLE = """
<table>
<tr><td colspan="2">MODEL</td><td>deepseek-v4-flash<sup>(1)</sup></td><td>deepseek-v4-pro</td></tr>
<tr><td colspan="2">BASE URL (OpenAI Format)</td><td colspan="2">https://api.deepseek.com</td></tr>
<tr><td>1M INPUT TOKENS (CACHE HIT)</td><td>$0.0028</td><td>$0.003625 (75% off)<del>$0.0145</del></td></tr>
<tr><td>1M INPUT TOKENS (CACHE MISS)</td><td>$0.14</td><td>$0.435 (75% off)<del>$1.74</del></td></tr>
<tr><td>1M OUTPUT TOKENS</td><td>$0.28</td><td>$0.87 (75% off)<del>$3.48</del></td></tr>
</table>
"""


def test_parse_deepseek_official_pricing_html_v4_models():
    from deepseek_responses_proxy.app import _parse_deepseek_official_pricing_html

    parsed = _parse_deepseek_official_pricing_html(OFFICIAL_PRICING_HTML_SAMPLE)

    assert parsed == {
        "deepseek-v4-flash": {
            "input_cache_hit": 0.0028,
            "input_cache_miss": 0.14,
            "output": 0.28,
        },
        "deepseek-v4-pro": {
            "input_cache_hit": 0.003625,
            "input_cache_miss": 0.435,
            "output": 0.87,
        },
    }


def test_refresh_deepseek_pricing_validates_without_writing(monkeypatch, tmp_path):
    import importlib

    app_module = importlib.import_module("deepseek_responses_proxy.app")
    cache_path = tmp_path / "pricing-cache.json"
    monkeypatch.setattr(app_module, "_fetch_text_url", lambda url, timeout=20.0: OFFICIAL_PRICING_HTML_SAMPLE)

    result = app_module._refresh_deepseek_pricing_from_official_docs(
        model="deepseek-v4-flash",
        write_cache=False,
        cache_path=cache_path,
    )

    assert result["status"] == "ok"
    assert result["available"] is True
    assert result["writes_cache"] is False
    assert result["source_kind"] == "official_docs_html"
    assert result["pricing"]["prices"]["input_cache_miss"] == 0.14
    assert not cache_path.exists()


def test_refresh_deepseek_pricing_writes_cache_atomically(monkeypatch, tmp_path):
    import importlib

    app_module = importlib.import_module("deepseek_responses_proxy.app")
    cache_path = tmp_path / "pricing-cache.json"
    monkeypatch.setattr(app_module, "_fetch_text_url", lambda url, timeout=20.0: OFFICIAL_PRICING_HTML_SAMPLE)

    result = app_module._refresh_deepseek_pricing_from_official_docs(
        model="deepseek-v4-pro",
        write_cache=True,
        cache_path=cache_path,
    )

    assert result["status"] == "ok"
    assert result["writes_cache"] is True
    saved = json.loads(cache_path.read_text(encoding="utf-8"))
    assert saved["__metadata__"]["source_kind"] == "official_docs_html"
    assert saved["__metadata__"]["source_url"] == "https://api-docs.deepseek.com/zh-cn/quick_start/pricing/"
    assert saved["deepseek-v4-pro"]["output"] == 0.87

    monkeypatch.setenv("DEEPSEEK_PROXY_PRICING_PATH", str(cache_path))
    pricing = app_module._weclaw_pricing_contract("deepseek-v4-pro")
    assert pricing["source_url"] == "https://api-docs.deepseek.com/zh-cn/quick_start/pricing/"
    assert pricing["prices"]["output"] == 0.87
    assert pricing["refresh"]["available"] is True


def test_refresh_deepseek_pricing_parse_failure_preserves_existing_cache(monkeypatch, tmp_path):
    import importlib

    app_module = importlib.import_module("deepseek_responses_proxy.app")
    cache_path = tmp_path / "pricing-cache.json"
    original = {"deepseek-v4-flash": {"input_cache_hit": 1.0, "input_cache_miss": 2.0, "output": 3.0}}
    cache_path.write_text(json.dumps(original), encoding="utf-8")
    monkeypatch.setattr(app_module, "_fetch_text_url", lambda url, timeout=20.0: "<html>no v4 pricing table</html>")

    result = app_module._refresh_deepseek_pricing_from_official_docs(
        model="deepseek-v4-flash",
        write_cache=True,
        cache_path=cache_path,
    )

    assert result["status"] == "error"
    assert result["reason"] == "official_pricing_parse_failed"
    assert result["writes_cache"] is False
    assert json.loads(cache_path.read_text(encoding="utf-8")) == original



def test_weclaw_pricing_contract_converts_usd_to_cny_for_display(monkeypatch, tmp_path):
    from deepseek_responses_proxy.app import _weclaw_pricing_contract

    pricing_path = tmp_path / "pricing.json"
    pricing_path.write_text(
        json.dumps(
            {
                "__metadata__": {
                    "source_kind": "bundled_official_docs_snapshot",
                    "source_url": "https://api-docs.deepseek.com/quick_start/pricing",
                    "snapshot_created_at": "2026-05-17T00:00:00Z",
                    "currency": "USD",
                },
                "deepseek-v4-flash": {
                    "input_cache_hit": 0.0028,
                    "input_cache_miss": 0.14,
                    "output": 0.28,
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("DEEPSEEK_PROXY_PRICING_PATH", str(pricing_path))
    monkeypatch.setenv("DEEPSEEK_PROXY_USD_CNY_FX_RATE", "7.25")
    monkeypatch.setenv("DEEPSEEK_PROXY_USD_CNY_FX_UPDATED_AT", "2026-05-18T00:00:00Z")

    pricing = _weclaw_pricing_contract("deepseek-v4-flash", display_currency="CNY")

    assert pricing["model"] == "deepseek-v4-flash"
    assert pricing["source_currency"] == "USD"
    assert pricing["display_currency"] == "CNY"
    assert pricing["converted"] is True
    assert pricing["fx_rate"] == 7.25
    assert pricing["cache_hit_input"]["amount"] == 0.0028 * 7.25
    assert pricing["cache_hit_input"]["source_amount"] == 0.0028
    assert pricing["cache_miss_input"]["currency"] == "CNY"
    assert pricing["output"]["currency"] == "CNY"
    assert pricing["reasoning_output"]["available"] is False


def test_parse_deepseek_official_pricing_html_handles_pricing_row_header():
    from deepseek_responses_proxy.app import _parse_deepseek_official_pricing_html

    html = """
    <table>
    <tr><td>MODEL</td><td>deepseek-v4-flash</td><td>deepseek-v4-pro</td></tr>
    <tr><td>PRICING</td><td>1M INPUT TOKENS (CACHE HIT)</td><td>$0.0028</td><td>$0.003625 (75% off)</td></tr>
    <tr><td></td><td>1M INPUT TOKENS (CACHE MISS)</td><td>$0.14</td><td>$0.435</td></tr>
    <tr><td></td><td>1M OUTPUT TOKENS</td><td>$0.28</td><td>$0.87</td></tr>
    </table>
    """
    parsed = _parse_deepseek_official_pricing_html(html)

    assert parsed["deepseek-v4-flash"]["input_cache_hit"] == 0.0028
    assert parsed["deepseek-v4-pro"]["input_cache_hit"] == 0.003625



def test_weclaw_pricing_contract_uses_cny_primary_snapshot_without_fx(monkeypatch, tmp_path):
    from deepseek_responses_proxy.app import _weclaw_pricing_contract

    pricing_path = tmp_path / "pricing.json"
    pricing_path.write_text(
        json.dumps(
            {
                "__metadata__": {
                    "source_kind": "bundled_official_docs_snapshot",
                    "source_url": "https://api-docs.deepseek.com/zh-cn/quick_start/pricing/",
                    "snapshot_created_at": "2026-05-18T00:00:00Z",
                    "currency": "CNY",
                    "unit": "per_million_tokens",
                },
                "deepseek-v4-flash": {
                    "input_cache_hit": 0.02,
                    "input_cache_miss": 1.0,
                    "output": 2.0,
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("DEEPSEEK_PROXY_PRICING_PATH", str(pricing_path))

    pricing = _weclaw_pricing_contract("deepseek-v4-flash", display_currency="CNY")

    assert pricing["model"] == "deepseek-v4-flash"
    assert pricing["source_currency"] == "CNY"
    assert pricing["display_currency"] == "CNY"
    assert pricing["converted"] is False
    assert pricing["fx_rate"] is None
    assert pricing["cache_hit_input"]["amount"] == 0.02
    assert pricing["cache_hit_input"]["source_amount"] == 0.02
    assert pricing["cache_miss_input"]["amount"] == 1.0
    assert pricing["output"]["amount"] == 2.0
    assert pricing["source_url"] == "https://api-docs.deepseek.com/zh-cn/quick_start/pricing/"


def test_parse_deepseek_official_pricing_html_zh_cny_models():
    from deepseek_responses_proxy.app import _parse_deepseek_official_pricing_html

    html = """
    <table>
    <tr><td>模型</td><td>deepseek-v4-flash</td><td>deepseek-v4-pro</td></tr>
    <tr><td>价格</td><td>百万tokens输入（缓存命中）</td><td>0.02元</td><td>0.025元（2.5折）<del>0.1元</del></td></tr>
    <tr><td></td><td>百万tokens输入（缓存未命中）</td><td>1元</td><td>3元</td></tr>
    <tr><td></td><td>百万tokens输出</td><td>2元</td><td>6元</td></tr>
    </table>
    """
    parsed = _parse_deepseek_official_pricing_html(html)

    assert parsed["deepseek-v4-flash"]["input_cache_hit"] == 0.02
    assert parsed["deepseek-v4-flash"]["input_cache_miss"] == 1.0
    assert parsed["deepseek-v4-flash"]["output"] == 2.0
    assert parsed["deepseek-v4-pro"]["input_cache_hit"] == 0.025
    assert parsed["deepseek-v4-pro"]["input_cache_miss"] == 3.0
    assert parsed["deepseek-v4-pro"]["output"] == 6.0
