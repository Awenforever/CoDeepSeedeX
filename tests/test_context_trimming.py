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
