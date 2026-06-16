from __future__ import annotations

import contextlib
import importlib
import inspect
import io
import json
from pathlib import Path
from typing import Any

import pytest


cli = importlib.import_module(
    "codexchange_proxy.cli"
)


def _run_pricing(
    arguments: list[str],
) -> tuple[int, dict[str, Any]]:
    parser = cli.build_parser()
    args = parser.parse_args(
        [
            "pricing",
            "refresh",
            *arguments,
        ]
    )
    stdout = io.StringIO()

    with contextlib.redirect_stdout(
        stdout
    ):
        rc = cli._pricing(args)

    return rc, json.loads(
        stdout.getvalue()
    )


def test_cli_imports_existing_single_write_execution_seam() -> None:
    assert hasattr(
        cli,
        (
            "_provider_pricing_refresh_writer_"
            "single_write_execution"
        ),
    )

    pricing_source = inspect.getsource(
        cli._pricing
    )
    parser_source = inspect.getsource(
        cli.build_parser
    )

    assert (
        "_pricing_refresh_provider_owned_"
        "cli_candidate_contract"
        in pricing_source
    )
    assert (
        "_provider_pricing_refresh_writer_"
        "single_write_execution"
        in pricing_source
    )
    assert "validation only" not in parser_source
    assert "single write target" in parser_source


def test_legacy_refresh_dispatch_is_unchanged(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    legacy_path = (
        tmp_path
        / "legacy"
        / "pricing.json"
    )
    legacy_calls: list[
        dict[str, object]
    ] = []
    candidate_calls: list[
        dict[str, object]
    ] = []
    execution_calls: list[
        dict[str, object]
    ] = []

    original_candidate = (
        cli
        ._pricing_refresh_provider_owned_cli_candidate_contract
    )

    def capture_candidate(
        provider_id: str,
        **kwargs: object,
    ) -> dict[str, object]:
        candidate_calls.append(
            {
                "provider_id": provider_id,
                **kwargs,
            }
        )
        return original_candidate(
            provider_id,
            **kwargs,
        )

    def fake_legacy(
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
            "available": True,
            "writes_cache": True,
            "cache_path": str(
                kwargs.get("cache_path")
            ),
        }

    def forbidden_execution(
        provider_id: str,
        **kwargs: object,
    ) -> dict[str, object]:
        execution_calls.append(
            {
                "provider_id": provider_id,
                **kwargs,
            }
        )
        raise AssertionError(
            "provider_execution_called"
        )

    monkeypatch.setattr(
        cli,
        "_pricing_refresh_provider_owned_cli_candidate_contract",
        capture_candidate,
    )
    monkeypatch.setattr(
        cli,
        "_refresh_provider_pricing_from_official_docs",
        fake_legacy,
    )
    monkeypatch.setattr(
        cli,
        (
            "_provider_pricing_refresh_writer_"
            "single_write_execution"
        ),
        forbidden_execution,
    )

    rc, payload = _run_pricing(
        [
            "--provider",
            "deepseek",
            "--write-cache",
            "--cache-path",
            str(legacy_path),
            "--json",
        ]
    )

    assert rc == 0
    assert payload["status"] == "ok"
    assert len(legacy_calls) == 1
    assert candidate_calls == []
    assert execution_calls == []
    assert (
        legacy_calls[0]["cache_path"]
        == str(legacy_path)
    )


def test_valid_candidate_executes_once_and_normalizes_cli_metadata(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    provider_path = (
        tmp_path
        / "providers"
        / "deepseek"
        / "pricing.json"
    )
    execution_calls: list[
        dict[str, object]
    ] = []
    legacy_calls: list[
        dict[str, object]
    ] = []

    def fake_execution(
        provider_id: str,
        **kwargs: object,
    ) -> dict[str, object]:
        execution_calls.append(
            {
                "provider_id": provider_id,
                **kwargs,
            }
        )
        return {
            "status": "ok",
            "available": True,
            "writes_cache": True,
            "cache_path": str(
                kwargs["provider_path"]
            ),
            "execution": {
                "execution_seam": (
                    "function_level_unwired"
                ),
                "existing_cli_modified": False,
                "execution_attempted": True,
                "execution_allowed": True,
                "target_count": 1,
                "target_path": str(
                    kwargs["provider_path"]
                ),
                "writer": (
                    "_write_deepseek_provider_"
                    "pricing_cache_atomic"
                ),
                "legacy_writer_called": False,
                "legacy_path_written": False,
                "dual_write": False,
                "fallback_write": False,
            },
        }

    def forbidden_legacy(
        provider_id: str,
        **kwargs: object,
    ) -> dict[str, object]:
        legacy_calls.append(
            {
                "provider_id": provider_id,
                **kwargs,
            }
        )
        raise AssertionError(
            "legacy_refresh_called"
        )

    monkeypatch.setattr(
        cli,
        (
            "_provider_pricing_refresh_writer_"
            "single_write_execution"
        ),
        fake_execution,
    )
    monkeypatch.setattr(
        cli,
        "_refresh_provider_pricing_from_official_docs",
        forbidden_legacy,
    )

    rc, payload = _run_pricing(
        [
            "--provider",
            "deepseek",
            "--model",
            "deepseek-v4-pro",
            "--source-url",
            "https://example.invalid/pricing",
            "--timeout",
            "3.5",
            "--write-cache",
            "--provider-owned",
            "--provider-cache-path",
            str(provider_path),
            "--json",
        ]
    )

    assert rc == 0
    assert payload["status"] == "ok"
    assert len(execution_calls) == 1
    assert legacy_calls == []

    assert execution_calls[0] == {
        "provider_id": "deepseek",
        "activate": True,
        "mode": "provider_owned",
        "provider_path": str(
            provider_path
        ),
        "model": "deepseek-v4-pro",
        "source_url": (
            "https://example.invalid/pricing"
        ),
        "timeout": 3.5,
    }

    assert (
        payload["execution"][
            "execution_seam"
        ]
        == (
            "cli_explicit_provider_owned_"
            "dispatch"
        )
    )
    assert (
        payload["execution"][
            "existing_cli_modified"
        ]
        is True
    )
    assert (
        payload["execution"][
            "target_count"
        ]
        == 1
    )
    assert (
        payload["execution"][
            "legacy_writer_called"
        ]
        is False
    )
    assert (
        payload["execution"][
            "dual_write"
        ]
        is False
    )
    assert (
        payload["execution"][
            "fallback_write"
        ]
        is False
    )

    candidate = payload["cli_candidate"]
    assert candidate["status"] == "ok"
    assert (
        candidate["candidate_contract_valid"]
        is True
    )
    assert (
        candidate["argument_mapping"]
        == {
            "activate": True,
            "mode": "provider_owned",
            "provider_path": str(
                provider_path
            ),
        }
    )
    assert candidate["parser_registered"] is True
    assert candidate["dispatch_wired"] is True
    assert candidate["execution_called"] is False

    cli_execution = payload[
        "cli_execution"
    ]
    assert (
        cli_execution[
            "provider_execution_dispatch_wired"
        ]
        is True
    )
    assert (
        cli_execution[
            "execution_called"
        ]
        is True
    )
    assert (
        cli_execution[
            "candidate_validation_only"
        ]
        is False
    )
    assert (
        cli_execution[
            "activation_source"
        ]
        == "explicit_cli_arguments_only"
    )
    assert (
        cli_execution[
            "environment_activation"
        ]
        is False
    )
    assert (
        cli_execution["path_inference"]
        is False
    )
    assert cli_execution["dual_write"] is False
    assert (
        cli_execution["fallback_write"]
        is False
    )


@pytest.mark.parametrize(
    (
        "arguments",
        "reason",
    ),
    [
        (
            [
                "--provider",
                "deepseek",
                "--write-cache",
                "--provider-cache-path",
                "provider.json",
            ],
            (
                "provider_cache_path_requires_"
                "provider_owned"
            ),
        ),
        (
            [
                "--provider",
                "deepseek",
                "--provider-owned",
                "--provider-cache-path",
                "provider.json",
            ],
            (
                "provider_owned_requires_"
                "write_cache"
            ),
        ),
        (
            [
                "--provider",
                "deepseek",
                "--write-cache",
                "--cache-path",
                "legacy.json",
                "--provider-owned",
                "--provider-cache-path",
                "provider.json",
            ],
            (
                "provider_owned_rejects_"
                "legacy_cache_path"
            ),
        ),
        (
            [
                "--provider",
                "deepseek",
                "--write-cache",
                "--provider-owned",
            ],
            (
                "provider_owned_requires_"
                "provider_cache_path"
            ),
        ),
        (
            [
                "--provider",
                "qwen-singapore",
                "--write-cache",
                "--provider-owned",
                "--provider-cache-path",
                "provider.json",
            ],
            (
                "provider_owned_cli_candidate_"
                "initially_deepseek_only"
            ),
        ),
    ],
)
def test_invalid_candidate_never_calls_execution(
    monkeypatch: pytest.MonkeyPatch,
    arguments: list[str],
    reason: str,
) -> None:
    execution_calls: list[
        dict[str, object]
    ] = []
    legacy_calls: list[
        dict[str, object]
    ] = []

    def forbidden_execution(
        provider_id: str,
        **kwargs: object,
    ) -> dict[str, object]:
        execution_calls.append(
            {
                "provider_id": provider_id,
                **kwargs,
            }
        )
        raise AssertionError(
            "execution_called"
        )

    def forbidden_legacy(
        provider_id: str,
        **kwargs: object,
    ) -> dict[str, object]:
        legacy_calls.append(
            {
                "provider_id": provider_id,
                **kwargs,
            }
        )
        raise AssertionError(
            "legacy_refresh_called"
        )

    monkeypatch.setattr(
        cli,
        (
            "_provider_pricing_refresh_writer_"
            "single_write_execution"
        ),
        forbidden_execution,
    )
    monkeypatch.setattr(
        cli,
        "_refresh_provider_pricing_from_official_docs",
        forbidden_legacy,
    )

    rc, payload = _run_pricing(
        arguments
    )

    assert rc == 1
    assert payload["status"] == "error"
    assert payload["reason"] == reason
    assert payload["execution_called"] is False
    assert (
        payload[
            "cli_execution_dispatch_wired"
        ]
        is False
    )
    assert execution_calls == []
    assert legacy_calls == []


def test_execution_error_returns_one_without_legacy_fallback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    provider_path = (
        tmp_path
        / "providers"
        / "deepseek"
        / "pricing.json"
    )
    execution_calls: list[
        dict[str, object]
    ] = []
    legacy_calls: list[
        dict[str, object]
    ] = []

    def fake_execution(
        provider_id: str,
        **kwargs: object,
    ) -> dict[str, object]:
        execution_calls.append(
            {
                "provider_id": provider_id,
                **kwargs,
            }
        )
        return {
            "status": "error",
            "available": False,
            "reason": (
                "probe_provider_refresh_error"
            ),
            "writes_cache": False,
            "old_cache_preserved": True,
            "execution": {
                "execution_attempted": True,
                "execution_allowed": True,
                "target_count": 1,
                "target_path": str(
                    kwargs["provider_path"]
                ),
                "legacy_writer_called": False,
                "legacy_path_written": False,
                "dual_write": False,
                "fallback_write": False,
                "execution_seam": (
                    "function_level_unwired"
                ),
                "existing_cli_modified": False,
            },
        }

    def forbidden_legacy(
        provider_id: str,
        **kwargs: object,
    ) -> dict[str, object]:
        legacy_calls.append(
            {
                "provider_id": provider_id,
                **kwargs,
            }
        )
        raise AssertionError(
            "legacy_refresh_called"
        )

    monkeypatch.setattr(
        cli,
        (
            "_provider_pricing_refresh_writer_"
            "single_write_execution"
        ),
        fake_execution,
    )
    monkeypatch.setattr(
        cli,
        "_refresh_provider_pricing_from_official_docs",
        forbidden_legacy,
    )

    rc, payload = _run_pricing(
        [
            "--provider",
            "deepseek",
            "--write-cache",
            "--provider-owned",
            "--provider-cache-path",
            str(provider_path),
            "--json",
        ]
    )

    assert rc == 1
    assert (
        payload["reason"]
        == "probe_provider_refresh_error"
    )
    assert payload["writes_cache"] is False
    assert len(execution_calls) == 1
    assert legacy_calls == []
    assert (
        payload["execution"][
            "fallback_write"
        ]
        is False
    )
    assert (
        payload["execution"][
            "legacy_writer_called"
        ]
        is False
    )
    assert (
        payload["execution"][
            "execution_seam"
        ]
        == (
            "cli_explicit_provider_owned_"
            "dispatch"
        )
    )
    assert (
        payload["execution"][
            "existing_cli_modified"
        ]
        is True
    )


def test_cli_execution_dispatch_does_not_read_activation_environment() -> None:
    pricing_source = inspect.getsource(
        cli._pricing
    )
    candidate_source = inspect.getsource(
        cli
        ._pricing_refresh_provider_owned_cli_candidate_contract
    )

    for name in (
        "COX_PRICING_PROVIDER_OWNED",
        "COX_PRICING_PROVIDER_CACHE_PATH",
        "COX_PRICING_REFRESH_WRITER_MODE",
        "COX_PRICING_REFRESH_WRITER_PATH",
    ):
        assert name not in pricing_source
        assert name not in candidate_source

    assert "os.environ" not in pricing_source
    assert "os.getenv" not in pricing_source
