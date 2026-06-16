from __future__ import annotations

import contextlib
import importlib
import inspect
import io
import json
from pathlib import Path
from typing import Any

import pytest


app = importlib.import_module(
    "codexchange_proxy.app"
)
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

    payload = json.loads(
        stdout.getvalue()
    )
    return rc, payload


def test_help_exposes_validation_only_candidate_flags() -> None:
    parser_source = inspect.getsource(
        cli.build_parser
    )
    pricing_source = inspect.getsource(
        cli._pricing
    )

    assert "--provider-owned" in parser_source
    assert "--provider-cache-path" in parser_source
    assert (
        "_pricing_refresh_provider_owned_"
        "cli_candidate_contract"
        in pricing_source
    )
    assert (
        "_provider_pricing_refresh_writer_"
        "single_write_execution"
        not in pricing_source
    )
    assert (
        "_deepseek_pricing_refresh_writer_"
        "single_write_execution"
        not in pricing_source
    )


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
    assert (
        legacy_calls[0]["cache_path"]
        == str(legacy_path)
    )


@pytest.mark.parametrize(
    "json_output",
    [False, True],
)
def test_valid_candidate_is_validation_only_dispatched(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    json_output: bool,
) -> None:
    provider_path = (
        tmp_path
        / "providers"
        / "deepseek"
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

    def fake_execution(
        *args: object,
        **kwargs: object,
    ) -> dict[str, object]:
        execution_calls.append(
            {
                "args": args,
                "kwargs": kwargs,
            }
        )
        raise AssertionError(
            "execution_seam_called"
        )

    monkeypatch.setattr(
        cli,
        "_pricing_refresh_provider_owned_cli_candidate_contract",
        capture_candidate,
    )
    monkeypatch.setattr(
        cli,
        "_refresh_provider_pricing_from_official_docs",
        forbidden_legacy,
    )
    monkeypatch.setattr(
        app,
        "_provider_pricing_refresh_writer_single_write_execution",
        fake_execution,
    )
    monkeypatch.setattr(
        app,
        "_deepseek_pricing_refresh_writer_single_write_execution",
        fake_execution,
    )

    arguments = [
        "--provider",
        "deepseek",
        "--write-cache",
        "--provider-owned",
        "--provider-cache-path",
        str(provider_path),
    ]

    if json_output:
        arguments.append("--json")

    rc, payload = _run_pricing(
        arguments
    )

    assert rc == 0
    assert payload["status"] == "ok"
    assert (
        payload["selected_mode"]
        == "provider_owned"
    )
    assert (
        payload["candidate_contract_valid"]
        is True
    )
    assert payload["parser_registered"] is True
    assert payload["dispatch_wired"] is True
    assert payload["execution_called"] is False
    assert (
        payload[
            "cli_candidate_validation_only"
        ]
        is True
    )
    assert payload["runtime_active"] is False
    assert (
        payload[
            "runtime_activation_allowed"
        ]
        is False
    )
    assert payload["argument_mapping"] == {
        "activate": True,
        "mode": "provider_owned",
        "provider_path": str(
            provider_path
        ),
    }
    assert "execution remains disabled" in str(
        payload["action"]
    )
    assert len(candidate_calls) == 1
    assert legacy_calls == []
    assert execution_calls == []
    assert not provider_path.exists()
    assert not provider_path.parent.exists()


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
def test_invalid_candidate_requests_return_validation_errors_without_execution(
    monkeypatch: pytest.MonkeyPatch,
    arguments: list[str],
    reason: str,
) -> None:
    legacy_calls: list[
        dict[str, object]
    ] = []
    execution_calls: list[
        dict[str, object]
    ] = []

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

    def fake_execution(
        *args: object,
        **kwargs: object,
    ) -> dict[str, object]:
        execution_calls.append(
            {
                "args": args,
                "kwargs": kwargs,
            }
        )
        raise AssertionError(
            "execution_seam_called"
        )

    monkeypatch.setattr(
        cli,
        "_refresh_provider_pricing_from_official_docs",
        forbidden_legacy,
    )
    monkeypatch.setattr(
        app,
        "_provider_pricing_refresh_writer_single_write_execution",
        fake_execution,
    )
    monkeypatch.setattr(
        app,
        "_deepseek_pricing_refresh_writer_single_write_execution",
        fake_execution,
    )

    rc, payload = _run_pricing(
        arguments
    )

    assert rc == 1
    assert payload["status"] == "error"
    assert payload["reason"] == reason
    assert payload["parser_registered"] is True
    assert payload["dispatch_wired"] is True
    assert payload["execution_called"] is False
    assert (
        payload[
            "cli_candidate_validation_only"
        ]
        is True
    )
    assert payload["runtime_active"] is False
    assert (
        payload[
            "runtime_activation_allowed"
        ]
        is False
    )
    assert legacy_calls == []
    assert execution_calls == []


def test_candidate_dispatch_does_not_read_activation_environment() -> None:
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
