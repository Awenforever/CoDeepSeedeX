import importlib
import json

import pytest


def _app_module():
    return importlib.import_module("codexchange_proxy.app")


def test_command_risk_policy_status_defaults_to_dry_run(monkeypatch):
    app_module = _app_module()
    monkeypatch.delenv("COX_COMMAND_RISK_POLICY_MODE", raising=False)

    status = app_module._command_risk_policy_status()

    assert status["mode"] == "dry_run"
    assert status["enabled"] is False
    assert status["policy_is_dry_run_only"] is True
    assert status["gate_scope"] == "C4_only_future_gate"
    assert status["c4_gate_available"] is True
    assert status["c4_gate_action_when_enabled"] == "suppress_and_explain"
    assert status["c4_gate_resume_supported"] is False
    assert "C2_routine_side_effect" in status["normal_development_risks_allowed"]
    assert "C3_codex_governed_destructive" in status["normal_development_risks_allowed"]


def test_command_risk_policy_status_enabled(monkeypatch):
    app_module = _app_module()
    monkeypatch.setenv("COX_COMMAND_RISK_POLICY_MODE", "enabled")

    status = app_module._command_risk_policy_status()

    assert status["mode"] == "enabled"
    assert status["enabled"] is True
    assert status["active_when_enabled"] is True
    assert status["env_var"] == "COX_COMMAND_RISK_POLICY_MODE"


def test_command_risk_policy_status_bad_value_falls_back_to_dry_run(monkeypatch):
    app_module = _app_module()
    monkeypatch.setenv("COX_COMMAND_RISK_POLICY_MODE", "bad_value")

    status = app_module._command_risk_policy_status()

    assert status["mode"] == "dry_run"
    assert status["enabled"] is False


@pytest.mark.asyncio
async def test_proxy_status_tool_exposes_command_risk_policy(monkeypatch):
    app_module = _app_module()
    monkeypatch.setenv("COX_COMMAND_RISK_POLICY_MODE", "enabled")

    result = await app_module._execute_proxy_tool_call(
        {
            "type": "function",
            "function": {
                "name": "proxy_status",
                "arguments": json.dumps({}),
            },
        }
    )

    policy = result["command_risk_policy"]
    assert policy["mode"] == "enabled"
    assert policy["enabled"] is True
    assert policy["gate_scope"] == "C4_only_future_gate"
    assert policy["c4_gate_action_when_enabled"] == "suppress_and_explain"
    assert policy["c4_gate_resume_supported"] is False
