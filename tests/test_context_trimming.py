import json
from pathlib import Path

import pytest

from deepseek_responses_proxy.app import (
    DeepSeekClient,
    _compact_deepseek_payload_context,
)


def test_long_tool_output_is_truncated_without_breaking_tool_call_pair(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_PROXY_MAX_CONTEXT_CHARS", "100000")
    monkeypatch.setenv("DEEPSEEK_PROXY_MAX_TOOL_OUTPUT_CHARS", "240")
    monkeypatch.setenv("DEEPSEEK_PROXY_KEEP_RECENT_MESSAGES", "8")

    payload = {
        "model": "deepseek-v4-pro",
        "messages": [
            {"role": "user", "content": "run command"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "shell", "arguments": "{}"},
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "call_1",
                "content": "A" * 5000,
            },
            {"role": "user", "content": "continue"},
        ],
        "stream": False,
    }

    trimmed, report = _compact_deepseek_payload_context(payload)

    assert report["trimmed"] is True
    assert trimmed["messages"][1]["role"] == "assistant"
    assert trimmed["messages"][1]["tool_calls"][0]["id"] == "call_1"
    assert trimmed["messages"][2]["role"] == "tool"
    assert trimmed["messages"][2]["tool_call_id"] == "call_1"
    assert len(trimmed["messages"][2]["content"]) <= 240
    assert "context trimmed" in trimmed["messages"][2]["content"]


def test_compaction_keeps_recent_tool_call_protocol_pair(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_PROXY_MAX_CONTEXT_CHARS", "2500")
    monkeypatch.setenv("DEEPSEEK_PROXY_MAX_TOOL_OUTPUT_CHARS", "300")
    monkeypatch.setenv("DEEPSEEK_PROXY_KEEP_RECENT_MESSAGES", "2")

    old_messages = [
        {"role": "user", "content": f"old message {i}: " + ("X" * 1000)}
        for i in range(8)
    ]
    payload = {
        "model": "deepseek-v4-pro",
        "messages": old_messages
        + [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_recent",
                        "type": "function",
                        "function": {"name": "proxy_echo", "arguments": json.dumps({"x": 1})},
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "call_recent",
                "content": "recent tool output",
            },
            {"role": "user", "content": "final request"},
        ],
        "stream": False,
    }

    trimmed, report = _compact_deepseek_payload_context(payload)

    assert report["trimmed"] is True
    assert report["after_chars"] <= report["max_context_chars"]

    messages = trimmed["messages"]
    assistant_index = next(
        i
        for i, message in enumerate(messages)
        if message.get("role") == "assistant" and message.get("tool_calls")
    )
    assert messages[assistant_index + 1]["role"] == "tool"
    assert messages[assistant_index + 1]["tool_call_id"] == "call_recent"


@pytest.mark.asyncio
async def test_deepseek_client_writes_context_trimming_report(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DEEPSEEK_PROXY_MAX_CONTEXT_CHARS", "100000")
    monkeypatch.setenv("DEEPSEEK_PROXY_MAX_TOOL_OUTPUT_CHARS", "200")
    monkeypatch.setenv("DEEPSEEK_PROXY_KEEP_RECENT_MESSAGES", "8")

    class FakeResponse:
        status_code = 200
        text = '{"ok": true}'

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [{"message": {"role": "assistant", "content": "ok"}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            }

    class FakeHTTPClient:
        def __init__(self):
            self.payloads = []

        async def post(self, url, headers=None, json=None):
            self.payloads.append(json)
            return FakeResponse()

    fake_http = FakeHTTPClient()
    client = DeepSeekClient(api_key="", base_url="http://deepseek.test", http_client=fake_http)

    payload = {
        "model": "deepseek-v4-pro",
        "messages": [
            {"role": "tool", "tool_call_id": "call_1", "content": "Z" * 4000},
        ],
        "stream": False,
    }

    response = await client.chat_completions(payload)

    assert response["choices"][0]["message"]["content"] == "ok"
    assert fake_http.payloads
    assert len(fake_http.payloads[0]["messages"][0]["content"]) <= 200

    report_path = Path(".debug/context_trimming_report.json")
    assert report_path.exists()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["trimmed"] is True
    assert report["max_tool_output_chars"] == 200


def test_context_trim_token_first_dry_run_enumerates_types_and_protects_first_image(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_PROXY_MAX_CONTEXT_CHARS", "100000")
    monkeypatch.setenv("DEEPSEEK_PROXY_MAX_TOOL_OUTPUT_CHARS", "240")
    monkeypatch.setenv("DEEPSEEK_PROXY_KEEP_RECENT_MESSAGES", "1")
    monkeypatch.setenv("DEEPSEEK_PROXY_TRIM_MAX_CONTEXT_TOKENS", "10")

    first_image = "data:image/png;base64," + ("A" * 5000)
    payload = {
        "model": "deepseek-v4-flash",
        "messages": [
            {"role": "user", "content": first_image},
            {"role": "user", "content": "old log " + ("B" * 5000)},
            {"role": "assistant", "content": "ok"},
        ],
        "stream": False,
    }

    trimmed, report = _compact_deepseek_payload_context(payload)

    assert report["token_first_trim_dry_run"]["available"] is True
    assert report["token_first_trim_dry_run"]["unit"] == "tokens"
    assert report["token_first_trim_dry_run"]["mode"] == "runtime_plan"
    assert report["token_first_trim_dry_run"]["would_trim"] is True
    assert report["token_first_trim_dry_run"]["runtime_applied"] is True
    assert report["token_first_runtime_trim"]["applied"] is True
    assert report["token_first_runtime_trim"]["unit"] == "tokens"
    assert report["token_first_runtime_trim"]["before_tokens"] > report["token_first_runtime_trim"]["after_tokens"]
    assert report["token_first_trim_dry_run"]["type_counts"]["image_payload"] == 1
    assert report["image_first_protection"]["first_image_index"] == 0
    assert report["image_first_protection"]["protected"] is True
    assert 0 in report["protected_message_indexes"]

    assert trimmed["messages"][0]["content"] == first_image
    serialized_report = json.dumps(report, ensure_ascii=False)
    assert first_image not in serialized_report
    assert '"raw_content_exposed": true' not in serialized_report.lower()



def test_context_trim_protects_latest_static_blocks_without_raw_content(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_PROXY_MAX_CONTEXT_CHARS", "100000")
    monkeypatch.setenv("DEEPSEEK_PROXY_MAX_TOOL_OUTPUT_CHARS", "200")
    monkeypatch.setenv("DEEPSEEK_PROXY_KEEP_RECENT_MESSAGES", "1")

    old_agents = "AGENTS.md old copy " + ("A" * 4000)
    latest_agents = "AGENTS.md current copy " + ("B" * 4000)
    environment = "<environment_context> current env " + ("C" * 4000)
    payload = {
        "model": "deepseek-v4-flash",
        "messages": [
            {"role": "user", "content": old_agents},
            {"role": "user", "content": latest_agents},
            {"role": "user", "content": environment},
            {"role": "user", "content": "final request"},
        ],
    }

    trimmed, report = _compact_deepseek_payload_context(payload)

    static = report["protected_static_blocks"]
    assert static["available"] is True
    assert static["latest_static_indexes"]["static_agents"] == 1
    assert static["latest_static_indexes"]["static_environment"] == 2
    assert 1 in static["protected_static_message_indexes"]
    assert 2 in static["protected_static_message_indexes"]
    assert "context trimmed" in trimmed["messages"][0]["content"]
    assert trimmed["messages"][1]["content"] == latest_agents
    assert trimmed["messages"][2]["content"] == environment

    serialized_report = json.dumps(report, ensure_ascii=False)
    assert latest_agents not in serialized_report
    assert environment not in serialized_report
    assert '"raw_content_exposed": true' not in serialized_report.lower()


def test_type_aware_trim_applies_low_risk_limits_without_leaking_raw_content(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_PROXY_MAX_CONTEXT_CHARS", "100000")
    monkeypatch.setenv("DEEPSEEK_PROXY_MAX_TOOL_OUTPUT_CHARS", "60000")
    monkeypatch.setenv("DEEPSEEK_PROXY_KEEP_RECENT_MESSAGES", "1")
    monkeypatch.setenv("DEEPSEEK_PROXY_TRIM_LOG_CHARS", "1200")
    monkeypatch.setenv("DEEPSEEK_PROXY_TRIM_TRACEBACK_CHARS", "1500")
    monkeypatch.setenv("DEEPSEEK_PROXY_TRIM_TOOL_CALL_ARGUMENTS_CHARS", "900")

    raw_log = "stdout\nrun_ok=1\n" + ("L" * 5000)
    raw_traceback = "Traceback (most recent call last):\n" + ("T" * 5000)
    raw_arguments = json.dumps({"cmd": "python", "payload": "A" * 5000}, ensure_ascii=False)
    payload = {
        "model": "deepseek-v4-flash",
        "messages": [
            {"role": "user", "content": raw_log},
            {"role": "assistant", "content": "calling tool", "tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "shell", "arguments": raw_arguments}}]},
            {"role": "user", "content": raw_traceback},
            {"role": "user", "content": "final request"},
        ],
    }

    trimmed, report = _compact_deepseek_payload_context(payload)

    assert report["trimmed"] is True
    assert report["type_aware_trim"]["enabled"] is True
    assert report["type_aware_trim"]["mode"] == "enabled"
    assert report["type_aware_trim"]["applied"] is True
    assert report["type_aware_trim"]["applied_by_type"]["log"]["trimmed_field_count"] == 1
    assert report["type_aware_trim"]["applied_by_type"]["tool_call_arguments"]["trimmed_field_count"] == 1
    assert report["type_aware_trim"]["applied_by_type"]["traceback"]["trimmed_field_count"] == 1
    assert report["type_aware_trim"]["limits"]["log"] == 1200
    assert report["type_aware_trim"]["limits"]["traceback"] == 1500

    assert "context trimmed" in trimmed["messages"][0]["content"]
    assert "context trimmed" in trimmed["messages"][1]["tool_calls"][0]["function"]["arguments"]
    assert "context trimmed" in trimmed["messages"][2]["content"]

    serialized_report = json.dumps(report, ensure_ascii=False)
    assert raw_log not in serialized_report
    assert raw_traceback not in serialized_report
    assert raw_arguments not in serialized_report
    assert '"raw_content_exposed": true' not in serialized_report.lower()


def test_type_aware_trim_can_be_disabled_without_disabling_dry_run(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_PROXY_TYPE_AWARE_TRIM", "0")
    monkeypatch.setenv("DEEPSEEK_PROXY_MAX_CONTEXT_CHARS", "100000")
    monkeypatch.setenv("DEEPSEEK_PROXY_MAX_TOOL_OUTPUT_CHARS", "60000")
    monkeypatch.setenv("DEEPSEEK_PROXY_KEEP_RECENT_MESSAGES", "1")
    monkeypatch.setenv("DEEPSEEK_PROXY_TRIM_LOG_CHARS", "1200")

    raw_log = "stdout\nrun_ok=1\n" + ("L" * 5000)
    payload = {
        "model": "deepseek-v4-flash",
        "messages": [
            {"role": "user", "content": raw_log},
            {"role": "user", "content": "final request"},
        ],
    }

    trimmed, report = _compact_deepseek_payload_context(payload)

    assert report["token_first_trim_dry_run"]["available"] is True
    assert report["type_aware_trim"]["enabled"] is False
    assert report["type_aware_trim"]["applied"] is False
    assert trimmed["messages"][0]["content"] == raw_log


def test_image_semantic_envelope_transforms_non_first_image_without_raw_leak(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_PROXY_MAX_CONTEXT_CHARS", "100000")
    monkeypatch.setenv("DEEPSEEK_PROXY_MAX_TOOL_OUTPUT_CHARS", "60000")
    monkeypatch.setenv("DEEPSEEK_PROXY_KEEP_RECENT_MESSAGES", "1")

    first_image = "data:image/png;base64," + ("A" * 1600)
    second_image = "data:image/png;base64," + ("B" * 2200)
    payload = {
        "model": "deepseek-v4-flash",
        "messages": [
            {"role": "user", "content": first_image},
            {"role": "user", "content": second_image},
            {"role": "user", "content": "final request"},
        ],
    }

    trimmed, report = _compact_deepseek_payload_context(payload)

    envelope = report["image_semantic_envelope"]
    assert envelope["available"] is True
    assert envelope["enabled"] is True
    assert envelope["transform_enabled"] is True
    assert envelope["applied"] is True
    assert envelope["image_message_count"] == 2
    assert envelope["protected_count"] == 1
    assert envelope["transformed_count"] == 1
    assert envelope["items"][0]["protected"] is True
    assert envelope["items"][0]["raw_image_content_exposed"] is False
    assert envelope["items"][0]["semantic_summary_unavailable"] is True
    assert envelope["items"][1]["transformed"] is True
    assert envelope["items"][1]["semantic_summary_available"] is False
    assert envelope["items"][1]["semantic_summary_unavailable_reason"] == "no_vision_caption_or_ocr_available"
    assert envelope["semantic_summary_available"] is False
    assert envelope["semantic_summary_unavailable"] is True

    assert trimmed["messages"][0]["content"] == first_image
    assert "[deepseek-proxy image semantic envelope]" in trimmed["messages"][1]["content"]
    assert "semantic_summary_unavailable: true" in trimmed["messages"][1]["content"]
    assert "semantic_summary_unavailable_reason: no_vision_caption_or_ocr_available" in trimmed["messages"][1]["content"]
    assert "raw_image_content_exposed: false" in trimmed["messages"][1]["content"]

    serialized_report = json.dumps(report, ensure_ascii=False)
    serialized_trimmed = json.dumps(trimmed, ensure_ascii=False)
    assert second_image not in serialized_report
    assert second_image not in serialized_trimmed
    assert '"raw_image_content_exposed": true' not in serialized_report.lower()


def test_image_semantic_envelope_transform_can_be_disabled(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_PROXY_IMAGE_SEMANTIC_ENVELOPE_TRANSFORM", "0")
    monkeypatch.setenv("DEEPSEEK_PROXY_MAX_CONTEXT_CHARS", "100000")
    monkeypatch.setenv("DEEPSEEK_PROXY_MAX_TOOL_OUTPUT_CHARS", "60000")
    monkeypatch.setenv("DEEPSEEK_PROXY_KEEP_RECENT_MESSAGES", "1")

    first_image = "data:image/png;base64," + ("A" * 1600)
    second_image = "data:image/png;base64," + ("B" * 2200)
    payload = {
        "model": "deepseek-v4-flash",
        "messages": [
            {"role": "user", "content": first_image},
            {"role": "user", "content": second_image},
            {"role": "user", "content": "final request"},
        ],
    }

    trimmed, report = _compact_deepseek_payload_context(payload)

    assert report["image_semantic_envelope"]["available"] is True
    assert report["image_semantic_envelope"]["transform_enabled"] is False
    assert report["image_semantic_envelope"]["applied"] is False
    assert report["image_semantic_envelope"]["transformed_count"] == 0
    assert trimmed["messages"][1]["content"] == second_image
