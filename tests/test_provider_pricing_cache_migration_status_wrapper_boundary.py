from __future__ import annotations

import importlib
import inspect
import json
from pathlib import Path

import pytest


app = importlib.import_module(
    "codexchange_proxy.app"
)


def _write(
    path: Path,
    payload: object,
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    path.write_text(
        json.dumps(
            payload,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def _status(
    tmp_path: Path,
) -> tuple[Path, Path]:
    return (
        tmp_path / "legacy.json",
        tmp_path / "providers/deepseek.json",
    )


def test_none_state_is_read_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    legacy, provider = _status(
        tmp_path
    )
    monkeypatch.delenv(
        "COX_PRICING_PATH",
        raising=False,
    )

    result = (
        app
        ._provider_pricing_cache_migration_status(
            "deepseek",
            legacy_path=legacy,
            provider_path=provider,
        )
    )

    assert result["state"] == "none"
    assert (
        result[
            "automatic_migration_allowed"
        ]
        is False
    )
    assert (
        result["writes_files"]
        is False
    )
    assert not legacy.exists()
    assert not provider.exists()


def test_legacy_only_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    legacy, provider = _status(
        tmp_path
    )
    monkeypatch.delenv(
        "COX_PRICING_PATH",
        raising=False,
    )
    _write(
        legacy,
        {
            "__metadata__": {
                "source_kind": (
                    "official_docs_html"
                )
            },
            "model": {},
        },
    )
    before = legacy.read_bytes()

    result = (
        app
        ._provider_pricing_cache_migration_status(
            "deepseek",
            legacy_path=legacy,
            provider_path=provider,
        )
    )

    assert (
        result["state"]
        == "legacy_only"
    )
    assert (
        result[
            "legacy_identity_ambiguous"
        ]
        is True
    )
    assert (
        result["legacy"][
            "provider_identity_present"
        ]
        is False
    )
    assert legacy.read_bytes() == before
    assert not provider.exists()


def test_provider_only_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    legacy, provider = _status(
        tmp_path
    )
    monkeypatch.delenv(
        "COX_PRICING_PATH",
        raising=False,
    )
    _write(
        provider,
        {
            "__metadata__": {
                "provider": "deepseek",
                "cache_schema_owner": (
                    "deepseek"
                ),
            },
            "model": {},
        },
    )
    before = provider.read_bytes()

    result = (
        app
        ._provider_pricing_cache_migration_status(
            "deepseek",
            legacy_path=legacy,
            provider_path=provider,
        )
    )

    assert (
        result["state"]
        == "provider_only"
    )
    assert (
        result["provider_cache"][
            "provider_identity_present"
        ]
        is True
    )
    assert provider.read_bytes() == before
    assert not legacy.exists()


def test_both_identical_state_uses_raw_sha256(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    legacy, provider = _status(
        tmp_path
    )
    monkeypatch.delenv(
        "COX_PRICING_PATH",
        raising=False,
    )

    payload = {
        "__metadata__": {
            "source_kind": (
                "official_docs_html"
            )
        },
        "model": {
            "output": 1.0,
        },
    }
    _write(legacy, payload)
    provider.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    provider.write_bytes(
        legacy.read_bytes()
    )

    result = (
        app
        ._provider_pricing_cache_migration_status(
            "deepseek",
            legacy_path=legacy,
            provider_path=provider,
        )
    )

    assert (
        result["state"]
        == "both_identical"
    )
    assert (
        result["content_identical"]
        is True
    )
    assert result["conflict"] is False
    assert (
        result["comparison"]
        == "sha256_raw_bytes"
    )


def test_semantically_equal_but_byte_different_is_conflict(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    legacy, provider = _status(
        tmp_path
    )
    monkeypatch.delenv(
        "COX_PRICING_PATH",
        raising=False,
    )

    legacy.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    provider.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    legacy.write_text(
        '{"model":{"output":1}}\n',
        encoding="utf-8",
    )
    provider.write_text(
        '{\n  "model": {\n'
        '    "output": 1\n'
        '  }\n}\n',
        encoding="utf-8",
    )

    result = (
        app
        ._provider_pricing_cache_migration_status(
            "deepseek",
            legacy_path=legacy,
            provider_path=provider,
        )
    )

    assert (
        result["state"]
        == "both_conflict"
    )
    assert result["conflict"] is True
    assert (
        result["content_identical"]
        is False
    )


def test_explicit_pricing_path_takes_decision_precedence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    legacy, provider = _status(
        tmp_path
    )
    explicit = (
        tmp_path / "external.json"
    )

    _write(legacy, {"legacy": True})
    _write(provider, {"provider": True})

    monkeypatch.setenv(
        "COX_PRICING_PATH",
        str(explicit),
    )

    result = (
        app
        ._provider_pricing_cache_migration_status(
            "deepseek",
            legacy_path=legacy,
            provider_path=provider,
        )
    )

    assert (
        result["state"]
        == "explicit_pricing_path"
    )
    assert (
        result[
            "explicit_pricing_path"
        ]
        == str(explicit)
    )
    assert (
        result[
            "explicit_pricing_path_exists"
        ]
        is False
    )
    assert result["conflict"] is False


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
    with pytest.raises(
        ValueError,
        match=(
            "provider_pricing_cache_"
            "migration_not_supported"
        ),
    ):
        app._provider_pricing_cache_migration_status(
            provider_id,
            legacy_path=(
                tmp_path / "legacy.json"
            ),
            provider_path=(
                tmp_path / "provider.json"
            ),
        )


def test_deepseek_wrapper_delegates(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[dict[str, object]] = []
    sentinel = {
        "state": "legacy_only",
    }

    def fake_status(
        provider_id: str,
        *,
        provider_path: str | Path,
        legacy_path: (
            str | Path | None
        ) = None,
    ) -> dict[str, object]:
        calls.append(
            {
                "provider_id": (
                    provider_id
                ),
                "provider_path": (
                    provider_path
                ),
                "legacy_path": (
                    legacy_path
                ),
            }
        )
        return sentinel

    monkeypatch.setattr(
        app,
        "_provider_pricing_cache_migration_status",
        fake_status,
    )

    provider = (
        tmp_path / "provider.json"
    )
    legacy = (
        tmp_path / "legacy.json"
    )

    result = (
        app
        ._deepseek_pricing_cache_migration_status(
            provider_path=provider,
            legacy_path=legacy,
        )
    )

    assert result is sentinel
    assert calls == [
        {
            "provider_id": "deepseek",
            "provider_path": provider,
            "legacy_path": legacy,
        }
    ]


def test_function_signatures_are_explicit() -> None:
    assert list(
        inspect.signature(
            app._pricing_cache_file_snapshot
        ).parameters
    ) == ["path"]

    migration_parameters = (
        inspect.signature(
            app
            ._provider_pricing_cache_migration_status
        ).parameters
    )

    assert list(
        migration_parameters
    ) == [
        "provider_id",
        "provider_path",
        "legacy_path",
    ]
    assert (
        migration_parameters[
            "provider_path"
        ].kind
        is inspect.Parameter.KEYWORD_ONLY
    )


def test_existing_runtime_paths_do_not_call_classifier() -> None:
    for function in (
        app._pricing_config_path,
        app._pricing_source_info,
        app._pricing_daily_refresh_contract,
        app._load_model_pricing_usd_per_1m,
        app._write_pricing_cache_atomic,
        app._refresh_provider_pricing_from_official_docs,
        app._pricing_context_for_usage_event,
        app._weclaw_pricing_contract,
    ):
        source = inspect.getsource(
            function
        )

        assert (
            "_provider_pricing_cache_"
            "migration_status("
            not in source
        )
        assert (
            "_deepseek_pricing_cache_"
            "migration_status("
            not in source
        )


def test_classifier_reports_no_mutating_capabilities(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    legacy, provider = _status(
        tmp_path
    )
    monkeypatch.delenv(
        "COX_PRICING_PATH",
        raising=False,
    )

    result = (
        app
        ._provider_pricing_cache_migration_status(
            "deepseek",
            legacy_path=legacy,
            provider_path=provider,
        )
    )

    for key in (
        "automatic_migration_allowed",
        "migration_execution_safe",
        "copies_files",
        "moves_files",
        "deletes_files",
        "writes_files",
        "switches_reader",
        "switches_writer",
        "changes_config_precedence",
    ):
        assert result[key] is False
