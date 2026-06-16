from __future__ import annotations

import ast
import importlib
import inspect
import json
import textwrap
from pathlib import Path

import pytest


app = importlib.import_module(
    "codexchange_proxy.app"
)


IDENTITY = {
    "provider": "deepseek",
    "adapter_provider_id": "deepseek",
    "family": "deepseek",
    "cache_scope": "provider_scoped",
    "cache_schema_owner": "deepseek",
    "cache_is_provider_scoped": True,
}


def _normalize_writer(
    function: object,
    *,
    provider_owned: bool,
) -> str:
    source = textwrap.dedent(
        inspect.getsource(function)
    )
    tree = ast.parse(source)
    node = tree.body[0]

    assert isinstance(
        node,
        ast.FunctionDef,
    )

    if (
        node.body
        and isinstance(
            node.body[0],
            ast.Expr,
        )
        and isinstance(
            node.body[0].value,
            ast.Constant,
        )
        and isinstance(
            node.body[0].value.value,
            str,
        )
    ):
        node.body = node.body[1:]

    node.name = (
        "_write_pricing_cache_atomic"
    )

    if provider_owned:
        names = [
            argument.arg
            for argument
            in node.args.kwonlyargs
        ]
        index = names.index(
            "provider_id"
        )
        node.args.kwonlyargs.pop(index)
        node.args.kw_defaults.pop(index)

        class Transformer(
            ast.NodeTransformer
        ):
            def visit_Call(
                self,
                call: ast.Call,
            ) -> ast.AST:
                call = self.generic_visit(
                    call
                )

                if (
                    isinstance(
                        call.func,
                        ast.Name,
                    )
                    and call.func.id
                    == (
                        "_build_provider_owned_"
                        "pricing_cache_metadata"
                    )
                ):
                    call.func.id = (
                        "_build_deepseek_"
                        "pricing_cache_metadata"
                    )

                    assert (
                        isinstance(
                            call.args[0],
                            ast.Name,
                        )
                        and call.args[0].id
                        == "provider_id"
                    )
                    call.args.pop(0)

                return call

        Transformer().visit(node)

    ast.fix_missing_locations(node)

    return ast.dump(
        node,
        include_attributes=False,
    )


def test_provider_owned_writer_preserves_legacy_atomic_body() -> None:
    assert _normalize_writer(
        app._write_provider_pricing_cache_atomic,
        provider_owned=True,
    ) == _normalize_writer(
        app._write_pricing_cache_atomic,
        provider_owned=False,
    )


def test_provider_owned_metadata_contains_identity() -> None:
    metadata = (
        app
        ._build_provider_owned_pricing_cache_metadata(
            "deepseek",
            source_url=(
                "https://example.invalid/pricing"
            ),
            fetched_at=(
                "2026-06-16T00:00:00Z"
            ),
            ttl_seconds=86400,
        )
    )

    for key, value in IDENTITY.items():
        assert metadata[key] == value

    assert metadata["currency"] == "CNY"
    assert (
        metadata["source_kind"]
        == "official_docs_html"
    )


def test_provider_owned_writer_uses_explicit_path(
    tmp_path: Path,
) -> None:
    target = (
        tmp_path
        / "providers"
        / "deepseek"
        / "pricing.json"
    )
    prices = {
        "probe-model": {
            "input_cache_hit": 1.0,
            "input_cache_miss": 2.0,
            "output": 3.0,
        }
    }

    result = (
        app
        ._write_provider_pricing_cache_atomic(
            prices,
            provider_id="deepseek",
            path=target,
            source_url=(
                "https://example.invalid/pricing"
            ),
            fetched_at=(
                "2026-06-16T00:00:00Z"
            ),
            ttl_seconds=86400,
        )
    )

    assert result is None
    assert target.is_file()

    payload = json.loads(
        target.read_text(
            encoding="utf-8"
        )
    )

    assert (
        payload["probe-model"]
        == prices["probe-model"]
    )

    for key, value in IDENTITY.items():
        assert (
            payload["__metadata__"][key]
            == value
        )

    remaining = [
        path
        for path in target.parent.iterdir()
        if path != target
    ]
    assert remaining == []


def test_legacy_writer_remains_identity_free(
    tmp_path: Path,
) -> None:
    target = tmp_path / "legacy.json"

    app._write_pricing_cache_atomic(
        {
            "probe": {
                "output": 1.0,
            }
        },
        path=target,
        source_url=(
            "https://example.invalid/pricing"
        ),
        fetched_at=(
            "2026-06-16T00:00:00Z"
        ),
        ttl_seconds=86400,
    )

    metadata = json.loads(
        target.read_text(
            encoding="utf-8"
        )
    )["__metadata__"]

    for key in IDENTITY:
        assert key not in metadata


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
def test_unsupported_provider_is_rejected_before_write(
    provider_id: str,
    tmp_path: Path,
) -> None:
    target = tmp_path / "pricing.json"

    with pytest.raises(
        ValueError,
        match=(
            "provider_owned_pricing_cache_"
            "writer_not_supported"
        ),
    ):
        app._write_provider_pricing_cache_atomic(
            {},
            provider_id=provider_id,
            path=target,
            source_url=(
                "https://example.invalid/pricing"
            ),
            fetched_at=(
                "2026-06-16T00:00:00Z"
            ),
            ttl_seconds=86400,
        )

    assert not target.exists()


def test_deepseek_provider_writer_delegates(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[
        dict[str, object]
    ] = []

    def fake_writer(
        prices: dict[str, object],
        *,
        provider_id: str,
        path: Path,
        source_url: str,
        fetched_at: str,
        ttl_seconds: int,
    ) -> None:
        calls.append(
            {
                "prices": prices,
                "provider_id": provider_id,
                "path": path,
                "source_url": source_url,
                "fetched_at": fetched_at,
                "ttl_seconds": ttl_seconds,
            }
        )

    monkeypatch.setattr(
        app,
        "_write_provider_pricing_cache_atomic",
        fake_writer,
    )

    prices = {"probe": {}}
    path = tmp_path / "deepseek.json"

    result = (
        app
        ._write_deepseek_provider_pricing_cache_atomic(
            prices,
            path=path,
            source_url="source",
            fetched_at="timestamp",
            ttl_seconds=123,
        )
    )

    assert result is None
    assert calls == [
        {
            "prices": prices,
            "provider_id": "deepseek",
            "path": path,
            "source_url": "source",
            "fetched_at": "timestamp",
            "ttl_seconds": 123,
        }
    ]


def test_provider_writer_signature_requires_explicit_inputs() -> None:
    signature = inspect.signature(
        app._write_provider_pricing_cache_atomic
    )
    parameters = signature.parameters

    assert list(parameters) == [
        "prices",
        "provider_id",
        "path",
        "source_url",
        "fetched_at",
        "ttl_seconds",
    ]

    for name in (
        "provider_id",
        "path",
        "source_url",
        "fetched_at",
        "ttl_seconds",
    ):
        assert (
            parameters[name].kind
            is inspect.Parameter.KEYWORD_ONLY
        )
        assert (
            parameters[name].default
            is inspect.Parameter.empty
        )


def test_provider_writer_does_not_call_legacy_writer() -> None:
    source = inspect.getsource(
        app._write_provider_pricing_cache_atomic
    )

    assert (
        "_write_pricing_cache_atomic("
        not in source
    )
    assert (
        "_build_provider_owned_"
        "pricing_cache_metadata("
        in source
    )


def test_existing_runtime_paths_do_not_call_new_writer() -> None:
    for function in (
        app._pricing_daily_refresh_contract,
        app._refresh_provider_pricing_from_official_docs,
        app._refresh_deepseek_pricing_from_official_docs,
        app._load_model_pricing_usd_per_1m,
        app._pricing_context_for_usage_event,
        app._weclaw_pricing_contract,
    ):
        source = inspect.getsource(
            function
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
