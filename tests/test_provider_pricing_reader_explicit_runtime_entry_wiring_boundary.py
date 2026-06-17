from __future__ import annotations

import importlib
import inspect
import json
from pathlib import Path

import pytest

app = importlib.import_module(
    "codexchange_proxy.app"
)


def _document(
    *,
    output: float = 0.42,
) -> dict[str, object]:
    return {
        "deepseek-v4-pro": {
            "input_cache_hit": 0.07,
            "input_cache_miss": 0.28,
            "output": output,
        }
    }


def test_no_argument_call_preserves_legacy_reader(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    path = tmp_path / "pricing.json"
    path.write_text(
        json.dumps(_document()),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        app,
        "_pricing_config_path",
        lambda: path,
    )

    def forbidden(
        *args: object,
        **kwargs: object,
    ) -> object:
        raise AssertionError(
            "no-argument legacy reader called "
            "provider-owned execution"
        )

    monkeypatch.setattr(
        app,
        (
            "_provider_pricing_reader_"
            "single_source_execution"
        ),
        forbidden,
    )

    result = (
        app._load_model_pricing_usd_per_1m()
    )

    assert result["deepseek-v4-pro"]["output"] == 0.42


def test_no_argument_missing_file_keeps_default_fallback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    missing = tmp_path / "missing.json"

    monkeypatch.setattr(
        app,
        "_pricing_config_path",
        lambda: missing,
    )

    result = (
        app._load_model_pricing_usd_per_1m()
    )

    assert result == (
        app.DEFAULT_MODEL_PRICING_USD_PER_1M
    )
    assert result is not (
        app.DEFAULT_MODEL_PRICING_USD_PER_1M
    )


def test_explicit_provider_owned_entry_delegates_once(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    target = tmp_path / "pricing.json"
    calls: list[dict[str, object]] = []

    def fake_execution(
        provider_id: str,
        *,
        activate: bool,
        mode: str,
        provider_path: str | Path | None = None,
    ) -> dict[str, object]:
        calls.append(
            {
                "provider_id": provider_id,
                "activate": activate,
                "mode": mode,
                "provider_path": provider_path,
            }
        )
        return {
            "status": "ok",
            "prices": _document(
                output=0.99
            ),
        }

    monkeypatch.setattr(
        app,
        (
            "_provider_pricing_reader_"
            "single_source_execution"
        ),
        fake_execution,
    )

    result = (
        app._load_model_pricing_usd_per_1m(
            provider_id="deepseek",
            activate=True,
            mode="provider-owned",
            provider_path=target,
        )
    )

    assert calls == [
        {
            "provider_id": "deepseek",
            "activate": True,
            "mode": "provider_owned",
            "provider_path": target,
        }
    ]
    assert result["deepseek-v4-pro"]["output"] == 0.99


def test_explicit_entry_defaults_provider_to_deepseek(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    target = tmp_path / "pricing.json"
    providers: list[str] = []

    def fake_execution(
        provider_id: str,
        **kwargs: object,
    ) -> dict[str, object]:
        providers.append(provider_id)
        return {
            "status": "ok",
            "prices": _document(),
        }

    monkeypatch.setattr(
        app,
        (
            "_provider_pricing_reader_"
            "single_source_execution"
        ),
        fake_execution,
    )

    result = (
        app._load_model_pricing_usd_per_1m(
            activate=True,
            mode="provider_owned",
            provider_path=target,
        )
    )

    assert providers == ["deepseek"]
    assert result


@pytest.mark.parametrize(
    "status",
    [
        "error",
        "disabled",
    ],
)
def test_explicit_non_ok_result_never_uses_legacy_or_defaults(
    monkeypatch: pytest.MonkeyPatch,
    status: str,
) -> None:
    def forbidden() -> object:
        raise AssertionError(
            "explicit reader used a legacy path"
        )

    monkeypatch.setattr(
        app,
        "_pricing_config_path",
        forbidden,
    )
    monkeypatch.setattr(
        app,
        "_pricing_cache_path",
        forbidden,
    )

    monkeypatch.setattr(
        app,
        (
            "_provider_pricing_reader_"
            "single_source_execution"
        ),
        lambda *args, **kwargs: {
            "status": status,
            "prices": {},
        },
    )

    result = (
        app._load_model_pricing_usd_per_1m(
            provider_id="deepseek",
            activate=True,
            mode=(
                "disabled"
                if status == "disabled"
                else "provider_owned"
            ),
            provider_path=Path(
                "/explicit/provider.json"
            ),
        )
    )

    assert result == {}
    assert result is not (
        app.DEFAULT_MODEL_PRICING_USD_PER_1M
    )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"provider_id": "deepseek"},
        {"activate": True},
        {"mode": "legacy_shared"},
        {
            "provider_path": Path(
                "/explicit/provider.json"
            )
        },
    ],
)
def test_incomplete_or_legacy_explicit_request_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    kwargs: dict[str, object],
) -> None:
    def forbidden(
        *args: object,
        **call_kwargs: object,
    ) -> object:
        raise AssertionError(
            "invalid explicit request executed "
            "a reader source"
        )

    monkeypatch.setattr(
        app,
        (
            "_provider_pricing_reader_"
            "single_source_execution"
        ),
        forbidden,
    )

    result = (
        app._load_model_pricing_usd_per_1m(
            **kwargs
        )
    )

    assert result == {}


def test_unknown_provider_fails_before_file_read(
    tmp_path: Path,
) -> None:
    target = (
        tmp_path
        / "anthropic"
        / "pricing.json"
    )

    with pytest.raises(
        ValueError,
        match=(
            "unsupported_provider_adapter:"
            "anthropic"
        ),
    ):
        app._load_model_pricing_usd_per_1m(
            provider_id="anthropic",
            activate=True,
            mode="provider_owned",
            provider_path=target,
        )

    assert not target.exists()
    assert not target.parent.exists()


def test_provider_owned_environment_does_not_activate_default_call(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    legacy = tmp_path / "legacy.json"
    legacy.write_text(
        json.dumps(_document()),
        encoding="utf-8",
    )

    monkeypatch.setenv(
        "COX_PRICING_READER_MODE",
        "provider_owned",
    )
    monkeypatch.setenv(
        "COX_PRICING_READER_PATH",
        str(tmp_path / "provider.json"),
    )
    monkeypatch.setattr(
        app,
        "_pricing_config_path",
        lambda: legacy,
    )

    def forbidden(
        *args: object,
        **kwargs: object,
    ) -> object:
        raise AssertionError(
            "environment activated provider reader"
        )

    monkeypatch.setattr(
        app,
        (
            "_provider_pricing_reader_"
            "single_source_execution"
        ),
        forbidden,
    )

    result = (
        app._load_model_pricing_usd_per_1m()
    )

    assert result["deepseek-v4-pro"]["output"] == 0.42


def test_loader_signature_and_source_boundary() -> None:
    signature = inspect.signature(
        app._load_model_pricing_usd_per_1m
    )

    assert list(signature.parameters) == [
        "provider_id",
        "activate",
        "mode",
        "provider_path",
    ]

    for parameter in (
        "provider_id",
        "activate",
        "mode",
        "provider_path",
    ):
        assert (
            signature.parameters[
                parameter
            ].kind
            is inspect.Parameter.KEYWORD_ONLY
        )

    source = inspect.getsource(
        app._load_model_pricing_usd_per_1m
    )

    assert (
        "_provider_pricing_reader_"
        "single_source_execution("
        in source
    )
    assert "_pricing_config_path()" in source
    assert "_pricing_context_for_usage_event(" not in source
    assert "_weclaw_pricing_contract(" not in source
    assert "_pricing_daily_refresh_contract(" not in source
    assert "_write_pricing_cache_atomic(" not in source

    for name in (
        "COX_PRICING_READER_MODE",
        "COX_PRICING_READER_PATH",
        "COX_PRICING_PROVIDER_OWNED",
        "COX_PRICING_PROVIDER_CACHE_PATH",
    ):
        assert name not in source


def test_existing_production_callers_remain_legacy_no_argument_calls() -> None:
    for function in (
        app._estimate_cost_usd,
        app._execute_proxy_tool_call,
        app._pricing_context_for_usage_event,
        app._weclaw_pricing_contract,
    ):
        source = inspect.getsource(function)

        assert (
            "_load_model_pricing_usd_per_1m()"
            in source
        )
        assert (
            "_load_model_pricing_usd_per_1m("
            "provider_id="
            not in source
        )


def test_usage_context_is_explicitly_wired_while_weclaw_daily_refresh_and_cli_remain_frozen() -> None:
    usage_source = inspect.getsource(
        app._pricing_context_for_usage_event
    )

    assert (
        "_provider_pricing_reader_"
        "single_source_execution("
        in usage_source
    )
    assert (
        "_pricing_config_path()"
        in usage_source
    )

    reader_symbols = (
        "_provider_pricing_reader_selection_profile",
        "_provider_pricing_reader_activation_contract",
        "_provider_pricing_reader_single_source_execution",
    )

    for function in (
        app._weclaw_pricing_contract,
        app._pricing_daily_refresh_contract,
    ):
        source = inspect.getsource(function)

        for symbol in reader_symbols:
            assert symbol not in source
