from pathlib import Path
import json


REQUIRED_CODEX_MODEL_FIELDS = {
    "prefer_websockets",
    "support_verbosity",
    "default_verbosity",
    "apply_patch_tool_type",
    "web_search_tool_type",
    "input_modalities",
    "supports_image_detail_original",
    "truncation_policy",
    "supports_parallel_tool_calls",
    "context_window",
    "max_context_window",
    "auto_compact_token_limit",
    "reasoning_summary_format",
    "default_reasoning_summary",
    "slug",
    "display_name",
    "description",
    "default_reasoning_level",
    "supported_reasoning_levels",
    "shell_type",
    "visibility",
    "minimal_client_version",
    "supported_in_api",
    "availability_nux",
    "upgrade",
    "priority",
    "base_instructions",
    "model_messages",
}


def test_repo_model_catalog_entries_have_codex_required_schema():
    data = json.loads(Path("experiments/model-catalog/deepseek-proxy-models.json").read_text(encoding="utf-8"))
    models = data.get("models", [])
    assert models
    for model in models:
        missing = REQUIRED_CODEX_MODEL_FIELDS - set(model)
        assert not missing, (model.get("slug"), sorted(missing))
        assert model["visibility"] in {"list", "hide", "none"}
        assert model["shell_type"] == "shell_command"
        assert isinstance(model["supported_reasoning_levels"], list)
        assert model["supported_reasoning_levels"]
        for level in model["supported_reasoning_levels"]:
            assert isinstance(level, dict)
            assert isinstance(level.get("effort"), str)
            assert isinstance(level.get("description"), str)


def test_custom_provider_catalog_generator_emits_codex_required_schema():
    source = Path("deepseek_responses_proxy/cli.py").read_text(encoding="utf-8")
    start = source.index("def _write_custom_provider_model_catalog(")
    end = source.index("\n\ndef ", start + 1)
    generator = source[start:end]
    for literal in [
        '"slug": model_key',
        '"shell_type": "shell_command"',
        '"minimal_client_version": "0.98.0"',
        '"supported_in_api": True',
        '"base_instructions":',
        '"model_messages":',
        '"availability_nux": None',
        '"upgrade": None',
    ]:
        assert literal in generator
    assert '"visibility": "visible"' not in generator
