from pathlib import Path


APP_SOURCE = Path("codexchange_proxy/app.py").read_text(encoding="utf-8")


def test_tool_flattening_diagnostic_uses_provider_neutral_boundary() -> None:
    assert "tool messages because no configured provider tools were available" in APP_SOURCE
    assert "tool messages because no DeepSeek tools were available" not in APP_SOURCE
