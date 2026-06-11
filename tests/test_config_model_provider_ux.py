import importlib
import json
import subprocess
import sys
from pathlib import Path

cli = importlib.import_module("codexchange_proxy.cli")
ROOT = Path(__file__).resolve().parents[1]

def _codex_profile_text(config_path: Path, profile: str = "cox") -> str:
    path = config_path.parent / f"{profile}.config.toml"
    return path.read_text(encoding="utf-8") if path.exists() else ""



def _patch_post_config(monkeypatch):
    monkeypatch.setattr(cli, "_post_config_apply", lambda: {"status": "ok", "message": "all updates applied"})


def test_set_model_can_configure_provider_key_and_model(tmp_path, monkeypatch, capsys):
    _patch_post_config(monkeypatch)
    env_file = tmp_path / "env"
    codex_config = tmp_path / "config.toml"
    codex_config.write_text("[profiles.cox]\nmodel = \"deepseek-v4-pro\"\n", encoding="utf-8")

    rc = cli.main([
        "config",
        "set-model",
        "moonshot-v1-8k",
        "--provider",
        "kimi",
        "--value",
        "sk-kimi-test-123456",
        "--skip-validation",
        "--env-file",
        str(env_file),
        "--codex-config",
        str(codex_config),
    ])

    assert rc == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "ok"
    assert result["model_provider"] == "kimi"
    assert result["model"] == "moonshot-v1-8k"
    assert result["validation"]["status"] == "skipped"
    assert result["preferred_command"] == "cox config set-model moonshot-v1-8k --provider kimi"
    values = cli._read_env_exports(env_file)
    assert values["COX_MODEL_API_KEY"] == "sk-kimi-test-123456"
    assert values["COX_MODEL_PROVIDER"] == "kimi"
    assert values["COX_MODEL"] == "moonshot-v1-8k"
    assert 'model = "moonshot-v1-8k"' in _codex_profile_text(codex_config)
    assert "[profiles.cox]" not in codex_config.read_text(encoding="utf-8")


def test_set_api_key_remains_compatibility_alias(tmp_path, monkeypatch, capsys):
    _patch_post_config(monkeypatch)
    env_file = tmp_path / "env"

    rc = cli.main([
        "config",
        "set-api-key",
        "--provider",
        "zai",
        "--value",
        "sk-zai-test-123456",
        "--skip-validation",
        "--env-file",
        str(env_file),
    ])

    assert rc == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "ok"
    assert result["model_provider"] == "zai"
    assert result["deprecated_command"] == "set-api-key"
    assert "compatibility alias" in result["compatibility_note"]
    assert result["preferred_command"].startswith("cox config set-model")
    values = cli._read_env_exports(env_file)
    assert values["COX_MODEL_API_KEY"] == "sk-zai-test-123456"
    assert values["COX_MODEL_PROVIDER"] == "zai"


def test_set_model_model_only_flow_remains_supported(tmp_path, monkeypatch, capsys):
    _patch_post_config(monkeypatch)
    env_file = tmp_path / "env"
    codex_config = tmp_path / "config.toml"
    codex_config.write_text("[profiles.cox]\nmodel = \"deepseek-v4-pro\"\n", encoding="utf-8")

    rc = cli.main([
        "config",
        "set-model",
        "deepseek-v4-flash",
        "--env-file",
        str(env_file),
        "--codex-config",
        str(codex_config),
    ])

    assert rc == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "ok"
    assert result["model"] == "deepseek-v4-flash"
    values = cli._read_env_exports(env_file)
    assert "COX_MODEL_API_KEY" not in values
    assert values["COX_MODEL"] == "deepseek-v4-flash"


def test_set_model_help_is_provider_setup_entrypoint():
    result = subprocess.run(
        [sys.executable, "-m", "codexchange_proxy.cli", "config", "set-model", "--help"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    assert "--provider" in result.stdout
    assert "--value" in result.stdout
    assert "model API provider" in result.stdout
