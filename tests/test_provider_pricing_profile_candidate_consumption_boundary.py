from __future__ import annotations

import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "scripts" / "codex-wrapper.bash"


def _run_bash(script: str, *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    clean_env = dict(os.environ)
    for key in list(clean_env):
        if key.startswith("COX_PRICING_"):
            clean_env.pop(key, None)
    if env:
        clean_env.update(env)
    return subprocess.run(
        ["bash", "-c", script],
        cwd=ROOT,
        env=clean_env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def _profile_files(tmp_path: Path, profile_body: str) -> tuple[Path, Path]:
    codex_home = tmp_path / "codex"
    codex_home.mkdir()
    profile = codex_home / "sample.config.toml"
    profile.write_text(profile_body, encoding="utf-8")
    config = codex_home / "config.toml"
    config.write_text(
        "[model_providers.sample-proxy]\n"
        'base_url = "http://127.0.0.1:8123/v1"\n',
        encoding="utf-8",
    )
    return codex_home, profile


def test_profile_without_pricing_fields_consumes_exact_legacy_start_contract(tmp_path: Path) -> None:
    codex_home, profile = _profile_files(
        tmp_path,
        'model = "example-model"\nmodel_provider = "sample-proxy"\n',
    )
    capture = tmp_path / "capture.txt"
    script = f'''
source {WRAPPER!s}
__codexchange_proxy_models_ok() {{ return 1; }}
__codexchange_port_open() {{ return 1; }}
__codexchange_start_local_proxy() {{ printf '%s\\n' "$@" > {capture!s}; }}
CODEX_HOME={codex_home!s}
__codexchange_profile_runtime_autostart --profile sample
'''
    result = _run_bash(script)
    assert result.returncode == 0, result.stderr
    assert capture.read_text(encoding="utf-8").splitlines() == [
        "8123",
        "sample",
        "example-model",
        "sample-proxy",
        "",
        "",
        "",
        str(profile),
    ]


def test_complete_profile_candidate_maps_only_explicit_fields_to_runtime_arguments(tmp_path: Path) -> None:
    pricing = tmp_path / "pricing.json"
    pricing.write_text("{}\n", encoding="utf-8")
    codex_home, profile = _profile_files(
        tmp_path,
        'model = "example-model"\n'
        'model_provider = "unrelated-proxy"\n'
        'pricing_provider_id = "Example-Provider"\n'
        'pricing_provider_owned = true\n'
        'pricing_mode = "provider-owned"\n'
        f'pricing_provider_path = "{pricing}"\n',
    )
    config = codex_home / "config.toml"
    config.write_text(
        "[model_providers.unrelated-proxy]\n"
        'base_url = "http://127.0.0.1:8123/v1"\n',
        encoding="utf-8",
    )
    capture = tmp_path / "capture.txt"
    script = f'''
source {WRAPPER!s}
__codexchange_proxy_models_ok() {{ return 1; }}
__codexchange_port_open() {{ return 1; }}
__codexchange_start_local_proxy() {{ printf '%s\\n' "$@" > {capture!s}; }}
CODEX_HOME={codex_home!s}
__codexchange_profile_runtime_autostart --profile sample
'''
    result = _run_bash(script)
    assert result.returncode == 0, result.stderr
    assert capture.read_text(encoding="utf-8").splitlines() == [
        "8123",
        "sample",
        "example-model",
        "unrelated-proxy",
        "example_provider",
        "provider_owned",
        str(pricing),
        str(profile),
    ]


def test_partial_profile_candidate_fails_closed_before_start(tmp_path: Path) -> None:
    codex_home, profile = _profile_files(
        tmp_path,
        'model = "example-model"\n'
        'model_provider = "sample-proxy"\n'
        'pricing_provider_id = "example"\n',
    )
    capture = tmp_path / "capture.txt"
    script = f'''
source {WRAPPER!s}
__codexchange_start_local_proxy() {{ touch {capture!s}; }}
CODEX_HOME={codex_home!s}
__codexchange_profile_runtime_autostart --profile sample
'''
    result = _run_bash(script)
    assert result.returncode == 70
    assert "profile pricing fields are incomplete" in result.stderr
    assert not capture.exists()


def test_pricing_environment_does_not_activate_legacy_profile(tmp_path: Path) -> None:
    codex_home, profile = _profile_files(
        tmp_path,
        'model = "example-model"\nmodel_provider = "sample-proxy"\n',
    )
    capture = tmp_path / "capture.txt"
    script = f'''
source {WRAPPER!s}
__codexchange_proxy_models_ok() {{ return 1; }}
__codexchange_port_open() {{ return 1; }}
__codexchange_start_local_proxy() {{ printf '%s\\n' "$@" > {capture!s}; }}
CODEX_HOME={codex_home!s}
__codexchange_profile_runtime_autostart --profile sample
'''
    result = _run_bash(
        script,
        env={
            "COX_PRICING_PROVIDER_ID": "ignored",
            "COX_PRICING_PROVIDER_OWNED": "1",
            "COX_PRICING_MODE": "provider_owned",
            "COX_PRICING_PROVIDER_PATH": "/tmp/ignored.json",
        },
    )
    assert result.returncode == 0, result.stderr
    assert capture.read_text(encoding="utf-8").splitlines()[4:] == ["", "", "", str(profile)]


def test_start_function_selects_static_or_explicit_runtime_from_arguments(tmp_path: Path) -> None:
    install_dir = tmp_path / "install"
    python_bin = install_dir / ".venv" / "bin" / "python"
    python_bin.parent.mkdir(parents=True)
    python_bin.write_text(
        "#!/usr/bin/env bash\nprintf '%s\\n' \"$@\" > \"$COX_CAPTURE\"\n",
        encoding="utf-8",
    )
    python_bin.chmod(0o755)
    pricing = tmp_path / "pricing.json"
    pricing.write_text("{}\n", encoding="utf-8")
    state_dir = tmp_path / "state"
    log_dir = tmp_path / "logs"

    legacy_provider = "".join(("deepseek", "-proxy"))
    legacy_capture = tmp_path / "legacy.txt"
    legacy_script = f'''
source {WRAPPER!s}
__codexchange_proxy_models_ok() {{ return 0; }}
COX_INSTALL_DIR={install_dir!s}
COX_LOG_DIR={log_dir!s}
COX_STATE_DIR={state_dir!s}
COX_CAPTURE={legacy_capture!s}
export COX_CAPTURE
__codexchange_start_local_proxy 8123 sample example-model {legacy_provider}
'''
    legacy = _run_bash(legacy_script)
    assert legacy.returncode == 0, legacy.stderr
    assert legacy_capture.read_text(encoding="utf-8").splitlines() == [
        "-m",
        "codexchange_proxy.cli",
        "start",
        "standard",
        "--port",
        "8123",
        "--state-dir",
        str(state_dir),
        "--pid-file",
        str(state_dir / "profile-sample-proxy-8123.pid"),
        "--log-file",
        str(log_dir / "codex-profile-sample-proxy-8123.log"),
        "--owner-profile",
        "sample",
    ]

    explicit_capture = tmp_path / "explicit.txt"
    explicit_script = f'''
source {WRAPPER!s}
__codexchange_proxy_models_ok() {{ return 0; }}
__codexchange_proxy_runtime_identity_matches() {{ return 0; }}
COX_INSTALL_DIR={install_dir!s}
COX_LOG_DIR={log_dir!s}
COX_STATE_DIR={state_dir!s}
COX_CAPTURE={explicit_capture!s}
export COX_CAPTURE
__codexchange_start_local_proxy 8123 sample example-model {legacy_provider} example_provider provider_owned {pricing!s}
'''
    explicit = _run_bash(explicit_script)
    assert explicit.returncode == 0, explicit.stderr
    assert explicit_capture.read_text(encoding="utf-8").splitlines() == [
        "-m",
        "codexchange_proxy.cli",
        "start",
        "standard",
        "--port",
        "8123",
        "--state-dir",
        str(state_dir),
        "--pid-file",
        str(state_dir / "profile-sample-proxy-8123.pid"),
        "--log-file",
        str(log_dir / "codex-profile-sample-proxy-8123.log"),
        "--owner-profile",
        "sample",
        "--pricing-provider-id",
        "example_provider",
        "--pricing-mode",
        "provider_owned",
        "--pricing-provider-path",
        str(pricing),
    ]


def test_wrapper_consumption_has_no_pricing_environment_activation() -> None:
    text = WRAPPER.read_text(encoding="utf-8")
    function_body = text[
        text.index("__codexchange_start_local_proxy() (") :
        text.index("__codexchange_profile_runtime_autostart() (")
    ]
    assert '"$python_bin" -m codexchange_proxy.cli "${start_args[@]}"' in function_body
    assert "codexchange_proxy.app:app" not in function_body
    assert "codexchange_proxy.runtime_app" not in function_body
    assert "COX_PRICING_PROVIDER_ID" not in text
    assert "COX_PRICING_PROVIDER_OWNED" not in text
    assert "COX_PRICING_MODE" not in text
    assert "COX_PRICING_PROVIDER_PATH" not in text
    assert "COX_PRICING_PATH" not in text
    assert "--cache-path" not in text
