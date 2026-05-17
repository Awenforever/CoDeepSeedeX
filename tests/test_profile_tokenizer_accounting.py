from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from deepseek_responses_proxy.app import (
    DeepSeekClient,
    SQLiteResponseStore,
    _profile_tokenizer_report_for_messages,
    _weclaw_tokens_contract,
    create_app,
)


def test_profile_tokenizer_counts_prompt_subcategories_with_packaged_deepseek_tokenizer() -> None:
    report = _profile_tokenizer_report_for_messages(
        [
            {"role": "system", "content": "You are concise."},
            {"role": "user", "content": "Hello token accounting."},
            {"role": "assistant", "content": "Previous answer."},
            {"role": "tool", "content": "tool output text"},
            {
                "role": "user",
                "content": "[deepseek-proxy persistent compaction summary]\nolder context",
            },
        ],
        profile="deepseek",
        model="deepseek-v4-flash",
        provider="deepseek",
    )

    assert report["available"] is True
    assert report["tokenizer"]["tokenizer_kind"] == "deepseek_v3"
    assert Path(report["tokenizer"]["source"]).name == "tokenizer.json"
    split = report["prompt_subcategory_split"]
    assert split["available"] is True
    assert split["is_estimated"] is True
    assert split["precision"] == "local_profile_tokenizer_content_estimate"
    assert split["categories"]["user"]["tokens"] > 0
    assert split["categories"]["system"]["tokens"] > 0
    assert split["categories"]["assistant_history"]["tokens"] > 0
    assert split["categories"]["tool_output"]["tokens"] > 0
    assert split["categories"]["compaction_summary"]["tokens"] > 0
    assert split["total_tokens"] == report["summary"]["total_content_tokens"]


def test_weclaw_tokens_contract_exposes_profile_tokenizer_split_when_available(tmp_path) -> None:
    store = SQLiteResponseStore(tmp_path / "usage.sqlite3")
    store.record_usage(
        response_id="resp_1",
        previous_response_id=None,
        model="deepseek-v4-flash",
        thinking_enabled=False,
        usage_numbers={
            "prompt_tokens": 20,
            "completion_tokens": 5,
            "total_tokens": 25,
            "cached_tokens": 0,
            "reasoning_tokens": 0,
        },
        estimated_cost_usd=0.001,
        purpose="primary",
        call_index=0,
        request_id="req_1",
        requested_model="deepseek-v4-flash",
        effective_model="deepseek-v4-flash",
        upstream_model="deepseek-v4-flash",
    )
    report = _profile_tokenizer_report_for_messages(
        [{"role": "user", "content": "Hello from WeClaw."}],
        profile="deepseek",
        model="deepseek-v4-flash",
        provider="deepseek",
    )

    tokens = _weclaw_tokens_contract(store, profile="deepseek", profile_tokenizer_report=report)

    assert tokens["taxonomy"]["version"] == 4
    assert tokens["profile_tokenizer"]["available"] is True
    assert tokens["prompt_subcategory_split"]["available"] is True
    assert tokens["prompt_subcategory_split"]["categories"]["user"]["tokens"] > 0
    assert tokens["last_turn"]["summary"]["prompt_tokens"] == 20
    assert tokens["attribution"]["provider_usage_totals"]["precision"] == "exact_provider_reported"
    assert tokens["attribution"]["profile_tokenizer"]["billing_authoritative"] is False


@pytest.mark.asyncio
async def test_runtime_weclaw_status_includes_latest_profile_tokenizer_report(tmp_path, monkeypatch) -> None:
    codex_config = tmp_path / "codex.toml"
    codex_config.write_text(
        "[model_providers.deepseek-proxy]\n"
        "base_url = \"http://127.0.0.1:8000/v1\"\n\n"
        "[profiles.deepseek]\n"
        "model = \"deepseek-v4-flash\"\n"
        "model_provider = \"deepseek-proxy\"\n"
        "model_context_window = 1000000\n"
        "model_auto_compact_token_limit = 750000\n"
        "model_reasoning_effort = \"xhigh\"\n"
        "plan_mode_reasoning_effort = \"high\"\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("CODEX_CONFIG_FILE", str(codex_config))
    monkeypatch.setenv("DEEPSEEK_PROXY_MODEL", "deepseek-v4-flash")
    monkeypatch.setenv("DEEPSEEK_PROXY_FORCE_MODEL", "1")

    store = SQLiteResponseStore(tmp_path / "usage.sqlite3")
    app = create_app(deepseek_client=DeepSeekClient(), store=store)
    report = _profile_tokenizer_report_for_messages(
        [{"role": "user", "content": "Runtime status prompt."}],
        profile="deepseek",
        model="deepseek-v4-flash",
        provider="deepseek",
    )
    app.state.last_profile_tokenizer_report_by_profile["deepseek"] = report
    store.record_usage(
        response_id="resp_2",
        previous_response_id=None,
        model="deepseek-v4-flash",
        thinking_enabled=False,
        usage_numbers={
            "prompt_tokens": 30,
            "completion_tokens": 5,
            "total_tokens": 35,
            "cached_tokens": 0,
            "reasoning_tokens": 0,
        },
        estimated_cost_usd=0.001,
        purpose="primary",
        call_index=0,
        request_id="req_2",
        requested_model="deepseek-v4-flash",
        effective_model="deepseek-v4-flash",
        upstream_model="deepseek-v4-flash",
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/v1/proxy/weclaw/status?profile=deepseek&include_balance=false")

    assert response.status_code == 200
    data = response.json()
    assert data["tokens"]["profile_tokenizer"]["available"] is True
    assert data["tokens"]["prompt_subcategory_split"]["available"] is True
    assert data["tokens"]["last_turn"]["summary"]["prompt_tokens"] == 30
