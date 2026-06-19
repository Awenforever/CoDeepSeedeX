from __future__ import annotations

import contextlib
import io

from codexchange_proxy import cli


def _capture_main(argv: list[str]) -> tuple[int, str]:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        try:
            rc = cli.main(argv)
        except SystemExit as exc:
            rc = int(exc.code or 0)
    return rc, buf.getvalue()


def _squish(text: str) -> str:
    return " ".join(text.split())


def test_runtime_commands_expose_reasoning_flag_as_primary_alias() -> None:
    for command in ["start", "stop", "status", "doctor", "logs", "usage"]:
        rc, output = _capture_main([command, "--help"])
        assert rc == 0
        normalized = _squish(output)
        assert "--reasoning" in output
        assert "--thinking" in output
        assert "legacy alias" in normalized
        assert "thinking proxy" not in normalized


def test_doctor_tool_routing_exposes_reasoning_flag_alias() -> None:
    rc, output = _capture_main(["doctor", "tool-routing", "--help"])

    assert rc == 0
    normalized = _squish(output)
    assert "--reasoning" in output
    assert "--thinking" in output
    assert "legacy alias" in normalized
    assert "thinking proxy" not in normalized


def test_start_stop_status_reasoning_flag_routes_to_reasoning_runtime(monkeypatch) -> None:
    calls: list[tuple[str, bool, int | None]] = []
    status_base_url_calls: list[tuple[bool, int | None]] = []
    status_http_calls: list[tuple[str, float]] = []

    def fake_start(args):
        calls.append(("start", bool(args.thinking), getattr(args, "port", None)))
        return 0

    def fake_stop(args):
        calls.append(("stop", bool(args.thinking), getattr(args, "port", None)))
        return 0

    def fake_base_url(*, thinking=False, port=None):
        status_base_url_calls.append((bool(thinking), port))
        return "http://127.0.0.1:8001" if thinking else "http://127.0.0.1:8000"

    def fake_http_json(url, *, timeout=10.0):
        status_http_calls.append((url, timeout))
        return 200, {"status": "ok"}, None

    monkeypatch.setattr(cli, "_start_proxy", fake_start)
    monkeypatch.setattr(cli, "_stop_proxy", fake_stop)
    monkeypatch.setattr(cli, "_base_url", fake_base_url)
    monkeypatch.setattr(cli, "_http_json", fake_http_json)

    assert cli.main(["start", "--reasoning"]) == 0
    assert cli.main(["stop", "--reasoning"]) == 0
    assert cli.main(["status", "--reasoning", "--port", "8001", "--timeout", "1"]) == 0

    assert calls == [("start", True, None), ("stop", True, None)]
    assert status_base_url_calls == [(True, 8001)]
    assert status_http_calls[-1][0].startswith("http://127.0.0.1:8001/")
    assert status_http_calls[-1][1] == 1.0


def test_logs_and_usage_reasoning_flag_routes_to_reasoning_runtime(monkeypatch, tmp_path, capsys) -> None:
    log_file = tmp_path / "reasoning.log"
    log_file.write_text("line1\nline2\n", encoding="utf-8")

    usage_base_url_calls: list[tuple[bool, int | None]] = []
    usage_http_calls: list[tuple[str, float]] = []

    def fake_base_url(*, thinking=False, port=None):
        usage_base_url_calls.append((bool(thinking), port))
        return "http://127.0.0.1:8001" if thinking else "http://127.0.0.1:8000"

    def fake_http_json(url, *, timeout=10.0):
        usage_http_calls.append((url, timeout))
        return 200, {"entries": [], "summary": {"count": 0}}, None

    monkeypatch.setattr(cli, "_base_url", fake_base_url)
    monkeypatch.setattr(cli, "_http_json", fake_http_json)

    assert cli.main(["logs", "--reasoning", "--log-file", str(log_file), "--lines", "1"]) == 0
    assert "line2" in capsys.readouterr().out

    assert cli.main(["usage", "--reasoning", "--port", "8001", "--timeout", "1", "--summary"]) == 0
    assert usage_base_url_calls[-1] == (True, 8001)
    assert usage_http_calls[-1][0].startswith("http://127.0.0.1:8001/")
    assert usage_http_calls[-1][1] == 1.0


def test_doctor_reasoning_flag_sets_reasoning_runtime(monkeypatch) -> None:
    seen: list[tuple[bool, int | None]] = []

    def fake_doctor(args):
        seen.append((bool(args.thinking), getattr(args, "port", None)))
        return 0

    monkeypatch.setattr(cli, "_doctor", fake_doctor)

    assert cli.main(["doctor", "--reasoning", "--port", "8001"]) == 0
    assert seen == [(True, 8001)]
