from pathlib import Path


APP_TEXT = Path("codexchange_proxy/app.py").read_text(encoding="utf-8")


def test_token_diagnostic_sources_are_provider_neutral():
    assert "provider_chat_payload_after_cox_build_chat_payload" in APP_TEXT
    assert "cox_provider_messages_after_payload_assembly" in APP_TEXT
    assert "provider_usage.prompt_cache_hit_tokens_and_prompt_cache_miss_tokens_via_cox_usage_ledger" in APP_TEXT

    assert "deepseek_chat_payload_after_cox_build_chat_payload" not in APP_TEXT
    assert "cox_deepseek_messages_after_payload_assembly" not in APP_TEXT
    assert "deepseek_usage.prompt_cache_hit_tokens_and_prompt_cache_miss_tokens_via_cox_usage_ledger" not in APP_TEXT
