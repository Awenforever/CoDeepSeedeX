from __future__ import annotations

import importlib
import inspect
from typing import Any

import pytest

app = importlib.import_module(
    "codexchange_proxy.app"
)


def _usage_numbers() -> dict[str, int]:
    return {
        "prompt_tokens": 100,
        "cached_tokens": 40,
        "prompt_cache_hit_tokens": 40,
        "prompt_cache_miss_tokens": 60,
        "completion_tokens": 2,
        "total_tokens": 102,
        "reasoning_tokens": 0,
    }


def _pricing_context(
    *,
    model: str = "deepseek-v4-pro",
    cache_hit: float = 1.0,
    cache_miss: float = 10.0,
    output: float = 100.0,
    currency: str = "CNY",
) -> dict[str, Any]:
    return {
        "pricing_model": model,
        "pricing_currency": currency,
        "pricing_unit": (
            "per_million_tokens"
        ),
        "pricing_source": (
            "provider_owned_explicit_path"
        ),
        "pricing_source_kind": (
            "official_docs_html"
        ),
        "pricing_updated_at": (
            "2026-06-17T00:00:00Z"
        ),
        "pricing_source_url": (
            "https://example.invalid/pricing"
        ),
        "pricing_input_cache_hit": (
            cache_hit
        ),
        "pricing_input_cache_miss": (
            cache_miss
        ),
        "pricing_output": output,
    }


def test_default_estimate_preserves_legacy_loader(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def legacy_loader() -> dict[
        str,
        dict[str, float],
    ]:
        calls.append("legacy")

        return {
            "deepseek-v4-pro": {
                "input_cache_hit": 1.0,
                "input_cache_miss": 10.0,
                "output": 100.0,
            }
        }

    monkeypatch.setattr(
        app,
        "_load_model_pricing_usd_per_1m",
        legacy_loader,
    )

    cost = app._estimate_cost_usd(
        "deepseek-v4-pro",
        _usage_numbers(),
    )
    expected = (
        40 * 1.0
        + 60 * 10.0
        + 2 * 100.0
    ) / 1_000_000

    assert calls == ["legacy"]
    assert abs(cost - expected) < 1e-12


def test_supplied_context_is_only_price_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden_loader() -> object:
        raise AssertionError(
            "context composition called "
            "legacy pricing loader"
        )

    monkeypatch.setattr(
        app,
        "_load_model_pricing_usd_per_1m",
        forbidden_loader,
    )

    context = _pricing_context(
        cache_hit=2.0,
        cache_miss=20.0,
        output=200.0,
    )

    cost = app._estimate_cost_usd(
        "deepseek-v4-pro",
        _usage_numbers(),
        pricing_context=context,
    )
    expected = (
        40 * 2.0
        + 60 * 20.0
        + 2 * 200.0
    ) / 1_000_000

    assert abs(cost - expected) < 1e-12


def test_context_uses_cache_miss_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden_loader() -> object:
        raise AssertionError(
            "context composition called "
            "legacy pricing loader"
        )

    monkeypatch.setattr(
        app,
        "_load_model_pricing_usd_per_1m",
        forbidden_loader,
    )

    usage = _usage_numbers()
    usage.pop(
        "prompt_cache_miss_tokens"
    )

    cost = app._estimate_cost_usd(
        "deepseek-v4-pro",
        usage,
        pricing_context=(
            _pricing_context()
        ),
    )
    expected = (
        40 * 1.0
        + 60 * 10.0
        + 2 * 100.0
    ) / 1_000_000

    assert abs(cost - expected) < 1e-12


@pytest.mark.parametrize(
    "context",
    [
        {},
        {
            **_pricing_context(),
            "pricing_model": "other-model",
        },
        {
            **_pricing_context(),
            "pricing_unit": "per_token",
        },
        {
            **_pricing_context(),
            "pricing_output": None,
        },
        {
            **_pricing_context(),
            "pricing_output": -1.0,
        },
        {
            **_pricing_context(),
            "pricing_output": float("nan"),
        },
        {
            **_pricing_context(),
            "pricing_output": float("inf"),
        },
    ],
)
def test_invalid_context_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    context: dict[str, Any],
) -> None:
    def forbidden_loader() -> object:
        raise AssertionError(
            "invalid context fell back "
            "to legacy pricing"
        )

    monkeypatch.setattr(
        app,
        "_load_model_pricing_usd_per_1m",
        forbidden_loader,
    )

    assert (
        app._estimate_cost_usd(
            "deepseek-v4-pro",
            _usage_numbers(),
            pricing_context=context,
        )
        == 0.0
    )


def test_non_mapping_context_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden_loader() -> object:
        raise AssertionError(
            "non-mapping context fell "
            "back to legacy pricing"
        )

    monkeypatch.setattr(
        app,
        "_load_model_pricing_usd_per_1m",
        forbidden_loader,
    )

    assert (
        app._estimate_cost_usd(
            "deepseek-v4-pro",
            _usage_numbers(),
            pricing_context=[],  # type: ignore[arg-type]
        )
        == 0.0
    )


def test_estimate_signature_and_boundary() -> None:
    signature = inspect.signature(
        app._estimate_cost_usd
    )

    assert list(
        signature.parameters
    ) == [
        "model",
        "usage_numbers",
        "pricing_context",
    ]
    assert (
        signature.parameters[
            "pricing_context"
        ].kind
        is inspect.Parameter.KEYWORD_ONLY
    )

    source = inspect.getsource(
        app._estimate_cost_usd
    )

    assert (
        "pricing_context is None"
        in source
    )
    assert (
        "_load_model_pricing_usd_per_1m()"
        in source
    )

    for marker in (
        "pricing_model",
        "pricing_unit",
        "pricing_input_cache_hit",
        "pricing_input_cache_miss",
        "pricing_output",
    ):
        assert marker in source

    for forbidden in (
        "_provider_pricing_reader_"
        "single_source_execution(",
        "_pricing_context_for_usage_event(",
        "_pricing_daily_refresh_contract(",
        "_weclaw_pricing_contract(",
    ):
        assert forbidden not in source



def test_chat_passes_same_context_to_estimate() -> None:
    source = inspect.getsource(app._chat_completions_with_usage)

    explicit_index = source.index("explicit_pricing_runtime_entry = bool(")
    legacy_index = source.index("_pricing_context_for_usage_event(effective_model)")
    estimate_index = source.index("estimated_cost_source_amount = _estimate_cost_usd(")

    assert explicit_index < legacy_index < estimate_index
    assert "provider_id=pricing_provider_id" in source
    assert "pricing_context=pricing_context" in source[estimate_index:estimate_index + 320]




@pytest.mark.asyncio
async def test_chat_persists_context_derived_amount(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _pricing_context(
        cache_hit=2.0,
        cache_miss=20.0,
        output=200.0,
        currency="CNY",
    )
    estimate_calls: list[
        tuple[str, object]
    ] = []
    stored: list[dict[str, Any]] = []

    def fake_context(
        model: str,
    ) -> dict[str, Any]:
        assert model == (
            "deepseek-v4-pro"
        )
        return context

    def fake_estimate(
        model: str,
        usage_numbers: dict[str, int],
        *,
        pricing_context: dict[
            str,
            Any,
        ] | None = None,
    ) -> float:
        assert usage_numbers[
            "prompt_tokens"
        ] == 100
        estimate_calls.append(
            (
                model,
                pricing_context,
            )
        )
        return 0.00168

    class Client:
        last_context_trimming_report = None

        async def chat_completions(
            self,
            payload: dict[str, Any],
            trace_metadata: dict[
                str,
                Any,
            ] | None = None,
        ) -> dict[str, Any]:
            assert payload["model"] == (
                "deepseek-v4-pro"
            )
            assert trace_metadata is not None

            return {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "ok",
                        }
                    }
                ],
                "usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 2,
                    "total_tokens": 102,
                    "prompt_tokens_details": {
                        "cached_tokens": 40
                    },
                },
            }

    class Store:
        def record_usage(
            self,
            **kwargs: Any,
        ) -> None:
            stored.append(kwargs)

    monkeypatch.setattr(
        app,
        "_pricing_context_for_usage_event",
        fake_context,
    )
    monkeypatch.setattr(
        app,
        "_estimate_cost_usd",
        fake_estimate,
    )

    response = await (
        app._chat_completions_with_usage(
            deepseek_client=Client(),
            store=Store(),
            payload={
                "model": "deepseek-v4-pro",
                "messages": [],
            },
            purpose="final",
            response_id="resp-1",
            previous_response_id=None,
            request_id="req-1",
            requested_model=(
                "deepseek-v4-pro"
            ),
            thinking_enabled=False,
        )
    )

    assert (
        response["choices"][0]
        ["message"]["content"]
        == "ok"
    )
    assert estimate_calls == [
        (
            "deepseek-v4-pro",
            context,
        )
    ]
    assert len(stored) == 1
    assert (
        stored[0]["pricing_context"]
        is context
    )
    assert (
        stored[0][
            "estimated_cost_source_amount"
        ]
        == 0.00168
    )
    assert (
        stored[0][
            "estimated_cost_source_currency"
        ]
        == "CNY"
    )
    assert (
        stored[0]["estimated_cost_usd"]
        == 0.0
    )


def test_weclaw_daily_and_cli_remain_frozen() -> None:
    for function in (
        app._weclaw_pricing_contract,
        app._pricing_daily_refresh_contract,
        app.SQLiteResponseStore.record_usage,
    ):
        source = inspect.getsource(
            function
        )

        assert (
            "_estimate_cost_usd("
            not in source
        )

    cli_source = inspect.getsource(
        importlib.import_module(
            "codexchange_proxy.cli"
        )
    )

    assert (
        "_estimate_cost_usd("
        not in cli_source
    )
