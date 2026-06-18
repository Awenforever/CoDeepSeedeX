from __future__ import annotations

import os
import shlex
import stat
import subprocess
import sys
from pathlib import Path

import codexchange_proxy.cli as cli


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "scripts" / "install.sh"


def _installer_env(home: Path, log: Path) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "HOME": str(home),
            "COX_INSTALL_LOG": str(log),
            "COX_PYTHON_BIN": sys.executable,
        }
    )
    return env


def _run_uninstall(root: Path, *, dry_run: bool) -> subprocess.CompletedProcess[str]:
    home = root / "home"
    install_dir = root / "install"
    bin_dir = root / "bin"
    config_dir = root / "config"
    for path in (home, install_dir, bin_dir, config_dir):
        path.mkdir(parents=True, exist_ok=True)
    command = [
        "bash",
        str(INSTALLER),
        "--uninstall",
        "--non-interactive",
        "--install-dir",
        str(install_dir),
        "--bin-dir",
        str(bin_dir),
        "--config-dir",
        str(config_dir),
    ]
    if dry_run:
        command.append("--dry-run")
    return subprocess.run(
        command,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=_installer_env(home, root / "install.log"),
        timeout=20,
        check=False,
    )


def _manifest_helper_block() -> str:
    text = INSTALLER.read_text(encoding="utf-8")
    start = text.index("select_install_manifest_python_bin() {")
    end = text.index("write_codex_wrapper() {", start)
    return text[start:end]


def test_p90_installer_manifest_is_never_sourced_and_uses_atomic_data_helpers() -> None:
    text = INSTALLER.read_text(encoding="utf-8")
    assert 'source "$MANIFEST_FILE"' not in text
    assert "select_install_manifest_python_bin()" in text
    assert "write_install_manifest_data()" in text
    assert "read_install_manifest_data()" in text
    assert "shlex.quote(value)" in text
    assert "os.replace(temporary, manifest)" in text
    assert 'read_install_manifest_data "$MANIFEST_FILE" "$manifest_data"' in text


def test_p90_real_uninstall_treats_manifest_shell_payload_as_inert_data(tmp_path: Path) -> None:
    root = tmp_path / "malicious"
    config = root / "config"
    config.mkdir(parents=True)
    marker = root / "manifest-command-executed"
    manifest = config / "install-manifest.env"
    manifest.write_text(
        f'CODEX_WRAPPER_PATH="$(touch {marker})"\n'
        "CODEX_WRAPPER_BACKUP=''\n"
        f"touch {marker}\n",
        encoding="utf-8",
    )

    completed = _run_uninstall(root, dry_run=True)

    assert completed.returncode == 0, completed.stderr
    assert not marker.exists()
    assert "Done" in completed.stdout


def test_p90_real_uninstall_restores_backup_from_legacy_quoted_manifest(tmp_path: Path) -> None:
    root = tmp_path / "restore"
    bin_dir = root / "bin"
    config = root / "config"
    bin_dir.mkdir(parents=True)
    config.mkdir(parents=True)
    marker = root / "must-not-execute"
    wrapper = bin_dir / "custom codex $(literal)"
    backup = bin_dir / "native backup $(literal)"
    wrapper.write_text("#!/usr/bin/env bash\n# CodeXchange codex wrapper\n", encoding="utf-8")
    backup.write_text("#!/usr/bin/env bash\nprintf 'native-restored\\n'\n", encoding="utf-8")
    wrapper.chmod(0o755)
    backup.chmod(0o755)
    (config / "install-manifest.env").write_text(
        f'CODEX_WRAPPER_PATH="{wrapper}"\n'
        f'CODEX_WRAPPER_BACKUP="{backup}"\n'
        f'IGNORED_COMMAND="$(touch {marker})"\n',
        encoding="utf-8",
    )

    completed = _run_uninstall(root, dry_run=False)

    assert completed.returncode == 0, completed.stderr
    assert wrapper.read_text(encoding="utf-8").startswith("#!/usr/bin/env bash\nprintf 'native-restored")
    assert not backup.exists()
    assert not marker.exists()


def test_p90_manifest_writer_round_trips_special_values_as_data_with_mode_0600(tmp_path: Path) -> None:
    manifest = tmp_path / "config with spaces" / "install-manifest.env"
    install_dir = tmp_path / "install"
    execution_marker = tmp_path / "writer-command-executed"
    command_like = f"$(printf should-not-run > {execution_marker}) ; equals=value 'quoted'"
    script = (
        "set -euo pipefail\n"
        "warn() { printf 'warning=%s\\n' \"$*\" >&2; }\n"
        "INSTALL_DIR=\"$1\"\n"
        "PYTHON_BIN=\"$2\"\n"
        "MANIFEST_FILE=\"$3\"\n"
        "shift 3\n"
        + _manifest_helper_block()
        + "\nwrite_install_manifest_data \"$@\"\n"
    )
    completed = subprocess.run(
        [
            "bash",
            "-c",
            script,
            "_",
            str(install_dir),
            sys.executable,
            str(manifest),
            "CODEX_WRAPPER_PATH",
            str(tmp_path / "bin path" / "codex"),
            "CODEX_WRAPPER_BACKUP",
            command_like,
            "REAL_CODEX",
            str(tmp_path / "native codex"),
            "STABLE_PORT",
            "8000",
            "THINKING_PORT",
            "8001",
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=20,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    values = cli._read_manifest_exports(manifest)
    assert values["CODEX_WRAPPER_BACKUP"] == command_like
    assert values["CODEX_WRAPPER_PATH"] == str(tmp_path / "bin path" / "codex")
    assert values["REAL_CODEX"] == str(tmp_path / "native codex")
    assert values["STABLE_PORT"] == "8000"
    assert stat.S_IMODE(manifest.stat().st_mode) == 0o600
    assert not list(manifest.parent.glob(f".{manifest.name}.tmp-*"))
    assert "should-not-run" in manifest.read_text(encoding="utf-8")
    assert not execution_marker.exists()


def test_p90_invalid_recognized_manifest_assignment_fails_closed_without_execution(tmp_path: Path) -> None:
    root = tmp_path / "invalid"
    config = root / "config"
    config.mkdir(parents=True)
    marker = root / "invalid-command-executed"
    (config / "install-manifest.env").write_text(
        "CODEX_WRAPPER_PATH='unterminated\n"
        f"touch {shlex.quote(str(marker))}\n",
        encoding="utf-8",
    )

    completed = _run_uninstall(root, dry_run=True)

    assert completed.returncode == 0
    assert not marker.exists()
    assert "invalid data" in completed.stdout
    assert "no manifest content was executed" in completed.stdout
