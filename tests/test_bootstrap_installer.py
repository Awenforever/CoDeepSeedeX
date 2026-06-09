from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP = ROOT / "bootstrap.sh"


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
        env={
            "PATH": "/usr/bin:/bin",
            "HOME": "/tmp/codeepseedex-bootstrap-dry-run-test-home",
            "DEEPSEEK_PROXY_LATEST_RELEASE_API_URL": "https://127.0.0.1:9/should-not-be-called",
        },
    )
    assert result.returncode == 0
    assert "dry-run" in result.stdout
    assert "DEEPSEEK_PROXY_PYTHON_BIN" in result.stdout
    assert "should-not-be-called" not in result.stderr


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
    assert 'if [ -n "${DEEPSEEK_PROXY_PYTHON_BIN:-}" ]; then' in text
    assert 'PYTHON_BIN="$DEEPSEEK_PROXY_PYTHON_BIN"' in text
    assert "PYTHON_BIN_EXPLICIT=1" in text
    assert "PYTHON_BIN_EXPLICIT=0" in text
    assert "select_codeepseedex_python_bin()" in text
    assert "ensure_codeepseedex_python_bin" in text
    assert "python3.13" in text
    assert "python3.12" in text
    assert "python3.11" in text
    assert '"$INSTALL_DIR/.venv/bin/python"' in text
    assert '--python-bin) PYTHON_BIN="$2"; PYTHON_BIN_EXPLICIT=1; shift ;;' in text
    assert "CoDeepSeedeX does not install or patch Python automatically" in text
    assert 'if [ -n "${PYTHON_BIN:-}" ] && [ -n "${CODEEPSEEDEX_SELECTED_PYTHON_VERSION:-}" ]; then' in text
    assert "ensure_codeepseedex_python_bin\nchoose_installer_language" in text
    forbidden_auto_python_install_markers = [
        "apt-get install python",
        "apt install python",
        "dnf install python",
        "yum install python",
        "brew install python",
        "pacman -s python",
        "pyenv install",
        "conda install python",
    ]
    lowered = text.lower()
    for marker in forbidden_auto_python_install_markers:
        assert marker not in lowered

def test_install_script_defaults_to_latest_release_ref() -> None:
    text = (ROOT / "scripts" / "install.sh").read_text(encoding="utf-8")
    assert "LATEST_RELEASE_API_URL=" in text
    assert "resolve_install_ref()" in text
    assert 'INSTALL_TARGET_REF="$(resolve_install_ref)"' in text
    assert 'sync_install_checkout_to_ref "$INSTALL_TARGET_REF"' in text
    assert 'git checkout -B "$requested_ref" "origin/$requested_ref"' in text
    assert 'git checkout -f "$requested_ref"' in text
    assert 'git -C "$INSTALL_DIR" pull --ff-only' not in text


def test_bootstrap_hides_duplicate_ready_messages() -> None:
    text = (ROOT / "bootstrap.sh").read_text(encoding="utf-8") if "ROOT" in globals() else (REPO_ROOT / "bootstrap.sh").read_text(encoding="utf-8")
    assert 'ok "Python $(python_version_text "$selected_python") via $selected_python"' not in text
    assert 'ok "Installer ready"' not in text
    assert "installer ready:" in text
    assert "python:" in text


def test_bootstrap_hides_top_level_log_line_and_passes_bootstrap_log() -> None:
    text = BOOTSTRAP.read_text(encoding="utf-8")
    assert 'printf \'  log: %s\\n\' "$INSTALL_LOG"' not in text
    assert 'color "1;36" "CoDeepSeedeX bootstrap"' not in text
    assert 'DEEPSEEK_PROXY_BOOTSTRAP_LOG="$INSTALL_LOG"' in text
