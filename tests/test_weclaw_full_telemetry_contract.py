from __future__ import annotations

import json
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from codexchange_proxy.app import DeepSeekClient, SQLiteResponseStore, create_app
from codexchange_proxy import cli


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
        "[model_providers.cox-proxy]\n"
        "base_url = \"http://127.0.0.1:8001/v1\"\n\n"
        "[profiles.cox]\n"
        "model = \"deepseek-v4-flash\"\n"
        "model_provider = \"cox-proxy\"\n"
        "model_context_window = 1000000\n"
        "model_auto_compact_token_limit = 900000\n"
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
    monkeypatch.setenv("COX_MODEL", "deepseek-v4-flash")
    monkeypatch.setenv("COX_FORCE_MODEL", "1")

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
            "runtime_trigger_source": "token_first",
            "unit": "tokens",
            "estimated_context_tokens": 123,
            "estimated_context_tokens_precision": "local_profile_tokenizer_estimate",
            "model_context_window_tokens": 1000000,
            "auto_compact_threshold_tokens": 900000,
            "auto_compact_threshold_source": "codex_profile.model_auto_compact_token_limit",
            "model_auto_compact_token_limit": 900000,
            "auto_compact_ratio": 0.9,
            "tokens_to_auto_compact": 899877,
        },
        "runtime_trigger_source": "token_first",
        "unit": "tokens",
        "estimated_context_tokens": 123,
        "estimated_context_tokens_precision": "local_profile_tokenizer_estimate",
        "model_context_window_tokens": 1000000,
        "auto_compact_threshold_tokens": 900000,
        "auto_compact_threshold_source": "codex_profile.model_auto_compact_token_limit",
        "model_auto_compact_token_limit": 900000,
        "auto_compact_ratio": 0.9,
        "tokens_to_auto_compact": 899877,
        "observed_at": "2026-05-17T10:00:00Z",
        "source": "runtime_context_builder",
        "material": {
            "compactable_message_count": 8,
            "compaction_prompt_fingerprint": {
                "available": True,
                "sha256": "c" * 64,
                "raw_prompt_exposed": False,
                "raw_material_exposed": False,
            },
            "compact_material_classifier_dry_run": {
                "available": True,
                "mode": "dry_run",
                "applied": False,
            },
            "retained_recent_policy": {
                "available": True,
                "retained_recent_message_count": 4,
            },
        },
        "compact_audit_generation": {
            "available": True,
            "mode": "dry_run",
            "applied": False,
            "source": "policy_decision_not_triggered",
            "raw_prompt_exposed": False,
            "raw_material_exposed": False,
        },
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
        "type_enum_version": 1,
        "token_first_trim_dry_run": {
            "available": True,
            "mode": "dry_run",
            "applied": False,
            "unit": "tokens",
            "estimated_payload_tokens": 123,
            "would_trim": False,
            "raw_content_exposed": False,
            "runtime_context": {
                "profile": "cox",
                "model": "deepseek-v4-flash",
                "model_context_window_tokens": 1000000,
                "auto_compact_threshold_tokens": 900000,
            },
        },
        "item_type_summary": {
            "type_enum_version": 1,
            "type_counts": {"tool_result": 1},
            "raw_content_exposed": False,
            "redacted": True,
        },
        "protected_static_blocks": {
            "available": True,
            "protected_static_message_indexes": [0],
            "raw_content_exposed": False,
        },
        "image_first_protection": {
            "available": False,
            "first_image_index": None,
            "protected": False,
            "raw_image_content_exposed": False,
        },
        "image_semantic_envelope": {
            "available": True,
            "enabled": True,
            "mode": "enabled",
            "transform_enabled": True,
            "applied": True,
            "applied_count": 1,
            "image_message_count": 2,
            "image_count": 2,
            "protected_count": 1,
            "transformed_count": 1,
            "items": [{"index": 0, "protected": True, "raw_image_content_exposed": False}, {"index": 1, "transformed": True, "raw_image_content_exposed": False}],
            "raw_image_content_exposed": False,
            "redacted": True,
        },
        "type_aware_trim": {
            "available": True,
            "enabled": True,
            "mode": "enabled",
            "applied": True,
            "applied_count": 1,
            "applied_by_type": {"tool_result": {"trimmed_field_count": 1, "chars_removed": 10}},
            "raw_content_exposed": False,
            "redacted": True,
        },
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/v1/proxy/weclaw/status?profile=cox")

    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "ok"
    assert data["profile"] == "cox"

    context_window = data["context_window"]
    assert context_window["used_tokens_available"] is True
    assert context_window["used_tokens"] == 1000
    assert context_window["used_tokens_is_estimated"] is True
    assert context_window["used_tokens_source"] == "cox_usage_ledger.latest_primary_turn.summary.prompt_tokens"
    assert context_window["latest_upstream_prompt_tokens"]["value"] == 1000
    assert context_window["latest_upstream_prompt_tokens"]["is_estimated_for_context_window"] is True
    assert context_window["remaining_tokens_estimate"] == 999000
    assert context_window["limit_explanation"]["display_limit_tokens"] == 1000000
    assert context_window["limit_explanation"]["model_context_window_tokens"] == 1000000
    assert context_window["limit_explanation"]["auto_compact_token_limit"] == 900000

    guard = data["runtime_payload_guard"]
    assert guard["available"] is True
    assert guard["unit"] == "tokens"
    assert guard["current_tokens"] == 123
    assert guard["current_tokens_available"] is True
    assert guard["current_tokens_source"] == "token_first_runtime_trim"
    assert guard["current_tokens_precision"] == "local_profile_tokenizer_estimate"
    assert guard["primary_control_unit"] == "tokens"
    assert "legacy_char_debug" not in guard
    assert guard["compaction"]["available"] is True
    assert guard["compaction"]["unit"] == "tokens"
    assert guard["compaction"]["trigger_tokens"] == 900000
    assert guard["compaction"]["current_tokens"] == 123
    assert guard["compaction"]["capacity_progress_ratio"] == pytest.approx(123 / 900000)
    assert guard["compaction"]["remaining_tokens"] == 899877
    assert guard["compaction"]["status"] == "not_triggered"
    assert "legacy_char_debug" not in guard["compaction"]
    token_compaction = guard["compaction"]["token_first"]
    assert token_compaction["unit"] == "tokens"
    assert token_compaction["primary_control_unit"] == "tokens"
    assert token_compaction["estimated_tokens_before_compact"] == token_compaction["before_tokens"]
    assert token_compaction["estimated_tokens_after_compact"] == token_compaction["after_tokens"]
    assert token_compaction["estimated_tokens_removed_by_compact"] == token_compaction["tokens_removed"]
    assert token_compaction["trigger_tokens"] == 900000
    assert token_compaction["target_available"] is False
    assert token_compaction["target_reason"] == "explicit_token_compact_target_not_configured"
    assert isinstance(token_compaction["before_tokens"], int)
    assert token_compaction["after_tokens"] == token_compaction["before_tokens"]
    assert token_compaction["retention_ratio"] == 1.0
    assert data["compaction"]["token_first"]["trigger_tokens"] == 900000
    assert guard["compaction"]["last_report"]["exists"] is True
    assert guard["compaction"]["compact_audit"]["available"] is True
    assert guard["compaction"]["compact_audit"]["fingerprint"]["sha256"] == "c" * 64
    assert guard["compaction"]["last_report"]["compact_audit"]["fingerprint"]["sha256"] == "c" * 64
    assert guard["compaction"]["last_report"]["compact_material_classifier_dry_run"]["mode"] == "dry_run"
    assert guard["compaction"]["last_report"]["retained_recent_policy"]["retained_recent_message_count"] == 4
    assert data["compaction"]["compact_audit"]["fingerprint"]["sha256"] == "c" * 64
    assert data["context_window"]["runtime"]["payload_guard"]["compaction"]["compact_audit"]["available"] is True
    assert guard["trimming"]["available"] is True
    assert guard["trimming"]["unit"] == "tokens"
    assert guard["trimming"]["current_tokens"] == 123
    assert guard["trimming"]["max_context_tokens"] == 900000
    assert guard["trimming"]["capacity_progress_ratio"] == pytest.approx(123 / 900000)
    assert guard["trimming"]["remaining_tokens"] == 899877
    assert guard["trimming"]["status"] == "not_triggered"
    assert "legacy_char_debug" not in guard["trimming"]
    assert guard["trimming"]["last_report"]["exists"] is True
    assert guard["trimming"]["last_report"]["type_enum_version"] == 1
    assert guard["trimming"]["last_report"]["token_first_trim_dry_run"]["available"] is True
    assert guard["trimming"]["last_report"]["token_first_trim_dry_run"]["unit"] == "tokens"
    runtime_trim = guard["trimming"]["token_first_runtime_trim"]
    assert runtime_trim["primary_control_unit"] == "tokens"
    assert runtime_trim["estimated_tokens_before_trim"] == runtime_trim["before_tokens"]
    assert runtime_trim["estimated_tokens_after_trim"] == runtime_trim["after_tokens"]
    assert runtime_trim["estimated_tokens_removed_by_trim"] == runtime_trim["tokens_removed"]
    assert guard["trimming"]["last_report"]["token_first_trim_dry_run"]["runtime_context"]["profile"] == "cox"
    assert guard["trimming"]["last_report"]["item_type_summary"]["type_counts"]["tool_result"] == 1
    assert guard["trimming"]["last_report"]["protected_static_blocks"]["raw_content_exposed"] is False
    assert guard["trimming"]["last_report"]["image_semantic_envelope"]["enabled"] is True
    assert guard["trimming"]["last_report"]["image_semantic_envelope"]["transformed_count"] == 1
    assert guard["trimming"]["last_report"]["image_semantic_envelope"]["items"][1]["raw_image_content_exposed"] is False
    assert guard["trimming"]["last_report"]["type_aware_trim"]["enabled"] is True
    assert guard["trimming"]["last_report"]["type_aware_trim"]["applied"] is True
    assert guard["trimming"]["last_report"]["type_aware_trim"]["applied_by_type"]["tool_result"]["trimmed_field_count"] == 1
    assert data["context_window"]["runtime"]["unit"] == "tokens"
    assert data["context_window"]["runtime"]["payload_guard"]["current_tokens"] == 123
    assert "legacy_char_debug" not in data["context_window"]["runtime"]
    assert data["compaction"]["unit"] == "tokens"
    assert data["compaction"]["runtime_payload_guard"]["current_tokens"] == 123

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
    monkeypatch.setenv("COX_MODEL", "deepseek-v4-flash")
    monkeypatch.setenv("COX_FORCE_MODEL", "1")
    monkeypatch.setenv("COX_DB_PATH", str(tmp_path / "runtime.sqlite3"))

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
        response = await client.get("/v1/proxy/weclaw/status?profile=cox")

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
    monkeypatch.setenv("COX_MODEL", "deepseek-v4-flash")
    monkeypatch.setenv("COX_FORCE_MODEL", "1")

    app = create_app(deepseek_client=NoBalanceClient(), store=SQLiteResponseStore(tmp_path / "usage.sqlite3"))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/v1/proxy/weclaw/status?profile=cox")

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
        "export COX_REASONING_EFFORT=max\n"
        "export COX_MODEL=deepseek-v4-flash\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("CODEX_CONFIG_FILE", str(codex_config))
    monkeypatch.setenv("COX_ENV_FILE", str(env_file))

    runtime_payload = {
        "status": "ok",
        "profile": "cox",
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
    monkeypatch.setenv("COX_MODEL", "deepseek-v4-flash")
    monkeypatch.setenv("COX_FORCE_MODEL", "1")
    monkeypatch.setenv("COX_USD_CNY_FX_RATE", "7.25")
    monkeypatch.setenv("COX_USD_CNY_FX_UPDATED_AT", "2026-05-18T00:00:00Z")

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
        response = await client.get("/v1/proxy/weclaw/status?profile=cox")

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
    monkeypatch.setenv("COX_PRICING_PATH", str(pricing_path))
    monkeypatch.setenv("COX_MODEL", "deepseek-v4-flash")
    monkeypatch.setenv("COX_FORCE_MODEL", "1")

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
        response = await client.get("/v1/proxy/weclaw/status?profile=cox")

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


class WeClawNoNetworkPrimaryClient(WeClawBalanceClient):
    def __init__(self) -> None:
        super().__init__(api_key="test", base_url="https://example.deepseek")
        self.primary_payloads: list[dict] = []

    async def chat_completions(self, payload: dict, trace_metadata: dict | None = None):
        serialized_payload = json.dumps(payload, ensure_ascii=False)
        assert "Codex-like conversation compactor" not in serialized_payload
        self.primary_payloads.append(payload)
        return {
            "id": "chatcmpl_skip_audit_primary",
            "model": payload.get("model") or "deepseek-v4-flash",
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "OK",
                    }
                }
            ],
            "usage": {
                "prompt_tokens": 12,
                "completion_tokens": 1,
                "total_tokens": 13,
            },
        }


@pytest.mark.asyncio
async def test_weclaw_http_status_exposes_compact_audit_after_real_skipped_compaction_request(tmp_path, monkeypatch):
    codex_config = tmp_path / "codex.toml"
    _write_codex_config(codex_config)
    monkeypatch.setenv("CODEX_CONFIG_FILE", str(codex_config))
    monkeypatch.setenv("COX_MODEL", "deepseek-v4-flash")
    monkeypatch.setenv("COX_FORCE_MODEL", "1")
    monkeypatch.setenv("COX_COMPACT_ENABLED", "1")
    monkeypatch.setenv("COX_COMPACT_POLICY", "fixed")
    monkeypatch.setenv("COX_COMPACT_TRIGGER_CHARS", "1000000")
    monkeypatch.setenv("COX_COMPACT_KEEP_RECENT_MESSAGES", "2")
    monkeypatch.setenv("COX_COMPACT_MATERIAL_CHARS", "12000")
    monkeypatch.setenv("COX_TOKENIZER_RESOURCE_DIR", str(tmp_path / "missing-tokenizer-resources"))
    monkeypatch.chdir(tmp_path)

    upstream = WeClawNoNetworkPrimaryClient()
    app = create_app(
        deepseek_client=upstream,
        store=SQLiteResponseStore(tmp_path / "usage.sqlite3"),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/responses",
            json={
                "model": "deepseek-v4-flash",
                "input": "Reply OK exactly. Do not leak this raw user sentence through Compact audit metadata.",
            },
        )
        assert response.status_code == 200

        status_response = await client.get(
            "/v1/proxy/weclaw/status?profile=cox&include_balance=false"
        )
        proxy_status_response = await client.get("/v1/proxy/status")

    assert len(upstream.primary_payloads) == 1
    assert app.state.last_context_compaction_report is not None
    report = app.state.last_context_compaction_report
    assert report["compacted"] is False
    assert report["runtime_trigger_source"] == "token_first"
    assert report["reason"] == "token_first_below_auto_compact_threshold"
    assert report["tokens_to_auto_compact"] > 0
    assert report["compact_audit_generation"]["available"] is True
    assert report["compact_audit_generation"]["mode"] == "dry_run"
    assert report["compact_audit_generation"]["applied"] is False
    assert report["compact_audit_generation"]["source"] == "policy_decision_not_triggered"
    assert report["compact_audit_generation"]["raw_prompt_exposed"] is False
    assert report["compact_audit_generation"]["raw_material_exposed"] is False

    assert status_response.status_code == 200
    assert proxy_status_response.status_code == 200
    data = status_response.json()
    proxy_status_data = proxy_status_response.json()
    semantic = data["semantic_compaction"]
    proxy_semantic = proxy_status_data["semantic_compaction"]
    assert app.state.last_semantic_compaction_events is not None
    assert semantic["latest"]["semantic_audit"]["present"] is True
    assert semantic["latest"]["semantic_audit"]["source"] == "in_memory_runtime_semantic_payload_snapshot"
    assert semantic["latest"]["semantic_policy_dry_run"]["present"] is True
    assert semantic["latest"]["semantic_policy_dry_run"]["source"] == "in_memory_runtime_semantic_payload_snapshot"
    assert semantic["latest"]["semantic_payload_compaction"]["present"] is True
    assert semantic["latest"]["semantic_payload_compaction"]["source"] == "in_memory_runtime_semantic_payload_snapshot"
    assert semantic["latest"]["semantic_payload_compaction"]["mode"] == "dry_run"
    assert semantic["latest"]["semantic_payload_compaction"]["reason"] == "semantic_payload_compaction_mode_not_enabled"
    assert proxy_semantic["latest"]["semantic_payload_compaction"]["present"] is True
    assert proxy_semantic["latest"]["semantic_payload_compaction"]["source"] == "in_memory_runtime_semantic_payload_snapshot"
    assert "semantic_audit_event_missing" not in semantic["rollout"]["blockers"]
    assert "semantic_policy_dry_run_event_missing" not in semantic["rollout"]["blockers"]
    assert "semantic_payload_compaction_event_missing" not in semantic["rollout"]["blockers"]
    guard = data["runtime_payload_guard"]
    top_audit = data["compaction"]["compact_audit"]
    nested_audit = data["context_window"]["runtime"]["payload_guard"]["compaction"]["compact_audit"]
    last_report = guard["compaction"]["last_report"]

    for audit in (top_audit, nested_audit, guard["compaction"]["compact_audit"], last_report["compact_audit"]):
        assert audit["available"] is True
        assert "unit" not in audit
        audit_dump = json.dumps(audit, ensure_ascii=False, sort_keys=True)
        assert "chars/messages" not in audit_dump
        assert "char_count" not in audit_dump
        assert '"chars"' not in audit_dump
        assert audit["redacted"] is True
        assert audit["raw_content_exposed"] is False
        assert audit["missing"] == []
        assert audit["reason"] is None
        assert len(audit["fingerprint"]["sha256"]) == 64
        assert audit["fingerprint"]["raw_prompt_exposed"] is False
        assert audit["fingerprint"]["raw_material_exposed"] is False
        assert audit["classifier_dry_run"]["available"] is True
        assert audit["classifier_dry_run"]["mode"] == "dry_run"
        assert audit["classifier_dry_run"]["applied"] is False
        assert audit["retained_recent_policy"]["available"] is True
        assert audit["codex_native_source_evidence"]["prompt_md_sha256"] == "ab0c334d4faca17e3afbb9b16967c1b2fdcc7242a9a0880af57949fa236d6d07"
        assert audit["codex_native_source_evidence"]["remote_compact_endpoint"] == "responses/compact"
        assert audit["codex_native_source_evidence"]["remote_compaction_claimed_for_cox_provider"] is False
        assert audit["compact_prompt_alignment"]["alignment"] == "github_source_backed_codex_native_local_prompt"
        assert audit["compact_prompt_alignment"]["exact_native_codex_local_prompt_text"] is True
        assert audit["compact_prompt_alignment"]["remote_native_compaction_claimed"] is False
        assert audit["codex_summary_prefix"]["sha256"] == "e9b088e794a6bb9082ac053fcc760bd818d7e720ee4bcdc72c6e480de7b7cb0e"

    assert guard["compaction"]["available"] is True
    assert guard["compaction"]["status"] == "not_triggered"
    assert guard["compaction"]["last_report"]["exists"] is True
    assert guard["compaction"]["last_report"]["compact_audit_generation"]["available"] is True
    assert guard["compaction"]["last_report"]["compact_material_classifier_dry_run"]["mode"] == "dry_run"
    assert data["context_window"]["runtime"]["payload_guard"]["compaction"]["compact_audit"]["available"] is True
    assert data["compaction"]["compact_audit"]["fingerprint"]["sha256"] == guard["compaction"]["compact_audit"]["fingerprint"]["sha256"]

    serialized_status = json.dumps(data, ensure_ascii=False)
    assert "Reply OK exactly. Do not leak this raw user sentence through Compact audit metadata." not in serialized_status
    assert '"raw_prompt_exposed": true' not in serialized_status.lower()
    assert '"raw_material_exposed": true' not in serialized_status.lower()


def test_weclaw_semantic_payload_display_contract_exposes_mode_savings_and_safety_metadata():
    import importlib

    proxy_app = importlib.import_module("codexchange_proxy.app")
    status = {
        "latest": {
            "semantic_audit": {"present": True, "source": "in_memory_runtime_semantic_payload_snapshot"},
            "semantic_policy_dry_run": {
                "present": True,
                "would_compact": True,
                "semantic_type_counts": {"test_output": 2},
                "risk_counts": {"low": 2},
                "policy_decisions": {"compact": 2},
                "recommended_actions": {"compact_test_output_summary": 2},
            },
            "semantic_payload_compaction": {
                "present": True,
                "source": "in_memory_runtime_semantic_payload_snapshot",
                "observed_at": "2026-05-22T12:00:00Z",
                "mode": "enabled",
                "effective_mode": "enabled",
                "applied": True,
                "reason": "enabled",
                "compacted_count": 2,
                "skipped_policy_count": 1,
                "retained_recent_flattened_count": 1,
                "tokens_before": 1000,
                "tokens_after": 400,
                "tokens_removed": 600,
                "chars_before": 4000,
                "chars_after": 1600,
                "chars_removed": 2400,
                "semantic_type_counts": {"test_output": 2},
                "risk_counts": {"low": 2, "medium": 1},
                "policy_decisions": {"compact": 2, "structure_only": 1},
                "recommended_actions": {"compact_test_output_summary": 2, "structure_preserving_summary_dry_run_only": 1},
                "skip_reasons": {"medium_risk_requires_marker_preservation": 1},
                "canary_guard": {"allowed": True},
                "top_target": {
                    "semantic_type": "test_output",
                    "semantic_plan_type": "pytest_success",
                    "semantic_risk": "low",
                    "policy_decision": "compact",
                    "safe_payload_mutation_allowed": True,
                    "source": "semantic_payload_safety_core_v1",
                    "tokens_removed": 300,
                },
            },
        },
        "rollout": {
            "runtime_state": "enabled_monitoring",
            "enabled_monitoring_healthy": True,
            "safe_to_enable_payload_compaction": False,
            "current_payload_mode": "enabled",
            "latest_payload_mode": "enabled",
            "latest_payload_effective_mode": "enabled",
            "latest_payload_reason": "enabled",
            "latest_payload_applied": True,
            "latest_payload_canary_allowed": True,
            "blockers": [],
            "warnings": ["semantic_payload_compaction_enabled_monitoring_active"],
            "recommendation": "monitor_enabled_rollout",
        },
    }

    enriched = proxy_app._weclaw_enrich_semantic_compaction_status(status)
    display = enriched["display"]

    assert display["available"] is True
    assert display["display_contract_version"] == 1
    assert display["status"] == "applied"
    assert display["mode"] == "enabled"
    assert display["effective_mode"] == "enabled"
    assert display["runtime_state"] == "enabled_monitoring"
    assert display["enabled_monitoring_healthy"] is True
    assert display["applied"] is True
    assert display["applied_count"] == 2
    assert display["skipped_count"] == 2
    assert display["tokens_before"] == 1000
    assert display["tokens_after"] == 400
    assert display["tokens_removed"] == 600
    assert "chars_removed" not in display
    assert "chars_before" not in display
    assert "chars_after" not in display
    assert display["type_counts"] == {"test_output": 2}
    assert display["type_actions"] == {"compact": 2, "structure_only": 1}
    assert display["recommended_actions"]["compact_test_output_summary"] == 2
    assert display["risk_counts"]["medium"] == 1
    assert display["skip_reasons"]["medium_risk_requires_marker_preservation"] == 1
    assert display["last_event"]["reason"] == "enabled"
    assert display["last_event"]["source"] == "in_memory_runtime_semantic_payload_snapshot"
    assert display["last_event"]["top_target"]["safe_payload_mutation_allowed"] is True
    assert display["raw_content_exposed"] is False
    assert display["redacted"] is True

    diagnostics = proxy_app._weclaw_diagnostics_contract({"semantic_compaction": enriched})
    assert all(item["path"] != "semantic_compaction.rollout" for item in diagnostics["degraded_fields"])


def test_semantic_payload_runtime_status_exposes_display_contract(monkeypatch):
    import importlib

    proxy_app = importlib.import_module("codexchange_proxy.app")
    monkeypatch.setenv("COX_FLATTENED_TOOL_SEMANTIC_PAYLOAD_COMPACTION_MODE", "enabled")
    monkeypatch.setenv("COX_FLATTENED_TOOL_SEMANTIC_PAYLOAD_CANARY_ALLOW_ENABLED", "1")

    payload_event = {
        "event": "flattened_tool_transcript_semantic_payload_compaction_applied",
        "source": "in_memory_runtime_semantic_payload_snapshot",
        "mode": "enabled",
        "effective_mode": "enabled",
        "applied": True,
        "reason": "enabled",
        "compacted_count": 1,
        "tokens_before": 100,
        "tokens_after": 60,
        "tokens_removed": 40,
        "chars_before": 400,
        "chars_after": 240,
        "chars_removed": 160,
        "semantic_type_counts": {"test_output": 1},
        "risk_counts": {"low": 1},
        "policy_decisions": {"compact": 1},
        "recommended_actions": {"compact_test_output_summary": 1},
        "canary_guard": {"allowed": True},
        "targets": [
            {
                "index": 0,
                "semantic_type": "test_output",
                "semantic_plan_type": "pytest_success",
                "semantic_risk": "low",
                "risk_level": "low",
                "policy_decision": "compact",
                "recommended_action": "compact_test_output_summary",
                "compression_strategy": "pytest_passed_summary_with_tail",
                "safe_payload_mutation_allowed": True,
                "safety_core_version": 1,
                "source": "semantic_payload_safety_core_v1",
                "reason": "semantic_payload_enabled_low_risk_test_output",
                "tokens_removed": 40,
            }
        ],
    }
    runtime_status = proxy_app._semantic_compaction_runtime_status(
        runtime_events={
            "semantic_audit": {"event": "flattened_tool_transcript_semantic_audit", "source": "in_memory_runtime_semantic_payload_snapshot"},
            "semantic_policy_dry_run": {
                "event": "flattened_tool_transcript_semantic_policy_dry_run",
                "source": "in_memory_runtime_semantic_payload_snapshot",
                "would_compact": True,
            },
            "semantic_payload_compaction": payload_event,
        }
    )

    display = runtime_status["display"]
    assert display["status"] == "applied"
    assert display["runtime_state"] == "enabled_monitoring"
    assert display["tokens_removed"] == 40
    assert display["type_counts"] == {"test_output": 1}
    assert display["type_actions"] == {"compact": 1}
    assert display["recommended_actions"] == {"compact_test_output_summary": 1}
    assert display["last_event"]["top_target"]["source"] == "semantic_payload_safety_core_v1"


@pytest.mark.asyncio
async def test_weclaw_status_marks_mismatched_trim_report_unavailable(tmp_path, monkeypatch):
    codex_config = tmp_path / "codex.toml"
    _write_codex_config(codex_config)
    monkeypatch.setenv("CODEX_CONFIG_FILE", str(codex_config))
    monkeypatch.setenv("COX_MODEL", "deepseek-v4-flash")
    monkeypatch.setenv("COX_FORCE_MODEL", "1")

    app = create_app(deepseek_client=WeClawBalanceClient(), store=SQLiteResponseStore(tmp_path / "usage.sqlite3"))
    app.state.deepseek_client.last_context_trimming_report = {
        "version": "v0.3.9-alpha",
        "enabled": True,
        "trimmed": False,
        "before_chars": 100,
        "after_chars": 100,
        "observed_at": "2026-05-21T10:00:00Z",
        "token_first_trim_dry_run": {
            "available": True,
            "unit": "tokens",
            "runtime_context": {
                "profile": "deepseek",
                "model": "deepseek-v4-pro",
                "auto_compact_threshold_tokens": 750000,
            },
        },
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/v1/proxy/weclaw/status?profile=cox&include_balance=false")

    assert response.status_code == 200
    trimming = response.json()["runtime_payload_guard"]["trimming"]
    assert trimming["available"] is False
    assert trimming["last_report"]["reason"] == "runtime_trimming_report_profile_mismatch"
    assert trimming["last_report"]["requested_profile"] == "cox"
    assert trimming["last_report"]["observed_profile"] == "deepseek"
    assert trimming["last_report"]["token_first_trim_dry_run"]["available"] is False


@pytest.mark.asyncio
async def test_weclaw_status_restores_profile_tokenizer_report_from_sqlite_for_resumed_session(tmp_path, monkeypatch):
    codex_config = tmp_path / "codex.toml"
    _write_codex_config(codex_config)
    monkeypatch.setenv("CODEX_CONFIG_FILE", str(codex_config))
    monkeypatch.setenv("COX_MODEL", "deepseek-v4-flash")
    monkeypatch.setenv("COX_FORCE_MODEL", "1")

    store = SQLiteResponseStore(tmp_path / "usage.sqlite3")
    store.record_usage(
        response_id="resp_restore",
        previous_response_id=None,
        model="deepseek-v4-flash",
        thinking_enabled=True,
        usage_numbers={
            "prompt_tokens": 10,
            "completion_tokens": 2,
            "total_tokens": 12,
            "cached_tokens": 0,
            "reasoning_tokens": 0,
        },
        estimated_cost_usd=0.0,
        purpose="primary",
        call_index=0,
        request_id="resp_restore",
        session_id="sess-resume",
        requested_model="deepseek-v4-flash",
        effective_model="deepseek-v4-flash",
        upstream_model="deepseek-v4-flash",
    )
    store.save_profile_tokenizer_report(
        {
            "available": True,
            "profile": "cox",
            "session_id": "sess-resume",
            "request_id": "resp_restore",
            "response_id": "resp_restore",
            "model": "deepseek-v4-flash",
            "provider": "deepseek",
            "tokenizer": {
                "available": True,
                "source_kind": "managed",
                "tokenizer_kind": "deepseek_official_current",
                "source": "test",
            },
            "summary": {"available": True, "total_content_tokens": 10},
            "prompt_subcategory_split": {
                "available": True,
                "scope": "current_session",
                "session_id": "sess-resume",
                "unit": "tokens",
                "is_estimated": True,
                "precision": "local_profile_tokenizer_estimate",
                "semantic_scope": "message_content_and_tool_call_arguments_after_cox_payload_assembly",
                "categories": {
                    "user": {"tokens": 4},
                    "system": {"tokens": 6},
                    "assistant_history": {"tokens": 0},
                    "user_history": {"tokens": 0},
                    "tool_output": {"tokens": 0},
                    "environment": {"tokens": 0},
                    "developer": {"tokens": 0},
                    "compaction_summary": {"tokens": 0},
                    "runtime_injected": {"tokens": 0},
                    "other_prompt": {"tokens": 0},
                },
                "total_tokens": 10,
                "latest_prompt_segmentation": {
                    "available": True,
                    "session_id": "sess-resume",
                    "total_prompt_tokens_profile_tokenizer": 10,
                    "segments": [
                        {"index": 0, "category": "system", "source": "system", "role": "system", "char_count": 10, "token_count": 6, "sha256": "s", "preview": "sys"},
                        {"index": 1, "category": "user", "source": "codex_request", "role": "user", "char_count": 2, "token_count": 4, "sha256": "u", "preview": "ok"},
                    ],
                },
            },
        }
    )

    app = create_app(deepseek_client=WeClawBalanceClient(), store=store)
    app.state.last_profile_tokenizer_report_by_profile = {}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/v1/proxy/weclaw/status?profile=cox&session_id=sess-resume&include_balance=false")

    assert response.status_code == 200
    data = response.json()
    origin = data["tokens"]["prompt_reconciliation"]["details_origin_breakdown"]
    assert origin["available"] is True
    assert origin["restored_from_persistence"] is True
    assert origin["source"] == "sqlite_profile_tokenizer_report_store"
    assert origin["components"]["user"]["tokens"] == 4
    assert origin["components"]["system"]["tokens"] == 6
