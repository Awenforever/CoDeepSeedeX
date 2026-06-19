from pathlib import Path


def test_upstream_error_log_uses_provider_neutral_diagnostic() -> None:
    text = Path("codexchange_proxy/app.py").read_text(encoding="utf-8")
    assert '[codexchange] provider upstream error' in text
    assert '[codexchange] DeepSeek upstream error' not in text
