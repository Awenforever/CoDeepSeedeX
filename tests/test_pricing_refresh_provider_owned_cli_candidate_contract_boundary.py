from __future__ import annotations

import importlib
import inspect
from pathlib import Path

import pytest


cli = importlib.import_module(
    "codexchange_proxy.cli"
)


def test_legacy_candidate_preserves_existing_cache_path_semantics(
    tmp_path: Path,
) -> None:
    legacy_path = (
        tmp_path
        / "legacy"
        / "pricing.json"
    )

    result = (
        cli
        ._pricing_refresh_provider_owned_cli_candidate_contract(
            "deepseek",
            write_cache=True,
            cache_path=str(legacy_path),
            provider_owned=False,
            provider_cache_path=None,
        )
    )

    assert result["status"] == "ok"
    assert (
        result["candidate_contract_valid"]
        is True
    )
    assert (
        result["candidate_requested"]
        is False
    )
    assert (
        result["selected_mode"]
        == "legacy_shared"
    )
    assert (
        result["dispatch_target"]
        == (
            "_refresh_provider_pricing_"
            "from_official_docs"
        )
    )
    assert (
        result["legacy_cache_path"]
        == str(legacy_path)
    )
    assert result["argument_mapping"] is None
    assert (
        result[
            "legacy_cache_path_semantics_unchanged"
        ]
        is True
    )
    assert result["parser_registered"] is False
    assert result["dispatch_wired"] is False
    assert result["execution_called"] is False
    assert not legacy_path.exists()
    assert not legacy_path.parent.exists()


def test_valid_provider_owned_candidate_maps_explicit_arguments_only(
    tmp_path: Path,
) -> None:
    provider_path = (
        tmp_path
        / "providers"
        / "deepseek"
        / "pricing.json"
    )

    result = (
        cli
        ._pricing_refresh_provider_owned_cli_candidate_contract(
            "deepseek",
            write_cache=True,
            cache_path=None,
            provider_owned=True,
            provider_cache_path=str(
                provider_path
            ),
        )
    )

    assert result["status"] == "ok"
    assert (
        result["candidate_contract_valid"]
        is True
    )
    assert (
        result["candidate_requested"]
        is True
    )
    assert (
        result["selected_mode"]
        == "provider_owned"
    )
    assert (
        result["dispatch_target"]
        == (
            "_provider_pricing_refresh_writer_"
            "single_write_execution"
        )
    )
    assert result["argument_mapping"] == {
        "activate": True,
        "mode": "provider_owned",
        "provider_path": str(
            provider_path
        ),
    }
    assert (
        result["candidate_source"]
        == "explicit_cli_arguments_only"
    )
    assert result["path_inference"] is False
    assert result["environment_lookup"] is False
    assert result["dual_write"] is False
    assert result["fallback_write"] is False
    assert result["parser_registered"] is False
    assert result["dispatch_wired"] is False
    assert result["execution_called"] is False
    assert result["writes_files"] is False
    assert (
        result["creates_directories"]
        is False
    )
    assert not provider_path.exists()
    assert not provider_path.parent.exists()


@pytest.mark.parametrize(
    (
        "provider_id",
        "write_cache",
        "cache_path",
        "provider_owned",
        "provider_cache_path",
        "reason",
    ),
    [
        (
            "deepseek",
            True,
            None,
            False,
            "provider.json",
            (
                "provider_cache_path_requires_"
                "provider_owned"
            ),
        ),
        (
            "deepseek",
            False,
            None,
            True,
            "provider.json",
            (
                "provider_owned_requires_"
                "write_cache"
            ),
        ),
        (
            "deepseek",
            True,
            "legacy.json",
            True,
            "provider.json",
            (
                "provider_owned_rejects_"
                "legacy_cache_path"
            ),
        ),
        (
            "deepseek",
            True,
            None,
            True,
            None,
            (
                "provider_owned_requires_"
                "provider_cache_path"
            ),
        ),
        (
            "qwen-singapore",
            True,
            None,
            True,
            "provider.json",
            (
                "provider_owned_cli_candidate_"
                "initially_deepseek_only"
            ),
        ),
        (
            "kimi",
            True,
            None,
            True,
            "provider.json",
            (
                "provider_owned_cli_candidate_"
                "initially_deepseek_only"
            ),
        ),
    ],
)
def test_invalid_candidate_combinations_fail_without_side_effects(
    tmp_path: Path,
    provider_id: str,
    write_cache: bool,
    cache_path: str | None,
    provider_owned: bool,
    provider_cache_path: str | None,
    reason: str,
) -> None:
    legacy = (
        tmp_path / cache_path
        if cache_path
        else None
    )
    provider = (
        tmp_path / provider_cache_path
        if provider_cache_path
        else None
    )

    result = (
        cli
        ._pricing_refresh_provider_owned_cli_candidate_contract(
            provider_id,
            write_cache=write_cache,
            cache_path=(
                str(legacy)
                if legacy is not None
                else None
            ),
            provider_owned=provider_owned,
            provider_cache_path=(
                str(provider)
                if provider is not None
                else None
            ),
        )
    )

    assert result["status"] == "error"
    assert result["available"] is False
    assert result["reason"] == reason
    assert (
        result["candidate_contract_valid"]
        is False
    )
    assert result["dispatch_target"] is None
    assert result["argument_mapping"] is None
    assert result["parser_registered"] is False
    assert result["dispatch_wired"] is False
    assert result["execution_called"] is False
    assert result["writes_files"] is False

    if legacy is not None:
        assert not legacy.exists()

    if provider is not None:
        assert not provider.exists()


def test_candidate_contract_signature_requires_all_cli_inputs() -> None:
    signature = inspect.signature(
        cli
        ._pricing_refresh_provider_owned_cli_candidate_contract
    )

    assert list(
        signature.parameters
    ) == [
        "provider_id",
        "write_cache",
        "cache_path",
        "provider_owned",
        "provider_cache_path",
    ]

    for name in (
        "write_cache",
        "cache_path",
        "provider_owned",
        "provider_cache_path",
    ):
        parameter = (
            signature.parameters[name]
        )
        assert (
            parameter.kind
            is inspect.Parameter.KEYWORD_ONLY
        )
        assert (
            parameter.default
            is inspect.Parameter.empty
        )


def test_candidate_contract_is_not_registered_or_dispatched() -> None:
    candidate_name = (
        "_pricing_refresh_provider_owned_"
        "cli_candidate_contract"
    )
    pricing_source = inspect.getsource(
        cli._pricing
    )
    parser_source = inspect.getsource(
        cli.build_parser
    )
    candidate_source = inspect.getsource(
        cli
        ._pricing_refresh_provider_owned_cli_candidate_contract
    )

    assert candidate_name not in pricing_source
    assert candidate_name not in parser_source

    for option in (
        "--provider-owned",
        "--provider-cache-path",
    ):
        assert option not in parser_source

    for execution_name in (
        "_provider_pricing_refresh_writer_"
        "single_write_execution",
        "_deepseek_pricing_refresh_writer_"
        "single_write_execution",
    ):
        assert execution_name not in pricing_source
        assert (
            f"{execution_name}("
            not in candidate_source
        )

    assert "os.environ" not in candidate_source
    assert "os.getenv" not in candidate_source
    assert ".mkdir(" not in candidate_source
    assert ".write_text(" not in candidate_source
    assert ".write_bytes(" not in candidate_source
    assert "open(" not in candidate_source


def test_current_parser_still_rejects_unregistered_candidate_flags() -> None:
    parser = cli.build_parser()

    with pytest.raises(SystemExit) as exc:
        parser.parse_args(
            [
                "pricing",
                "refresh",
                "--provider-owned",
            ]
        )

    assert exc.value.code == 2

    with pytest.raises(SystemExit) as exc:
        parser.parse_args(
            [
                "pricing",
                "refresh",
                "--provider-cache-path",
                "provider.json",
            ]
        )

    assert exc.value.code == 2


def test_candidate_environment_variables_remain_absent() -> None:
    source = Path(
        cli.__file__
    ).read_text(
        encoding="utf-8",
    )

    for name in (
        "COX_PRICING_PROVIDER_OWNED",
        "COX_PRICING_PROVIDER_CACHE_PATH",
        "COX_PRICING_REFRESH_WRITER_MODE",
        "COX_PRICING_REFRESH_WRITER_PATH",
    ):
        assert name not in source
