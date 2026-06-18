from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "scripts" / "codex-wrapper.bash"
WRAPPER_TEXT = WRAPPER.read_text(encoding="utf-8")


def _write_executable(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


def _profile_file(codex_home: Path, profile: str = "demo") -> Path:
    codex_home.mkdir(parents=True, exist_ok=True)
    path = codex_home / f"{profile}.config.toml"
    path.write_text(
        'model = "demo-model"\n'
        'model_provider = "remote-provider"\n'
        '[model_providers.remote-provider]\n'
        'base_url = "https://example.invalid/v1"\n',
        encoding="utf-8",
    )
    return path


def _base_env(tmp_path: Path, native: Path, native_log: Path, cox_log: Path) -> dict[str, str]:
    home = tmp_path / "home"
    codex_home = home / ".codex"
    _profile_file(codex_home)
    env = os.environ.copy()
    env.update(
        {
            "HOME": str(home),
            "CODEX_HOME": str(codex_home),
            "COX_REAL_CODEX": str(native),
            "COX_ENV_FILE": str(tmp_path / "missing-env"),
            "NATIVE_LOG": str(native_log),
            "COX_LOG": str(cox_log),
            "PATH": f"{native.parent}:/usr/bin:/bin",
        }
    )
    return env


def _run_sourced(wrapper: Path, args: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    rendered = " ".join(shlex.quote(arg) for arg in args)
    script = (
        f"source {shlex.quote(str(wrapper))}\n"
        "set +e\n"
        f"codex {rendered}\n"
        "rc=$?\n"
        "printf 'sourced_rc=%s\\n' \"$rc\"\n"
        "exit \"$rc\"\n"
    )
    return subprocess.run(
        ["bash", "--noprofile", "--norc", "-c", script],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        check=False,
        timeout=15,
    )


def _run_executable(wrapper: Path, args: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(wrapper), *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        check=False,
        timeout=15,
    )


def test_p80_profile_parser_accepts_short_flag_and_respects_double_dash(tmp_path: Path) -> None:
    script = (
        f"source {shlex.quote(str(WRAPPER))}\n"
        "printf 'short=%s\\n' \"$(__codexchange_profile_arg -p demo --version)\"\n"
        "printf 'long=%s\\n' \"$(__codexchange_profile_arg --profile demo --version)\"\n"
        "printf 'equals=%s\\n' \"$(__codexchange_profile_arg --profile=demo --version)\"\n"
        "printf 'boundary=%s\\n' \"$(__codexchange_profile_arg -- -p ignored)\"\n"
    )
    result = subprocess.run(
        ["bash", "--noprofile", "--norc", "-c", script],
        text=True,
        capture_output=True,
        check=False,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [
        "short=demo",
        "long=demo",
        "equals=demo",
        "boundary=",
    ]


def test_p80_sourced_and_executable_modes_have_one_common_preflight_and_no_launch_mutations() -> None:
    sourced = WRAPPER_TEXT[
        WRAPPER_TEXT.index("# BEGIN COX UNIFIED INVOCATION-MODE DISPATCH") :
        WRAPPER_TEXT.index("# END COX UNIFIED INVOCATION-MODE DISPATCH")
    ]
    executable = WRAPPER_TEXT[
        WRAPPER_TEXT.index("__codexchange_executable_wrapper_main()") :
        WRAPPER_TEXT.index('if [ "${BASH_SOURCE[0]}" = "$0" ]; then')
    ]

    assert sourced.count('__codexchange_profile_runtime_autostart "$@"') == 1
    assert executable.count('__codexchange_profile_runtime_autostart "$@"') == 1
    assert 'command codex "$@"' not in sourced
    assert '__codexchange_resolve_real_codex' in sourced
    assert 'command "$__codexchange_real_codex" "$@"' in sourced
    assert 'exec "$__codexchange_real_codex" "$@"' in executable
    for forbidden in (
        "cox start thinking",
        "cox config custom-provider use",
        "cox provider install-profile",
        'source "$HOME/.config/codexchange/env"',
    ):
        assert forbidden not in sourced


def test_p80_short_profile_dispatch_is_mutation_free_and_mode_equivalent(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    native_log = tmp_path / "native.log"
    cox_log = tmp_path / "cox.log"
    native = bin_dir / "codex"
    cox = bin_dir / "cox"
    executable_wrapper = tmp_path / "codex-wrapper"
    executable_wrapper.write_bytes(WRAPPER.read_bytes())
    executable_wrapper.chmod(0o755)

    _write_executable(
        native,
        "#!/usr/bin/env bash\n"
        "printf 'native:%s\\n' \"$*\" >>\"$NATIVE_LOG\"\n",
    )
    _write_executable(
        cox,
        "#!/usr/bin/env bash\n"
        "printf 'cox:%s\\n' \"$*\" >>\"$COX_LOG\"\n",
    )
    env = _base_env(tmp_path, native, native_log, cox_log)

    sourced = _run_sourced(WRAPPER, ["-p", "demo", "--version"], env)
    executable = _run_executable(executable_wrapper, ["-p", "demo", "--version"], env)

    assert sourced.returncode == 0, sourced.stderr
    assert executable.returncode == 0, executable.stderr
    assert native_log.read_text(encoding="utf-8").splitlines() == [
        "native:-p demo --version",
        "native:-p demo --version",
    ]
    assert not cox_log.exists()


def test_p80_deprecated_and_unknown_profile_diagnostics_are_mode_equivalent(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    native_log = tmp_path / "native.log"
    cox_log = tmp_path / "cox.log"
    native = bin_dir / "codex"
    executable_wrapper = tmp_path / "codex-wrapper"
    executable_wrapper.write_bytes(WRAPPER.read_bytes())
    executable_wrapper.chmod(0o755)
    _write_executable(
        native,
        "#!/usr/bin/env bash\n"
        "printf 'native:%s\\n' \"$*\" >>\"$NATIVE_LOG\"\n",
    )
    env = _base_env(tmp_path, native, native_log, cox_log)

    for profile, expected in (
        ("deepseek", 'profile "deepseek" is deprecated'),
        ("missing", 'unknown Codex profile "missing"'),
    ):
        sourced = _run_sourced(WRAPPER, ["-p", profile, "--version"], env)
        executable = _run_executable(executable_wrapper, ["-p", profile, "--version"], env)
        assert sourced.returncode == 2
        assert executable.returncode == 2
        assert expected in sourced.stderr
        assert expected in executable.stderr

    assert not native_log.exists()
    assert not cox_log.exists()
