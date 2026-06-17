from __future__ import annotations

import importlib
import inspect
from pathlib import Path

import pytest


cli = importlib.import_module("codexchange_proxy.cli")


def test_profile_without_pricing_fields_preserves_legacy_startup() -> None:
    result = cli._profile_pricing_candidate_contract(
        {
            "model": "deepseek-v4-pro",
            "model_provider": "cox-proxy",
        }
    )

    assert result["status"] == "ok"
    assert result["candidate_contract_valid"] is True
    assert result["candidate_requested"] is False
    assert result["selected_mode"] == "legacy_shared"
    assert result["argument_mapping"] is None
    assert result["model_provider_inference"] is False
    assert result["environment_lookup"] is False
    assert result["wrapper_wired"] is False
    assert result["runtime_active"] is False


def test_complete_explicit_provider_owned_profile_candidate(
    tmp_path: Path,
) -> None:
    provider_path = tmp_path / "deepseek-pricing.json"
    provider_path.write_text("{}\n", encoding="utf-8")

    result = cli._profile_pricing_candidate_contract(
        {
            "model_provider": "unrelated-proxy",
            "pricing_provider_id": "DeepSeek",
            "pricing_provider_owned": True,
            "pricing_mode": "provider-owned",
            "pricing_provider_path": str(provider_path),
        }
    )

    assert result["status"] == "ok"
    assert result["candidate_contract_valid"] is True
    assert result["candidate_requested"] is True
    assert result["selected_mode"] == "provider_owned"
    assert result["argument_mapping"] == {
        "pricing_provider_id": "deepseek",
        "pricing_provider_owned": True,
        "pricing_mode": "provider_owned",
        "pricing_provider_path": str(provider_path),
    }
    assert result["candidate_source"] == "explicit_profile_fields_only"
    assert result["path_inference"] is False
    assert result["model_provider_inference"] is False
    assert result["profile_write"] is False
    assert result["startup_dispatch_wired"] is False
    assert result["writes_files"] is False


@pytest.mark.parametrize(
    ("values", "reason"),
    [
        (
            {"pricing_provider_id": "deepseek"},
            "profile_pricing_fields_incomplete",
        ),
        (
            {
                "pricing_provider_id": "deepseek",
                "pricing_provider_owned": "not-a-bool",
                "pricing_mode": "provider-owned",
                "pricing_provider_path": "/tmp/pricing.json",
            },
            "pricing_provider_owned_invalid_boolean",
        ),
        (
            {
                "pricing_provider_id": "deepseek",
                "pricing_provider_owned": False,
                "pricing_mode": "provider-owned",
                "pricing_provider_path": "/tmp/pricing.json",
            },
            "pricing_provider_owned_must_be_true",
        ),
        (
            {
                "pricing_provider_id": "deepseek",
                "pricing_provider_owned": True,
                "pricing_mode": "disabled",
                "pricing_provider_path": "/tmp/pricing.json",
            },
            "pricing_mode_must_be_provider_owned",
        ),
        (
            {
                "pricing_provider_id": "deepseek",
                "pricing_provider_owned": True,
                "pricing_mode": "provider-owned",
                "pricing_provider_path": "relative.json",
            },
            "pricing_provider_path_must_be_absolute",
        ),
        (
            {
                "pricing_provider_id": "deepseek",
                "pricing_provider_owned": True,
                "pricing_mode": "provider-owned",
                "pricing_provider_path": "/definitely/missing/pricing.json",
            },
            "pricing_provider_path_not_file",
        ),
    ],
)
def test_invalid_profile_candidate_fails_closed_without_side_effects(
    values: dict[str, object],
    reason: str,
) -> None:
    result = cli._profile_pricing_candidate_contract(values)

    assert result["status"] == "error"
    assert result["available"] is False
    assert result["candidate_contract_valid"] is False
    assert result["reason"] == reason
    assert result["selected_mode"] is None
    assert result["argument_mapping"] is None
    assert result["writes_files"] is False
    assert result["creates_directories"] is False
    assert result["wrapper_wired"] is False
    assert result["runtime_active"] is False


def test_profile_candidate_does_not_infer_from_model_provider_or_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("COX_MODEL_PROVIDER", "deepseek")
    monkeypatch.setenv("COX_PRICING_PROVIDER_OWNED", "1")
    monkeypatch.setenv("COX_PRICING_PROVIDER_CACHE_PATH", "/tmp/inferred.json")

    result = cli._profile_pricing_candidate_contract(
        {"model_provider": "example-proxy"}
    )

    assert result["candidate_requested"] is False
    assert result["selected_mode"] == "legacy_shared"
    assert result["argument_mapping"] is None
    assert result["model_provider_inference"] is False
    assert result["environment_lookup"] is False


def test_profile_renderer_supports_explicit_pricing_fields_in_stable_order() -> None:
    rendered = cli._render_simple_toml_key_values(
        {
            "model": "deepseek-v4-pro",
            "model_provider": "cox-proxy",
            "pricing_provider_id": "deepseek",
            "pricing_provider_owned": True,
            "pricing_mode": "provider_owned",
            "pricing_provider_path": "/tmp/deepseek-pricing.json",
        }
    )

    expected = [
        'model = "deepseek-v4-pro"',
        'model_provider = "cox-proxy"',
        'pricing_provider_id = "deepseek"',
        'pricing_provider_owned = true',
        'pricing_mode = "provider_owned"',
        'pricing_provider_path = "/tmp/deepseek-pricing.json"',
    ]
    assert rendered.splitlines() == expected


def test_profile_candidate_signature_and_source_remain_pure() -> None:
    function = cli._profile_pricing_candidate_contract
    signature = inspect.signature(function)

    assert list(signature.parameters) == ["profile_values"]
    parameter = signature.parameters["profile_values"]
    assert parameter.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
    assert parameter.default is inspect.Parameter.empty

    source = inspect.getsource(function)
    assert "os.environ" not in source
    assert "os.getenv" not in source
    assert "COX_MODEL_PROVIDER" not in source
    assert "COX_PRICING_PATH" not in source
    assert "--cache-path" not in source
    assert "_start_proxy" not in source
    assert "runtime_app" not in source
