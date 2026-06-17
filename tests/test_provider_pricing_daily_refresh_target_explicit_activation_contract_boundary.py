from __future__ import annotations

import importlib
import inspect
from pathlib import Path

import pytest

app = importlib.import_module("codexchange_proxy.app")


def test_provider_owned_activation_ready_with_explicit_path(
    tmp_path: Path,
) -> None:
    target = (
        tmp_path
        / "deepseek"
        / "pricing.json"
    )

    contract = (
        app
        ._provider_pricing_daily_refresh_target_activation_contract(
            "deepseek",
            activate=True,
            mode="provider-owned",
            provider_path=target,
        )
    )

    assert contract["provider"] == "deepseek"
    assert contract["activation_source"] == (
        "explicit_arguments_only"
    )
    assert contract["activation_requested"] is True
    assert contract["requested_mode"] == "provider_owned"
    assert contract["selected_mode"] == "provider_owned"
    assert contract["selected_target_path"] == str(target)
    assert contract["target_selection_valid"] is True
    assert contract["activation_contract_valid"] is True
    assert contract["activation_ready"] is True
    assert (
        contract["provider_owned_activation_allowed"]
        is True
    )
    assert contract["provider_path_inferred"] is False
    assert contract["reads_activation_env"] is False
    assert contract["calls_execution"] is False
    assert contract["calls_refresh"] is False
    assert contract["calls_writer"] is False
    assert contract["writes_files"] is False
    assert contract["creates_directories"] is False
    assert contract["runtime_active"] is False
    assert contract["runtime_wired"] is False
    assert contract["dual_write"] is False
    assert contract["fallback_write"] is False
    assert contract["reader_switch"] is False
    assert contract["usage_source_switch"] is False
    assert contract["weclaw_source_switch"] is False
    assert (
        contract["changes_daily_refresh_contract"]
        is False
    )
    assert not target.exists()
    assert not target.parent.exists()


def test_activation_false_is_not_ready(
    tmp_path: Path,
) -> None:
    target = tmp_path / "pricing.json"

    contract = (
        app
        ._provider_pricing_daily_refresh_target_activation_contract(
            "deepseek",
            activate=False,
            mode="provider_owned",
            provider_path=target,
        )
    )

    assert contract["activation_requested"] is False
    assert contract["activation_contract_valid"] is True
    assert contract["activation_ready"] is False
    assert contract["reason"] == (
        "explicit_daily_refresh_"
        "activation_not_requested"
    )
    assert not target.exists()


def test_legacy_shared_cannot_be_explicitly_activated() -> None:
    contract = (
        app
        ._provider_pricing_daily_refresh_target_activation_contract(
            "deepseek",
            activate=True,
            mode="legacy_shared",
        )
    )

    assert contract["activation_requested"] is True
    assert contract["target_selection_valid"] is True
    assert contract["activation_contract_valid"] is False
    assert contract["activation_ready"] is False
    assert (
        contract["legacy_shared_activation_allowed"]
        is False
    )
    assert contract["reason"] == (
        "legacy_shared_daily_refresh_"
        "activation_not_allowed"
    )


def test_provider_owned_requires_explicit_provider_path() -> None:
    contract = (
        app
        ._provider_pricing_daily_refresh_target_activation_contract(
            "deepseek",
            activate=True,
            mode="provider_owned",
        )
    )

    assert contract["provider_path_argument_required"] is True
    assert (
        contract["explicit_provider_path_present"]
        is False
    )
    assert contract["target_selection_valid"] is False
    assert contract["activation_contract_valid"] is False
    assert contract["activation_ready"] is False
    assert contract["reason"] == (
        "explicit_provider_path_required"
    )


def test_disabled_activation_contract_is_ready_without_target() -> None:
    contract = (
        app
        ._provider_pricing_daily_refresh_target_activation_contract(
            "deepseek",
            activate=True,
            mode="disabled",
        )
    )

    assert contract["selected_mode"] == "disabled"
    assert contract["selected_target_path"] is None
    assert contract["target_selection_valid"] is True
    assert contract["activation_contract_valid"] is True
    assert contract["activation_ready"] is True
    assert contract["disabled_activation_allowed"] is True
    assert (
        contract["provider_owned_activation_allowed"]
        is False
    )
    assert contract["reason"] == (
        "daily_refresh_disabled_"
        "activation_contract_ready"
    )


@pytest.mark.parametrize(
    "provider_id",
    [
        "qwen-beijing",
        "qwen-singapore",
        "kimi",
        "zhipu",
        "zai",
        "custom",
    ],
)
def test_registered_provider_without_pricing_support_fails_closed(
    provider_id: str,
    tmp_path: Path,
) -> None:
    target = (
        tmp_path
        / provider_id
        / "pricing.json"
    )

    contract = (
        app
        ._provider_pricing_daily_refresh_target_activation_contract(
            provider_id,
            activate=True,
            mode="provider_owned",
            provider_path=target,
        )
    )

    assert contract["provider"] == (
        provider_id.replace("-", "_")
    )
    assert (
        contract["target_selection_valid"]
        is False
    )
    assert (
        contract["activation_contract_valid"]
        is False
    )
    assert contract["activation_ready"] is False
    assert (
        contract["provider_owned_activation_allowed"]
        is False
    )
    assert contract["runtime_active"] is False
    assert contract["runtime_wired"] is False
    assert contract["calls_execution"] is False
    assert contract["calls_refresh"] is False
    assert contract["calls_writer"] is False
    assert contract["writes_files"] is False
    assert contract["creates_directories"] is False
    assert contract["dual_write"] is False
    assert contract["fallback_write"] is False
    assert not target.exists()
    assert not target.parent.exists()


def test_unknown_provider_adapter_fails_closed_before_side_effects(
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
            ._provider_pricing_daily_refresh_target_activation_contract(
                "anthropic",
                activate=True,
                mode="provider_owned",
                provider_path=target,
            )
        )

    assert not target.exists()
    assert not target.parent.exists()



def test_contract_does_not_call_execution_refresh_or_writers(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[str] = []

    def forbidden(*args: object, **kwargs: object) -> object:
        calls.append("forbidden")
        raise AssertionError(
            "activation contract executed a runtime seam"
        )

    for name in (
        "_provider_pricing_refresh_writer_single_write_execution",
        "_refresh_provider_pricing_from_official_docs",
        "_write_pricing_cache_atomic",
        "_write_provider_pricing_cache_atomic",
        "_write_deepseek_provider_pricing_cache_atomic",
    ):
        monkeypatch.setattr(
            app,
            name,
            forbidden,
        )

    target = tmp_path / "pricing.json"

    contract = (
        app
        ._provider_pricing_daily_refresh_target_activation_contract(
            "deepseek",
            activate=True,
            mode="provider_owned",
            provider_path=target,
        )
    )

    assert contract["activation_ready"] is True
    assert calls == []
    assert not target.exists()


def test_deepseek_wrapper_delegates(
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
        (
            "_provider_pricing_daily_refresh_"
            "target_activation_contract"
        ),
        fake_contract,
    )

    target = tmp_path / "pricing.json"

    result = (
        app
        ._deepseek_pricing_daily_refresh_target_activation_contract(
            activate=True,
            mode="provider_owned",
            provider_path=target,
        )
    )

    assert result == {"provider": "deepseek"}
    assert calls == [
        {
            "provider_id": "deepseek",
            "activate": True,
            "mode": "provider_owned",
            "provider_path": target,
        }
    ]


def test_existing_daily_refresh_runtime_remains_unwired() -> None:
    signature = inspect.signature(
        app._pricing_daily_refresh_contract
    )

    assert list(signature.parameters) == ["model"]

    source = inspect.getsource(
        app._pricing_daily_refresh_contract
    )

    assert (
        "_provider_pricing_daily_refresh_"
        "target_activation_contract"
        not in source
    )
    assert (
        "_deepseek_pricing_daily_refresh_"
        "target_activation_contract"
        not in source
    )
    assert (
        "_provider_pricing_daily_refresh_"
        "target_selection_profile"
        not in source
    )
    assert (
        "_provider_pricing_refresh_writer_"
        "single_write_execution"
        not in source
    )
    assert (
        '_refresh_provider_pricing_from_official_docs('
        in source
    )
    assert '"deepseek"' in source
    assert "_pricing_cache_path()" in source


def test_activation_contract_source_has_no_hidden_input() -> None:
    source = inspect.getsource(
        app
        ._provider_pricing_daily_refresh_target_activation_contract
    )

    assert "os.environ" not in source
    assert "getenv" not in source
    assert "COX_" not in source
    assert (
        "_provider_pricing_refresh_writer_"
        "single_write_execution"
        not in source
    )
    assert (
        "_refresh_provider_pricing_from_official_docs"
        not in source
    )
    assert "_write_pricing_cache_atomic" not in source
    assert "_write_provider_pricing_cache_atomic" not in source
