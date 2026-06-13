from __future__ import annotations

import contextlib
import io
import json
import tempfile
from pathlib import Path

from codexchange_proxy import cli


def test_zhipu_native_status_is_exposed_at_model_api_top_level() -> None:
    for provider, adapter_id in (("zhipu", "zhipu"), ("zhipu_coding", "zhipu_coding")):
        env_file = Path(tempfile.mkdtemp(prefix=f"cox-p30a16-{provider}-")) / "env"
        env_file.write_text(
            f"export COX_MODEL_PROVIDER={provider}\n"
            "export COX_MODEL=glm-5.1\n"
            "export COX_MODEL_API_KEY=sk-test\n",
            encoding="utf-8",
        )

        payloads = {}
        for command in ("show", "status"):
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                rc = cli.main(["config", command, "--env-file", str(env_file)])
            assert rc == 0
            payload = json.loads(stdout.getvalue())
            payloads[command] = payload

            model_api = payload["model_api"]
            assert model_api["adapter_kind"] == "native"
            assert model_api["adapter_provider_id"] == adapter_id
            assert model_api["adapter_family"] == "zhipu"
            assert model_api["adapter_status"]["adapter_provider_id"] == adapter_id
            assert model_api["adapter_status"]["adapter_family"] == "zhipu"
            assert model_api["validation_method"] == "zhipu_openai_compatible_models"
            assert model_api["adapter_matrix_summary"]["native_count"] == 8
            assert model_api["adapter_matrix_summary"]["generic_count"] == 2

        assert payloads["show"] == payloads["status"]


def test_provider_adapter_contract_documents_current_native_matrix() -> None:
    text = Path("docs/provider-adapter-contract.md").read_text(encoding="utf-8")

    assert "The current adapter matrix after the Qwen, Zhipu, and Z.AI native adapter skeletons is:" in text
    assert "- `adapter_provider_id`: the currently configured provider adapter id." in text
    assert "- `adapter_family`: the currently configured provider adapter family." in text
    assert "| `zhipu` | native | `zhipu` |" in text
    assert "| `zhipu-coding` | native | `zhipu` |" in text
    assert "| `zai` | native | `zai` |" in text
    assert "| `zai-coding` | native | `zai` |" in text
    assert "| `custom` | generic | `openai_compatible` |" in text


def test_installer_provider_classification_matches_native_adapter_matrix() -> None:
    text = Path("scripts/install.sh").read_text(encoding="utf-8")

    assert 'kimi) printf \'%s\\n\' "Built-in OpenAI-compatible" ;;' in text
    assert 'zhipu|zhipu-coding|zai|zai-coding|qwen-beijing|qwen-singapore|qwen-us) printf \'%s\\n\' "Built-in native adapter" ;;' in text
    assert 'kimi|zai|zai-coding) printf \'%s\\n\' "Built-in OpenAI-compatible" ;;' not in text
    assert 'kimi|zhipu|zhipu-coding|zai|zai-coding|qwen-beijing|qwen-singapore|qwen-us) printf \'%s\\n\' "Built-in OpenAI-compatible" ;;' not in text
