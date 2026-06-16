from __future__ import annotations

import importlib
import inspect
from pathlib import Path

import pytest


app = importlib.import_module(
    "codexchange_proxy.app"
)


def test_provider_owned_activation_requires_explicit_intent_and_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    legacy = tmp_path / "legacy.json"
    provider = (
        tmp_path
        / "providers"
        / "deepseek"
        / "pricing.json"
    )

    monkeypatch.setenv(
        "COX_PRICING_CACHE_PATH",
        str(legacy),
    )
    monkeypatch.setenv(
        "COX_PRICING_REFRESH_WRITER_MODE",
        "disabled",
    )
    monkeypatch.setenv(
        "COX_PRICING_REFRESH_WRITER_PATH",
        str(tmp_path / "ignored.json"),
    )
    monkeypatch.setenv(
        "COX_PRICING_PROVIDER_CACHE_PATH",
        str(tmp_path / "ignored-provider.json"),
    )

    calls: list[str] = []

    def forbidden(*args: object, **kwargs: object) -> None:
        calls.append("writer")
        raise AssertionError(
            "activation contract called writer"
        )

    monkeypatch.setattr(
        app,
        "_write_pricing_cache_atomic",
        forbidden,
    )
    monkeypatch.setattr(
        app,
        "_write_provider_pricing_cache_atomic",
        forbidden,
    )
    monkeypatch.setattr(
        app,
        "_write_deepseek_provider_pricing_cache_atomic",
        forbidden,
    )

    contract = (
        app
        ._provider_pricing_refresh_writer_activation_contract(
            "deepseek",
            activate=True,
            mode="provider-owned",
            provider_path=provider,
        )
    )

    assert contract["supported"] is True
    assert (
        contract["activation_source"]
        == "explicit_arguments_only"
    )
    assert contract["activation_requested"] is True
    assert (
        contract["requested_mode"]
        == "provider_owned"
    )
    assert (
        contract["activation_contract_valid"]
        is True
    )
    assert contract["activation_ready"] is True
    assert (
        contract["candidate_writer"]
        == (
            "_write_deepseek_provider_"
            "pricing_cache_atomic"
        )
    )
    assert (
        contract["candidate_path"]
        == str(provider)
    )
    assert (
        contract["automatic_environment_lookup"]
        is False
    )
    assert contract["automatic_cli_lookup"] is False
    assert contract["runtime_wiring_present"] is False
    assert (
        contract["runtime_activation_allowed"]
        is False
    )
    assert contract["runtime_active"] is False
    assert contract["execution_allowed"] is False
    assert contract["calls_writer"] is False
    assert contract["writes_files"] is False
    assert contract["changes_refresh_routing"] is False
    assert contract["changes_reader_routing"] is False
    assert (
        contract["changes_daily_refresh_target"]
        is False
    )
    assert calls == []
    assert not legacy.exists()
    assert not provider.exists()
    assert not provider.parent.exists()


def test_activation_not_requested_never_becomes_ready(
    tmp_path: Path,
) -> None:
    provider = tmp_path / "pricing.json"

    contract = (
        app
        ._provider_pricing_refresh_writer_activation_contract(
            "deepseek",
            activate=False,
            mode="provider_owned",
            provider_path=provider,
        )
    )

    assert contract["activation_requested"] is False
    assert contract["activation_ready"] is False
    assert (
        contract["reason"]
        == "explicit_activation_not_requested"
    )
    assert contract["runtime_active"] is False
    assert not provider.exists()


def test_legacy_shared_cannot_be_explicitly_activated() -> None:
    contract = (
        app
        ._provider_pricing_refresh_writer_activation_contract(
            "deepseek",
            activate=True,
            mode="legacy_shared",
        )
    )

    assert contract["activation_requested"] is True
    assert (
        contract["activation_contract_valid"]
        is False
    )
    assert contract["activation_ready"] is False
    assert (
        contract[
            "legacy_shared_activation_allowed"
        ]
        is False
    )
    assert (
        contract["reason"]
        == "legacy_shared_activation_not_allowed"
    )


def test_provider_owned_requires_explicit_provider_path() -> None:
    contract = (
        app
        ._provider_pricing_refresh_writer_activation_contract(
            "deepseek",
            activate=True,
            mode="provider_owned",
        )
    )

    assert contract["activation_ready"] is False
    assert (
        contract["activation_contract_valid"]
        is False
    )
    assert (
        contract[
            "provider_path_argument_required"
        ]
        is True
    )
    assert (
        contract["reason"]
        == "explicit_provider_path_required"
    )


def test_disabled_candidate_is_explicit_but_not_executed() -> None:
    contract = (
        app
        ._deepseek_pricing_refresh_writer_activation_contract(
            activate=True,
            mode="disabled",
        )
    )

    assert contract["activation_requested"] is True
    assert contract["activation_contract_valid"] is True
    assert contract["activation_ready"] is True
    assert contract["candidate_writer"] is None
    assert contract["candidate_path"] is None
    assert contract["execution_allowed"] is False
    assert contract["runtime_active"] is False
    assert (
        contract["reason"]
        == "disabled_activation_contract_ready"
    )


@pytest.mark.parametrize(
    "provider_id",
    [
        "qwen-singapore",
        "kimi",
        "zhipu",
        "zai",
        "custom",
    ],
)
def test_unsupported_provider_fails_closed(
    provider_id: str,
    tmp_path: Path,
) -> None:
    provider_path = (
        tmp_path
        / provider_id
        / "pricing.json"
    )

    contract = (
        app
        ._provider_pricing_refresh_writer_activation_contract(
            provider_id,
            activate=True,
            mode="provider_owned",
            provider_path=provider_path,
        )
    )

    assert contract["supported"] is False
    assert (
        contract["activation_contract_valid"]
        is False
    )
    assert contract["activation_ready"] is False
    assert contract["runtime_active"] is False
    assert contract["execution_allowed"] is False
    assert contract["candidate_writer"] is None
    assert contract["candidate_path"] is None
    assert not provider_path.exists()
    assert not provider_path.parent.exists()


def test_invalid_mode_fails_closed() -> None:
    with pytest.raises(
        ValueError,
        match=(
            "provider_pricing_refresh_writer_"
            "selection_mode_not_supported"
        ),
    ):
        app._provider_pricing_refresh_writer_activation_contract(
            "deepseek",
            activate=True,
            mode="dual_write",
        )


def test_deepseek_activation_wrapper_delegates(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[dict[str, object]] = []

    def fake_contract(
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
        return {"provider": provider_id}

    monkeypatch.setattr(
        app,
        "_provider_pricing_refresh_writer_activation_contract",
        fake_contract,
    )

    path = tmp_path / "pricing.json"

    result = (
        app
        ._deepseek_pricing_refresh_writer_activation_contract(
            activate=True,
            mode="provider_owned",
            provider_path=path,
        )
    )

    assert result == {
        "provider": "deepseek"
    }
    assert calls == [
        {
            "provider_id": "deepseek",
            "activate": True,
            "mode": "provider_owned",
            "provider_path": path,
        }
    ]


def test_activation_contract_signatures_are_explicit() -> None:
    provider_signature = inspect.signature(
        app
        ._provider_pricing_refresh_writer_activation_contract
    )
    deepseek_signature = inspect.signature(
        app
        ._deepseek_pricing_refresh_writer_activation_contract
    )

    assert list(
        provider_signature.parameters
    ) == [
        "provider_id",
        "activate",
        "mode",
        "provider_path",
    ]
    assert list(
        deepseek_signature.parameters
    ) == [
        "activate",
        "mode",
        "provider_path",
    ]

    for signature in (
        provider_signature,
        deepseek_signature,
    ):
        assert (
            signature.parameters[
                "activate"
            ].kind
            is inspect.Parameter.KEYWORD_ONLY
        )
        assert (
            signature.parameters[
                "activate"
            ].default
            is inspect.Parameter.empty
        )
        assert (
            signature.parameters[
                "mode"
            ].kind
            is inspect.Parameter.KEYWORD_ONLY
        )
        assert (
            signature.parameters[
                "mode"
            ].default
            is inspect.Parameter.empty
        )
        assert (
            signature.parameters[
                "provider_path"
            ].kind
            is inspect.Parameter.KEYWORD_ONLY
        )


def test_existing_runtime_does_not_use_activation_contract() -> None:
    for function in (
        app._refresh_provider_pricing_from_official_docs,
        app._refresh_deepseek_pricing_from_official_docs,
        app._pricing_daily_refresh_contract,
        app._load_model_pricing_usd_per_1m,
        app._pricing_context_for_usage_event,
        app._weclaw_pricing_contract,
    ):
        source = inspect.getsource(
            function
        )

        assert (
            "_provider_pricing_refresh_writer_"
            "activation_contract"
            not in source
        )
        assert (
            "_deepseek_pricing_refresh_writer_"
            "activation_contract"
            not in source
        )

    refresh_source = inspect.getsource(
        app
        ._refresh_provider_pricing_from_official_docs
    )

    assert (
        "pricing_cache_path="
        "_pricing_cache_path"
        in refresh_source
    )
    assert (
        "write_pricing_cache_atomic="
        "_write_pricing_cache_atomic"
        in refresh_source
    )
    assert (
        "_write_provider_pricing_cache_atomic"
        not in refresh_source
    )


def test_activation_cli_and_environment_surfaces_do_not_exist() -> None:
    cli_source = inspect.getsource(
        importlib.import_module(
            "codexchange_proxy.cli"
        )
    )
    app_source = inspect.getsource(app)

    for value in (
        "--pricing-refresh-writer-mode",
        "--pricing-refresh-writer-path",
        "--pricing-provider-cache-path",
        "COX_PRICING_REFRESH_WRITER_MODE",
        "COX_PRICING_REFRESH_WRITER_PATH",
        "COX_PRICING_PROVIDER_CACHE_PATH",
    ):
        assert value not in cli_source
        assert value not in app_source
