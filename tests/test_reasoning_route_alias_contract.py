from __future__ import annotations

from codexchange_proxy import cli


def test_route_target_alias_normalization_contract() -> None:
    assert cli._normalize_route_target_to_thinking("reasoning") is True
    assert cli._normalize_route_target_to_thinking("thinking") is True
    assert cli._normalize_route_target_to_thinking("standard") is False
    assert cli._normalize_route_target_to_thinking("stable") is False
    assert cli._normalize_route_target_to_thinking("non-thinking") is False
    assert cli._normalize_route_target_to_thinking("non_thinking") is False
    assert cli._normalize_route_target_to_thinking(None) is None


def test_lifecycle_commands_accept_standard_and_reasoning_aliases(monkeypatch) -> None:
    calls: list[tuple[str, bool, object]] = []

    def fake_start(args):
        calls.append(("start", bool(args.thinking), getattr(args, "target", None)))
        return 0

    def fake_stop(args):
        calls.append(("stop", bool(args.thinking), getattr(args, "target", None)))
        return 0

    def fake_status(args):
        calls.append(("status", bool(args.thinking), getattr(args, "target", None)))
        return 0

    monkeypatch.setattr(cli, "_start_proxy", fake_start)
    monkeypatch.setattr(cli, "_stop_proxy", fake_stop)
    monkeypatch.setattr(cli, "_status", fake_status)

    assert cli.main(["start", "standard"]) == 0
    assert cli.main(["stop", "standard"]) == 0
    assert cli.main(["status", "standard"]) == 0

    assert cli.main(["start", "reasoning"]) == 0
    assert cli.main(["stop", "reasoning"]) == 0
    assert cli.main(["status", "reasoning"]) == 0

    assert calls == [
        ("start", False, "standard"),
        ("stop", False, "standard"),
        ("status", False, "standard"),
        ("start", True, "reasoning"),
        ("stop", True, "reasoning"),
        ("status", True, "reasoning"),
    ]


def test_lifecycle_commands_keep_legacy_thinking_and_non_thinking_aliases(monkeypatch) -> None:
    calls: list[tuple[str, bool, object]] = []

    def fake_start(args):
        calls.append(("start", bool(args.thinking), getattr(args, "target", None)))
        return 0

    def fake_stop(args):
        calls.append(("stop", bool(args.thinking), getattr(args, "target", None)))
        return 0

    def fake_status(args):
        calls.append(("status", bool(args.thinking), getattr(args, "target", None)))
        return 0

    monkeypatch.setattr(cli, "_start_proxy", fake_start)
    monkeypatch.setattr(cli, "_stop_proxy", fake_stop)
    monkeypatch.setattr(cli, "_status", fake_status)

    assert cli.main(["start", "thinking"]) == 0
    assert cli.main(["stop", "thinking"]) == 0
    assert cli.main(["status", "thinking"]) == 0
    assert cli.main(["start", "--thinking"]) == 0
    assert cli.main(["status", "non-thinking"]) == 0
    assert cli.main(["status", "non_thinking"]) == 0

    assert calls == [
        ("start", True, "thinking"),
        ("stop", True, "thinking"),
        ("status", True, "thinking"),
        ("start", True, None),
        ("status", False, "non-thinking"),
        ("status", False, "non_thinking"),
    ]
