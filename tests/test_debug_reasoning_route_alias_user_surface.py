from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse


def _fake_response(body: dict[str, object]):
    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps(body).encode("utf-8")

    return FakeResponse()


def test_debug_latest_reasoning_alias_uses_reasoning_runtime_port(monkeypatch, capsys) -> None:
    import codexchange_proxy.cli as cli

    calls: list[tuple[str, float]] = []

    def fake_urlopen(url, timeout=0):
        calls.append((url, timeout))
        return _fake_response({"status": "ok", "events": []})

    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)

    assert cli.main(["debug", "latest", "--reasoning", "--limit", "7", "--timeout", "0.5"]) == 0
    data = json.loads(capsys.readouterr().out)

    assert data["proxy_url"] == "http://127.0.0.1:8001"
    assert data["debug_command"] == "latest"
    parsed = urlparse(calls[0][0])
    assert parsed.netloc == "127.0.0.1:8001"
    assert parsed.path == "/v1/proxy/debug/latest"
    assert parse_qs(parsed.query) == {"limit": ["7"]}
    assert calls[0][1] == 0.5


def test_debug_behavioral_reasoning_alias_uses_reasoning_runtime_port(monkeypatch, capsys) -> None:
    import codexchange_proxy.cli as cli

    calls: list[tuple[str, float]] = []

    def fake_urlopen(url, timeout=0):
        calls.append((url, timeout))
        return _fake_response({"status": "ok", "long_session": {"metrics": {}}})

    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)

    assert cli.main(["debug", "behavioral", "--reasoning", "--limit", "25", "--timeout", "0.5"]) == 0
    data = json.loads(capsys.readouterr().out)

    assert data["proxy_url"] == "http://127.0.0.1:8001"
    assert data["debug_command"] == "behavioral"
    parsed = urlparse(calls[0][0])
    assert parsed.netloc == "127.0.0.1:8001"
    assert parsed.path == "/v1/proxy/debug/long-session"
    assert parse_qs(parsed.query) == {"limit": ["25"], "mode": ["aggregate"]}
    assert calls[0][1] == 0.5


def test_real_long_session_smoke_prefers_reasoning_alias_in_user_surface() -> None:
    script = Path("scripts/real-long-session-behavioral-smoke.sh").read_text(encoding="utf-8")

    assert "local CodeXchange reasoning runtime" in script
    assert "local thinking proxy" not in script
    assert "debug behavioral --reasoning" in script
    assert "debug behavioral --thinking" not in script
