from __future__ import annotations

import json

import deepseek_responses_proxy.cli as cli_module
from deepseek_responses_proxy.cli import default_config_path, main


def test_cli_version(capsys):
    assert main(["--version"]) == 0
    out = capsys.readouterr().out
    assert "public version: v0.3.7-alpha |" in out
    assert "internal version: p" in out


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
    assert data["proxy_version"] == cli_module.PROXY_VERSION
    assert data["target"] == "thinking"
    assert data["port"] == 9
    assert data["ok"] is False


def test_cli_logs_reads_tail(tmp_path, capsys):
    log_path = tmp_path / "proxy.log"
    log_path.write_text("a\nb\nc\n", encoding="utf-8")

    assert main(["logs", "--log-file", str(log_path), "--lines", "2"]) == 0

    out = capsys.readouterr().out.strip().splitlines()
    assert out == ["b", "c"]




def test_cli_start_thinking_defaults_tool_output_trim_rollout(monkeypatch, tmp_path):
    captured = {}
    process_started = {"value": False}

    class FakeProcess:
        pid = 12345

        def poll(self):
            return None

    monkeypatch.setenv("DEEPSEEK_PROXY_STATE_DIR", str(tmp_path))
    monkeypatch.delenv("DEEPSEEK_PROXY_TOOL_OUTPUT_TRIM_MODE", raising=False)
    monkeypatch.delenv("DEEPSEEK_PROXY_TOOL_OUTPUT_IMAGE_PAYLOAD_MAX_ITEM_CHARS", raising=False)
    def fake_tcp_port_open(host, port):
        return process_started["value"]

    monkeypatch.setattr("deepseek_responses_proxy.cli._tcp_port_open", fake_tcp_port_open)

    def fake_healthz_for_port(port, *, timeout=1.0):
        if not process_started["value"]:
            return None, None, "connection_refused"
        return 200, {
            "status": "ok",
            "version": cli_module.PROXY_VERSION,
        }, None

    monkeypatch.setattr("deepseek_responses_proxy.cli._healthz_for_port", fake_healthz_for_port)

    def fake_popen(cmd, env=None, stdout=None, stderr=None, cwd=None, start_new_session=None):
        process_started["value"] = True
        captured["cmd"] = cmd
        captured["env"] = env or {}
        captured["cwd"] = cwd
        return FakeProcess()

    monkeypatch.setattr("subprocess.Popen", fake_popen)

    assert main(["start", "--thinking", "--port", "8766", "--state-dir", str(tmp_path)]) == 0

    assert captured["env"]["DEEPSEEK_THINKING"] == "enabled"
    assert captured["env"]["DEEPSEEK_PROXY_TOOL_OUTPUT_TRIM_MODE"] == "enabled"
    assert captured["env"]["DEEPSEEK_PROXY_TOOL_OUTPUT_IMAGE_PAYLOAD_MAX_ITEM_CHARS"] == "12000"


def test_cli_start_stable_does_not_default_tool_output_trim_rollout(monkeypatch, tmp_path):
    captured = {}
    process_started = {"value": False}

    class FakeProcess:
        pid = 12346

        def poll(self):
            return None

    monkeypatch.setenv("DEEPSEEK_PROXY_STATE_DIR", str(tmp_path))
    monkeypatch.delenv("DEEPSEEK_PROXY_TOOL_OUTPUT_TRIM_MODE", raising=False)
    monkeypatch.delenv("DEEPSEEK_PROXY_TOOL_OUTPUT_IMAGE_PAYLOAD_MAX_ITEM_CHARS", raising=False)
    def fake_tcp_port_open(host, port):
        return process_started["value"]

    monkeypatch.setattr("deepseek_responses_proxy.cli._tcp_port_open", fake_tcp_port_open)

    def fake_healthz_for_port(port, *, timeout=1.0):
        if not process_started["value"]:
            return None, None, "connection_refused"
        return 200, {
            "status": "ok",
            "version": cli_module.PROXY_VERSION,
        }, None

    monkeypatch.setattr("deepseek_responses_proxy.cli._healthz_for_port", fake_healthz_for_port)

    def fake_popen(cmd, env=None, stdout=None, stderr=None, cwd=None, start_new_session=None):
        process_started["value"] = True
        captured["cmd"] = cmd
        captured["env"] = env or {}
        captured["cwd"] = cwd
        return FakeProcess()

    monkeypatch.setattr("subprocess.Popen", fake_popen)

    assert main(["start", "--port", "8765", "--state-dir", str(tmp_path)]) == 0

    assert "DEEPSEEK_THINKING" not in captured["env"]
    assert "DEEPSEEK_PROXY_TOOL_OUTPUT_TRIM_MODE" not in captured["env"]
    assert "DEEPSEEK_PROXY_TOOL_OUTPUT_IMAGE_PAYLOAD_MAX_ITEM_CHARS" not in captured["env"]


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
    assert data["expected_version"] == cli_module.PROXY_VERSION
    assert data["running_version"] == "v0.old"


def test_cli_start_accepts_matching_running_proxy_version(monkeypatch, capsys):
    import deepseek_responses_proxy.cli as cli

    monkeypatch.setattr(
        cli,
        "_healthz_for_port",
        lambda port, timeout=1.0: (200, {"version": cli_module.PROXY_VERSION}, None),
    )

    rc = cli.main(["start", "--thinking", "--port", "8766"])

    assert rc == 0
    out = capsys.readouterr().out
    assert "already_running" in out
    assert cli_module.PROXY_VERSION in out


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

    class FakeUrlResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b'{"tag_name":"v9.9-latest"}'

    monkeypatch.setattr(cli.subprocess, "run", fake_run)
    monkeypatch.setattr(cli.urllib.request, "urlopen", lambda request, timeout=0: FakeUrlResponse())

    assert main(["upgrade", "--repo", str(repo), "--dry-run"]) == 1

    data = json.loads(capsys.readouterr().out)
    assert data["status"] == "error"
    assert data["error"] == "not_a_git_checkout"
    assert "bootstrap.sh" in data["one_line_upgrade"]
    assert "releases/latest/download/bootstrap.sh" in data["one_line_upgrade"]



def test_cli_upgrade_dry_run_defaults_to_latest_release(monkeypatch, tmp_path, capsys):
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

    class FakeUrlResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b'{"tag_name":"v9.9-latest","name":"CoDeepSeedeX v9.9-latest","html_url":"https://example.test/release"}'

    def fake_urlopen(request, timeout=0):
        assert "releases/latest" in request.full_url
        return FakeUrlResponse()

    monkeypatch.setattr(cli.subprocess, "run", fake_run)
    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)

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
    assert data["target_ref"] == "v9.9-latest"
    assert data["target_source"] == "latest_release"
    assert data["latest_release"]["tag_name"] == "v9.9-latest"

    commands = [" ".join(step["cmd"]) for step in data["steps"]]
    assert any("fetch --tags origin" in cmd for cmd in commands)
    assert any("checkout v9.9-latest" in cmd for cmd in commands)
    assert not any("checkout master" in cmd for cmd in commands)
    assert not any("pull --ff-only origin master" in cmd for cmd in commands)
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


def test_cli_debug_behavioral_summarizes_long_session_readiness(monkeypatch, capsys):
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
                "kind": "runtime_long_session_observability",
                "trace_event_count": 12,
                "response_count": 4,
                "context_budget": {
                    "event_count": 2,
                    "latest_chars": 260000,
                    "max_chars": 300000,
                },
                "primary_usage": {
                    "event_count": 2,
                    "latest_prompt_tokens": 92000,
                    "max_prompt_tokens": 98000,
                },
                "tool_output_trim": {
                    "event_count": 3,
                    "applied_count": 1,
                    "chars_removed": 66000,
                    "image_payload_trim_count": 0,
                    "by_category": {
                        "shell_command": {
                            "trimmed_item_count": 1,
                            "estimated_remove_chars": 42000,
                        },
                        "interactive_shell": {
                            "trimmed_item_count": 1,
                            "estimated_remove_chars": 24000,
                        },
                    },
                },
                "recommendation": "monitor_limited_enabled_session",
            }).encode("utf-8")

    seen_urls = []

    def fake_urlopen(url, timeout=0):
        seen_urls.append((str(url), timeout))
        return FakeResponse()

    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)

    assert cli.main(["debug", "behavioral", "--port", "8123", "--limit", "25"]) == 0
    data = json.loads(capsys.readouterr().out)

    assert data["status"] == "ok"
    assert data["debug_command"] == "behavioral"
    assert "long_session" not in data
    assert data["behavioral"]["status"] == "ready"
    assert data["behavioral"]["recommendation"] == "ready_for_real_long_session_behavioral_test"
    assert data["behavioral"]["assertions"]["has_context_budget"] is True
    assert data["behavioral"]["assertions"]["has_primary_usage"] is True
    assert data["behavioral"]["assertions"]["has_tool_output_trim_applied"] is True
    assert data["behavioral"]["assertions"]["has_development_continuity_categories"] is True
    assert data["behavioral"]["metrics"]["tool_output_trim_chars_removed"] == 66000
    assert data["behavioral"]["metrics"]["trimmed_categories"] == ["interactive_shell", "shell_command"]
    assert seen_urls == [("http://127.0.0.1:8123/v1/proxy/debug/long-session?limit=25&mode=aggregate", 3.0)]


def test_cli_debug_long_session_fetches_long_session_endpoint(monkeypatch, capsys):
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
                "kind": "runtime_long_session_observability",
                "context_budget": {
                    "latest_chars": 2400,
                    "max_chars": 2400,
                },
                "semantic_payload": {
                    "event_count": 2,
                    "applied_count": 1,
                },
                "recommendation": "monitor_limited_enabled_session",
            }).encode("utf-8")

    seen_urls = []

    def fake_urlopen(url, timeout=0):
        seen_urls.append((str(url), timeout))
        return FakeResponse()

    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)

    assert cli.main(["debug", "long-session", "--port", "8123", "--limit", "25", "--mode", "aggregate"]) == 0
    data = json.loads(capsys.readouterr().out)

    assert data["debug_command"] == "long-session"
    assert data["long_session"]["kind"] == "runtime_long_session_observability"
    assert data["long_session"]["context_budget"]["latest_chars"] == 2400
    assert data["long_session"]["semantic_payload"]["applied_count"] == 1
    assert seen_urls == [("http://127.0.0.1:8123/v1/proxy/debug/long-session?limit=25&mode=aggregate", 3.0)]


def test_cli_debug_semantic_canary_check_fetches_canary_endpoint(monkeypatch, capsys):
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
                "kind": "semantic_compaction_canary_check",
                "ready_for_limited_enabled_session": True,
            }).encode("utf-8")

    seen_urls = []

    def fake_urlopen(url, timeout=0):
        seen_urls.append(str(url))
        return FakeResponse()

    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)

    assert cli.main(["debug", "semantic", "--canary-check", "--port", "8123"]) == 0
    data = json.loads(capsys.readouterr().out)

    assert data["debug_command"] == "semantic"
    assert data["canary_check"] is True
    assert data["semantic_canary_check"]["kind"] == "semantic_compaction_canary_check"
    assert data["semantic_canary_check"]["ready_for_limited_enabled_session"] is True
    assert any("/v1/proxy/debug/semantic-canary-check" in url for url in seen_urls)


def test_cli_debug_semantic_self_test_fetches_selftest_endpoint(monkeypatch, capsys):
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
                "kind": "semantic_compaction_selftest",
                "assertions": {
                    "low_risk_test_output_compacted": True,
                    "medium_stacktrace_preserved": True,
                    "high_chatty_terminal_preserved": True,
                },
            }).encode("utf-8")

    seen_urls = []

    def fake_urlopen(url, timeout=0):
        seen_urls.append(str(url))
        return FakeResponse()

    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)

    assert cli.main(["debug", "semantic", "--self-test", "--port", "8123"]) == 0
    data = json.loads(capsys.readouterr().out)

    assert data["debug_command"] == "semantic"
    assert data["self_test"] is True
    assert data["semantic_selftest"]["kind"] == "semantic_compaction_selftest"
    assert data["semantic_selftest"]["assertions"]["low_risk_test_output_compacted"] is True
    assert any("/v1/proxy/debug/semantic-selftest" in url for url in seen_urls)


def test_cli_debug_semantic_combines_status_and_trace_events(monkeypatch, capsys):
    import deepseek_responses_proxy.cli as cli

    class FakeResponse:
        status = 200

        def __init__(self, payload):
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps(self.payload).encode("utf-8")

    def fake_urlopen(url, timeout=0):
        url_text = str(url)
        if "/v1/proxy/status" in url_text:
            return FakeResponse({
                "status": "ok",
                "semantic_compaction": {
                    "config": {
                        "semantic_payload_compaction": {
                            "mode": "dry_run",
                            "enabled": False,
                        }
                    },
                    "latest": {},
                    "rollout": {
                        "safe_to_enable_payload_compaction": True,
                        "recommendation": "safe_to_enable_for_limited_session",
                    },
                },
            })
        if "/v1/proxy/debug/latest" in url_text:
            return FakeResponse({
                "status": "ok",
                "events": [
                    {"event": "flattened_tool_transcript_semantic_audit", "flattened_message_count": 2},
                    {"event": "flattened_tool_transcript_semantic_policy_dry_run", "would_compact": True},
                    {
                        "event": "flattened_tool_transcript_semantic_payload_compaction_applied",
                        "mode": "dry_run",
                        "applied": False,
                    },
                ],
            })
        raise AssertionError(url_text)

    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)

    assert cli.main(["debug", "semantic", "--port", "8123", "--limit", "25"]) == 0
    data = json.loads(capsys.readouterr().out)

    assert data["debug_command"] == "semantic"
    semantic = data["semantic"]
    assert semantic["status_semantic_compaction"]["rollout"]["safe_to_enable_payload_compaction"] is True
    assert semantic["trace_semantic_compaction"]["semantic_audit"]["found"] is True
    assert semantic["trace_semantic_compaction"]["semantic_policy_dry_run"]["event"]["would_compact"] is True
    assert semantic["trace_semantic_compaction"]["semantic_payload_compaction"]["event"]["mode"] == "dry_run"


def test_cli_debug_budget_extracts_semantic_compaction_events(monkeypatch, capsys):
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
                        "chat_payload_chars": 1000,
                    },
                    {
                        "event": "flattened_tool_transcript_semantic_audit",
                        "flattened_message_count": 3,
                    },
                    {
                        "event": "flattened_tool_transcript_semantic_policy_dry_run",
                        "would_compact": True,
                        "would_remove_chars_estimate": 1200,
                    },
                    {
                        "event": "flattened_tool_transcript_semantic_payload_compaction_applied",
                        "mode": "dry_run",
                        "applied": False,
                        "reason": "semantic_payload_compaction_mode_not_enabled",
                    },
                ],
            }).encode("utf-8")

    monkeypatch.setattr(cli.urllib.request, "urlopen", lambda url, timeout=0: FakeResponse())

    assert cli.main(["debug", "budget", "--port", "8123"]) == 0
    data = json.loads(capsys.readouterr().out)

    semantic = data["budget"]["semantic_compaction"]
    assert semantic["semantic_audit"]["found"] is True
    assert semantic["semantic_audit"]["event"]["flattened_message_count"] == 3
    assert semantic["semantic_policy_dry_run"]["found"] is True
    assert semantic["semantic_policy_dry_run"]["event"]["would_compact"] is True
    assert semantic["semantic_payload_compaction"]["found"] is True
    assert semantic["semantic_payload_compaction"]["event"]["reason"] == "semantic_payload_compaction_mode_not_enabled"


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


def test_debug_behavioral_check_marks_stale_payload_monitor_not_ready():
    import deepseek_responses_proxy.cli as cli

    long_session = {
        "status": "ok",
        "kind": "runtime_long_session_observability",
        "trace_event_count": 2019,
        "response_count": 183,
        "context_budget": {
            "latest_chars": 270012,
            "max_chars": 405107,
        },
        "primary_usage": {
            "latest_prompt_tokens": 12345,
            "max_prompt_tokens": 20000,
        },
        "tool_output_trim": {
            "event_count": 54,
            "applied_count": 2,
            "chars_removed": 44822,
            "image_payload_trim_count": 0,
            "by_category": {
                "shell_command": {"trimmed_item_count": 1},
                "interactive_shell": {"trimmed_item_count": 1},
            },
        },
        "recommendation": "trace_stale_last_payload_fallback",
        "monitor_state": "trace_stale",
        "trace_stale": True,
        "current_runtime_payload_seen": True,
        "last_responses_payload_mtime": 1778420320.0,
        "last_responses_payload_size": 835048,
        "last_deepseek_payload_mtime": 1778420330.0,
        "last_deepseek_payload_size": 274166,
        "runtime_payload": {
            "tool_output_trim_marker_summary": {
                "marker_count": 2,
                "image_payload_trim_count": 2,
            }
        },
    }

    behavioral = cli._debug_behavioral_check_from_long_session(long_session)

    assert behavioral["status"] == "monitor_stale"
    assert behavioral["recommendation"] == "inspect_current_runtime_payload_or_enable_debug_trace"
    assert behavioral["assertions"]["trace_current"] is False
    assert "trace_current" in behavioral["blockers"]
    assert behavioral["metrics"]["current_runtime_payload_seen"] is True
    assert behavioral["metrics"]["monitor_state"] == "trace_stale"
    assert behavioral["metrics"]["last_responses_payload_size"] == 835048
    assert behavioral["metrics"]["last_deepseek_payload_size"] == 274166
    assert behavioral["metrics"]["runtime_payload_image_payload_trim_count"] == 2


def test_cli_config_set_api_key_writes_env_and_masks(tmp_path, capsys):
    from deepseek_responses_proxy.cli import main

    env_file = tmp_path / "env"
    assert main(["config", "set-api-key", "--skip-validation", "--env-file", str(env_file), "--value", "sk-test-123456"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "ok"
    assert result["env_file"] == str(env_file)
    assert result["deepseek_api_key_configured"] is True
    assert result["deepseek_api_key_preview"] == "sk-t...3456"
    text = env_file.read_text(encoding="utf-8")
    assert "DEEPSEEK_API_KEY=sk-test-123456" in text

    assert main(["config", "show", "--env-file", str(env_file)]) == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown["values"]["DEEPSEEK_API_KEY"] == "***"


def test_cli_config_test_api_key_reads_env_file(monkeypatch, tmp_path, capsys):
    import deepseek_responses_proxy.cli as cli

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b'{"is_available": true, "balance_infos": []}'

    seen = {}

    def fake_urlopen(request, timeout=0):
        seen["authorization"] = request.headers.get("Authorization")
        seen["timeout"] = timeout
        return FakeResponse()

    env_file = tmp_path / "env"
    env_file.write_text("export DEEPSEEK_API_KEY=sk-file-123456\n", encoding="utf-8")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)

    assert cli.main(["config", "test-api-key", "--env-file", str(env_file), "--timeout", "2"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["ok"] is True
    assert result["api_key_source"] == str(env_file)
    assert result["deepseek_api_key_preview"] == "sk-f...3456"
    assert seen["authorization"] == "Bearer sk-file-123456"
    assert seen["timeout"] == 2.0


def test_cli_install_codex_profile_writes_model_catalog_json(tmp_path, capsys):
    from deepseek_responses_proxy.cli import main

    config_path = tmp_path / "codex.toml"
    catalog_json = '"/tmp/deepseek-proxy-models.json"'
    assert main([
        "install-codex-profile",
        "--name",
        "deepseek-thinking",
        "--provider-name",
        "deepseek-thinking-proxy",
        "--base-url",
        "http://127.0.0.1:8001/v1",
        "--model",
        "deepseek-v4-pro",
        "--model-catalog-json",
        catalog_json,
        "--path",
        str(config_path),
    ]) == 0

    result = json.loads(capsys.readouterr().out)
    assert result["profile"] == "deepseek-thinking"
    text = config_path.read_text(encoding="utf-8")
    assert "model_catalog_json" in text
    assert "/tmp/deepseek-proxy-models.json" in text


def test_cli_config_set_web_search_api_key(monkeypatch, tmp_path, capsys):
    env_file = tmp_path / "env"
    rc = main([
        "config",
        "set-web-search-api-key",
        "--skip-validation",
        "--env-file",
        str(env_file),
        "--provider",
        "serpapi",
        "--value",
        "serpapi-test-key",
    ])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "ok"
    text = env_file.read_text(encoding="utf-8")
    assert "DEEPSEEK_PROXY_WEB_SEARCH_PROVIDER=serpapi" in text
    assert "SERPAPI_API_KEY=serpapi-test-key" in text
    assert "DEEPSEEK_PROXY_TOOL_BRIDGE=1" in text


def test_cli_config_set_image_api_key(monkeypatch, tmp_path, capsys):
    env_file = tmp_path / "env"
    rc = main([
        "config",
        "set-image-api-key",
        "--skip-validation",
        "--env-file",
        str(env_file),
        "--provider",
        "glm",
        "--value",
        "glm-test-key",
    ])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "ok"
    text = env_file.read_text(encoding="utf-8")
    assert "DEEPSEEK_PROXY_IMAGE_PROVIDER=glm" in text
    assert "DEEPSEEK_PROXY_IMAGE_MODEL=cogView-4-250304" in text
    assert "DEEPSEEK_PROXY_IMAGE_API_KEY=glm-test-key" in text
    assert "ZAI_API_KEY=glm-test-key" in text
    assert "DEEPSEEK_PROXY_IMAGE_BASE_URL=https://api.z.ai/api/paas/v4/images/generations" in text
    assert "DEEPSEEK_PROXY_TOOL_BRIDGE=1" in text


def test_cli_config_set_zhipu_image_api_key_sets_domestic_endpoint(tmp_path, capsys):
    from deepseek_responses_proxy.cli import main

    env_file = tmp_path / "env"
    assert main([
        "config",
        "set-image-api-key",
        "--skip-validation",
        "--env-file",
        str(env_file),
        "--provider",
        "zhipu",
        "--value",
        "zhipu-test-key",
    ]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "ok"
    assert out["image_provider"] == "zhipu"
    text = env_file.read_text(encoding="utf-8")
    assert "DEEPSEEK_PROXY_IMAGE_PROVIDER=zhipu" in text
    assert "DEEPSEEK_PROXY_IMAGE_BASE_URL=https://open.bigmodel.cn/api/paas/v4/images/generations" in text
    assert "DEEPSEEK_PROXY_IMAGE_API_KEY=zhipu-test-key" in text
    assert "ZHIPUAI_API_KEY=zhipu-test-key" in text


def test_cli_config_set_zai_image_api_key_sets_international_endpoint(tmp_path, capsys):
    from deepseek_responses_proxy.cli import main

    env_file = tmp_path / "env"
    assert main([
        "config",
        "set-image-api-key",
        "--skip-validation",
        "--env-file",
        str(env_file),
        "--provider",
        "zai",
        "--value",
        "zai-test-key",
    ]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "ok"
    assert out["image_provider"] == "zai"
    text = env_file.read_text(encoding="utf-8")
    assert "DEEPSEEK_PROXY_IMAGE_PROVIDER=zai" in text
    assert "DEEPSEEK_PROXY_IMAGE_BASE_URL=https://api.z.ai/api/paas/v4/images/generations" in text
    assert "DEEPSEEK_PROXY_IMAGE_API_KEY=zai-test-key" in text
    assert "ZAI_API_KEY=zai-test-key" in text




def test_cli_doctor_providers_lists_configured_without_live(tmp_path, capsys):
    from deepseek_responses_proxy.cli import main

    env_file = tmp_path / "env"
    env_file.write_text(
        "export SERPAPI_API_KEY=serpapi-test-key\n"
        "export DEEPSEEK_PROXY_IMAGE_PROVIDER=zhipu\n"
        "export DEEPSEEK_PROXY_IMAGE_API_KEY=zhipu-test-key\n",
        encoding="utf-8",
    )

    assert main(["doctor", "providers", "--env-file", str(env_file)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["command"] == "doctor providers"
    assert result["live"] is False
    assert result["api_key_values_logged"] is False
    assert "serpapi-test-key" not in json.dumps(result)
    assert "zhipu-test-key" not in json.dumps(result)

    providers = {(item["kind"], item["provider"]): item for item in result["results"]}
    assert providers[("web_search", "serpapi")]["configured"] is True
    assert providers[("image_generation", "zhipu")]["configured"] is True
    assert providers[("image_generation", "zai")]["configured"] is False
    assert providers[("image_generation", "qwen_image")]["configured"] is False
    assert providers[("image_generation", "stability")]["configured"] is False
    assert providers[("image_generation", "fal")]["configured"] is False


def test_cli_doctor_providers_scopes_generic_image_key_to_selected_provider(tmp_path, capsys):
    from deepseek_responses_proxy.cli import main

    env_file = tmp_path / "env"
    env_file.write_text(
        "export DEEPSEEK_PROXY_IMAGE_PROVIDER=qwen_image\n"
        "export DEEPSEEK_PROXY_IMAGE_API_KEY=generic-qwen-test-key\n",
        encoding="utf-8",
    )

    assert main(["doctor", "providers", "--env-file", str(env_file)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert "generic-qwen-test-key" not in json.dumps(result)

    providers = {(item["kind"], item["provider"]): item for item in result["results"]}
    assert providers[("image_generation", "zhipu")]["configured"] is False
    assert providers[("image_generation", "zai")]["configured"] is False
    assert providers[("image_generation", "qwen_image")]["configured"] is True
    assert providers[("image_generation", "qwen_image")]["api_key_env_key"] == "DEEPSEEK_PROXY_IMAGE_API_KEY"
    assert providers[("image_generation", "stability")]["configured"] is False
    assert providers[("image_generation", "fal")]["configured"] is False


def test_cli_doctor_providers_live_requires_allow_spend(tmp_path, capsys):
    from deepseek_responses_proxy.cli import main

    env_file = tmp_path / "env"
    env_file.write_text("export SERPAPI_API_KEY='serpapi-test-key'\n", encoding="utf-8")

    assert main(["doctor", "providers", "--env-file", str(env_file), "--kind", "web-search", "--provider", "serpapi", "--live"]) == 1
    result = json.loads(capsys.readouterr().out)
    assert result["results"][0]["error"] == "allow_spend_required"
    assert "serpapi-test-key" not in json.dumps(result)


def test_cli_doctor_providers_web_live_uses_validation(monkeypatch, tmp_path, capsys):
    import deepseek_responses_proxy.cli as cli

    env_file = tmp_path / "env"
    env_file.write_text("export SERPAPI_API_KEY='serpapi-test-key'\n", encoding="utf-8")
    seen = {}

    def fake_validate(provider, api_key, *, timeout=10.0):
        seen["provider"] = provider
        seen["api_key"] = api_key
        seen["timeout"] = timeout
        return {
            "ok": True,
            "status": "ok",
            "kind": "web_search",
            "provider": provider,
            "validation_strength": "live_query_probe",
            "functional_probe": True,
            "functional_validation": "performed",
            "may_consume_quota": True,
        }

    monkeypatch.setattr(cli, "_validate_web_search_api_key", fake_validate)

    assert cli.main([
        "doctor",
        "providers",
        "--env-file",
        str(env_file),
        "--kind",
        "web-search",
        "--provider",
        "serpapi",
        "--live",
        "--allow-spend",
        "--timeout",
        "2",
    ]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["results"][0]["probe"]["validation_strength"] == "live_query_probe"
    assert seen == {"provider": "serpapi", "api_key": "serpapi-test-key", "timeout": 2.0}
    assert "serpapi-test-key" not in json.dumps(result)


def test_cli_doctor_providers_image_live_zhipu_posts_generation(monkeypatch, tmp_path, capsys):
    import io
    import urllib.request

    import deepseek_responses_proxy.cli as cli

    env_file = tmp_path / "env"
    env_file.write_text("export DEEPSEEK_PROXY_IMAGE_API_KEY='zhipu-test-key'\n", encoding="utf-8")
    seen = {}

    class FakeHeaders(dict):
        def get(self, key, default=None):
            return super().get(key.lower(), default)

    class FakeResponse:
        status = 200
        headers = FakeHeaders({"content-type": "application/json"})

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b'{"data":[{"url":"https://example.test/zhipu-image.png"}]}'

    def fake_urlopen(request, timeout=0):
        seen["url"] = request.full_url
        seen["headers"] = dict(request.header_items())
        seen["body"] = request.data.decode("utf-8")
        seen["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)

    assert cli.main([
        "doctor",
        "providers",
        "--env-file",
        str(env_file),
        "--kind",
        "image",
        "--provider",
        "zhipu",
        "--live",
        "--allow-spend",
        "--timeout",
        "3",
        "--prompt",
        "probe image",
    ]) == 0
    result = json.loads(capsys.readouterr().out)
    probe = result["results"][0]["probe"]
    assert probe["validation_strength"] == "live_generation_probe"
    assert probe["functional_probe"] is True
    assert probe["functional_validation"] == "performed"
    assert probe["has_image"] is True
    assert probe["evidence"] == "data_url_or_base64"
    assert seen["url"] == "https://open.bigmodel.cn/api/paas/v4/images/generations"
    assert "probe image" in seen["body"]
    assert "zhipu-test-key" in seen["headers"].get("Authorization", "")
    assert "zhipu-test-key" not in json.dumps(result)



def test_lifecycle_commands_accept_positional_thinking(monkeypatch):
    import deepseek_responses_proxy.cli as cli

    calls = []
    status_base_url_calls = []
    status_http_calls = []

    def fake_start(args):
        calls.append(("start", bool(args.thinking), getattr(args, "target", None)))
        return 0

    def fake_stop(args):
        calls.append(("stop", bool(args.thinking), getattr(args, "target", None)))
        return 0

    def fake_base_url(*, thinking, port=None):
        status_base_url_calls.append((bool(thinking), port))
        return "http://127.0.0.1:8001" if thinking else "http://127.0.0.1:8000"

    def fake_http_json(url, *, timeout=10.0):
        status_http_calls.append((url, timeout))
        return 200, {"status": "ok"}, None

    monkeypatch.setattr(cli, "_start_proxy", fake_start)
    monkeypatch.setattr(cli, "_stop_proxy", fake_stop)
    monkeypatch.setattr(cli, "_base_url", fake_base_url)
    monkeypatch.setattr(cli, "_http_json", fake_http_json)

    assert cli.main(["start", "thinking"]) == 0
    assert cli.main(["stop", "thinking"]) == 0
    assert cli.main(["status", "thinking", "--timeout", "1"]) == 0

    assert calls == [
        ("start", True, "thinking"),
        ("stop", True, "thinking"),
    ]
    assert status_base_url_calls == [(True, 8001)]
    assert status_http_calls
    assert status_http_calls[-1][0].startswith("http://127.0.0.1:8001/")
    assert status_http_calls[-1][1] == 1.0


def test_lifecycle_commands_keep_thinking_flag_compatibility(monkeypatch):
    import deepseek_responses_proxy.cli as cli

    calls = []
    status_base_url_calls = []
    status_http_calls = []

    def fake_start(args):
        calls.append(("start", bool(args.thinking), getattr(args, "target", None)))
        return 0

    def fake_stop(args):
        calls.append(("stop", bool(args.thinking), getattr(args, "target", None)))
        return 0

    def fake_base_url(*, thinking, port=None):
        status_base_url_calls.append((bool(thinking), port))
        return "http://127.0.0.1:8001" if thinking else "http://127.0.0.1:8000"

    def fake_http_json(url, *, timeout=10.0):
        status_http_calls.append((url, timeout))
        return 200, {"status": "ok"}, None

    monkeypatch.setattr(cli, "_start_proxy", fake_start)
    monkeypatch.setattr(cli, "_stop_proxy", fake_stop)
    monkeypatch.setattr(cli, "_base_url", fake_base_url)
    monkeypatch.setattr(cli, "_http_json", fake_http_json)

    assert cli.main(["start", "--thinking"]) == 0
    assert cli.main(["stop", "--thinking"]) == 0
    assert cli.main(["status", "--thinking", "--timeout", "1"]) == 0

    assert calls == [
        ("start", True, None),
        ("stop", True, None),
    ]
    assert status_base_url_calls == [(True, 8001)]
    assert status_http_calls
    assert status_http_calls[-1][0].startswith("http://127.0.0.1:8001/")
    assert status_http_calls[-1][1] == 1.0

def test_cli_start_prints_latest_release_update_notice(monkeypatch, tmp_path, capsys):
    import deepseek_responses_proxy.cli as cli

    process_started = {"value": False}

    class FakeProcess:
        pid = 33333

        def poll(self):
            return None

    monkeypatch.setenv("DEEPSEEK_PROXY_RELEASE_CHECK", "always")
    monkeypatch.setenv("DEEPSEEK_PROXY_STATE_DIR", str(tmp_path))
    monkeypatch.setattr(
        cli,
        "_resolve_latest_release_tag",
        lambda *args, **kwargs: ("v0.3.3-alpha", {"html_url": "https://example.test/releases/v0.3.3-alpha"}),
    )

    def fake_tcp_port_open(host, port):
        return process_started["value"]

    def fake_healthz_for_port(port, *, timeout=1.0):
        if not process_started["value"]:
            return None, None, "connection_refused"
        return 200, {"status": "ok", "version": cli_module.PROXY_VERSION}, None

    def fake_popen(cmd, env=None, stdout=None, stderr=None, cwd=None, start_new_session=None):
        process_started["value"] = True
        return FakeProcess()

    monkeypatch.setattr(cli, "_tcp_port_open", fake_tcp_port_open)
    monkeypatch.setattr(cli, "_healthz_for_port", fake_healthz_for_port)
    monkeypatch.setattr(cli.subprocess, "Popen", fake_popen)

    assert cli.main(["start", "--port", "8876", "--state-dir", str(tmp_path)]) == 0
    err = capsys.readouterr().err
    assert "update available" in err
    assert "v0.3.3-alpha" in err
    assert "dsproxy upgrade" in err


def test_cli_start_does_not_warn_for_matching_alpha_release(monkeypatch, tmp_path, capsys):
    import deepseek_responses_proxy.cli as cli

    process_started = {"value": False}

    class FakeProcess:
        pid = 33334

        def poll(self):
            return None

    monkeypatch.setenv("DEEPSEEK_PROXY_RELEASE_CHECK", "always")
    monkeypatch.setenv("DEEPSEEK_PROXY_STATE_DIR", str(tmp_path))
    monkeypatch.setattr(
        cli,
        "_resolve_latest_release_tag",
        lambda *args, **kwargs: (cli_module.PROXY_VERSION + "-alpha", {"html_url": "https://example.test/releases/current"}),
    )

    def fake_tcp_port_open(host, port):
        return process_started["value"]

    def fake_healthz_for_port(port, *, timeout=1.0):
        if not process_started["value"]:
            return None, None, "connection_refused"
        return 200, {"status": "ok", "version": cli_module.PROXY_VERSION}, None

    def fake_popen(cmd, env=None, stdout=None, stderr=None, cwd=None, start_new_session=None):
        process_started["value"] = True
        return FakeProcess()

    monkeypatch.setattr(cli, "_tcp_port_open", fake_tcp_port_open)
    monkeypatch.setattr(cli, "_healthz_for_port", fake_healthz_for_port)
    monkeypatch.setattr(cli.subprocess, "Popen", fake_popen)

    assert cli.main(["start", "--port", "8877", "--state-dir", str(tmp_path)]) == 0
    assert "update available" not in capsys.readouterr().err


def test_cli_config_wizard_non_interactive_reports_missing(tmp_path, capsys):
    from deepseek_responses_proxy.cli import main

    env_file = tmp_path / "env"
    assert main(["config", "wizard", "--env-file", str(env_file), "--non-interactive"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["status"] == "ok"
    assert data["mode"] == "config_wizard"
    assert data["interactive"] is False
    assert data["configuration_status"]["missing"]["model_api"] is True
    assert data["configuration_status"]["missing"]["web_search_api"] is True
    assert data["configuration_status"]["missing"]["image_generation_api"] is True
    assert data["configuration_status"]["commands"]["guided"] == "dsproxy config wizard"

def test_cli_config_set_tavily_web_search_api_key(tmp_path, capsys):
    from deepseek_responses_proxy.cli import main

    env_file = tmp_path / "env"
    assert main([
        "config",
        "set-web-search-api-key",
        "--skip-validation",
        "--env-file",
        str(env_file),
        "--provider",
        "tavily",
        "--value",
        "tvly-test-key",
    ]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "ok"
    assert out["web_search_provider"] == "tavily"
    text = env_file.read_text(encoding="utf-8")
    assert "DEEPSEEK_PROXY_WEB_SEARCH_PROVIDER=tavily" in text
    assert "TAVILY_API_KEY=tvly-test-key" in text
    assert "DEEPSEEK_PROXY_TOOL_BRIDGE=1" in text
def test_cli_config_set_qwen_image_api_key(tmp_path, capsys):
    from deepseek_responses_proxy.cli import main

    env_file = tmp_path / "env"
    assert main([
        "config",
        "set-image-api-key",
        "--skip-validation",
        "--env-file",
        str(env_file),
        "--provider",
        "qwen_image",
        "--value",
        "dashscope-test-key",
    ]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "ok"
    assert out["image_provider"] == "qwen_image"
    text = env_file.read_text(encoding="utf-8")
    assert "DEEPSEEK_PROXY_IMAGE_PROVIDER=qwen_image" in text
    assert "DEEPSEEK_PROXY_IMAGE_MODEL=qwen-image-2.0-pro" in text
    assert "DEEPSEEK_PROXY_IMAGE_API_KEY=dashscope-test-key" in text
    assert "DASHSCOPE_API_KEY=dashscope-test-key" in text

def test_cli_config_set_exa_web_search_api_key(tmp_path, capsys):
    from deepseek_responses_proxy.cli import main

    env_file = tmp_path / "env"
    assert main([
        "config",
        "set-web-search-api-key",
        "--skip-validation",
        "--env-file",
        str(env_file),
        "--provider",
        "exa",
        "--value",
        "exa-test-key",
    ]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "ok"
    assert out["web_search_provider"] == "exa"
    text = env_file.read_text(encoding="utf-8")
    assert "DEEPSEEK_PROXY_WEB_SEARCH_PROVIDER=exa" in text
    assert "EXA_API_KEY=exa-test-key" in text


def test_cli_config_set_firecrawl_web_search_api_key(tmp_path, capsys):
    from deepseek_responses_proxy.cli import main

    env_file = tmp_path / "env"
    assert main([
        "config",
        "set-web-search-api-key",
        "--skip-validation",
        "--env-file",
        str(env_file),
        "--provider",
        "firecrawl",
        "--value",
        "firecrawl-test-key",
    ]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "ok"
    assert out["web_search_provider"] == "firecrawl"
    text = env_file.read_text(encoding="utf-8")
    assert "DEEPSEEK_PROXY_WEB_SEARCH_PROVIDER=firecrawl" in text
    assert "FIRECRAWL_API_KEY=firecrawl-test-key" in text


def test_cli_config_set_stability_image_api_key(tmp_path, capsys):
    from deepseek_responses_proxy.cli import main

    env_file = tmp_path / "env"
    assert main([
        "config",
        "set-image-api-key",
        "--skip-validation",
        "--env-file",
        str(env_file),
        "--provider",
        "stability",
        "--value",
        "stability-test-key",
    ]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "ok"
    assert out["image_provider"] == "stability"
    text = env_file.read_text(encoding="utf-8")
    assert "DEEPSEEK_PROXY_IMAGE_PROVIDER=stability" in text
    assert "DEEPSEEK_PROXY_IMAGE_MODEL=stable-image-core" in text
    assert "DEEPSEEK_PROXY_IMAGE_API_KEY=stability-test-key" in text
    assert "STABILITY_API_KEY=stability-test-key" in text


def test_cli_config_set_fal_image_api_key(tmp_path, capsys):
    from deepseek_responses_proxy.cli import main

    env_file = tmp_path / "env"
    assert main([
        "config",
        "set-image-api-key",
        "--skip-validation",
        "--env-file",
        str(env_file),
        "--provider",
        "fal",
        "--value",
        "fal-test-key",
    ]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "ok"
    assert out["image_provider"] == "fal"
    text = env_file.read_text(encoding="utf-8")
    assert "DEEPSEEK_PROXY_IMAGE_PROVIDER=fal" in text
    assert "DEEPSEEK_PROXY_IMAGE_MODEL=fal-ai/flux/schnell" in text
    assert "DEEPSEEK_PROXY_IMAGE_API_KEY=fal-test-key" in text
    assert "FAL_KEY=fal-test-key" in text


def test_cli_config_set_api_key_validates_before_write(monkeypatch, tmp_path, capsys):
    import deepseek_responses_proxy.cli as cli

    env_file = tmp_path / "env"

    def fake_check(api_key, *, url, timeout):
        return {
            "ok": False,
            "status": "error",
            "error": "http_error",
            "http_status": 401,
            "url": url,
        }

    monkeypatch.setattr(cli, "_check_deepseek_api_key", fake_check)

    assert cli.main(["config", "set-api-key", "--env-file", str(env_file), "--value", "bad-key"]) == 1
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "error"
    assert result["deepseek_api_key_configured"] is False
    assert not env_file.exists()


def test_cli_config_set_web_search_api_key_validates_before_write(monkeypatch, tmp_path, capsys):
    import deepseek_responses_proxy.cli as cli

    env_file = tmp_path / "env"

    def fake_validate(provider, api_key, *, timeout):
        return {
            "ok": True,
            "status": "ok",
            "kind": "web_search",
            "provider": provider,
            "validation_method": "fake",
        }

    monkeypatch.setattr(cli, "_validate_web_search_api_key", fake_validate)

    assert cli.main([
        "config",
        "set-web-search-api-key",
        "--env-file",
        str(env_file),
        "--provider",
        "tavily",
        "--value",
        "tvly-valid",
    ]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["validation"]["ok"] is True
    assert result["web_search_provider"] == "tavily"
    assert "TAVILY_API_KEY=tvly-valid" in env_file.read_text(encoding="utf-8")


def test_cli_config_set_image_api_key_validation_failure_does_not_write(monkeypatch, tmp_path, capsys):
    import deepseek_responses_proxy.cli as cli

    env_file = tmp_path / "env"

    def fake_validate(provider, api_key, *, timeout):
        return {
            "ok": False,
            "status": "error",
            "kind": "image_generation",
            "provider": provider,
            "error": "http_error",
            "http_status": 401,
        }

    monkeypatch.setattr(cli, "_validate_image_api_key", fake_validate)

    assert cli.main([
        "config",
        "set-image-api-key",
        "--env-file",
        str(env_file),
        "--provider",
        "fal",
        "--value",
        "fal-invalid",
    ]) == 1
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "error"
    assert result["image_api_key_configured"] is False
    assert not env_file.exists()


def test_cli_config_show_masks_all_api_keys(tmp_path, capsys):
    from deepseek_responses_proxy.cli import main

    env_file = tmp_path / "env"
    env_file.write_text(
        "export DEEPSEEK_API_KEY=sk-test\n"
        "export TAVILY_API_KEY=tvly-test\n"
        "export FAL_KEY=fal-test\n"
        "export DEEPSEEK_PROXY_WEB_SEARCH_PROVIDER=tavily\n",
        encoding="utf-8",
    )

    assert main(["config", "show", "--env-file", str(env_file)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["values"]["DEEPSEEK_API_KEY"] == "***"
    assert result["values"]["TAVILY_API_KEY"] == "***"
    assert result["values"]["FAL_KEY"] == "***"
    assert result["values"]["DEEPSEEK_PROXY_WEB_SEARCH_PROVIDER"] == "tavily"


def test_cli_provider_auth_error_detects_provider_specific_fields():
    import deepseek_responses_proxy.cli as cli

    assert cli._provider_auth_error_detected({
        "error": {
            "code": "1002",
            "msg": "Invalid Authentication Token, please confirm the correct transmission of the Authentication Token",
        }
    })

    assert cli._provider_auth_error_detected({
        "status_code": 401,
        "msg": "Unauthorized",
    })

    assert cli._provider_auth_error_detected({
        "code": "1210",
        "message": "Invalid API parameter, please check the documentation.",
    }) is None


def test_cli_validation_matrix_all_supported_providers(monkeypatch):
    import contextlib
    import io
    import json
    import urllib.error

    import deepseek_responses_proxy.cli as cli

    calls = []

    class FakeResponse:
        def __init__(self, status, body):
            self.status = status
            self._body = body

        def read(self):
            return self._body

    def fake_urlopen(request, timeout=0):
        calls.append({
            "url": request.full_url,
            "method": request.get_method(),
            "headers": dict(request.headers),
            "data": request.data,
            "timeout": timeout,
        })
        url = request.full_url
        if "images/generations" in url or "multimodal-generation/generation" in url:
            body = json.dumps({"error": {"code": "1210", "message": "Input cannot be empty"}}).encode("utf-8")
            raise urllib.error.HTTPError(url, 400, "Bad Request", {}, io.BytesIO(body))
        if "user/balance" in url:
            return contextlib.nullcontext(FakeResponse(200, b'{"credits": 1}'))
        if "models" in url:
            return contextlib.nullcontext(FakeResponse(200, b'{"models": []}'))
        return contextlib.nullcontext(FakeResponse(200, b'{"results": []}'))

    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)

    for provider in ("serpapi", "tavily", "exa", "firecrawl"):
        result = cli._validate_web_search_api_key(provider, "provider-test-key", timeout=2.0)
        assert result["ok"] is True
        assert result["may_consume_quota"] is True
        assert result["validation_method"] == "fixed_query_search"
        assert result["validation_strength"] == "live_query_probe"
        assert result["functional_probe"] is True
        assert result["functional_validation"] == "performed"
        assert result["may_consume_quota"] is True
        assert "may consume provider search quota" in result["warning"]

    for provider in ("glm", "zai", "zhipu", "bigmodel", "qwen_image", "stability", "fal"):
        result = cli._validate_image_api_key(provider, "provider-test-key", timeout=2.0)
        assert result["ok"] is True
        assert result["may_consume_quota"] is False
        assert result["functional_probe"] is False
        assert result["functional_validation"] == "not_performed"
        assert "does not prove that real image generation" in result["warning"]
        if provider in {"glm", "zai", "zhipu", "bigmodel", "qwen_image"}:
            assert result["validation_strength"] == "auth_probe"
        elif provider == "stability":
            assert result["validation_strength"] == "account_probe"
        elif provider == "fal":
            assert result["validation_strength"] == "metadata_probe"

    assert any("serpapi.com/search.json" in call["url"] for call in calls)
    assert any("api.tavily.com/search" in call["url"] for call in calls)
    assert any("api.exa.ai/search" in call["url"] for call in calls)
    assert any("api.firecrawl.dev/v2/search" in call["url"] for call in calls)
    assert any("api.z.ai/api/paas/v4/images/generations" in call["url"] for call in calls)
    assert any("open.bigmodel.cn/api/paas/v4/images/generations" in call["url"] for call in calls)
    assert any("dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation" in call["url"] for call in calls)
    assert any("api.stability.ai/v1/user/balance" in call["url"] for call in calls)
    assert any("api.fal.ai/v1/models" in call["url"] for call in calls)


def test_cli_non_generation_probe_rejects_empty_400_422_body(monkeypatch):
    import io
    import urllib.error

    import deepseek_responses_proxy.cli as cli

    def fake_urlopen(request, timeout=0):
        raise urllib.error.HTTPError(request.full_url, 400, "Bad Request", {}, io.BytesIO(b"{}"))

    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)

    result = cli._validate_image_api_key("glm", "provider-test-key", timeout=2.0)
    assert result["ok"] is False
    assert result["error"] == "missing_provider_error_body"
    assert result["require_provider_error_body"] is True
    assert result["validation_strength"] == "auth_probe"
    assert result["functional_probe"] is False
    assert result["functional_validation"] == "not_performed"
    assert "does not prove that real image generation" in result["warning"]


def test_cli_skipped_validation_reports_non_functional_semantics():
    import deepseek_responses_proxy.cli as cli

    result = cli._skipped_validation("image_generation", "zhipu")
    assert result["status"] == "skipped"
    assert result["validation_strength"] == "skipped"
    assert result["functional_probe"] is False
    assert result["functional_validation"] == "not_performed"


def test_cli_config_set_image_api_key_output_reports_non_functional_probe(monkeypatch, tmp_path, capsys):
    import contextlib
    import io
    import json
    import urllib.error

    import deepseek_responses_proxy.cli as cli

    env_file = tmp_path / "env"

    def fake_urlopen(request, timeout=0):
        body = json.dumps({"error": {"code": "1210", "message": "Input cannot be empty"}}).encode("utf-8")
        raise urllib.error.HTTPError(request.full_url, 400, "Bad Request", {}, io.BytesIO(body))

    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)

    assert cli.main([
        "config",
        "set-image-api-key",
        "--env-file",
        str(env_file),
        "--provider",
        "zhipu",
        "--value",
        "zhipu-test-key",
    ]) == 0
    result = json.loads(capsys.readouterr().out)
    validation = result["validation"]
    assert validation["validation_method"] == "non_generation_auth_probe"
    assert validation["validation_strength"] == "auth_probe"
    assert validation["functional_probe"] is False
    assert validation["functional_validation"] == "not_performed"
    assert "does not prove that real image generation" in validation["warning"]


def test_cli_config_set_qwen_model_api_key(tmp_path, capsys):
    from deepseek_responses_proxy.cli import main

    env_file = tmp_path / "env"
    assert main([
        "config",
        "set-api-key",
        "--skip-validation",
        "--env-file",
        str(env_file),
        "--provider",
        "qwen",
        "--value",
        "qwen-test-key",
    ]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "ok"
    assert result["model_provider"] == "qwen"
    assert result["base_url"] == "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
    assert result["model"] == "qwen-plus"
    text = env_file.read_text(encoding="utf-8")
    assert "DEEPSEEK_API_KEY=qwen-test-key" in text
    assert "DEEPSEEK_BASE_URL=https://dashscope-intl.aliyuncs.com/compatible-mode/v1" in text
    assert "DEEPSEEK_PROXY_MODEL_PROVIDER=qwen" in text
    assert "DEEPSEEK_PROXY_MODEL=qwen-plus" in text


def test_cli_config_set_custom_model_api_requires_base_url(tmp_path, capsys):
    from deepseek_responses_proxy.cli import main

    env_file = tmp_path / "env"
    assert main([
        "config",
        "set-api-key",
        "--skip-validation",
        "--env-file",
        str(env_file),
        "--provider",
        "custom",
        "--model",
        "custom-model",
        "--value",
        "custom-key",
    ]) == 1
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "error"
    assert result["error"] == "missing_custom_model_api_details"
    assert not env_file.exists()


def test_cli_config_set_kimi_model_api_validation_failure_does_not_write(monkeypatch, tmp_path, capsys):
    import deepseek_responses_proxy.cli as cli

    env_file = tmp_path / "env"

    def fake_validate(provider, api_key, *, base_url, timeout):
        return {
            "ok": False,
            "status": "error",
            "kind": "model_api",
            "provider": provider,
            "base_url": base_url,
            "error": "http_error",
            "http_status": 401,
        }

    monkeypatch.setattr(cli, "_validate_model_api_key", fake_validate)

    assert cli.main([
        "config",
        "set-api-key",
        "--env-file",
        str(env_file),
        "--provider",
        "kimi",
        "--value",
        "bad-kimi-key",
    ]) == 1
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "error"
    assert result["model_provider"] == "kimi"
    assert result["model_api_key_configured"] is False
    assert not env_file.exists()


def test_cli_config_status_lists_model_api_providers(tmp_path, capsys):
    from deepseek_responses_proxy.cli import main

    env_file = tmp_path / "env"
    assert main(["config", "wizard", "--env-file", str(env_file), "--non-interactive"]) == 0
    result = json.loads(capsys.readouterr().out)
    status = result["configuration_status"]
    assert status["commands"]["model_api"] == "dsproxy config set-api-key --provider deepseek|kimi|glm|qwen|custom"
    assert status["supported"]["model_api"] == ["deepseek", "kimi", "glm", "qwen", "custom"]
    assert status["unsupported_catalog"]["model_api"] == ["mimo", "baichuan"]


def test_cli_qwen_image_probe_payload_respects_region_endpoint_env(monkeypatch):
    import json

    import deepseek_responses_proxy.cli as cli

    endpoint = "https://dashscope-intl.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
    monkeypatch.setenv("DEEPSEEK_PROXY_IMAGE_BASE_URL", endpoint)
    monkeypatch.setenv("DEEPSEEK_PROXY_IMAGE_MODEL", "qwen-image-region-test")

    url, payload_bytes, headers = cli._provider_probe_image_payload("qwen_image", "draw a region test image")
    payload = json.loads(payload_bytes.decode("utf-8"))

    assert url == endpoint
    assert headers["Content-Type"] == "application/json"
    assert payload["model"] == "qwen-image-region-test"
    assert payload["input"]["messages"][0]["content"][0]["text"] == "draw a region test image"


def test_cli_qwen_image_validation_respects_region_endpoint_env(monkeypatch):
    import deepseek_responses_proxy.cli as cli

    endpoint = "https://dashscope-us.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
    calls = {}

    def fake_validation_http_json(**kwargs):
        calls.update(kwargs)
        return {
            "ok": True,
            "status": "ok",
            "kind": kwargs["kind"],
            "provider": kwargs["provider"],
            "endpoint": kwargs["endpoint"],
            "functional_validation": "not_performed",
        }

    monkeypatch.setattr(cli, "_validation_http_json", fake_validation_http_json)
    monkeypatch.setenv("DEEPSEEK_PROXY_IMAGE_BASE_URL", endpoint)

    result = cli._validate_image_api_key("qwen_image", "dashscope-region-key", timeout=2.0)

    assert result["ok"] is True
    assert calls["url"] == endpoint
    assert calls["endpoint"] == endpoint
    assert calls["provider"] == "qwen_image"
    assert calls["payload"] == {}
