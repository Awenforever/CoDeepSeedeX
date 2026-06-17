from __future__ import annotations

import ast
import importlib
import inspect
from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

app = importlib.import_module("codexchange_proxy.app")

PRICING_NAMES = [
    "pricing_provider_id",
    "pricing_activate",
    "pricing_mode",
    "pricing_provider_path",
]

WRAPPER_NAMES = (
    "_compact_chat_history_for_codex_like_persistence",
    "_judge_agent_liveness_with_llm",
    "_run_chat_with_tool_bridge",
)


class UsageClient:
    last_context_trimming_report = None

    async def chat_completions(
        self,
        payload: dict[str, Any],
        trace_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        assert trace_metadata is not None
        return {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "ok",
                    }
                }
            ],
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 2,
                "total_tokens": 102,
                "prompt_tokens_details": {
                    "cached_tokens": 40,
                },
            },
        }


def _function_node(
    tree: ast.Module,
    name: str,
) -> ast.FunctionDef | ast.AsyncFunctionDef:
    matches = [
        node
        for node in ast.walk(tree)
        if isinstance(
            node,
            (ast.FunctionDef, ast.AsyncFunctionDef),
        )
        and node.name == name
    ]
    assert len(matches) == 1
    return matches[0]


def _call_name(node: ast.Call) -> str:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return ""


def test_factory_and_three_wrappers_have_explicit_pricing_tail() -> None:
    for function in (
        app.create_app,
        app._compact_chat_history_for_codex_like_persistence,
        app._judge_agent_liveness_with_llm,
        app._run_chat_with_tool_bridge,
    ):
        signature = inspect.signature(function)
        assert list(signature.parameters)[-4:] == PRICING_NAMES
        for name in PRICING_NAMES:
            assert (
                signature.parameters[name].kind
                is inspect.Parameter.KEYWORD_ONLY
            )


def test_all_five_usage_calls_forward_same_explicit_entry() -> None:
    tree = ast.parse(inspect.getsource(app))
    calls: list[tuple[str, set[str]]] = []
    scopes: list[str] = []

    class Visitor(ast.NodeVisitor):
        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            scopes.append(node.name)
            self.generic_visit(node)
            scopes.pop()

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            scopes.append(node.name)
            self.generic_visit(node)
            scopes.pop()

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            scopes.append(node.name)
            self.generic_visit(node)
            scopes.pop()

        def visit_Call(self, node: ast.Call) -> None:
            if _call_name(node) == "_chat_completions_with_usage":
                calls.append(
                    (
                        ".".join(scopes),
                        {
                            keyword.arg
                            for keyword in node.keywords
                            if keyword.arg is not None
                        },
                    )
                )
            self.generic_visit(node)

    Visitor().visit(tree)
    assert len(calls) == 5
    assert {scope for scope, _keywords in calls} == set(WRAPPER_NAMES)
    for _scope, keywords in calls:
        assert set(PRICING_NAMES).issubset(keywords)


def test_factory_endpoint_forwards_entry_to_both_top_level_paths() -> None:
    source = inspect.getsource(app.create_app)
    tree = ast.parse(source)
    create_response = _function_node(tree, "create_response")

    calls = [
        node
        for node in ast.walk(create_response)
        if isinstance(node, ast.Call)
        and _call_name(node)
        in {
            "_compact_chat_history_for_codex_like_persistence",
            "_run_chat_with_tool_bridge",
        }
    ]
    assert len(calls) == 2
    for call in calls:
        keywords = {
            keyword.arg
            for keyword in call.keywords
            if keyword.arg is not None
        }
        assert set(PRICING_NAMES).issubset(keywords)


def test_no_environment_or_path_inference_in_propagation_functions() -> None:
    forbidden = (
        "COX_PRICING_READER_MODE",
        "COX_PRICING_READER_PATH",
        "COX_PRICING_PROVIDER_OWNED",
        "COX_PRICING_PROVIDER_CACHE_PATH",
        "_provider_pricing_cache_path(",
        "_provider_pricing_cache_path_profile(",
    )
    for function in (
        app.create_app,
        app._compact_chat_history_for_codex_like_persistence,
        app._judge_agent_liveness_with_llm,
        app._run_chat_with_tool_bridge,
    ):
        source = inspect.getsource(function)
        for marker in forbidden:
            assert marker not in source


@pytest.mark.asyncio
async def test_default_factory_keeps_legacy_usage_context_call(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []

    def fake_context(
        model: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        calls.append((model, kwargs))
        return {
            "pricing_model": model,
            "pricing_currency": "CNY",
            "pricing_unit": "per_million_tokens",
            "pricing_source": "legacy_test",
            "pricing_source_kind": "legacy_shared",
            "pricing_updated_at": None,
            "pricing_source_url": None,
            "pricing_input_cache_hit": 1.0,
            "pricing_input_cache_miss": 10.0,
            "pricing_output": 100.0,
        }

    monkeypatch.setattr(
        app,
        "_pricing_context_for_usage_event",
        fake_context,
    )
    monkeypatch.setenv("COX_TOOL_BRIDGE", "0")
    monkeypatch.setenv("COX_COMPACT_ENABLED", "0")

    store = app.SQLiteResponseStore(tmp_path / "legacy.sqlite3")
    application = app.create_app(
        deepseek_client=UsageClient(),
        store=store,
    )

    async with AsyncClient(
        transport=ASGITransport(app=application),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/v1/responses",
            json={
                "model": "deepseek-v4-pro",
                "input": "Reply exactly: ok",
            },
        )

    assert response.status_code == 200
    assert calls == [("deepseek-v4-pro", {})]
    events = store.usage_events()
    assert len(events) == 1
    assert events[0]["pricing_source_kind"] == "legacy_shared"


@pytest.mark.asyncio
async def test_explicit_factory_round_trip_uses_one_provider_owned_source(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    target = tmp_path / "providers" / "deepseek" / "pricing.json"
    app._write_provider_pricing_cache_atomic(
        {
            "deepseek-v4-pro": {
                "input_cache_hit": 2.0,
                "input_cache_miss": 20.0,
                "output": 200.0,
            }
        },
        provider_id="deepseek",
        path=target,
        source_url="https://example.invalid/provider-pricing",
        fetched_at="2026-06-17T00:00:00Z",
        ttl_seconds=86400,
    )

    def forbidden(*args: object, **kwargs: object) -> object:
        raise AssertionError(
            "explicit factory propagation touched legacy pricing"
        )

    for name in (
        "_pricing_config_path",
        "_pricing_metadata_from_path",
        "_pricing_source_info",
        "_load_model_pricing_usd_per_1m",
    ):
        monkeypatch.setattr(app, name, forbidden)

    monkeypatch.setenv("COX_TOOL_BRIDGE", "0")
    monkeypatch.setenv("COX_COMPACT_ENABLED", "0")

    store = app.SQLiteResponseStore(tmp_path / "provider.sqlite3")
    application = app.create_app(
        deepseek_client=UsageClient(),
        store=store,
        pricing_provider_id="deepseek",
        pricing_activate=True,
        pricing_mode="provider_owned",
        pricing_provider_path=target,
    )

    async with AsyncClient(
        transport=ASGITransport(app=application),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/v1/responses",
            json={
                "model": "deepseek-v4-pro",
                "input": "Reply exactly: ok",
            },
        )

    assert response.status_code == 200
    events = store.usage_events()
    assert len(events) == 1
    event = events[0]
    assert event["pricing_source_kind"] == "official_docs_html"
    assert event["pricing_currency"] == "CNY"
    assert event["estimated_cost_source_amount"] == pytest.approx(0.00168)
    assert event["estimated_cost_source_currency"] == "CNY"
    assert event["estimated_cost_usd"] == 0.0
