from __future__ import annotations

import json

from deepseek_responses_proxy.cli import default_config_path, main


def test_cli_version(capsys):
    assert main(["--version"]) == 0
    out = capsys.readouterr().out
    assert "v2.7a6a1-compact-policy-budget-event" in out


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
    assert data["proxy_version"].startswith("v2.7a6a1-compact-policy-budget-event")
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
    assert data["expected_version"].startswith("v2.7a6a1-compact-policy-budget-event")
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



def test_cli_install_codex_profile_writes_profile(tmp_path, capsys):
    config_path = tmp_path / "config.toml"
    config_path.write_text('model = "gpt-5.4"\n\n[features]\nmemories = true\n', encoding="utf-8")

    assert main([
        "install-codex-profile",
        "--path",
        str(config_path),
        "--name",
        "deepseek-thinking",
        "--base-url",
        "http://127.0.0.1:8001/v1",
        "--model",
        "deepseek-v4-pro",
        "--no-backup",
    ]) == 0

    result = json.loads(capsys.readouterr().out)
    assert result["profile"] == "deepseek-thinking"
    assert result["provider"] == "deepseek-thinking-proxy"

    text = config_path.read_text(encoding="utf-8")
    assert "[features]" in text
    assert "[model_providers.deepseek-thinking-proxy]" in text
    assert 'base_url = "http://127.0.0.1:8001/v1"' in text
    assert "[profiles.deepseek-thinking]" in text
    assert 'model = "deepseek-v4-pro"' in text
    assert 'model_provider = "deepseek-thinking-proxy"' in text
    assert 'model_reasoning_effort = "xhigh"' in text


def test_cli_install_codex_profile_dry_run_does_not_write(tmp_path, capsys):
    config_path = tmp_path / "config.toml"

    assert main([
        "install-codex-profile",
        "--path",
        str(config_path),
        "--dry-run",
    ]) == 0

    result = json.loads(capsys.readouterr().out)
    assert result["dry_run"] is True
    assert "[profiles.deepseek-thinking]" in result["config_preview"]
    assert not config_path.exists()


def test_cli_uninstall_codex_profile_removes_profile_and_provider(tmp_path, capsys):
    config_path = tmp_path / "config.toml"
    assert main([
        "install-codex-profile",
        "--path",
        str(config_path),
        "--no-backup",
    ]) == 0
    capsys.readouterr()

    assert main([
        "uninstall-codex-profile",
        "--path",
        str(config_path),
        "--no-backup",
    ]) == 0

    result = json.loads(capsys.readouterr().out)
    assert result["profile_removed"] is True
    assert result["provider_removed"] is True

    text = config_path.read_text(encoding="utf-8")
    assert "[profiles.deepseek-thinking]" not in text
    assert "[model_providers.deepseek-thinking-proxy]" not in text


def test_cli_config_set_model_updates_env_and_codex_profile(tmp_path, capsys):
    config_path = tmp_path / "codex.toml"
    env_file = tmp_path / "env"
    config_path.write_text("[profiles.deepseek-thinking]\nmodel = \"deepseek-v4-pro\"\nmodel_provider = \"deepseek-thinking-proxy\"\n", encoding="utf-8")
    assert main(["config", "set-model", "deepseek-v4-flash", "--env-file", str(env_file), "--codex-config", str(config_path)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["model"] == "deepseek-v4-flash"
    assert result["codex_profile_patched"] is True
    assert "DEEPSEEK_PROXY_MODEL=deepseek-v4-flash" in env_file.read_text(encoding="utf-8")
    assert 'model = "deepseek-v4-flash"' in config_path.read_text(encoding="utf-8")


def test_cli_config_set_effort_updates_env_and_codex_profile(tmp_path, capsys):
    config_path = tmp_path / "codex.toml"
    env_file = tmp_path / "env"
    config_path.write_text("[profiles.deepseek-thinking]\nmodel = \"deepseek-v4-pro\"\n", encoding="utf-8")
    assert main(["config", "set-effort", "high", "--env-file", str(env_file), "--codex-config", str(config_path)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["effort"] == "high"
    assert result["codex_profile_patched"] is True
    assert "DEEPSEEK_REASONING_EFFORT=high" in env_file.read_text(encoding="utf-8")
    assert 'model_reasoning_effort = "high"' in config_path.read_text(encoding="utf-8")


def test_cli_balance_missing_api_key(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    assert main(["balance", "--env-file", str(tmp_path / "missing.env")]) == 1
    result = json.loads(capsys.readouterr().out)
    assert result["error"] == "missing_deepseek_api_key"

def test_cli_upgrade_dry_run_outputs_plan(monkeypatch, tmp_path, capsys):
    import deepseek_responses_proxy.cli as cli

    repo = tmp_path / "repo"
    repo.mkdir()

    class FakeCompleted:
        def __init__(self, returncode=0, stdout="", stderr=""):
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    def fake_run(argv, **kwargs):
        if argv[:3] == ["git", "-C", str(repo)] and argv[3:] == ["rev-parse", "--show-toplevel"]:
            return FakeCompleted(stdout=str(repo) + "\n")
        if argv[:3] == ["git", "-C", str(repo)] and argv[3:] == ["status", "--porcelain"]:
            return FakeCompleted(stdout="")
        raise AssertionError(f"unexpected command: {argv}")

    monkeypatch.setattr(cli.subprocess, "run", fake_run)

    assert main([
        "upgrade",
        "--repo",
        str(repo),
        "--tag",
        "v9.9-test",
        "--dry-run",
        "--skip-profile",
        "--no-restart",
    ]) == 0

    data = json.loads(capsys.readouterr().out)
    assert data["status"] == "ok"
    assert data["dry_run"] is True
    assert data["target_ref"] == "v9.9-test"
    assert data["mode"] == "dsproxy_upgrade"

    commands = [" ".join(step["cmd"]) for step in data["steps"]]
    assert any("git" in cmd and "fetch --tags origin" in cmd for cmd in commands)
    assert any("git" in cmd and "checkout v9.9-test" in cmd for cmd in commands)
    assert any("pip install -e" in cmd for cmd in commands)
    assert not any("install-codex-profile" in cmd for cmd in commands)
    assert not any(" start" in cmd or " stop" in cmd for cmd in commands)


def test_cli_upgrade_rejects_non_git_checkout_with_one_line_hint(monkeypatch, tmp_path, capsys):
    import deepseek_responses_proxy.cli as cli

    repo = tmp_path / "not-git"
    repo.mkdir()

    class FakeCompleted:
        def __init__(self, returncode=0, stdout="", stderr=""):
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    def fake_run(argv, **kwargs):
        if argv[:3] == ["git", "-C", str(repo)] and argv[3:] == ["rev-parse", "--show-toplevel"]:
            return FakeCompleted(returncode=128, stderr="not a git repository")
        raise AssertionError(f"unexpected command: {argv}")

    monkeypatch.setattr(cli.subprocess, "run", fake_run)

    assert main(["upgrade", "--repo", str(repo), "--dry-run"]) == 1

    data = json.loads(capsys.readouterr().out)
    assert data["status"] == "error"
    assert data["error"] == "not_a_git_checkout"
    assert "install.sh" in data["one_line_upgrade"]



def test_cli_upgrade_dry_run_defaults_to_latest_master(monkeypatch, tmp_path, capsys):
    import deepseek_responses_proxy.cli as cli

    repo = tmp_path / "repo"
    repo.mkdir()

    class FakeCompleted:
        def __init__(self, returncode=0, stdout="", stderr=""):
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    def fake_run(argv, **kwargs):
        if argv[:3] == ["git", "-C", str(repo)] and argv[3:] == ["rev-parse", "--show-toplevel"]:
            return FakeCompleted(stdout=str(repo) + "\n")
        if argv[:3] == ["git", "-C", str(repo)] and argv[3:] == ["status", "--porcelain"]:
            return FakeCompleted(stdout="")
        raise AssertionError(f"unexpected command: {argv}")

    monkeypatch.setattr(cli.subprocess, "run", fake_run)

    assert main([
        "upgrade",
        "--repo",
        str(repo),
        "--dry-run",
        "--skip-profile",
        "--no-restart",
    ]) == 0

    data = json.loads(capsys.readouterr().out)
    assert data["status"] == "ok"
    assert data["dry_run"] is True
    assert data["target_ref"] == "master"
    assert data["target_source"] == "latest_master"

    commands = [" ".join(step["cmd"]) for step in data["steps"]]
    assert any("fetch --tags origin" in cmd for cmd in commands)
    assert any("checkout master" in cmd for cmd in commands)
    assert any("pull --ff-only origin master" in cmd for cmd in commands)


def test_cli_debug_status(monkeypatch, capsys):
    import deepseek_responses_proxy.cli as cli

    calls = []

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps({
                "status": "ok",
                "debug_trace": {
                    "enabled": True,
                    "trace_count": 1,
                },
            }).encode("utf-8")

    def fake_urlopen(url, timeout=0):
        calls.append((url, timeout))
        return FakeResponse()

    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)

    assert cli.main(["debug", "status", "--port", "8123", "--timeout", "0.5"]) == 0
    data = json.loads(capsys.readouterr().out)

    assert data["status"] == "ok"
    assert data["proxy_url"] == "http://127.0.0.1:8123"
    assert data["debug_command"] == "status"
    assert data["result"]["json"]["debug_trace"]["enabled"] is True
    assert calls == [("http://127.0.0.1:8123/v1/proxy/debug/status", 0.5)]


def test_cli_debug_latest_uses_limit_and_thinking_port(monkeypatch, capsys):
    import deepseek_responses_proxy.cli as cli

    calls = []

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps({
                "status": "ok",
                "events": [{"event": "request_received"}],
            }).encode("utf-8")

    def fake_urlopen(url, timeout=0):
        calls.append((url, timeout))
        return FakeResponse()

    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)

    assert cli.main(["debug", "latest", "--thinking", "--limit", "50"]) == 0
    data = json.loads(capsys.readouterr().out)

    assert data["status"] == "ok"
    assert data["proxy_url"] == "http://127.0.0.1:8001"
    assert data["debug_command"] == "latest"
    assert data["result"]["json"]["events"][0]["event"] == "request_received"
    assert calls == [("http://127.0.0.1:8001/v1/proxy/debug/latest?limit=50", 3.0)]


def test_cli_debug_returns_nonzero_when_proxy_unreachable(monkeypatch, capsys):
    import deepseek_responses_proxy.cli as cli

    def fake_urlopen(url, timeout=0):
        raise OSError("connection refused")

    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)

    assert cli.main(["debug", "status", "--port", "9"]) == 1
    data = json.loads(capsys.readouterr().out)

    assert data["status"] == "error"
    assert data["result"]["ok"] is False
    assert "connection refused" in data["result"]["error"]


def test_cli_debug_budget_extracts_context_budget(monkeypatch, capsys):
    import deepseek_responses_proxy.cli as cli

    calls = []

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps({
                "status": "ok",
                "trace_path": ".debug/traces/trace-resp_budget.jsonl",
                "events": [
                    {
                        "event": "context_budget_breakdown",
                        "response_id": "resp_budget",
                        "chat_payload_chars": 247930,
                        "chat_payload_tool_count": 37,
                        "messages_for_deepseek": {
                            "message_count": 128,
                            "total_chars": 212783,
                            "roles": {
                                "user": {"count": 60, "chars": 120000},
                                "assistant": {"count": 60, "chars": 90000},
                            },
                        },
                        "compaction": {
                            "reason": "not_triggered",
                            "effective_trigger_chars": 1250000,
                        },
                    },
                    {
                        "event": "tool_output_budget_breakdown",
                        "function_call_count": 36,
                        "function_call_output_count": 36,
                        "function_call_output_chars": 191260,
                        "largest_outputs": [
                            {
                                "index": 13,
                                "call_id": "call_large",
                                "tool_name": "shell",
                                "item_chars": 41290,
                                "output_chars": 41000,
                            }
                        ],
                        "trim_dry_run": {
                            "mode": "dry_run",
                            "applied": False,
                            "would_trim": True,
                            "would_trim_item_count": 1,
                            "would_remove_chars_estimate": 35000,
                            "estimated_total_output_chars_before": 191260,
                            "estimated_total_output_chars_after": 156260,
                            "target_total_output_chars": 80000,
                            "unmet_total_budget_chars": 76260,
                            "total_budget_reachable": False,
                            "targets": [
                                {
                                    "call_id": "call_large",
                                    "tool_name": "shell",
                                    "estimated_remove_chars": 35000,
                                }
                            ],
                        },
                        "policy_dry_run": {
                            "enabled": True,
                            "applied": False,
                            "would_trim": True,
                            "would_trim_item_count": 1,
                            "would_remove_chars_estimate": 36000,
                            "estimated_total_output_chars_before": 191260,
                            "estimated_total_output_chars_after": 155260,
                            "target_total_output_chars": 80000,
                            "unmet_total_budget_chars": 75260,
                            "total_budget_reachable": False,
                            "category_counts": {"shell_command": 1},
                            "would_remove_chars_by_category": {"shell_command": 36000},
                            "targets": [
                                {
                                    "call_id": "call_large",
                                    "tool_name": "shell",
                                    "category": "shell_command",
                                    "policy_name": "shell_command",
                                    "estimated_remove_chars": 36000,
                                }
                            ],
                        },
                    },
                    {
                        "event": "upstream_call_finished",
                        "purpose": "primary",
                        "usage": {
                            "prompt_tokens": 71042,
                            "cached_tokens": 69632,
                        },
                    },
                ],
            }).encode("utf-8")

    def fake_urlopen(url, timeout=0):
        calls.append((url, timeout))
        return FakeResponse()

    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)

    assert cli.main(["debug", "budget", "--port", "8123", "--limit", "25"]) == 0
    data = json.loads(capsys.readouterr().out)

    assert data["status"] == "ok"
    assert data["debug_command"] == "budget"
    assert data["budget"]["found"] is True
    assert data["budget"]["event"]["chat_payload_chars"] == 247930
    assert data["budget"]["event"]["chat_payload_tool_count"] == 37
    assert data["budget"]["tool_output_budget"]["function_call_output_chars"] == 191260
    assert data["budget"]["tool_output_budget"]["largest_outputs"][0]["tool_name"] == "shell"
    assert data["budget"]["tool_output_budget"]["trim_dry_run"]["would_trim"] is True
    assert data["budget"]["tool_output_budget"]["trim_dry_run"]["would_remove_chars_estimate"] == 35000
    assert data["budget"]["tool_output_budget"]["trim_dry_run"]["total_budget_reachable"] is False
    assert data["budget"]["tool_output_budget"]["trim_dry_run"]["unmet_total_budget_chars"] == 76260
    assert data["budget"]["tool_output_budget"]["policy_dry_run"]["would_trim"] is True
    assert data["budget"]["tool_output_budget"]["policy_dry_run"]["targets"][0]["category"] == "shell_command"
    assert data["budget"]["primary_usage"]["usage"]["prompt_tokens"] == 71042
    assert calls == [("http://127.0.0.1:8123/v1/proxy/debug/latest?limit=25", 3.0)]


def test_cli_debug_budget_marks_truncated_tool_output_event(monkeypatch, capsys):
    import deepseek_responses_proxy.cli as cli

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps({
                "status": "ok",
                "events": [
                    {
                        "event": "context_budget_breakdown",
                        "chat_payload_chars": 123,
                    },
                    {
                        "event": "tool_output_budget_breakdown",
                        "truncated_event": True,
                        "original_chars": 13319,
                        "keys": ["policy_dry_run", "trim_dry_run"],
                    },
                ],
            }).encode("utf-8")

    monkeypatch.setattr(cli.urllib.request, "urlopen", lambda url, timeout=0: FakeResponse())

    assert cli.main(["debug", "budget", "--port", "8123"]) == 0
    data = json.loads(capsys.readouterr().out)

    assert data["budget"]["tool_output_budget_truncated"] is True
    assert data["budget"]["tool_output_budget_error"] == "tool_output_budget_event_truncated"
