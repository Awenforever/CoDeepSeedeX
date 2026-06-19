from __future__ import annotations

import importlib
from pathlib import Path


proxy_app = importlib.import_module("codexchange_proxy.app")


def test_context_budget_breakdown_uses_provider_neutral_message_budget_key() -> None:
    budget = proxy_app._context_budget_breakdown(
        request_payload={"input": [{"role": "user", "content": "hello"}], "tools": []},
        input_value=[{"role": "user", "content": "hello"}],
        messages_before_compaction=[{"role": "user", "content": "hello"}],
        messages_after_compaction=[{"role": "user", "content": "hello"}],
        messages_for_deepseek=[{"role": "user", "content": "hello"}],
        deepseek_tools=[],
        chat_payload={"model": "custom-model", "messages": [{"role": "user", "content": "hello"}]},
        context_compaction_report={
            "compacted": False,
            "reason": "not_triggered",
            "policy": "adaptive",
            "before_chars": 100,
            "after_chars": 100,
            "chars_removed": None,
            "message_count_before": 1,
            "message_count_after": 1,
            "policy_decision": {},
        },
    )

    assert "messages_for_provider" in budget
    assert "messages_for_deepseek" not in budget
    assert budget["messages_for_provider"]["message_count"] == 1


def test_context_budget_trace_runtime_event_name_is_provider_neutral() -> None:
    source = Path(proxy_app.__file__).read_text(encoding="utf-8")

    assert "messages_prepared_for_provider" in source
    assert "messages_prepared_for_deepseek" not in source
    assert '\"messages_for_provider\": _debug_trace_message_budget' in source
    assert '\"messages_for_deepseek\": _debug_trace_message_budget' not in source
