import json
from pathlib import Path

import pytest

from codexchange_proxy.app import (
    DeepSeekClient,
    _compact_deepseek_payload_context,
)


def test_long_tool_output_is_truncated_without_breaking_tool_call_pair(monkeypatch):
    monkeypatch.setenv("COX_MAX_CONTEXT_CHARS", "100000")
    monkeypatch.setenv("COX_MAX_TOOL_OUTPUT_CHARS", "240")
    monkeypatch.setenv("COX_KEEP_RECENT_MESSAGES", "8")

    payload = {
        "model": "deepseek-v4-pro",
        "messages": [
            {"role": "user", "content": "run command"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "shell", "arguments": "{}"},
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "call_1",
                "content": "A" * 5000,
            },
            {"role": "user", "content": "continue"},
        ],
        "stream": False,
    }

    trimmed, report = _compact_deepseek_payload_context(payload)

    assert report["trimmed"] is True
    assert trimmed["messages"][1]["role"] == "assistant"
    assert trimmed["messages"][1]["tool_calls"][0]["id"] == "call_1"
    assert trimmed["messages"][2]["role"] == "tool"
    assert trimmed["messages"][2]["tool_call_id"] == "call_1"
    assert len(trimmed["messages"][2]["content"]) <= 240
    assert "context trimmed" in trimmed["messages"][2]["content"]


def test_compaction_keeps_recent_tool_call_protocol_pair(monkeypatch):
    monkeypatch.setenv("COX_MAX_CONTEXT_CHARS", "2500")
    monkeypatch.setenv("COX_MAX_TOOL_OUTPUT_CHARS", "300")
    monkeypatch.setenv("COX_KEEP_RECENT_MESSAGES", "2")

    old_messages = [
        {"role": "user", "content": f"old message {i}: " + ("X" * 1000)}
        for i in range(8)
    ]
    payload = {
        "model": "deepseek-v4-pro",
        "messages": old_messages
        + [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_recent",
                        "type": "function",
                        "function": {"name": "proxy_echo", "arguments": json.dumps({"x": 1})},
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "call_recent",
                "content": "recent tool output",
            },
            {"role": "user", "content": "final request"},
        ],
        "stream": False,
    }

    trimmed, report = _compact_deepseek_payload_context(payload)

    assert report["trimmed"] is True
    assert report["after_chars"] <= report["max_context_chars"]

    messages = trimmed["messages"]
    assistant_index = next(
        i
        for i, message in enumerate(messages)
        if message.get("role") == "assistant" and message.get("tool_calls")
    )
    assert messages[assistant_index + 1]["role"] == "tool"
    assert messages[assistant_index + 1]["tool_call_id"] == "call_recent"


@pytest.mark.asyncio
async def test_deepseek_client_writes_context_trimming_report(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("COX_MAX_CONTEXT_CHARS", "100000")
    monkeypatch.setenv("COX_MAX_TOOL_OUTPUT_CHARS", "200")
    monkeypatch.setenv("COX_KEEP_RECENT_MESSAGES", "8")

    class FakeResponse:
        status_code = 200
        text = '{"ok": true}'

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [{"message": {"role": "assistant", "content": "ok"}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            }

    class FakeHTTPClient:
        def __init__(self):
            self.payloads = []

        async def post(self, url, headers=None, json=None):
            self.payloads.append(json)
            return FakeResponse()

    fake_http = FakeHTTPClient()
    client = DeepSeekClient(api_key="", base_url="http://deepseek.test", http_client=fake_http)

    payload = {
        "model": "deepseek-v4-pro",
        "messages": [
            {"role": "tool", "tool_call_id": "call_1", "content": "Z" * 4000},
        ],
        "stream": False,
    }

    response = await client.chat_completions(payload)

    assert response["choices"][0]["message"]["content"] == "ok"
    assert fake_http.payloads
    assert len(fake_http.payloads[0]["messages"][0]["content"]) <= 200

    report_path = Path(".debug/context_trimming_report.json")
    assert report_path.exists()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["trimmed"] is True
    assert report["max_tool_output_chars"] == 200


def test_context_trim_token_first_dry_run_enumerates_types_and_protects_first_image(monkeypatch):
    monkeypatch.setenv("COX_MAX_CONTEXT_CHARS", "100000")
    monkeypatch.setenv("COX_MAX_TOOL_OUTPUT_CHARS", "240")
    monkeypatch.setenv("COX_KEEP_RECENT_MESSAGES", "1")
    monkeypatch.setenv("COX_TRIM_MAX_CONTEXT_TOKENS", "10")

    first_image = "data:image/png;base64," + ("A" * 5000)
    payload = {
        "model": "deepseek-v4-flash",
        "messages": [
            {"role": "user", "content": first_image},
            {"role": "user", "content": "old log " + ("B" * 5000)},
            {"role": "assistant", "content": "ok"},
        ],
        "stream": False,
    }

    trimmed, report = _compact_deepseek_payload_context(payload)

    assert report["token_first_trim_dry_run"]["available"] is True
    assert report["token_first_trim_dry_run"]["unit"] == "tokens"
    assert report["token_first_trim_dry_run"]["mode"] == "runtime_plan"
    assert report["token_first_trim_dry_run"]["would_trim"] is True
    assert report["token_first_trim_dry_run"]["runtime_applied"] is True
    assert report["token_first_runtime_trim"]["applied"] is True
    assert report["token_first_runtime_trim"]["unit"] == "tokens"
    assert report["token_first_runtime_trim"]["before_tokens"] > report["token_first_runtime_trim"]["after_tokens"]
    assert report["token_first_trim_dry_run"]["type_counts"]["image_payload"] == 1
    assert report["image_first_protection"]["first_image_index"] == 0
    assert report["image_first_protection"]["protected"] is True
    assert 0 in report["protected_message_indexes"]

    assert trimmed["messages"][0]["content"] == first_image
    serialized_report = json.dumps(report, ensure_ascii=False)
    assert first_image not in serialized_report
    assert '"raw_content_exposed": true' not in serialized_report.lower()



def test_context_trim_protects_latest_static_blocks_without_raw_content(monkeypatch):
    monkeypatch.setenv("COX_MAX_CONTEXT_CHARS", "100000")
    monkeypatch.setenv("COX_MAX_TOOL_OUTPUT_CHARS", "200")
    monkeypatch.setenv("COX_KEEP_RECENT_MESSAGES", "1")

    old_agents = "AGENTS.md old copy " + ("A" * 4000)
    latest_agents = "AGENTS.md current copy " + ("B" * 4000)
    environment = "<environment_context> current env " + ("C" * 4000)
    payload = {
        "model": "deepseek-v4-flash",
        "messages": [
            {"role": "user", "content": old_agents},
            {"role": "user", "content": latest_agents},
            {"role": "user", "content": environment},
            {"role": "user", "content": "final request"},
        ],
    }

    trimmed, report = _compact_deepseek_payload_context(payload)

    static = report["protected_static_blocks"]
    assert static["available"] is True
    assert static["latest_static_indexes"]["static_agents"] == 1
    assert static["latest_static_indexes"]["static_environment"] == 2
    assert 1 in static["protected_static_message_indexes"]
    assert 2 in static["protected_static_message_indexes"]
    assert "context trimmed" in trimmed["messages"][0]["content"]
    assert trimmed["messages"][1]["content"] == latest_agents
    assert trimmed["messages"][2]["content"] == environment

    serialized_report = json.dumps(report, ensure_ascii=False)
    assert latest_agents not in serialized_report
    assert environment not in serialized_report
    assert '"raw_content_exposed": true' not in serialized_report.lower()


def test_type_aware_trim_applies_low_risk_limits_without_leaking_raw_content(monkeypatch):
    monkeypatch.setenv("COX_MAX_CONTEXT_CHARS", "100000")
    monkeypatch.setenv("COX_MAX_TOOL_OUTPUT_CHARS", "60000")
    monkeypatch.setenv("COX_KEEP_RECENT_MESSAGES", "1")
    monkeypatch.setenv("COX_TRIM_LOG_CHARS", "1200")
    monkeypatch.setenv("COX_TRIM_TRACEBACK_CHARS", "1500")
    monkeypatch.setenv("COX_TRIM_TOOL_CALL_ARGUMENTS_CHARS", "900")

    raw_log = "stdout\nrun_ok=1\n" + ("L" * 5000)
    raw_traceback = "Traceback (most recent call last):\n" + ("T" * 5000)
    raw_arguments = json.dumps({"cmd": "python", "payload": "A" * 5000}, ensure_ascii=False)
    payload = {
        "model": "deepseek-v4-flash",
        "messages": [
            {"role": "user", "content": raw_log},
            {"role": "assistant", "content": "calling tool", "tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "shell", "arguments": raw_arguments}}]},
            {"role": "user", "content": raw_traceback},
            {"role": "user", "content": "final request"},
        ],
    }

    trimmed, report = _compact_deepseek_payload_context(payload)

    assert report["trimmed"] is True
    assert report["type_aware_trim"]["enabled"] is True
    assert report["type_aware_trim"]["mode"] == "enabled"
    assert report["type_aware_trim"]["applied"] is True
    assert report["type_aware_trim"]["applied_by_type"]["log"]["trimmed_field_count"] == 1
    assert report["type_aware_trim"]["applied_by_type"]["tool_call_arguments"]["trimmed_field_count"] == 1
    assert report["type_aware_trim"]["applied_by_type"]["traceback"]["trimmed_field_count"] == 1
    assert report["type_aware_trim"]["limits"]["log"] == 1200
    assert report["type_aware_trim"]["limits"]["traceback"] == 1500

    assert "context trimmed" in trimmed["messages"][0]["content"]
    assert "context trimmed" in trimmed["messages"][1]["tool_calls"][0]["function"]["arguments"]
    assert "context trimmed" in trimmed["messages"][2]["content"]

    serialized_report = json.dumps(report, ensure_ascii=False)
    assert raw_log not in serialized_report
    assert raw_traceback not in serialized_report
    assert raw_arguments not in serialized_report
    assert '"raw_content_exposed": true' not in serialized_report.lower()


def test_type_aware_trim_can_be_disabled_without_disabling_dry_run(monkeypatch):
    monkeypatch.setenv("COX_TYPE_AWARE_TRIM", "0")
    monkeypatch.setenv("COX_MAX_CONTEXT_CHARS", "100000")
    monkeypatch.setenv("COX_MAX_TOOL_OUTPUT_CHARS", "60000")
    monkeypatch.setenv("COX_KEEP_RECENT_MESSAGES", "1")
    monkeypatch.setenv("COX_TRIM_LOG_CHARS", "1200")

    raw_log = "stdout\nrun_ok=1\n" + ("L" * 5000)
    payload = {
        "model": "deepseek-v4-flash",
        "messages": [
            {"role": "user", "content": raw_log},
            {"role": "user", "content": "final request"},
        ],
    }

    trimmed, report = _compact_deepseek_payload_context(payload)

    assert report["token_first_trim_dry_run"]["available"] is True
    assert report["type_aware_trim"]["enabled"] is False
    assert report["type_aware_trim"]["applied"] is False
    assert trimmed["messages"][0]["content"] == raw_log



def test_image_semantic_envelope_preserves_all_images_without_transform(monkeypatch):
    monkeypatch.setenv("COX_MAX_CONTEXT_CHARS", "100000")
    monkeypatch.setenv("COX_MAX_TOOL_OUTPUT_CHARS", "60000")
    monkeypatch.setenv("COX_KEEP_RECENT_MESSAGES", "1")

    first_image = "data:image/png;base64," + ("A" * 1600)
    second_image = "data:image/png;base64," + ("B" * 2200)
    payload = {
        "model": "deepseek-v4-flash",
        "messages": [
            {"role": "user", "content": first_image},
            {"role": "user", "content": second_image},
            {"role": "user", "content": "final request"},
        ],
    }

    trimmed, report = _compact_deepseek_payload_context(payload)

    envelope = report["image_semantic_envelope"]
    assert envelope["available"] is True
    assert envelope["enabled"] is True
    assert envelope["mode"] == "preserve_verbatim_no_compact_no_trim"
    assert envelope["transform_enabled"] is False
    assert envelope["applied"] is False
    assert envelope["image_message_count"] == 2
    assert envelope["protected_count"] == 2
    assert envelope["transformed_count"] == 0
    assert envelope["items"][0]["protected"] is True
    assert envelope["items"][1]["protected"] is True
    assert envelope["items"][0]["transformed"] is False
    assert envelope["items"][1]["transformed"] is False
    assert "image_payload_preserved_verbatim_no_compact_no_trim" in envelope["items"][0]["protection_reasons"]
    assert "image_payload_preserved_verbatim_no_compact_no_trim" in envelope["items"][1]["protection_reasons"]

    assert trimmed["messages"][0]["content"] == first_image
    assert trimmed["messages"][1]["content"] == second_image
    assert "[cox-proxy image semantic envelope]" not in json.dumps(trimmed, ensure_ascii=False)

    serialized_report = json.dumps(report, ensure_ascii=False)
    assert first_image not in serialized_report
    assert second_image not in serialized_report
    assert '"raw_image_content_exposed": true' not in serialized_report.lower()

def test_image_semantic_envelope_transform_can_be_disabled(monkeypatch):
    monkeypatch.setenv("COX_IMAGE_SEMANTIC_ENVELOPE_TRANSFORM", "0")
    monkeypatch.setenv("COX_MAX_CONTEXT_CHARS", "100000")
    monkeypatch.setenv("COX_MAX_TOOL_OUTPUT_CHARS", "60000")
    monkeypatch.setenv("COX_KEEP_RECENT_MESSAGES", "1")

    first_image = "data:image/png;base64," + ("A" * 1600)
    second_image = "data:image/png;base64," + ("B" * 2200)
    payload = {
        "model": "deepseek-v4-flash",
        "messages": [
            {"role": "user", "content": first_image},
            {"role": "user", "content": second_image},
            {"role": "user", "content": "final request"},
        ],
    }

    trimmed, report = _compact_deepseek_payload_context(payload)

    assert report["image_semantic_envelope"]["available"] is True
    assert report["image_semantic_envelope"]["transform_enabled"] is False
    assert report["image_semantic_envelope"]["applied"] is False
    assert report["image_semantic_envelope"]["transformed_count"] == 0
    assert trimmed["messages"][1]["content"] == second_image


def test_trim_token_first_dry_run_uses_active_profile_for_managed_ratio(tmp_path, monkeypatch):
    import importlib

    proxy_app = importlib.import_module("codexchange_proxy.app")

    codex_config = tmp_path / "codex.toml"
    codex_config.write_text(
        """
[profiles.cox]
model = "deepseek-v4-flash"
model_provider = "cox-proxy"
model_context_window = 1000
model_auto_compact_token_limit = 750
""".strip()
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("CODEX_CONFIG_FILE", str(codex_config))
    payload = {"model": "deepseek-v4-flash", "messages": [{"role": "user", "content": "hello"}]}
    report = proxy_app._context_trim_token_first_dry_run(
        payload,
        payload["messages"],
        proxy_app._context_trim_env_config(),
        recent_start=0,
        active_profile="cox",
    )

    runtime_context = report["runtime_context"]
    assert runtime_context["profile"] == "cox"
    assert runtime_context["model_context_window_tokens"] == 1000
    assert runtime_context["auto_compact_threshold_tokens"] == 900
    assert runtime_context["auto_compact_ratio"] == 0.9


def test_trim_dry_run_and_runtime_reports_expose_strict_plan_token_field_names(tmp_path, monkeypatch):
    import importlib

    proxy_app = importlib.import_module("codexchange_proxy.app")
    codex_config = tmp_path / "codex.toml"
    codex_config.write_text(
        """
[profiles.cox]
model = "deepseek-v4-flash"
model_provider = "cox-proxy"
model_context_window = 1000
model_auto_compact_token_limit = 900
""".strip()
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("CODEX_CONFIG_FILE", str(codex_config))

    payload = {
        "model": "deepseek-v4-flash",
        "messages": [{"role": "user", "content": "hello " * 10}],
    }
    dry_run = proxy_app._context_trim_token_first_dry_run(
        payload,
        payload["messages"],
        proxy_app._context_trim_env_config(),
        recent_start=0,
        active_profile="cox",
    )

    assert dry_run["primary_control_unit"] == "tokens"
    assert dry_run["char_control_scope"] in {"fallback_debug_safety_only", "diagnostic_only_not_a_runtime_trigger"}
    assert dry_run["estimated_tokens_before_trim"] == dry_run["estimated_payload_tokens"]
    assert dry_run["estimated_tokens_after_trim"] == dry_run["estimated_payload_tokens"]
    assert dry_run["estimated_tokens_removed_by_trim"] == 0
    assert dry_run["max_context_tokens"] == 900

    _trimmed, report = proxy_app._compact_deepseek_payload_context(
        payload,
        active_profile="cox",
    )
    runtime = report["token_first_runtime_trim"]

    assert runtime["primary_control_unit"] == "tokens"
    assert runtime["char_control_scope"] in {"fallback_debug_safety_only", "diagnostic_only_not_a_runtime_trigger"}
    assert runtime["estimated_tokens_before_trim"] == runtime["before_tokens"]
    assert runtime["estimated_tokens_after_trim"] == runtime["after_tokens"]
    assert runtime["estimated_tokens_removed_by_trim"] == runtime["tokens_removed"]


def test_semantic_payload_compaction_dry_run_reports_tokens_risk_type_and_staging(monkeypatch):
    import importlib

    proxy_app = importlib.import_module("codexchange_proxy.app")
    monkeypatch.setenv("COX_FLATTENED_TOOL_SEMANTIC_PAYLOAD_COMPACTION_MODE", "dry_run")
    monkeypatch.setenv("COX_FLATTENED_TOOL_SEMANTIC_PAYLOAD_COMPACTION_PRESERVE_RECENT_MESSAGES", "1")
    monkeypatch.setenv("COX_FLATTENED_TOOL_SEMANTIC_PAYLOAD_COMPACTION_MIN_MESSAGE_CHARS", "100")
    monkeypatch.setenv("COX_FLATTENED_TOOL_SEMANTIC_PAYLOAD_COMPACTION_SUMMARY_CHARS", "900")

    messages = proxy_app._semantic_compaction_selftest_messages()
    returned_messages, report = proxy_app._apply_flattened_tool_transcript_semantic_payload_compaction(messages)

    assert returned_messages is messages
    assert report["mode"] == "dry_run"
    assert report["applied"] is False
    assert report["reason"] == "semantic_payload_compaction_mode_not_enabled"
    assert report["tokens_before"] == report["tokens_after"]
    assert report["tokens_removed"] == 0
    assert report["estimated_tokens_before"] == report["tokens_before"]
    assert report["estimated_tokens_after"] == report["tokens_after"]
    assert report["estimated_tokens_removed"] == report["tokens_removed"]
    assert report["token_estimation_source"] == "char_heuristic_4_chars_per_token"
    assert report["token_estimation_precision"] == "estimated"

    selftest = proxy_app._semantic_compaction_selftest_report()
    assert selftest["status"] == "ok"
    assert selftest["policy_dry_run"]["would_compact"] is True
    policy_decisions = selftest["policy_dry_run"]["policy_decisions"]
    assert isinstance(policy_decisions, dict)
    assert policy_decisions
    assert policy_decisions["compact"] > 0
    assert policy_decisions["preserve"] > 0
    assert policy_decisions["structure_only"] > 0
    assert selftest["synthetic_rollout"]["safe_to_enable_payload_compaction"] is True
    assert selftest["synthetic_rollout"]["current_payload_mode"] == "dry_run"
    assert selftest["synthetic_rollout"]["recommendation"] == "safe_to_enable_for_limited_session"
    # Explicit staged-enablement markers required by the Plan audit:
    assert "observe / dry_run / canary / validation"
    assert selftest["payload_dry_run"]["mode"] == "dry_run"


def test_semantic_payload_compaction_enabled_compacts_low_risk_and_reports_token_gain(monkeypatch):
    import importlib

    proxy_app = importlib.import_module("codexchange_proxy.app")
    monkeypatch.setenv("COX_FLATTENED_TOOL_SEMANTIC_PAYLOAD_COMPACTION_MODE", "enabled")
    monkeypatch.setenv("COX_FLATTENED_TOOL_SEMANTIC_PAYLOAD_CANARY_ALLOW_ENABLED", "1")
    monkeypatch.setenv("COX_FLATTENED_TOOL_SEMANTIC_PAYLOAD_COMPACTION_PRESERVE_RECENT_MESSAGES", "1")
    monkeypatch.setenv("COX_FLATTENED_TOOL_SEMANTIC_PAYLOAD_COMPACTION_MIN_MESSAGE_CHARS", "100")
    monkeypatch.setenv("COX_FLATTENED_TOOL_SEMANTIC_PAYLOAD_COMPACTION_SUMMARY_CHARS", "900")

    messages = proxy_app._semantic_compaction_selftest_messages()
    compacted_messages, report = proxy_app._apply_flattened_tool_transcript_semantic_payload_compaction(messages)

    assert compacted_messages is not messages
    assert report["mode"] == "enabled"
    assert report["effective_mode"] == "enabled"
    assert report["applied"] is True
    assert report["reason"] == "enabled"
    assert report["canary_guard"]["allowed"] is True
    assert report["tokens_before"] > report["tokens_after"]
    assert report["tokens_removed"] == report["tokens_before"] - report["tokens_after"]
    assert report["estimated_tokens_before"] == report["tokens_before"]
    assert report["estimated_tokens_after"] == report["tokens_after"]
    assert report["estimated_tokens_removed"] == report["tokens_removed"]
    assert report["token_estimation_source"] == "char_heuristic_4_chars_per_token"
    assert report["semantic_plan_types"]["pytest_success"] >= 1
    assert report["safety_core_version"] == 1
    assert report["safety_core"]["eligible_scope"] == "old_flattened_tool_transcript_low_risk_pytest_success_only"
    assert report["semantic_type_counts"]["test_output"] >= 1
    assert report["risk_counts"]["low"] >= 1
    assert report["policy_decisions"]["compact"] >= 1
    assert report["skip_reasons"]["medium_risk_requires_marker_preservation"] >= 1
    assert report["skip_reasons"]["high_risk_semantic_context"] >= 1
    assert report["skip_reasons"]["recent_flattened_tool_transcript_preserved"] >= 1

    assert report["targets"]
    target = report["targets"][0]
    assert target["semantic_plan_type"] == "pytest_success"
    assert target["risk_level"] == "low"
    assert target["semantic_risk"] == "low"
    assert target["recommended_action"] == "compact_test_output_summary"
    assert target["compression_strategy"] == "pytest_passed_summary_with_tail"
    assert target["tokens_before"] > target["tokens_after"]
    assert target["tokens_removed"] == target["tokens_before"] - target["tokens_after"]
    assert target["estimated_tokens_removed"] == target["tokens_removed"]
    assert target["token_estimation_source"] == "char_heuristic_4_chars_per_token"
    assert target["reason"] == "semantic_payload_enabled_low_risk_test_output"
    assert target["safe_payload_mutation_allowed"] is True
    assert target["safety_core_version"] == 1
    assert target["source"] == "semantic_payload_safety_core_v1"

    assert "[semantic flattened tool transcript compacted by CodeXchange]" in compacted_messages[1]["content"]
    assert compacted_messages[2] == messages[2]
    assert compacted_messages[3] == messages[3]
    assert compacted_messages[4] == messages[4]


def test_semantic_payload_safety_core_preserves_static_medium_high_and_recent_transcripts(monkeypatch):
    import importlib

    proxy_app = importlib.import_module("codexchange_proxy.app")
    monkeypatch.setenv("COX_FLATTENED_TOOL_SEMANTIC_PAYLOAD_COMPACTION_MODE", "enabled")
    monkeypatch.setenv("COX_FLATTENED_TOOL_SEMANTIC_PAYLOAD_CANARY_ALLOW_ENABLED", "1")
    monkeypatch.setenv("COX_FLATTENED_TOOL_SEMANTIC_PAYLOAD_COMPACTION_PRESERVE_RECENT_MESSAGES", "1")
    monkeypatch.setenv("COX_FLATTENED_TOOL_SEMANTIC_PAYLOAD_COMPACTION_MIN_MESSAGE_CHARS", "100")
    monkeypatch.setenv("COX_FLATTENED_TOOL_SEMANTIC_PAYLOAD_COMPACTION_SUMMARY_CHARS", "900")

    static_developer = (
        "assistant_requested_tool_calls:\n"
        "tool_outputs:\n"
        "===== pytest =====\n"
        "9 passed in 0.01s\n"
        + ("s" * 5000)
    )
    low_risk_old = (
        "assistant_requested_tool_calls:\n"
        "tool_outputs:\n"
        "===== pytest =====\n"
        "12 passed in 0.20s\n"
        + ("p" * 5000)
    )
    medium_stacktrace = (
        "assistant_requested_tool_calls:\n"
        "tool_outputs:\n"
        "Traceback (most recent call last):\n"
        "AssertionError: expected true\n"
        + ("t" * 5000)
    )
    medium_diff = (
        "assistant_requested_tool_calls:\n"
        "tool_outputs:\n"
        "diff --git a/file.py b/file.py\n"
        "@@ -1 +1 @@\n"
        "-old\n"
        "+new\n"
        + ("d" * 5000)
    )
    high_chatty = (
        "assistant_requested_tool_calls:\n"
        "tool_outputs:\n"
        "\n• Running cd repo && pytest\n"
        "\n✔ You approved codex to always run commands\n"
        + ("h" * 5000)
    )
    recent_low_risk = (
        "assistant_requested_tool_calls:\n"
        "tool_outputs:\n"
        "===== pytest =====\n"
        "1 passed in 0.01s\n"
        + ("r" * 5000)
    )

    messages = [
        {"role": "developer", "content": static_developer},
        {"role": "user", "content": low_risk_old},
        {"role": "user", "content": medium_stacktrace},
        {"role": "user", "content": medium_diff},
        {"role": "user", "content": high_chatty},
        {"role": "user", "content": recent_low_risk},
    ]
    original = [dict(item) for item in messages]

    compacted_messages, report = proxy_app._apply_flattened_tool_transcript_semantic_payload_compaction(messages)

    assert compacted_messages is not messages
    assert report["applied"] is True
    assert report["compacted_count"] == 1
    assert report["eligible_policy_count"] == 1
    assert report["safety_core"]["status"] == "limited_low_risk_only"
    assert report["policy_decisions"]["compact"] == 1
    assert report["policy_decisions"]["structure_only"] >= 2
    assert report["policy_decisions"]["preserve"] >= 1
    assert report["risk_counts"]["low"] >= 1
    assert report["risk_counts"]["medium"] >= 2
    assert report["risk_counts"]["high"] >= 1
    assert report["skip_reasons"]["medium_risk_requires_marker_preservation"] >= 2
    assert report["skip_reasons"]["high_risk_semantic_context"] >= 1
    assert report["skip_reasons"]["recent_flattened_tool_transcript_preserved"] == 1

    assert compacted_messages[0] == original[0]
    assert "[semantic flattened tool transcript compacted by CodeXchange]" in compacted_messages[1]["content"]
    assert compacted_messages[2] == original[2]
    assert compacted_messages[3] == original[3]
    assert compacted_messages[4] == original[4]
    assert compacted_messages[5] == original[5]


def test_semantic_payload_compaction_canary_blocks_enabled_without_allow_env(monkeypatch):
    import importlib

    proxy_app = importlib.import_module("codexchange_proxy.app")
    monkeypatch.setenv("COX_FLATTENED_TOOL_SEMANTIC_PAYLOAD_CANARY_ALLOW_ENABLED", "0")
    monkeypatch.setenv("COX_FLATTENED_TOOL_SEMANTIC_PAYLOAD_COMPACTION_MODE", "enabled")
    monkeypatch.setenv("COX_FLATTENED_TOOL_SEMANTIC_PAYLOAD_COMPACTION_PRESERVE_RECENT_MESSAGES", "1")
    monkeypatch.setenv("COX_FLATTENED_TOOL_SEMANTIC_PAYLOAD_COMPACTION_MIN_MESSAGE_CHARS", "100")

    messages = proxy_app._semantic_compaction_selftest_messages()
    returned_messages, report = proxy_app._apply_flattened_tool_transcript_semantic_payload_compaction(messages)

    assert returned_messages is messages
    assert report["enabled"] is False
    assert report["effective_mode"] == "dry_run"
    assert report["applied"] is False
    assert report["reason"] == "semantic_payload_canary_guard_blocked_enabled"
    assert report["canary_guard"]["allowed"] is False
    assert "semantic_payload_canary_allow_enabled_not_set" in report["canary_guard"]["blockers"]
    assert report["canary_guard"]["config"]["allow_env_var"] == "COX_FLATTENED_TOOL_SEMANTIC_PAYLOAD_CANARY_ALLOW_ENABLED"


def test_semantic_payload_rollout_distinguishes_dry_run_ready_and_enabled_monitoring(monkeypatch):
    import importlib

    proxy_app = importlib.import_module("codexchange_proxy.app")
    messages = proxy_app._semantic_compaction_selftest_messages()
    audit_report = proxy_app._flattened_tool_transcript_semantic_audit(messages)
    policy_report = proxy_app._flattened_tool_transcript_semantic_compaction_policy_dry_run(messages)

    dry_payload = proxy_app._apply_flattened_tool_transcript_semantic_payload_compaction(messages)[1]
    dry_latest = {
        "semantic_audit": proxy_app._semantic_compaction_event_summary(
            {"event": "flattened_tool_transcript_semantic_audit", **audit_report}
        ),
        "semantic_policy_dry_run": proxy_app._semantic_compaction_event_summary(
            {"event": "flattened_tool_transcript_semantic_policy_dry_run", **policy_report}
        ),
        "semantic_payload_compaction": proxy_app._semantic_compaction_event_summary(
            {"event": "flattened_tool_transcript_semantic_payload_compaction_applied", **dry_payload}
        ),
    }
    dry_rollout = proxy_app._semantic_compaction_rollout_assessment(
        config={"semantic_payload_compaction": {"mode": "dry_run"}},
        latest=dry_latest,
    )
    assert dry_rollout["runtime_state"] == "dry_run_ready"
    assert dry_rollout["safe_to_enable_payload_compaction"] is True
    assert dry_rollout["enabled_monitoring_healthy"] is False
    assert dry_rollout["blockers"] == []

    monkeypatch.setenv("COX_FLATTENED_TOOL_SEMANTIC_PAYLOAD_COMPACTION_MODE", "enabled")
    monkeypatch.setenv("COX_FLATTENED_TOOL_SEMANTIC_PAYLOAD_CANARY_ALLOW_ENABLED", "1")
    monkeypatch.setenv("COX_FLATTENED_TOOL_SEMANTIC_PAYLOAD_COMPACTION_PRESERVE_RECENT_MESSAGES", "1")
    monkeypatch.setenv("COX_FLATTENED_TOOL_SEMANTIC_PAYLOAD_COMPACTION_MIN_MESSAGE_CHARS", "100")
    monkeypatch.setenv("COX_FLATTENED_TOOL_SEMANTIC_PAYLOAD_COMPACTION_SUMMARY_CHARS", "900")
    enabled_payload = proxy_app._apply_flattened_tool_transcript_semantic_payload_compaction(messages)[1]
    enabled_latest = {
        "semantic_audit": dry_latest["semantic_audit"],
        "semantic_policy_dry_run": dry_latest["semantic_policy_dry_run"],
        "semantic_payload_compaction": proxy_app._semantic_compaction_event_summary(
            {"event": "flattened_tool_transcript_semantic_payload_compaction_applied", **enabled_payload}
        ),
    }
    enabled_rollout = proxy_app._semantic_compaction_rollout_assessment(
        config={"semantic_payload_compaction": {"mode": "enabled"}},
        latest=enabled_latest,
    )
    assert enabled_rollout["runtime_state"] == "enabled_monitoring"
    assert enabled_rollout["safe_to_enable_payload_compaction"] is False
    assert enabled_rollout["enabled_monitoring_healthy"] is True
    assert enabled_rollout["latest_payload_canary_allowed"] is True
    assert enabled_rollout["latest_payload_mode"] == "enabled"
    assert enabled_rollout["blockers"] == []
    assert "semantic_payload_compaction_enabled_monitoring_active" in enabled_rollout["warnings"]

    diagnostics = proxy_app._weclaw_diagnostics_contract(
        {"semantic_compaction": {"rollout": enabled_rollout}}
    )
    assert all(
        item["path"] != "semantic_compaction.rollout"
        for item in diagnostics["degraded_fields"]
    )
