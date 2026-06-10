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


def test_custom_provider_catalog_generator_does_not_emit_visible_visibility():
    source = Path("deepseek_responses_proxy/cli.py").read_text(encoding="utf-8")
    assert '"visibility": "visible"' not in source
    assert "'visibility': 'visible'" not in source
