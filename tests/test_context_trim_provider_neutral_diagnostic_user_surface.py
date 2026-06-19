import importlib
import inspect

proxy_app = importlib.import_module("codexchange_proxy.app")


def test_context_compaction_summary_uses_provider_neutral_upstream_limit():
    source = inspect.getsource(proxy_app._compact_old_message_prefix)
    assert "DeepSeek upstream context limit" not in source
    assert "configured provider upstream context limit" in source

    report: dict[str, object] = {}
    messages = [
        {"role": "system", "content": "system prompt"},
        {"role": "user", "content": "old request A"},
        {"role": "assistant", "content": "old answer B"},
        {"role": "user", "content": "recent request"},
    ]

    trimmed = proxy_app._compact_old_message_prefix(
        messages,
        keep_recent_messages=1,
        report=report,
    )

    summary_messages = [
        message
        for message in trimmed
        if isinstance(message, dict)
        and isinstance(message.get("content"), str)
        and message["content"].startswith("[cox-proxy context compacted]")
    ]
    assert len(summary_messages) == 1
    summary_text = summary_messages[0]["content"]
    assert "configured provider upstream context limit" in summary_text
    assert "DeepSeek upstream context limit" not in summary_text
    assert report["trimmed"] is True
