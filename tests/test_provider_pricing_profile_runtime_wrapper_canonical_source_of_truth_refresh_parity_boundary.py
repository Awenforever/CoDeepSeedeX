from __future__ import annotations

import json
import os
import shlex
import subprocess
from pathlib import Path

import codexchange_proxy.cli as cli


ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / "scripts" / "codex-wrapper.bash"
INSTALLER = ROOT / "scripts" / "install.sh"


def _write_manifest(tmp_path: Path, wrapper: Path, real_codex: Path) -> Path:
    manifest = tmp_path / "install-manifest.env"
    manifest.write_text(
        f"CODEX_WRAPPER_PATH={wrapper}\n"
        "CODEX_WRAPPER_BACKUP=\n"
        f"REAL_CODEX={real_codex}\n"
        f"ENV_FILE={tmp_path / 'env'}\n"
        f"INSTALL_DIR={tmp_path}\n"
        f"BIN_DIR={wrapper.parent}\n"
        "STABLE_PORT=8000\n"
        "THINKING_PORT=8001\n",
        encoding="utf-8",
    )
    return manifest


def _write_real_codex(path: Path) -> None:
    path.write_text("#!/usr/bin/env bash\nprintf 'codex-cli 0.140.0\\n'\n", encoding="utf-8")
    path.chmod(0o755)


def test_p78_canonical_wrapper_contains_managed_and_p76_contract_markers() -> None:
    text = CANONICAL.read_text(encoding="utf-8")
    for marker in (
        "# CodeXchange codex wrapper",
        "BEGIN COX PROFILE-AGNOSTIC RUNTIME AUTOSTART",
        "BEGIN COX EXECUTABLE WRAPPER DISPATCHER",
        "__codexchange_profile_pricing_candidate",
        "__codexchange_proxy_runtime_identity_matches",
        '--owner-profile "${profile:-default}"',
        "--pricing-provider-id",
        "recovery command: cox stop --port ${port}",
        "__codexchange_manifest_real_codex",
    ):
        assert marker in text


def test_p78_refresh_recognizes_pre_marker_canonical_and_writes_byte_parity(tmp_path, capsys) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    wrapper = bin_dir / "codex"
    real_codex = bin_dir / "real-codex"
    _write_real_codex(real_codex)
    wrapper.write_text(
        "#!/usr/bin/env bash\n"
        "# BEGIN COX PROFILE-AGNOSTIC RUNTIME AUTOSTART\n"
        "# BEGIN COX EXECUTABLE WRAPPER DISPATCHER\n",
        encoding="utf-8",
    )
    wrapper.chmod(0o755)
    manifest = _write_manifest(tmp_path, wrapper, real_codex)

    assert cli.main(["profile", "refresh-wrapper", "--manifest", str(manifest), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["canonical_parity"] is True
    assert payload["backup"] is None
    assert wrapper.read_bytes() == CANONICAL.read_bytes()
    assert wrapper.stat().st_mode & 0o111


def test_p78_force_refresh_unknown_wrapper_creates_backup_and_canonical_target(tmp_path, capsys) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    wrapper = bin_dir / "codex"
    real_codex = bin_dir / "real-codex"
    _write_real_codex(real_codex)
    original = b"#!/usr/bin/env bash\nprintf unknown-user-wrapper\n"
    wrapper.write_bytes(original)
    wrapper.chmod(0o755)
    manifest = _write_manifest(tmp_path, wrapper, real_codex)

    assert cli.main([
        "profile", "refresh-wrapper", "--manifest", str(manifest), "--json", "--force"
    ]) == 0
    payload = json.loads(capsys.readouterr().out)
    backup = Path(payload["backup"])

    assert backup.read_bytes() == original
    assert wrapper.read_bytes() == CANONICAL.read_bytes()
    assert cli._read_manifest_exports(manifest)["CODEX_WRAPPER_BACKUP"] == str(backup)


def test_p78_canonical_wrapper_resolves_manifest_real_codex(tmp_path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    wrapper = bin_dir / "codex"
    real_codex = bin_dir / "native-codex"
    _write_real_codex(real_codex)
    wrapper.write_bytes(CANONICAL.read_bytes())
    wrapper.chmod(0o755)
    manifest = _write_manifest(tmp_path, wrapper, real_codex)

    env = os.environ.copy()
    env["COX_INSTALL_MANIFEST"] = str(manifest)
    env["PATH"] = "/usr/bin:/bin"
    import subprocess
    completed = subprocess.run(
        [str(wrapper), "--version"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        timeout=10,
    )
    assert completed.returncode == 0
    assert "codex-cli 0.140.0" in completed.stdout


def test_p78_installer_and_cli_have_no_embedded_wrapper_body() -> None:
    installer = INSTALLER.read_text(encoding="utf-8")
    cli_text = (ROOT / "codexchange_proxy" / "cli.py").read_text(encoding="utf-8")
    write_body = installer[installer.index("write_codex_wrapper() {"):installer.index("uninstall() {")]

    assert 'cp "$template" "$wrapper_path"' in write_body
    assert 'cat > "$wrapper_path" <<EOF' not in write_body
    assert "wrapper_template = r\"\"\"" not in cli_text
    assert "_load_canonical_codex_wrapper_template" in cli_text



def test_canonical_wrapper_manifest_parser_does_not_execute_shell_code(tmp_path: Path) -> None:
    wrapper = ROOT / "scripts" / "codex-wrapper.bash"
    marker = tmp_path / "manifest-code-executed"
    manifest = tmp_path / "install-manifest.env"
    manifest.write_text(
        f'REAL_CODEX="$(touch {marker})"\n',
        encoding="utf-8",
    )

    env = os.environ.copy()
    env["COX_INSTALL_MANIFEST"] = str(manifest)
    result = subprocess.run(
        [
            "bash",
            "-c",
            f'source {shlex.quote(str(wrapper))}; __codexchange_manifest_real_codex',
        ],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )

    assert result.returncode == 0
    assert result.stdout.strip() == f"$(touch {marker})"
    assert not marker.exists()
