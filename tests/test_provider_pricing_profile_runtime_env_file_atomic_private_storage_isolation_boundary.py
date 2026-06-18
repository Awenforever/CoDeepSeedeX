from __future__ import annotations

import importlib.util
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ENV_MODULE = ROOT / "codexchange_proxy" / "env_file.py"
INSTALL = ROOT / "scripts" / "install.sh"
COX_CONFIG = ROOT / "scripts" / "cox-config"


def _load_env_module():
    spec = importlib.util.spec_from_file_location("p96_env_file", ENV_MODULE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def test_p96_static_contract_uses_one_locked_atomic_data_writer() -> None:
    env_text = ENV_MODULE.read_text(encoding="utf-8")
    install_text = INSTALL.read_text(encoding="utf-8")
    config_text = COX_CONFIG.read_text(encoding="utf-8")

    assert "fcntl.flock(fd, fcntl.LOCK_EX)" in env_text
    assert "tempfile.mkstemp" in env_text
    assert "os.replace(temporary, path)" in env_text
    assert "os.fsync(stream.fileno())" in env_text
    assert "_fsync_directory(path.parent)" in env_text
    assert "O_NOFOLLOW" in env_text
    assert "metadata.st_nlink != 1" in env_text
    assert "replace-exports-nul" in install_text
    assert '} > "$ENV_FILE"' not in install_text[install_text.index("write_env_file() {"):install_text.index("refresh_canonical_codex_wrapper_template() {")]
    assert "ensure-exports-nul" in config_text
    assert "cat > \"$ENV_FILE\"" not in config_text


def test_p96_private_random_temp_and_predictable_legacy_symlink_is_inert(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_env_module()
    env_file = tmp_path / "env"
    victim = tmp_path / "victim"
    victim.write_text("keep", encoding="utf-8")
    legacy_temp = tmp_path / f".env.tmp-{os.getpid()}"
    legacy_temp.symlink_to(victim)
    observed: dict[str, object] = {}
    original_replace = module.os.replace

    def recording_replace(source, destination):
        source_path = Path(source)
        observed["name"] = source_path.name
        observed["mode"] = _mode(source_path)
        return original_replace(source, destination)

    monkeypatch.setattr(module.os, "replace", recording_replace)
    module.write_env_exports(env_file, {"COX_MODEL_API_KEY": "dummy-secret"})

    assert observed["name"] != legacy_temp.name
    assert str(observed["name"]).startswith(".env.tmp-")
    assert observed["mode"] == 0o600
    assert victim.read_text(encoding="utf-8") == "keep"
    assert legacy_temp.is_symlink()
    assert _mode(env_file) == 0o600
    assert _mode(tmp_path / ".env.lock") == 0o600


def test_p96_rejects_env_and_lock_symlinks_and_hardlinks(tmp_path: Path) -> None:
    module = _load_env_module()
    victim = tmp_path / "victim"
    victim.write_text("keep", encoding="utf-8")

    env_symlink = tmp_path / "env-symlink"
    env_symlink.symlink_to(victim)
    with pytest.raises(module.EnvFileStorageError):
        module.write_env_exports(env_symlink, {"COX_MODEL": "blocked"})
    with pytest.raises(module.EnvFileStorageError):
        module.read_env_exports(env_symlink)
    assert victim.read_text(encoding="utf-8") == "keep"

    env_hardlink = tmp_path / "env-hardlink"
    os.link(victim, env_hardlink)
    with pytest.raises(module.EnvFileStorageError):
        module.write_env_exports(env_hardlink, {"COX_MODEL": "blocked"})
    assert victim.read_text(encoding="utf-8") == "keep"

    env_file = tmp_path / "env"
    lock_victim = tmp_path / "lock-victim"
    lock_victim.write_text("keep-lock", encoding="utf-8")
    (tmp_path / ".env.lock").symlink_to(lock_victim)
    with pytest.raises(module.EnvFileStorageError):
        module.write_env_exports(env_file, {"COX_MODEL": "blocked"})
    assert lock_victim.read_text(encoding="utf-8") == "keep-lock"
    assert not env_file.exists()


def test_p96_concurrent_set_export_and_snapshot_rebase_preserve_updates(tmp_path: Path) -> None:
    env_file = tmp_path / "env"
    barrier = tmp_path / "go"
    ready_a = tmp_path / "ready-a"
    ready_b = tmp_path / "ready-b"
    helper = tmp_path / "writer.py"
    helper.write_text(
        """
import importlib.util
import sys
import time
from pathlib import Path
module_path, env_path, ready_path, barrier_path, key, value = map(Path, sys.argv[1:5]) + tuple(sys.argv[5:])
""".strip(),
        encoding="utf-8",
    )
    # Build the helper without importing the package, so the storage test has no
    # dependency on FastAPI/httpx or the CLI import graph.
    helper.write_text(
        """
import importlib.util
import sys
import time
from pathlib import Path
module_path = Path(sys.argv[1])
env_path = Path(sys.argv[2])
ready_path = Path(sys.argv[3])
barrier_path = Path(sys.argv[4])
key = sys.argv[5]
value = sys.argv[6]
spec = importlib.util.spec_from_file_location("p96_child_env", module_path)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
values = module.read_env_exports(env_path)
ready_path.write_text("ready", encoding="utf-8")
while not barrier_path.exists():
    time.sleep(0.01)
values[key] = value
module.write_env_exports(env_path, values, header=("# concurrent",))
""".lstrip(),
        encoding="utf-8",
    )
    processes = [
        subprocess.Popen([sys.executable, str(helper), str(ENV_MODULE), str(env_file), str(ready_a), str(barrier), "COX_ALPHA", "one"]),
        subprocess.Popen([sys.executable, str(helper), str(ENV_MODULE), str(env_file), str(ready_b), str(barrier), "COX_BETA", "two"]),
    ]
    for _ in range(500):
        if ready_a.exists() and ready_b.exists():
            break
        import time
        time.sleep(0.01)
    assert ready_a.exists() and ready_b.exists()
    barrier.write_text("go", encoding="utf-8")
    assert [process.wait(timeout=20) for process in processes] == [0, 0]

    module = _load_env_module()
    values = module.read_env_exports(env_file)
    assert values["COX_ALPHA"] == "one"
    assert values["COX_BETA"] == "two"


def test_p96_installer_and_legacy_config_route_all_writes_through_shared_tool(tmp_path: Path) -> None:
    install_text = INSTALL.read_text(encoding="utf-8")
    body = install_text[install_text.index("write_env_file() {"):install_text.index("refresh_canonical_codex_wrapper_template() {")]
    assert '"$env_python" "$env_data_tool" replace-exports-nul "$ENV_FILE"' in body
    assert 'backup_local_file_before_overwrite "$ENV_FILE" "local env file"' in body
    assert 'chmod 600 "$ENV_FILE"' not in body

    env_file = tmp_path / "env"
    completed = subprocess.run(
        ["bash", str(COX_CONFIG), "set-model", "p96-model"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={
            **os.environ,
            "COX_PROJECT": str(ROOT),
            "COX_PYTHON": sys.executable,
            "COX_ENV_FILE": str(env_file),
            "CODEX_CONFIG_FILE": str(tmp_path / "codex" / "config.toml"),
            "COX_CONFIG_RESTART_THINKING": "0",
            "PYTHONPATH": str(ROOT),
        },
        check=False,
        timeout=20,
    )
    assert completed.returncode == 0, completed.stderr
    assert _mode(env_file) == 0o600
    assert _mode(tmp_path / ".env.lock") == 0o600
    assert _load_env_module().read_env_exports(env_file)["COX_MODEL"] == "p96-model"
