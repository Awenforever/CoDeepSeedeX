from __future__ import annotations

import json
from pathlib import Path

from codexchange_proxy import cli as cli_module


def test_doctor_uses_standard_reasoning_target_labels(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("COX_CONFIG", str(tmp_path / "config.toml"))

    assert cli_module.main(["doctor", "--port", "9", "--timeout", "0.05", "--allow-down"]) == 0
    standard = json.loads(capsys.readouterr().out)
    assert standard["target"] == "standard"
    assert standard["tool_routing"]["target"] == "standard"

    assert cli_module.main(["doctor", "--reasoning", "--port", "9", "--timeout", "0.05", "--allow-down"]) == 0
    reasoning = json.loads(capsys.readouterr().out)
    assert reasoning["target"] == "reasoning"
    assert reasoning["tool_routing"]["target"] == "reasoning"


def test_doctor_tool_routing_uses_standard_reasoning_target_labels(monkeypatch, tmp_path, capsys):
    env_file = tmp_path / "env"
    env_file.write_text("", encoding="utf-8")

    def fake_http_json(url: str, *, timeout: float):
        return None, None, "down"

    monkeypatch.setattr(cli_module, "_http_json", fake_http_json)

    assert cli_module.main(["doctor", "tool-routing", "--env-file", str(env_file)]) == 0
    standard = json.loads(capsys.readouterr().out)
    assert standard["target"] == "standard"

    assert cli_module.main(["doctor", "tool-routing", "--reasoning", "--env-file", str(env_file)]) == 0
    reasoning = json.loads(capsys.readouterr().out)
    assert reasoning["target"] == "reasoning"


def test_cli_source_no_longer_emits_stable_thinking_target_json():
    source = Path(cli_module.__file__).read_text(encoding="utf-8")
    assert '"target": "thinking" if thinking else "stable"' not in source
    assert '"target": _lifecycle_route_name(thinking)' in source
