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

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/v1/proxy/weclaw/status?profile=deepseek-thinking")

    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "ok"
    assert data["profile"] == "deepseek-thinking"

    last_turn = data["tokens"]["last_turn"]
    assert last_turn["available"] is True
    assert last_turn["unit"] == "tokens"
    assert last_turn["request_id"] == "resp_turn"
    assert last_turn["summary"]["model_call_count"] == 3
    assert last_turn["summary"]["prompt_tokens"] == 1350
    assert last_turn["summary"]["completion_tokens"] == 135
    assert last_turn["summary"]["total_tokens"] == 1485
    assert last_turn["summary"]["cached_tokens"] == 220
    assert last_turn["summary"]["reasoning_tokens"] == 10
    assert last_turn["by_purpose"]["primary"]["prompt_tokens"] == 1000
    assert last_turn["by_purpose"]["tool_bridge"]["prompt_tokens"] == 300
    assert last_turn["by_purpose"]["liveness_judge"]["prompt_tokens"] == 50

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
    assert data["pricing"]["currency"] == "USD"
    assert data["pricing"]["unit"] == "per_1m_tokens"
    assert data["pricing"]["prices"]["input_cache_miss"] > 0

    assert data["cost"]["available"] is True
    assert data["cost"]["is_estimated"] is True
    assert data["cost"]["last_turn_estimated_cost"] == pytest.approx(0.015)
    assert data["cost"]["session_estimated_cost"] == pytest.approx(0.016)
    assert data["cost"]["auxiliary_estimated_cost"] == pytest.approx(0.005)

    assert data["balance"]["available"] is True
    assert data["balance"]["provider"] == "deepseek"
    assert data["balance"]["balance"]["balance_infos"][0]["total_balance"] == "12.34"
    assert data["cost"]["balance"]["available"] is True


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
    assert data["balance"]["available"] is True
    assert data["runtime_status"]["available"] is True
    assert seen_urls
