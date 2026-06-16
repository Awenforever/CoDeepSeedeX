from __future__ import annotations

import importlib
import inspect
import json
from pathlib import Path

import pytest


app = importlib.import_module("codexchange_proxy.app")


EXPECTED_STATIC = {
    "source_kind": "official_docs_html",
    "unit": "per_million_tokens",
    "unit_legacy": "per_1m_tokens",
    "currency": "CNY",
    "parser": (
        "deepseek_official_docs_html_"
        "bilingual_v3_discount_aware"
    ),
    "primary_locale": "zh-cn",
    "fallback_locale": "en",
}


def test_provider_cache_metadata_builder_deepseek_contract() -> None:
    metadata = app._build_provider_pricing_cache_metadata(
        "deepseek",
        source_url="https://example.invalid/pricing",
        fetched_at="2026-06-16T00:00:00Z",
        ttl_seconds=86400,
    )

    assert metadata == {
        "source_url": "https://example.invalid/pricing",
        "source_kind": "official_docs_html",
        "fetched_at": "2026-06-16T00:00:00Z",
        "updated_at": "2026-06-16T00:00:00Z",
        "expires_at": "2026-06-17T00:00:00Z",
        "ttl_seconds": 86400,
        **EXPECTED_STATIC,
    }


def test_deepseek_cache_metadata_wrapper_delegates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []
    sentinel = {"sentinel": True}

    def fake_builder(
        provider_id: str,
        *,
        source_url: str,
        fetched_at: str,
        ttl_seconds: int,
    ) -> dict[str, object]:
        calls.append(
            {
                "provider_id": provider_id,
                "source_url": source_url,
                "fetched_at": fetched_at,
                "ttl_seconds": ttl_seconds,
            }
        )
        return sentinel

    monkeypatch.setattr(
        app,
        "_build_provider_pricing_cache_metadata",
        fake_builder,
    )

    result = app._build_deepseek_pricing_cache_metadata(
        source_url="https://example.invalid/source",
        fetched_at="2026-06-16T01:02:03Z",
        ttl_seconds=123,
    )

    assert result is sentinel
    assert calls == [
        {
            "provider_id": "deepseek",
            "source_url": "https://example.invalid/source",
            "fetched_at": "2026-06-16T01:02:03Z",
            "ttl_seconds": 123,
        }
    ]


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
def test_provider_cache_metadata_builder_rejects_unsupported_provider(
    provider_id: str,
) -> None:
    with pytest.raises(
        ValueError,
        match=(
            "provider_pricing_cache_metadata_"
            "not_supported"
        ),
    ):
        app._build_provider_pricing_cache_metadata(
            provider_id,
            source_url="https://example.invalid/pricing",
            fetched_at="2026-06-16T00:00:00Z",
            ttl_seconds=86400,
        )


def test_provider_cache_metadata_builder_rejects_incomplete_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        app,
        "_provider_pricing_resource_profile",
        lambda provider_id: {
            "provider": provider_id,
            "supported": True,
            "cache_schema_owner": provider_id,
            "source_kind": "official_docs_html",
            "unit": "per_million_tokens",
            "unit_legacy": "per_1m_tokens",
            "currency": "USD",
            "parser": None,
            "primary_locale": "en",
            "fallback_locale": "en",
        },
    )

    with pytest.raises(
        ValueError,
        match=(
            "provider_pricing_cache_metadata_"
            "incomplete:probe:parser"
        ),
    ):
        app._build_provider_pricing_cache_metadata(
            "probe",
            source_url="https://example.invalid/pricing",
            fetched_at="2026-06-16T00:00:00Z",
            ttl_seconds=86400,
        )


def test_legacy_writer_payload_is_unchanged(
    tmp_path: Path,
) -> None:
    target = tmp_path / "pricing.json"
    prices = {
        "probe-model": {
            "input_cache_hit": 1.0,
            "input_cache_miss": 2.0,
            "output": 3.0,
        }
    }

    app._write_pricing_cache_atomic(
        prices,
        path=target,
        source_url="https://example.invalid/pricing",
        fetched_at="2026-06-16T00:00:00Z",
        ttl_seconds=86400,
    )

    payload = json.loads(
        target.read_text(
            encoding="utf-8",
        )
    )

    assert payload == {
        "__metadata__": {
            "source_url": "https://example.invalid/pricing",
            "source_kind": "official_docs_html",
            "fetched_at": "2026-06-16T00:00:00Z",
            "updated_at": "2026-06-16T00:00:00Z",
            "expires_at": "2026-06-17T00:00:00Z",
            "ttl_seconds": 86400,
            **EXPECTED_STATIC,
        },
        **prices,
    }


def test_legacy_writer_uses_deepseek_metadata_wrapper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "pricing.json"
    calls: list[dict[str, object]] = []

    def fake_metadata(
        *,
        source_url: str,
        fetched_at: str,
        ttl_seconds: int,
    ) -> dict[str, object]:
        calls.append(
            {
                "source_url": source_url,
                "fetched_at": fetched_at,
                "ttl_seconds": ttl_seconds,
            }
        )
        return {"sentinel": True}

    monkeypatch.setattr(
        app,
        "_build_deepseek_pricing_cache_metadata",
        fake_metadata,
    )

    app._write_pricing_cache_atomic(
        {"probe-model": {}},
        path=target,
        source_url="https://example.invalid/source",
        fetched_at="2026-06-16T00:00:00Z",
        ttl_seconds=90,
    )

    payload = json.loads(
        target.read_text(
            encoding="utf-8",
        )
    )

    assert payload["__metadata__"] == {
        "sentinel": True
    }
    assert calls == [
        {
            "source_url": "https://example.invalid/source",
            "fetched_at": "2026-06-16T00:00:00Z",
            "ttl_seconds": 90,
        }
    ]


def test_legacy_writer_signature_is_unchanged() -> None:
    signature = inspect.signature(
        app._write_pricing_cache_atomic
    )

    assert list(signature.parameters) == [
        "prices",
        "path",
        "source_url",
        "fetched_at",
        "ttl_seconds",
    ]
    assert (
        signature.parameters["prices"].kind
        is inspect.Parameter.POSITIONAL_OR_KEYWORD
    )

    for name in (
        "path",
        "source_url",
        "fetched_at",
        "ttl_seconds",
    ):
        assert (
            signature.parameters[name].kind
            is inspect.Parameter.KEYWORD_ONLY
        )
