from __future__ import annotations

import argparse
import json
from pathlib import Path

from codexchange_proxy import cli

def _codex_profile_text(config_path: Path, profile: str = "cox") -> str:
    path = config_path.parent / f"{profile}.config.toml"
    return path.read_text(encoding="utf-8") if path.exists() else ""



def test_post_config_apply_skips_when_disabled(monkeypatch):
    monkeypatch.setenv("COX_POST_CONFIG_APPLY", "off")
    result = cli._post_config_apply()
    assert result["status"] == "skipped"
    assert result["message"] == "post-config apply disabled"


def test_post_config_apply_refreshes_only_running_proxy(monkeypatch):
    monkeypatch.delenv("COX_POST_CONFIG_APPLY", raising=False)
    calls: list[list[str]] = []

    monkeypatch.setattr(cli, "_port_for", lambda thinking, explicit_port=None: 8001 if thinking else 8000)
    monkeypatch.setattr(cli, "_port_status_looks_like_proxy", lambda port: port == 8001)

    def fake_run(argv, *, timeout=20.0):
        calls.append(list(argv))
        return {"ok": True, "returncode": 0, "argv": ["cox", *argv], "stdout_tail": "", "stderr_tail": ""}

    monkeypatch.setattr(cli, "_post_config_run_self", fake_run)

    result = cli._post_config_apply()

    assert result["status"] == "ok"
    assert result["message"] == "all updates applied"
    assert result["stable_proxy"]["action"] == "not_running"
    assert result["thinking_proxy"]["action"] == "refreshed"
    assert calls == [["stop", "thinking"], ["start", "thinking"]]


def test_cli_effort_compatibility_normalizes_medium_to_high(tmp_path, monkeypatch, capsys):
    env_file = tmp_path / "env"
    codex_config = tmp_path / "config.toml"
    codex_config.write_text(
        "[profiles.cox]\n"
        "model = \"deepseek-v4-pro\"\n"
        "model_reasoning_effort = \"medium\"\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(cli, "_post_config_apply", lambda: {"status": "ok", "message": "all updates applied"})

    args = argparse.Namespace(
        config_command="set-effort",
        effort="medium",
        env_file=str(env_file),
        codex_config=str(codex_config),
        profile="cox",
        path=None,
    )

    assert cli._config(args) == 0
    output = json.loads(capsys.readouterr().out)

    assert output["requested_effort"] == "medium"
    assert output["effort"] == "high"
    assert output["post_config_apply"]["message"] == "all updates applied"
    assert "COX_REASONING_EFFORT=high" in env_file.read_text(encoding="utf-8")
    assert 'model_reasoning_effort = "high"' in _codex_profile_text(codex_config)
    assert "[profiles.cox]" not in codex_config.read_text(encoding="utf-8")


def test_cli_effort_canonicalizer_accepts_codex_compatibility_values():
    assert cli._canonical_cli_reasoning_effort("low") == "high"
    assert cli._canonical_cli_reasoning_effort("medium") == "high"
    assert cli._canonical_cli_reasoning_effort("high") == "high"
    assert cli._canonical_cli_reasoning_effort("xhigh") == "max"
    assert cli._canonical_cli_reasoning_effort("max") == "max"
    assert cli._canonical_cli_reasoning_effort("unsupported") is None
