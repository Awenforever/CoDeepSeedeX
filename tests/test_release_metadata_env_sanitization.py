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
    assert 'p3.3a20a74-provider-pricing-runtime-identity-exposure-and-reconciliation-v0455' in output


def test_install_script_writes_current_release_metadata_env() -> None:
    text = (ROOT / "scripts" / "install.sh").read_text(encoding="utf-8")
    assert "p2.10a26-wrapper-start-plan-mode-hardening" not in text
    assert "resolve_install_internal_version_for_metadata()" in text
    assert 'INSTALL_TARGET_INTERNAL_VERSION="$(resolve_install_internal_version_for_metadata)"' in text

    writer = text[text.index("write_env_file() {"):text.index("refresh_canonical_codex_wrapper_template() {")]
    assert '"$env_python" "$env_data_tool" replace-exports-nul "$ENV_FILE"' in writer
    assert r"printf 'COX_INTERNAL_VERSION\0%s\0'" in writer
    assert '"$INSTALL_TARGET_INTERNAL_VERSION"' in writer
    assert r"printf 'COX_PUBLIC_COMMIT\0%s\0'" in writer
    assert r"printf 'COX_INTERNAL_COMMIT\0%s\0'" in writer
    assert '"$INSTALL_TARGET_COMMIT"' in writer
    assert 'export COX_INTERNAL_VERSION=%q' not in writer
    assert 'export COX_PUBLIC_COMMIT=%q' not in writer
    assert 'export COX_INTERNAL_COMMIT=%q' not in writer


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
