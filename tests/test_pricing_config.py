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
