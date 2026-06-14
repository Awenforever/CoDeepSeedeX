from __future__ import annotations

import importlib
import inspect
import json
import zipfile

from codexchange_proxy.providers import get_provider_adapter

app_module = importlib.import_module("codexchange_proxy.app")
cli_module = importlib.import_module("codexchange_proxy.cli")


def test_deepseek_provider_owns_tokenizer_metadata() -> None:
    adapter = get_provider_adapter("deepseek")
    metadata = adapter.tokenizer_resource_metadata()
    assert adapter.capabilities.tokenizer is True
    assert metadata["provider"] == "deepseek"
    assert metadata["tokenizer_kind"] == "deepseek_official_current"
    assert metadata["legacy_tokenizer_kind"] == "deepseek_v3"
    assert "COX_DEEPSEEK_TOKENIZER_JSON" in metadata["env_names"]
    assert metadata["billing_authoritative"] is False


def test_app_tokenizer_wrappers_delegate_to_provider_adapter() -> None:
    kind_source = inspect.getsource(app_module._profile_tokenizer_kind_for_model)
    candidates_source = inspect.getsource(app_module._profile_tokenizer_json_candidates)
    contract_source = inspect.getsource(app_module._profile_tokenizer_contract)

    assert "get_provider_adapter" in kind_source
    assert "profile_tokenizer_kind_for_model" in kind_source
    assert "tokenizer_json_candidates" in candidates_source
    assert "profile_tokenizer_contract" in contract_source

    assert app_module._profile_tokenizer_kind_for_model("deepseek-v4-flash", "deepseek") == "deepseek_official_current"
    assert app_module._profile_tokenizer_kind_for_model("qwen-plus", "qwen") is None


def test_cli_tokenizer_wrappers_delegate_to_provider_adapter(tmp_path) -> None:
    kind_source = inspect.getsource(cli_module._tokenizer_provider_kind)
    status_source = inspect.getsource(cli_module._tokenizer_resource_status)
    sync_source = inspect.getsource(cli_module._sync_deepseek_tokenizer_resource)

    assert "get_provider_adapter" in kind_source
    assert "_deepseek_tokenizer_resource_metadata" in status_source
    assert "_deepseek_tokenizer_resource_metadata" in sync_source

    unsupported = cli_module._tokenizer_resource_status("qwen", resource_root=str(tmp_path))
    assert unsupported["status"] == "unsupported"
    assert unsupported["provider_tokenizer"]["tokenizer_kind"] == "deepseek_official_current"

    status = cli_module._tokenizer_resource_status("deepseek", resource_root=str(tmp_path))
    assert status["status"] == "ok"
    assert status["tokenizer_kind"] == "deepseek_official_current"
    assert status["provider_tokenizer"]["provider"] == "deepseek"


def test_deepseek_tokenizer_sync_manifest_records_provider_metadata(tmp_path) -> None:
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    zip_path = source_dir / "tokenizer.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("deepseek_v3_tokenizer/tokenizer.json", "{}")
        archive.writestr("deepseek_v3_tokenizer/tokenizer_config.json", "{}")

    expected_sha = cli_module._sha256_path(zip_path)
    result = cli_module._sync_deepseek_tokenizer_resource(
        source_url=str(zip_path),
        expected_sha256=expected_sha,
        resource_root=str(tmp_path / "resources"),
        force=True,
    )

    assert result["status"] == "ok"
    assert result["tokenizer_kind"] == "deepseek_official_current"
    assert result["manifest"]["provider_tokenizer"]["tokenizer_kind"] == "deepseek_official_current"

    manifest_path = tmp_path / "resources" / "deepseek_official_current" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["provider_tokenizer"]["provider"] == "deepseek"
