from __future__ import annotations

import importlib

import pytest


app = importlib.import_module("codexchange_proxy.app")


def test_provider_pricing_resource_profile_deepseek_contract() -> None:
    profile = app._provider_pricing_resource_profile("deepseek")

    assert profile == {
        "provider": "deepseek",
        "adapter_provider_id": "deepseek",
        "family": "deepseek",
        "supported": True,
        "capability": "pricing",
        "official_refresh_supported": True,
        "source_url": app.DEEPSEEK_OFFICIAL_PRICING_URL,
        "source_url_en": app.DEEPSEEK_OFFICIAL_PRICING_URL_EN,
        "source_kind": "official_docs_html",
        "parser": (
            "deepseek_official_docs_html_"
            "bilingual_v3_discount_aware"
        ),
        "currency": "CNY",
        "unit": "per_million_tokens",
        "cache_scope": "legacy_shared",
        "cache_schema_owner": "deepseek",
        "cache_is_provider_scoped": False,
        "reason": None,
        "action": None,
    }


@pytest.mark.parametrize(
    "provider_id,adapter_provider_id,family",
    [
        ("qwen_beijing", "qwen_beijing", "qwen"),
        ("qwen_singapore", "qwen_singapore", "qwen"),
        ("qwen_us", "qwen_us", "qwen"),
        ("kimi", "kimi", "kimi"),
        ("zhipu", "zhipu", "zhipu"),
        ("zhipu_coding", "zhipu_coding", "zhipu"),
        ("zai", "zai", "zai"),
        ("zai_coding", "zai_coding", "zai"),
        ("custom", "openai_compatible", "openai_compatible"),
    ],
)
def test_non_pricing_provider_profile_is_neutral(
    provider_id: str,
    adapter_provider_id: str,
    family: str,
) -> None:
    profile = app._provider_pricing_resource_profile(provider_id)

    assert profile["provider"] == provider_id
    assert profile["adapter_provider_id"] == adapter_provider_id
    assert profile["family"] == family
    assert profile["supported"] is False
    assert profile["capability"] == "pricing"
    assert profile["official_refresh_supported"] is False

    for key in (
        "source_url",
        "source_url_en",
        "source_kind",
        "parser",
        "currency",
        "unit",
        "cache_scope",
        "cache_schema_owner",
    ):
        assert profile[key] is None

    assert profile["cache_is_provider_scoped"] is False
    assert profile["reason"] == "provider_pricing_not_supported"
    assert "DeepSeek" not in str(profile)
    assert "deepseek" not in str(profile)


def test_deepseek_pricing_resource_profile_is_compatibility_wrapper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    sentinel = {"sentinel": True}

    def fake_profile(provider_id: str) -> dict[str, object]:
        calls.append(provider_id)
        return sentinel

    monkeypatch.setattr(
        app,
        "_provider_pricing_resource_profile",
        fake_profile,
    )

    assert app._deepseek_pricing_resource_profile() is sentinel
    assert calls == ["deepseek"]


def test_profile_wrapper_does_not_change_pricing_runtime_contracts() -> None:
    assert (
        app._pricing_cache_path.__name__
        == "_pricing_cache_path"
    )
    assert (
        app._pricing_daily_refresh_contract.__name__
        == "_pricing_daily_refresh_contract"
    )
    assert (
        app._write_pricing_cache_atomic.__name__
        == "_write_pricing_cache_atomic"
    )
    assert (
        app._weclaw_pricing_contract.__name__
        == "_weclaw_pricing_contract"
    )
