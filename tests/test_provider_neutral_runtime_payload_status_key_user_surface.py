from pathlib import Path


def test_runtime_payload_status_keys_do_not_expose_deepseek_payload_boundary():
    app_source = Path("codexchange_proxy/app.py").read_text(encoding="utf-8")
    cli_source = Path("codexchange_proxy/cli.py").read_text(encoding="utf-8")

    assert "last_provider_payload" in app_source
    assert "last_provider_payload_size" in app_source
    assert "last_provider_payload_size" in cli_source

    forbidden_status_keys = (
        '"last_deepseek_payload":',
        '"last_deepseek_payload_mtime":',
        '"last_deepseek_payload_size":',
    )
    combined = app_source + "\n" + cli_source
    for key in forbidden_status_keys:
        assert key not in combined


def test_legacy_debug_payload_filename_remains_internal_file_contract():
    app_source = Path("codexchange_proxy/app.py").read_text(encoding="utf-8")
    assert "last_deepseek_payload.json" in app_source
