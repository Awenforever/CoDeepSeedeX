from __future__ import annotations

from pathlib import Path

from codexchange_proxy import cli as cli_module


def test_cli_tokenizer_resource_metadata_dispatches_to_provider_adapter(monkeypatch):
    calls: list[str] = []

    class Adapter:
        def tokenizer_resource_metadata(self):
            return {
                "provider": "deepseek",
                "tokenizer": True,
                "tokenizer_kind": "custom_kind",
                "source_url": "https://example.invalid/tokenizer.zip",
                "source_zip_sha256": "abc123",
                "source_zip_entries": {"tokenizer_json": "x/tokenizer.json"},
            }

    def fake_get_provider_adapter(provider: str):
        calls.append(provider)
        return Adapter()

    monkeypatch.setattr(cli_module, "get_provider_adapter", fake_get_provider_adapter)

    metadata = cli_module._tokenizer_resource_metadata("deepseek")
    assert calls == ["deepseek"]
    assert metadata["provider"] == "deepseek"
    assert metadata["tokenizer_kind"] == "custom_kind"
    assert metadata["source_zip_sha256"] == "abc123"


def test_cli_legacy_deepseek_tokenizer_metadata_delegates_to_provider_wrapper(monkeypatch):
    calls: list[str] = []

    def fake_metadata(provider: str = "deepseek"):
        calls.append(provider)
        return {"provider": provider, "tokenizer": True, "tokenizer_kind": "kind"}

    monkeypatch.setattr(cli_module, "_tokenizer_resource_metadata", fake_metadata)

    assert cli_module._deepseek_tokenizer_resource_metadata()["provider"] == "deepseek"
    assert calls == ["deepseek"]


def test_cli_tokenizer_status_uses_provider_metadata_wrapper(monkeypatch, tmp_path: Path):
    calls: list[str] = []

    def fake_metadata(provider: str = "deepseek"):
        calls.append(provider)
        return {
            "provider": provider,
            "tokenizer": True,
            "tokenizer_kind": "missing_kind",
            "legacy_tokenizer_kind": "legacy_kind",
            "env_names": ["COX_PROFILE_TOKENIZER_JSON", "COX_DEEPSEEK_TOKENIZER_JSON"],
            "sync_action": f"run cox tokenizer sync {provider} --json",
        }

    monkeypatch.setattr(cli_module, "_tokenizer_resource_metadata", fake_metadata)
    monkeypatch.setattr(cli_module, "_tokenizer_provider_kind", lambda provider: "missing_kind")

    status = cli_module._tokenizer_resource_status("deepseek", resource_root=str(tmp_path))
    assert calls == ["deepseek"]
    assert status["provider"] == "deepseek"
    assert status["tokenizer_kind"] == "missing_kind"
    assert status["available"] is False
    assert status["tokenizer_json"]["exists"] is False
    assert "cox tokenizer sync deepseek" in str(status)


def test_cli_provider_tokenizer_sync_refuses_unsupported_provider_without_network(tmp_path: Path):
    payload = cli_module._sync_provider_tokenizer_resource(
        "unknown-provider",
        source_url="https://example.invalid/tokenizer.zip",
        expected_sha256="bad",
        resource_root=str(tmp_path),
        timeout=0.01,
        force=True,
    )
    assert payload["status"] == "error"
    assert payload["provider"] == "unknown-provider"
    assert payload["reason"] == "profile_tokenizer_resource_unsupported"
    assert payload["supported_providers"] == ["deepseek"]


def test_cli_legacy_deepseek_tokenizer_sync_delegates_to_provider_wrapper(monkeypatch, tmp_path: Path):
    calls: list[tuple[str, dict]] = []

    def fake_sync(provider: str = "deepseek", **kwargs):
        calls.append((provider, kwargs))
        return {"status": "ok", "provider": provider, "kwargs": kwargs}

    monkeypatch.setattr(cli_module, "_sync_provider_tokenizer_resource", fake_sync)

    payload = cli_module._sync_deepseek_tokenizer_resource(
        source_url="file:///tmp/deepseek-tokenizer.zip",
        expected_sha256="sha",
        resource_root=str(tmp_path),
        timeout=1.25,
        force=True,
    )
    assert payload["status"] == "ok"
    assert calls[0][0] == "deepseek"
    assert calls[0][1]["source_url"] == "file:///tmp/deepseek-tokenizer.zip"
    assert calls[0][1]["expected_sha256"] == "sha"
    assert calls[0][1]["resource_root"] == str(tmp_path)
    assert calls[0][1]["timeout"] == 1.25
    assert calls[0][1]["force"] is True
