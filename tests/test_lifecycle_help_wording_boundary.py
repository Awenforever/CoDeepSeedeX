from __future__ import annotations

import contextlib
import io

from codexchange_proxy import cli


def _squish(text: str) -> str:
    return " ".join(text.split())


def _capture_main(argv: list[str]) -> tuple[int, str]:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        try:
            rc = cli.main(argv)
        except SystemExit as exc:
            rc = int(exc.code or 0)
    return rc, buf.getvalue()


def test_lifecycle_target_help_is_provider_neutral() -> None:
    for argv in [
        ["start", "--help"],
        ["start", "reasoning", "--help"],
        ["start", "standard", "--help"],
        ["status", "reasoning", "--help"],
        ["status", "standard", "--help"],
        ["stop", "reasoning", "--help"],
        ["stop", "standard", "--help"],
    ]:
        rc, output = _capture_main(argv)
        assert rc == 0
        normalized = _squish(output)
        assert "optional target: standard or reasoning" in normalized
        assert "legacy aliases: thinking, non-thinking" in normalized
        assert "optional target: thinking" not in normalized


def test_legacy_thinking_flag_help_points_to_reasoning_route() -> None:
    rc, output = _capture_main(["start", "--help"])

    assert rc == 0
    assert "--thinking" in output
    assert "legacy alias for reasoning route on port 8001" in _squish(output)
    assert "start thinking proxy on port 8001" not in _squish(output)


def test_lifecycle_help_keeps_legacy_alias_choices() -> None:
    rc, output = _capture_main(["status", "--help"])

    assert rc == 0
    for choice in ["standard", "reasoning", "thinking", "non-thinking", "non_thinking", "nonthinking"]:
        assert choice in output
