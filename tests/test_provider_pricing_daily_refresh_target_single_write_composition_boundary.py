from __future__ import annotations

import importlib
import inspect
from pathlib import Path

import pytest

app = importlib.import_module(
    "codexchange_proxy.app"
)


def test_provider_owned_ready_dispatches_exactly_once(
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
        return {
            "status": "ok",
            "writes_cache": True,
            "cache_path": str(provider_path),
            "execution": {
                "execution_attempted": True,
                "target_count": 1,
            },
        }

    monkeypatch.setattr(
        app,
        (
            "_provider_pricing_refresh_writer_"
            "single_write_execution"
        ),
        fake_execution,
    )

    target = (
        tmp_path
        / "deepseek"
        / "pricing.json"
    )

    result = (
        app
        ._provider_pricing_daily_refresh_target_single_write_execution(
            "deepseek",
            activate=True,
            mode="provider-owned",
            provider_path=target,
            model="deepseek-v4-pro",
            source_url="https://example.invalid",
            timeout=3.0,
        )
    )

    assert result["status"] == "ok"
    assert result["writes_cache"] is True
    assert calls == [
        {
            "provider_id": "deepseek",
            "activate": True,
            "mode": "provider_owned",
            "provider_path": str(target),
            "model": "deepseek-v4-pro",
            "source_url": "https://example.invalid",
            "timeout": 3.0,
        }
    ]
    assert (
        result[
            "daily_refresh_target_execution"
        ]["execution_attempted"]
        is True
    )
    assert (
        result[
            "daily_refresh_target_execution"
        ]["target_count"]
        == 1
    )
    assert result["runtime_wired"] is False
    assert (
        result["changes_daily_refresh_contract"]
        is False
    )
    assert result["dual_write"] is False
    assert result["fallback_write"] is False


def test_activation_false_never_dispatches(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[str] = []

    def forbidden(
        *args: object,
        **kwargs: object,
    ) -> object:
        calls.append("called")
        raise AssertionError(
            "execution seam was called"
        )

    monkeypatch.setattr(
        app,
        (
            "_provider_pricing_refresh_writer_"
            "single_write_execution"
        ),
        forbidden,
    )

    target = tmp_path / "pricing.json"

    result = (
        app
        ._provider_pricing_daily_refresh_target_single_write_execution(
            "deepseek",
            activate=False,
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


def test_disabled_mode_never_dispatches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def forbidden(
        *args: object,
        **kwargs: object,
    ) -> object:
        calls.append("called")
        raise AssertionError(
            "disabled mode executed"
        )

    monkeypatch.setattr(
        app,
        (
            "_provider_pricing_refresh_writer_"
            "single_write_execution"
        ),
        forbidden,
    )

    result = (
        app
        ._provider_pricing_daily_refresh_target_single_write_execution(
            "deepseek",
            activate=True,
            mode="disabled",
            provider_path=None,
        )
    )

    assert result["status"] == "disabled"
    assert result["writes_cache"] is False
    assert result["selected_mode"] == "disabled"
    assert (
        result["execution"][
            "execution_attempted"
        ]
        is False
    )
    assert calls == []


@pytest.mark.parametrize(
    "mode,provider_path",
    [
        ("legacy_shared", None),
        ("provider_owned", None),
    ],
)
def test_invalid_target_never_dispatches(
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    provider_path: str | None,
) -> None:
    calls: list[str] = []

    def forbidden(
        *args: object,
        **kwargs: object,
    ) -> object:
        calls.append("called")
        raise AssertionError(
            "invalid target executed"
        )

    monkeypatch.setattr(
        app,
        (
            "_provider_pricing_refresh_writer_"
            "single_write_execution"
        ),
        forbidden,
    )

    result = (
        app
        ._provider_pricing_daily_refresh_target_single_write_execution(
            "deepseek",
            activate=True,
            mode=mode,
            provider_path=provider_path,
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


def test_registered_provider_without_pricing_support_never_dispatches(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[str] = []

    def forbidden(
        *args: object,
        **kwargs: object,
    ) -> object:
        calls.append("called")
        raise AssertionError(
            "unsupported pricing provider executed"
        )

    monkeypatch.setattr(
        app,
        (
            "_provider_pricing_refresh_writer_"
            "single_write_execution"
        ),
        forbidden,
    )

    target = (
        tmp_path
        / "qwen-beijing"
        / "pricing.json"
    )

    result = (
        app
        ._provider_pricing_daily_refresh_target_single_write_execution(
            "qwen-beijing",
            activate=True,
            mode="provider_owned",
            provider_path=target,
        )
    )

    assert result["provider"] == "qwen_beijing"
    assert result["status"] == "error"
    assert result["writes_cache"] is False
    assert calls == []
    assert not target.exists()


def test_unknown_adapter_fails_before_dispatch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[str] = []

    def forbidden(
        *args: object,
        **kwargs: object,
    ) -> object:
        calls.append("called")
        raise AssertionError(
            "unknown adapter executed"
        )

    monkeypatch.setattr(
        app,
        (
            "_provider_pricing_refresh_writer_"
            "single_write_execution"
        ),
        forbidden,
    )

    target = (
        tmp_path
        / "anthropic"
        / "pricing.json"
    )

    with pytest.raises(
        ValueError,
        match=(
            "unsupported_provider_adapter:"
            "anthropic"
        ),
    ):
        (
            app
            ._provider_pricing_daily_refresh_target_single_write_execution(
                "anthropic",
                activate=True,
                mode="provider_owned",
                provider_path=target,
            )
        )

    assert calls == []
    assert not target.exists()
    assert not target.parent.exists()


def test_execution_error_is_preserved_and_augmented(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def fake_execution(
        *args: object,
        **kwargs: object,
    ) -> dict[str, object]:
        return {
            "status": "error",
            "reason": (
                "official_pricing_cache_"
                "write_failed"
            ),
            "writes_cache": False,
            "old_cache_preserved": True,
            "execution": {
                "execution_attempted": True,
                "target_count": 1,
            },
        }

    monkeypatch.setattr(
        app,
        (
            "_provider_pricing_refresh_writer_"
            "single_write_execution"
        ),
        fake_execution,
    )

    target = tmp_path / "pricing.json"

    result = (
        app
        ._provider_pricing_daily_refresh_target_single_write_execution(
            "deepseek",
            activate=True,
            mode="provider_owned",
            provider_path=target,
        )
    )

    assert result["status"] == "error"
    assert result["reason"] == (
        "official_pricing_cache_write_failed"
    )
    assert result["old_cache_preserved"] is True
    assert (
        result[
            "daily_refresh_target_execution"
        ]["execution_attempted"]
        is True
    )


def test_deepseek_wrapper_delegates_exact_arguments(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[dict[str, object]] = []

    def fake_composition(
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
        (
            "_provider_pricing_daily_refresh_"
            "target_single_write_execution"
        ),
        fake_composition,
    )

    target = tmp_path / "pricing.json"

    result = (
        app
        ._deepseek_pricing_daily_refresh_target_single_write_execution(
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


def test_composition_signatures_require_explicit_fields() -> None:
    provider_signature = inspect.signature(
        app
        ._provider_pricing_daily_refresh_target_single_write_execution
    )
    wrapper_signature = inspect.signature(
        app
        ._deepseek_pricing_daily_refresh_target_single_write_execution
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
        wrapper_signature.parameters
    ) == [
        "activate",
        "mode",
        "provider_path",
        "model",
        "source_url",
        "timeout",
    ]


def test_daily_refresh_runtime_remains_unwired() -> None:
    source = inspect.getsource(
        app._pricing_daily_refresh_contract
    )

    assert (
        "_provider_pricing_daily_refresh_"
        "target_single_write_execution"
        not in source
    )
    assert (
        "_deepseek_pricing_daily_refresh_"
        "target_single_write_execution"
        not in source
    )
    assert (
        "_provider_pricing_daily_refresh_"
        "target_activation_contract"
        not in source
    )
    assert (
        "_provider_pricing_refresh_writer_"
        "single_write_execution"
        not in source
    )
    assert (
        "_refresh_provider_pricing_from_official_docs("
        in source
    )
    assert '"deepseek"' in source
    assert "_pricing_cache_path()" in source


def test_composition_has_no_hidden_activation_input() -> None:
    source = inspect.getsource(
        app
        ._provider_pricing_daily_refresh_target_single_write_execution
    )

    assert "os.environ" not in source
    assert "getenv" not in source
    assert "COX_" not in source
    assert "_pricing_config_path" not in source
    assert "_pricing_cache_path" not in source
    assert "_write_pricing_cache_atomic" not in source
    assert (
        "_write_provider_pricing_cache_atomic"
        not in source
    )
    assert (
        "_provider_pricing_daily_refresh_"
        "target_activation_contract"
        in source
    )
    assert (
        "_provider_pricing_refresh_writer_"
        "single_write_execution"
        in source
    )
