import importlib
import json
from pathlib import Path

proxy_app = importlib.import_module("deepseek_responses_proxy.app")


def test_debug_trace_disabled_by_default(monkeypatch, tmp_path):
    monkeypatch.delenv("DEEPSEEK_PROXY_DEBUG_TRACE", raising=False)
    monkeypatch.setenv("DEEPSEEK_PROXY_DEBUG_DIR", str(tmp_path / "traces"))

    proxy_app._debug_trace_event("resp_disabled", "request_received", payload={"input": "hello"})

    assert not (tmp_path / "traces").exists()
    status = proxy_app._debug_trace_status()
    assert status["enabled"] is False
    assert status["trace_count"] == 0


def test_debug_trace_none_mode_summarizes_without_raw_content(monkeypatch, tmp_path):
    trace_dir = tmp_path / "traces"
    monkeypatch.setenv("DEEPSEEK_PROXY_DEBUG_TRACE", "1")
    monkeypatch.setenv("DEEPSEEK_PROXY_DEBUG_DIR", str(trace_dir))
    monkeypatch.setenv("DEEPSEEK_PROXY_DEBUG_CONTENT", "none")

    proxy_app._debug_trace_event(
        "resp_unit",
        "request_received",
        payload={"input": "secret-ish content should not appear verbatim"},
    )

    trace_file = trace_dir / "trace-resp_unit.jsonl"
    assert trace_file.exists()
    raw = trace_file.read_text(encoding="utf-8")
    assert "secret-ish content" not in raw

    event = json.loads(raw.splitlines()[0])
    assert event["event"] == "request_received"
    assert event["response_id"] == "resp_unit"
    assert event["version"] == proxy_app.PROXY_VERSION
    assert event["payload"]["type"] == "dict"
    assert event["payload"]["chars"] > 0


def test_debug_trace_preview_mode_redacts_secret_like_keys(monkeypatch, tmp_path):
    trace_dir = tmp_path / "traces"
    monkeypatch.setenv("DEEPSEEK_PROXY_DEBUG_TRACE", "1")
    monkeypatch.setenv("DEEPSEEK_PROXY_DEBUG_DIR", str(trace_dir))
    monkeypatch.setenv("DEEPSEEK_PROXY_DEBUG_CONTENT", "preview")

    proxy_app._debug_trace_event(
        "resp_preview",
        "upstream_call_started",
        headers={"Authorization": "Bearer should-not-leak"},
        payload={"messages": [{"role": "user", "content": "hello"}]},
    )

    raw = (trace_dir / "trace-resp_preview.jsonl").read_text(encoding="utf-8")
    assert "should-not-leak" not in raw
    assert "Bearer should-not-leak" not in raw

    event = json.loads(raw.splitlines()[0])
    assert event["headers"]["Authorization"] == "[redacted]"
    assert event["payload"]["messages"]["label"] == "messages"


def test_debug_trace_latest_returns_recent_events(monkeypatch, tmp_path):
    trace_dir = tmp_path / "traces"
    monkeypatch.setenv("DEEPSEEK_PROXY_DEBUG_TRACE", "1")
    monkeypatch.setenv("DEEPSEEK_PROXY_DEBUG_DIR", str(trace_dir))
    monkeypatch.setenv("DEEPSEEK_PROXY_DEBUG_CONTENT", "none")

    proxy_app._debug_trace_event("resp_latest", "request_received", payload={"input": "a"})
    proxy_app._debug_trace_event("resp_latest", "response_envelope_built", output_item_count=1)

    latest = proxy_app._debug_trace_latest(limit=10)
    assert latest["status"] == "ok"
    assert latest["trace_path"].endswith("trace-resp_latest.jsonl")
    assert [event["event"] for event in latest["events"]] == [
        "request_received",
        "response_envelope_built",
    ]

    status = proxy_app._debug_trace_status()
    assert status["enabled"] is True
    assert status["trace_count"] == 1
    assert status["latest"]["response_id"] == "resp_latest"


def test_debug_trace_sanitizes_response_id(monkeypatch, tmp_path):
    trace_dir = tmp_path / "traces"
    monkeypatch.setenv("DEEPSEEK_PROXY_DEBUG_TRACE", "1")
    monkeypatch.setenv("DEEPSEEK_PROXY_DEBUG_DIR", str(trace_dir))
    monkeypatch.setenv("DEEPSEEK_PROXY_DEBUG_CONTENT", "none")

    proxy_app._debug_trace_event("resp/unsafe value", "request_received")

    files = sorted(path.name for path in trace_dir.glob("trace-*.jsonl"))
    assert files == ["trace-resp_unsafe_value.jsonl"]
