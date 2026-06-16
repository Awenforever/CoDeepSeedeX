from __future__ import annotations

import importlib
import inspect
import sys
from pathlib import Path


app_module = importlib.import_module("codexchange_proxy.app")


def test_provider_tokenizer_candidate_wrapper_source_contract() -> None:
    provider_source = inspect.getsource(
        app_module._provider_profile_tokenizer_json_candidates
    )
    legacy_source = inspect.getsource(
        app_module._profile_tokenizer_json_candidates
    )
    contract_source = inspect.getsource(
        app_module._profile_tokenizer_contract
    )

    assert "get_provider_adapter(adapter_provider)" in provider_source
    assert 'get_provider_adapter("deepseek")' not in provider_source
    assert (
        '_provider_profile_tokenizer_json_candidates(\n'
        '        "deepseek",\n'
        "        kind,"
        in legacy_source
    )
    assert (
        "_provider_profile_tokenizer_json_candidates("
        "provider_value, kind)"
        in contract_source.replace("\n", " ")
        or (
            "_provider_profile_tokenizer_json_candidates(\n"
            "        provider_value,\n"
            "        kind,"
            in contract_source
        )
    )


def test_provider_tokenizer_candidates_use_selected_adapter(
    monkeypatch,
    tmp_path: Path,
) -> None:
    calls: list[dict[str, object]] = []

    class FakeAdapter:
        def tokenizer_json_candidates(
            self,
            kind: str,
            *,
            resource_root: Path,
            package_root: Path,
            env_get,
        ):
            calls.append(
                {
                    "kind": kind,
                    "resource_root": resource_root,
                    "package_root": package_root,
                    "env_get": env_get,
                }
            )
            return [
                (
                    tmp_path / "provider-tokenizer.json",
                    "fake_provider_adapter",
                )
            ]

    requested_providers: list[str] = []

    def fake_get_provider_adapter(provider_id: str):
        requested_providers.append(provider_id)
        return FakeAdapter()

    monkeypatch.setattr(
        app_module,
        "get_provider_adapter",
        fake_get_provider_adapter,
    )
    monkeypatch.setenv(
        "COX_TOKENIZER_RESOURCE_DIR",
        str(tmp_path / "resources"),
    )

    result = (
        app_module
        ._provider_profile_tokenizer_json_candidates(
            "qwen_singapore",
            "qwen_test_kind",
        )
    )

    assert requested_providers == ["qwen_singapore"]
    assert result == [
        (
            tmp_path / "provider-tokenizer.json",
            "fake_provider_adapter",
        )
    ]
    assert calls[0]["kind"] == "qwen_test_kind"
    assert calls[0]["resource_root"] == (
        tmp_path / "resources"
    )


def test_generic_candidate_fallback_excludes_deepseek_aliases(
    monkeypatch,
    tmp_path: Path,
) -> None:
    def unavailable_adapter(_provider_id: str):
        raise ValueError("adapter unavailable")

    generic_json = tmp_path / "generic.json"
    deepseek_json = tmp_path / "deepseek.json"

    monkeypatch.setattr(
        app_module,
        "get_provider_adapter",
        unavailable_adapter,
    )
    monkeypatch.setenv(
        "COX_PROFILE_TOKENIZER_JSON",
        str(generic_json),
    )
    monkeypatch.setenv(
        "COX_DEEPSEEK_TOKENIZER_JSON",
        str(deepseek_json),
    )
    monkeypatch.setenv(
        "COX_TOKENIZER_RESOURCE_DIR",
        str(tmp_path / "resources"),
    )

    result = (
        app_module
        ._provider_profile_tokenizer_json_candidates(
            "custom",
            "custom_kind",
        )
    )

    assert (
        generic_json,
        "env.COX_PROFILE_TOKENIZER_JSON",
    ) in result

    assert all(
        path != deepseek_json
        for path, _source in result
    )
    assert all(
        "deepseek_v3" not in str(path)
        for path, _source in result
    )


def test_legacy_tokenizer_candidate_wrapper_delegates_to_deepseek(
    monkeypatch,
) -> None:
    calls: list[tuple[str | None, str]] = []

    def fake_provider_candidates(
        provider_id: str | None,
        kind: str,
    ):
        calls.append((provider_id, kind))
        return []

    monkeypatch.setattr(
        app_module,
        "_provider_profile_tokenizer_json_candidates",
        fake_provider_candidates,
    )

    assert (
        app_module
        ._profile_tokenizer_json_candidates(
            "deepseek_official_current"
        )
        == []
    )
    assert calls == [
        (
            "deepseek",
            "deepseek_official_current",
        )
    ]


def test_profile_tokenizer_contract_routes_fallback_candidates_by_provider(
    monkeypatch,
    tmp_path: Path,
) -> None:
    tokenizer_path = tmp_path / "tokenizer.json"
    tokenizer_path.write_text(
        "{}",
        encoding="utf-8",
    )

    class FakeAdapter:
        def profile_tokenizer_kind_for_model(
            self,
            model: str | None,
            provider: str | None = None,
        ) -> str:
            return "fake_kind"

    monkeypatch.setattr(
        app_module,
        "get_provider_adapter",
        lambda _provider_id: FakeAdapter(),
    )

    candidate_calls: list[tuple[str | None, str]] = []

    def fake_candidates(
        provider_id: str | None,
        kind: str,
    ):
        candidate_calls.append(
            (provider_id, kind)
        )
        return [
            (
                tokenizer_path,
                "test_provider_resource",
            )
        ]

    monkeypatch.setattr(
        app_module,
        "_provider_profile_tokenizer_json_candidates",
        fake_candidates,
    )
    monkeypatch.setitem(
        sys.modules,
        "tokenizers",
        object(),
    )

    contract = app_module._profile_tokenizer_contract(
        "custom-model",
        "custom",
    )

    assert candidate_calls == [
        (
            "custom",
            "fake_kind",
        )
    ]
    assert contract["available"] is True
    assert contract["provider"] == "custom"
    assert contract["tokenizer_kind"] == "fake_kind"
    assert contract["source"] == str(tokenizer_path)
    assert (
        contract["source_kind"]
        == "test_provider_resource"
    )
