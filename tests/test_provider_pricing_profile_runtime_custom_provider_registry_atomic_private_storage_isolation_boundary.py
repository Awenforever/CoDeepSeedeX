from __future__ import annotations

import json
import os
import shlex
import stat
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from codexchange_proxy import cli


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "scripts" / "install.sh"


def _installer_registry_functions() -> str:
    text = INSTALLER.read_text(encoding="utf-8")
    start = text.index("custom_provider_registry_transaction() {")
    end = text.index("\nmodel_api_key_state_label() {", start)
    return text[start:end]


def _run_bash(script: str, cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-c", script, "_", *args],
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=60,
        check=False,
    )


def _cli_worker_source() -> str:
    return (
        "from pathlib import Path\n"
        "import sys\n"
        "from codexchange_proxy.cli import _upsert_custom_provider_registry_entry\n"
        "_upsert_custom_provider_registry_entry(\n"
        "    Path(sys.argv[1]),\n"
        "    display_name=sys.argv[2],\n"
        "    base_url=f'https://{sys.argv[2].lower().replace(\" \", \"-\")}.invalid/v1',\n"
        "    model=sys.argv[3],\n"
        "    api_key=f'dummy-{sys.argv[2]}',\n"
        "    make_active=False,\n"
        ")\n"
    )


def test_p94_static_contract_uses_private_atomic_locked_symlink_safe_storage() -> None:
    cli_text = (ROOT / "codexchange_proxy" / "cli.py").read_text(encoding="utf-8")
    installer = _installer_registry_functions()

    for text in (cli_text, installer):
        assert "O_NOFOLLOW" in text
        assert "LOCK_EX" in text
        assert "tempfile.mkstemp" in text
        assert "os.fchmod" in text
        assert "0o600" in text
        assert "os.fsync" in text
        assert "os.replace" in text
        assert 'f".{path.name}.lock"' in text

    assert "_update_custom_provider_registry(" in cli_text
    assert "_custom_provider_registry_read_unlocked(expanded, strict=True)" in cli_text
    assert "path.write_text(json.dumps(data" not in installer
    assert "os.chmod(path, 0o600)" not in installer


def test_p94_cli_first_write_is_private_and_never_exposes_registry_path(tmp_path: Path) -> None:
    registry = tmp_path / "model-providers.json"
    providers = {
        f"provider-{index:05d}": {
            "id": f"provider-{index:05d}",
            "type": "custom_openai_compatible",
            "display_name": f"Provider {index:05d}",
            "base_url": f"https://provider-{index:05d}.invalid/v1",
            "active_model": f"model-{index:05d}",
            "models": [f"model-{index:05d}"],
            "api_key": f"dummy-secret-{index:05d}",
        }
        for index in range(15000)
    }
    data = {"version": 1, "active_provider": None, "providers": providers}
    observed_modes: set[int] = set()
    error: list[BaseException] = []

    def writer() -> None:
        try:
            cli._write_custom_provider_registry(registry, data)
        except BaseException as exc:  # pragma: no cover - asserted below
            error.append(exc)

    previous_umask = os.umask(0o022)
    try:
        thread = threading.Thread(target=writer)
        thread.start()
        while thread.is_alive():
            try:
                observed_modes.add(stat.S_IMODE(registry.stat().st_mode))
            except FileNotFoundError:
                pass
        thread.join(timeout=10)
    finally:
        os.umask(previous_umask)

    assert not error
    observed_modes.add(stat.S_IMODE(registry.stat().st_mode))
    assert observed_modes == {0o600}
    lock = tmp_path / ".model-providers.json.lock"
    assert stat.S_IMODE(lock.stat().st_mode) == 0o600
    assert not list(tmp_path.glob(".model-providers.json.tmp-*"))


def test_p94_cli_rejects_registry_and_lock_symlinks_without_touching_victim(tmp_path: Path) -> None:
    victim = tmp_path / "victim.txt"
    victim.write_text("do-not-touch\n", encoding="utf-8")
    victim.chmod(0o644)
    registry = tmp_path / "model-providers.json"
    registry.symlink_to(victim)

    with pytest.raises(ValueError):
        cli._upsert_custom_provider_registry_entry(
            registry,
            display_name="Alpha",
            base_url="https://alpha.invalid/v1",
            model="alpha-model",
            api_key="dummy-alpha",
        )
    assert victim.read_text(encoding="utf-8") == "do-not-touch\n"
    assert stat.S_IMODE(victim.stat().st_mode) == 0o644

    registry.unlink()
    lock_victim = tmp_path / "lock-victim.txt"
    lock_victim.write_text("lock-do-not-touch\n", encoding="utf-8")
    lock_victim.chmod(0o644)
    (tmp_path / ".model-providers.json.lock").unlink(missing_ok=True)
    (tmp_path / ".model-providers.json.lock").symlink_to(lock_victim)
    with pytest.raises(ValueError):
        cli._upsert_custom_provider_registry_entry(
            registry,
            display_name="Beta",
            base_url="https://beta.invalid/v1",
            model="beta-model",
            api_key="dummy-beta",
        )
    assert lock_victim.read_text(encoding="utf-8") == "lock-do-not-touch\n"
    assert stat.S_IMODE(lock_victim.stat().st_mode) == 0o644
    assert not registry.exists()


def test_p94_cli_concurrent_upserts_preserve_every_provider(tmp_path: Path) -> None:
    registry = tmp_path / "model-providers.json"
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(ROOT)
    processes = [
        subprocess.Popen(
            [
                sys.executable,
                "-c",
                _cli_worker_source(),
                str(registry),
                f"Provider {index:02d}",
                f"model-{index:02d}",
            ],
            cwd=ROOT,
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        for index in range(12)
    ]
    results = [process.communicate(timeout=60) + (process.returncode,) for process in processes]
    assert all(returncode == 0 for _stdout, _stderr, returncode in results), results

    data = json.loads(registry.read_text(encoding="utf-8"))
    assert set(data["providers"]) == {f"provider-{index:02d}" for index in range(12)}
    assert stat.S_IMODE(registry.stat().st_mode) == 0o600


def test_p94_installer_concurrent_upserts_share_the_same_lock_and_atomic_contract(tmp_path: Path) -> None:
    registry = tmp_path / "model-providers.json"
    install_log = tmp_path / "install.log"
    functions = _installer_registry_functions()
    script = (
        "set -euo pipefail\n"
        f"PYTHON_BIN={shlex.quote(sys.executable)}\n"
        "MODEL_PROVIDER_REGISTRY_FILE=\"$1\"\n"
        "INSTALL_LOG=\"$2\"\n"
        "DRY_RUN=0\n"
        + functions
        + "\n"
        "write_model_provider_registry custom \"$3\" \"https://$4.invalid/v1\" \"$5\" \"dummy-$4\"\n"
    )
    processes = [
        subprocess.Popen(
            [
                "bash",
                "-c",
                script,
                "_",
                str(registry),
                str(install_log),
                f"Installer Provider {index:02d}",
                f"installer-{index:02d}",
                f"model-{index:02d}",
            ],
            cwd=tmp_path,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        for index in range(10)
    ]
    results = [process.communicate(timeout=60) + (process.returncode,) for process in processes]
    assert all(returncode == 0 for _stdout, _stderr, returncode in results), results

    data = json.loads(registry.read_text(encoding="utf-8"))
    assert set(data["providers"]) == {
        f"installer-provider-{index:02d}" for index in range(10)
    }
    assert stat.S_IMODE(registry.stat().st_mode) == 0o600
    assert stat.S_IMODE((tmp_path / ".model-providers.json.lock").stat().st_mode) == 0o600


def test_p94_installer_rejects_registry_symlink_without_overwriting_target(tmp_path: Path) -> None:
    victim = tmp_path / "victim.json"
    victim.write_text('{"safe": true}\n', encoding="utf-8")
    victim.chmod(0o644)
    registry = tmp_path / "model-providers.json"
    registry.symlink_to(victim)
    install_log = tmp_path / "install.log"
    script = (
        "set -euo pipefail\n"
        f"PYTHON_BIN={shlex.quote(sys.executable)}\n"
        "MODEL_PROVIDER_REGISTRY_FILE=\"$1\"\n"
        "INSTALL_LOG=\"$2\"\n"
        "DRY_RUN=0\n"
        + _installer_registry_functions()
        + "\n"
        "if write_model_provider_registry custom Alpha https://alpha.invalid/v1 alpha-model dummy-alpha; then\n"
        "  exit 99\n"
        "fi\n"
    )
    completed = _run_bash(script, tmp_path, str(registry), str(install_log))

    assert completed.returncode == 0, completed.stderr
    assert victim.read_text(encoding="utf-8") == '{"safe": true}\n'
    assert stat.S_IMODE(victim.stat().st_mode) == 0o644
    assert registry.is_symlink()
