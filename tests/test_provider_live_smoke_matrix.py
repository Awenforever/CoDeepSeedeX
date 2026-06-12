from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "provider-live-smoke-matrix.py"


def load_module():
    spec = importlib.util.spec_from_file_location("provider_live_smoke_matrix", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_smoke_matrix_skips_without_api_key(monkeypatch) -> None:
    module = load_module()
    monkeypatch.delenv("COX_LIVE_DS_KEY", raising=False)
    monkeypatch.delenv("COX_MODEL_API_KEY", raising=False)

    result = module.run_provider("deepseek", include_chat=True, timeout_seconds=0.01, insecure_tls=False)

    assert result["provider"] == "deepseek"
    assert result["configured"] is False
    assert result["validation"]["reason"] == "no_api_key"
    assert result["chat"]["reason"] == "no_api_key"


def test_smoke_matrix_uses_adapter_validation_metadata_without_network(monkeypatch) -> None:
    module = load_module()
    calls = []

    def fake_request_json(**kwargs):
        calls.append(kwargs)
        return {
            "ok": True,
            "status_code": 200,
            "elapsed_ms": 1,
            "body_kind": "dict",
            "top_level_keys": ["ok"],
            "error": "",
        }

    monkeypatch.setenv("COX_LIVE_DS_KEY", "secret")
    monkeypatch.setattr(module, "_request_json", fake_request_json)

    result = module.run_provider("deepseek", include_chat=False, timeout_seconds=1, insecure_tls=False)

    assert result["adapter_provider_id"] == "deepseek"
    assert result["validation_method"] == "account_balance_probe"
    assert result["validation_path"] == "/user/balance"
    assert result["validation"]["ok"] is True
    assert calls[0]["method"] == "GET"
    assert calls[0]["url"].endswith("/user/balance")


def test_smoke_matrix_runs_openai_compatible_chat_with_provider_specific_key(monkeypatch) -> None:
    module = load_module()
    calls = []

    def fake_request_json(**kwargs):
        calls.append(kwargs)
        return {
            "ok": True,
            "status_code": 200,
            "elapsed_ms": 1,
            "body_kind": "dict",
            "top_level_keys": ["id"],
            "error": "",
        }

    monkeypatch.setenv("COX_LIVE_KIMI_API_KEY", "secret")
    monkeypatch.setattr(module, "_request_json", fake_request_json)

    result = module.run_provider("kimi", include_chat=True, timeout_seconds=1, insecure_tls=False)

    assert result["adapter_provider_id"] == "openai_compatible"
    assert result["validation_path"] == "/models"
    assert result["validation"]["ok"] is True
    assert result["chat"]["ok"] is True
    assert calls[0]["url"].endswith("/models")
    assert calls[1]["url"].endswith("/chat/completions")
    assert calls[1]["payload"]["messages"][0]["content"] == "Reply exactly: ok"


def test_smoke_matrix_summary_counts_skips_and_successes() -> None:
    module = load_module()
    summary = module.build_summary(
        [
            {"validation": {"ok": True}, "chat": {"ok": True}},
            {"validation": {"skipped": True}, "chat": {"skipped": True}},
            {"validation": {"ok": False}, "chat": {"ok": False}},
        ]
    )

    assert summary == {
        "providers_total": 3,
        "validation_ok": 1,
        "validation_skipped": 1,
        "validation_failed": 1,
        "chat_ok": 1,
        "chat_skipped": 1,
        "chat_failed": 1,
    }

def test_smoke_matrix_allow_provider_failures_returns_success(monkeypatch, tmp_path) -> None:
    module = load_module()

    def fake_run_provider(provider, *, include_chat, timeout_seconds, insecure_tls):
        return {
            "provider": provider,
            "validation": {"ok": False},
            "chat": {"ok": False},
        }

    output = tmp_path / "result.json"
    monkeypatch.setattr(module, "run_provider", fake_run_provider)

    assert module.main(["--providers", "kimi", "--chat", "--output", str(output), "--allow-provider-failures"]) == 0
    assert output.exists()


def test_smoke_matrix_provider_failures_return_nonzero_by_default(monkeypatch, tmp_path) -> None:
    module = load_module()

    def fake_run_provider(provider, *, include_chat, timeout_seconds, insecure_tls):
        return {
            "provider": provider,
            "validation": {"ok": False},
            "chat": {"ok": False},
        }

    output = tmp_path / "result.json"
    monkeypatch.setattr(module, "run_provider", fake_run_provider)

    assert module.main(["--providers", "kimi", "--chat", "--output", str(output)]) == 1
    assert output.exists()
