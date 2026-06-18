from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "scripts" / "install.sh"
INSTALLER_TEXT = INSTALLER.read_text(encoding="utf-8")
FUNCTION_BLOCK = INSTALLER_TEXT[
    INSTALLER_TEXT.index("choose_shell_profile_file() {") :
    INSTALLER_TEXT.index("post_install_entrypoint_diagnostics() {")
]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _base_env(home: Path) -> dict[str, str]:
    env = os.environ.copy()
    for name in list(env):
        if name.startswith(("COX_", "DEEPSEEK_")):
            env.pop(name, None)
    env.update(
        {
            "HOME": str(home),
            "SHELL": "/bin/bash",
            "P84_BIN_DIR": str(home / ".local" / "bin"),
            "P84_ENV_FILE": str(home / ".config" / "codexchange" / "env"),
            "P84_STATE_FILE": str(home / ".config" / "codexchange" / "shell-profiles.list"),
            "P84_INSTALL_LOG": str(home / "install.log"),
            "P84_BACKUP_DIR": str(home / "backups"),
        }
    )
    return env


def _run_functions(home: Path, body: str) -> subprocess.CompletedProcess[str]:
    prelude = r'''
set -euo pipefail
BIN_DIR="$P84_BIN_DIR"
ENV_FILE="$P84_ENV_FILE"
SHELL_PROFILE_STATE_FILE="$P84_STATE_FILE"
INSTALL_LOG="$P84_INSTALL_LOG"
LOCAL_BACKUP_DIR="$P84_BACKUP_DIR"
DRY_RUN=0
INSTALL_SHELL_PROFILE=1
SHELL_PROFILE_FILE=""
COX_SHELL_PROFILE="${COX_SHELL_PROFILE:-}"
ok() { :; }
warn() { :; }
backup_local_file_before_overwrite() {
  local path="$1"
  local label="$2"
  [ -e "$path" ] || return 0
  mkdir -p "$LOCAL_BACKUP_DIR"
  cp -p "$path" "$LOCAL_BACKUP_DIR/$(basename "$path").backup"
  printf 'backup:%s:%s\n' "$label" "$path" >> "$INSTALL_LOG"
}
'''
    result = subprocess.run(
        ["bash", "-c", prelude + "\n" + FUNCTION_BLOCK + "\n" + body],
        cwd=ROOT,
        env=_base_env(home),
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    return result


def _source_profile(profile: Path, home: Path, command: str) -> subprocess.CompletedProcess[str]:
    env = _base_env(home)
    env.pop("COX_MODEL_API_KEY", None)
    env.pop("COX_MODEL_PROVIDER", None)
    env.pop("COX_CUSTOM_PROVIDER_NAME", None)
    env.pop("COX_MODEL", None)
    env.pop("COX_PORT", None)
    env.pop("COX_REASONING", None)
    return subprocess.run(
        ["bash", "--noprofile", "--norc", "-c", f'. "$1"; {command}', "bash", str(profile)],
        env=env,
        text=True,
        capture_output=True,
        timeout=15,
        check=False,
    )


def test_p84_shell_startup_block_is_path_only_and_runtime_env_stays_on_demand() -> None:
    section = FUNCTION_BLOCK[
        FUNCTION_BLOCK.index("append_minimal_shell_profile_block() {") :
        FUNCTION_BLOCK.index("record_shell_profile_path() {")
    ]
    ensure = FUNCTION_BLOCK[
        FUNCTION_BLOCK.index("ensure_shell_profile_integration() {") :
    ]
    uninstall = INSTALLER_TEXT[INSTALLER_TEXT.index("uninstall() {") :]

    assert "# >>> CodeXchange managed PATH >>>" in section
    assert "# <<< CodeXchange managed PATH <<<" in section
    assert 'export PATH="$BIN_DIR:\\$PATH"' in section
    assert "ENV_FILE" not in section
    assert '. "$ENV_FILE"' not in ensure
    assert "remove_shell_profile_integrations" in uninstall
    assert uninstall.index("remove_shell_profile_integrations") < uninstall.index('rm -f "$wrapper_path"')
    assert 'SHELL_PROFILE_STATE_FILE="$SHELL_PROFILE_STATE_FILE"' in INSTALLER_TEXT


def test_p84_fresh_install_adds_minimal_bootstrap_without_secret_inheritance(tmp_path: Path) -> None:
    home = tmp_path / "home"
    bashrc = home / ".bashrc"
    env_file = home / ".config" / "codexchange" / "env"
    bashrc.parent.mkdir(parents=True)
    env_file.parent.mkdir(parents=True)
    (home / ".local" / "bin").mkdir(parents=True)
    bashrc.write_text("export USER_SETTING=keep\n", encoding="utf-8")
    env_file.write_text(
        "export COX_MODEL_API_KEY=p84-dummy-secret\n"
        "export COX_MODEL_PROVIDER=custom\n"
        "export COX_CUSTOM_PROVIDER_NAME=stale-provider\n"
        "export COX_MODEL=stale-model\n"
        "export COX_PORT=18888\n"
        "export COX_REASONING=enabled\n",
        encoding="utf-8",
    )

    result = _run_functions(home, "ensure_shell_profile_integration\n")
    assert result.returncode == 0, result.stdout + result.stderr

    profile_text = bashrc.read_text(encoding="utf-8")
    assert profile_text.count("# >>> CodeXchange managed PATH >>>") == 1
    assert profile_text.count("# <<< CodeXchange managed PATH <<<") == 1
    assert "USER_SETTING=keep" in profile_text
    assert "codexchange/env" not in profile_text
    assert "COX_MODEL_API_KEY" not in profile_text

    shell = _source_profile(
        bashrc,
        home,
        "printf 'key=%s\\nprovider=%s\\nmodel=%s\\nport=%s\\nreasoning=%s\\npath=%s\\n' "
        '"${COX_MODEL_API_KEY-__UNSET__}" "${COX_CUSTOM_PROVIDER_NAME-__UNSET__}" '
        '"${COX_MODEL-__UNSET__}" "${COX_PORT-__UNSET__}" "${COX_REASONING-__UNSET__}" "$PATH"',
    )
    assert shell.returncode == 0, shell.stdout + shell.stderr
    assert "key=__UNSET__" in shell.stdout
    assert "provider=__UNSET__" in shell.stdout
    assert "model=__UNSET__" in shell.stdout
    assert "port=__UNSET__" in shell.stdout
    assert "reasoning=__UNSET__" in shell.stdout
    assert str(home / ".local" / "bin") in shell.stdout


def test_p84_upgrade_replaces_legacy_env_sourcing_block_and_is_idempotent(tmp_path: Path) -> None:
    home = tmp_path / "home"
    bashrc = home / ".bashrc"
    env_file = home / ".config" / "codexchange" / "env"
    bin_dir = home / ".local" / "bin"
    bashrc.parent.mkdir(parents=True)
    env_file.parent.mkdir(parents=True)
    env_file.write_text("export COX_MODEL_API_KEY=p84-upgrade-secret\n", encoding="utf-8")
    bashrc.write_text(
        "export BEFORE_KEEP=1\n"
        "# CodeXchange environment\n"
        f'if [ -d "{bin_dir}" ]; then\n'
        '  case ":$PATH:" in\n'
        f'    *:"{bin_dir}":*) ;;\n'
        f'    *) export PATH="{bin_dir}:$PATH" ;;\n'
        "  esac\n"
        "fi\n"
        f'if [ -f "{env_file}" ]; then\n'
        f'  . "{env_file}"\n'
        "fi\n"
        "export AFTER_KEEP=1\n",
        encoding="utf-8",
    )

    first = _run_functions(home, "ensure_shell_profile_integration\n")
    assert first.returncode == 0, first.stdout + first.stderr
    first_hash = _sha256(bashrc)
    upgraded = bashrc.read_text(encoding="utf-8")
    assert "# CodeXchange environment" not in upgraded
    assert str(env_file) not in upgraded
    assert "export BEFORE_KEEP=1" in upgraded
    assert "export AFTER_KEEP=1" in upgraded
    assert upgraded.count("# >>> CodeXchange managed PATH >>>") == 1

    second = _run_functions(home, "ensure_shell_profile_integration\n")
    assert second.returncode == 0, second.stdout + second.stderr
    assert _sha256(bashrc) == first_hash
    state = home / ".config" / "codexchange" / "shell-profiles.list"
    assert state.read_text(encoding="utf-8").splitlines().count(str(bashrc)) == 1


def test_p84_uninstall_cleanup_removes_only_managed_blocks_and_state(tmp_path: Path) -> None:
    home = tmp_path / "home"
    custom = home / "shell" / "custom.rc"
    custom.parent.mkdir(parents=True)
    custom.write_text("export KEEP_BEFORE=yes\nexport KEEP_AFTER=yes\n", encoding="utf-8")

    env = _base_env(home)
    env["COX_SHELL_PROFILE"] = str(custom)
    prelude = r'''
set -euo pipefail
BIN_DIR="$P84_BIN_DIR"
ENV_FILE="$P84_ENV_FILE"
SHELL_PROFILE_STATE_FILE="$P84_STATE_FILE"
INSTALL_LOG="$P84_INSTALL_LOG"
LOCAL_BACKUP_DIR="$P84_BACKUP_DIR"
DRY_RUN=0
INSTALL_SHELL_PROFILE=1
SHELL_PROFILE_FILE=""
ok() { :; }
warn() { :; }
backup_local_file_before_overwrite() {
  local path="$1"
  local label="$2"
  [ -e "$path" ] || return 0
  mkdir -p "$LOCAL_BACKUP_DIR"
  cp -p "$path" "$LOCAL_BACKUP_DIR/$(basename "$path").backup"
}
'''
    result = subprocess.run(
        [
            "bash",
            "-c",
            prelude
            + "\n"
            + FUNCTION_BLOCK
            + "\nensure_shell_profile_integration\nremove_shell_profile_integrations\n",
        ],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    text = custom.read_text(encoding="utf-8")
    assert "KEEP_BEFORE=yes" in text
    assert "KEEP_AFTER=yes" in text
    assert "CodeXchange managed PATH" not in text
    assert not (home / ".config" / "codexchange" / "shell-profiles.list").exists()


def test_p84_unrelated_native_child_does_not_receive_shared_runtime_env(tmp_path: Path) -> None:
    home = tmp_path / "home"
    bashrc = home / ".bashrc"
    env_file = home / ".config" / "codexchange" / "env"
    native = home / "native-codex"
    native_log = home / "native.log"
    bashrc.parent.mkdir(parents=True)
    env_file.parent.mkdir(parents=True)
    bashrc.write_text("", encoding="utf-8")
    env_file.write_text(
        "export COX_MODEL_API_KEY=p84-native-secret\n"
        "export COX_CUSTOM_PROVIDER_NAME=stale-native-provider\n"
        "export COX_MODEL=stale-native-model\n"
        "export COX_PORT=19999\n",
        encoding="utf-8",
    )
    native.write_text(
        "#!/usr/bin/env bash\n"
        "printf 'key=%s\\nprovider=%s\\nmodel=%s\\nport=%s\\n' "
        '"${COX_MODEL_API_KEY-__UNSET__}" "${COX_CUSTOM_PROVIDER_NAME-__UNSET__}" '
        '"${COX_MODEL-__UNSET__}" "${COX_PORT-__UNSET__}" > "$NATIVE_LOG"\n',
        encoding="utf-8",
    )
    native.chmod(0o755)

    result = _run_functions(home, "ensure_shell_profile_integration\n")
    assert result.returncode == 0, result.stdout + result.stderr

    env = _base_env(home)
    env["NATIVE_LOG"] = str(native_log)
    child = subprocess.run(
        ["bash", "--noprofile", "--norc", "-c", '. "$1"; "$2"', "bash", str(bashrc), str(native)],
        env=env,
        text=True,
        capture_output=True,
        timeout=15,
        check=False,
    )
    assert child.returncode == 0, child.stdout + child.stderr
    assert native_log.read_text(encoding="utf-8").splitlines() == [
        "key=__UNSET__",
        "provider=__UNSET__",
        "model=__UNSET__",
        "port=__UNSET__",
    ]
