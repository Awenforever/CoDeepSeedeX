from __future__ import annotations

import importlib
import inspect
from pathlib import Path

import pytest


app = importlib.import_module(
    "codexchange_proxy.app"
)


def test_default_selection_describes_current_legacy_runtime(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    legacy = tmp_path / "legacy.json"
    monkeypatch.setenv(
        "COX_PRICING_CACHE_PATH",
        str(legacy),
    )

    calls: list[str] = []

    def forbidden(*args: object, **kwargs: object) -> None:
        calls.append("writer")
        raise AssertionError(
            "selection profile called writer"
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

    profile = (
        app
        ._provider_pricing_refresh_writer_selection_profile(
            "deepseek"
        )
    )

    assert profile["supported"] is True
    assert (
        profile["requested_mode"]
        == "legacy_shared"
    )
    assert (
        profile["selected_mode"]
        == "legacy_shared"
    )
    assert (
        profile["default_mode"]
        == "legacy_shared"
    )
    assert profile["selection_valid"] is True
    assert (
        profile["selected_writer"]
        == "_write_pricing_cache_atomic"
    )
    assert (
        profile["selected_path"]
        == str(legacy)
    )
    assert (
        profile["current_runtime_mode"]
        == "legacy_shared"
    )
    assert (
        profile["current_runtime_writer"]
        == "_write_pricing_cache_atomic"
    )
    assert (
        profile["current_runtime_path"]
        == str(legacy)
    )
    assert profile["profile_only"] is True
    assert profile["runtime_active"] is False
    assert (
        profile["runtime_activation_allowed"]
        is False
    )
    assert (
        profile["selection_has_side_effects"]
        is False
    )
    assert profile["writes_files"] is False
    assert profile["calls_writer"] is False
    assert calls == []
    assert not legacy.exists()


def test_provider_owned_candidate_requires_explicit_path(
    tmp_path: Path,
) -> None:
    missing = (
        app
        ._provider_pricing_refresh_writer_selection_profile(
            "deepseek",
            mode="provider_owned",
        )
    )

    assert missing["supported"] is True
    assert missing["selection_valid"] is False
    assert missing["selected_mode"] is None
    assert missing["selected_writer"] is None
    assert missing["selected_path"] is None
    assert (
        missing["reason"]
        == "explicit_provider_path_required"
    )

    provider_path = (
        tmp_path
        / "providers"
        / "deepseek"
        / "pricing.json"
    )

    selected = (
        app
        ._provider_pricing_refresh_writer_selection_profile(
            "deepseek",
            mode="provider-owned",
            provider_path=provider_path,
        )
    )

    assert selected["selection_valid"] is True
    assert (
        selected["selected_mode"]
        == "provider_owned"
    )
    assert (
        selected["selected_writer"]
        == (
            "_write_deepseek_provider_"
            "pricing_cache_atomic"
        )
    )
    assert (
        selected["selected_path"]
        == str(provider_path)
    )
    assert (
        selected[
            "explicit_provider_path_present"
        ]
        is True
    )
    assert (
        selected[
            "requires_explicit_provider_path"
        ]
        is True
    )
    assert selected["runtime_active"] is False
    assert (
        selected["changes_refresh_routing"]
        is False
    )
    assert (
        selected["changes_daily_refresh_target"]
        is False
    )
    assert not provider_path.exists()
    assert not provider_path.parent.exists()


def test_disabled_mode_is_profile_only() -> None:
    profile = (
        app
        ._provider_pricing_refresh_writer_selection_profile(
            "deepseek",
            mode="disabled",
        )
    )

    assert profile["selection_valid"] is True
    assert profile["selected_mode"] == "disabled"
    assert profile["candidate_writer"] is None
    assert profile["selected_writer"] is None
    assert profile["selected_path"] is None
    assert profile["runtime_active"] is False
    assert profile["writes_files"] is False
    assert profile["calls_writer"] is False


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
def test_unsupported_provider_is_neutral_without_deepseek_leakage(
    provider_id: str,
    tmp_path: Path,
) -> None:
    candidate = (
        tmp_path
        / provider_id
        / "pricing.json"
    )

    profile = (
        app
        ._provider_pricing_refresh_writer_selection_profile(
            provider_id,
            mode="provider_owned",
            provider_path=candidate,
        )
    )

    assert profile["supported"] is False
    assert profile["selection_valid"] is False
    assert profile["selected_mode"] is None
    assert profile["candidate_writer"] is None
    assert profile["selected_writer"] is None
    assert profile["selected_path"] is None
    assert profile["legacy_path"] is None
    assert profile["provider_path"] is None
    assert profile["current_runtime_mode"] is None
    assert profile["current_runtime_writer"] is None
    assert profile["current_runtime_path"] is None
    assert (
        profile["provider_owned_available"]
        is False
    )
    assert (
        profile["runtime_activation_allowed"]
        is False
    )
    assert not candidate.exists()
    assert not candidate.parent.exists()


def test_invalid_selection_mode_fails_closed() -> None:
    with pytest.raises(
        ValueError,
        match=(
            "provider_pricing_refresh_writer_"
            "selection_mode_not_supported"
        ),
    ):
        app._provider_pricing_refresh_writer_selection_profile(
            "deepseek",
            mode="dual_write",
        )


def test_deepseek_wrapper_delegates(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[dict[str, object]] = []

    def fake_profile(
        provider_id: str,
        *,
        mode: str | None = None,
        provider_path: str | Path | None = None,
    ) -> dict[str, object]:
        calls.append(
            {
                "provider_id": provider_id,
                "mode": mode,
                "provider_path": (
                    provider_path
                ),
            }
        )
        return {"provider": provider_id}

    monkeypatch.setattr(
        app,
        "_provider_pricing_refresh_writer_selection_profile",
        fake_profile,
    )

    path = tmp_path / "pricing.json"

    result = (
        app
        ._deepseek_pricing_refresh_writer_selection_profile(
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
            "mode": "provider_owned",
            "provider_path": path,
        }
    ]


def test_selection_profile_signatures_are_explicit() -> None:
    provider_signature = inspect.signature(
        app
        ._provider_pricing_refresh_writer_selection_profile
    )
    deepseek_signature = inspect.signature(
        app
        ._deepseek_pricing_refresh_writer_selection_profile
    )

    assert list(
        provider_signature.parameters
    ) == [
        "provider_id",
        "mode",
        "provider_path",
    ]
    assert list(
        deepseek_signature.parameters
    ) == [
        "mode",
        "provider_path",
    ]

    for name in (
        "mode",
        "provider_path",
    ):
        assert (
            provider_signature.parameters[
                name
            ].kind
            is inspect.Parameter.KEYWORD_ONLY
        )
        assert (
            deepseek_signature.parameters[
                name
            ].kind
            is inspect.Parameter.KEYWORD_ONLY
        )


def test_profile_explicitly_blocks_dual_and_fallback_writes() -> None:
    profile = (
        app
        ._deepseek_pricing_refresh_writer_selection_profile()
    )

    assert (
        profile["allowed_modes"]
        == [
            "legacy_shared",
            "provider_owned",
            "disabled",
        ]
    )
    assert (
        profile["dual_write_supported"]
        is False
    )
    assert (
        profile["fallback_write_supported"]
        is False
    )
    assert (
        profile["explicit_activation_required"]
        is True
    )


def test_existing_refresh_runtime_does_not_use_selection_profile() -> None:
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
            "_provider_pricing_refresh_"
            "writer_selection_profile"
            not in source
        )
        assert (
            "_deepseek_pricing_refresh_"
            "writer_selection_profile"
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
