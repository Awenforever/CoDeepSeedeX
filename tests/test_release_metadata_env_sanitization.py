import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_cli_version_ignores_stale_release_metadata_env() -> None:
    env = os.environ.copy()
    env["COX_PUBLIC_COMMIT"] = "72e0f77"
    env["COX_INTERNAL_COMMIT"] = "72e0f77"
    env["COX_INTERNAL_VERSION"] = "p2.10a26-wrapper-start-plan-mode-hardening"

    result = subprocess.run(
        [sys.executable, "-m", "codexchange_proxy.cli", "--version"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
        env=env,
    )

    output = result.stdout.strip()
    assert "72e0f77" not in output
    assert "p3.0a1-codexchange-hardcut-generalized-router" in output


def test_install_script_writes_current_release_metadata_env() -> None:
    text = (ROOT / "scripts" / "install.sh").read_text(encoding="utf-8")
    assert "p2.10a26-wrapper-start-plan-mode-hardening" not in text
    assert "resolve_install_internal_version_for_metadata()" in text
    assert 'INSTALL_TARGET_INTERNAL_VERSION="$(resolve_install_internal_version_for_metadata)"' in text
    assert 'export COX_INTERNAL_VERSION=%q' in text
    assert '"$INSTALL_TARGET_INTERNAL_VERSION"' in text
    assert 'export COX_PUBLIC_COMMIT=%q' in text
    assert 'export COX_INTERNAL_COMMIT=%q' in text


def test_bootstrap_unsets_stale_release_metadata_before_installer() -> None:
    text = (ROOT / "bootstrap.sh").read_text(encoding="utf-8")
    assert "unset COX_PUBLIC_COMMIT" in text
    assert "unset COX_INTERNAL_COMMIT" in text
    assert "unset COX_INTERNAL_VERSION" in text
    assert text.index("unset COX_PUBLIC_COMMIT") < text.index('bash "$INSTALLER_PATH"')


def test_cli_non_git_upgrade_scrubs_release_metadata_env() -> None:
    text = (ROOT / "codexchange_proxy" / "cli.py").read_text(encoding="utf-8")
    assert '"COX_PUBLIC_COMMIT"' in text
    assert '"COX_INTERNAL_COMMIT"' in text
    assert '"COX_INTERNAL_VERSION"' in text
    assert "env.pop(metadata_key, None)" in text
    assert 'step["metadata_env_sanitized"] = True' in text
    assert text.index("env.pop(metadata_key, None)") < text.index('env["COX_INSTALL_REF"] = target_ref')
