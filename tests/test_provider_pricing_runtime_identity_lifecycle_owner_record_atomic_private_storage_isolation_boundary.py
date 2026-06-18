from __future__ import annotations

import argparse
import json
import os
import stat
import threading
from pathlib import Path

import pytest

from codexchange_proxy import cli


def _record(*, pid: int = 4242, port: int = 8001, token: str = "owner-token") -> dict[str, object]:
    return {
        "contract": cli.LIFECYCLE_OWNER_CONTRACT,
        "schema_version": cli.LIFECYCLE_OWNER_SCHEMA_VERSION,
        "pid": pid,
        "process_start_identity": "linux-proc-start:boot:100",
        "host": cli.DEFAULT_HOST,
        "port": port,
        "route": "reasoning",
        "profile": "sample",
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


def _mode(path: Path) -> int:
    return stat.S_IMODE(os.lstat(path).st_mode)


def test_p98_creates_private_state_lock_temp_and_owner_record(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_dir = tmp_path / "state"
    pid_path = state_dir / "proxy-thinking.pid"
    original_mkstemp = cli.tempfile.mkstemp
    observed_temp_modes: list[int] = []

    def capturing_mkstemp(*args, **kwargs):
        fd, name = original_mkstemp(*args, **kwargs)
        observed_temp_modes.append(stat.S_IMODE(os.fstat(fd).st_mode))
        return fd, name

    monkeypatch.setattr(cli.tempfile, "mkstemp", capturing_mkstemp)
    previous_umask = os.umask(0o022)
    try:
        cli._write_lifecycle_record(pid_path, _record())
    finally:
        os.umask(previous_umask)

    assert _mode(state_dir) == 0o700
    assert _mode(pid_path) == 0o600
    assert _mode(state_dir / ".codexchange-lifecycle-owner.lock") == 0o600
    assert observed_temp_modes == [0o600]
    assert not list(state_dir.glob(".proxy-thinking.pid.tmp-*"))
    assert cli._read_lifecycle_record(pid_path) == _record()


def test_p98_writer_and_reader_reject_symlink_owner_record_without_touching_victim(
    tmp_path: Path,
) -> None:
    victim = tmp_path / "victim"
    victim.write_text("do-not-touch\n", encoding="utf-8")
    victim.chmod(0o600)
    pid_path = tmp_path / "proxy.pid"
    pid_path.symlink_to(victim)

    with pytest.raises(cli.LifecycleStorageError):
        cli._read_lifecycle_record(pid_path)
    with pytest.raises(cli.LifecycleStorageError):
        cli._write_lifecycle_record(pid_path, _record())

    assert pid_path.is_symlink()
    assert victim.read_text(encoding="utf-8") == "do-not-touch\n"


def test_p98_lock_symlink_is_rejected_without_touching_victim(tmp_path: Path) -> None:
    victim = tmp_path / "lock-victim"
    victim.write_text("lock-victim\n", encoding="utf-8")
    victim.chmod(0o600)
    lock_path = tmp_path / ".codexchange-lifecycle-owner.lock"
    lock_path.symlink_to(victim)

    with pytest.raises(cli.LifecycleStorageError):
        cli._write_lifecycle_record(tmp_path / "proxy.pid", _record())

    assert lock_path.is_symlink()
    assert victim.read_text(encoding="utf-8") == "lock-victim\n"


def test_p98_reader_and_writer_reject_hardlinked_owner_record(tmp_path: Path) -> None:
    victim = tmp_path / "victim"
    victim.write_text(json.dumps(_record()) + "\n", encoding="utf-8")
    victim.chmod(0o600)
    pid_path = tmp_path / "proxy.pid"
    os.link(victim, pid_path)

    with pytest.raises(cli.LifecycleStorageError):
        cli._read_lifecycle_record(pid_path)
    with pytest.raises(cli.LifecycleStorageError):
        cli._write_lifecycle_record(pid_path, _record(pid=9999))

    assert json.loads(victim.read_text(encoding="utf-8"))["pid"] == 4242
    assert os.lstat(victim).st_nlink == 2


def test_p98_reader_and_writer_reject_non_regular_owner_record(tmp_path: Path) -> None:
    pid_path = tmp_path / "proxy.pid"
    pid_path.mkdir()

    with pytest.raises(cli.LifecycleStorageError):
        cli._read_lifecycle_record(pid_path)
    with pytest.raises(cli.LifecycleStorageError):
        cli._write_lifecycle_record(pid_path, _record())


def test_p98_versioned_record_must_be_private_but_legacy_plain_pid_can_migrate(
    tmp_path: Path,
) -> None:
    versioned = tmp_path / "versioned.pid"
    versioned.write_text(json.dumps(_record()) + "\n", encoding="utf-8")
    versioned.chmod(0o644)
    with pytest.raises(cli.LifecycleStorageError):
        cli._read_lifecycle_record(versioned)

    legacy = tmp_path / "legacy.pid"
    legacy.write_text("12345\n", encoding="utf-8")
    legacy.chmod(0o644)
    parsed = cli._read_lifecycle_record(legacy)
    assert parsed == {
        "contract": "legacy_plain_pid_v0",
        "schema_version": 0,
        "pid": 12345,
        "ownership_source": "legacy_plain_pid_file",
    }
    moved = cli._move_stale_pid_file(
        legacy,
        pid=12345,
        port=8001,
        reason="legacy_migration",
    )
    assert moved["stale_pid_moved"] is True
    stale = Path(str(moved["stale_pid_file"]))
    assert stale.exists()
    assert _mode(stale) == 0o600
    assert not legacy.exists()


def test_p98_stale_move_uses_random_non_overwriting_destination(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pid_path = tmp_path / "proxy.pid"
    cli._write_lifecycle_record(pid_path, _record())
    victim = tmp_path / "victim"
    victim.write_text("unchanged\n", encoding="utf-8")
    victim.chmod(0o600)
    occupied = tmp_path / "proxy.pid.stale-1000-aaaaaaaaaaaa"
    occupied.symlink_to(victim)
    tokens = iter(["aaaaaaaaaaaa", "bbbbbbbbbbbb"])
    monkeypatch.setattr(cli.time, "time", lambda: 1000.0)
    monkeypatch.setattr(cli.secrets, "token_hex", lambda _n: next(tokens))

    moved = cli._move_stale_pid_file(
        pid_path,
        pid=4242,
        port=8001,
        reason="test",
    )

    assert moved["stale_pid_moved"] is True
    assert Path(str(moved["stale_pid_file"])).name == "proxy.pid.stale-1000-bbbbbbbbbbbb"
    assert occupied.is_symlink()
    assert victim.read_text(encoding="utf-8") == "unchanged\n"


def test_p98_custom_insecure_state_directory_fails_before_spawn(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    state_dir = tmp_path / "custom-state"
    state_dir.mkdir(mode=0o755)
    state_dir.chmod(0o755)
    monkeypatch.setattr(cli, "_maybe_print_startup_release_update_notice", lambda: None)
    monkeypatch.setattr(cli, "_managed_profile_route_preflight_or_error", lambda reason: None)
    spawned: list[object] = []
    monkeypatch.setattr(cli.subprocess, "Popen", lambda *a, **k: spawned.append((a, k)))
    args = argparse.Namespace(
        thinking=True,
        port=8123,
        state_dir=str(state_dir),
        pid_file=None,
        log_file=None,
        db_path=None,
        owner_profile="sample",
        pricing_provider_id=None,
        pricing_provider_owned=False,
        pricing_mode=None,
        pricing_provider_path=None,
    )

    assert cli._start_proxy(args) == 1
    assert spawned == []
    output = capsys.readouterr().out
    assert "lifecycle_storage_integrity_error" in output
    assert "must have mode 0700" in output
    assert _mode(state_dir) == 0o755


def test_p98_managed_state_directory_permission_repair_is_explicit(tmp_path: Path) -> None:
    state_dir = tmp_path / "managed-state"
    state_dir.mkdir(mode=0o755)
    state_dir.chmod(0o755)

    with pytest.raises(cli.LifecycleStorageError):
        cli._ensure_lifecycle_state_directory(
            state_dir,
            create=False,
            repair_permissions=False,
        )
    cli._ensure_lifecycle_state_directory(
        state_dir,
        create=False,
        repair_permissions=True,
    )
    assert _mode(state_dir) == 0o700


def test_p98_stop_fails_closed_on_symlink_record_without_terminating(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    victim = tmp_path / "victim"
    victim.write_text(json.dumps(_record()) + "\n", encoding="utf-8")
    victim.chmod(0o600)
    pid_path = tmp_path / "proxy-thinking.pid"
    pid_path.symlink_to(victim)
    terminated: list[int] = []
    monkeypatch.setattr(cli, "_default_stop_port", lambda args: 8001)
    monkeypatch.setattr(cli, "_terminate_pid", lambda pid, label: terminated.append(pid) or True)
    args = argparse.Namespace(
        thinking=True,
        state_dir=str(tmp_path),
        pid_file=str(pid_path),
        port=None,
    )

    assert cli._stop_proxy(args) == 1
    assert terminated == []
    assert "lifecycle_storage_integrity_error" in capsys.readouterr().out
    assert victim.exists()



def test_p98_spawned_process_is_terminated_if_owner_record_write_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(cli, "_maybe_print_startup_release_update_notice", lambda: None)
    monkeypatch.setattr(cli, "_managed_profile_route_preflight_or_error", lambda reason: None)
    monkeypatch.setattr(cli, "_healthz_for_port", lambda port, timeout=1.0: (None, None, "refused"))
    monkeypatch.setattr(cli, "_tcp_port_open", lambda host, port, timeout=0.25: False)
    monkeypatch.setattr(cli, "_read_env_exports", lambda path: {})
    monkeypatch.setattr(cli, "_process_start_identity", lambda pid: "linux-proc-start:boot:100")
    monkeypatch.setattr(cli, "_cmdline_for_pid", lambda pid: "python -m codexchange_proxy.runtime_app")

    class FakeProcess:
        pid = 54321
        returncode = None

        def poll(self):
            return self.returncode

    monkeypatch.setattr(cli.subprocess, "Popen", lambda *args, **kwargs: FakeProcess())
    monkeypatch.setattr(
        cli,
        "_write_lifecycle_record_unlocked",
        lambda path, record: (_ for _ in ()).throw(cli.LifecycleStorageError("simulated write failure")),
    )
    terminated: list[int] = []
    monkeypatch.setattr(cli, "_terminate_pid", lambda pid, label: terminated.append(pid) or True)
    args = argparse.Namespace(
        thinking=True,
        port=8124,
        state_dir=str(tmp_path),
        pid_file=None,
        log_file=str(tmp_path / "proxy.log"),
        db_path=str(tmp_path / "responses.sqlite3"),
        owner_profile="sample",
        pricing_provider_id=None,
        pricing_provider_owned=False,
        pricing_mode=None,
        pricing_provider_path=None,
    )

    assert cli._start_proxy(args) == 1
    assert terminated == [54321]
    output = capsys.readouterr().out
    assert "lifecycle_storage_integrity_error" in output
    assert "spawned_process_cleanup_succeeded=true" in output
    assert not (tmp_path / "proxy-thinking.pid").exists()

def test_p98_directory_lock_serializes_concurrent_writers(tmp_path: Path) -> None:
    pid_path = tmp_path / "proxy.pid"
    barrier = threading.Barrier(8)
    errors: list[BaseException] = []

    def worker(index: int) -> None:
        try:
            barrier.wait(timeout=5)
            for round_index in range(10):
                cli._write_lifecycle_record(
                    pid_path,
                    _record(pid=1000 + index, token=f"token-{index}-{round_index}"),
                )
                parsed = cli._read_lifecycle_record(pid_path)
                assert isinstance(parsed, dict)
                assert parsed.get("contract") == cli.LIFECYCLE_OWNER_CONTRACT
        except BaseException as exc:  # pragma: no cover - collected for the main thread
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(index,)) for index in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=15)

    assert not any(thread.is_alive() for thread in threads)
    assert errors == []
    parsed = cli._read_lifecycle_record(pid_path)
    assert isinstance(parsed, dict)
    assert parsed["contract"] == cli.LIFECYCLE_OWNER_CONTRACT
    assert _mode(pid_path) == 0o600
    assert not list(tmp_path.glob(".proxy.pid.tmp-*"))


def test_p98_static_contract_has_private_atomic_symlink_safe_primitives() -> None:
    source = Path(cli.__file__).read_text(encoding="utf-8")
    for marker in [
        "fcntl.flock",
        "O_NOFOLLOW",
        "tempfile.mkstemp",
        "os.fchmod(fd, 0o600)",
        "os.fsync(stream.fileno())",
        "os.replace(temporary, pid_path)",
        "_fsync_lifecycle_directory",
        "metadata.st_nlink != 1",
        "stat.S_ISLNK",
        "_exclusive_lifecycle_directory_lock",
    ]:
        assert marker in source
    assert ".tmp-{os.getpid()}-{time.time_ns()}" not in source
    assert "temporary.write_text(payload" not in source
