from __future__ import annotations

import json
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from deepseek_responses_proxy.app import DeepSeekClient, SQLiteResponseStore, create_app
from deepseek_responses_proxy import cli


class WeClawBalanceClient(DeepSeekClient):
    async def user_balance(self):
        return {
            "is_available": True,
            "balance_infos": [
                {
                    "currency": "USD",
                    "total_balance": "12.34",
                    "granted_balance": "1.00",
                    "topped_up_balance": "11.34",
                }
            ],
        }


def _write_codex_config(path: Path) -> None:
    path.write_text(
        "[model_providers.deepseek-thinking-proxy]\n"
        "base_url = \"http://127.0.0.1:8001/v1\"\n\n"
        "[profiles.deepseek-thinking]\n"
        "model = \"deepseek-v4-flash\"\n"
        "model_provider = \"deepseek-thinking-proxy\"\n"
        "model_context_window = 1000000\n"
        "model_auto_compact_token_limit = 750000\n"
        "model_reasoning_effort = \"xhigh\"\n"
        "plan_mode_reasoning_effort = \"high\"\n",
        encoding="utf-8",
    )


def _record_usage(
    store,
    *,
    response_id,
    request_id,
    created_at,
    purpose,
    call_index,
    prompt_tokens,
    completion_tokens,
    total_tokens,
    cached_tokens=0,
    reasoning_tokens=0,
    cost=0.0,
):
    store.record_usage(
        response_id=response_id,
        previous_response_id=None,
        model="deepseek-v4-flash",
        thinking_enabled=True,
        usage_numbers={
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "cached_tokens": cached_tokens,
            "reasoning_tokens": reasoning_tokens,
        },
        estimated_cost_usd=cost,
        purpose=purpose,
        call_index=call_index,
        request_id=request_id,
        requested_model="deepseek-v4-flash",
        effective_model="deepseek-v4-flash",
        upstream_model="deepseek-v4-flash",
    )
    with store._connect() as conn:
        conn.execute(
            "UPDATE usage_events SET created_at = ? WHERE response_id = ? AND purpose = ?",
            (created_at, response_id, purpose),
        )


@pytest.mark.asyncio
async def test_weclaw_http_status_exposes_usage_pricing_cost_auxiliary_and_balance(tmp_path, monkeypatch):
    codex_config = tmp_path / "codex.toml"
    _write_codex_config(codex_config)
    monkeypatch.setenv("CODEX_CONFIG_FILE", str(codex_config))
    monkeypatch.setenv("DEEPSEEK_PROXY_MODEL", "deepseek-v4-flash")
    monkeypatch.setenv("DEEPSEEK_PROXY_FORCE_MODEL", "1")

    store = SQLiteResponseStore(tmp_path / "usage.sqlite3")
    _record_usage(
        store,
        response_id="resp_old_primary",
        request_id="resp_old",
        created_at=100,
        purpose="primary",
        call_index=0,
        prompt_tokens=100,
        completion_tokens=10,
        total_tokens=110,
        cached_tokens=20,
        reasoning_tokens=0,
        cost=0.001,
    )
    _record_usage(
        store,
        response_id="resp_turn_primary",
        request_id="resp_turn",
        created_at=200,
        purpose="primary",
        call_index=0,
        prompt_tokens=1000,
        completion_tokens=100,
        total_tokens=1100,
        cached_tokens=200,
        reasoning_tokens=10,
        cost=0.01,
    )
    _record_usage(
        store,
        response_id="resp_turn_judge",
        request_id="resp_turn",
        created_at=201,
        purpose="liveness_judge",
        call_index=1,
        prompt_tokens=50,
        completion_tokens=5,
        total_tokens=55,
        cached_tokens=0,
        reasoning_tokens=0,
        cost=0.002,
    )
    _record_usage(
        store,
        response_id="resp_turn_tool_bridge",
        request_id="resp_turn",
        created_at=202,
        purpose="tool_bridge",
        call_index=2,
        prompt_tokens=300,
        completion_tokens=30,
        total_tokens=330,
        cached_tokens=20,
        reasoning_tokens=0,
        cost=0.003,
    )

    app = create_app(deepseek_client=WeClawBalanceClient(), store=store)
    app.state.last_context_compaction_report = {
        "version": "v0.3.9-alpha",
        "enabled": True,
        "compacted": False,
        "reason": "not_triggered_yet",
        "policy": "adaptive",
        "before_chars": 12345,
        "after_chars": 12345,
        "message_count_before": 5,
        "message_count_after": 5,
        "policy_decision": {
            "effective_trigger_chars": 900000,
            "effective_target_chars": 280000,
        },
        "observed_at": "2026-05-17T10:00:00Z",
        "source": "runtime_context_builder",
    }
    app.state.deepseek_client.last_context_trimming_report = {
        "version": "v0.3.9-alpha",
        "enabled": True,
        "trimmed": False,
        "reason": "not_triggered_yet",
        "max_context_chars": 1500000,
        "max_tool_output_chars": 60000,
        "keep_recent_messages": 24,
        "before_chars": 12345,
        "after_chars": 12345,
        "message_count_before": 5,
        "message_count_after": 5,
        "observed_at": "2026-05-17T10:00:00Z",
        "source": "live_request_payload",
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/v1/proxy/weclaw/status?profile=deepseek-thinking")

    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "ok"
    assert data["profile"] == "deepseek-thinking"

    context_window = data["context_window"]
    assert context_window["used_tokens_available"] is True
    assert context_window["used_tokens"] == 1000
    assert context_window["used_tokens_is_estimated"] is True
    assert context_window["used_tokens_source"] == "dsproxy_usage_ledger.latest_primary_turn.summary.prompt_tokens"
    assert context_window["latest_upstream_prompt_tokens"]["value"] == 1000
    assert context_window["latest_upstream_prompt_tokens"]["is_estimated_for_context_window"] is True
    assert context_window["remaining_tokens_estimate"] == 749000
    assert context_window["limit_explanation"]["display_limit_tokens"] == 750000
    assert context_window["limit_explanation"]["model_context_window_tokens"] == 1000000
    assert context_window["limit_explanation"]["auto_compact_token_limit"] == 750000

    guard = data["runtime_payload_guard"]
    assert guard["available"] is True
    assert guard["unit"] == "chars"
    assert guard["current_chars"] == 12345
    assert guard["current_chars_available"] is True
    assert guard["current_chars_source"] == "live_request_payload"
    assert guard["current_chars_precision"] == "exact"
    assert guard["compaction"]["available"] is True
    assert guard["compaction"]["trigger_chars"] == 900000
    assert guard["compaction"]["target_chars"] == 280000
    assert guard["compaction"]["current_chars"] == 12345
    assert guard["compaction"]["usage_ratio"] == guard["compaction"]["progress_ratio"]
    assert guard["compaction"]["capacity_progress_ratio"] == pytest.approx(12345 / 900000)
    assert guard["compaction"]["remaining_chars"] == 887655
    assert guard["compaction"]["status"] == "not_triggered"
    assert guard["compaction"]["last_report"]["exists"] is True
    assert guard["trimming"]["available"] is True
    assert guard["trimming"]["max_context_chars"] == 1500000
    assert guard["trimming"]["current_chars"] == 12345
    assert guard["trimming"]["usage_ratio"] == guard["trimming"]["progress_ratio"]
    assert guard["trimming"]["capacity_progress_ratio"] == pytest.approx(12345 / 1500000)
    assert guard["trimming"]["remaining_chars"] == 1487655
    assert guard["trimming"]["status"] == "not_triggered"
    assert guard["trimming"]["last_report"]["exists"] is True
    assert data["context_window"]["runtime"]["payload_guard"]["current_chars"] == 12345
    assert data["compaction"]["runtime_payload_guard"]["current_chars"] == 12345

    last_turn = data["tokens"]["last_turn"]
    assert last_turn["available"] is True
    assert last_turn["unit"] == "tokens"
    assert last_turn["request_id"] == "resp_turn"
    assert last_turn["summary"]["model_call_count"] == 1
    assert last_turn["summary"]["prompt_tokens"] == 1000
    assert last_turn["summary"]["completion_tokens"] == 100
    assert last_turn["summary"]["total_tokens"] == 1100
    assert last_turn["summary"]["cached_tokens"] == 200
    assert last_turn["summary"]["reasoning_tokens"] == 10
    assert set(last_turn["by_purpose"]) == {"primary"}
    assert last_turn["by_purpose"]["primary"]["prompt_tokens"] == 1000

    latest_primary = data["tokens"]["latest_primary_turn"]
    assert latest_primary["request_id"] == "resp_turn"
    assert latest_primary["summary"]["prompt_tokens"] == 1000

    latest_any = data["tokens"]["latest_any_model_call"]
    assert latest_any["available"] is True
    assert latest_any["unit"] == "tokens"
    assert latest_any["request_id"] == "resp_turn"
    assert latest_any["summary"]["model_call_count"] == 3
    assert latest_any["summary"]["prompt_tokens"] == 1350
    assert latest_any["summary"]["completion_tokens"] == 135
    assert latest_any["summary"]["total_tokens"] == 1485
    assert latest_any["summary"]["cached_tokens"] == 220
    assert latest_any["summary"]["reasoning_tokens"] == 10
    assert latest_any["by_purpose"]["primary"]["prompt_tokens"] == 1000
    assert latest_any["by_purpose"]["tool_bridge"]["prompt_tokens"] == 300
    assert latest_any["by_purpose"]["liveness_judge"]["prompt_tokens"] == 50

    session_total = data["tokens"]["session_total"]
    assert session_total["available"] is True
    assert session_total["summary"]["model_call_count"] == 4
    assert session_total["summary"]["prompt_tokens"] == 1450
    assert session_total["summary"]["estimated_cost_usd"] == pytest.approx(0.016)

    auxiliary = data["tokens"]["auxiliary_model_calls"]
    assert auxiliary["available"] is True
    assert auxiliary["included_in_session_total"] is True
    assert auxiliary["summary"]["model_call_count"] == 2
    assert auxiliary["summary"]["prompt_tokens"] == 350
    assert set(auxiliary["by_purpose"]) == {"liveness_judge", "tool_bridge"}

    assert data["pricing"]["available"] is True
    assert data["pricing"]["model"] == "deepseek-v4-flash"
    assert data["pricing"]["source_currency"] in {"CNY", "USD"}
    assert data["pricing"]["display_currency"] in {"CNY", "USD"}
    assert data["pricing"]["unit"] == "per_million_tokens"
    assert data["pricing"]["prices"]["input_cache_miss"] > 0
    assert data["pricing"]["official_reference_url"] == "https://api-docs.deepseek.com/zh-cn/quick_start/pricing/"
    assert data["pricing"]["source_trust"] in {"bundled_official_docs_snapshot", "official_docs_html_cache", "external_config"}
    assert data["pricing"]["pricing_source_state"]["must_display_source_label"] is True

    assert data["cost"]["available"] is False
    assert data["cost"]["scope"] == "unavailable"
    assert data["cost"]["session"]["available"] is False
    assert data["cost"]["session"]["scope"] == "current_session"
    assert data["cost"]["is_estimated"] is True
    assert data["cost"]["last_turn_estimated_cost"] == pytest.approx(0.01)
    assert data["cost"]["session_estimated_cost"] is None
    assert data["cost"]["total_estimated_cost"] is None
    assert data["cost"]["auxiliary_estimated_cost"] == pytest.approx(0.005)
    assert data["cost"]["profile_route_estimated_cost"] == pytest.approx(0.016)
    assert data["cost"]["cash_estimated_cost"] == pytest.approx(0.016)
    assert data["cost"]["cash_definition"] == "current_session_estimated_cost_when_session_id_available_else_profile_route_history"
    assert data["cost"]["source_currency"] in {"CNY", "USD", "mixed"}
    assert data["cost"]["display_currency"] in {"CNY", "USD"}
    assert data["cost"]["ledger_precision"] == "per_turn_model_pricing"
    assert data["cost"]["turn_ledger"]["session_cost_recomputed_from_current_model"] is False
    assert data["cost"]["reasoning_cost_available"] is False
    assert data["cost"]["pricing_source_kind"]
    assert data["cost"]["pricing_source_url"] == "https://api-docs.deepseek.com/zh-cn/quick_start/pricing/"

    assert data["balance"]["available"] is True
    assert data["balance"]["provider"] == "deepseek"
    assert data["balance"]["balance"]["balance_infos"][0]["total_balance"] == "12.34"
    assert data["balance"]["currency"] == "USD"
    assert data["balance"]["amount"] == pytest.approx(12.34)
    assert data["balance"]["display"] == "12.34 USD"
    assert data["cost"]["balance"]["available"] is True


@pytest.mark.asyncio
async def test_weclaw_http_status_uses_app_state_store_and_client_for_runtime_contract(tmp_path, monkeypatch):
    codex_config = tmp_path / "codex.toml"
    _write_codex_config(codex_config)
    monkeypatch.setenv("CODEX_CONFIG_FILE", str(codex_config))
    monkeypatch.setenv("DEEPSEEK_PROXY_MODEL", "deepseek-v4-flash")
    monkeypatch.setenv("DEEPSEEK_PROXY_FORCE_MODEL", "1")
    monkeypatch.setenv("DEEPSEEK_PROXY_DB_PATH", str(tmp_path / "runtime.sqlite3"))

    app = create_app(deepseek_client=WeClawBalanceClient())
    _record_usage(
        app.state.store,
        response_id="resp_runtime_primary",
        request_id="resp_runtime",
        created_at=300,
        purpose="primary",
        call_index=0,
        prompt_tokens=42,
        completion_tokens=8,
        total_tokens=50,
        cached_tokens=2,
        reasoning_tokens=1,
        cost=0.004,
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/v1/proxy/weclaw/status?profile=deepseek-thinking")

    assert response.status_code == 200
    data = response.json()
    assert data["tokens"]["last_turn"]["available"] is True
    assert data["tokens"]["last_turn"]["summary"]["total_tokens"] == 50
    assert data["tokens"]["session_total"]["available"] is True
    assert data["cost"]["available"] is False
    assert data["cost"]["scope"] == "unavailable"
    assert data["cost"]["session"]["available"] is False
    assert data["cost"]["session_estimated_cost"] is None
    assert data["cost"]["profile_route_estimated_cost"] is not None
    assert data["balance"]["available"] is True
    assert data["balance"]["display"] == "12.34 USD"


@pytest.mark.asyncio
async def test_weclaw_http_status_balance_unavailable_is_actionable(tmp_path, monkeypatch):
    class NoBalanceClient:
        pass

    codex_config = tmp_path / "codex.toml"
    _write_codex_config(codex_config)
    monkeypatch.setenv("CODEX_CONFIG_FILE", str(codex_config))
    monkeypatch.setenv("DEEPSEEK_PROXY_MODEL", "deepseek-v4-flash")
    monkeypatch.setenv("DEEPSEEK_PROXY_FORCE_MODEL", "1")

    app = create_app(deepseek_client=NoBalanceClient(), store=SQLiteResponseStore(tmp_path / "usage.sqlite3"))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/v1/proxy/weclaw/status?profile=deepseek-thinking")

    assert response.status_code == 200
    data = response.json()
    assert data["balance"]["available"] is False
    assert data["balance"]["status"] == "provider_unsupported"
    assert data["balance"]["provider"] == "deepseek"
    assert data["balance"]["reason"] == "balance_client_unavailable"
    assert data["balance"]["action"] == "provider does not expose balance API through this client"


def test_cli_status_weclaw_json_prefers_runtime_weclaw_status(monkeypatch, tmp_path, capsys):
    codex_config = tmp_path / "codex.toml"
    env_file = tmp_path / "env"
    _write_codex_config(codex_config)
    env_file.write_text(
        "export DEEPSEEK_REASONING_EFFORT=max\n"
        "export DEEPSEEK_PROXY_MODEL=deepseek-v4-flash\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("CODEX_CONFIG_FILE", str(codex_config))
    monkeypatch.setenv("DEEPSEEK_PROXY_ENV_FILE", str(env_file))

    runtime_payload = {
        "status": "ok",
        "profile": "deepseek-thinking",
        "tokens": {
            "last_turn": {"available": True, "summary": {"total_tokens": 1485}},
            "session_total": {"available": True, "summary": {"total_tokens": 1595}},
            "auxiliary_model_calls": {"available": True, "included_in_session_total": True},
        },
        "pricing": {"available": True, "currency": "USD"},
        "cost": {"available": True, "session_estimated_cost": 0.016},
        "balance": {"available": True},
    }

    seen_urls = []

    def fake_http_json(url, timeout=2.0):
        seen_urls.append(url)
        assert "/v1/proxy/weclaw/status" in url
        return 200, runtime_payload, None

    monkeypatch.setattr(cli, "_http_json", fake_http_json)

    assert cli.main(["status", "thinking", "--weclaw-json"]) == 0

    data = json.loads(capsys.readouterr().out)
    assert data["tokens"]["last_turn"]["available"] is True
    assert data["pricing"]["available"] is True
    assert data["cost"]["available"] is True
    assert data["cost"]["session_estimated_cost"] == pytest.approx(0.016)
    assert data["balance"]["available"] is True
    assert data["runtime_status"]["available"] is True
    assert seen_urls



class WeClawCnyBalanceClient(DeepSeekClient):
    async def user_balance(self):
        return {
            "is_available": True,
            "balance_infos": [
                {
                    "currency": "CNY",
                    "total_balance": "4.50",
                    "granted_balance": "0.00",
                    "topped_up_balance": "4.50",
                }
            ],
        }


@pytest.mark.asyncio
async def test_weclaw_status_converts_cost_to_cny_when_balance_is_cny(tmp_path, monkeypatch):
    codex_config = tmp_path / "codex.toml"
    _write_codex_config(codex_config)
    monkeypatch.setenv("CODEX_CONFIG_FILE", str(codex_config))
    monkeypatch.setenv("DEEPSEEK_PROXY_MODEL", "deepseek-v4-flash")
    monkeypatch.setenv("DEEPSEEK_PROXY_FORCE_MODEL", "1")
    monkeypatch.setenv("DEEPSEEK_PROXY_USD_CNY_FX_RATE", "7.25")
    monkeypatch.setenv("DEEPSEEK_PROXY_USD_CNY_FX_UPDATED_AT", "2026-05-18T00:00:00Z")

    store = SQLiteResponseStore(tmp_path / "usage.sqlite3")
    _record_usage(
        store,
        response_id="resp_primary",
        request_id="resp_turn",
        created_at=200,
        purpose="primary",
        call_index=0,
        prompt_tokens=1000,
        completion_tokens=100,
        total_tokens=1100,
        cached_tokens=200,
        reasoning_tokens=10,
        cost=0.01,
    )

    app = create_app(deepseek_client=WeClawCnyBalanceClient(), store=store)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/v1/proxy/weclaw/status?profile=deepseek-thinking")

    assert response.status_code == 200
    data = response.json()
    assert data["balance"]["currency"] == "CNY"
    assert data["pricing"]["source_currency"] in {"CNY", "USD"}
    assert data["pricing"]["display_currency"] == "CNY"
    assert data["pricing"]["cache_miss_input"]["currency"] == "CNY"
    assert data["pricing"]["fx_rate"] is None
    assert data["pricing"]["converted"] is False
    assert data["cost"]["source_currency"] in {"CNY", "USD", "mixed"}
    assert data["cost"]["display_currency"] == "CNY"
    assert data["cost"]["available"] is False
    assert data["cost"]["scope"] == "unavailable"
    assert data["cost"]["session"]["available"] is False
    assert data["cost"]["session_estimated_cost"] is None
    assert data["cost"]["profile_route_estimated_cost"] == pytest.approx(0.0725)
    assert data["cost"].get("session_estimated_cost_usd_legacy", data["cost"].get("session_estimated_cost_usd", 0.0)) == pytest.approx(0.0)
    assert data["cost"]["cash_estimated_cost"] == pytest.approx(0.0725)



@pytest.mark.asyncio
async def test_weclaw_status_uses_cny_primary_pricing_without_fx(tmp_path, monkeypatch):
    codex_config = tmp_path / "codex.toml"
    _write_codex_config(codex_config)
    pricing_path = tmp_path / "pricing.json"
    pricing_path.write_text(
        json.dumps(
            {
                "__metadata__": {
                    "source_url": "https://api-docs.deepseek.com/zh-cn/quick_start/pricing/",
                    "source_kind": "bundled_official_docs_snapshot",
                    "snapshot_created_at": "2026-05-18T00:00:00Z",
                    "currency": "CNY",
                    "unit": "per_million_tokens",
                },
                "deepseek-v4-flash": {
                    "input_cache_hit": 0.02,
                    "input_cache_miss": 1.0,
                    "output": 2.0,
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CODEX_CONFIG_FILE", str(codex_config))
    monkeypatch.setenv("DEEPSEEK_PROXY_PRICING_PATH", str(pricing_path))
    monkeypatch.setenv("DEEPSEEK_PROXY_MODEL", "deepseek-v4-flash")
    monkeypatch.setenv("DEEPSEEK_PROXY_FORCE_MODEL", "1")

    store = SQLiteResponseStore(tmp_path / "usage.sqlite3")
    store.record_usage(
        response_id="resp_primary",
        previous_response_id=None,
        model="deepseek-v4-flash",
        thinking_enabled=True,
        usage_numbers={
            "prompt_tokens": 1000,
            "completion_tokens": 100,
            "total_tokens": 1100,
            "cached_tokens": 200,
            "reasoning_tokens": 0,
        },
        estimated_cost_usd=0.0,
        estimated_cost_source_amount=0.001,
        estimated_cost_source_currency="CNY",
        estimated_cost_display_amount=0.001,
        estimated_cost_display_currency="CNY",
        purpose="primary",
        request_id="resp_turn",
        pricing_context={
            "pricing_model": "deepseek-v4-flash",
            "pricing_currency": "CNY",
            "pricing_unit": "per_million_tokens",
            "pricing_source_kind": "bundled_official_docs_snapshot",
            "pricing_updated_at": "2026-05-18T00:00:00Z",
            "pricing_input_cache_hit": 0.02,
            "pricing_input_cache_miss": 1.0,
            "pricing_output": 2.0,
        },
    )

    app = create_app(deepseek_client=WeClawCnyBalanceClient(), store=store)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/v1/proxy/weclaw/status?profile=deepseek-thinking")

    assert response.status_code == 200
    data = response.json()
    assert data["pricing"]["source_currency"] == "CNY"
    assert data["pricing"]["display_currency"] == "CNY"
    assert data["pricing"]["converted"] is False
    assert data["pricing"]["cache_hit_input"]["amount"] == 0.02
    assert data["pricing"]["cache_miss_input"]["amount"] == 1.0
    assert data["pricing"]["output"]["amount"] == 2.0
    assert data["cost"]["display_currency"] == "CNY"
    assert data["cost"]["available"] is False
    assert data["cost"]["scope"] == "unavailable"
    assert data["cost"]["session"]["available"] is False
    assert data["cost"]["session_estimated_cost"] is None
    assert data["cost"]["profile_route_estimated_cost"] == pytest.approx(0.001)
    assert data["cost"]["cash_estimated_cost"] == pytest.approx(0.001)
    assert data["cost"]["converted"] is False
