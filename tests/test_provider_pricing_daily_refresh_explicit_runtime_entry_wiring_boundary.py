from __future__ import annotations

import importlib
import inspect
from pathlib import Path

import pytest

app = importlib.import_module(
    "codexchange_proxy.app"
)


def _install_paths(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> tuple[Path, Path]:
    reader_path = tmp_path / "legacy-reader.json"
    legacy_cache = tmp_path / "legacy-cache.json"
    reader_path.write_text(
        "{}",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        app,
        "_pricing_config_path",
        lambda: reader_path,
    )
    monkeypatch.setattr(
        app,
        "_pricing_cache_path",
        lambda: legacy_cache,
    )
    monkeypatch.setattr(
        app,
        "_pricing_current_local_day",
        lambda: "2026-06-17",
    )
    monkeypatch.setattr(
        app,
        "_pricing_local_day_from_timestamp",
        lambda value: (
            "2026-06-16"
            if value
            else None
        ),
    )

    return reader_path, legacy_cache


def test_default_call_preserves_legacy_refresh_dispatch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    reader_path, legacy_cache = _install_paths(
        monkeypatch,
        tmp_path,
    )
    legacy_calls: list[dict[str, object]] = []

    monkeypatch.setattr(
        app,
        "_pricing_source_info",
        lambda path: {
            "source_kind": (
                "bundled_official_docs_snapshot"
            )
        },
    )
    monkeypatch.setattr(
        app,
        "_pricing_metadata_from_path",
        lambda path: {
            "source_kind": (
                "bundled_official_docs_snapshot"
            ),
            "snapshot_created_at": (
                "2026-06-16T00:00:00Z"
            ),
        },
    )
    monkeypatch.setattr(
        app,
        "_pricing_daily_refresh_required",
        lambda metadata, *, source_kind: True,
    )
    monkeypatch.setattr(
        app,
        "_pricing_auto_refresh_enabled",
        lambda: True,
    )

    def fake_legacy_refresh(
        provider_id: str,
        **kwargs: object,
    ) -> dict[str, object]:
        legacy_calls.append(
            {
                "provider_id": provider_id,
                **kwargs,
            }
        )
        return {
            "status": "ok",
            "writes_cache": True,
            "updated_at": (
                "2026-06-17T00:00:00Z"
            ),
            "expires_at": (
                "2026-06-18T00:00:00Z"
            ),
            "ttl_seconds": 86400,
        }

    monkeypatch.setattr(
        app,
        "_refresh_provider_pricing_from_official_docs",
        fake_legacy_refresh,
    )

    def forbidden_composition(
        *args: object,
        **kwargs: object,
    ) -> object:
        raise AssertionError(
            "default daily refresh called "
            "provider-owned composition"
        )

    monkeypatch.setattr(
        app,
        (
            "_provider_pricing_daily_refresh_"
            "target_single_write_execution"
        ),
        forbidden_composition,
    )

    result = app._pricing_daily_refresh_contract(
        "deepseek-v4-pro"
    )

    assert result["status"] == (
        "official_daily_refresh_succeeded"
    )
    assert result["active_path"] == str(
        reader_path
    )
    assert result["refresh_target_path"] == str(
        legacy_cache
    )
    assert len(legacy_calls) == 1
    assert (
        legacy_calls[0]["provider_id"]
        == "deepseek"
    )
    assert (
        legacy_calls[0]["cache_path"]
        == legacy_cache
    )


def test_explicit_provider_owned_stale_target_executes_once(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    reader_path, _ = _install_paths(
        monkeypatch,
        tmp_path,
    )
    target = (
        tmp_path
        / "deepseek"
        / "pricing.json"
    )
    calls: list[dict[str, object]] = []

    monkeypatch.setattr(
        app,
        "_pricing_daily_refresh_required",
        lambda metadata, *, source_kind: True,
    )
    monkeypatch.setattr(
        app,
        "_pricing_auto_refresh_enabled",
        lambda: True,
    )

    def forbidden_legacy(
        *args: object,
        **kwargs: object,
    ) -> object:
        raise AssertionError(
            "explicit provider-owned entry "
            "called legacy refresh"
        )

    monkeypatch.setattr(
        app,
        "_refresh_provider_pricing_from_official_docs",
        forbidden_legacy,
    )

    def fake_composition(
        provider_id: str,
        *,
        activate: bool,
        mode: str,
        provider_path: str | Path | None,
        model: str | None = None,
        source_url: str | None = None,
        timeout: float = 20.0,
    ) -> dict[str, object]:
        calls.append(
            {
                "provider_id": provider_id,
                "activate": activate,
                "mode": mode,
                "provider_path": provider_path,
                "model": model,
                "source_url": source_url,
                "timeout": timeout,
            }
        )
        return {
            "status": "ok",
            "writes_cache": True,
            "updated_at": (
                "2026-06-17T00:00:00Z"
            ),
            "expires_at": (
                "2026-06-18T00:00:00Z"
            ),
            "ttl_seconds": 86400,
        }

    monkeypatch.setattr(
        app,
        (
            "_provider_pricing_daily_refresh_"
            "target_single_write_execution"
        ),
        fake_composition,
    )

    result = app._pricing_daily_refresh_contract(
        "deepseek-v4-pro",
        provider_id="deepseek",
        activate=True,
        mode="provider-owned",
        provider_path=target,
        source_url="https://example.invalid",
        timeout=4.0,
    )

    assert result["status"] == (
        "official_daily_refresh_succeeded"
    )
    assert result["refreshed"] is True
    assert result["runtime_entry_wired"] is True
    assert (
        result["provider_owned_execution_called"]
        is True
    )
    assert result["active_path"] == str(
        reader_path
    )
    assert result["reader_path"] == str(
        reader_path
    )
    assert result["reader_path_unchanged"] is True
    assert result["refresh_target_path"] == str(
        target
    )
    assert result["reader_switch"] is False
    assert result["usage_source_switch"] is False
    assert result["weclaw_source_switch"] is False
    assert result["dual_write"] is False
    assert result["fallback_write"] is False
    assert calls == [
        {
            "provider_id": "deepseek",
            "activate": True,
            "mode": "provider_owned",
            "provider_path": target,
            "model": "deepseek-v4-pro",
            "source_url": (
                "https://example.invalid"
            ),
            "timeout": 4.0,
        }
    ]


def test_explicit_current_target_does_not_execute(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _install_paths(monkeypatch, tmp_path)
    target = tmp_path / "pricing.json"
    target.write_text(
        "{}",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        app,
        "_pricing_metadata_from_path",
        lambda path: {
            "source_kind": "official_docs_html",
            "fetched_at": (
                "2026-06-17T00:00:00Z"
            ),
        },
    )
    monkeypatch.setattr(
        app,
        "_pricing_daily_refresh_required",
        lambda metadata, *, source_kind: False,
    )
    monkeypatch.setattr(
        app,
        "_pricing_auto_refresh_enabled",
        lambda: True,
    )

    def forbidden(
        *args: object,
        **kwargs: object,
    ) -> object:
        raise AssertionError(
            "current target executed refresh"
        )

    monkeypatch.setattr(
        app,
        (
            "_provider_pricing_daily_refresh_"
            "target_single_write_execution"
        ),
        forbidden,
    )
    monkeypatch.setattr(
        app,
        "_refresh_provider_pricing_from_official_docs",
        forbidden,
    )

    result = app._pricing_daily_refresh_contract(
        provider_id="deepseek",
        activate=True,
        mode="provider_owned",
        provider_path=target,
    )

    assert result["status"] == (
        "official_daily_refresh_current"
    )
    assert result["requires_refresh"] is False
    assert result["refreshed"] is False
    assert (
        result["provider_owned_execution_called"]
        is False
    )


def test_auto_refresh_disabled_does_not_execute(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _install_paths(monkeypatch, tmp_path)
    target = tmp_path / "pricing.json"

    monkeypatch.setattr(
        app,
        "_pricing_daily_refresh_required",
        lambda metadata, *, source_kind: True,
    )
    monkeypatch.setattr(
        app,
        "_pricing_auto_refresh_enabled",
        lambda: False,
    )

    def forbidden(
        *args: object,
        **kwargs: object,
    ) -> object:
        raise AssertionError(
            "disabled auto refresh executed"
        )

    monkeypatch.setattr(
        app,
        (
            "_provider_pricing_daily_refresh_"
            "target_single_write_execution"
        ),
        forbidden,
    )

    result = app._pricing_daily_refresh_contract(
        provider_id="deepseek",
        activate=True,
        mode="provider_owned",
        provider_path=target,
    )

    assert result["status"] == (
        "official_daily_refresh_required"
    )
    assert result["requires_refresh"] is True
    assert result["refreshed"] is False
    assert (
        result["provider_owned_execution_called"]
        is False
    )


def test_explicit_disabled_mode_never_executes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _install_paths(monkeypatch, tmp_path)

    def forbidden(
        *args: object,
        **kwargs: object,
    ) -> object:
        raise AssertionError(
            "disabled mode executed refresh"
        )

    monkeypatch.setattr(
        app,
        (
            "_provider_pricing_daily_refresh_"
            "target_single_write_execution"
        ),
        forbidden,
    )
    monkeypatch.setattr(
        app,
        "_refresh_provider_pricing_from_official_docs",
        forbidden,
    )

    result = app._pricing_daily_refresh_contract(
        provider_id="deepseek",
        activate=True,
        mode="disabled",
    )

    assert result["status"] == (
        "official_daily_refresh_"
        "disabled_explicitly"
    )
    assert result["requires_refresh"] is False
    assert result["refreshed"] is False
    assert result["refresh_target_path"] is None


@pytest.mark.parametrize(
    "activate,provider_path,expected_reason",
    [
        (
            False,
            "explicit",
            (
                "explicit_daily_refresh_"
                "activation_not_requested"
            ),
        ),
        (
            True,
            None,
            "explicit_provider_path_required",
        ),
    ],
)
def test_invalid_provider_owned_request_fails_before_execution(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    activate: bool,
    provider_path: str | None,
    expected_reason: str,
) -> None:
    _install_paths(monkeypatch, tmp_path)
    target = (
        tmp_path / "pricing.json"
        if provider_path
        else None
    )

    def forbidden(
        *args: object,
        **kwargs: object,
    ) -> object:
        raise AssertionError(
            "invalid request executed refresh"
        )

    monkeypatch.setattr(
        app,
        (
            "_provider_pricing_daily_refresh_"
            "target_single_write_execution"
        ),
        forbidden,
    )
    monkeypatch.setattr(
        app,
        "_refresh_provider_pricing_from_official_docs",
        forbidden,
    )

    result = app._pricing_daily_refresh_contract(
        provider_id="deepseek",
        activate=activate,
        mode="provider_owned",
        provider_path=target,
    )

    assert result["status"] == (
        "official_daily_refresh_"
        "explicit_target_rejected"
    )
    assert result["reason"] == expected_reason
    assert result["requires_refresh"] is False
    assert result["refreshed"] is False


def test_unknown_adapter_fails_before_network_or_write(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _install_paths(monkeypatch, tmp_path)
    target = (
        tmp_path
        / "anthropic"
        / "pricing.json"
    )

    def forbidden(
        *args: object,
        **kwargs: object,
    ) -> object:
        raise AssertionError(
            "unknown adapter reached execution"
        )

    monkeypatch.setattr(
        app,
        (
            "_provider_pricing_daily_refresh_"
            "target_single_write_execution"
        ),
        forbidden,
    )
    monkeypatch.setattr(
        app,
        "_refresh_provider_pricing_from_official_docs",
        forbidden,
    )

    with pytest.raises(
        ValueError,
        match=(
            "unsupported_provider_adapter:"
            "anthropic"
        ),
    ):
        app._pricing_daily_refresh_contract(
            provider_id="anthropic",
            activate=True,
            mode="provider_owned",
            provider_path=target,
        )

    assert not target.exists()
    assert not target.parent.exists()


def test_provider_owned_failure_never_falls_back_to_legacy(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _install_paths(monkeypatch, tmp_path)
    target = tmp_path / "pricing.json"
    calls: list[str] = []

    monkeypatch.setattr(
        app,
        "_pricing_daily_refresh_required",
        lambda metadata, *, source_kind: True,
    )
    monkeypatch.setattr(
        app,
        "_pricing_auto_refresh_enabled",
        lambda: True,
    )

    def forbidden_legacy(
        *args: object,
        **kwargs: object,
    ) -> object:
        calls.append("legacy")
        raise AssertionError(
            "provider-owned failure fell back "
            "to legacy refresh"
        )

    monkeypatch.setattr(
        app,
        "_refresh_provider_pricing_from_official_docs",
        forbidden_legacy,
    )

    def failed_composition(
        *args: object,
        **kwargs: object,
    ) -> dict[str, object]:
        calls.append("provider_owned")
        return {
            "status": "error",
            "reason": (
                "official_pricing_cache_"
                "write_failed"
            ),
            "writes_cache": False,
            "old_cache_preserved": True,
        }

    monkeypatch.setattr(
        app,
        (
            "_provider_pricing_daily_refresh_"
            "target_single_write_execution"
        ),
        failed_composition,
    )

    result = app._pricing_daily_refresh_contract(
        provider_id="deepseek",
        activate=True,
        mode="provider_owned",
        provider_path=target,
    )

    assert result["status"] == (
        "official_daily_refresh_"
        "failed_using_previous_prices"
    )
    assert result["reason"] == (
        "official_pricing_cache_write_failed"
    )
    assert result["old_cache_preserved"] is True
    assert result["dual_write"] is False
    assert result["fallback_write"] is False
    assert calls == ["provider_owned"]


def test_provider_owned_activation_environment_is_ignored(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _install_paths(monkeypatch, tmp_path)

    for name, value in {
        "COX_PRICING_PROVIDER_OWNED": "1",
        "COX_PRICING_PROVIDER_CACHE_PATH": (
            str(tmp_path / "provider.json")
        ),
        "COX_PRICING_DAILY_REFRESH_MODE": (
            "provider_owned"
        ),
        "COX_PRICING_DAILY_REFRESH_PATH": (
            str(tmp_path / "provider.json")
        ),
    }.items():
        monkeypatch.setenv(name, value)

    monkeypatch.setattr(
        app,
        "_pricing_source_info",
        lambda path: {
            "source_kind": "official_docs_html"
        },
    )
    monkeypatch.setattr(
        app,
        "_pricing_metadata_from_path",
        lambda path: {
            "source_kind": "official_docs_html",
            "fetched_at": (
                "2026-06-17T00:00:00Z"
            ),
        },
    )
    monkeypatch.setattr(
        app,
        "_pricing_daily_refresh_required",
        lambda metadata, *, source_kind: False,
    )

    def forbidden(
        *args: object,
        **kwargs: object,
    ) -> object:
        raise AssertionError(
            "environment implicitly activated "
            "provider-owned refresh"
        )

    monkeypatch.setattr(
        app,
        (
            "_provider_pricing_daily_refresh_"
            "target_single_write_execution"
        ),
        forbidden,
    )

    result = app._pricing_daily_refresh_contract()

    assert result["status"] == (
        "official_daily_refresh_current"
    )
    assert "runtime_entry_wired" not in result


def test_runtime_entry_source_and_callers_preserve_boundaries() -> None:
    signature = inspect.signature(
        app._pricing_daily_refresh_contract
    )
    source = inspect.getsource(
        app._pricing_daily_refresh_contract
    )

    assert list(
        signature.parameters
    ) == [
        "model",
        "provider_id",
        "activate",
        "mode",
        "provider_path",
        "source_url",
        "timeout",
    ]
    assert (
        "_provider_pricing_daily_refresh_"
        "target_activation_contract("
        in source
    )
    assert (
        "_provider_pricing_daily_refresh_"
        "target_single_write_execution("
        in source
    )
    assert (
        "_provider_pricing_refresh_writer_"
        "single_write_execution("
        not in source
    )
    assert (
        "_write_provider_pricing_cache_atomic"
        not in source
    )
    assert (
        "_write_deepseek_provider_"
        "pricing_cache_atomic"
        not in source
    )

    weclaw_source = inspect.getsource(
        app._weclaw_pricing_contract
    )
    reader_source = inspect.getsource(
        app._load_model_pricing_usd_per_1m
    )
    usage_source = inspect.getsource(
        app._pricing_context_for_usage_event
    )

    assert (
        "_pricing_daily_refresh_contract(model)"
        in weclaw_source
    )
    assert (
        "_provider_pricing_daily_refresh_"
        "target_single_write_execution"
        not in weclaw_source
    )
    assert "_pricing_config_path()" in reader_source
    assert "_pricing_config_path()" in usage_source

    for name in (
        "COX_PRICING_PROVIDER_OWNED",
        "COX_PRICING_PROVIDER_CACHE_PATH",
        "COX_PRICING_DAILY_REFRESH_MODE",
        "COX_PRICING_DAILY_REFRESH_PATH",
    ):
        assert name not in source
