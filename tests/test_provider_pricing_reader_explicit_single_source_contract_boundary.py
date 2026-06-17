from __future__ import annotations

import importlib
import inspect
import json
from pathlib import Path

import pytest

app = importlib.import_module(
    "codexchange_proxy.app"
)


def _pricing_document(
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


def test_default_selection_describes_legacy_reader(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    legacy_path = tmp_path / "legacy.json"

    monkeypatch.setattr(
        app,
        "_pricing_config_path",
        lambda: legacy_path,
    )

    result = (
        app
        ._provider_pricing_reader_selection_profile(
            "deepseek"
        )
    )

    assert result["requested_mode"] == (
        "legacy_shared"
    )
    assert result["selected_mode"] == (
        "legacy_shared"
    )
    assert result["selected_source_path"] == str(
        legacy_path
    )
    assert result["selection_valid"] is True
    assert result["profile_only"] is True
    assert result["runtime_active"] is False
    assert result["reads_pricing_file"] is False
    assert result["read_count"] == 0
    assert not legacy_path.exists()


def test_provider_owned_selection_never_resolves_legacy_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    target = (
        tmp_path
        / "deepseek"
        / "pricing.json"
    )

    def forbidden() -> Path:
        raise AssertionError(
            "provider-owned reader selection "
            "resolved a legacy path"
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

    result = (
        app
        ._provider_pricing_reader_selection_profile(
            "deepseek",
            mode="provider-owned",
            provider_path=target,
        )
    )

    assert result["requested_mode"] == (
        "provider_owned"
    )
    assert result["selected_mode"] == (
        "provider_owned"
    )
    assert result["selected_source_path"] == str(
        target
    )
    assert result["selection_valid"] is True
    assert result["provider_path_inferred"] is False
    assert result["reads_activation_env"] is False
    assert not target.exists()
    assert not target.parent.exists()


def test_provider_owned_selection_requires_explicit_path() -> None:
    result = (
        app
        ._provider_pricing_reader_selection_profile(
            "deepseek",
            mode="provider_owned",
        )
    )

    assert result["selection_valid"] is False
    assert result["selected_mode"] is None
    assert result["selected_source_path"] is None
    assert result["reason"] == (
        "explicit_provider_path_required"
    )


def test_provider_owned_activation_ready(
    tmp_path: Path,
) -> None:
    target = tmp_path / "pricing.json"

    result = (
        app
        ._provider_pricing_reader_activation_contract(
            "deepseek",
            activate=True,
            mode="provider_owned",
            provider_path=target,
        )
    )

    assert result["activation_source"] == (
        "explicit_arguments_only"
    )
    assert result["activation_requested"] is True
    assert result["activation_contract_valid"] is True
    assert result["activation_ready"] is True
    assert (
        result["provider_owned_activation_allowed"]
        is True
    )
    assert result["selected_source_path"] == str(
        target
    )
    assert result["reads_pricing_file"] is False
    assert result["calls_execution"] is False
    assert result["reader_switch"] is False
    assert result["usage_source_switch"] is False
    assert result["weclaw_source_switch"] is False
    assert not target.exists()


def test_activation_false_is_not_ready(
    tmp_path: Path,
) -> None:
    target = tmp_path / "pricing.json"

    result = (
        app
        ._provider_pricing_reader_activation_contract(
            "deepseek",
            activate=False,
            mode="provider_owned",
            provider_path=target,
        )
    )

    assert result["activation_ready"] is False
    assert result["reason"] == (
        "explicit_pricing_reader_"
        "activation_not_requested"
    )
    assert not target.exists()


def test_legacy_shared_cannot_be_explicitly_activated(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    legacy_path = tmp_path / "legacy.json"

    monkeypatch.setattr(
        app,
        "_pricing_config_path",
        lambda: legacy_path,
    )

    result = (
        app
        ._provider_pricing_reader_activation_contract(
            "deepseek",
            activate=True,
            mode="legacy_shared",
        )
    )

    assert result["activation_ready"] is False
    assert (
        result["legacy_shared_activation_allowed"]
        is False
    )
    assert result["reason"] == (
        "legacy_shared_pricing_reader_"
        "activation_not_allowed"
    )


def test_disabled_activation_is_ready_without_path() -> None:
    result = (
        app
        ._provider_pricing_reader_activation_contract(
            "deepseek",
            activate=True,
            mode="disabled",
        )
    )

    assert result["activation_ready"] is True
    assert result["disabled_activation_allowed"] is True
    assert result["selected_source_path"] is None


def test_single_source_execution_reads_exact_provider_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    target = (
        tmp_path
        / "deepseek"
        / "pricing.json"
    )
    target.parent.mkdir(parents=True)
    target.write_text(
        json.dumps(_pricing_document()),
        encoding="utf-8",
    )

    def forbidden() -> Path:
        raise AssertionError(
            "single-source execution resolved "
            "a legacy reader path"
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

    result = (
        app
        ._provider_pricing_reader_single_source_execution(
            "deepseek",
            activate=True,
            mode="provider_owned",
            provider_path=target,
        )
    )

    assert result["status"] == "ok"
    assert result["available"] is True
    assert result["source_path"] == str(target)
    assert result["reads_pricing_file"] is True
    assert result["read_count"] == 1
    assert result["models"] == [
        "deepseek-v4-pro"
    ]
    assert result["model_count"] == 1
    assert (
        result["prices"]["deepseek-v4-pro"][
            "output"
        ]
        == 0.42
    )
    assert result["fallback_read"] is False
    assert result["default_prices_used"] is False
    assert result["legacy_path_read"] is False
    assert result["writes_files"] is False
    assert result["reader_switch"] is False
    assert result["usage_source_switch"] is False
    assert result["weclaw_source_switch"] is False


def test_missing_provider_source_never_falls_back(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    target = tmp_path / "missing.json"

    def forbidden() -> object:
        raise AssertionError(
            "missing provider source used "
            "legacy/default fallback"
        )

    monkeypatch.setattr(
        app,
        "_pricing_config_path",
        forbidden,
    )
    monkeypatch.setattr(
        app,
        "_load_model_pricing_usd_per_1m",
        forbidden,
    )

    result = (
        app
        ._provider_pricing_reader_single_source_execution(
            "deepseek",
            activate=True,
            mode="provider_owned",
            provider_path=target,
        )
    )

    assert result["status"] == "error"
    assert result["reason"] == (
        "provider_pricing_reader_source_missing"
    )
    assert result["reads_pricing_file"] is False
    assert result["read_count"] == 0
    assert result["prices"] == {}
    assert result["fallback_read"] is False
    assert result["default_prices_used"] is False
    assert not target.exists()


def test_invalid_provider_source_never_falls_back(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    target = tmp_path / "invalid.json"
    target.write_text(
        "[]",
        encoding="utf-8",
    )

    def forbidden() -> object:
        raise AssertionError(
            "invalid provider source used "
            "legacy/default fallback"
        )

    monkeypatch.setattr(
        app,
        "_pricing_config_path",
        forbidden,
    )
    monkeypatch.setattr(
        app,
        "_load_model_pricing_usd_per_1m",
        forbidden,
    )

    result = (
        app
        ._provider_pricing_reader_single_source_execution(
            "deepseek",
            activate=True,
            mode="provider_owned",
            provider_path=target,
        )
    )

    assert result["status"] == "error"
    assert result["reason"] == (
        "provider_pricing_reader_source_invalid"
    )
    assert result["reads_pricing_file"] is True
    assert result["read_count"] == 1
    assert result["prices"] == {}
    assert result["fallback_read"] is False
    assert result["default_prices_used"] is False


def test_disabled_execution_performs_no_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(
        *args: object,
        **kwargs: object,
    ) -> object:
        raise AssertionError(
            "disabled reader attempted a read"
        )

    monkeypatch.setattr(
        Path,
        "read_text",
        forbidden,
    )

    result = (
        app
        ._provider_pricing_reader_single_source_execution(
            "deepseek",
            activate=True,
            mode="disabled",
        )
    )

    assert result["status"] == "disabled"
    assert result["reads_pricing_file"] is False
    assert result["read_count"] == 0
    assert result["prices"] == {}


def test_registered_provider_without_pricing_support_fails_closed(
    tmp_path: Path,
) -> None:
    target = (
        tmp_path
        / "qwen-beijing"
        / "pricing.json"
    )

    result = (
        app
        ._provider_pricing_reader_single_source_execution(
            "qwen-beijing",
            activate=True,
            mode="provider_owned",
            provider_path=target,
        )
    )

    assert result["provider"] == "qwen_beijing"
    assert result["status"] == "error"
    assert result["reads_pricing_file"] is False
    assert result["read_count"] == 0
    assert result["prices"] == {}
    assert not target.exists()
    assert not target.parent.exists()


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
        (
            app
            ._provider_pricing_reader_single_source_execution(
                "anthropic",
                activate=True,
                mode="provider_owned",
                provider_path=target,
            )
        )

    assert not target.exists()
    assert not target.parent.exists()


def test_deepseek_wrappers_delegate_exact_arguments(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[dict[str, object]] = []
    target = tmp_path / "pricing.json"

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
        return {"status": "ok"}

    monkeypatch.setattr(
        app,
        (
            "_provider_pricing_reader_"
            "single_source_execution"
        ),
        fake_execution,
    )

    result = (
        app
        ._deepseek_pricing_reader_single_source_execution(
            activate=True,
            mode="provider_owned",
            provider_path=target,
        )
    )

    assert result == {"status": "ok"}
    assert calls == [
        {
            "provider_id": "deepseek",
            "activate": True,
            "mode": "provider_owned",
            "provider_path": target,
        }
    ]


def test_reader_contract_signatures_and_source_boundaries() -> None:
    selection_signature = inspect.signature(
        app._provider_pricing_reader_selection_profile
    )
    activation_signature = inspect.signature(
        app._provider_pricing_reader_activation_contract
    )
    execution_signature = inspect.signature(
        app
        ._provider_pricing_reader_single_source_execution
    )

    assert list(
        selection_signature.parameters
    ) == [
        "provider_id",
        "mode",
        "provider_path",
    ]
    assert list(
        activation_signature.parameters
    ) == [
        "provider_id",
        "activate",
        "mode",
        "provider_path",
    ]
    assert list(
        execution_signature.parameters
    ) == [
        "provider_id",
        "activate",
        "mode",
        "provider_path",
    ]

    execution_source = inspect.getsource(
        app
        ._provider_pricing_reader_single_source_execution
    )

    assert (
        "_provider_pricing_reader_"
        "activation_contract("
        in execution_source
    )
    assert (
        "_validate_model_pricing_mapping("
        in execution_source
    )
    assert "_pricing_config_path(" not in execution_source
    assert "_pricing_cache_path(" not in execution_source
    assert (
        "_load_model_pricing_usd_per_1m("
        not in execution_source
    )
    assert "_pricing_context_for_usage_event(" not in execution_source
    assert "_weclaw_pricing_contract(" not in execution_source
    assert "_pricing_daily_refresh_contract(" not in execution_source
    assert "_write_pricing_cache_atomic(" not in execution_source
    assert "_write_provider_pricing_cache_atomic(" not in execution_source

    for name in (
        "COX_PRICING_PROVIDER_OWNED",
        "COX_PRICING_PROVIDER_CACHE_PATH",
        "COX_PRICING_READER_MODE",
        "COX_PRICING_READER_PATH",
    ):
        assert name not in execution_source


def test_reader_and_usage_runtime_entries_are_wired_but_weclaw_and_daily_refresh_remain_unwired() -> None:
    reader_source = inspect.getsource(
        app._load_model_pricing_usd_per_1m
    )
    usage_source = inspect.getsource(
        app._pricing_context_for_usage_event
    )

    assert (
        "_provider_pricing_reader_"
        "single_source_execution("
        in reader_source
    )
    assert (
        "_provider_pricing_reader_"
        "single_source_execution("
        in usage_source
    )
    assert (
        "_pricing_config_path()"
        in reader_source
    )
    assert (
        "_pricing_config_path()"
        in usage_source
    )

    frozen_symbols = (
        "_provider_pricing_reader_selection_profile",
        "_provider_pricing_reader_activation_contract",
        "_provider_pricing_reader_single_source_execution",
    )

    for function in (
        app._weclaw_pricing_contract,
        app._pricing_daily_refresh_contract,
    ):
        source = inspect.getsource(function)

        for symbol in frozen_symbols:
            assert symbol not in source
