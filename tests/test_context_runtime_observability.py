import json
from pathlib import Path

import pytest
import importlib

proxy_app = importlib.import_module("deepseek_responses_proxy.app")
from httpx import ASGITransport, AsyncClient

from deepseek_responses_proxy.app import create_app


@pytest.mark.asyncio
async def test_proxy_status_reports_context_config_and_last_reports(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DEEPSEEK_PROXY_COMPACT_ENABLED", "1")
    monkeypatch.setenv("DEEPSEEK_PROXY_COMPACT_TRIGGER_CHARS", "12345")
    monkeypatch.setenv("DEEPSEEK_PROXY_COMPACT_TARGET_CHARS", "6789")
    monkeypatch.setenv("DEEPSEEK_PROXY_COMPACT_KEEP_RECENT_MESSAGES", "11")
    monkeypatch.setenv("DEEPSEEK_PROXY_MAX_CONTEXT_CHARS", "22222")
    monkeypatch.setenv("DEEPSEEK_PROXY_MAX_TOOL_OUTPUT_CHARS", "333")
    monkeypatch.setenv("DEEPSEEK_PROXY_KEEP_RECENT_MESSAGES", "7")

    debug_dir = Path(".debug")
    debug_dir.mkdir()
    (debug_dir / "context_compaction_report.json").write_text(
        json.dumps(
            {
                "version": "test-version",
                "enabled": True,
                "compacted": True,
                "reason": "triggered",
                "summary_source": "deepseek",
                "before_chars": 100000,
                "after_chars": 20000,
                "chars_removed": 80000,
                "message_count_before": 50,
                "message_count_after": 10,
                "trigger_chars": 12345,
                "target_chars": 6789,
                "material": {
                    "compactable_message_count": 40,
                    "recent_message_count": 10,
                    "recent_start": 40,
                    "material_chars": 12000,
                    "compaction_prompt_fingerprint": {
                        "available": True,
                        "sha256": "b" * 64,
                        "raw_prompt_exposed": False,
                        "raw_material_exposed": False,
                    },
                    "compact_material_classifier_dry_run": {
                        "available": True,
                        "mode": "dry_run",
                        "applied": False,
                    },
                    "retained_recent_policy": {
                        "available": True,
                        "retained_recent_message_count": 10,
                    },
                },
                "build": {
                    "summary_chars": 3000,
                    "summary_was_trimmed": False,
                    "after_final_shrink_chars": 20000,
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (debug_dir / "context_trimming_report.json").write_text(
        json.dumps(
            {
                "version": "test-version",
                "enabled": True,
                "trimmed": False,
                "before_chars": 20000,
                "after_chars": 20000,
                "chars_removed": 0,
                "message_count_before": 10,
                "message_count_after": 10,
                "max_context_chars": 22222,
                "max_tool_output_chars": 333,
                "keep_recent_messages": 7,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    app = create_app()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/v1/proxy/status")

    assert response.status_code == 200
    data = response.json()

    assert data["version"].startswith("v")
    assert "context" in data

    compaction = data["context"]["compaction"]
    trimming = data["context"]["trimming"]

    assert compaction["config"]["enabled"] is True
    assert compaction["config"]["policy"] == "adaptive"
    assert compaction["config"]["trigger_chars"] == 12345
    assert compaction["config"]["target_chars"] == 6789
    assert compaction["config"]["keep_recent_messages"] == 11
    assert "min_target_chars" in compaction["config"]
    assert "max_target_chars" in compaction["config"]

    assert compaction["last_report"]["exists"] is True
    assert compaction["last_report"]["compacted"] is True
    assert compaction["last_report"]["summary_source"] == "deepseek"
    assert compaction["last_report"]["chars_removed"] == 80000
    assert compaction["last_report"]["material"]["compactable_message_count"] == 40
    assert compaction["last_report"]["compact_audit"]["available"] is True
    assert compaction["last_report"]["compact_audit"]["fingerprint"]["sha256"] == "b" * 64
    assert compaction["last_report"]["compaction_prompt_fingerprint"]["sha256"] == "b" * 64
    assert compaction["last_report"]["compact_material_classifier_dry_run"]["mode"] == "dry_run"
    assert compaction["last_report"]["retained_recent_policy"]["retained_recent_message_count"] == 10
    assert compaction["last_report"]["build"]["summary_chars"] == 3000

    live_report = {
        "version": "v0.3.9-alpha",
        "enabled": True,
        "compacted": True,
        "reason": "adaptive_triggered",
        "before_chars": 10000,
        "after_chars": 4000,
        "material": {
            "compactable_message_count": 8,
            "compaction_prompt_fingerprint": {
                "available": True,
                "sha256": "a" * 64,
                "redacted": True,
            },
            "compact_material_classifier_dry_run": {
                "available": True,
                "mode": "dry_run",
                "applied": False,
            },
            "retained_recent_policy": {
                "available": True,
                "retained_recent_message_count": 3,
            },
        },
        "compaction_prompt_fingerprint": {
            "available": True,
            "sha256": "a" * 64,
            "redacted": True,
        },
        "compact_material_classifier_dry_run": {
            "available": True,
            "mode": "dry_run",
            "applied": False,
        },
        "retained_recent_policy": {
            "available": True,
            "retained_recent_message_count": 3,
        },
    }
    runtime = proxy_app._runtime_payload_guard_contract({"compaction": {"config": {}}}, compaction_report=live_report)
    last_report = runtime["compaction"]["last_report"]
    assert runtime["compaction"]["compact_audit"]["available"] is True
    assert runtime["compaction"]["compact_audit"]["fingerprint"]["sha256"] == "a" * 64
    assert last_report["compact_audit"]["fingerprint"]["sha256"] == "a" * 64
    assert last_report["compaction_prompt_fingerprint"]["sha256"] == "a" * 64
    assert last_report["compact_material_classifier_dry_run"]["mode"] == "dry_run"
    assert last_report["retained_recent_policy"]["retained_recent_message_count"] == 3

    assert trimming["config"]["max_context_chars"] == 22222
    assert trimming["config"]["max_tool_output_chars"] == 333
    assert trimming["config"]["keep_recent_messages"] == 7
    assert trimming["last_report"]["exists"] is True
    assert trimming["last_report"]["trimmed"] is False
    assert trimming["last_report"]["chars_removed"] == 0


@pytest.mark.asyncio
async def test_proxy_status_reports_missing_context_reports(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    app = create_app()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/v1/proxy/status")

    assert response.status_code == 200
    data = response.json()

    assert data["context"]["compaction"]["last_report"]["exists"] is False
    assert data["context"]["trimming"]["last_report"]["exists"] is False
