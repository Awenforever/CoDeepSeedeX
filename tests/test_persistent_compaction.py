import json
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from deepseek_responses_proxy.app import (
    InMemoryResponseStore,
    _compact_chat_history_for_codex_like_persistence,
    _compaction_prompt_messages,
    create_app,
)


class FakeDeepSeekClient:
    def __init__(self):
        self.payloads = []
        self.compaction_calls = 0
        self.normal_calls = 0

    async def chat_completions(self, payload):
        self.payloads.append(payload)
        serialized = json.dumps(payload, ensure_ascii=False)

        if "Codex-like conversation compactor" in serialized:
            self.compaction_calls += 1
            return {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": (
                                "OBJECTIVE\n"
                                "Continue maintaining deepseek-responses-proxy.\n\n"
                                "REPOSITORY_STATE\n"
                                "Repo path: /home/kelvin/projects/deepseek-responses-proxy.\n\n"
                                "COMPLETED_CHANGES\n"
                                "Older long context was compacted by v2.3a4 test.\n\n"
                                "FILES_AND_CODE_AREAS\n"
                                "deepseek_responses_proxy/app.py and tests.\n\n"
                                "TESTS_AND_VALIDATION\n"
                                "Use pytest and py_compile.\n\n"
                                "OPEN_ISSUES\n"
                                "Continue from recent messages.\n\n"
                                "USER_CONSTRAINTS\n"
                                "Save outputs to /tmp files and show summaries only.\n\n"
                                "NEXT_STEPS\n"
                                "Proceed with the current request."
                            ),
                        }
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            }

        self.normal_calls += 1
        return {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": f"normal response {self.normal_calls}",
                    }
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }


@pytest.mark.asyncio
async def test_persistent_compaction_replaces_stored_previous_history(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    monkeypatch.setenv("DEEPSEEK_PROXY_COMPACT_POLICY", "fixed")
    monkeypatch.setenv("DEEPSEEK_PROXY_COMPACT_ENABLED", "0")
    monkeypatch.setenv("DEEPSEEK_PROXY_MAX_CONTEXT_CHARS", "1000000")
    monkeypatch.setenv("DEEPSEEK_PROXY_MAX_TOOL_OUTPUT_CHARS", "100000")
    monkeypatch.setenv("DEEPSEEK_PROXY_KEEP_RECENT_MESSAGES", "24")

    fake = FakeDeepSeekClient()
    store = InMemoryResponseStore()
    app = create_app(deepseek_client=fake, store=store)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first = await client.post(
            "/v1/responses",
            json={"input": "initial huge project context\n" + ("X" * 20000)},
        )
        assert first.status_code == 200
        first_body = first.json()

        monkeypatch.setenv("DEEPSEEK_PROXY_COMPACT_ENABLED", "1")
        monkeypatch.setenv("DEEPSEEK_PROXY_COMPACT_TRIGGER_CHARS", "3000")
        monkeypatch.setenv("DEEPSEEK_PROXY_COMPACT_TARGET_CHARS", "5000")
        monkeypatch.setenv("DEEPSEEK_PROXY_COMPACT_KEEP_RECENT_MESSAGES", "1")
        monkeypatch.setenv("DEEPSEEK_PROXY_COMPACT_MATERIAL_CHARS", "12000")
        monkeypatch.setenv("DEEPSEEK_PROXY_COMPACT_MAX_SUMMARY_CHARS", "3000")

        second = await client.post(
            "/v1/responses",
            json={
                "previous_response_id": first_body["id"],
                "input": "continue the current task",
            },
        )
        assert second.status_code == 200
        second_body = second.json()

        assert fake.compaction_calls == 1
        assert fake.normal_calls == 2

        second_normal_payload = fake.payloads[-1]
        second_serialized = json.dumps(second_normal_payload, ensure_ascii=False)
        assert "[deepseek-proxy persistent compaction summary]" in second_serialized
        assert "OBJECTIVE" in second_serialized
        assert "X" * 5000 not in second_serialized

        third = await client.post(
            "/v1/responses",
            json={
                "previous_response_id": second_body["id"],
                "input": "verify compacted history persisted",
            },
        )
        assert third.status_code == 200

        third_normal_payload = fake.payloads[-1]
        third_serialized = json.dumps(third_normal_payload, ensure_ascii=False)
        assert "[deepseek-proxy persistent compaction summary]" in third_serialized
        assert "X" * 5000 not in third_serialized

        report_path = Path(".debug/context_compaction_report.json")
        assert report_path.exists()
        report = json.loads(report_path.read_text(encoding="utf-8"))
        assert "version" in report


@pytest.mark.asyncio
async def test_compaction_helper_preserves_recent_tool_pair(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_PROXY_COMPACT_POLICY", "fixed")
    monkeypatch.setenv("DEEPSEEK_PROXY_COMPACT_ENABLED", "1")
    monkeypatch.setenv("DEEPSEEK_PROXY_COMPACT_TRIGGER_CHARS", "2000")
    monkeypatch.setenv("DEEPSEEK_PROXY_COMPACT_TARGET_CHARS", "6000")
    monkeypatch.setenv("DEEPSEEK_PROXY_COMPACT_KEEP_RECENT_MESSAGES", "2")
    monkeypatch.setenv("DEEPSEEK_PROXY_COMPACT_MATERIAL_CHARS", "10000")
    monkeypatch.setenv("DEEPSEEK_PROXY_COMPACT_MAX_SUMMARY_CHARS", "2000")

    fake = FakeDeepSeekClient()
    old_messages = [
        {"role": "user", "content": f"old material {i} " + ("Y" * 1000)}
        for i in range(6)
    ]
    messages = old_messages + [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call_recent",
                    "type": "function",
                    "function": {"name": "shell", "arguments": "{}"},
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "call_recent",
            "content": "recent tool result",
        },
    ]

    compacted, report = await _compact_chat_history_for_codex_like_persistence(
        deepseek_client=fake,
        messages=messages,
        request_payload={"model": "deepseek-v4-pro"},
        previous_response_id="resp_old",
    )

    assert report["compacted"] is True
    assistant_index = next(
        i
        for i, message in enumerate(compacted)
        if message.get("role") == "assistant" and message.get("tool_calls")
    )
    assert compacted[assistant_index + 1]["role"] == "tool"
    assert compacted[assistant_index + 1]["tool_call_id"] == "call_recent"
    assert "[deepseek-proxy persistent compaction summary]" in json.dumps(compacted, ensure_ascii=False)
    assert report["material"]["compaction_prompt_fingerprint"]["sha256"]
    assert len(report["material"]["compaction_prompt_fingerprint"]["sha256"]) == 64
    assert report["compaction_prompt_fingerprint"]["sha256"] == report["material"]["compaction_prompt_fingerprint"]["sha256"]
    assert report["compact_material_classifier_dry_run"]["mode"] == "dry_run"
    assert report["compact_material_classifier_dry_run"]["applied"] is False
    assert report["retained_recent_policy"]["retained_recent_message_count"] >= 2



def test_compaction_prompt_metadata_is_fingerprinted_redacted_and_classified():
    messages = [
        {"role": "system", "content": "system policy must stay protected"},
        {"role": "user", "content": "old task details should be compacted"},
        {"role": "assistant", "content": "old assistant answer should be compacted"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call_recent",
                    "type": "function",
                    "function": {"name": "shell", "arguments": "{\"cmd\": \"pytest\"}"},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "call_recent", "content": "recent tool output"},
        {"role": "user", "content": "latest user instruction"},
    ]

    prompt_messages, meta = _compaction_prompt_messages(
        messages,
        material_chars=12000,
        keep_recent_messages=2,
    )

    assert len(prompt_messages) == 2
    fingerprint = meta["compaction_prompt_fingerprint"]
    assert fingerprint["available"] is True
    assert fingerprint["fingerprint_kind"] == "sha256"
    assert len(fingerprint["sha256"]) == 64
    assert len(fingerprint["material_sha256"]) == 64
    assert len(fingerprint["recent_material_sha256"]) == 64
    assert fingerprint["raw_prompt_exposed"] is False
    assert fingerprint["raw_material_exposed"] is False

    serialized_meta = json.dumps(meta, ensure_ascii=False)
    assert "old task details should be compacted" not in serialized_meta
    assert "latest user instruction" not in serialized_meta

    retained = meta["retained_recent_policy"]
    assert retained["strategy"] == "retain_recent_tail_with_tool_result_boundary_rewind"
    assert retained["nominal_recent_start"] == 4
    assert retained["effective_recent_start"] == 3
    assert retained["adjusted_for_tool_result_boundary"] is True
    assert retained["retained_recent_message_count"] == 3

    classifier = meta["compact_material_classifier_dry_run"]
    assert classifier["mode"] == "dry_run"
    assert classifier["applied"] is False
    assert classifier["would_summarize_message_count"] == 3
    assert classifier["would_keep_recent_verbatim_message_count"] == 3
    assert classifier["sections"]["leading_system_developer_verbatim_after_compaction"]["message_count"] == 1



@pytest.mark.asyncio
async def test_adaptive_compaction_reports_policy_decision(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_PROXY_COMPACT_POLICY", "adaptive")
    monkeypatch.setenv("DEEPSEEK_PROXY_COMPACT_ENABLED", "1")
    monkeypatch.setenv("DEEPSEEK_PROXY_MAX_CONTEXT_CHARS", "10000")
    monkeypatch.setenv("DEEPSEEK_PROXY_COMPACT_MIN_TARGET_CHARS", "2000")
    monkeypatch.setenv("DEEPSEEK_PROXY_COMPACT_MAX_TARGET_CHARS", "8000")
    monkeypatch.setenv("DEEPSEEK_PROXY_COMPACT_RESERVE_BEFORE_MIN_CHARS", "1000")
    monkeypatch.setenv("DEEPSEEK_PROXY_COMPACT_RESERVE_BEFORE_MAX_CHARS", "2000")
    monkeypatch.setenv("DEEPSEEK_PROXY_COMPACT_RESERVE_AFTER_MIN_CHARS", "1000")
    monkeypatch.setenv("DEEPSEEK_PROXY_COMPACT_RESERVE_AFTER_MAX_CHARS", "3000")
    monkeypatch.setenv("DEEPSEEK_PROXY_COMPACT_KEEP_RECENT_MESSAGES", "2")
    monkeypatch.setenv("DEEPSEEK_PROXY_COMPACT_RECENT_GROWTH_MESSAGES", "2")
    monkeypatch.setenv("DEEPSEEK_PROXY_COMPACT_EXPECTED_GROWTH_TURNS", "3")
    monkeypatch.setenv("DEEPSEEK_PROXY_COMPACT_MIN_NEW_CHARS", "1000")
    monkeypatch.setenv("DEEPSEEK_PROXY_COMPACT_MIN_TURNS", "2")
    monkeypatch.setenv("DEEPSEEK_PROXY_COMPACT_MATERIAL_CHARS", "12000")
    monkeypatch.setenv("DEEPSEEK_PROXY_COMPACT_MAX_SUMMARY_CHARS", "3000")
    monkeypatch.delenv("DEEPSEEK_PROXY_COMPACT_TRIGGER_CHARS", raising=False)
    monkeypatch.delenv("DEEPSEEK_PROXY_COMPACT_TARGET_CHARS", raising=False)

    fake = FakeDeepSeekClient()
    messages = [
        {"role": "user", "content": f"adaptive old material {i} " + ("A" * 2500)}
        for i in range(7)
    ]

    compacted, report = await _compact_chat_history_for_codex_like_persistence(
        deepseek_client=fake,
        messages=messages,
        request_payload={"model": "deepseek-v4-pro"},
        previous_response_id="resp_adaptive",
    )

    assert report["policy"] == "adaptive"
    assert report["compacted"] is True
    assert report["reason"] in {"adaptive_triggered", "adaptive_emergency_triggered"}
    assert report["effective_trigger_chars"] > 0
    assert 2000 <= report["effective_target_chars"] <= 8000
    assert report["policy_decision"]["growth"]["recent_growth_chars_per_turn"] > 0
    assert "[deepseek-proxy persistent compaction summary]" in json.dumps(compacted, ensure_ascii=False)


@pytest.mark.asyncio
async def test_adaptive_compaction_cooldown_skips_recently_compacted_history(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_PROXY_COMPACT_POLICY", "adaptive")
    monkeypatch.setenv("DEEPSEEK_PROXY_COMPACT_ENABLED", "1")
    monkeypatch.setenv("DEEPSEEK_PROXY_MAX_CONTEXT_CHARS", "20000")
    monkeypatch.setenv("DEEPSEEK_PROXY_COMPACT_RESERVE_BEFORE_MIN_CHARS", "15000")
    monkeypatch.setenv("DEEPSEEK_PROXY_COMPACT_RESERVE_BEFORE_MAX_CHARS", "15000")
    monkeypatch.setenv("DEEPSEEK_PROXY_COMPACT_MIN_NEW_CHARS", "20000")
    monkeypatch.setenv("DEEPSEEK_PROXY_COMPACT_MIN_TURNS", "4")
    monkeypatch.setenv("DEEPSEEK_PROXY_COMPACT_KEEP_RECENT_MESSAGES", "2")
    monkeypatch.delenv("DEEPSEEK_PROXY_COMPACT_TRIGGER_CHARS", raising=False)

    fake = FakeDeepSeekClient()
    messages = [
        {
            "role": "user",
            "content": "[deepseek-proxy persistent compaction summary]\nprevious summary " + ("S" * 9000),
        },
        {"role": "user", "content": "small follow-up 1 " + ("B" * 500)},
        {"role": "assistant", "content": "small follow-up 2 " + ("C" * 500)},
        {"role": "user", "content": "small follow-up 3 " + ("D" * 500)},
    ]

    compacted, report = await _compact_chat_history_for_codex_like_persistence(
        deepseek_client=fake,
        messages=messages,
        request_payload={"model": "deepseek-v4-pro"},
        previous_response_id="resp_recent_compacted",
    )

    assert compacted == messages
    assert report["compacted"] is False
    assert report["reason"] == "adaptive_cooldown"
    assert fake.compaction_calls == 0
