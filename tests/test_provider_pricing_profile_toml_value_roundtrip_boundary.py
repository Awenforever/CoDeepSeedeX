from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
from pathlib import Path

import pytest

from codexchange_proxy import cli


ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "scripts" / "codex-wrapper.bash"


def _call_cli(argv: list[str]) -> tuple[int, dict[str, object]]:
    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        rc = int(cli.main(argv))
    payload = json.loads(stdout.getvalue())
    assert isinstance(payload, dict)
    return rc, payload


def _prepare_profile(tmp_path: Path) -> tuple[Path, Path]:
    codex_config = tmp_path / "config.toml"
    profile_path = tmp_path / "sample.config.toml"
    codex_config.write_text(
        "[model_providers.sample-proxy]\n"
        'base_url = "http://127.0.0.1:8123/v1"\n',
        encoding="utf-8",
    )
    profile_path.write_text(
        'model = "example-model"\n'
        'model_provider = "sample-proxy"\n',
        encoding="utf-8",
    )
    return codex_config, profile_path


def _capture_autostart_arguments(tmp_path: Path) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    capture = tmp_path / "capture.bin"
    script = tmp_path / "capture.sh"
    script.write_text(
        "\n".join(
            [
                "#!/usr/bin/env bash",
                "set -u",
                f"source {WRAPPER}",
                "__codexchange_proxy_models_ok() { return 1; }",
                "__codexchange_port_open() { return 1; }",
                '__codexchange_start_local_proxy() { printf \'%s\\0\' "$@" > "$CAPTURE"; }',
                "__codexchange_profile_runtime_autostart --profile sample",
                "",
            ]
        ),
        encoding="utf-8",
    )
    script.chmod(0o755)

    env = dict(os.environ)
    env["CODEX_HOME"] = str(tmp_path)
    env["CAPTURE"] = str(capture)
    result = subprocess.run(
        ["bash", str(script)],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    arguments: list[str] = []
    if capture.exists():
        raw = capture.read_bytes()
        parts = raw.split(b"\0")
        if parts and parts[-1] == b"":
            parts.pop()
        arguments = [
            part.decode("utf-8")
            for part in parts
        ]
    return result, arguments


@pytest.mark.parametrize(
    "pricing_filename",
    [
        "pricing.json",
        "pricing file.json",
        "pricing#file.json",
        "pricing\\file.json",
        'pricing"file.json',
    ],
)
def test_cli_written_provider_path_roundtrips_into_wrapper_autostart(
    tmp_path: Path,
    pricing_filename: str,
) -> None:
    codex_config, profile_path = _prepare_profile(tmp_path)
    pricing_path = tmp_path / pricing_filename
    pricing_path.write_text("{}\n", encoding="utf-8")

    rc, payload = _call_cli([
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

    assert rc == 0
    assert payload["status"] == "ok"
    assert payload["runtime_activation"] is False

    values = cli._parse_simple_toml_key_values_from_text(
        profile_path.read_text(encoding="utf-8")
    )
    assert values["pricing_provider_path"] == str(pricing_path)

    result, arguments = _capture_autostart_arguments(tmp_path)
    assert result.returncode == 0, result.stderr
    assert arguments == [
        "8123",
        "sample",
        "example-model",
        "sample-proxy",
        "example_provider",
        "provider_owned",
        str(pricing_path),
        str(profile_path),
    ]


def test_clear_pricing_returns_to_exact_legacy_autostart_arguments(
    tmp_path: Path,
) -> None:
    codex_config, profile_path = _prepare_profile(tmp_path)
    pricing_path = tmp_path / 'pricing"\\file.json'
    pricing_path.write_text("{}\n", encoding="utf-8")

    set_rc, _ = _call_cli([
        "profile",
        "set-pricing",
        "sample",
        "--provider-id",
        "example",
        "--provider-path",
        str(pricing_path),
        "--codex-config",
        str(codex_config),
        "--json",
    ])
    clear_rc, clear_payload = _call_cli([
        "profile",
        "clear-pricing",
        "sample",
        "--codex-config",
        str(codex_config),
        "--json",
    ])

    assert set_rc == 0
    assert clear_rc == 0
    assert clear_payload["changed"] is True

    profile_text = profile_path.read_text(encoding="utf-8")
    for field in (
        "pricing_provider_id",
        "pricing_provider_owned",
        "pricing_mode",
        "pricing_provider_path",
    ):
        assert field not in profile_text

    result, arguments = _capture_autostart_arguments(tmp_path)
    assert result.returncode == 0, result.stderr
    assert arguments == [
        "8123",
        "sample",
        "example-model",
        "sample-proxy",
        "",
        "",
        "",
        str(profile_path),
    ]


def test_wrapper_decoder_is_scoped_and_does_not_execute_toml_content() -> None:
    wrapper = WRAPPER.read_text(encoding="utf-8")
    start = wrapper.index("__codexchange_toml_value() {")
    end = wrapper.index("\n}\n", start) + 3
    function = wrapper[start:end]

    assert "decode_basic_string" in function
    assert 'ch == "\\\\" || ch == "\\\""' in function
    assert "eval " not in function
    assert "printf %b" not in function
    assert "source " not in function
