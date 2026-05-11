from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_bootstrap_help() -> None:
    result = subprocess.run(
        ["bash", str(ROOT / "bootstrap.sh"), "--help"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0
    assert "Usage: bootstrap.sh" in result.stdout
    assert "--print-python-selection" in result.stdout


def test_bootstrap_dry_run_does_not_require_apt_changes() -> None:
    result = subprocess.run(
        ["bash", str(ROOT / "bootstrap.sh"), "--dry-run", "--", "--non-interactive"],
        text=True,
        capture_output=True,
        check=False,
        timeout=20,
    )
    assert result.returncode == 0
    assert "dry-run" in result.stdout
    assert "DEEPSEEK_PROXY_PYTHON_BIN" in result.stdout


def test_install_script_accepts_python_bin_option() -> None:
    result = subprocess.run(
        ["bash", str(ROOT / "scripts" / "install.sh"), "--help"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0
    assert "--python-bin PATH" in result.stdout


def test_install_script_uses_selected_python_bin() -> None:
    text = (ROOT / "scripts" / "install.sh").read_text(encoding="utf-8")
    assert 'PYTHON_BIN="${DEEPSEEK_PROXY_PYTHON_BIN:-python3}"' in text
    assert '"$PYTHON_BIN" -m venv "$INSTALL_DIR/.venv"' in text
    assert 'PY_VERSION="$("$PYTHON_BIN" - <<' in text
