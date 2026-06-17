from __future__ import annotations

import json
from pathlib import Path

from codexchange_proxy import cli


PRICING_FIELDS = {
    "pricing_provider_id",
    "pricing_provider_owned",
    "pricing_mode",
    "pricing_provider_path",
}


def _write_profile(codex_config: Path, profile: str, text: str) -> Path:
    profile_path = codex_config.parent / f"{profile}.config.toml"
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_text(text, encoding="utf-8")
    return profile_path


def _read_json(capsys) -> dict[str, object]:
    return json.loads(capsys.readouterr().out)


def test_set_pricing_writes_complete_explicit_contract_without_activation(tmp_path: Path, capsys) -> None:
    codex_config = tmp_path / "config.toml"
    profile_path = _write_profile(
        codex_config,
        "sample",
        'model = "example-model"\nmodel_provider = "example-proxy"\n',
    )
    pricing_path = tmp_path / "pricing.json"
    pricing_path.write_text('{"models": {}}\n', encoding="utf-8")

    rc = cli.main([
        "profile",
        "set-pricing",
        "sample",
        "--provider-id",
        "Example-Provider",
        "--provider-path",
        str(pricing_path),
        "--codex-config",
        str(codex_config),
        "--json",
    ])

    payload = _read_json(capsys)
    assert rc == 0
    assert payload["status"] == "ok"
    assert payload["operation"] == "profile_pricing_set"
    assert payload["runtime_activation"] is False
    assert payload["runtime_restart"] is False
    assert payload["environment_activation"] is False
    assert payload["model_provider_inference"] is False
    assert payload["activation_boundary"] == "next_profile_autostart"

    values = cli._parse_simple_toml_key_values_from_text(profile_path.read_text(encoding="utf-8"))
    assert values["model"] == "example-model"
    assert values["model_provider"] == "example-proxy"
    assert values["pricing_provider_id"] == "example_provider"
    assert values["pricing_provider_owned"] == "true"
    assert values["pricing_mode"] == "provider_owned"
    assert values["pricing_provider_path"] == str(pricing_path)


def test_set_pricing_updates_all_fields_with_one_profile_write(tmp_path: Path, capsys, monkeypatch) -> None:
    codex_config = tmp_path / "config.toml"
    profile_path = _write_profile(
        codex_config,
        "sample",
        'model = "example-model"\nmodel_provider = "example-proxy"\n'
        'pricing_provider_id = "old"\npricing_provider_owned = true\n'
        'pricing_mode = "provider_owned"\npricing_provider_path = "/tmp/old.json"\n',
    )
    pricing_path = tmp_path / "new-pricing.json"
    pricing_path.write_text('{}\n', encoding="utf-8")

    calls: list[dict[str, object]] = []
    original = cli._write_codex_profile_values

    def tracked(config_path: Path, profile_name: str, values: dict[str, object]) -> Path:
        calls.append(dict(values))
        return original(config_path, profile_name, values)

    monkeypatch.setattr(cli, "_write_codex_profile_values", tracked)
    rc = cli.main([
        "profile", "set-pricing", "sample",
        "--provider-id", "new-provider",
        "--provider-path", str(pricing_path),
        "--codex-config", str(codex_config),
    ])
    payload = _read_json(capsys)

    assert rc == 0
    assert payload["changed"] is True
    assert len(calls) == 1
    values = cli._parse_simple_toml_key_values_from_text(profile_path.read_text(encoding="utf-8"))
    assert values["pricing_provider_id"] == "new_provider"
    assert values["pricing_provider_path"] == str(pricing_path)


def test_clear_pricing_removes_all_four_fields_and_preserves_profile(tmp_path: Path, capsys) -> None:
    codex_config = tmp_path / "config.toml"
    profile_path = _write_profile(
        codex_config,
        "sample",
        'model = "example-model"\nmodel_provider = "example-proxy"\n'
        'pricing_provider_id = "example"\npricing_provider_owned = true\n'
        'pricing_mode = "provider_owned"\npricing_provider_path = "/tmp/example.json"\n',
    )

    rc = cli.main([
        "profile", "clear-pricing", "sample",
        "--codex-config", str(codex_config),
        "--json",
    ])
    payload = _read_json(capsys)

    assert rc == 0
    assert payload["operation"] == "profile_pricing_clear"
    assert set(payload["cleared_fields"]) == PRICING_FIELDS
    assert payload["pricing"]["selected_mode"] == "legacy_shared"
    values = cli._parse_simple_toml_key_values_from_text(profile_path.read_text(encoding="utf-8"))
    assert values["model"] == "example-model"
    assert values["model_provider"] == "example-proxy"
    assert PRICING_FIELDS.isdisjoint(values)


def test_clear_pricing_repairs_partial_field_set_without_activation(tmp_path: Path, capsys) -> None:
    codex_config = tmp_path / "config.toml"
    profile_path = _write_profile(
        codex_config,
        "sample",
        'model = "example-model"\nmodel_provider = "example-proxy"\n'
        'pricing_provider_id = "partial"\n',
    )

    rc = cli.main([
        "profile", "clear-pricing", "sample",
        "--codex-config", str(codex_config),
    ])
    payload = _read_json(capsys)

    assert rc == 0
    assert payload["runtime_activation"] is False
    assert payload["pricing"]["candidate_requested"] is False
    values = cli._parse_simple_toml_key_values_from_text(profile_path.read_text(encoding="utf-8"))
    assert PRICING_FIELDS.isdisjoint(values)


def test_set_and_clear_dry_run_do_not_write(tmp_path: Path, capsys) -> None:
    codex_config = tmp_path / "config.toml"
    profile_path = _write_profile(
        codex_config,
        "sample",
        'model = "example-model"\nmodel_provider = "example-proxy"\n',
    )
    before = profile_path.read_bytes()
    pricing_path = tmp_path / "pricing.json"
    pricing_path.write_text('{}\n', encoding="utf-8")

    rc = cli.main([
        "profile", "set-pricing", "sample",
        "--provider-id", "example",
        "--provider-path", str(pricing_path),
        "--codex-config", str(codex_config),
        "--dry-run",
    ])
    set_payload = _read_json(capsys)
    assert rc == 0
    assert set_payload["dry_run"] is True
    assert profile_path.read_bytes() == before

    profile_path.write_text(
        before.decode("utf-8")
        + 'pricing_provider_id = "example"\npricing_provider_owned = true\n'
        + 'pricing_mode = "provider_owned"\n'
        + f'pricing_provider_path = "{pricing_path}"\n',
        encoding="utf-8",
    )
    before_clear = profile_path.read_bytes()
    rc = cli.main([
        "profile", "clear-pricing", "sample",
        "--codex-config", str(codex_config),
        "--dry-run",
    ])
    clear_payload = _read_json(capsys)
    assert rc == 0
    assert clear_payload["dry_run"] is True
    assert profile_path.read_bytes() == before_clear


def test_set_pricing_rejects_missing_profile_relative_or_missing_path(tmp_path: Path, capsys) -> None:
    codex_config = tmp_path / "config.toml"
    pricing_path = tmp_path / "pricing.json"
    pricing_path.write_text('{}\n', encoding="utf-8")

    rc = cli.main([
        "profile", "set-pricing", "missing",
        "--provider-id", "example",
        "--provider-path", str(pricing_path),
        "--codex-config", str(codex_config),
    ])
    payload = _read_json(capsys)
    assert rc == 2
    assert payload["error"] == "codex_profile_not_found"
    assert not (tmp_path / "missing.config.toml").exists()

    _write_profile(codex_config, "sample", 'model = "example"\nmodel_provider = "example-proxy"\n')
    rc = cli.main([
        "profile", "set-pricing", "sample",
        "--provider-id", "example",
        "--provider-path", "relative.json",
        "--codex-config", str(codex_config),
    ])
    payload = _read_json(capsys)
    assert rc == 2
    assert payload["error"] == "pricing_provider_path_must_be_absolute"

    rc = cli.main([
        "profile", "set-pricing", "sample",
        "--provider-id", "example",
        "--provider-path", str(tmp_path / "missing.json"),
        "--codex-config", str(codex_config),
    ])
    payload = _read_json(capsys)
    assert rc == 2
    assert payload["error"] == "pricing_provider_path_not_file"


def test_profile_status_exposes_pricing_candidate_contract(tmp_path: Path, capsys) -> None:
    codex_config = tmp_path / "config.toml"
    pricing_path = tmp_path / "pricing.json"
    pricing_path.write_text('{}\n', encoding="utf-8")
    _write_profile(
        codex_config,
        "sample",
        'model = "example"\nmodel_provider = "example-proxy"\n'
        'pricing_provider_id = "example"\npricing_provider_owned = true\n'
        'pricing_mode = "provider_owned"\n'
        f'pricing_provider_path = "{pricing_path}"\n',
    )

    rc = cli.main([
        "profile", "status", "sample",
        "--codex-config", str(codex_config),
        "--json",
    ])
    payload = _read_json(capsys)
    assert rc == 0
    assert payload["pricing"]["candidate_contract_valid"] is True
    assert payload["pricing"]["argument_mapping"] == {
        "pricing_provider_id": "example",
        "pricing_provider_owned": True,
        "pricing_mode": "provider_owned",
        "pricing_provider_path": str(pricing_path),
    }


def test_configuration_write_boundary_has_no_environment_or_legacy_path_activation() -> None:
    source = (Path(cli.__file__).resolve()).read_text(encoding="utf-8")
    for function_name in (
        "_set_profile_pricing_contract",
        "_clear_profile_pricing_contract",
    ):
        start = source.index(f"def {function_name}(")
        end = source.find("\ndef ", start + 1)
        body = source[start:] if end < 0 else source[start:end]
        assert "os.environ" not in body
        assert "os.getenv" not in body
        assert "COX_PRICING_PATH" not in body
        assert "COX_PRICING_PROVIDER" not in body
        assert "cache_path" not in body
        assert "model_provider" not in body
        assert "_post_config_apply" not in body
        assert "_start_proxy" not in body
