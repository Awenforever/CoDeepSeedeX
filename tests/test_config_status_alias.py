from __future__ import annotations

import contextlib
import io
import json
import tempfile
from pathlib import Path

from codexchange_proxy import cli


def _run_config_command(command: str) -> dict[str, object]:
    env_file = Path(tempfile.mkdtemp(prefix=f"cox-p30a14-{command}-")) / "env"
    env_file.write_text(
        "export COX_MODEL_PROVIDER=qwen_beijing\n"
        "export COX_MODEL=qwen-plus\n"
        "export COX_MODEL_API_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1\n"
        "export COX_MODEL_API_KEY=sk-test\n",
        encoding="utf-8",
    )

    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        rc = cli.main(["config", command, "--env-file", str(env_file)])

    assert rc == 0
    payload = json.loads(stdout.getvalue())

    # env_file path is expected to differ because each run uses a fresh temp file.
    payload.pop("env_file", None)
    if isinstance(payload.get("custom_provider_registry"), dict):
        payload["custom_provider_registry"].pop("path", None)

    return payload


def test_config_status_alias_matches_config_show_payload() -> None:
    show_payload = _run_config_command("show")
    status_payload = _run_config_command("status")

    assert status_payload == show_payload
    assert status_payload["model_api"]["adapter_kind"] == "native"
    assert status_payload["model_api"]["adapter_status"]["adapter_provider_id"] == "qwen_beijing"
    assert status_payload["model_api"]["adapter_provider_id"] == "qwen_beijing"
    assert status_payload["model_api"]["adapter_family"] == "qwen"
    assert status_payload["model_api"]["adapter_matrix_summary"]["native_count"] == 9
    assert status_payload["model_api"]["adapter_matrix_summary"]["generic_count"] == 1
    assert "qwen-beijing    native  qwen               qwen_beijing" in status_payload["model_api"]["adapter_matrix_display"]
    assert "kimi            native  kimi               kimi" in status_payload["model_api"]["adapter_matrix_display"]


def test_config_status_alias_is_listed_in_config_help() -> None:
    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        try:
            cli.main(["config", "--help"])
        except SystemExit as exc:
            assert exc.code == 0
        else:
            raise AssertionError("argparse help should terminate with SystemExit(0)")

    text = stdout.getvalue()
    assert "show" in text
    assert "status" in text
