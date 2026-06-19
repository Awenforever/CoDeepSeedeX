from pathlib import Path

APP_SOURCE = Path("codexchange_proxy/app.py").read_text(encoding="utf-8")


def test_persistent_compaction_summary_budget_wording_is_provider_neutral() -> None:
    assert "agent loop within the configured provider context budget" in APP_SOURCE
    assert "agent loop within the DeepSeek context budget" not in APP_SOURCE
