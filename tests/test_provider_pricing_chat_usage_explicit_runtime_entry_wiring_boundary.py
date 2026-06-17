from __future__ import annotations

import ast
import importlib
import inspect
from pathlib import Path
from typing import Any

import pytest

app = importlib.import_module("codexchange_proxy.app")

PRICING_KEYWORDS = {
    "pricing_provider_id",
    "pricing_activate",
    "pricing_mode",
    "pricing_provider_path",
}


def _client_response() -> dict[str, Any]:
    return {
        "choices": [{"message": {"role": "assistant", "content": "ok"}}],
        "usage": {
            "prompt_tokens": 100,
            "completion_tokens": 2,
            "total_tokens": 102,
            "prompt_tokens_details": {"cached_tokens": 40},
        },
    }


class Client:
    last_context_trimming_report = None

    async def chat_completions(
        self,
        payload: dict[str, Any],
        trace_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        assert trace_metadata is not None
        return _client_response()


class Store:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def record_usage(self, **kwargs: Any) -> None:
        self.events.append(kwargs)


def test_chat_usage_signature_has_explicit_pricing_entry() -> None:
    signature = inspect.signature(app._chat_completions_with_usage)
    assert list(signature.parameters)[-4:] == [
        "pricing_provider_id",
        "pricing_activate",
        "pricing_mode",
        "pricing_provider_path",
    ]
    for name in PRICING_KEYWORDS:
        assert signature.parameters[name].kind is inspect.Parameter.KEYWORD_ONLY


def test_chat_usage_source_has_explicit_and_legacy_branches() -> None:
    source = inspect.getsource(app._chat_completions_with_usage)
    assert "explicit_pricing_runtime_entry = bool(" in source
    assert "_pricing_context_for_usage_event(effective_model)" in source
    for marker in (
        "provider_id=pricing_provider_id",
        "activate=pricing_activate",
        "mode=pricing_mode",
        "provider_path=pricing_provider_path",
    ):
        assert marker in source
    for forbidden in (
        "COX_PRICING_READER_MODE",
        "COX_PRICING_READER_PATH",
        "COX_PRICING_PROVIDER_OWNED",
        "COX_PRICING_PROVIDER_CACHE_PATH",
        "_pricing_daily_refresh_contract(",
        "_weclaw_pricing_contract(",
    ):
        assert forbidden not in source


@pytest.mark.asyncio
async def test_default_chat_usage_calls_legacy_context_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []
    context = {
        "pricing_model": "deepseek-v4-pro",
        "pricing_currency": "CNY",
        "pricing_unit": "per_million_tokens",
        "pricing_source": "legacy",
        "pricing_source_kind": "legacy_shared",
        "pricing_updated_at": None,
        "pricing_source_url": None,
        "pricing_input_cache_hit": 1.0,
        "pricing_input_cache_miss": 10.0,
        "pricing_output": 100.0,
    }

    def fake_context(model: str) -> dict[str, Any]:
        calls.append((model, {}))
        return context

    monkeypatch.setattr(app, "_pricing_context_for_usage_event", fake_context)
    store = Store()
    await app._chat_completions_with_usage(
        deepseek_client=Client(),
        store=store,
        payload={"model": "deepseek-v4-pro", "messages": []},
        purpose="primary",
        response_id="r1",
        previous_response_id=None,
        request_id="r1",
        requested_model="deepseek-v4-pro",
        thinking_enabled=False,
    )
    assert calls == [("deepseek-v4-pro", {})]
    assert store.events[0]["pricing_context"] is context


@pytest.mark.asyncio
async def test_explicit_provider_owned_chat_usage_round_trip(
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
        raise AssertionError("explicit chat usage touched legacy pricing")

    for name in (
        "_pricing_config_path",
        "_pricing_metadata_from_path",
        "_pricing_source_info",
        "_load_model_pricing_usd_per_1m",
    ):
        monkeypatch.setattr(app, name, forbidden)

    store = Store()
    await app._chat_completions_with_usage(
        deepseek_client=Client(),
        store=store,
        payload={"model": "deepseek-v4-pro", "messages": []},
        purpose="primary",
        response_id="r2",
        previous_response_id=None,
        request_id="r2",
        requested_model="deepseek-v4-pro",
        thinking_enabled=False,
        pricing_provider_id="deepseek",
        pricing_activate=True,
        pricing_mode="provider_owned",
        pricing_provider_path=target,
    )

    assert len(store.events) == 1
    event = store.events[0]
    context = event["pricing_context"]
    assert context["pricing_source"] == "provider_owned_explicit_path"
    assert context["pricing_source_kind"] == "official_docs_html"
    assert context["pricing_currency"] == "CNY"
    assert event["estimated_cost_source_amount"] == pytest.approx(0.00168)
    assert event["estimated_cost_source_currency"] == "CNY"
    assert event["estimated_cost_usd"] == 0.0


def test_five_production_callers_forward_explicit_pricing_entry() -> None:
    source = inspect.getsource(app)
    tree = ast.parse(source)
    scopes: list[str] = []
    calls: list[dict[str, Any]] = []

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
            name = node.func.id if isinstance(node.func, ast.Name) else node.func.attr if isinstance(node.func, ast.Attribute) else ""
            if name == "_chat_completions_with_usage":
                calls.append({
                    "scope": ".".join(scopes),
                    "keywords": [kw.arg for kw in node.keywords if kw.arg is not None],
                })
            self.generic_visit(node)

    Visitor().visit(tree)
    assert len(calls) == 5
    assert {call["scope"] for call in calls} == {
        "_compact_chat_history_for_codex_like_persistence",
        "_judge_agent_liveness_with_llm",
        "_run_chat_with_tool_bridge",
    }
    for call in calls:
        assert PRICING_KEYWORDS.issubset(call["keywords"])
