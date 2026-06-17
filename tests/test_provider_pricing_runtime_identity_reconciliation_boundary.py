from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

from codexchange_proxy.app import create_app
from codexchange_proxy.runtime_app import create_runtime_app


ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "scripts" / "codex-wrapper.bash"


def _run_bash(
    script: str,
    *,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
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


def _profile_home(
    tmp_path: Path,
    *,
    pricing_path: Path | None,
) -> Path:
    codex_home = tmp_path / "codex"
    codex_home.mkdir()
    body = (
        'model = "example-model"\n'
        'model_provider = "sample-proxy"\n'
    )
    if pricing_path is not None:
        body += (
            'pricing_provider_id = "Example-Provider"\n'
            'pricing_provider_owned = true\n'
            'pricing_mode = "provider-owned"\n'
            f'pricing_provider_path = "{pricing_path}"\n'
        )
    (codex_home / "sample.config.toml").write_text(
        body,
        encoding="utf-8",
    )
    (codex_home / "config.toml").write_text(
        "[model_providers.sample-proxy]\n"
        'base_url = "http://127.0.0.1:8123/v1"\n',
        encoding="utf-8",
    )
    return codex_home


def _fake_curl_bin(
    tmp_path: Path,
) -> tuple[Path, Path]:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    curl_log = tmp_path / "curl.log"
    fake_curl = fake_bin / "curl"
    fake_curl.write_text(
        """#!/usr/bin/env bash
set -u
url="${!#}"
printf '%s\n' "$url" >> "$COX_TEST_CURL_LOG"
case "$url" in
  */v1/proxy/status)
    printf '%s\n' "$COX_TEST_RUNTIME_STATUS"
    ;;
  *)
    printf '%s\n' '{}'
    ;;
esac
""",
        encoding="utf-8",
    )
    fake_curl.chmod(0o755)
    return fake_bin, curl_log


def _explicit_identity(
    pricing: Path,
    *,
    provider_id: str = "example_provider",
) -> dict[str, object]:
    return {
        "status": "ok",
        "runtime_identity": {
            "contract": "provider_pricing_runtime_identity_v1",
            "source": "explicit_runtime_arguments",
            "pricing_provider_id": provider_id,
            "pricing_activate": True,
            "pricing_provider_owned": True,
            "pricing_mode": "provider_owned",
            "pricing_provider_path": str(pricing),
        },
    }


def test_explicit_runtime_status_exposes_normalized_non_secret_identity(
    tmp_path: Path,
) -> None:
    pricing = tmp_path / "pricing.json"
    pricing.write_text("{}\n", encoding="utf-8")
    application = create_runtime_app(
        pricing_provider_id="Example-Provider",
        pricing_activate=True,
        pricing_mode="provider-owned",
        pricing_provider_path=pricing,
    )
    with TestClient(application) as client:
        response = client.get("/v1/proxy/status")
    assert response.status_code == 200
    assert response.json()["runtime_identity"] == {
        "contract": "provider_pricing_runtime_identity_v1",
        "source": "explicit_runtime_arguments",
        "pricing_provider_id": "example_provider",
        "pricing_activate": True,
        "pricing_provider_owned": True,
        "pricing_mode": "provider_owned",
        "pricing_provider_path": str(pricing),
    }


def test_legacy_runtime_status_exposes_legacy_shared_identity() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/v1/proxy/status")
    assert response.status_code == 200
    assert response.json()["runtime_identity"] == {
        "contract": "provider_pricing_runtime_identity_v1",
        "source": "legacy_shared_app",
        "pricing_provider_id": None,
        "pricing_activate": False,
        "pricing_provider_owned": False,
        "pricing_mode": "legacy_shared",
        "pricing_provider_path": None,
    }


def test_matching_explicit_runtime_identity_allows_healthy_proxy_reuse(
    tmp_path: Path,
) -> None:
    pricing = tmp_path / "pricing.json"
    pricing.write_text("{}\n", encoding="utf-8")
    codex_home = _profile_home(
        tmp_path,
        pricing_path=pricing,
    )
    fake_bin, curl_log = _fake_curl_bin(tmp_path)
    start_capture = tmp_path / "start-called"
    script = f'''
source {WRAPPER!s}
__codexchange_proxy_models_ok() {{ return 0; }}
__codexchange_start_local_proxy() {{ touch {start_capture!s}; }}
CODEX_HOME={codex_home!s}
__codexchange_profile_runtime_autostart --profile sample
'''
    env = {
        "PATH": str(fake_bin) + os.pathsep + os.environ.get("PATH", ""),
        "COX_TEST_CURL_LOG": str(curl_log),
        "COX_TEST_RUNTIME_STATUS": json.dumps(_explicit_identity(pricing)),
    }
    result = _run_bash(script, env=env)
    assert result.returncode == 0, result.stderr
    assert not start_capture.exists()
    assert curl_log.read_text(encoding="utf-8").splitlines() == [
        "http://127.0.0.1:8123/v1/proxy/status",
    ]


def test_mismatched_explicit_runtime_identity_fails_closed_before_codex(
    tmp_path: Path,
) -> None:
    pricing = tmp_path / "pricing.json"
    pricing.write_text("{}\n", encoding="utf-8")
    codex_home = _profile_home(
        tmp_path,
        pricing_path=pricing,
    )
    fake_bin, curl_log = _fake_curl_bin(tmp_path)
    start_capture = tmp_path / "start-called"
    status = _explicit_identity(
        pricing,
        provider_id="different_provider",
    )
    script = f'''
source {WRAPPER!s}
__codexchange_proxy_models_ok() {{ return 0; }}
__codexchange_start_local_proxy() {{ touch {start_capture!s}; }}
CODEX_HOME={codex_home!s}
__codexchange_profile_runtime_autostart --profile sample
'''
    env = {
        "PATH": str(fake_bin) + os.pathsep + os.environ.get("PATH", ""),
        "COX_TEST_CURL_LOG": str(curl_log),
        "COX_TEST_RUNTIME_STATUS": json.dumps(status),
    }
    result = _run_bash(script, env=env)
    assert result.returncode == 70
    assert "runtime pricing identity does not match" in result.stderr
    assert "refusing to enter Codex" in result.stderr
    assert not start_capture.exists()


def test_missing_runtime_identity_fails_closed_for_explicit_profile(
    tmp_path: Path,
) -> None:
    pricing = tmp_path / "pricing.json"
    pricing.write_text("{}\n", encoding="utf-8")
    codex_home = _profile_home(
        tmp_path,
        pricing_path=pricing,
    )
    fake_bin, curl_log = _fake_curl_bin(tmp_path)
    script = f'''
source {WRAPPER!s}
__codexchange_proxy_models_ok() {{ return 0; }}
CODEX_HOME={codex_home!s}
__codexchange_profile_runtime_autostart --profile sample
'''
    env = {
        "PATH": str(fake_bin) + os.pathsep + os.environ.get("PATH", ""),
        "COX_TEST_CURL_LOG": str(curl_log),
        "COX_TEST_RUNTIME_STATUS": json.dumps({"status": "ok"}),
    }
    result = _run_bash(script, env=env)
    assert result.returncode == 70
    assert "runtime pricing identity does not match" in result.stderr


def test_legacy_profile_preserves_health_only_reuse_compatibility(
    tmp_path: Path,
) -> None:
    codex_home = _profile_home(
        tmp_path,
        pricing_path=None,
    )
    fake_bin, curl_log = _fake_curl_bin(tmp_path)
    script = f'''
source {WRAPPER!s}
__codexchange_proxy_models_ok() {{ return 0; }}
CODEX_HOME={codex_home!s}
__codexchange_profile_runtime_autostart --profile sample
'''
    env = {
        "PATH": str(fake_bin) + os.pathsep + os.environ.get("PATH", ""),
        "COX_TEST_CURL_LOG": str(curl_log),
        "COX_TEST_RUNTIME_STATUS": json.dumps({"status": "ok"}),
    }
    result = _run_bash(script, env=env)
    assert result.returncode == 0, result.stderr
    assert not curl_log.exists()


def test_wrapper_identity_contract_has_no_environment_activation_or_process_kill() -> None:
    text = WRAPPER.read_text(encoding="utf-8")
    assert "/v1/proxy/status" in text
    assert "provider_pricing_runtime_identity_v1" in text
    assert "COX_PRICING_PROVIDER_ID" not in text
    assert "COX_PRICING_PROVIDER_PATH" not in text
    assert "pkill" not in text
    assert "kill -9" not in text
