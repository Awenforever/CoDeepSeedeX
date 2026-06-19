from pathlib import Path


APP_SOURCE = Path("codexchange_proxy/app.py").read_text(encoding="utf-8")


def test_chat_role_normalization_diagnostic_uses_provider_neutral_boundary() -> None:
    assert "mapped unsupported provider message role" in APP_SOURCE
    assert "mapped unsupported DeepSeek message role" not in APP_SOURCE
