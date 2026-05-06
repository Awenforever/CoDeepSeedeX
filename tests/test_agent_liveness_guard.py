import json
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from deepseek_responses_proxy.app import (
    _assistant_message_needs_liveness_guard,
    _run_chat_with_tool_bridge,
    create_app,
)


class FakeDeepSeekClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.payloads = []

    async def chat_completions(self, payload):
        self.payloads.append(payload)
        if not self.responses:
            raise AssertionError("unexpected extra chat_completions call")
        return self.responses.pop(0)


def _response(message):
    return {
        "choices": [{"message": message}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }


def test_liveness_intent_detector_only_matches_unfinished_tool_intent():
    assert _assistant_message_needs_liveness_guard(
        {
            "role": "assistant",
            "content": "uiautomator2 connected successfully. Now let me try more — wake the screen, dump UI, and test a real action:",
        },
        tools_available=True,
    )

    assert not _assistant_message_needs_liveness_guard(
        {"role": "assistant", "content": "Done. The repository is clean and all tests passed."},
        tools_available=True,
    )

    assert not _assistant_message_needs_liveness_guard(
        {"role": "assistant", "content": "Now let me summarize the result for you."},
        tools_available=True,
    )

    assert not _assistant_message_needs_liveness_guard(
        {"role": "assistant", "content": "Now let me run tests:", "tool_calls": [{"id": "x"}]},
        tools_available=True,
    )

    assert not _assistant_message_needs_liveness_guard(
        {"role": "assistant", "content": "Now let me run tests:"},
        tools_available=False,
    )


@pytest.mark.asyncio
async def test_liveness_guard_reasks_and_surfaces_local_codex_tool_call(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DEEPSEEK_PROXY_AGENT_LIVENESS_GUARD", "1")
    monkeypatch.setenv("DEEPSEEK_PROXY_AGENT_LIVENESS_MAX_RETRIES", "1")

    fake = FakeDeepSeekClient(
        [
            _response(
                {
                    "role": "assistant",
                    "content": "uiautomator2 connected successfully. Now let me try more — wake the screen, dump UI, and test a real action:",
                }
            ),
            _response(
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call_shell",
                            "type": "function",
                            "function": {
                                "name": "shell",
                                "arguments": json.dumps({"cmd": "echo ok"}),
                            },
                        }
                    ],
                }
            ),
        ]
    )

    deepseek_response, history = await _run_chat_with_tool_bridge(
        deepseek_client=fake,
        chat_payload={
            "model": "deepseek-v4-pro",
            "messages": [{"role": "user", "content": "test device"}],
            "tools": [{"type": "function", "function": {"name": "shell", "parameters": {}}}],
        },
        messages_for_deepseek=[{"role": "user", "content": "test device"}],
        history_messages=[{"role": "user", "content": "test device"}],
        model="deepseek-v4-pro",
        deepseek_tools=[{"type": "function", "function": {"name": "shell", "parameters": {}}}],
        reasoning_effort=None,
        request_payload={},
    )

    assert len(fake.payloads) == 2
    assert "Codex agent-loop protocol correction" in json.dumps(fake.payloads[1], ensure_ascii=False)
    assert deepseek_response["choices"][0]["message"]["tool_calls"][0]["function"]["name"] == "shell"
    assert history == [{"role": "user", "content": "test device"}]

    report = json.loads(Path(".debug/agent_liveness_guard_report.json").read_text(encoding="utf-8"))
    assert report["triggered"] is True
    assert report["retry_count"] == 1
    assert report["final_has_tool_calls"] is True
    assert report["final_tool_call_count"] == 1


@pytest.mark.asyncio
async def test_liveness_guard_does_not_reask_final_answer(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DEEPSEEK_PROXY_AGENT_LIVENESS_GUARD", "1")

    fake = FakeDeepSeekClient(
        [
            _response({"role": "assistant", "content": "Done. All requested checks are complete."}),
        ]
    )

    deepseek_response, _history = await _run_chat_with_tool_bridge(
        deepseek_client=fake,
        chat_payload={
            "model": "deepseek-v4-pro",
            "messages": [{"role": "user", "content": "summarize"}],
            "tools": [{"type": "function", "function": {"name": "shell", "parameters": {}}}],
        },
        messages_for_deepseek=[{"role": "user", "content": "summarize"}],
        history_messages=[{"role": "user", "content": "summarize"}],
        model="deepseek-v4-pro",
        deepseek_tools=[{"type": "function", "function": {"name": "shell", "parameters": {}}}],
        reasoning_effort=None,
        request_payload={},
    )

    assert len(fake.payloads) == 1
    assert deepseek_response["choices"][0]["message"]["content"].startswith("Done")

    report = json.loads(Path(".debug/agent_liveness_guard_report.json").read_text(encoding="utf-8"))
    assert report["triggered"] is False
    assert report["retry_count"] == 0
    assert report["final_has_tool_calls"] is False


@pytest.mark.asyncio
async def test_proxy_status_reports_agent_liveness(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DEEPSEEK_PROXY_AGENT_LIVENESS_GUARD", "1")
    monkeypatch.setenv("DEEPSEEK_PROXY_AGENT_LIVENESS_MAX_RETRIES", "2")

    debug_dir = Path(".debug")
    debug_dir.mkdir()
    (debug_dir / "agent_liveness_guard_report.json").write_text(
        json.dumps(
            {
                "version": "test-version",
                "enabled": True,
                "triggered": True,
                "retry_count": 1,
                "max_retries": 2,
                "tools_available": True,
                "round_index": 1,
                "guard_reason": "assistant_narrated_tool_intent_without_tool_call",
                "final_has_tool_calls": True,
                "final_tool_call_count": 1,
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

    assert data["version"].startswith("v2.3a6-")
    assert data["agent_liveness"]["config"]["enabled"] is True
    assert data["agent_liveness"]["config"]["max_retries"] == 2
    assert data["agent_liveness"]["last_report"]["exists"] is True
    assert data["agent_liveness"]["last_report"]["triggered"] is True
    assert data["agent_liveness"]["last_report"]["retry_count"] == 1
    assert data["agent_liveness"]["last_report"]["final_has_tool_calls"] is True
