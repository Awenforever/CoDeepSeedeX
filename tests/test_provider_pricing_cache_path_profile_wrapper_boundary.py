from __future__ import annotations

import importlib
import inspect
import json
from pathlib import Path

import pytest


app = importlib.import_module(
    "codexchange_proxy.app"
)


def test_deepseek_path_profile_matches_legacy_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(
        "COX_PRICING_CACHE_PATH",
        raising=False,
    )
    monkeypatch.setenv(
        "HOME",
        str(tmp_path),
    )

    legacy = app._pricing_cache_path()
    profile = (
        app
        ._provider_pricing_cache_path_profile(
            "deepseek"
        )
    )

    assert legacy == (
        tmp_path
        / ".cache"
        / "codexchange"
        / "pricing.json"
    )
    assert profile == {
        "provider": "deepseek",
        "adapter_provider_id": "deepseek",
        "family": "deepseek",
        "supported": True,
        "pricing_supported": True,
        "capability": "pricing_cache_path",
        "cache_scope": "legacy_shared",
        "cache_schema_owner": "deepseek",
        "cache_is_provider_scoped": False,
        "legacy_compatibility_active": True,
        "override_env": (
            "COX_PRICING_CACHE_PATH"
        ),
        "path": str(legacy),
        "legacy_shared_path": str(legacy),
        "reason": None,
        "action": None,
    }

    assert (
        app._provider_pricing_cache_path(
            "deepseek"
        )
        == legacy
    )
    assert (
        app._deepseek_pricing_cache_path()
        == legacy
    )


def test_deepseek_path_profile_preserves_env_override(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "HOME",
        str(tmp_path),
    )
    monkeypatch.setenv(
        "COX_PRICING_CACHE_PATH",
        "~/custom/pricing.json",
    )

    expected = (
        tmp_path
        / "custom"
        / "pricing.json"
    )

    assert app._pricing_cache_path() == expected
    assert (
        app._provider_pricing_cache_path(
            "deepseek"
        )
        == expected
    )
    assert (
        app
        ._provider_pricing_cache_path_profile(
            "deepseek"
        )["path"]
        == str(expected)
    )


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
def test_unsupported_provider_path_profile_is_neutral(
    provider_id: str,
) -> None:
    profile = (
        app
        ._provider_pricing_cache_path_profile(
            provider_id
        )
    )

    assert profile["provider"] == (
        provider_id
    )
    assert profile["supported"] is False
    assert (
        profile["pricing_supported"]
        is False
    )
    assert profile["cache_scope"] is None
    assert (
        profile["cache_schema_owner"]
        is None
    )
    assert (
        profile[
            "cache_is_provider_scoped"
        ]
        is False
    )
    assert (
        profile[
            "legacy_compatibility_active"
        ]
        is False
    )
    assert profile["override_env"] is None
    assert profile["path"] is None
    assert (
        profile["legacy_shared_path"]
        is None
    )
    assert (
        "deepseek"
        not in json.dumps(
            profile,
            ensure_ascii=False,
        ).lower()
    )

    with pytest.raises(
        ValueError,
        match=(
            "provider_pricing_cache_path_"
            "not_supported"
        ),
    ):
        app._provider_pricing_cache_path(
            provider_id
        )


def test_deepseek_path_wrapper_delegates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel = Path(
        "/tmp/deepseek-pricing-sentinel.json"
    )
    calls: list[str] = []

    def fake_provider_path(
        provider_id: str,
    ) -> Path:
        calls.append(provider_id)
        return sentinel

    monkeypatch.setattr(
        app,
        "_provider_pricing_cache_path",
        fake_provider_path,
    )

    assert (
        app._deepseek_pricing_cache_path()
        == sentinel
    )
    assert calls == ["deepseek"]


def test_legacy_path_signatures_remain_unchanged() -> None:
    assert list(
        inspect.signature(
            app._pricing_cache_path
        ).parameters
    ) == []

    assert list(
        inspect.signature(
            app._pricing_config_path
        ).parameters
    ) == []

    assert list(
        inspect.signature(
            app._provider_pricing_cache_path
        ).parameters
    ) == ["provider_id"]


def test_config_path_precedence_is_unchanged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    external = (
        tmp_path / "external.json"
    )
    cache = tmp_path / "cache.json"
    project = tmp_path / "project.json"

    monkeypatch.setattr(
        app,
        "_pricing_cache_path",
        lambda: cache,
    )
    monkeypatch.setattr(
        app,
        "_pricing_project_config_path",
        lambda: project,
    )

    cache.write_text(
        "{}\n",
        encoding="utf-8",
    )
    project.write_text(
        "{}\n",
        encoding="utf-8",
    )

    monkeypatch.setenv(
        "COX_PRICING_PATH",
        str(external),
    )
    assert (
        app._pricing_config_path()
        == external
    )

    monkeypatch.delenv(
        "COX_PRICING_PATH",
        raising=False,
    )
    assert (
        app._pricing_config_path()
        == cache
    )

    cache.unlink()
    assert (
        app._pricing_config_path()
        == project
    )


def test_existing_runtime_callers_still_use_legacy_paths() -> None:
    for function in (
        app._pricing_config_path,
        app._pricing_source_info,
        app._pricing_daily_refresh_contract,
        app._load_model_pricing_usd_per_1m,
        app._pricing_context_for_usage_event,
        app._weclaw_pricing_contract,
        app._refresh_provider_pricing_from_official_docs,
    ):
        source = inspect.getsource(
            function
        )

        assert (
            "_provider_pricing_cache_path("
            not in source
        )
        assert (
            "_deepseek_pricing_cache_path("
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
