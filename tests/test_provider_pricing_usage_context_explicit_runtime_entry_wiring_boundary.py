from __future__ import annotations

import ast
import importlib
import inspect
import json
from pathlib import Path

import pytest

app = importlib.import_module(
    "codexchange_proxy.app"
)

CONTEXT_KEYS = {
    "pricing_model",
    "pricing_currency",
    "pricing_unit",
    "pricing_source",
    "pricing_source_kind",
    "pricing_updated_at",
    "pricing_source_url",
    "pricing_input_cache_hit",
    "pricing_input_cache_miss",
    "pricing_output",
}


def _legacy_document() -> dict[str, object]:
    return {
        "__metadata__": {
            "source_kind": (
                "bundled_official_docs_snapshot"
            ),
            "source_url": (
                "https://example.invalid/legacy"
            ),
            "snapshot_created_at": (
                "2026-06-01T00:00:00Z"
            ),
            "currency": "CNY",
            "unit": "per_million_tokens",
        },
        "deepseek-v4-pro": {
            "input_cache_hit": 0.07,
            "input_cache_miss": 0.28,
            "output": 0.42,
        },
    }


def _forbidden_legacy() -> object:
    raise AssertionError(
        "explicit provider-owned usage context "
        "called a legacy pricing source"
    )


def test_default_model_only_call_preserves_legacy_context(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    legacy = tmp_path / "legacy.json"
    legacy.write_text(
        json.dumps(_legacy_document()),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        app,
        "_pricing_config_path",
        lambda: legacy,
    )
    monkeypatch.setattr(
        app,
        "_pricing_source_info",
        lambda path: {
            "source": "legacy_probe",
            "source_kind": (
                "bundled_official_docs_snapshot"
            ),
            "path": path,
            "fallback_used": False,
        },
    )

    def forbidden_execution(
        *args: object,
        **kwargs: object,
    ) -> object:
        raise AssertionError(
            "default usage context activated "
            "provider-owned reader"
        )

    monkeypatch.setattr(
        app,
        (
            "_provider_pricing_reader_"
            "single_source_execution"
        ),
        forbidden_execution,
    )

    result = (
        app._pricing_context_for_usage_event(
            "deepseek-v4-pro"
        )
    )

    assert set(result) == CONTEXT_KEYS
    assert result == {
        "pricing_model": "deepseek-v4-pro",
        "pricing_currency": "CNY",
        "pricing_unit": "per_million_tokens",
        "pricing_source": "legacy_probe",
        "pricing_source_kind": (
            "bundled_official_docs_snapshot"
        ),
        "pricing_updated_at": (
            "2026-06-01T00:00:00Z"
        ),
        "pricing_source_url": (
            "https://example.invalid/legacy"
        ),
        "pricing_input_cache_hit": 0.07,
        "pricing_input_cache_miss": 0.28,
        "pricing_output": 0.42,
    }


def test_provider_writer_reader_usage_context_round_trip(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    target = (
        tmp_path
        / "providers"
        / "deepseek"
        / "pricing.json"
    )
    fetched_at = "2026-06-17T00:00:00Z"
    source_url = (
        "https://example.invalid/provider-pricing"
    )

    app._write_provider_pricing_cache_atomic(
        {
            "deepseek-v4-pro": {
                "input_cache_hit": 0.11,
                "input_cache_miss": 0.22,
                "output": 0.33,
            }
        },
        provider_id="deepseek",
        path=target,
        source_url=source_url,
        fetched_at=fetched_at,
        ttl_seconds=86400,
    )

    stored = json.loads(
        target.read_text(
            encoding="utf-8"
        )
    )

    assert "__metadata__" in stored
    assert "__pricing_metadata__" not in stored

    for name in (
        "_pricing_config_path",
        "_pricing_metadata_from_path",
        "_pricing_source_info",
        "_load_model_pricing_usd_per_1m",
    ):
        monkeypatch.setattr(
            app,
            name,
            _forbidden_legacy,
        )

    result = (
        app._pricing_context_for_usage_event(
            "deepseek-v4-pro",
            provider_id="deepseek",
            activate=True,
            mode="provider-owned",
            provider_path=target,
        )
    )

    assert set(result) == CONTEXT_KEYS
    assert result == {
        "pricing_model": "deepseek-v4-pro",
        "pricing_currency": "CNY",
        "pricing_unit": "per_million_tokens",
        "pricing_source": (
            "provider_owned_explicit_path"
        ),
        "pricing_source_kind": (
            "official_docs_html"
        ),
        "pricing_updated_at": fetched_at,
        "pricing_source_url": source_url,
        "pricing_input_cache_hit": 0.11,
        "pricing_input_cache_miss": 0.22,
        "pricing_output": 0.33,
    }


def test_reader_execution_extracts_canonical_writer_metadata(
    tmp_path: Path,
) -> None:
    target = tmp_path / "pricing.json"

    app._write_provider_pricing_cache_atomic(
        {
            "deepseek-v4-pro": {
                "input_cache_hit": 1.0,
                "input_cache_miss": 2.0,
                "output": 3.0,
            }
        },
        provider_id="deepseek",
        path=target,
        source_url="https://example.invalid/source",
        fetched_at="2026-06-17T01:02:03Z",
        ttl_seconds=3600,
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
    assert result["metadata"]["provider"] == (
        "deepseek"
    )
    assert result["metadata"]["cache_scope"] == (
        "provider_scoped"
    )
    assert (
        result["metadata"][
            "cache_is_provider_scoped"
        ]
        is True
    )
    assert result["metadata"]["currency"] == "CNY"
    assert result["metadata"]["source_kind"] == (
        "official_docs_html"
    )
    assert result["metadata"]["fetched_at"] == (
        "2026-06-17T01:02:03Z"
    )


def test_canonical_metadata_overrides_compatibility_alias(
    tmp_path: Path,
) -> None:
    target = tmp_path / "pricing.json"
    target.write_text(
        json.dumps(
            {
                "__pricing_metadata__": {
                    "currency": "USD",
                    "source_kind": "compatibility",
                },
                "__metadata__": {
                    "currency": "CNY",
                    "source_kind": (
                        "official_docs_html"
                    ),
                },
                "deepseek-v4-pro": {
                    "input_cache_hit": 1.0,
                    "input_cache_miss": 2.0,
                    "output": 3.0,
                },
            }
        ),
        encoding="utf-8",
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
    assert result["metadata"]["currency"] == "CNY"
    assert result["metadata"]["source_kind"] == (
        "official_docs_html"
    )


def test_missing_provider_source_never_falls_back(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    target = tmp_path / "missing.json"

    for name in (
        "_pricing_config_path",
        "_pricing_metadata_from_path",
        "_pricing_source_info",
        "_load_model_pricing_usd_per_1m",
    ):
        monkeypatch.setattr(
            app,
            name,
            _forbidden_legacy,
        )

    result = (
        app._pricing_context_for_usage_event(
            "deepseek-v4-pro",
            provider_id="deepseek",
            activate=True,
            mode="provider_owned",
            provider_path=target,
        )
    )

    assert set(result) == CONTEXT_KEYS
    assert result["pricing_source"] == (
        "provider_owned_explicit_path"
    )
    assert result["pricing_source_kind"] is None
    assert result["pricing_input_cache_hit"] == 0.0
    assert result["pricing_input_cache_miss"] == 0.0
    assert result["pricing_output"] == 0.0
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

    for name in (
        "_pricing_config_path",
        "_pricing_metadata_from_path",
        "_pricing_source_info",
        "_load_model_pricing_usd_per_1m",
    ):
        monkeypatch.setattr(
            app,
            name,
            _forbidden_legacy,
        )

    result = (
        app._pricing_context_for_usage_event(
            "deepseek-v4-pro",
            provider_id="deepseek",
            activate=True,
            mode="provider_owned",
            provider_path=target,
        )
    )

    assert set(result) == CONTEXT_KEYS
    assert result["pricing_source"] == (
        "provider_owned_explicit_path"
    )
    assert result["pricing_input_cache_hit"] == 0.0
    assert result["pricing_input_cache_miss"] == 0.0
    assert result["pricing_output"] == 0.0


def test_disabled_explicit_usage_context_reads_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden_read(
        *args: object,
        **kwargs: object,
    ) -> object:
        raise AssertionError(
            "disabled usage pricing read a file"
        )

    monkeypatch.setattr(
        Path,
        "read_text",
        forbidden_read,
    )

    result = (
        app._pricing_context_for_usage_event(
            "deepseek-v4-pro",
            provider_id="deepseek",
            activate=True,
            mode="disabled",
        )
    )

    assert set(result) == CONTEXT_KEYS
    assert result["pricing_source"] == (
        "provider_owned_reader_disabled"
    )
    assert result["pricing_source_kind"] == (
        "disabled"
    )
    assert result["pricing_source_url"] is None
    assert result["pricing_output"] == 0.0


@pytest.mark.parametrize(
    "kwargs",
    [
        {"provider_id": "deepseek"},
        {"activate": True},
        {"mode": "legacy_shared"},
        {
            "provider_path": Path(
                "/explicit/provider.json"
            )
        },
    ],
)
def test_incomplete_or_legacy_explicit_request_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    kwargs: dict[str, object],
) -> None:
    def forbidden_execution(
        *args: object,
        **call_kwargs: object,
    ) -> object:
        raise AssertionError(
            "invalid explicit usage request "
            "called reader execution"
        )

    monkeypatch.setattr(
        app,
        (
            "_provider_pricing_reader_"
            "single_source_execution"
        ),
        forbidden_execution,
    )

    result = (
        app._pricing_context_for_usage_event(
            "deepseek-v4-pro",
            **kwargs,
        )
    )

    assert set(result) == CONTEXT_KEYS
    assert result["pricing_source"] is None
    assert result["pricing_source_kind"] is None
    assert result["pricing_output"] == 0.0


def test_unknown_provider_fails_before_read(
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
        app._pricing_context_for_usage_event(
            "claude-probe",
            provider_id="anthropic",
            activate=True,
            mode="provider_owned",
            provider_path=target,
        )

    assert not target.exists()
    assert not target.parent.exists()


def test_environment_cannot_activate_provider_owned_usage(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    legacy = tmp_path / "legacy.json"
    legacy.write_text(
        json.dumps(_legacy_document()),
        encoding="utf-8",
    )

    monkeypatch.setenv(
        "COX_PRICING_READER_MODE",
        "provider_owned",
    )
    monkeypatch.setenv(
        "COX_PRICING_READER_PATH",
        str(tmp_path / "provider.json"),
    )
    monkeypatch.setattr(
        app,
        "_pricing_config_path",
        lambda: legacy,
    )
    monkeypatch.setattr(
        app,
        "_pricing_source_info",
        lambda path: {
            "source": "legacy_probe",
            "source_kind": (
                "bundled_official_docs_snapshot"
            ),
            "path": path,
            "fallback_used": False,
        },
    )

    def forbidden_execution(
        *args: object,
        **kwargs: object,
    ) -> object:
        raise AssertionError(
            "environment activated provider-owned "
            "usage pricing"
        )

    monkeypatch.setattr(
        app,
        (
            "_provider_pricing_reader_"
            "single_source_execution"
        ),
        forbidden_execution,
    )

    result = (
        app._pricing_context_for_usage_event(
            "deepseek-v4-pro"
        )
    )

    assert result["pricing_source"] == (
        "legacy_probe"
    )
    assert result["pricing_output"] == 0.42


def test_usage_context_signature_and_source_boundary() -> None:
    signature = inspect.signature(
        app._pricing_context_for_usage_event
    )

    assert list(signature.parameters) == [
        "model",
        "provider_id",
        "activate",
        "mode",
        "provider_path",
    ]

    assert (
        signature.parameters["model"].kind
        is inspect.Parameter.POSITIONAL_OR_KEYWORD
    )

    for name in (
        "provider_id",
        "activate",
        "mode",
        "provider_path",
    ):
        assert (
            signature.parameters[name].kind
            is inspect.Parameter.KEYWORD_ONLY
        )

    source = inspect.getsource(
        app._pricing_context_for_usage_event
    )

    assert (
        "_provider_pricing_reader_"
        "single_source_execution("
        in source
    )
    assert "_pricing_config_path()" in source
    assert "_pricing_metadata_from_path(" in source
    assert "_pricing_source_info(" in source
    assert "_load_model_pricing_usd_per_1m()" in source

    for forbidden in (
        "_write_pricing_cache_atomic(",
        "_write_provider_pricing_cache_atomic(",
        "_pricing_daily_refresh_contract(",
        "_weclaw_pricing_contract(",
        "_estimate_cost_usd(",
    ):
        assert forbidden not in source

    for env_name in (
        "COX_PRICING_READER_MODE",
        "COX_PRICING_READER_PATH",
        "COX_PRICING_PROVIDER_OWNED",
        "COX_PRICING_PROVIDER_CACHE_PATH",
    ):
        assert env_name not in source


def _usage_call_contracts() -> list[
    dict[str, object]
]:
    text = inspect.getsource(app)
    tree = ast.parse(text)
    scopes: list[str] = []
    calls: list[dict[str, object]] = []

    class Visitor(ast.NodeVisitor):
        def visit_ClassDef(
            self,
            node: ast.ClassDef,
        ) -> None:
            scopes.append(node.name)

            for statement in node.body:
                self.visit(statement)

            scopes.pop()

        def visit_FunctionDef(
            self,
            node: ast.FunctionDef,
        ) -> None:
            scopes.append(node.name)

            for statement in node.body:
                self.visit(statement)

            scopes.pop()

        def visit_AsyncFunctionDef(
            self,
            node: ast.AsyncFunctionDef,
        ) -> None:
            scopes.append(node.name)

            for statement in node.body:
                self.visit(statement)

            scopes.pop()

        def visit_Call(
            self,
            node: ast.Call,
        ) -> None:
            name = ""

            if isinstance(node.func, ast.Name):
                name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                name = node.func.attr

            if (
                name
                == "_pricing_context_for_usage_event"
            ):
                calls.append(
                    {
                        "scope": ".".join(scopes),
                        "positional_count": len(
                            node.args
                        ),
                        "keywords": [
                            keyword.arg
                            for keyword in node.keywords
                            if keyword.arg is not None
                        ],
                    }
                )

            self.generic_visit(node)

    Visitor().visit(tree)

    return sorted(
        calls,
        key=lambda item: str(item["scope"]),
    )


def test_existing_production_callers_remain_positional_legacy_calls() -> None:
    assert _usage_call_contracts() == [
        {
            "scope": (
                "SQLiteResponseStore.record_usage"
            ),
            "positional_count": 1,
            "keywords": [],
        },
        {
            "scope": (
                "_chat_completions_with_usage"
            ),
            "positional_count": 1,
            "keywords": [],
        },
    ]


def test_cost_persistence_weclaw_daily_refresh_and_cli_remain_frozen() -> None:
    estimate_source = inspect.getsource(
        app._estimate_cost_usd
    )
    chat_source = inspect.getsource(
        app._chat_completions_with_usage
    )
    record_source = inspect.getsource(
        app.SQLiteResponseStore.record_usage
    )
    weclaw_source = inspect.getsource(
        app._weclaw_pricing_contract
    )
    daily_source = inspect.getsource(
        app._pricing_daily_refresh_contract
    )

    assert (
        "_load_model_pricing_usd_per_1m()"
        in estimate_source
    )
    assert (
        "_pricing_context_for_usage_event("
        "effective_model)"
        in chat_source
    )
    assert (
        "_pricing_context_for_usage_event("
        "normalized_effective_model)"
        in record_source
    )

    for source in (
        chat_source,
        record_source,
        estimate_source,
        weclaw_source,
        daily_source,
    ):
        assert (
            "_pricing_context_for_usage_event("
            "effective_model,"
            not in source
        )
        assert (
            "_pricing_context_for_usage_event("
            "normalized_effective_model,"
            not in source
        )

    for source in (
        weclaw_source,
        daily_source,
    ):
        assert (
            "_provider_pricing_reader_"
            "single_source_execution("
            not in source
        )
