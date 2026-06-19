from __future__ import annotations

import importlib.util
import os
import stat
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COX_CONFIG = ROOT / "scripts" / "cox-config"
ENV_MODULE = ROOT / "codexchange_proxy" / "env_file.py"


def _load_env_module():
    spec = importlib.util.spec_from_file_location("p101_env_file", ENV_MODULE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def _run_cox_config(args: list[str], tmp_path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(COX_CONFIG), *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={
            **os.environ,
            "COX_PROJECT": str(ROOT),
            "COX_PYTHON": sys.executable,
            "COX_ENV_FILE": str(tmp_path / "env"),
            "CODEX_CONFIG_FILE": str(tmp_path / "codex" / "config.toml"),
            "COX_CONFIG_RESTART_THINKING": "0",
            "PYTHONPATH": str(ROOT),
        },
        check=False,
        timeout=20,
    )


def test_p101_cox_config_no_longer_calls_removed_thinking_shortcuts() -> None:
    text = COX_CONFIG.read_text(encoding="utf-8")
    assert "cox-start-thinking" not in text
    assert "cox-stop-thinking" not in text
    assert "restarting DeepSeek thinking proxy" not in text
    assert "DEEPSEEK_(PROXY_MODEL|REASONING_EFFORT)" not in text
    assert "cox config set-model <model> --provider <provider>" in text
    assert "_post_config_apply" in text


def test_p101_legacy_set_model_remains_inert_and_provider_neutral(tmp_path: Path) -> None:
    marker = tmp_path / "executed.txt"
    model = f'p101-model"; printf executed > {marker}; #'
    completed = _run_cox_config(["set-model", model], tmp_path)

    assert completed.returncode == 0, completed.stderr
    assert "model set to" in completed.stdout
    assert "runtime refresh skipped" in completed.stdout
    assert "DeepSeek thinking" not in completed.stdout + completed.stderr
    assert not marker.exists()

    env_file = tmp_path / "env"
    values = _load_env_module().read_env_exports(env_file)
    assert values["COX_MODEL"] == model
    assert values["COX_MODEL_PROVIDER"] == "deepseek"
    assert _mode(env_file) == 0o600
    assert _mode(tmp_path / ".env.lock") == 0o600


def test_p101_show_reports_cox_env_without_refreshing_runtime(tmp_path: Path) -> None:
    first = _run_cox_config(["set", "model", "deepseek-v4-flash", "effort", "max"], tmp_path)
    assert first.returncode == 0, first.stderr

    shown = _run_cox_config(["show"], tmp_path)
    assert shown.returncode == 0, shown.stderr
    assert "ENV_FILE=" in shown.stdout
    assert "COX_MODEL" in shown.stdout
    assert "COX_REASONING_EFFORT" in shown.stdout
    assert "restarting" not in shown.stdout + shown.stderr
    assert "DeepSeek thinking" not in shown.stdout + shown.stderr
