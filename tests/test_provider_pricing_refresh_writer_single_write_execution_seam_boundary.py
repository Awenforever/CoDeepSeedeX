from __future__ import annotations

import importlib
import inspect
import json
from pathlib import Path

import pytest


app = importlib.import_module(
    "codexchange_proxy.app"
)


def _prices() -> dict[str, object]:
    return {
        "deepseek-v4-pro": {
            "input_cache_hit": 0.1,
            "input_cache_miss": 1.0,
            "output": 2.0,
        }
    }


def _install_success_dependencies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        app,
        "_fetch_text_url",
        lambda url, timeout=20.0: (
            "<html>pricing</html>"
        ),
    )

    def fake_parse(
        provider_id: str,
        text: str,
        *,
        include_metadata: bool = False,
    ) -> dict[str, object]:
        assert provider_id == "deepseek"
        assert text == "<html>pricing</html>"
        assert include_metadata is True
        return _prices()

    monkeypatch.setattr(
        app,
        "_parse_provider_official_pricing_html",
        fake_parse,
    )


def test_provider_owned_single_write_executes_exactly_one_provider_writer(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _install_success_dependencies(
        monkeypatch
    )

    target = (
        tmp_path
        / "providers"
        / "deepseek"
        / "pricing.json"
    )
    legacy = tmp_path / "legacy.json"

    monkeypatch.setenv(
        "COX_PRICING_CACHE_PATH",
        str(legacy),
    )

    calls: list[Path] = []
    original_provider_writer = (
        app
        ._write_deepseek_provider_pricing_cache_atomic
    )

    def capture_provider_writer(
        prices: dict[str, object],
        *,
        path: Path,
        source_url: str,
        fetched_at: str,
        ttl_seconds: int,
    ) -> None:
        calls.append(path)
        original_provider_writer(
            prices,
            path=path,
            source_url=source_url,
            fetched_at=fetched_at,
            ttl_seconds=ttl_seconds,
        )

    def forbidden_legacy_writer(
        *args: object,
        **kwargs: object,
    ) -> None:
        raise AssertionError(
            "legacy writer was called"
        )

    monkeypatch.setattr(
        app,
        "_write_deepseek_provider_pricing_cache_atomic",
        capture_provider_writer,
    )
    monkeypatch.setattr(
        app,
        "_write_pricing_cache_atomic",
        forbidden_legacy_writer,
    )

    result = (
        app
        ._provider_pricing_refresh_writer_single_write_execution(
            "deepseek",
            activate=True,
            mode="provider-owned",
            provider_path=target,
            model="deepseek-v4-pro",
            source_url=(
                "https://example.invalid/pricing"
            ),
            timeout=3.0,
        )
    )

    assert result["status"] == "ok"
    assert result["writes_cache"] is True
    assert result["cache_path"] == str(target)
    assert calls == [target]
    assert target.is_file()
    assert not legacy.exists()

    document = json.loads(
        target.read_text(
            encoding="utf-8",
        )
    )
    metadata = document["__metadata__"]

    assert metadata["provider"] == "deepseek"
    assert (
        metadata["adapter_provider_id"]
        == "deepseek"
    )
    assert metadata["family"] == "deepseek"
    assert (
        metadata["cache_scope"]
        == "provider_scoped"
    )
    assert (
        metadata["cache_schema_owner"]
        == "deepseek"
    )
    assert (
        metadata[
            "cache_is_provider_scoped"
        ]
        is True
    )

    execution = result["execution"]

    assert (
        execution["execution_seam"]
        == "function_level_unwired"
    )
    assert (
        execution["execution_attempted"]
        is True
    )
    assert execution["execution_allowed"] is True
    assert execution["target_count"] == 1
    assert execution["legacy_writer_called"] is False
    assert execution["legacy_path_written"] is False
    assert execution["dual_write"] is False
    assert execution["fallback_write"] is False
    assert execution["cli_lookup"] is False
    assert execution["environment_lookup"] is False
    assert (
        execution["existing_refresh_wrapper_modified"]
        is False
    )
    assert execution["existing_cli_modified"] is False


@pytest.mark.parametrize(
    ("activate", "mode", "provider_path", "reason"),
    [
        (
            False,
            "provider_owned",
            "pricing.json",
            "explicit_activation_not_requested",
        ),
        (
            True,
            "legacy_shared",
            None,
            "legacy_shared_activation_not_allowed",
        ),
        (
            True,
            "provider_owned",
            None,
            "explicit_provider_path_required",
        ),
        (
            True,
            "disabled",
            None,
            (
                "provider_pricing_refresh_"
                "single_write_requires_"
                "provider_owned_mode"
            ),
        ),
    ],
)
def test_invalid_execution_intent_fails_before_network_or_writer(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    activate: bool,
    mode: str,
    provider_path: str | None,
    reason: str,
) -> None:
    calls: list[str] = []

    def forbidden(*args: object, **kwargs: object) -> None:
        calls.append("called")
        raise AssertionError(
            "network or writer called"
        )

    monkeypatch.setattr(
        app,
        "_fetch_text_url",
        forbidden,
    )
    monkeypatch.setattr(
        app,
        "_write_pricing_cache_atomic",
        forbidden,
    )
    monkeypatch.setattr(
        app,
        "_write_deepseek_provider_pricing_cache_atomic",
        forbidden,
    )

    path = (
        tmp_path / provider_path
        if provider_path
        else None
    )

    result = (
        app
        ._provider_pricing_refresh_writer_single_write_execution(
            "deepseek",
            activate=activate,
            mode=mode,
            provider_path=path,
        )
    )

    assert result["status"] == "error"
    assert result["reason"] == reason
    assert result["writes_cache"] is False
    assert (
        result["execution"][
            "execution_attempted"
        ]
        is False
    )
    assert calls == []

    if path is not None:
        assert not path.exists()


@pytest.mark.parametrize(
    "provider_id",
    [
        "qwen-singapore",
        "kimi",
        "zhipu",
        "zai",
        "custom",
    ],
)
def test_unsupported_provider_fails_before_network(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    provider_id: str,
) -> None:
    calls: list[str] = []

    def forbidden(*args: object, **kwargs: object) -> None:
        calls.append("called")
        raise AssertionError(
            "unsupported provider executed"
        )

    monkeypatch.setattr(
        app,
        "_fetch_text_url",
        forbidden,
    )
    monkeypatch.setattr(
        app,
        "_write_pricing_cache_atomic",
        forbidden,
    )
    monkeypatch.setattr(
        app,
        "_write_deepseek_provider_pricing_cache_atomic",
        forbidden,
    )

    target = (
        tmp_path
        / provider_id
        / "pricing.json"
    )

    result = (
        app
        ._provider_pricing_refresh_writer_single_write_execution(
            provider_id,
            activate=True,
            mode="provider_owned",
            provider_path=target,
        )
    )

    assert result["status"] == "error"
    assert result["writes_cache"] is False
    assert (
        result["execution"][
            "execution_attempted"
        ]
        is False
    )
    assert calls == []
    assert not target.exists()
    assert not target.parent.exists()


def test_provider_writer_failure_preserves_existing_target(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _install_success_dependencies(
        monkeypatch
    )

    target = tmp_path / "pricing.json"
    original = (
        b'{"sentinel":"preserve"}\n'
    )
    target.write_bytes(original)

    def failing_provider_writer(
        *args: object,
        **kwargs: object,
    ) -> None:
        raise OSError(
            "provider_owned_write_failure"
        )

    def forbidden_legacy_writer(
        *args: object,
        **kwargs: object,
    ) -> None:
        raise AssertionError(
            "legacy writer was called"
        )

    monkeypatch.setattr(
        app,
        "_write_deepseek_provider_pricing_cache_atomic",
        failing_provider_writer,
    )
    monkeypatch.setattr(
        app,
        "_write_pricing_cache_atomic",
        forbidden_legacy_writer,
    )

    result = (
        app
        ._deepseek_pricing_refresh_writer_single_write_execution(
            activate=True,
            mode="provider_owned",
            provider_path=target,
            source_url=(
                "https://example.invalid/pricing"
            ),
        )
    )

    assert result["status"] == "error"
    assert (
        result["reason"]
        == "official_pricing_cache_write_failed"
    )
    assert result["writes_cache"] is False
    assert result["old_cache_preserved"] is True
    assert target.read_bytes() == original
    assert (
        result["execution"][
            "execution_attempted"
        ]
        is True
    )
    assert (
        result["execution"]["target_count"]
        == 1
    )


def test_deepseek_wrapper_delegates_explicitly(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[dict[str, object]] = []

    def fake_execution(
        provider_id: str,
        *,
        activate: bool,
        mode: str,
        provider_path: str | Path | None,
        model: str | None = None,
        source_url: str | None = None,
        timeout: float = 20.0,
    ) -> dict[str, object]:
        calls.append(
            {
                "provider_id": provider_id,
                "activate": activate,
                "mode": mode,
                "provider_path": provider_path,
                "model": model,
                "source_url": source_url,
                "timeout": timeout,
            }
        )
        return {"status": "ok"}

    monkeypatch.setattr(
        app,
        "_provider_pricing_refresh_writer_single_write_execution",
        fake_execution,
    )

    target = tmp_path / "pricing.json"

    result = (
        app
        ._deepseek_pricing_refresh_writer_single_write_execution(
            activate=True,
            mode="provider_owned",
            provider_path=target,
            model="deepseek-v4-pro",
            source_url="https://example.invalid",
            timeout=4.0,
        )
    )

    assert result == {"status": "ok"}
    assert calls == [
        {
            "provider_id": "deepseek",
            "activate": True,
            "mode": "provider_owned",
            "provider_path": target,
            "model": "deepseek-v4-pro",
            "source_url": "https://example.invalid",
            "timeout": 4.0,
        }
    ]


def test_execution_signatures_require_explicit_activation_fields() -> None:
    provider_signature = inspect.signature(
        app
        ._provider_pricing_refresh_writer_single_write_execution
    )
    deepseek_signature = inspect.signature(
        app
        ._deepseek_pricing_refresh_writer_single_write_execution
    )

    assert list(
        provider_signature.parameters
    ) == [
        "provider_id",
        "activate",
        "mode",
        "provider_path",
        "model",
        "source_url",
        "timeout",
    ]
    assert list(
        deepseek_signature.parameters
    ) == [
        "activate",
        "mode",
        "provider_path",
        "model",
        "source_url",
        "timeout",
    ]

    for signature in (
        provider_signature,
        deepseek_signature,
    ):
        for name in (
            "activate",
            "mode",
            "provider_path",
        ):
            parameter = (
                signature.parameters[name]
            )
            assert (
                parameter.kind
                is inspect.Parameter.KEYWORD_ONLY
            )
            assert (
                parameter.default
                is inspect.Parameter.empty
            )


def test_existing_refresh_cli_and_readers_remain_unwired() -> None:
    new_names = (
        "_provider_pricing_refresh_writer_"
        "single_write_execution",
        "_deepseek_pricing_refresh_writer_"
        "single_write_execution",
    )

    for function in (
        app._refresh_provider_pricing_from_official_docs,
        app._refresh_deepseek_pricing_from_official_docs,
        app._pricing_daily_refresh_contract,
        app._load_model_pricing_usd_per_1m,
        app._pricing_context_for_usage_event,
        app._weclaw_pricing_contract,
    ):
        source = inspect.getsource(
            function
        )

        for name in new_names:
            assert name not in source

    refresh_source = inspect.getsource(
        app
        ._refresh_provider_pricing_from_official_docs
    )

    assert (
        "pricing_cache_path="
        "_pricing_cache_path"
        in refresh_source
    )
    assert (
        "write_pricing_cache_atomic="
        "_write_pricing_cache_atomic"
        in refresh_source
    )
    assert (
        "_write_deepseek_provider_"
        "pricing_cache_atomic"
        not in refresh_source
    )

    cli = importlib.import_module(
        "codexchange_proxy.cli"
    )
    cli_source = inspect.getsource(
        cli._pricing
    )

    for name in new_names:
        assert name not in cli_source

    for value in (
        "--pricing-refresh-writer-mode",
        "--pricing-refresh-writer-path",
        "--pricing-provider-cache-path",
        "COX_PRICING_REFRESH_WRITER_MODE",
        "COX_PRICING_REFRESH_WRITER_PATH",
        "COX_PRICING_PROVIDER_CACHE_PATH",
    ):
        assert value not in cli_source
