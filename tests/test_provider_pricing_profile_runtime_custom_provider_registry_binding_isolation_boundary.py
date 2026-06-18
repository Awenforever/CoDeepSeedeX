from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "scripts" / "codex-wrapper.bash"
WRAPPER_TEXT = WRAPPER.read_text(encoding="utf-8")


def _write_executable(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


def _write_profile(
    codex_home: Path,
    *,
    name: str,
    model: str,
    provider: str,
    port: int,
    model_catalog: Path | None = None,
) -> Path:
    codex_home.mkdir(parents=True, exist_ok=True)
    lines = [
        f'model = "{model}"',
        f'model_provider = "{provider}"',
    ]
    if model_catalog is not None:
        lines.append(f'model_catalog_json = "{model_catalog}"')
    lines.extend(
        [
            f'[model_providers.{provider}]',
            f'base_url = "http://127.0.0.1:{port}/v1"',
        ]
    )
    path = codex_home / f"{name}.config.toml"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _entry(provider_id: str, *, model: str, base_url: str, api_key: str) -> dict[str, object]:
    return {
        "id": provider_id,
        "type": "custom_openai_compatible",
        "display_name": provider_id.title(),
        "base_url": base_url,
        "api_key": api_key,
        "active_model": model,
        "models": [model],
    }


def _write_registry(path: Path, providers: dict[str, dict[str, object]], *, active: str | None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"version": 1, "active_provider": active, "providers": providers}, indent=2) + "\n",
        encoding="utf-8",
    )


def _base_layout(tmp_path: Path) -> dict[str, Path]:
    home = tmp_path / "home"
    codex_home = home / ".codex"
    install_dir = tmp_path / "install"
    tool_bin = tmp_path / "tool-bin"
    started_dir = tmp_path / "started"
    env_file = tmp_path / "cox-env"
    registry = tmp_path / "model-providers.json"
    proxy_log = tmp_path / "proxy-env.jsonl"
    native_log = tmp_path / "native-env.jsonl"
    started_dir.mkdir(parents=True, exist_ok=True)
    return {
        "home": home,
        "codex_home": codex_home,
        "install_dir": install_dir,
        "tool_bin": tool_bin,
        "started_dir": started_dir,
        "env_file": env_file,
        "registry": registry,
        "proxy_log": proxy_log,
        "native_log": native_log,
    }


def _install_fakes(layout: dict[str, Path]) -> Path:
    native = layout["tool_bin"] / "native-codex"
    installed_env_tool = layout["install_dir"] / "codexchange_proxy" / "env_file.py"
    installed_env_tool.parent.mkdir(parents=True, exist_ok=True)
    installed_env_tool.write_bytes((ROOT / "codexchange_proxy" / "env_file.py").read_bytes())
    _write_executable(
        native,
        "#!/usr/bin/env bash\n"
        "python3 - <<'PY' >>\"$NATIVE_ENV_LOG\"\n"
        "import json, os\n"
        "keys=['COX_MODEL_API_KEY','COX_MODEL_BASE_URL','COX_CUSTOM_PROVIDER_NAME','COX_MODEL','COX_PORT']\n"
        "print(json.dumps({k: os.environ.get(k, '__UNSET__') for k in keys}, sort_keys=True))\n"
        "PY\n",
    )
    _write_executable(
        layout["install_dir"] / ".venv" / "bin" / "python",
        f"#!{sys.executable}\n"
        "import json, os, sys\n"
        "from pathlib import Path\n"
        "if len(sys.argv) > 1 and sys.argv[1] == '-':\n"
        "    code = sys.stdin.read()\n"
        "    sys.argv = sys.argv[1:]\n"
        "    namespace = {'__name__': '__main__'}\n"
        "    exec(compile(code, '<stdin>', 'exec'), namespace, namespace)\n"
        "else:\n"
        "    keys=['COX_MODEL_PROVIDER','COX_CUSTOM_PROVIDER_NAME','COX_MODEL_BASE_URL','COX_MODEL_API_KEY','COX_MODEL','COX_PORT','COX_MODEL_PROVIDER_REGISTRY']\n"
        "    with open(os.environ['PROXY_ENV_LOG'], 'a', encoding='utf-8') as handle:\n"
        "        handle.write(json.dumps({k: os.environ.get(k, '__UNSET__') for k in keys}, sort_keys=True) + '\\n')\n"
        "    Path(os.environ['STARTED_DIR'], os.environ['COX_PORT']).touch()\n",
    )
    return native


def _environment(layout: dict[str, Path], native: Path) -> dict[str, str]:
    env = os.environ.copy()
    for key in (
        "COX_MODEL_API_KEY",
        "COX_MODEL_BASE_URL",
        "COX_MODEL_PROVIDER",
        "COX_CUSTOM_PROVIDER_NAME",
        "COX_MODEL",
        "COX_PORT",
        "COX_REASONING",
        "COX_TOOL_OUTPUT_TRIM_MODE",
        "COX_TOOL_OUTPUT_IMAGE_PAYLOAD_MAX_ITEM_CHARS",
    ):
        env.pop(key, None)
    env.update(
        {
            "HOME": str(layout["home"]),
            "CODEX_HOME": str(layout["codex_home"]),
            "COX_INSTALL_DIR": str(layout["install_dir"]),
            "COX_REAL_CODEX": str(native),
            "COX_ENV_FILE": str(layout["env_file"]),
            "STARTED_DIR": str(layout["started_dir"]),
            "PROXY_ENV_LOG": str(layout["proxy_log"]),
            "NATIVE_ENV_LOG": str(layout["native_log"]),
            "REAL_PYTHON": sys.executable,
            "PATH": f"{layout['tool_bin']}:/usr/bin:/bin",
        }
    )
    return env


def _run_profile(profile: str, env: dict[str, str], *, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    script = (
        f"source {shlex.quote(str(WRAPPER))}\n"
        '__codexchange_proxy_models_ok() { [ -f "$STARTED_DIR/$1" ]; }\n'
        "__codexchange_port_open() { return 1; }\n"
        f"codex -p {shlex.quote(profile)} --version\n"
    )
    return subprocess.run(
        ["bash", "--noprofile", "--norc", "-c", script],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        check=False,
        timeout=timeout,
    )


def test_p86_static_contract_binds_registry_without_active_provider_fallback() -> None:
    helper = WRAPPER_TEXT[
        WRAPPER_TEXT.index("__codexchange_bind_custom_provider_registry_entry()") :
        WRAPPER_TEXT.index("__codexchange_start_local_proxy()")
    ]
    start = WRAPPER_TEXT[
        WRAPPER_TEXT.index("__codexchange_start_local_proxy()") :
        WRAPPER_TEXT.index("__codexchange_profile_runtime_autostart()")
    ]
    assert "custom_provider_registry_entry_not_found" in helper
    assert "custom_provider_registry_binding_ambiguous" in helper
    assert "custom_provider_registry_api_key_missing" in helper
    assert "custom_provider_profile_model_not_registered" in helper
    assert 'registry.get("active_provider")' not in helper
    assert "COX_MODEL_BASE_URL" in helper
    assert "COX_MODEL_API_KEY" in helper
    assert "base64 --decode" not in helper
    assert "mktemp" in helper
    assert "read -r -d ''" in helper
    assert "COX_MODEL_PROVIDER_REGISTRY" in helper
    assert '"$profile_file"' in start


def test_p86_alias_profile_uses_model_catalog_provider_id_not_active_provider(tmp_path: Path) -> None:
    layout = _base_layout(tmp_path)
    native = _install_fakes(layout)
    catalog = layout["codex_home"] / "model-catalogs" / "custom.json"
    catalog.parent.mkdir(parents=True, exist_ok=True)
    catalog.write_text(
        json.dumps(
            {
                "version": 1,
                "models": [
                    {
                        "id": "beta-model",
                        "model": "beta-model",
                        "provider": "research-alias-proxy",
                        "provider_id": "beta",
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    _write_profile(
        layout["codex_home"],
        name="research-alias",
        model="beta-model",
        provider="research-alias-proxy",
        port=18182,
        model_catalog=catalog,
    )
    _write_registry(
        layout["registry"],
        {
            "alpha": _entry(
                "alpha",
                model="alpha-model",
                base_url="https://alpha.example.invalid/v1",
                api_key="alpha-secret-never-use",
            ),
            "beta": _entry(
                "beta",
                model="beta-model",
                base_url="https://beta.example.invalid/v1",
                api_key="beta-secret-selected",
            ),
        },
        active="alpha",
    )
    layout["env_file"].write_text(
        "export COX_MODEL_PROVIDER=custom\n"
        "export COX_CUSTOM_PROVIDER_NAME=alpha\n"
        "export COX_MODEL_BASE_URL=https://alpha.example.invalid/v1\n"
        "export COX_MODEL_API_KEY=alpha-secret-never-use\n"
        f"export COX_MODEL_PROVIDER_REGISTRY={layout['registry']}\n",
        encoding="utf-8",
    )

    result = _run_profile("research-alias", _environment(layout, native))

    assert result.returncode == 0, result.stderr
    rows = [json.loads(line) for line in layout["proxy_log"].read_text(encoding="utf-8").splitlines()]
    assert rows == [
        {
            "COX_CUSTOM_PROVIDER_NAME": "beta",
            "COX_MODEL": "beta-model",
            "COX_MODEL_API_KEY": "beta-secret-selected",
            "COX_MODEL_BASE_URL": "https://beta.example.invalid/v1",
            "COX_MODEL_PROVIDER": "custom",
            "COX_MODEL_PROVIDER_REGISTRY": str(layout["registry"]),
            "COX_PORT": "18182",
        }
    ]
    native_rows = [json.loads(line) for line in layout["native_log"].read_text(encoding="utf-8").splitlines()]
    assert native_rows == [
        {
            "COX_CUSTOM_PROVIDER_NAME": "__UNSET__",
            "COX_MODEL": "__UNSET__",
            "COX_MODEL_API_KEY": "__UNSET__",
            "COX_MODEL_BASE_URL": "__UNSET__",
            "COX_PORT": "__UNSET__",
        }
    ]
    assert "alpha-secret-never-use" not in result.stdout
    assert "alpha-secret-never-use" not in result.stderr
    assert "beta-secret-selected" not in result.stdout
    assert "beta-secret-selected" not in result.stderr


def test_p86_sequential_profiles_bind_distinct_credentials_without_parent_leak(tmp_path: Path) -> None:
    layout = _base_layout(tmp_path)
    native = _install_fakes(layout)
    _write_profile(layout["codex_home"], name="alpha", model="alpha-model", provider="alpha-proxy", port=18183)
    _write_profile(layout["codex_home"], name="beta", model="beta-model", provider="beta-proxy", port=18184)
    _write_registry(
        layout["registry"],
        {
            "alpha": _entry("alpha", model="alpha-model", base_url="https://alpha.example.invalid/v1", api_key="alpha-key"),
            "beta": _entry("beta", model="beta-model", base_url="https://beta.example.invalid/v1", api_key="beta-key"),
        },
        active="alpha",
    )
    layout["env_file"].write_text(
        "export COX_MODEL_PROVIDER=custom\n"
        "export COX_CUSTOM_PROVIDER_NAME=alpha\n"
        "export COX_MODEL_BASE_URL=https://alpha.example.invalid/v1\n"
        "export COX_MODEL_API_KEY=alpha-key\n"
        f"export COX_MODEL_PROVIDER_REGISTRY={layout['registry']}\n",
        encoding="utf-8",
    )
    env = _environment(layout, native)
    tracked = "COX_MODEL_API_KEY COX_MODEL_BASE_URL COX_CUSTOM_PROVIDER_NAME COX_MODEL COX_PORT"
    script = (
        f"source {shlex.quote(str(WRAPPER))}\n"
        '__codexchange_proxy_models_ok() { [ -f "$STARTED_DIR/$1" ]; }\n'
        "__codexchange_port_open() { return 1; }\n"
        "codex -p alpha --version || exit $?\n"
        f"for key in {tracked}; do printf 'alpha:%s=%s\\n' \"$key\" \"${{!key-unset}}\"; done\n"
        "codex -p beta --version || exit $?\n"
        f"for key in {tracked}; do printf 'beta:%s=%s\\n' \"$key\" \"${{!key-unset}}\"; done\n"
    )
    result = subprocess.run(
        ["bash", "--noprofile", "--norc", "-c", script],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        check=False,
        timeout=60,
    )

    assert result.returncode == 0, result.stderr
    assert all(line.endswith("=unset") for line in result.stdout.splitlines())
    rows = [json.loads(line) for line in layout["proxy_log"].read_text(encoding="utf-8").splitlines()]
    assert [(row["COX_CUSTOM_PROVIDER_NAME"], row["COX_MODEL_API_KEY"], row["COX_MODEL_BASE_URL"]) for row in rows] == [
        ("alpha", "alpha-key", "https://alpha.example.invalid/v1"),
        ("beta", "beta-key", "https://beta.example.invalid/v1"),
    ]


def test_p86_concurrent_profiles_bind_distinct_registry_entries(tmp_path: Path) -> None:
    layout = _base_layout(tmp_path)
    native = _install_fakes(layout)
    _write_profile(layout["codex_home"], name="alpha", model="alpha-model", provider="alpha-proxy", port=18185)
    _write_profile(layout["codex_home"], name="beta", model="beta-model", provider="beta-proxy", port=18186)
    _write_registry(
        layout["registry"],
        {
            "alpha": _entry("alpha", model="alpha-model", base_url="https://alpha.example.invalid/v1", api_key="alpha-key"),
            "beta": _entry("beta", model="beta-model", base_url="https://beta.example.invalid/v1", api_key="beta-key"),
        },
        active="alpha",
    )
    layout["env_file"].write_text(
        "export COX_MODEL_PROVIDER=custom\n"
        "export COX_MODEL_API_KEY=stale-key\n"
        "export COX_MODEL_BASE_URL=https://stale.example.invalid/v1\n"
        f"export COX_MODEL_PROVIDER_REGISTRY={layout['registry']}\n",
        encoding="utf-8",
    )
    env = _environment(layout, native)
    script = (
        f"source {shlex.quote(str(WRAPPER))}\n"
        '__codexchange_proxy_models_ok() { [ -f "$STARTED_DIR/$1" ]; }\n'
        "__codexchange_port_open() { return 1; }\n"
        'codex -p "$PROFILE" --version\n'
    )
    processes = []
    for profile in ("alpha", "beta"):
        process_env = dict(env)
        process_env["PROFILE"] = profile
        processes.append(
            subprocess.Popen(
                ["bash", "--noprofile", "--norc", "-c", script],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=process_env,
            )
        )
    results = [process.communicate(timeout=60) + (process.returncode,) for process in processes]

    assert all(returncode == 0 for _stdout, _stderr, returncode in results), results
    rows = [json.loads(line) for line in layout["proxy_log"].read_text(encoding="utf-8").splitlines()]
    observed = {
        (row["COX_CUSTOM_PROVIDER_NAME"], row["COX_MODEL_API_KEY"], row["COX_MODEL_BASE_URL"], row["COX_PORT"])
        for row in rows
    }
    assert observed == {
        ("alpha", "alpha-key", "https://alpha.example.invalid/v1", "18185"),
        ("beta", "beta-key", "https://beta.example.invalid/v1", "18186"),
    }


@pytest.mark.parametrize(
    ("providers", "profile", "provider", "model", "expected_error"),
    [
        ({}, "missing", "missing-proxy", "missing-model", "custom_provider_registry_entry_not_found"),
        (
            {
                "incomplete": {
                    "id": "incomplete",
                    "type": "custom_openai_compatible",
                    "base_url": "https://incomplete.example.invalid/v1",
                    "active_model": "incomplete-model",
                    "models": ["incomplete-model"],
                }
            },
            "incomplete",
            "incomplete-proxy",
            "incomplete-model",
            "custom_provider_registry_api_key_missing",
        ),
        (
            {
                "wrong-model": _entry(
                    "wrong-model",
                    model="registered-model",
                    base_url="https://wrong-model.example.invalid/v1",
                    api_key="secret-never-print",
                )
            },
            "wrong-model",
            "wrong-model-proxy",
            "profile-model",
            "custom_provider_profile_model_not_registered",
        ),
        (
            {
                "ambiguous-profile": _entry(
                    "ambiguous-profile",
                    model="shared-model",
                    base_url="https://one.example.invalid/v1",
                    api_key="secret-one",
                ),
                "ambiguous-provider": _entry(
                    "ambiguous-provider",
                    model="shared-model",
                    base_url="https://two.example.invalid/v1",
                    api_key="secret-two",
                ),
            },
            "ambiguous-profile",
            "ambiguous-provider-proxy",
            "shared-model",
            "custom_provider_registry_binding_ambiguous",
        ),
    ],
)
def test_p86_invalid_registry_binding_fails_closed_without_secret_output(
    tmp_path: Path,
    providers: dict[str, dict[str, object]],
    profile: str,
    provider: str,
    model: str,
    expected_error: str,
) -> None:
    layout = _base_layout(tmp_path)
    native = _install_fakes(layout)
    _write_profile(layout["codex_home"], name=profile, model=model, provider=provider, port=18187)
    _write_registry(layout["registry"], providers, active=next(iter(providers), None))
    layout["env_file"].write_text(
        "export COX_MODEL_API_KEY=global-secret-never-print\n"
        "export COX_MODEL_BASE_URL=https://global.example.invalid/v1\n"
        f"export COX_MODEL_PROVIDER_REGISTRY={layout['registry']}\n",
        encoding="utf-8",
    )

    result = _run_profile(profile, _environment(layout, native))

    assert result.returncode == 70
    assert expected_error in result.stderr
    assert not layout["proxy_log"].exists()
    assert not layout["native_log"].exists()
    combined = result.stdout + result.stderr
    for secret in ("global-secret-never-print", "secret-never-print", "secret-one", "secret-two"):
        assert secret not in combined


def test_p86_managed_cox_profile_preserves_explicitly_active_shared_provider_without_registry(tmp_path: Path) -> None:
    layout = _base_layout(tmp_path)
    native = _install_fakes(layout)
    _write_profile(layout["codex_home"], name="cox", model="deepseek-model", provider="cox-proxy", port=18188)
    layout["env_file"].write_text(
        "export COX_MODEL_PROVIDER=deepseek\n"
        "export COX_MODEL_BASE_URL=https://api.deepseek.example.invalid\n"
        "export COX_MODEL_API_KEY=managed-cox-key\n",
        encoding="utf-8",
    )

    result = _run_profile("cox", _environment(layout, native))

    assert result.returncode == 0, result.stderr
    rows = [json.loads(line) for line in layout["proxy_log"].read_text(encoding="utf-8").splitlines()]
    assert rows == [
        {
            "COX_CUSTOM_PROVIDER_NAME": "__UNSET__",
            "COX_MODEL": "deepseek-model",
            "COX_MODEL_API_KEY": "managed-cox-key",
            "COX_MODEL_BASE_URL": "https://api.deepseek.example.invalid",
            "COX_MODEL_PROVIDER": "deepseek",
            "COX_MODEL_PROVIDER_REGISTRY": "__UNSET__",
            "COX_PORT": "18188",
        }
    ]
