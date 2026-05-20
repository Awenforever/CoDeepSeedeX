from __future__ import annotations

import importlib
import json

import pytest

app_module = importlib.import_module("deepseek_responses_proxy.app")


class _FakeDeepSeekResponse:
    status_code = 200
    text = "{}"

    def json(self) -> dict:
        return {
            "id": "chatcmpl-test",
            "choices": [{"message": {"role": "assistant", "content": "ok"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12},
        }


class _FakeAsyncClient:
    def __init__(self) -> None:
        self.posts: list[dict] = []

    async def post(self, url: str, json: dict | None = None, headers: dict | None = None):
        self.posts.append({"url": url, "json": json, "headers": headers})
        return _FakeDeepSeekResponse()


@pytest.mark.asyncio
async def test_append_only_payload_trace_records_each_upstream_call(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DEEPSEEK_PROXY_PAYLOAD_TRACE_DIR", str(tmp_path))
    fake_http = _FakeAsyncClient()
    client = app_module.DeepSeekClient(
        api_key="secret-test-key",
        base_url="https://example.test",
        http_client=fake_http,
    )

    payload = {
        "model": "deepseek-test",
        "messages": [{"role": "user", "content": "hello trace"}],
        "tools": [{"type": "function", "function": {"name": "demo_tool", "parameters": {"type": "object"}}}],
        "stream": False,
    }

    await client.chat_completions(payload, trace_metadata={"purpose": "primary", "request_id": "req-1"})
    await client.chat_completions(payload, trace_metadata={"purpose": "liveness_judge", "request_id": "req-2"})

    trace_files = sorted(tmp_path.glob("*.json"))
    assert len(trace_files) == 2

    first = json.loads(trace_files[0].read_text(encoding="utf-8"))
    second = json.loads(trace_files[1].read_text(encoding="utf-8"))

    assert first["schema_version"] == 1
    assert first["source"] == "DeepSeekClient.chat_completions"
    assert first["metadata"]["purpose"] == "primary"
    assert first["metadata"]["request_id"] == "req-1"
    assert first["payload"]["messages"][0]["content"] == "hello trace"
    assert first["summary"]["message_count"] == 1
    assert first["summary"]["tools_count"] == 1
    assert first["payload_sha256"] != ""
    assert "Authorization" not in json.dumps(first, ensure_ascii=False)

    assert second["metadata"]["purpose"] == "liveness_judge"
    assert second["metadata"]["request_id"] == "req-2"


@pytest.mark.asyncio
async def test_payload_trace_ignores_non_tmp_directory(tmp_path, monkeypatch) -> None:
    forbidden = tmp_path.parent.parent / "not-tmp-payload-trace"
    if str(forbidden).startswith("/tmp"):
        pytest.skip("test requires a non-/tmp path")

    monkeypatch.setenv("DEEPSEEK_PROXY_PAYLOAD_TRACE_DIR", str(forbidden))
    fake_http = _FakeAsyncClient()
    client = app_module.DeepSeekClient(
        api_key="secret-test-key",
        base_url="https://example.test",
        http_client=fake_http,
    )

    await client.chat_completions({"model": "deepseek-test", "messages": [{"role": "user", "content": "hello"}]})

    assert not forbidden.exists()
