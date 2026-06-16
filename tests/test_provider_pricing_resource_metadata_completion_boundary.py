from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest


app = importlib.import_module("codexchange_proxy.app")


STATIC_METADATA = {
    "source_kind": "official_docs_html",
    "parser": (
        "deepseek_official_docs_html_"
        "bilingual_v3_discount_aware"
    ),
    "currency": "CNY",
    "unit": "per_million_tokens",
    "unit_legacy": "per_1m_tokens",
    "primary_locale": "zh-cn",
    "fallback_locale": "en",
}


def test_deepseek_source_and_profile_complete_writer_metadata() -> None:
    adapter = app.get_provider_adapter("deepseek")
    source = adapter.official_pricing_source()
    profile = app._provider_pricing_resource_profile("deepseek")

    for key, value in STATIC_METADATA.items():
        assert source[key] == value
        assert profile[key] == value

    assert profile["source_url"] == source["source_url"]
    assert profile["source_url_en"] == source["source_url_en"]
    assert profile["cache_scope"] == "legacy_shared"
    assert profile["cache_schema_owner"] == "deepseek"
    assert profile["cache_is_provider_scoped"] is False


def test_deepseek_profile_static_metadata_matches_legacy_writer(
    tmp_path: Path,
) -> None:
    profile = app._provider_pricing_resource_profile("deepseek")
    target = tmp_path / "pricing.json"

    app._write_pricing_cache_atomic(
        {
            "probe-model": {
                "input_cache_hit": 1.0,
                "input_cache_miss": 2.0,
                "output": 3.0,
            }
        },
        path=target,
        source_url=profile["source_url"],
        fetched_at="2026-06-16T00:00:00Z",
        ttl_seconds=86400,
    )

    payload = json.loads(
        target.read_text(
            encoding="utf-8",
        )
    )
    metadata = payload["__metadata__"]

    assert metadata["source_url"] == profile["source_url"]

    for key, value in STATIC_METADATA.items():
        assert metadata[key] == value
        assert profile[key] == value


@pytest.mark.parametrize(
    "provider_id",
    [
        "qwen_beijing",
        "qwen_singapore",
        "qwen_us",
        "kimi",
        "zhipu",
        "zhipu_coding",
        "zai",
        "zai_coding",
        "custom",
    ],
)
def test_unsupported_provider_profile_has_no_pricing_schema_metadata(
    provider_id: str,
) -> None:
    profile = app._provider_pricing_resource_profile(provider_id)

    assert profile["supported"] is False

    for key in (
        "source_url",
        "source_url_en",
        "source_kind",
        "parser",
        "currency",
        "unit",
        "unit_legacy",
        "primary_locale",
        "fallback_locale",
        "cache_scope",
        "cache_schema_owner",
    ):
        assert profile[key] is None

    assert "deepseek" not in str(profile).lower()
