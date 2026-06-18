from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "scripts" / "install.sh"


def _function_text() -> str:
    text = INSTALLER.read_text(encoding="utf-8")
    start = text.index("custom_provider_registry_transaction() {")
    end = text.index("\nprompt_custom_provider_name_field() {", start)
    return text[start:end]


def _write_registry(path: Path, *, api_key: str) -> dict[str, str]:
    marker = path.parent / "registry-value-command-executed"
    values = {
        "display_name": f"Alpha Provider $(touch {marker})",
        "base_url": "https://alpha.invalid/v1?left=a=b&quoted='yes'",
        "active_model": "alpha model\nline two",
        "api_key": api_key,
    }
    payload = {
        "version": 1,
        "active_provider": "other-provider",
        "providers": {
            "alpha-provider": {
                "id": "alpha-provider",
                "type": "custom_openai_compatible",
                **values,
                "models": [values["active_model"]],
            }
        },
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    path.chmod(0o600)
    return values


def _run_bash(script: str, cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-c", script, "_", *args],
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        check=False,
    )


def test_p92_registry_loader_uses_only_secure_inert_data_channel() -> None:
    function = _function_text()

    assert 'assign_file="/tmp/codexchange-custom-provider-registry-assign-$$.sh"' not in function
    assert '. "$assign_file"' not in function
    assert "shlex.quote" not in function
    assert 'mktemp "${TMPDIR:-/tmp}/codexchange-custom-provider-registry-data.XXXXXX"' in function
    assert "umask 077" in function
    assert "sys.stdout.buffer.write(payload)" in function
    assert "while IFS= read -r -d '' key" in function
    assert 'case "$key" in' in function
    assert 'rm -f -- "$data_file"' in function


def test_p92_registry_values_round_trip_without_execution_and_old_predictable_file_is_ignored(tmp_path: Path) -> None:
    registry = tmp_path / "model-providers.json"
    expected = _write_registry(registry, api_key="dummy key = 'quoted'\nline two")
    output = tmp_path / "observed.json"
    old_marker = tmp_path / "old-assignment-executed"
    value_marker = tmp_path / "registry-value-command-executed"
    temp_dir = tmp_path / "temp"
    temp_dir.mkdir()

    script = (
        "set -euo pipefail\n"
        f"PYTHON_BIN={shlex.quote(sys.executable)}\n"
        "MODEL_PROVIDER_REGISTRY_FILE=\"$1\"\n"
        "OUT=\"$2\"\n"
        "TMPDIR=\"$3\"\n"
        "export TMPDIR\n"
        "warn() { printf 'warning=%s\\n' \"$*\" >&2; }\n"
        "record_model_api_validation_summary() { :; }\n"
        + _function_text()
        + "\n"
        'old_assign="/tmp/codexchange-custom-provider-registry-assign-$$.sh"\n'
        'printf \'touch %q\\nPROMPTED_CUSTOM_PROVIDER_NAME=tampered\\n\' "$4" > "$old_assign"\n'
        'trap \'rm -f "$old_assign"\' EXIT\n'
        "PROMPTED_API_KEY=stale-value\n"
        "apply_custom_provider_from_registry use alpha-provider ''\n"
        f"{shlex.quote(sys.executable)} - \"$OUT\" "
        '"$PROMPTED_MODEL_PROVIDER" "$PROMPTED_CUSTOM_PROVIDER_NAME" '
        '"$PROMPTED_MODEL_BASE_URL" "$PROMPTED_MODEL_NAME" "$PROMPTED_API_KEY" <<\'PYOBSERVED\'\n'
        "import json, sys\n"
        "from pathlib import Path\n"
        "Path(sys.argv[1]).write_text(json.dumps({\n"
        "    'provider': sys.argv[2],\n"
        "    'display_name': sys.argv[3],\n"
        "    'base_url': sys.argv[4],\n"
        "    'active_model': sys.argv[5],\n"
        "    'api_key': sys.argv[6],\n"
        "}, ensure_ascii=False), encoding='utf-8')\n"
        "PYOBSERVED\n"
    )
    completed = _run_bash(
        script,
        tmp_path,
        str(registry),
        str(output),
        str(temp_dir),
        str(old_marker),
    )

    assert completed.returncode == 0, completed.stderr
    observed = json.loads(output.read_text(encoding="utf-8"))
    assert observed == {"provider": "custom", **expected}
    assert not old_marker.exists()
    assert not value_marker.exists()
    assert list(temp_dir.iterdir()) == []
    registry_after = json.loads(registry.read_text(encoding="utf-8"))
    assert registry_after["active_provider"] == "alpha-provider"


def test_p92_empty_registry_api_key_clears_previous_prompted_key(tmp_path: Path) -> None:
    registry = tmp_path / "model-providers.json"
    _write_registry(registry, api_key="")
    output = tmp_path / "api-key.txt"
    temp_dir = tmp_path / "temp"
    temp_dir.mkdir()
    script = (
        "set -euo pipefail\n"
        f"PYTHON_BIN={shlex.quote(sys.executable)}\n"
        "MODEL_PROVIDER_REGISTRY_FILE=\"$1\"\n"
        "OUT=\"$2\"\n"
        "TMPDIR=\"$3\"\n"
        "export TMPDIR\n"
        "warn() { :; }\n"
        "record_model_api_validation_summary() { :; }\n"
        + _function_text()
        + "\n"
        "PROMPTED_API_KEY=stale-key\n"
        "apply_custom_provider_from_registry use alpha-provider ''\n"
        "printf '%s' \"$PROMPTED_API_KEY\" > \"$OUT\"\n"
    )
    completed = _run_bash(script, tmp_path, str(registry), str(output), str(temp_dir))

    assert completed.returncode == 0, completed.stderr
    assert output.read_text(encoding="utf-8") == ""
    assert list(temp_dir.iterdir()) == []


def test_p92_truncated_or_unknown_data_fails_closed_without_partial_assignment(tmp_path: Path) -> None:
    fake_python = tmp_path / "fake-python"
    fake_python.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "cat >/dev/null\n"
        "printf 'PROMPTED_MODEL_PROVIDER\\0custom\\0UNKNOWN_FIELD\\0tampered\\0'\n",
        encoding="utf-8",
    )
    fake_python.chmod(0o700)
    registry = tmp_path / "model-providers.json"
    registry.write_text("{}\n", encoding="utf-8")
    output = tmp_path / "observed.json"
    temp_dir = tmp_path / "temp"
    temp_dir.mkdir()
    script = (
        "set -euo pipefail\n"
        "PYTHON_BIN=\"$1\"\n"
        "MODEL_PROVIDER_REGISTRY_FILE=\"$2\"\n"
        "OUT=\"$3\"\n"
        "TMPDIR=\"$4\"\n"
        "export TMPDIR\n"
        "warn() { :; }\n"
        "record_model_api_validation_summary() { :; }\n"
        + _function_text()
        + "\n"
        "PROMPTED_MODEL_PROVIDER=sentinel-provider\n"
        "PROMPTED_CUSTOM_PROVIDER_NAME=sentinel-name\n"
        "PROMPTED_MODEL_BASE_URL=sentinel-url\n"
        "PROMPTED_MODEL_NAME=sentinel-model\n"
        "PROMPTED_API_KEY=sentinel-key\n"
        "if apply_custom_provider_from_registry use alpha-provider ''; then\n"
        "  exit 99\n"
        "else\n"
        "  rc=$?\n"
        "fi\n"
        f"{shlex.quote(sys.executable)} - \"$OUT\" \"$rc\" "
        '"$PROMPTED_MODEL_PROVIDER" "$PROMPTED_CUSTOM_PROVIDER_NAME" '
        '"$PROMPTED_MODEL_BASE_URL" "$PROMPTED_MODEL_NAME" "$PROMPTED_API_KEY" <<\'PYOBSERVED\'\n'
        "import json, sys\n"
        "from pathlib import Path\n"
        "Path(sys.argv[1]).write_text(json.dumps(sys.argv[2:]), encoding='utf-8')\n"
        "PYOBSERVED\n"
    )
    completed = _run_bash(
        script,
        tmp_path,
        str(fake_python),
        str(registry),
        str(output),
        str(temp_dir),
    )

    assert completed.returncode == 0, completed.stderr
    observed = json.loads(output.read_text(encoding="utf-8"))
    assert observed == [
        "70",
        "sentinel-provider",
        "sentinel-name",
        "sentinel-url",
        "sentinel-model",
        "sentinel-key",
    ]
    assert list(temp_dir.iterdir()) == []
