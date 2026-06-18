from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "scripts" / "codex-wrapper.bash"
WRAPPER_TEXT = WRAPPER.read_text(encoding="utf-8")


def _write_executable(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


def _write_profile(codex_home: Path, *, name: str, model: str, provider: str, port: int) -> None:
    codex_home.mkdir(parents=True, exist_ok=True)
    (codex_home / f"{name}.config.toml").write_text(
        f'model = "{model}"\n'
        f'model_provider = "{provider}"\n'
        f'[model_providers.{provider}]\n'
        f'base_url = "http://127.0.0.1:{port}/v1"\n',
        encoding="utf-8",
    )


def _write_registry(path: Path, entries: dict[str, dict[str, object]], *, active: str | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"version": 1, "active_provider": active, "providers": entries}, indent=2) + "\n",
        encoding="utf-8",
    )


def _run_bash(script: str, env: dict[str, str], *, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "--noprofile", "--norc", "-c", script],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        check=False,
        timeout=timeout,
    )


def test_p82_static_contract_uses_native_dispatch_and_isolated_runtime_environment() -> None:
    dispatch = WRAPPER_TEXT[
        WRAPPER_TEXT.index("# BEGIN COX UNIFIED INVOCATION-MODE DISPATCH") :
        WRAPPER_TEXT.index("# END COX UNIFIED INVOCATION-MODE DISPATCH")
    ]
    start = WRAPPER_TEXT[
        WRAPPER_TEXT.index("__codexchange_start_local_proxy()") :
        WRAPPER_TEXT.index("__codexchange_profile_runtime_autostart()")
    ]

    assert 'command codex "$@"' not in dispatch
    assert '__codexchange_resolve_real_codex' in dispatch
    assert 'command "$__codexchange_real_codex" "$@"' in dispatch
    assert "__codexchange_start_local_proxy() (" in start
    assert "__codexchange_profile_runtime_autostart() (" in WRAPPER_TEXT
    assert "__codexchange_load_env_file_data" in start
    assert '__codexchange_bind_custom_provider_registry_entry' in start
    assert 'custom_provider_registry_entry_not_found' in WRAPPER_TEXT
    assert 'COX_MODEL_API_KEY' in WRAPPER_TEXT
    assert 'COX_MODEL_BASE_URL' in WRAPPER_TEXT
    assert 'active_provider' not in start
    assert "unset COX_REASONING COX_TOOL_OUTPUT_TRIM_MODE" in start
    assert 'grep -q "# CodeXchange codex wrapper"' in WRAPPER_TEXT


def test_p82_real_install_sourced_dispatch_runs_one_preflight_and_one_native_codex(tmp_path: Path) -> None:
    home = tmp_path / "home"
    installed_bin = home / ".local" / "bin"
    tool_bin = tmp_path / "tool-bin"
    codex_home = home / ".codex"
    curl_log = tmp_path / "curl.log"
    native_log = tmp_path / "native.log"
    installed_wrapper = installed_bin / "codex"
    native = tool_bin / "native-codex"

    _write_profile(codex_home, name="demo", model="demo-model", provider="demo-proxy", port=18181)
    installed_bin.mkdir(parents=True, exist_ok=True)
    installed_wrapper.write_bytes(WRAPPER.read_bytes())
    installed_wrapper.chmod(0o755)
    _write_executable(
        tool_bin / "curl",
        "#!/usr/bin/env bash\n"
        "printf '%s\\n' \"$*\" >>\"$CURL_LOG\"\n"
        "exit 0\n",
    )
    _write_executable(
        native,
        "#!/usr/bin/env bash\n"
        "printf 'native:%s\\n' \"$*\" >>\"$NATIVE_LOG\"\n",
    )

    env = os.environ.copy()
    env.update(
        {
            "HOME": str(home),
            "CODEX_HOME": str(codex_home),
            "COX_REAL_CODEX": str(native),
            "COX_ENV_FILE": str(tmp_path / "missing-env"),
            "CURL_LOG": str(curl_log),
            "NATIVE_LOG": str(native_log),
            "PATH": f"{installed_bin}:{tool_bin}:/usr/bin:/bin",
        }
    )
    script = (
        f"source {shlex.quote(str(installed_wrapper))}\n"
        "codex -p demo --version\n"
    )
    result = _run_bash(script, env)

    assert result.returncode == 0, result.stderr
    assert len(curl_log.read_text(encoding="utf-8").splitlines()) == 1
    assert native_log.read_text(encoding="utf-8").splitlines() == [
        "native:-p demo --version"
    ]


def test_p82_sequential_profiles_isolate_proxy_start_and_parent_shell_environment(tmp_path: Path) -> None:
    home = tmp_path / "home"
    codex_home = home / ".codex"
    install_dir = tmp_path / "install"
    tool_bin = tmp_path / "tool-bin"
    started_dir = tmp_path / "started"
    proxy_env_log = tmp_path / "proxy-env.tsv"
    native_env_log = tmp_path / "native-env.tsv"
    env_file = tmp_path / "cox-env"
    registry = tmp_path / "model-providers.json"
    native = tool_bin / "native-codex"

    _write_profile(codex_home, name="alpha", model="alpha-model", provider="alpha-proxy", port=8001)
    _write_profile(codex_home, name="beta", model="beta-model", provider="beta-proxy", port=8002)
    _write_registry(
        registry,
        {
            "alpha": {
                "id": "alpha",
                "type": "custom_openai_compatible",
                "display_name": "Alpha",
                "base_url": "https://alpha.example.invalid/v1",
                "api_key": "alpha-secret",
                "active_model": "alpha-model",
                "models": ["alpha-model"],
            },
            "beta": {
                "id": "beta",
                "type": "custom_openai_compatible",
                "display_name": "Beta",
                "base_url": "https://beta.example.invalid/v1",
                "api_key": "beta-secret",
                "active_model": "beta-model",
                "models": ["beta-model"],
            },
        },
        active="alpha",
    )
    started_dir.mkdir(parents=True, exist_ok=True)
    env_file.write_text(
        "export COX_MODEL=stale-model\n"
        "export COX_MODEL_PROVIDER=custom\n"
        "export COX_CUSTOM_PROVIDER_NAME=stale-provider\n"
        "export COX_REASONING=enabled\n"
        "export COX_TOOL_OUTPUT_TRIM_MODE=enabled\n"
        "export COX_MODEL_API_KEY=stale-secret\n"
        "export COX_MODEL_BASE_URL=https://stale.example.invalid/v1\n"
        f"export COX_MODEL_PROVIDER_REGISTRY={registry}\n",
        encoding="utf-8",
    )

    _write_executable(
        native,
        "#!/usr/bin/env bash\n"
        "printf '%s\\t%s\\t%s\\t%s\\t%s\\t%s\\n' "
        '"${COX_PORT-__UNSET__}" "${COX_MODEL-__UNSET__}" '
        '"${COX_MODEL_PROVIDER-__UNSET__}" "${COX_CUSTOM_PROVIDER_NAME-__UNSET__}" '
        '"${COX_REASONING-__UNSET__}" "${PYTHONPATH-__UNSET__}" '
        '>>"$NATIVE_ENV_LOG"\n',
    )
    installed_env_tool = install_dir / "codexchange_proxy" / "env_file.py"
    installed_env_tool.parent.mkdir(parents=True, exist_ok=True)
    installed_env_tool.write_bytes((ROOT / "codexchange_proxy" / "env_file.py").read_bytes())
    _write_executable(
        install_dir / ".venv" / "bin" / "python",
        f"#!{sys.executable}\n"
        "import os, sys\n"
        "from pathlib import Path\n"
        "if len(sys.argv) > 1 and sys.argv[1] == '-':\n"
        "    code = sys.stdin.read()\n"
        "    sys.argv = sys.argv[1:]\n"
        "    namespace = {'__name__': '__main__'}\n"
        "    exec(compile(code, '<stdin>', 'exec'), namespace, namespace)\n"
        "else:\n"
        "    keys=['COX_PORT','COX_MODEL','COX_MODEL_PROVIDER','COX_CUSTOM_PROVIDER_NAME','COX_REASONING','PYTHONPATH','COX_MODEL_API_KEY','COX_MODEL_BASE_URL']\n"
        "    row = '\\t'.join(os.environ.get(key, '__UNSET__') for key in keys)\n"
        "    with open(os.environ['PROXY_ENV_LOG'], 'a', encoding='utf-8') as handle:\n"
        "        handle.write(row + '\\n')\n"
        "    Path(os.environ['STARTED_DIR'], os.environ['COX_PORT']).touch()\n",
    )

    env = os.environ.copy()
    for key in (
        "COX_PORT",
        "COX_MODEL",
        "COX_MODEL_PROVIDER",
        "COX_CUSTOM_PROVIDER_NAME",
        "COX_REASONING",
        "COX_TOOL_OUTPUT_TRIM_MODE",
        "COX_TOOL_OUTPUT_IMAGE_PAYLOAD_MAX_ITEM_CHARS",
    ):
        env.pop(key, None)
    env.update(
        {
            "HOME": str(home),
            "CODEX_HOME": str(codex_home),
            "COX_INSTALL_DIR": str(install_dir),
            "COX_REAL_CODEX": str(native),
            "COX_ENV_FILE": str(env_file),
            "STARTED_DIR": str(started_dir),
            "PROXY_ENV_LOG": str(proxy_env_log),
            "NATIVE_ENV_LOG": str(native_env_log),
            "PATH": f"{tool_bin}:/usr/bin:/bin",
            "REAL_PYTHON": sys.executable,
        }
    )
    tracked = "COX_PORT COX_MODEL COX_MODEL_PROVIDER COX_CUSTOM_PROVIDER_NAME COX_REASONING PYTHONPATH"
    script = (
        f"source {shlex.quote(str(WRAPPER))}\n"
        "__codexchange_proxy_models_ok() { [ -f \"$STARTED_DIR/$1\" ]; }\n"
        "__codexchange_port_open() { return 1; }\n"
        "codex -p alpha --version || exit $?\n"
        f"for key in {tracked}; do printf 'after_alpha:%s=%s\\n' \"$key\" \"${{!key-unset}}\"; done\n"
        "codex -p beta --version || exit $?\n"
        f"for key in {tracked}; do printf 'after_beta:%s=%s\\n' \"$key\" \"${{!key-unset}}\"; done\n"
    )
    result = _run_bash(script, env)

    assert result.returncode == 0, result.stderr
    assert all(line.endswith("=unset") for line in result.stdout.splitlines())

    proxy_rows = [line.split("\t") for line in proxy_env_log.read_text(encoding="utf-8").splitlines()]
    assert proxy_rows == [
        ["8001", "alpha-model", "custom", "alpha", "enabled", str(install_dir), "alpha-secret", "https://alpha.example.invalid/v1"],
        ["8002", "beta-model", "custom", "beta", "__UNSET__", str(install_dir), "beta-secret", "https://beta.example.invalid/v1"],
    ]

    native_rows = [line.split("\t") for line in native_env_log.read_text(encoding="utf-8").splitlines()]
    assert native_rows == [["__UNSET__"] * 6, ["__UNSET__"] * 6]

