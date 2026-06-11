from __future__ import annotations

import importlib
from pathlib import Path


def _app_module():
    return importlib.import_module("codexchange_proxy.app")


def _sample_compaction_report() -> dict:
    return {
        "version": "v0.3.9-alpha",
        "enabled": True,
        "compacted": True,
        "reason": "token_first_auto_compact_threshold_exceeded",
        "profile": "cox",
        "observed_at": "2026-05-22T12:34:00Z",
        "source": "runtime_context_builder",
        "estimated_context_tokens": 66022,
        "estimated_tokens_before_compact": 66022,
        "after_estimated_context_tokens": 17849,
        "estimated_tokens_after_compact": 17849,
        "tokens_removed": 48173,
        "estimated_tokens_removed_by_compact": 48173,
        "auto_compact_threshold_tokens": 20000,
        "model_auto_compact_token_limit": 20000,
        "model_context_window_tokens": 1000000,
        "auto_compact_ratio": 0.02,
        "threshold_exceeded": True,
        "primary_control_unit": "tokens",
        "raw_content_exposed": False,
        "redacted": True,
    }


def _sample_trimming_report() -> dict:
    return {
        "version": "v0.3.9-alpha",
        "enabled": True,
        "trimmed": False,
        "reason": "estimated_payload_tokens_within_token_first_runtime_limit",
        "profile": "cox",
        "observed_at": "2026-05-22T12:34:01Z",
        "source": "live_request_payload",
        "token_first_runtime_trim": {
            "available": True,
            "unit": "tokens",
            "source": "token_first_runtime_trim",
            "before_tokens": 20100,
            "after_tokens": 20100,
            "tokens_removed": 0,
            "max_context_tokens": 900000,
            "primary_control_unit": "tokens",
            "raw_content_exposed": False,
            "redacted": True,
        },
        "raw_content_exposed": False,
        "redacted": True,
    }


def test_sqlite_runtime_payload_reports_restore_after_restart(tmp_path: Path) -> None:
    app = _app_module()
    store = app.SQLiteResponseStore(tmp_path / "responses-thinking.sqlite3")

    store.save_runtime_payload_report(
        _sample_compaction_report(),
        kind="compaction",
        profile="cox",
        session_id="sess-1",
        request_id="resp-1",
        response_id="resp-1",
    )
    store.save_runtime_payload_report(
        _sample_trimming_report(),
        kind="trimming",
        profile="cox",
        session_id="sess-1",
        request_id="resp-1",
        response_id="resp-1",
    )

    restored_compaction = store.runtime_payload_report("cox", kind="compaction", session_id="sess-1")
    restored_trimming = store.runtime_payload_report("cox", kind="trimming", session_id="sess-1")

    assert restored_compaction is not None
    assert restored_compaction["restored_from_persistence"] is True
    assert restored_compaction["persistence_source"] == "SQLiteResponseStore.runtime_payload_report"
    assert restored_compaction["estimated_tokens_before_compact"] == 66022
    assert restored_compaction["estimated_tokens_after_compact"] == 17849
    assert restored_compaction["tokens_removed"] == 48173

    assert restored_trimming is not None
    assert restored_trimming["restored_from_persistence"] is True
    assert restored_trimming["token_first_runtime_trim"]["before_tokens"] == 20100



def test_weclaw_status_restores_runtime_payload_guard_from_persisted_reports(tmp_path: Path, monkeypatch) -> None:
    app = _app_module()
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg-config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg-data"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg-cache"))

    store = app.SQLiteResponseStore(tmp_path / "responses-thinking.sqlite3")
    store.save_runtime_payload_report(
        _sample_compaction_report(),
        kind="compaction",
        profile="cox",
        session_id="sess-1",
        request_id="resp-1",
        response_id="resp-1",
    )
    store.save_runtime_payload_report(
        _sample_trimming_report(),
        kind="trimming",
        profile="cox",
        session_id="sess-1",
        request_id="resp-1",
        response_id="resp-1",
    )

    restored_compaction = store.runtime_payload_report("cox", kind="compaction", session_id="sess-1")
    restored_trimming = store.runtime_payload_report("cox", kind="trimming", session_id="sess-1")
    assert restored_compaction is not None
    assert restored_compaction["estimated_tokens_before_compact"] == 66022
    assert restored_compaction["estimated_tokens_after_compact"] == 17849
    assert restored_compaction["tokens_removed"] == 48173
    assert restored_trimming is not None
    assert restored_trimming["token_first_runtime_trim"]["before_tokens"] == 20100

    payload = app._runtime_weclaw_status(
        "cox",
        store=store,
        balance=None,
        deepseek_client=object(),
        last_context_compaction_report=None,
        session_id="sess-1",
    )

    guard = payload["runtime_payload_guard"]
    compaction = guard["compaction"]
    trimming = guard["trimming"]
    dumped = __import__("json").dumps(guard, ensure_ascii=False, sort_keys=True)

    assert guard["available"] is True
    assert guard["unit"] == "tokens"
    assert guard["current_tokens"] == 20100
    assert guard["current_tokens_source"] == "token_first_runtime_trim"

    assert compaction["available"] is True
    assert compaction["unit"] == "tokens"
    assert compaction["status"] == "compacted"
    assert compaction.get("reason") not in {
        "no_runtime_compaction_report_observed",
        "runtime_compaction_tokens_unavailable",
    }

    assert trimming["available"] is True
    assert trimming["unit"] == "tokens"
    assert trimming["current_tokens"] == 20100
    assert trimming["current_tokens_source"] == "token_first_runtime_trim"

    assert "chars_removed" not in dumped
    assert "before_chars" not in dumped
    assert "after_chars" not in dumped
    assert "char_heuristic" not in dumped


def test_weclaw_status_prefers_persisted_matching_trim_report_over_stale_in_memory(tmp_path: Path, monkeypatch) -> None:
    app = _app_module()
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg-config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg-data"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg-cache"))

    store = app.SQLiteResponseStore(tmp_path / "responses-thinking.sqlite3")
    store.save_runtime_payload_report(
        _sample_trimming_report(),
        kind="trimming",
        profile="cox",
        session_id="sess-1",
        request_id="resp-1",
        response_id="resp-1",
    )

    class StaleTrimClient:
        last_context_trimming_report = {
            "version": "v0.3.9-alpha",
            "enabled": True,
            "trimmed": False,
            "observed_at": "2026-05-22T00:00:00Z",
            "token_first_trim_dry_run": {
                "available": True,
                "unit": "tokens",
                "runtime_context": {
                    "profile": "deepseek",
                    "auto_compact_threshold_tokens": 900000,
                },
            },
        }

    payload = app._runtime_weclaw_status(
        "cox",
        store=store,
        balance=None,
        deepseek_client=StaleTrimClient(),
        last_context_compaction_report=None,
        session_id="sess-1",
    )

    trimming = payload["runtime_payload_guard"]["trimming"]
    assert trimming["available"] is True
    assert trimming["status"] == "not_triggered"
    assert trimming["current_tokens"] == 20100
    assert trimming["max_context_tokens"] == 900000
    assert trimming["last_report"]["reason"] != "runtime_trimming_report_profile_mismatch"
    assert trimming["last_report"]["profile_mismatch_diagnostic"]["reason"] == "runtime_trimming_report_profile_mismatch"


def test_profile_scoped_trim_fallback_exposes_not_triggered_session_estimate() -> None:
    app = _app_module()

    report = app._profile_scoped_token_first_trim_not_triggered_report(
        profile="cox",
        context_window={
            "used_tokens": 19852,
            "auto_compact_token_limit": 900000,
            "model_context_window_tokens": 1000000,
        },
        profile_status={"context_window": {}},
        model_contract={"effective_model": "deepseek-v4-flash"},
        session_id="sess-current",
        diagnostic_report={
            "reason": "runtime_trimming_report_profile_mismatch",
            "requested_profile": "cox",
            "observed_profile": "deepseek",
        },
    )

    assert report is not None
    trim = report["token_first_runtime_trim"]
    assert trim["available"] is True
    assert trim["status"] == "not_triggered"
    assert trim["before_tokens"] == 19852
    assert trim["after_tokens"] == 19852
    assert trim["tokens_removed"] == 0
    assert trim["max_context_tokens"] == 900000
    assert trim["progress_numerator_tokens"] == 19852
    assert trim["progress_denominator_tokens"] == 19852
    assert trim["retention_ratio"] == 1.0
    assert trim["requested_profile"] == "cox"
    assert trim["observed_profile"] == "cox"

    guard = app._runtime_payload_guard_contract({"compaction": {"config": {}}}, trimming_report=report)
    assert guard["trimming"]["available"] is True
    assert guard["trimming"]["status"] == "not_triggered"
    assert guard["trimming"]["current_tokens"] == 19852
    assert guard["trimming"]["max_context_tokens"] == 900000
    assert guard["trimming"]["progress_numerator_tokens"] == 19852
    assert guard["trimming"]["progress_denominator_tokens"] == 19852
    assert guard["trimming"]["retention_ratio"] == 1.0
