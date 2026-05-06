from __future__ import annotations

import json

from deepseek_responses_proxy.cli import default_config_path, main


def test_cli_version(capsys):
    assert main(["--version"]) == 0
    out = capsys.readouterr().out
    assert "v2.4a1-cli-and-config-foundation" in out


def test_cli_config_path_uses_env(monkeypatch, tmp_path, capsys):
    config_path = tmp_path / "config.toml"
    monkeypatch.setenv("DEEPSEEK_PROXY_CONFIG", str(config_path))

    assert default_config_path() == config_path
    assert main(["config", "path"]) == 0

    out = capsys.readouterr().out.strip()
    assert out == str(config_path)


def test_cli_config_init_writes_default_config(monkeypatch, tmp_path, capsys):
    config_path = tmp_path / "config.toml"
    monkeypatch.setenv("DEEPSEEK_PROXY_CONFIG", str(config_path))

    assert main(["config", "init"]) == 0

    data = json.loads(capsys.readouterr().out)
    assert data["path"] == str(config_path)
    assert data["created_or_overwritten"] is True

    text = config_path.read_text(encoding="utf-8")
    assert "[server]" in text
    assert "thinking_port = 8001" in text
    assert 'model = "deepseek-v4-pro"' in text
    assert 'compaction_policy = "adaptive"' in text


def test_cli_doctor_allow_down_returns_zero(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("DEEPSEEK_PROXY_CONFIG", str(tmp_path / "config.toml"))

    assert main(["doctor", "--thinking", "--port", "9", "--timeout", "0.05", "--allow-down"]) == 0

    data = json.loads(capsys.readouterr().out)
    assert data["proxy_version"].startswith("v2.4a1-")
    assert data["target"] == "thinking"
    assert data["port"] == 9
    assert data["ok"] is False


def test_cli_logs_reads_tail(tmp_path, capsys):
    log_path = tmp_path / "proxy.log"
    log_path.write_text("a\nb\nc\n", encoding="utf-8")

    assert main(["logs", "--log-file", str(log_path), "--lines", "2"]) == 0

    out = capsys.readouterr().out.strip().splitlines()
    assert out == ["b", "c"]
