from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from codexchange_proxy import cli


ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "scripts" / "codex-wrapper.bash"


def _record(
    *,
    pid: int = 4242,
    port: int = 8001,
    route: str = "reasoning",
    profile: str | None = "sample",
    token: str | None = "owner-token",
) -> dict[str, object]:
    return {
        "contract": cli.LIFECYCLE_OWNER_CONTRACT,
        "schema_version": cli.LIFECYCLE_OWNER_SCHEMA_VERSION,
        "pid": pid,
        "process_start_identity": "linux-proc-start:boot:100",
        "host": cli.DEFAULT_HOST,
        "port": port,
        "route": route,
        "profile": profile,
        "runtime_identity": {
            "contract": "provider_pricing_runtime_identity_v1",
            "pricing_provider_id": "deepseek",
            "pricing_activate": True,
            "pricing_mode": "provider_owned",
            "pricing_provider_path": "/tmp/pricing.json",
        },
        "owner_token": token,
        "command_sha256": None,
        "ownership_source": "cox_cli_spawn_v1",
        "created_at_unix": 1.0,
    }


def _stop_args(tmp_path: Path, *, port: int | None = None, pid_file: Path | None = None):
    return argparse.Namespace(
        thinking=True,
        state_dir=str(tmp_path),
        pid_file=str(pid_file) if pid_file else None,
        port=port,
    )


def _patch_valid_runtime(monkeypatch: pytest.MonkeyPatch, *, pid: int, port: int) -> None:
    monkeypatch.setattr(cli, "_pid_alive", lambda value: value == pid)
    monkeypatch.setattr(cli, "_process_start_identity", lambda value: "linux-proc-start:boot:100" if value == pid else None)
    monkeypatch.setattr(cli, "_listen_pids_for_local_port", lambda value: [pid] if value == port else [])
    monkeypatch.setattr(cli, "_pid_looks_like_proxy", lambda value: value == pid)
    monkeypatch.setattr(cli, "_cmdline_for_pid", lambda value: "python -m codexchange_proxy.runtime_app --port 8001")
    monkeypatch.setattr(cli, "_pid_environment_value", lambda value, name: "owner-token")
    monkeypatch.setattr(cli, "_port_status_looks_like_proxy", lambda value: value == port)
    monkeypatch.setattr(
        cli,
        "_runtime_pricing_identity_for_port",
        lambda value, timeout=1.0: (
            200,
            {
                "contract": "provider_pricing_runtime_identity_v1",
                "pricing_provider_id": "deepseek",
                "pricing_activate": True,
                "pricing_mode": "provider_owned",
                "pricing_provider_path": "/tmp/pricing.json",
            },
            None,
        ),
    )


def test_default_stop_fails_closed_on_cross_port_pid_reuse(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    pid_file = tmp_path / "proxy-thinking.pid"
    cli._write_lifecycle_record(pid_file, _record(port=8001))
    monkeypatch.setattr(cli, "_pid_alive", lambda pid: pid == 4242)
    monkeypatch.setattr(cli, "_process_start_identity", lambda pid: "linux-proc-start:boot:100")
    monkeypatch.setattr(cli, "_listen_pids_for_local_port", lambda port: [4242] if port == 9009 else [])
    monkeypatch.setattr(cli, "_pid_looks_like_proxy", lambda pid: True)
    monkeypatch.setattr(cli, "_cmdline_for_pid", lambda pid: "python -m codexchange_proxy.runtime_app --port 9009")
    monkeypatch.setattr(cli, "_pid_environment_value", lambda pid, name: "owner-token")
    terminated: list[int] = []
    monkeypatch.setattr(cli, "_terminate_pid", lambda pid, label: terminated.append(pid) or True)

    assert cli._stop_proxy(_stop_args(tmp_path, pid_file=pid_file)) == 1
    assert terminated == []
    assert pid_file.exists()
    assert "pid_not_listening_on_target_port" in capsys.readouterr().out


def test_default_stop_fails_closed_on_pid_reuse_start_identity_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pid_file = tmp_path / "proxy-thinking.pid"
    cli._write_lifecycle_record(pid_file, _record())
    monkeypatch.setattr(cli, "_pid_alive", lambda pid: True)
    monkeypatch.setattr(cli, "_process_start_identity", lambda pid: "linux-proc-start:boot:999")
    monkeypatch.setattr(cli, "_listen_pids_for_local_port", lambda port: [4242])
    monkeypatch.setattr(cli, "_pid_looks_like_proxy", lambda pid: True)
    monkeypatch.setattr(cli, "_cmdline_for_pid", lambda pid: "python -m codexchange_proxy.runtime_app --port 8001")
    monkeypatch.setattr(cli, "_pid_environment_value", lambda pid, name: "owner-token")
    terminated: list[int] = []
    monkeypatch.setattr(cli, "_terminate_pid", lambda pid, label: terminated.append(pid) or True)

    assert cli._stop_proxy(_stop_args(tmp_path, pid_file=pid_file)) == 1
    assert terminated == []
    assert pid_file.exists()


def test_explicit_port_stop_requires_matching_versioned_owner_record(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_valid_runtime(monkeypatch, pid=4242, port=8123)
    terminated: list[int] = []
    monkeypatch.setattr(cli, "_terminate_pid", lambda pid, label: terminated.append(pid) or True)

    assert cli._stop_proxy(_stop_args(tmp_path, port=8123)) == 1
    assert terminated == []

    pid_file = tmp_path / "profile-sample-proxy-8123.pid"
    record = _record(port=8123)
    cli._write_lifecycle_record(pid_file, record)
    assert cli._stop_proxy(_stop_args(tmp_path, port=8123)) == 0
    assert terminated == [4242]
    assert not pid_file.exists()


def test_explicit_pricing_start_does_not_reuse_wrong_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    pricing = tmp_path / "pricing.json"
    pricing.write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(cli, "_maybe_print_startup_release_update_notice", lambda: None)
    monkeypatch.setattr(cli, "_managed_profile_route_preflight_or_error", lambda reason: None)
    monkeypatch.setattr(
        cli,
        "_healthz_for_port",
        lambda port, timeout=1.0: (200, {"version": cli.PROXY_VERSION}, None),
    )
    queried: list[int] = []

    def wrong_identity(port: int, *, timeout: float = 1.0):
        queried.append(port)
        return 200, {
            "contract": "provider_pricing_runtime_identity_v1",
            "pricing_provider_id": "different",
            "pricing_activate": True,
            "pricing_mode": "provider_owned",
            "pricing_provider_path": str(pricing),
        }, None

    monkeypatch.setattr(cli, "_runtime_pricing_identity_for_port", wrong_identity)
    args = argparse.Namespace(
        thinking=True,
        port=8124,
        state_dir=str(tmp_path),
        pid_file=None,
        log_file=None,
        db_path=None,
        owner_profile="sample",
        pricing_provider_id="deepseek",
        pricing_provider_owned=True,
        pricing_mode=None,
        pricing_provider_path=str(pricing),
    )

    assert cli._start_proxy(args) == 1
    output = capsys.readouterr().out
    assert "running_proxy_pricing_identity_mismatch" in output
    assert "cox stop --port 8124" in output
    assert queried == [8124]


def test_wrapper_delegates_isolated_startup_to_cli_and_emits_exact_recovery_command() -> None:
    text = WRAPPER.read_text(encoding="utf-8")
    function_body = text[
        text.index("__codexchange_start_local_proxy() (") :
        text.index("__codexchange_profile_runtime_autostart() (")
    ]
    assert '-m codexchange_proxy.cli "${start_args[@]}"' in function_body
    assert "exec \"$python_bin\" -m codexchange_proxy.runtime_app" not in function_body
    assert "exec \"$python_bin\" -m uvicorn" not in function_body
    assert "--owner-profile" in function_body
    assert "profile-${safe_profile}-proxy-${port}.pid" in function_body
    assert "__codexchange_source_env_file" in function_body
    assert "recovery command: cox stop --port ${port}" in text


def test_deprecated_stop_shims_forward_to_safe_cli_path() -> None:
    standard = (ROOT / "scripts" / "cox-stop").read_text(encoding="utf-8")
    reasoning = (ROOT / "scripts" / "cox-stop-reasoning").read_text(encoding="utf-8")
    assert 'exec cox stop "$@"' in standard
    assert 'exec cox stop reasoning "$@"' in reasoning
    for text in [standard, reasoning]:
        assert 'kill "$pid"' not in text
        assert "rm -f \"$PID_FILE\"" not in text
