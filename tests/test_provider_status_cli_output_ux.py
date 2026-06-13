from __future__ import annotations

import contextlib
import io
import json
import tempfile
from pathlib import Path

from codexchange_proxy import cli


def test_adapter_matrix_compact_and_display_rows_are_user_readable() -> None:
    compact = cli._model_api_provider_adapter_matrix_compact()
    display = cli._model_api_provider_adapter_matrix_display()

    assert compact == [
        {"provider": "deepseek", "adapter_kind": "native", "adapter_family": "deepseek", "adapter_provider_id": "deepseek"},
        {"provider": "kimi", "adapter_kind": "native", "adapter_family": "kimi", "adapter_provider_id": "kimi"},
        {"provider": "zhipu", "adapter_kind": "native", "adapter_family": "zhipu", "adapter_provider_id": "zhipu"},
        {"provider": "zhipu-coding", "adapter_kind": "native", "adapter_family": "zhipu", "adapter_provider_id": "zhipu_coding"},
        {"provider": "zai", "adapter_kind": "native", "adapter_family": "zai", "adapter_provider_id": "zai"},
        {"provider": "zai-coding", "adapter_kind": "native", "adapter_family": "zai", "adapter_provider_id": "zai_coding"},
        {"provider": "qwen-beijing", "adapter_kind": "native", "adapter_family": "qwen", "adapter_provider_id": "qwen_beijing"},
        {"provider": "qwen-singapore", "adapter_kind": "native", "adapter_family": "qwen", "adapter_provider_id": "qwen_singapore"},
        {"provider": "qwen-us", "adapter_kind": "native", "adapter_family": "qwen", "adapter_provider_id": "qwen_us"},
        {"provider": "custom", "adapter_kind": "generic", "adapter_family": "openai_compatible", "adapter_provider_id": "openai_compatible"},
    ]

    assert "deepseek        native  deepseek           deepseek" in display
    assert "qwen-beijing    native  qwen               qwen_beijing" in display
    assert "qwen-singapore  native  qwen               qwen_singapore" in display
    assert "qwen-us         native  qwen               qwen_us" in display
    assert "zhipu           native  zhipu              zhipu" in display
    assert "zhipu-coding    native  zhipu              zhipu_coding" in display
    assert "kimi            native  kimi               kimi" in display
    assert "custom          generic openai_compatible  openai_compatible" in display


def test_config_show_exposes_compact_adapter_matrix_for_cli_ux() -> None:
    env_file = Path(tempfile.mkdtemp(prefix="cox-p30a13-show-")) / "env"
    env_file.write_text(
        "export COX_MODEL_PROVIDER=qwen_beijing\n"
        "export COX_MODEL=qwen-plus\n"
        "export COX_MODEL_API_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1\n"
        "export COX_MODEL_API_KEY=sk-test\n",
        encoding="utf-8",
    )

    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        rc = cli.main(["config", "show", "--env-file", str(env_file)])

    assert rc == 0
    payload = json.loads(stdout.getvalue())
    model_api = payload["model_api"]

    assert model_api["adapter_kind"] == "native"
    assert model_api["adapter_status"]["adapter_provider_id"] == "qwen_beijing"
    assert model_api["adapter_provider_id"] == "qwen_beijing"
    assert model_api["adapter_family"] == "qwen"

    compact = model_api["adapter_matrix_compact"]
    display = model_api["adapter_matrix_display"]

    assert {"provider": "qwen-beijing", "adapter_kind": "native", "adapter_family": "qwen", "adapter_provider_id": "qwen_beijing"} in compact
    assert {"provider": "kimi", "adapter_kind": "native", "adapter_family": "kimi", "adapter_provider_id": "kimi"} in compact
    assert "qwen-beijing    native  qwen               qwen_beijing" in display
    assert "zhipu           native  zhipu              zhipu" in display
    assert "zhipu-coding    native  zhipu              zhipu_coding" in display
    assert "kimi            native  kimi               kimi" in display


def test_ambiguous_qwen_alias_display_remains_generic_when_requested_directly() -> None:
    rows = [cli._model_api_provider_adapter_status_row(provider) for provider in ("qwen", "dashscope")]
    compact = cli._model_api_provider_adapter_matrix_compact(rows)
    display = cli._model_api_provider_adapter_matrix_display(rows)

    assert compact == [
        {"provider": "qwen", "adapter_kind": "generic", "adapter_family": "openai_compatible", "adapter_provider_id": "openai_compatible"},
        {"provider": "dashscope", "adapter_kind": "generic", "adapter_family": "openai_compatible", "adapter_provider_id": "openai_compatible"},
    ]
    assert "qwen            generic openai_compatible  openai_compatible" in display
    assert "dashscope       generic openai_compatible  openai_compatible" in display
