from pathlib import Path
import json


def test_repo_model_catalog_uses_codex_visibility_schema():
    catalog_path = Path("experiments/model-catalog/deepseek-proxy-models.json")
    text = catalog_path.read_text(encoding="utf-8")
    assert '"visibility": "visible"' not in text
    data = json.loads(text)
    models = data.get("models", [])
    assert models
    for model in models:
        if "visibility" in model:
            assert model["visibility"] in {"list", "hide", "none"}


def test_repo_model_catalog_entries_have_codex_slug_schema():
    data = json.loads(Path("experiments/model-catalog/deepseek-proxy-models.json").read_text(encoding="utf-8"))
    models = data.get("models", [])
    assert models
    for model in models:
        assert isinstance(model.get("slug"), str)
        assert model["slug"].strip()
        assert isinstance(model.get("display_name") or model.get("displayName"), str)
        assert model.get("context_window") or model.get("context_window_tokens")


def test_model_catalog_does_not_emit_string_reasoning_level_presets():
    source = Path("deepseek_responses_proxy/cli.py").read_text(encoding="utf-8")
    catalog = Path("experiments/model-catalog/deepseek-proxy-models.json").read_text(encoding="utf-8")
    assert '"supported_reasoning_levels": ["minimal"' not in source
    assert "'supported_reasoning_levels': ['minimal'" not in source
    assert '"supported_reasoning_levels": [' not in catalog


def test_custom_provider_catalog_generator_emits_minimal_codex_schema_fields():
    source = Path("deepseek_responses_proxy/cli.py").read_text(encoding="utf-8")
    start = source.index("def _write_custom_provider_model_catalog(")
    end = source.index("\n\ndef ", start + 1)
    generator = source[start:end]
    assert '"slug": model_key' in generator
    assert '"display_name": model_key' in generator
    assert '"displayName": model_key' in generator
    assert '"provider": f"{provider_id}-proxy"' in generator
    assert '"context_window": int(context_window)' in generator
    assert '"max_context_window": int(context_window)' in generator
    assert '"visibility": "visible"' not in generator
