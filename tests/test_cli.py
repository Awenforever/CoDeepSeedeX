from __future__ import annotations

import json

from deepseek_responses_proxy.cli import default_config_path, main


def test_cli_version(capsys):
    assert main(["--version"]) == 0
    out = capsys.readouterr().out
    assert "v2.4a1a1-cli-start-version-and-port-guard" in out


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
    assert data["proxy_version"].startswith("v2.4a1a1-")
    assert data["target"] == "thinking"
    assert data["port"] == 9
    assert data["ok"] is False


def test_cli_logs_reads_tail(tmp_path, capsys):
    log_path = tmp_path / "proxy.log"
    log_path.write_text("a\nb\nc\n", encoding="utf-8")

    assert main(["logs", "--log-file", str(log_path), "--lines", "2"]) == 0

    out = capsys.readouterr().out.strip().splitlines()
    assert out == ["b", "c"]



def test_cli_start_rejects_different_running_proxy_version(monkeypatch, tmp_path, capsys):
    import deepseek_responses_proxy.cli as cli

    monkeypatch.setattr(cli, "_healthz_for_port", lambda port, timeout=1.0: (200, {"version": "v0.old"}, None))
    monkeypatch.setattr(cli, "_tcp_port_open", lambda host, port: True)

    rc = cli.main([
        "start",
        "--thinking",
        "--port",
        "8765",
        "--pid-file",
        str(tmp_path / "missing.pid"),
    ])

    assert rc == 1
    data = json.loads(capsys.readouterr().out)
    assert data["error"] == "port_in_use_by_different_proxy_version"
    assert data["expected_version"].startswith("v2.4a1a1-")
    assert data["running_version"] == "v0.old"


def test_cli_start_accepts_matching_running_proxy_version(monkeypatch, capsys):
    import deepseek_responses_proxy.cli as cli

    monkeypatch.setattr(
        cli,
        "_healthz_for_port",
        lambda port, timeout=1.0: (200, {"version": cli.PROXY_VERSION}, None),
    )

    rc = cli.main(["start", "--thinking", "--port", "8766"])

    assert rc == 0
    out = capsys.readouterr().out
    assert "already_running" in out
    assert cli.PROXY_VERSION in out


def test_cli_doctor_reports_version_mismatch(monkeypatch, tmp_path, capsys):
    import deepseek_responses_proxy.cli as cli

    monkeypatch.setenv("DEEPSEEK_PROXY_CONFIG", str(tmp_path / "config.toml"))

    def fake_http_json(url, timeout=3.0):
        if url.endswith("/healthz"):
            return 200, {"version": "v0.old"}, None
        return 200, {"version": "v0.old", "store": {"type": "fake"}}, None

    monkeypatch.setattr(cli, "_http_json", fake_http_json)

    rc = cli.main(["doctor", "--thinking", "--port", "8767", "--allow-down"])

    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert data["ok"] is False
    assert data["healthz"]["version_match"] is False
    assert data["proxy_status"]["version_match"] is False
