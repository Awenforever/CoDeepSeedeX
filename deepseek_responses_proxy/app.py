from __future__ import annotations

import json
import os
import sqlite3
import time
import tomllib
import uuid
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse


DEFAULT_MODEL = os.environ.get("DEEPSEEK_PROXY_MODEL", "deepseek-v4-pro").strip() or "deepseek-v4-pro"
PROXY_VERSION = "v2.7a22-tool-output-trim-runtime-observability"

# USD per 1M tokens. Keep this table small and explicit.
# Source should be periodically checked against DeepSeek official pricing.
DEFAULT_MODEL_PRICING_USD_PER_1M: dict[str, dict[str, float]] = {
    "deepseek-v4-flash": {
        "input_cache_hit": 0.0028,
        "input_cache_miss": 0.14,
        "output": 0.28,
    },
}


def _now() -> int:
    return int(time.time())


def _response_id() -> str:
    return f"resp_{uuid.uuid4().hex}"


def _item_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def _stringify_content(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def _default_db_path() -> Path:
    configured = os.environ.get("DEEPSEEK_PROXY_DB_PATH")
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".local" / "state" / "deepseek-responses-proxy" / "responses.sqlite3"


def _store_info(store: Any) -> dict[str, Any]:
    info: dict[str, Any] = {
        "type": type(store).__name__,
    }
    db_path = getattr(store, "db_path", None)
    if db_path is not None:
        info["db_path"] = str(db_path)
    return info


def _thinking_enabled() -> bool:
    return _deepseek_thinking_config().get("type") == "enabled"


def _normalize_deepseek_reasoning_effort(value: Any) -> str | None:
    if value is None:
        return None

    normalized = str(value).strip().lower()
    if not normalized:
        return None

    if normalized in {"max", "xhigh"}:
        return "max"

    if normalized in {"minimal", "low", "medium", "high"}:
        return "high"

    return None


def _extract_request_reasoning_effort(payload: dict[str, Any]) -> str | None:
    direct = _normalize_deepseek_reasoning_effort(payload.get("reasoning_effort"))
    if direct is not None:
        return direct

    codex_direct = _normalize_deepseek_reasoning_effort(payload.get("model_reasoning_effort"))
    if codex_direct is not None:
        return codex_direct

    reasoning = payload.get("reasoning")
    if isinstance(reasoning, dict):
        for key in ["effort", "reasoning_effort", "model_reasoning_effort"]:
            value = _normalize_deepseek_reasoning_effort(reasoning.get(key))
            if value is not None:
                return value
    else:
        value = _normalize_deepseek_reasoning_effort(reasoning)
        if value is not None:
            return value

    return None


def _deepseek_reasoning_effort_config(payload: dict[str, Any] | None = None) -> str | None:
    """Return DeepSeek reasoning_effort for upstream ChatCompletions."""
    if not _thinking_enabled():
        return None

    if payload is not None:
        request_effort = _extract_request_reasoning_effort(payload)
        if request_effort is not None:
            return request_effort

    env_effort = _normalize_deepseek_reasoning_effort(
        os.environ.get("DEEPSEEK_REASONING_EFFORT", "high")
    )
    if env_effort is not None:
        return env_effort

    print(
        "[deepseek-responses-proxy] invalid DEEPSEEK_REASONING_EFFORT="
        f"{os.environ.get('DEEPSEEK_REASONING_EFFORT')!r}; falling back to 'high'"
    )
    return "high"


def _force_proxy_model_enabled() -> bool:
    return os.environ.get("DEEPSEEK_PROXY_FORCE_MODEL", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _select_upstream_model(request_model: str | None) -> str:
    env_model = os.environ.get("DEEPSEEK_PROXY_MODEL", "").strip()

    if _force_proxy_model_enabled() and env_model:
        return env_model

    if request_model:
        return request_model

    if env_model:
        return env_model

    return DEFAULT_MODEL

def _extract_usage_numbers(deepseek_response: dict[str, Any]) -> dict[str, int]:
    usage = deepseek_response.get("usage") or {}

    prompt_tokens = int(usage.get("prompt_tokens") or 0)
    completion_tokens = int(usage.get("completion_tokens") or 0)
    total_tokens = int(usage.get("total_tokens") or prompt_tokens + completion_tokens)

    prompt_details = usage.get("prompt_tokens_details") or {}
    completion_details = usage.get("completion_tokens_details") or {}

    cached_tokens = int(
        prompt_details.get("cached_tokens")
        or usage.get("prompt_cache_hit_tokens")
        or 0
    )
    reasoning_tokens = int(completion_details.get("reasoning_tokens") or 0)

    if cached_tokens < 0:
        cached_tokens = 0
    if cached_tokens > prompt_tokens:
        cached_tokens = prompt_tokens

    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "cached_tokens": cached_tokens,
        "reasoning_tokens": reasoning_tokens,
    }


def _pricing_config_path() -> Path:
    return Path(
        os.environ.get(
            "DEEPSEEK_PROXY_PRICING_PATH",
            str(Path(__file__).resolve().parent.parent / "config" / "pricing.json"),
        )
    ).expanduser()


def _load_model_pricing_usd_per_1m() -> dict[str, dict[str, float]]:
    path = _pricing_config_path()

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return deepcopy(DEFAULT_MODEL_PRICING_USD_PER_1M)
    except Exception as exc:
        print(f"[deepseek-responses-proxy] failed to load pricing config {path}: {exc}")
        return deepcopy(DEFAULT_MODEL_PRICING_USD_PER_1M)

    if not isinstance(data, dict):
        print(f"[deepseek-responses-proxy] invalid pricing config root in {path}: expected object")
        return deepcopy(DEFAULT_MODEL_PRICING_USD_PER_1M)

    pricing: dict[str, dict[str, float]] = {}
    required_keys = {"input_cache_hit", "input_cache_miss", "output"}

    for model, raw_prices in data.items():
        if not isinstance(model, str) or not isinstance(raw_prices, dict):
            print(f"[deepseek-responses-proxy] ignored invalid pricing entry for model={model!r}")
            continue

        if not required_keys.issubset(raw_prices):
            print(f"[deepseek-responses-proxy] ignored incomplete pricing entry for model={model!r}")
            continue

        try:
            pricing[model] = {
                "input_cache_hit": float(raw_prices["input_cache_hit"]),
                "input_cache_miss": float(raw_prices["input_cache_miss"]),
                "output": float(raw_prices["output"]),
            }
        except (TypeError, ValueError):
            print(f"[deepseek-responses-proxy] ignored non-numeric pricing entry for model={model!r}")

    if not pricing:
        return deepcopy(DEFAULT_MODEL_PRICING_USD_PER_1M)

    return pricing


def _estimate_cost_usd(model: str, usage_numbers: dict[str, int]) -> float:
    pricing = _load_model_pricing_usd_per_1m().get(model)
    if pricing is None:
        return 0.0

    prompt_tokens = usage_numbers["prompt_tokens"]
    cached_tokens = usage_numbers["cached_tokens"]
    cache_miss_tokens = max(0, prompt_tokens - cached_tokens)
    completion_tokens = usage_numbers["completion_tokens"]

    cost = (
        cached_tokens * pricing["input_cache_hit"]
        + cache_miss_tokens * pricing["input_cache_miss"]
        + completion_tokens * pricing["output"]
    ) / 1_000_000

    return float(cost)


def _debug_trace_enabled() -> bool:
    return _env_bool("DEEPSEEK_PROXY_DEBUG_TRACE", False)


def _debug_trace_dir() -> Path:
    return Path(os.environ.get("DEEPSEEK_PROXY_DEBUG_DIR", ".debug/traces")).expanduser()


def _debug_trace_content_mode() -> str:
    value = os.environ.get("DEEPSEEK_PROXY_DEBUG_CONTENT", "preview").strip().lower()
    if value not in {"none", "preview", "full"}:
        return "preview"
    return value


def _debug_trace_preview_chars() -> int:
    return max(0, _env_int("DEEPSEEK_PROXY_DEBUG_PREVIEW_CHARS", 1200))


def _debug_trace_max_event_chars() -> int:
    return max(1000, _env_int("DEEPSEEK_PROXY_DEBUG_MAX_EVENT_CHARS", 8000))


def _debug_trace_safe_response_id(response_id: str | None) -> str:
    safe = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in str(response_id or "unknown"))
    return safe or "unknown"


def _debug_trace_file(response_id: str | None) -> Path:
    return _debug_trace_dir() / f"trace-{_debug_trace_safe_response_id(response_id)}.jsonl"


def _debug_trace_summary(value: Any, *, label: str = "value") -> dict[str, Any]:
    try:
        chars = _json_char_size(value)
    except Exception:
        chars = len(str(value))

    if isinstance(value, list):
        kind = "list"
        count = len(value)
    elif isinstance(value, dict):
        kind = "dict"
        count = len(value)
    elif isinstance(value, str):
        kind = "str"
        count = len(value)
    else:
        kind = type(value).__name__
        count = None

    summary: dict[str, Any] = {
        "label": label,
        "type": kind,
        "chars": chars,
    }
    if count is not None:
        summary["count"] = count
    return summary


_DEBUG_TRACE_SECRET_KEYS = {"authorization", "api_key", "token", "password", "secret"}
_DEBUG_TRACE_LARGE_CONTENT_KEYS = {"messages", "input", "content", "reasoning_content", "arguments"}
_DEBUG_TRACE_SAFE_METADATA_LIST_KEYS = {"largest_outputs", "largest_messages", "targets", "trim_targets", "policy_targets", "retention_markers"}
_DEBUG_TRACE_SAFE_STRING_KEYS = {
    "event",
    "response_id",
    "version",
    "purpose",
    "policy",
    "reason",
    "model",
    "requested_model",
    "effective_model",
    "upstream_model",
    "summary_source",
    "error_type",
    "guard_reason",
    "judge_decision",
    "status",
    "url",
    "trace_path",
    "debug_command",
    "call_id",
    "tool_name",
    "name",
    "item_type",
    "category",
    "mode",
    "policy_name",
    "history_category",
    "reason",
    "trim_mode",
    "trim_reason",
    "role",
    "strategy",
    "semantic_type",
    "semantic_risk",
    "recommended_action",
    "policy_decision",
    "compression_strategy",
}


def _debug_trace_safe_string(value: str, *, key: str | None = None) -> Any:
    mode = _debug_trace_content_mode()
    if mode == "full":
        return value

    preview_chars = _debug_trace_preview_chars()
    if key in _DEBUG_TRACE_SAFE_STRING_KEYS and len(value) <= max(preview_chars, 256):
        return value

    if mode == "none":
        return _debug_trace_summary(value)

    truncated, changed = _truncate_middle_text(value, preview_chars)
    if changed:
        return {
            "preview": truncated,
            "original_chars": len(value),
            "truncated": True,
        }
    return value


def _debug_trace_sanitize(value: Any, *, key: str | None = None) -> Any:
    mode = _debug_trace_content_mode()
    key_lower = str(key or "").lower()

    if key_lower in _DEBUG_TRACE_SECRET_KEYS:
        return "[redacted]"

    if key in _DEBUG_TRACE_LARGE_CONTENT_KEYS:
        return _debug_trace_summary(value, label=key)

    if isinstance(value, (int, float, bool)) or value is None:
        return value

    if isinstance(value, str):
        return _debug_trace_safe_string(value, key=key)

    if isinstance(value, list):
        if key == "retention_markers":
            return [str(item) for item in value]
        if mode == "full" or key in _DEBUG_TRACE_SAFE_METADATA_LIST_KEYS:
            return [_debug_trace_sanitize(item) for item in value]
        return {
            **_debug_trace_summary(value),
            "preview": [_debug_trace_sanitize(item) for item in value[:5]],
            "truncated": len(value) > 5,
        }

    if isinstance(value, dict):
        if mode == "full":
            return value
        sanitized: dict[str, Any] = {}
        for item_key, item in list(value.items())[:50]:
            item_key_str = str(item_key)
            item_key_lower = item_key_str.lower()
            if item_key_lower in _DEBUG_TRACE_SECRET_KEYS:
                sanitized[item_key_str] = "[redacted]"
            elif item_key_str in _DEBUG_TRACE_LARGE_CONTENT_KEYS:
                sanitized[item_key_str] = _debug_trace_summary(item, label=item_key_str)
            else:
                sanitized[item_key_str] = _debug_trace_sanitize(item, key=item_key_str)
        if len(value) > 50:
            sanitized["_truncated_keys"] = len(value) - 50
        return sanitized

    return str(value)


def _debug_trace_event(response_id: str | None, event: str, **fields: Any) -> None:
    if not _debug_trace_enabled() or not response_id:
        return

    try:
        debug_dir = _debug_trace_dir()
        debug_dir.mkdir(parents=True, exist_ok=True)
        path = _debug_trace_file(response_id)
        entry: dict[str, Any] = {
            "ts": time.time(),
            "event": event,
            "response_id": response_id,
            "version": PROXY_VERSION,
        }
        for key, value in fields.items():
            entry[key] = _debug_trace_sanitize(value, key=key)

        line = json.dumps(entry, ensure_ascii=False, default=str)
        max_chars = _debug_trace_max_event_chars()
        if len(line) > max_chars:
            entry = {
                "ts": entry["ts"],
                "event": event,
                "response_id": response_id,
                "version": PROXY_VERSION,
                "truncated_event": True,
                "original_chars": len(line),
                "keys": sorted(fields.keys()),
            }
            line = json.dumps(entry, ensure_ascii=False, default=str)

        with path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

        latest = debug_dir / "latest.json"
        latest.write_text(
            json.dumps(
                {
                    "response_id": response_id,
                    "trace_path": str(path),
                    "updated_at": time.time(),
                    "event": event,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    except Exception as exc:
        print(f"[deepseek-responses-proxy] failed to write debug trace event: {exc}")


def _debug_trace_status() -> dict[str, Any]:
    debug_dir = _debug_trace_dir()
    latest_path = debug_dir / "latest.json"
    latest: dict[str, Any] | None = None
    if latest_path.exists():
        try:
            latest = json.loads(latest_path.read_text(encoding="utf-8"))
        except Exception as exc:
            latest = {"error": f"{type(exc).__name__}: {exc}"}

    trace_count = 0
    try:
        trace_count = len(list(debug_dir.glob("trace-*.jsonl"))) if debug_dir.exists() else 0
    except Exception:
        trace_count = 0

    return {
        "enabled": _debug_trace_enabled(),
        "dir": str(debug_dir),
        "content_mode": _debug_trace_content_mode(),
        "preview_chars": _debug_trace_preview_chars(),
        "max_event_chars": _debug_trace_max_event_chars(),
        "trace_count": trace_count,
        "latest": latest,
    }


def _debug_trace_latest(limit: int = 200) -> dict[str, Any]:
    status = _debug_trace_status()
    latest = status.get("latest")
    if not isinstance(latest, dict) or not latest.get("trace_path"):
        return {"status": "empty", "debug_trace": status, "events": []}

    path = Path(str(latest["trace_path"]))
    if not path.exists():
        return {"status": "missing", "debug_trace": status, "events": []}

    safe_limit = max(1, min(int(limit), 1000))
    lines = path.read_text(encoding="utf-8").splitlines()[-safe_limit:]
    events: list[Any] = []
    for line in lines:
        try:
            events.append(json.loads(line))
        except Exception:
            events.append({"raw": line})
    return {
        "status": "ok",
        "debug_trace": status,
        "trace_path": str(path),
        "events": events,
    }


def _debug_trace_json_chars(value: Any) -> int:
    try:
        return _json_char_size(value)
    except Exception:
        return len(str(value))


def _debug_trace_message_budget(messages: Any) -> dict[str, Any]:
    if not isinstance(messages, list):
        return {
            "message_count": 0,
            "total_chars": 0,
            "roles": {},
        }

    roles: dict[str, dict[str, int]] = {}
    for message in messages:
        if isinstance(message, dict):
            role = str(message.get("role") or "unknown")
        else:
            role = "unknown"
        item = roles.setdefault(role, {"count": 0, "chars": 0})
        item["count"] += 1
        item["chars"] += _debug_trace_json_chars(message)

    return {
        "message_count": len(messages),
        "total_chars": _debug_trace_json_chars({"messages": messages}),
        "roles": roles,
    }


def _latest_debug_event_named(event_name: str, *, limit: int = 200) -> dict[str, Any] | None:
    latest = _debug_trace_latest(limit=limit)
    events = latest.get("events") or []
    if not isinstance(events, list):
        return None

    for event in reversed(events):
        if isinstance(event, dict) and event.get("event") == event_name:
            return event
    return None


def _semantic_compaction_event_summary(event: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(event, dict):
        return {"present": False}

    keys = [
        "event",
        "enabled",
        "mode",
        "applied",
        "reason",
        "strategy",
        "message_count",
        "message_count_before",
        "message_count_after",
        "flattened_message_count",
        "candidate_count",
        "eligible_compaction_count",
        "eligible_policy_count",
        "structure_only_count",
        "preserve_count",
        "skipped_policy_count",
        "retained_recent_flattened_count",
        "compacted_count",
        "would_compact",
        "would_compact_count",
        "would_remove_chars_estimate",
        "chars_before",
        "chars_after",
        "chars_removed",
    ]
    summary: dict[str, Any] = {"present": True}
    for key in keys:
        if key in event:
            summary[key] = event.get(key)

    targets = event.get("targets")
    if isinstance(targets, list):
        summary["target_count"] = len(targets)
        if targets and isinstance(targets[0], dict):
            summary["top_target"] = {
                "index": targets[0].get("index"),
                "semantic_type": targets[0].get("semantic_type"),
                "semantic_risk": targets[0].get("semantic_risk"),
                "policy_decision": targets[0].get("policy_decision"),
                "recommended_action": targets[0].get("recommended_action"),
                "compression_strategy": targets[0].get("compression_strategy"),
                "estimated_remove_chars": targets[0].get("estimated_remove_chars"),
                "reason": targets[0].get("reason"),
            }
    return summary


def _semantic_compaction_rollout_assessment(
    *,
    config: dict[str, Any],
    latest: dict[str, Any],
) -> dict[str, Any]:
    payload_config = config.get("semantic_payload_compaction")
    if not isinstance(payload_config, dict):
        payload_config = {}

    mode = str(payload_config.get("mode") or "dry_run")
    audit = latest.get("semantic_audit")
    policy = latest.get("semantic_policy_dry_run")
    payload = latest.get("semantic_payload_compaction")

    if not isinstance(audit, dict):
        audit = {"present": False}
    if not isinstance(policy, dict):
        policy = {"present": False}
    if not isinstance(payload, dict):
        payload = {"present": False}

    blockers: list[str] = []
    warnings: list[str] = []

    if mode == "enabled":
        warnings.append("semantic_payload_compaction_already_enabled")
    elif mode != "dry_run":
        blockers.append("semantic_payload_compaction_not_in_dry_run")

    if not bool(audit.get("present")):
        blockers.append("semantic_audit_event_missing")
    if not bool(policy.get("present")):
        blockers.append("semantic_policy_dry_run_event_missing")
    if not bool(payload.get("present")):
        blockers.append("semantic_payload_compaction_event_missing")

    if bool(policy.get("present")) and not bool(policy.get("would_compact")):
        warnings.append("no_semantic_compaction_candidate_seen")
    if bool(payload.get("present")) and payload.get("mode") == "enabled" and payload.get("applied") is not False:
        warnings.append("latest_payload_event_not_dry_run")

    safe_to_enable = mode == "dry_run" and not blockers

    if mode == "enabled":
        recommendation = "monitor_enabled_rollout"
    elif safe_to_enable:
        recommendation = "safe_to_enable_for_limited_session"
    else:
        recommendation = "keep_dry_run_until_blockers_clear"

    return {
        "safe_to_enable_payload_compaction": safe_to_enable,
        "current_payload_mode": mode,
        "blockers": blockers,
        "warnings": warnings,
        "recommendation": recommendation,
    }


def _semantic_compaction_selftest_messages() -> list[dict[str, Any]]:
    low_risk_test = (
        "assistant_requested_tool_calls:\n"
        "tool_outputs:\n"
        "===== pytest =====\n"
        "....\n"
        "4 passed in 0.10s\n"
        + ("x" * 5000)
    )
    medium_stacktrace = (
        "assistant_requested_tool_calls:\n"
        "tool_outputs:\n"
        "Traceback (most recent call last):\n"
        "AssertionError: expected true\n"
        + ("y" * 5000)
    )
    high_chatty = (
        "assistant_requested_tool_calls:\n"
        "tool_outputs:\n"
        "\n• Running cd repo && pytest\n"
        "\n• Ran git status\n"
        "\n✔ You approved codex to always run commands\n"
        + ("z" * 5000)
    )
    recent_low_risk = (
        "assistant_requested_tool_calls:\n"
        "tool_outputs:\n"
        "===== pytest =====\n"
        "1 passed in 0.01s\n"
        + ("r" * 5000)
    )
    return [
        {"role": "developer", "content": "system"},
        {"role": "user", "content": low_risk_test},
        {"role": "user", "content": medium_stacktrace},
        {"role": "user", "content": high_chatty},
        {"role": "user", "content": recent_low_risk},
    ]


def _with_semantic_payload_env(overrides: dict[str, str], func: Any) -> Any:
    previous: dict[str, str | None] = {}
    for key, value in overrides.items():
        previous[key] = os.environ.get(key)
        os.environ[key] = value
    try:
        return func()
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _semantic_compaction_selftest_report() -> dict[str, Any]:
    messages = _semantic_compaction_selftest_messages()
    original_messages = deepcopy(messages)

    audit_report = _flattened_tool_transcript_semantic_audit(messages)
    policy_report = _flattened_tool_transcript_semantic_compaction_policy_dry_run(messages)

    payload_env = {
        "DEEPSEEK_PROXY_FLATTENED_TOOL_SEMANTIC_PAYLOAD_COMPACTION_PRESERVE_RECENT_MESSAGES": "1",
        "DEEPSEEK_PROXY_FLATTENED_TOOL_SEMANTIC_PAYLOAD_COMPACTION_MIN_MESSAGE_CHARS": "100",
        "DEEPSEEK_PROXY_FLATTENED_TOOL_SEMANTIC_PAYLOAD_COMPACTION_SUMMARY_CHARS": "900",
        "DEEPSEEK_PROXY_FLATTENED_TOOL_SEMANTIC_PAYLOAD_CANARY_ALLOW_ENABLED": "1",
    }

    def _dry_run_call() -> tuple[Any, dict[str, Any]]:
        os.environ["DEEPSEEK_PROXY_FLATTENED_TOOL_SEMANTIC_PAYLOAD_COMPACTION_MODE"] = "dry_run"
        return _apply_flattened_tool_transcript_semantic_payload_compaction(messages)

    dry_run_messages, dry_run_report = _with_semantic_payload_env(payload_env, _dry_run_call)

    def _enabled_call() -> tuple[Any, dict[str, Any]]:
        os.environ["DEEPSEEK_PROXY_FLATTENED_TOOL_SEMANTIC_PAYLOAD_COMPACTION_MODE"] = "enabled"
        return _apply_flattened_tool_transcript_semantic_payload_compaction(messages)

    enabled_messages, enabled_report = _with_semantic_payload_env(payload_env, _enabled_call)

    enabled_is_list = isinstance(enabled_messages, list)
    low_risk_compacted = bool(
        enabled_is_list
        and isinstance(enabled_messages[1], dict)
        and "[semantic flattened tool transcript compacted by CoDeepSeedeX]" in str(enabled_messages[1].get("content") or "")
    )
    medium_preserved = bool(enabled_is_list and enabled_messages[2] == original_messages[2])
    high_preserved = bool(enabled_is_list and enabled_messages[3] == original_messages[3])
    recent_preserved = bool(enabled_is_list and enabled_messages[4] == original_messages[4])

    synthetic_latest = {
        "semantic_audit": _semantic_compaction_event_summary(
            {"event": "flattened_tool_transcript_semantic_audit", **audit_report}
        ),
        "semantic_policy_dry_run": _semantic_compaction_event_summary(
            {"event": "flattened_tool_transcript_semantic_policy_dry_run", **policy_report}
        ),
        "semantic_payload_compaction": _semantic_compaction_event_summary(
            {"event": "flattened_tool_transcript_semantic_payload_compaction_applied", **dry_run_report}
        ),
    }
    synthetic_config = {
        "semantic_audit": {
            "enabled": True,
            "targets": max(1, _env_int("DEEPSEEK_PROXY_FLATTENED_TOOL_SEMANTIC_AUDIT_TARGETS", 12)),
        },
        "semantic_policy_dry_run": {
            "enabled": True,
            "summary_chars": max(128, _env_int("DEEPSEEK_PROXY_FLATTENED_TOOL_SEMANTIC_POLICY_SUMMARY_CHARS", 700)),
            "targets": max(1, _env_int("DEEPSEEK_PROXY_FLATTENED_TOOL_SEMANTIC_POLICY_TARGETS", 12)),
        },
        "semantic_payload_compaction": {
            "mode": "dry_run",
            "enabled": False,
            "preserve_recent_messages": 1,
            "min_message_chars": 100,
            "summary_chars": 900,
            "trace_targets": max(1, _env_int("DEEPSEEK_PROXY_FLATTENED_TOOL_SEMANTIC_PAYLOAD_COMPACTION_TRACE_TARGETS", 8)),
        },
    }

    assertions = {
        "original_messages_unchanged": messages == original_messages,
        "dry_run_returned_original_object": dry_run_messages is messages,
        "dry_run_not_applied": dry_run_report.get("applied") is False,
        "enabled_returned_copy": enabled_messages is not messages,
        "enabled_applied": enabled_report.get("applied") is True,
        "low_risk_test_output_compacted": low_risk_compacted,
        "medium_stacktrace_preserved": medium_preserved,
        "high_chatty_terminal_preserved": high_preserved,
        "recent_low_risk_preserved": recent_preserved,
    }
    passed = all(bool(value) for value in assertions.values())

    return {
        "status": "ok" if passed else "failed",
        "version": PROXY_VERSION,
        "kind": "semantic_compaction_selftest",
        "description": "Local semantic compaction self-test without upstream calls or SQLite writes.",
        "samples": {
            "message_count": len(messages),
            "low_risk_index": 1,
            "medium_stacktrace_index": 2,
            "high_chatty_terminal_index": 3,
            "recent_low_risk_index": 4,
        },
        "audit": {
            "flattened_message_count": audit_report.get("flattened_message_count"),
            "semantic_types": audit_report.get("semantic_types"),
            "semantic_risks": audit_report.get("semantic_risks"),
        },
        "policy_dry_run": {
            "candidate_count": policy_report.get("candidate_count"),
            "eligible_compaction_count": policy_report.get("eligible_compaction_count"),
            "would_compact": policy_report.get("would_compact"),
            "would_compact_count": policy_report.get("would_compact_count"),
            "would_remove_chars_estimate": policy_report.get("would_remove_chars_estimate"),
            "policy_decisions": policy_report.get("policy_decisions"),
        },
        "payload_dry_run": {
            "mode": dry_run_report.get("mode"),
            "applied": dry_run_report.get("applied"),
            "reason": dry_run_report.get("reason"),
            "compacted_count": dry_run_report.get("compacted_count"),
            "chars_removed": dry_run_report.get("chars_removed"),
        },
        "payload_enabled_simulation": {
            "mode": enabled_report.get("mode"),
            "applied": enabled_report.get("applied"),
            "reason": enabled_report.get("reason"),
            "candidate_count": enabled_report.get("candidate_count"),
            "eligible_policy_count": enabled_report.get("eligible_policy_count"),
            "compacted_count": enabled_report.get("compacted_count"),
            "skipped_policy_count": enabled_report.get("skipped_policy_count"),
            "retained_recent_flattened_count": enabled_report.get("retained_recent_flattened_count"),
            "chars_removed": enabled_report.get("chars_removed"),
            "targets": enabled_report.get("targets"),
        },
        "synthetic_rollout": _semantic_compaction_rollout_assessment(
            config=synthetic_config,
            latest=synthetic_latest,
        ),
        "assertions": assertions,
    }


def _semantic_payload_canary_env_config() -> dict[str, Any]:
    guard_env = os.environ.get("DEEPSEEK_PROXY_FLATTENED_TOOL_SEMANTIC_PAYLOAD_CANARY_GUARD", "1").strip().lower()
    allow_env = os.environ.get("DEEPSEEK_PROXY_FLATTENED_TOOL_SEMANTIC_PAYLOAD_CANARY_ALLOW_ENABLED", "0").strip().lower()
    invariant_env = os.environ.get("DEEPSEEK_PROXY_FLATTENED_TOOL_SEMANTIC_PAYLOAD_CANARY_REQUIRE_LOCAL_INVARIANTS", "1").strip().lower()

    return {
        "guard_enabled": guard_env not in {"0", "false", "off", "no"},
        "allow_enabled": allow_env in {"1", "true", "on", "yes"},
        "require_local_invariants": invariant_env not in {"0", "false", "off", "no"},
        "allow_env_var": "DEEPSEEK_PROXY_FLATTENED_TOOL_SEMANTIC_PAYLOAD_CANARY_ALLOW_ENABLED",
        "mode_env_var": "DEEPSEEK_PROXY_FLATTENED_TOOL_SEMANTIC_PAYLOAD_COMPACTION_MODE",
    }


def _semantic_payload_canary_local_invariants() -> dict[str, Any]:
    messages = _semantic_compaction_selftest_messages()
    audit_report = _flattened_tool_transcript_semantic_audit(messages)
    policy_report = _flattened_tool_transcript_semantic_compaction_policy_dry_run(messages)

    semantic_risks = audit_report.get("semantic_risks") or {}
    low_count = int((semantic_risks.get("low") or {}).get("count") or 0) if isinstance(semantic_risks, dict) else 0
    medium_count = int((semantic_risks.get("medium") or {}).get("count") or 0) if isinstance(semantic_risks, dict) else 0
    high_count = int((semantic_risks.get("high") or {}).get("count") or 0) if isinstance(semantic_risks, dict) else 0

    passed = (
        int(audit_report.get("flattened_message_count") or 0) == 4
        and low_count >= 2
        and medium_count >= 1
        and high_count >= 1
        and bool(policy_report.get("would_compact")) is True
        and int(policy_report.get("eligible_compaction_count") or 0) == 2
    )

    return {
        "passed": passed,
        "audit_flattened_message_count": audit_report.get("flattened_message_count"),
        "low_risk_count": low_count,
        "medium_risk_count": medium_count,
        "high_risk_count": high_count,
        "policy_would_compact": policy_report.get("would_compact"),
        "policy_eligible_compaction_count": policy_report.get("eligible_compaction_count"),
    }


def _semantic_payload_canary_guard_for_mode(mode: str) -> dict[str, Any]:
    config = _semantic_payload_canary_env_config()
    normalized_mode = str(mode or "dry_run")

    blockers: list[str] = []
    warnings: list[str] = []

    if normalized_mode != "enabled":
        return {
            "allowed": True,
            "mode": normalized_mode,
            "config": config,
            "blockers": [],
            "warnings": [],
            "local_invariants": None,
            "reason": "not_enabled_mode",
        }

    local_invariants = None
    if not bool(config.get("guard_enabled")):
        warnings.append("semantic_payload_canary_guard_disabled")
        return {
            "allowed": True,
            "mode": normalized_mode,
            "config": config,
            "blockers": blockers,
            "warnings": warnings,
            "local_invariants": local_invariants,
            "reason": "guard_disabled",
        }

    if not bool(config.get("allow_enabled")):
        blockers.append("semantic_payload_canary_allow_enabled_not_set")

    if bool(config.get("require_local_invariants")):
        local_invariants = _semantic_payload_canary_local_invariants()
        if not bool(local_invariants.get("passed")):
            blockers.append("semantic_payload_canary_local_invariants_failed")

    allowed = not blockers
    return {
        "allowed": allowed,
        "mode": normalized_mode,
        "config": config,
        "blockers": blockers,
        "warnings": warnings,
        "local_invariants": local_invariants,
        "reason": "allowed" if allowed else "blocked",
    }


def _semantic_compaction_canary_check_report() -> dict[str, Any]:
    runtime_status = _semantic_compaction_runtime_status()
    selftest_report = _semantic_compaction_selftest_report()
    guard = _semantic_payload_canary_guard_for_mode("enabled")
    payload_config = _flattened_tool_semantic_payload_compaction_env_config()

    blockers: list[str] = []
    warnings: list[str] = []

    if selftest_report.get("status") != "ok":
        blockers.append("semantic_selftest_failed")

    if not bool(guard.get("allowed")):
        blockers.extend(str(item) for item in guard.get("blockers") or [])

    runtime_rollout = runtime_status.get("rollout") if isinstance(runtime_status, dict) else None
    if isinstance(runtime_rollout, dict) and not bool(runtime_rollout.get("safe_to_enable_payload_compaction")):
        warnings.append("runtime_rollout_not_yet_safe_based_on_live_trace")

    if payload_config.get("mode") == "enabled":
        warnings.append("semantic_payload_compaction_already_enabled")

    blockers = sorted(set(blockers))
    warnings = sorted(set(warnings))
    ready = not blockers

    return {
        "status": "ok" if ready else "blocked",
        "version": PROXY_VERSION,
        "kind": "semantic_compaction_canary_check",
        "ready_for_limited_enabled_session": ready,
        "current_payload_mode": payload_config.get("mode"),
        "required_enable_env": {
            "DEEPSEEK_PROXY_FLATTENED_TOOL_SEMANTIC_PAYLOAD_CANARY_ALLOW_ENABLED": "1",
            "DEEPSEEK_PROXY_FLATTENED_TOOL_SEMANTIC_PAYLOAD_COMPACTION_MODE": "enabled",
        },
        "blockers": blockers,
        "warnings": warnings,
        "guard": guard,
        "selftest": {
            "status": selftest_report.get("status"),
            "kind": selftest_report.get("kind"),
            "assertions": selftest_report.get("assertions"),
            "payload_enabled_simulation": selftest_report.get("payload_enabled_simulation"),
            "synthetic_rollout": selftest_report.get("synthetic_rollout"),
        },
        "runtime_rollout": runtime_rollout,
    }


def _semantic_compaction_runtime_status() -> dict[str, Any]:
    audit_enabled_env = os.environ.get("DEEPSEEK_PROXY_FLATTENED_TOOL_SEMANTIC_AUDIT", "1").strip().lower()
    policy_enabled_env = os.environ.get("DEEPSEEK_PROXY_FLATTENED_TOOL_SEMANTIC_POLICY_DRY_RUN", "1").strip().lower()
    audit_enabled = audit_enabled_env not in {"0", "false", "off", "no"}
    policy_enabled = policy_enabled_env not in {"0", "false", "off", "no"}

    policy_summary_chars = max(
        128,
        _env_int("DEEPSEEK_PROXY_FLATTENED_TOOL_SEMANTIC_POLICY_SUMMARY_CHARS", 700),
    )
    policy_targets = max(
        1,
        _env_int("DEEPSEEK_PROXY_FLATTENED_TOOL_SEMANTIC_POLICY_TARGETS", 12),
    )
    payload_config = _flattened_tool_semantic_payload_compaction_env_config()

    latest_audit = _latest_debug_event_named("flattened_tool_transcript_semantic_audit")
    latest_policy = _latest_debug_event_named("flattened_tool_transcript_semantic_policy_dry_run")
    latest_payload = _latest_debug_event_named("flattened_tool_transcript_semantic_payload_compaction_applied")

    config = {
        "semantic_audit": {
            "enabled": audit_enabled,
            "targets": max(1, _env_int("DEEPSEEK_PROXY_FLATTENED_TOOL_SEMANTIC_AUDIT_TARGETS", 12)),
        },
        "semantic_policy_dry_run": {
            "enabled": policy_enabled,
            "summary_chars": policy_summary_chars,
            "targets": policy_targets,
        },
        "semantic_payload_compaction": {
            "mode": payload_config.get("mode"),
            "enabled": payload_config.get("mode") == "enabled",
            "preserve_recent_messages": payload_config.get("preserve_recent_messages"),
            "min_message_chars": payload_config.get("min_message_chars"),
            "summary_chars": payload_config.get("summary_chars"),
            "trace_targets": payload_config.get("trace_targets"),
        },
        "semantic_payload_canary": _semantic_payload_canary_env_config(),
    }
    latest = {
        "semantic_audit": _semantic_compaction_event_summary(latest_audit),
        "semantic_policy_dry_run": _semantic_compaction_event_summary(latest_policy),
        "semantic_payload_compaction": _semantic_compaction_event_summary(latest_payload),
    }
    return {
        "config": config,
        "latest": latest,
        "rollout": _semantic_compaction_rollout_assessment(config=config, latest=latest),
    }


def _long_session_observability_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _long_session_context_chars(event: dict[str, Any]) -> int:
    for key in (
        "chat_payload_chars",
        "messages_total_chars",
        "messages_chars",
        "payload_chars",
        "estimated_messages_chars_before",
        "total_chars",
    ):
        if key in event:
            return _long_session_observability_int(event.get(key))
    return 0


def _long_session_usage_prompt_tokens(event: dict[str, Any]) -> int:
    usage = event.get("usage")
    if isinstance(usage, dict):
        for key in ("prompt_tokens", "input_tokens", "total_prompt_tokens"):
            if key in usage:
                return _long_session_observability_int(usage.get(key))
    for key in ("prompt_tokens", "input_tokens"):
        if key in event:
            return _long_session_observability_int(event.get(key))
    return 0


def _long_session_observability_from_events(events: Any, *, limit: int = 200) -> dict[str, Any]:
    if not isinstance(events, list):
        events = []

    normalized_events = [event for event in events if isinstance(event, dict)]
    response_ids = sorted(
        {
            str(event.get("response_id"))
            for event in normalized_events
            if event.get("response_id")
        }
    )
    context_events = [
        event for event in normalized_events if event.get("event") == "context_budget_breakdown"
    ]
    semantic_payload_events = [
        event
        for event in normalized_events
        if event.get("event") == "flattened_tool_transcript_semantic_payload_compaction_applied"
    ]
    tool_output_events = [
        event for event in normalized_events if event.get("event") == "tool_output_budget_breakdown"
    ]
    tool_output_trim_events = [
        event for event in normalized_events if event.get("event") == "tool_output_trim_applied"
    ]
    primary_usage_events = [
        event
        for event in normalized_events
        if event.get("event") == "upstream_call_finished" and event.get("purpose") == "primary"
    ]

    context_series: list[dict[str, Any]] = []
    for index, event in enumerate(context_events):
        chars = _long_session_context_chars(event)
        context_series.append(
            {
                "ordinal": index,
                "response_id": event.get("response_id"),
                "ts": event.get("ts"),
                "chars": chars,
                "message_count": event.get("message_count"),
                "conversation_message_count": event.get("conversation_message_count"),
                "tool_message_chars": event.get("tool_message_chars"),
                "compaction_summary_chars": event.get("compaction_summary_chars"),
            }
        )

    context_chars = [int(item.get("chars") or 0) for item in context_series]
    latest_context_chars = context_chars[-1] if context_chars else 0
    max_context_chars = max(context_chars) if context_chars else 0
    min_context_chars = min(context_chars) if context_chars else 0
    growth_chars = latest_context_chars - context_chars[0] if len(context_chars) >= 2 else 0

    semantic_applied = [
        event for event in semantic_payload_events if bool(event.get("applied"))
    ]
    semantic_blocked = [
        event
        for event in semantic_payload_events
        if event.get("reason") == "semantic_payload_canary_guard_blocked_enabled"
    ]
    semantic_chars_removed = sum(
        _long_session_observability_int(event.get("chars_removed"))
        for event in semantic_payload_events
    )
    semantic_compacted_count = sum(
        _long_session_observability_int(event.get("compacted_count"))
        for event in semantic_payload_events
    )

    tool_truncated_count = sum(1 for event in tool_output_events if event.get("truncated_event"))
    tool_latest = tool_output_events[-1] if tool_output_events else None
    max_context_event = max(context_events, key=_long_session_context_chars) if context_events else None
    max_tool_output_event = max(
        tool_output_events,
        key=lambda event: _long_session_observability_int(event.get("function_call_output_chars")),
    ) if tool_output_events else None

    tool_trim_applied = [
        event for event in tool_output_trim_events if bool(event.get("applied"))
    ]
    tool_trim_enabled_count = sum(
        1
        for event in tool_output_trim_events
        if bool(event.get("enabled"))
        or str(event.get("effective_mode") or event.get("mode") or "") == "enabled"
    )
    tool_trim_chars_removed = sum(
        _long_session_observability_int(event.get("chars_removed"))
        for event in tool_output_trim_events
    )
    tool_trim_item_count = sum(
        _long_session_observability_int(event.get("trimmed_item_count"))
        for event in tool_output_trim_events
    )
    tool_trim_by_category: dict[str, dict[str, int]] = {}
    tool_trim_target_trace_count = 0
    for event in tool_output_trim_events:
        targets = event.get("targets")
        if not isinstance(targets, list):
            continue
        for target in targets:
            if not isinstance(target, dict):
                continue
            category = str(target.get("category") or "unknown")
            tool_trim_target_trace_count += 1
            category_summary = tool_trim_by_category.setdefault(
                category,
                {"trimmed_item_count": 0, "estimated_remove_chars": 0},
            )
            category_summary["trimmed_item_count"] += 1
            category_summary["estimated_remove_chars"] += _long_session_observability_int(
                target.get("estimated_remove_chars")
            )
    tool_trim_by_category = dict(sorted(tool_trim_by_category.items()))
    image_payload_trim_count = int(
        tool_trim_by_category.get("image_payload", {}).get("trimmed_item_count", 0)
    )

    semantic_audit_events = [
        event for event in normalized_events if event.get("event") == "flattened_tool_transcript_semantic_audit"
    ]
    semantic_policy_events = [
        event for event in normalized_events if event.get("event") == "flattened_tool_transcript_semantic_policy_dry_run"
    ]

    prompt_tokens = [_long_session_usage_prompt_tokens(event) for event in primary_usage_events]
    latest_prompt_tokens = prompt_tokens[-1] if prompt_tokens else 0
    max_prompt_tokens = max(prompt_tokens) if prompt_tokens else 0

    if semantic_blocked:
        recommendation = "keep_dry_run_or_fix_canary"
    elif semantic_applied or tool_trim_applied:
        recommendation = "monitor_limited_enabled_session"
    elif semantic_payload_events or tool_output_trim_events:
        recommendation = "continue_dry_run_observation"
    elif context_events:
        recommendation = "collect_semantic_trace_events_before_enabled"
    else:
        recommendation = "collect_more_trace_data"

    return {
        "status": "ok",
        "version": PROXY_VERSION,
        "kind": "runtime_long_session_observability",
        "limit": max(1, min(int(limit), 1000)),
        "trace_event_count": len(normalized_events),
        "response_count": len(response_ids),
        "response_ids_tail": response_ids[-20:],
        "context_budget": {
            "event_count": len(context_events),
            "latest_chars": latest_context_chars,
            "max_chars": max_context_chars,
            "min_chars": min_context_chars,
            "growth_chars": growth_chars,
            "max_event": max_context_event,
            "series_tail": context_series[-20:],
        },
        "semantic_trace": {
            "audit_event_count": len(semantic_audit_events),
            "policy_dry_run_event_count": len(semantic_policy_events),
            "payload_event_count": len(semantic_payload_events),
        },
        "semantic_payload": {
            "event_count": len(semantic_payload_events),
            "applied_count": len(semantic_applied),
            "blocked_count": len(semantic_blocked),
            "compacted_count": semantic_compacted_count,
            "chars_removed": semantic_chars_removed,
            "latest_event": semantic_payload_events[-1] if semantic_payload_events else None,
        },
        "tool_output_budget": {
            "event_count": len(tool_output_events),
            "truncated_count": tool_truncated_count,
            "latest_event": tool_latest,
            "max_output_event": max_tool_output_event,
        },
        "tool_output_trim": {
            "event_count": len(tool_output_trim_events),
            "enabled_event_count": tool_trim_enabled_count,
            "applied_count": len(tool_trim_applied),
            "chars_removed": tool_trim_chars_removed,
            "trimmed_item_count": tool_trim_item_count,
            "target_trace_count": tool_trim_target_trace_count,
            "by_category": tool_trim_by_category,
            "image_payload_trim_count": image_payload_trim_count,
            "latest_event": tool_output_trim_events[-1] if tool_output_trim_events else None,
        },
        "primary_usage": {
            "event_count": len(primary_usage_events),
            "latest_prompt_tokens": latest_prompt_tokens,
            "max_prompt_tokens": max_prompt_tokens,
        },
        "recommendation": recommendation,
    }


def _long_session_read_trace_file(path: Path, *, per_file_limit: int = 200) -> list[dict[str, Any]]:
    if not path.exists() or not path.is_file():
        return []

    safe_limit = max(1, min(int(per_file_limit), 1000))
    events: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()[-safe_limit:]
    except Exception:
        return []

    for line in lines:
        try:
            event = json.loads(line)
        except Exception:
            continue
        if isinstance(event, dict):
            event.setdefault("_trace_file", str(path))
            events.append(event)
    return events


def _long_session_observability_report(*, limit: int = 200, mode: str = "aggregate") -> dict[str, Any]:
    normalized_limit = max(1, min(int(limit), 1000))
    normalized_mode = str(mode or "aggregate").strip().lower()
    if normalized_mode not in {"aggregate", "latest"}:
        normalized_mode = "aggregate"

    if normalized_mode == "latest":
        latest = _debug_trace_latest(limit=normalized_limit)
        events = latest.get("events") if isinstance(latest, dict) else []
        report = _long_session_observability_from_events(events, limit=normalized_limit)
        report["mode"] = "latest"
        report["trace_file_count"] = 1 if isinstance(latest, dict) and latest.get("trace_path") else 0
        report["aggregate"] = {
            "mode": "latest",
            "source": "latest_trace_only",
            "debug_dir": None,
            "trace_file_count": report["trace_file_count"],
            "scanned_trace_file_count": report["trace_file_count"],
            "latest_trace_path": latest.get("trace_path") if isinstance(latest, dict) else None,
        }
        report["trace"] = {
            "status": latest.get("status") if isinstance(latest, dict) else "unknown",
            "trace_path": latest.get("trace_path") if isinstance(latest, dict) else None,
            "response_id": latest.get("response_id") if isinstance(latest, dict) else None,
            "debug_enabled": latest.get("enabled") if isinstance(latest, dict) else None,
        }
        return report

    status = _debug_trace_status()
    debug_dir = Path(str(status.get("dir") or ""))
    trace_files: list[Path] = []
    try:
        trace_files = sorted(
            [path for path in debug_dir.glob("trace-*.jsonl") if path.is_file()],
            key=lambda path: (path.stat().st_mtime, path.name),
        )
    except Exception:
        trace_files = []

    selected_files = trace_files[-normalized_limit:]
    events: list[dict[str, Any]] = []
    per_file_limit = 200
    for path in selected_files:
        events.extend(_long_session_read_trace_file(path, per_file_limit=per_file_limit))

    report = _long_session_observability_from_events(events, limit=normalized_limit)
    report["mode"] = "aggregate"
    report["trace_file_count"] = len(trace_files)
    report["aggregate"] = {
        "mode": "aggregate",
        "source": "debug_dir_trace_files",
        "debug_dir": str(debug_dir),
        "trace_file_count": len(trace_files),
        "scanned_trace_file_count": len(selected_files),
        "per_file_event_limit": per_file_limit,
        "selected_trace_files_tail": [str(path) for path in selected_files[-20:]],
    }
    report["trace"] = {
        "status": "ok" if trace_files else "empty",
        "trace_path": None,
        "response_id": None,
        "debug_enabled": status.get("enabled"),
        "debug_dir": status.get("dir"),
        "latest": status.get("latest"),
    }
    return report


def _context_budget_breakdown(
    *,
    request_payload: dict[str, Any],
    input_value: Any,
    messages_before_compaction: list[dict[str, Any]],
    messages_after_compaction: list[dict[str, Any]],
    messages_for_deepseek: list[dict[str, Any]],
    deepseek_tools: list[dict[str, Any]] | None,
    chat_payload: dict[str, Any],
    context_compaction_report: dict[str, Any],
) -> dict[str, Any]:
    raw_tools = request_payload.get("tools") or []
    normalized_tools = deepseek_tools or []
    chat_payload_tools = chat_payload.get("tools") or []
    chat_payload_messages = chat_payload.get("messages") or []

    policy_decision = context_compaction_report.get("policy_decision")
    if not isinstance(policy_decision, dict):
        policy_decision = {}

    return {
        "request_payload_chars": _debug_trace_json_chars(request_payload),
        "current_input_chars": _debug_trace_json_chars(input_value),
        "raw_tool_count": len(raw_tools) if isinstance(raw_tools, list) else 0,
        "raw_tools_chars": _debug_trace_json_chars({"tools": raw_tools}),
        "normalized_tool_count": len(normalized_tools),
        "normalized_tools_chars": _debug_trace_json_chars({"tools": normalized_tools}),
        "chat_payload_chars": _debug_trace_json_chars(chat_payload),
        "chat_payload_message_count": len(chat_payload_messages) if isinstance(chat_payload_messages, list) else 0,
        "chat_payload_messages_chars": _debug_trace_json_chars({"messages": chat_payload_messages}),
        "chat_payload_tool_count": len(chat_payload_tools) if isinstance(chat_payload_tools, list) else 0,
        "chat_payload_tools_chars": _debug_trace_json_chars({"tools": chat_payload_tools}),
        "messages_before_compaction": _debug_trace_message_budget(messages_before_compaction),
        "messages_after_compaction": _debug_trace_message_budget(messages_after_compaction),
        "messages_for_deepseek": _debug_trace_message_budget(messages_for_deepseek),
        "compaction": {
            "compacted": context_compaction_report.get("compacted"),
            "reason": context_compaction_report.get("reason"),
            "policy": context_compaction_report.get("policy"),
            "before_chars": context_compaction_report.get("before_chars"),
            "after_chars": context_compaction_report.get("after_chars"),
            "chars_removed": context_compaction_report.get("chars_removed"),
            "message_count_before": context_compaction_report.get("message_count_before"),
            "message_count_after": context_compaction_report.get("message_count_after"),
            "effective_trigger_chars": policy_decision.get("effective_trigger_chars"),
            "effective_target_chars": policy_decision.get("effective_target_chars"),
            "emergency_chars": policy_decision.get("emergency_chars"),
            "min_new_chars": policy_decision.get("min_new_chars"),
            "min_turns": policy_decision.get("min_turns"),
            "growth": policy_decision.get("growth"),
        },
    }


def _tool_output_budget_env_config() -> dict[str, int]:
    return {
        "largest_items": max(1, _env_int("DEEPSEEK_PROXY_TOOL_OUTPUT_BUDGET_LARGEST_ITEMS", 12)),
        "warn_item_chars": max(1, _env_int("DEEPSEEK_PROXY_TOOL_OUTPUT_WARN_ITEM_CHARS", 12000)),
        "warn_total_chars": max(1, _env_int("DEEPSEEK_PROXY_TOOL_OUTPUT_WARN_TOTAL_CHARS", 80000)),
    }


def _tool_output_trim_dry_run_env_config() -> dict[str, Any]:
    mode = os.environ.get("DEEPSEEK_PROXY_TOOL_OUTPUT_TRIM_MODE", "dry_run").strip().lower()
    if mode not in {"off", "dry_run", "enabled"}:
        mode = "dry_run"
    return {
        "mode": mode,
        "max_item_chars": max(1, _env_int("DEEPSEEK_PROXY_TOOL_OUTPUT_MAX_ITEM_CHARS", 12000)),
        "max_total_chars": max(1, _env_int("DEEPSEEK_PROXY_TOOL_OUTPUT_MAX_TOTAL_CHARS", 80000)),
        "keep_head_chars": max(0, _env_int("DEEPSEEK_PROXY_TOOL_OUTPUT_KEEP_HEAD_CHARS", 3000)),
        "keep_tail_chars": max(0, _env_int("DEEPSEEK_PROXY_TOOL_OUTPUT_KEEP_TAIL_CHARS", 3000)),
        "max_targets": max(1, _env_int("DEEPSEEK_PROXY_TOOL_OUTPUT_TRIM_MAX_TARGETS", 12)),
        "notice_chars": max(128, _env_int("DEEPSEEK_PROXY_TOOL_OUTPUT_TRIM_NOTICE_CHARS", 512)),
    }


def _estimate_tool_output_trim_after_chars(original_chars: int, config: dict[str, Any]) -> int:
    keep_total = int(config["keep_head_chars"]) + int(config["keep_tail_chars"]) + int(config["notice_chars"])
    return min(int(original_chars), max(1, keep_total))


def _classify_tool_output_category(tool_name: str | None) -> str:
    name = str(tool_name or "").strip().lower()
    if not name:
        return "unknown"

    image_names = {
        "view_image",
        "open_image",
        "display_image",
        "show_image",
        "render_image",
        "image_viewer",
        "python.open_image",
        "container.open_image",
    }
    if (
        name in image_names
        or name.endswith(".view_image")
        or name.endswith("_view_image")
        or name.endswith(".open_image")
        or name.endswith("_open_image")
        or ("image" in name and any(marker in name for marker in ("view", "open", "display", "show", "render")))
    ):
        return "image_payload"

    if any(marker in name for marker in ("interactive", "session", "feed_chars", "stdin", "write_stdin", "send_stdin")):
        return "interactive_shell"

    if any(marker in name for marker in ("search", "web", "browser", "serp", "query")):
        return "search"

    if any(marker in name for marker in ("file", "read", "mclick", "open_file")):
        return "file_read"

    if any(marker in name for marker in ("ask", "approval", "user", "confirm")):
        return "user_interaction"

    if any(marker in name for marker in ("shell", "bash", "zsh", "powershell", "cmd", "exec", "terminal", "python")):
        return "shell_command"

    return "unknown"



def _tool_output_category_policy(category: str) -> dict[str, Any]:
    category = str(category or "unknown")
    defaults: dict[str, dict[str, int]] = {
        "interactive_shell": {
            "max_item_chars": 6000,
            "keep_head_chars": 1000,
            "keep_tail_chars": 3000,
            "notice_chars": 512,
        },
        "shell_command": {
            "max_item_chars": 9000,
            "keep_head_chars": 1500,
            "keep_tail_chars": 4500,
            "notice_chars": 512,
        },
        "search": {
            "max_item_chars": 16000,
            "keep_head_chars": 4000,
            "keep_tail_chars": 4000,
            "notice_chars": 512,
        },
        "file_read": {
            "max_item_chars": 20000,
            "keep_head_chars": 6000,
            "keep_tail_chars": 6000,
            "notice_chars": 512,
        },
        "user_interaction": {
            "max_item_chars": 50000,
            "keep_head_chars": 10000,
            "keep_tail_chars": 10000,
            "notice_chars": 512,
        },
        "image_payload": {
            "max_item_chars": 6000,
            "keep_head_chars": 1200,
            "keep_tail_chars": 1200,
            "notice_chars": 512,
        },
        "unknown": {
            "max_item_chars": 12000,
            "keep_head_chars": 3000,
            "keep_tail_chars": 3000,
            "notice_chars": 512,
        },
    }
    base = dict(defaults.get(category, defaults["unknown"]))
    prefix = "DEEPSEEK_PROXY_TOOL_OUTPUT_" + category.upper() + "_"
    base["max_item_chars"] = max(1, _env_int(prefix + "MAX_ITEM_CHARS", int(base["max_item_chars"])))
    base["keep_head_chars"] = max(0, _env_int(prefix + "KEEP_HEAD_CHARS", int(base["keep_head_chars"])))
    base["keep_tail_chars"] = max(0, _env_int(prefix + "KEEP_TAIL_CHARS", int(base["keep_tail_chars"])))
    base["notice_chars"] = max(128, _env_int(prefix + "NOTICE_CHARS", int(base["notice_chars"])))
    base["policy_name"] = category
    return base


def _estimate_tool_output_trim_after_chars_for_policy(original_chars: int, policy: dict[str, Any]) -> int:
    keep_total = int(policy["keep_head_chars"]) + int(policy["keep_tail_chars"]) + int(policy["notice_chars"])
    return min(int(original_chars), max(1, keep_total))


def _tool_output_policy_dry_run(
    outputs: list[dict[str, Any]],
    *,
    total_output_chars: int,
) -> dict[str, Any]:
    mode = os.environ.get("DEEPSEEK_PROXY_TOOL_OUTPUT_POLICY_DRY_RUN", "1").strip().lower()
    enabled = mode not in {"0", "false", "off", "no"}
    max_total_chars = max(1, _env_int("DEEPSEEK_PROXY_TOOL_OUTPUT_POLICY_MAX_TOTAL_CHARS", 80000))
    max_targets = max(1, _env_int("DEEPSEEK_PROXY_TOOL_OUTPUT_POLICY_MAX_TARGETS", 20))

    category_counts: dict[str, int] = {}
    category_chars: dict[str, int] = {}
    category_output_chars: dict[str, int] = {}
    policies: dict[str, dict[str, Any]] = {}

    for output in outputs:
        category = str(output.get("category") or "unknown")
        item_chars = int(output.get("item_chars") or 0)
        output_chars = int(output.get("output_chars") or 0)
        category_counts[category] = int(category_counts.get(category, 0)) + 1
        category_chars[category] = int(category_chars.get(category, 0)) + item_chars
        category_output_chars[category] = int(category_output_chars.get(category, 0)) + output_chars
        if category not in policies:
            policies[category] = _tool_output_category_policy(category)

    if not enabled:
        return {
            "enabled": False,
            "applied": False,
            "would_trim": False,
            "category_counts": category_counts,
            "category_chars": category_chars,
            "category_output_chars": category_output_chars,
            "policies": policies,
            "targets": [],
            "would_remove_chars_estimate": 0,
            "estimated_total_output_chars_before": int(total_output_chars),
            "estimated_total_output_chars_after": int(total_output_chars),
            "target_total_output_chars": max_total_chars,
            "unmet_total_budget_chars": max(0, int(total_output_chars) - max_total_chars),
            "total_budget_reachable": int(total_output_chars) <= max_total_chars,
        }

    targets_by_call_id: dict[str, dict[str, Any]] = {}

    for output in outputs:
        category = str(output.get("category") or "unknown")
        policy = policies.get(category) or _tool_output_category_policy(category)
        item_chars = int(output.get("item_chars") or 0)
        if item_chars <= int(policy["max_item_chars"]):
            continue
        after_chars = _estimate_tool_output_trim_after_chars_for_policy(item_chars, policy)
        call_id = str(output.get("call_id") or "")
        targets_by_call_id[call_id] = {
            **output,
            "policy_name": str(policy.get("policy_name") or category),
            "trim_reason": "category_item_exceeds_max_item_chars",
            "original_chars": item_chars,
            "estimated_after_chars": after_chars,
            "estimated_remove_chars": max(0, item_chars - after_chars),
        }

    estimated_after = int(total_output_chars) - sum(
        int(target.get("estimated_remove_chars") or 0)
        for target in targets_by_call_id.values()
    )

    if estimated_after > max_total_chars:
        for output in sorted(outputs, key=lambda item: int(item.get("item_chars") or 0), reverse=True):
            if estimated_after <= max_total_chars:
                break
            call_id = str(output.get("call_id") or "")
            if call_id in targets_by_call_id:
                continue

            category = str(output.get("category") or "unknown")
            policy = policies.get(category) or _tool_output_category_policy(category)
            item_chars = int(output.get("item_chars") or 0)
            after_chars = _estimate_tool_output_trim_after_chars_for_policy(item_chars, policy)
            remove_chars = max(0, item_chars - after_chars)
            if remove_chars <= 0:
                continue

            targets_by_call_id[call_id] = {
                **output,
                "policy_name": str(policy.get("policy_name") or category),
                "trim_reason": "category_total_output_exceeds_max_total_chars",
                "original_chars": item_chars,
                "estimated_after_chars": after_chars,
                "estimated_remove_chars": remove_chars,
            }
            estimated_after -= remove_chars

    targets = sorted(
        targets_by_call_id.values(),
        key=lambda item: int(item.get("estimated_remove_chars") or 0),
        reverse=True,
    )
    would_remove = sum(int(item.get("estimated_remove_chars") or 0) for item in targets)
    estimated_total_after = max(0, int(total_output_chars) - would_remove)
    unmet = max(0, estimated_total_after - max_total_chars)

    would_remove_by_category: dict[str, int] = {}
    would_trim_count_by_category: dict[str, int] = {}
    for target in targets:
        category = str(target.get("category") or "unknown")
        would_remove_by_category[category] = int(would_remove_by_category.get(category, 0)) + int(
            target.get("estimated_remove_chars") or 0
        )
        would_trim_count_by_category[category] = int(would_trim_count_by_category.get(category, 0)) + 1

    compact_policies = {
        category: {
            "policy_name": policy.get("policy_name"),
            "max_item_chars": policy.get("max_item_chars"),
            "keep_head_chars": policy.get("keep_head_chars"),
            "keep_tail_chars": policy.get("keep_tail_chars"),
            "notice_chars": policy.get("notice_chars"),
        }
        for category, policy in policies.items()
    }

    trace_target_limit = min(
        max_targets,
        max(1, _env_int("DEEPSEEK_PROXY_TOOL_OUTPUT_POLICY_TRACE_TARGETS", 5)),
    )

    return {
        "enabled": True,
        "applied": False,
        "would_trim": bool(targets),
        "would_trim_item_count": len(targets),
        "would_remove_chars_estimate": would_remove,
        "would_remove_chars_by_category": would_remove_by_category,
        "would_trim_count_by_category": would_trim_count_by_category,
        "estimated_total_output_chars_before": int(total_output_chars),
        "estimated_total_output_chars_after": estimated_total_after,
        "target_total_output_chars": max_total_chars,
        "unmet_total_budget_chars": unmet,
        "total_budget_reachable": unmet == 0,
        "category_counts": category_counts,
        "category_chars": category_chars,
        "category_output_chars": category_output_chars,
        "policies": compact_policies,
        "targets": _compact_tool_output_targets_for_trace(targets, max_items=trace_target_limit),
    }


def _compact_tool_output_target_for_trace(target: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "index",
        "call_id",
        "tool_name",
        "category",
        "policy_name",
        "trim_reason",
        "item_chars",
        "output_chars",
        "original_chars",
        "estimated_after_chars",
        "estimated_remove_chars",
        "exceeds_warn_item_chars",
    ]
    return {key: target.get(key) for key in keys if key in target}


def _compact_tool_output_targets_for_trace(
    targets: list[dict[str, Any]],
    *,
    max_items: int,
) -> list[dict[str, Any]]:
    safe_max = max(1, int(max_items))
    return [_compact_tool_output_target_for_trace(target) for target in targets[:safe_max]]


def _tool_output_trim_dry_run(
    outputs: list[dict[str, Any]],
    *,
    total_output_chars: int,
) -> dict[str, Any]:
    config = _tool_output_trim_dry_run_env_config()
    max_item_chars = int(config["max_item_chars"])
    max_total_chars = int(config["max_total_chars"])
    max_targets = int(config["max_targets"])

    targets_by_call_id: dict[str, dict[str, Any]] = {}

    for output in outputs:
        item_chars = int(output.get("item_chars") or 0)
        if item_chars <= max_item_chars:
            continue
        after_chars = _estimate_tool_output_trim_after_chars(item_chars, config)
        targets_by_call_id[str(output.get("call_id") or "")] = {
            **output,
            "trim_reason": "item_exceeds_max_item_chars",
            "original_chars": item_chars,
            "estimated_after_chars": after_chars,
            "estimated_remove_chars": max(0, item_chars - after_chars),
        }

    estimated_total_after_item_caps = int(total_output_chars) - sum(
        int(target.get("estimated_remove_chars") or 0)
        for target in targets_by_call_id.values()
    )

    if estimated_total_after_item_caps > max_total_chars:
        for output in sorted(outputs, key=lambda item: int(item.get("item_chars") or 0), reverse=True):
            if estimated_total_after_item_caps <= max_total_chars:
                break

            call_id = str(output.get("call_id") or "")
            if call_id in targets_by_call_id:
                continue

            item_chars = int(output.get("item_chars") or 0)
            after_chars = _estimate_tool_output_trim_after_chars(item_chars, config)
            remove_chars = max(0, item_chars - after_chars)
            if remove_chars <= 0:
                continue

            targets_by_call_id[call_id] = {
                **output,
                "trim_reason": "total_output_exceeds_max_total_chars",
                "original_chars": item_chars,
                "estimated_after_chars": after_chars,
                "estimated_remove_chars": remove_chars,
            }
            estimated_total_after_item_caps -= remove_chars

    targets = sorted(
        targets_by_call_id.values(),
        key=lambda item: int(item.get("estimated_remove_chars") or 0),
        reverse=True,
    )

    would_remove = sum(int(item.get("estimated_remove_chars") or 0) for item in targets)

    estimated_after = max(0, int(total_output_chars) - would_remove)
    unmet_total_budget_chars = max(0, estimated_after - max_total_chars)

    trace_target_limit = min(
        max_targets,
        max(1, _env_int("DEEPSEEK_PROXY_TOOL_OUTPUT_TRIM_TRACE_TARGETS", 5)),
    )

    return {
        "mode": config["mode"],
        "applied": False,
        "would_trim": bool(targets),
        "would_trim_item_count": len(targets),
        "would_remove_chars_estimate": would_remove,
        "estimated_total_output_chars_before": int(total_output_chars),
        "estimated_total_output_chars_after": estimated_after,
        "target_total_output_chars": max_total_chars,
        "unmet_total_budget_chars": unmet_total_budget_chars,
        "total_budget_reachable": unmet_total_budget_chars == 0,
        "max_item_chars": max_item_chars,
        "max_total_chars": max_total_chars,
        "keep_head_chars": int(config["keep_head_chars"]),
        "keep_tail_chars": int(config["keep_tail_chars"]),
        "trimmed_to_item_cap_chars": _estimate_tool_output_trim_after_chars(max_item_chars + 1, config),
        "targets": _compact_tool_output_targets_for_trace(targets, max_items=trace_target_limit),
    }


def _format_trimmed_tool_output_text(
    *,
    original_text: str,
    call_id: str,
    tool_name: str,
    category: str,
    policy: dict[str, Any],
    original_item_chars: int,
) -> str:
    keep_head = int(policy.get("keep_head_chars") or 0)
    keep_tail = int(policy.get("keep_tail_chars") or 0)

    if keep_head + keep_tail >= len(original_text):
        return original_text

    head = original_text[:keep_head] if keep_head > 0 else ""
    tail = original_text[-keep_tail:] if keep_tail > 0 else ""
    omitted_chars = max(0, len(original_text) - len(head) - len(tail))

    return (
        "[tool output trimmed by CoDeepSeedeX]\n"
        f"call_id: {call_id or 'unknown'}\n"
        f"tool_name: {tool_name or 'unknown'}\n"
        f"category: {category or 'unknown'}\n"
        f"original_output_chars: {len(original_text)}\n"
        f"original_item_chars: {original_item_chars}\n"
        f"kept_head_chars: {len(head)}\n"
        f"kept_tail_chars: {len(tail)}\n"
        f"omitted_middle_chars: {omitted_chars}\n"
        "\n--- kept head ---\n"
        f"{head}"
        "\n--- omitted middle ---\n"
        f"... {omitted_chars} chars omitted ...\n"
        "\n--- kept tail ---\n"
        f"{tail}"
    )


def _apply_tool_output_safe_trimming(input_value: Any) -> tuple[Any, dict[str, Any]]:
    config = _tool_output_trim_dry_run_env_config()
    mode = str(config.get("mode") or "dry_run")
    report: dict[str, Any] = {
        "mode": mode,
        "effective_mode": mode,
        "enabled": mode == "enabled",
        "applied": False,
        "reason": None,
        "canary_guard": None,
        "input_is_list": isinstance(input_value, list),
        "input_item_count_before": len(input_value) if isinstance(input_value, list) else 0,
        "input_item_count_after": len(input_value) if isinstance(input_value, list) else 0,
        "function_call_output_count": 0,
        "trimmed_item_count": 0,
        "chars_before": _debug_trace_json_chars(input_value),
        "chars_after": _debug_trace_json_chars(input_value),
        "chars_removed": 0,
        "targets": [],
        "error": None,
    }

    if mode != "enabled":
        report["reason"] = "trim_mode_not_enabled"
        return input_value, report

    if not isinstance(input_value, list):
        report["reason"] = "input_not_list"
        return input_value, report

    try:
        trimmed_input = deepcopy(input_value)

        calls_by_id: dict[str, dict[str, Any]] = {}
        for index, item in enumerate(trimmed_input):
            if not isinstance(item, dict):
                continue
            if str(item.get("type") or "") != "function_call":
                continue
            call_id = str(item.get("call_id") or "")
            if not call_id:
                continue
            calls_by_id[call_id] = {
                "index": index,
                "tool_name": str(item.get("name") or "unknown"),
                "arguments_chars": _debug_trace_json_chars(item.get("arguments")),
            }

        targets: list[dict[str, Any]] = []
        chars_before = _debug_trace_json_chars(trimmed_input)

        for index, item in enumerate(trimmed_input):
            if not isinstance(item, dict):
                continue
            if str(item.get("type") or "") != "function_call_output":
                continue

            report["function_call_output_count"] = int(report["function_call_output_count"]) + 1

            output = item.get("output")
            if not isinstance(output, str):
                continue

            call_id = str(item.get("call_id") or "")
            call_info = calls_by_id.get(call_id) or {}
            tool_name = str(call_info.get("tool_name") or "unknown")
            category = _classify_tool_output_category(tool_name)
            policy = _tool_output_category_policy(category)
            original_item_chars = _debug_trace_json_chars(item)

            if original_item_chars <= int(policy["max_item_chars"]):
                continue

            trimmed_output = _format_trimmed_tool_output_text(
                original_text=output,
                call_id=call_id,
                tool_name=tool_name,
                category=category,
                policy=policy,
                original_item_chars=original_item_chars,
            )
            if trimmed_output == output:
                continue

            original_output_chars = len(output)
            item["output"] = trimmed_output
            trimmed_item_chars = _debug_trace_json_chars(item)
            removed_chars = max(0, original_item_chars - trimmed_item_chars)
            if removed_chars <= 0:
                item["output"] = output
                continue

            targets.append(
                {
                    "index": index,
                    "call_id": call_id,
                    "tool_name": tool_name,
                    "category": category,
                    "policy_name": str(policy.get("policy_name") or category),
                    "trim_reason": "enabled_category_item_exceeds_max_item_chars",
                    "item_chars": original_item_chars,
                    "output_chars": original_output_chars,
                    "original_chars": original_item_chars,
                    "estimated_after_chars": trimmed_item_chars,
                    "estimated_remove_chars": removed_chars,
                    "exceeds_warn_item_chars": True,
                }
            )

        chars_after = _debug_trace_json_chars(trimmed_input)
        chars_removed = max(0, chars_before - chars_after)

        if not targets or chars_removed <= 0:
            report["reason"] = "no_outputs_exceeded_policy"
            report["chars_after"] = chars_after
            return input_value, report

        trace_target_limit = max(1, _env_int("DEEPSEEK_PROXY_TOOL_OUTPUT_APPLIED_TRACE_TARGETS", 5))
        report.update(
            {
                "applied": True,
                "reason": "enabled",
                "input_item_count_after": len(trimmed_input),
                "trimmed_item_count": len(targets),
                "chars_before": chars_before,
                "chars_after": chars_after,
                "chars_removed": chars_removed,
                "targets": _compact_tool_output_targets_for_trace(targets, max_items=trace_target_limit),
            }
        )
        return trimmed_input, report

    except Exception as exc:
        report["reason"] = "exception_fallback_to_original_input"
        report["error"] = f"{type(exc).__name__}: {exc}"
        report["applied"] = False
        report["chars_after"] = report["chars_before"]
        report["chars_removed"] = 0
        report["targets"] = []
        return input_value, report


def _tool_output_budget_breakdown(input_value: Any) -> dict[str, Any]:
    config = _tool_output_budget_env_config()
    summary: dict[str, Any] = {
        "config": config,
        "input_is_list": isinstance(input_value, list),
        "input_item_count": len(input_value) if isinstance(input_value, list) else 0,
        "input_chars": _debug_trace_json_chars(input_value),
        "function_call_count": 0,
        "function_call_chars": 0,
        "function_call_output_count": 0,
        "function_call_output_chars": 0,
        "function_call_output_payload_chars": 0,
        "type_counts": {},
        "type_chars": {},
        "tool_name_counts": {},
        "tool_name_chars": {},
        "largest_outputs": [],
        "large_output_count": 0,
        "total_output_exceeds_warn_total": False,
    }

    if not isinstance(input_value, list):
        return summary

    calls_by_id: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(input_value):
        if not isinstance(item, dict):
            item_type = type(item).__name__
            item_chars = _debug_trace_json_chars(item)
        else:
            item_type = str(item.get("type") or "missing_type")
            item_chars = _debug_trace_json_chars(item)

        summary["type_counts"][item_type] = int(summary["type_counts"].get(item_type, 0)) + 1
        summary["type_chars"][item_type] = int(summary["type_chars"].get(item_type, 0)) + item_chars

        if not isinstance(item, dict):
            continue

        if item_type == "function_call":
            call_id = str(item.get("call_id") or "")
            tool_name = str(item.get("name") or "unknown")
            arguments_chars = _debug_trace_json_chars(item.get("arguments"))
            summary["function_call_count"] = int(summary["function_call_count"]) + 1
            summary["function_call_chars"] = int(summary["function_call_chars"]) + item_chars
            summary["tool_name_counts"][tool_name] = int(summary["tool_name_counts"].get(tool_name, 0)) + 1
            summary["tool_name_chars"][tool_name] = int(summary["tool_name_chars"].get(tool_name, 0)) + item_chars
            if call_id:
                calls_by_id[call_id] = {
                    "index": index,
                    "tool_name": tool_name,
                    "arguments_chars": arguments_chars,
                    "item_chars": item_chars,
                }

    largest_outputs: list[dict[str, Any]] = []
    all_outputs: list[dict[str, Any]] = []
    warn_item_chars = int(config["warn_item_chars"])

    for index, item in enumerate(input_value):
        if not isinstance(item, dict):
            continue
        item_type = str(item.get("type") or "missing_type")
        if item_type != "function_call_output":
            continue

        call_id = str(item.get("call_id") or "")
        item_chars = _debug_trace_json_chars(item)
        output_chars = _debug_trace_json_chars(item.get("output"))
        call_info = calls_by_id.get(call_id) or {}
        tool_name = str(call_info.get("tool_name") or "unknown")

        summary["function_call_output_count"] = int(summary["function_call_output_count"]) + 1
        summary["function_call_output_chars"] = int(summary["function_call_output_chars"]) + item_chars
        summary["function_call_output_payload_chars"] = int(summary["function_call_output_payload_chars"]) + output_chars
        summary["tool_name_counts"][tool_name] = int(summary["tool_name_counts"].get(tool_name, 0)) + 1
        summary["tool_name_chars"][tool_name] = int(summary["tool_name_chars"].get(tool_name, 0)) + item_chars
        if item_chars >= warn_item_chars:
            summary["large_output_count"] = int(summary["large_output_count"]) + 1

        category = _classify_tool_output_category(tool_name)
        output_record = {
            "index": index,
            "call_id": call_id,
            "tool_name": tool_name,
            "category": category,
            "item_chars": item_chars,
            "output_chars": output_chars,
            "matching_function_call_index": call_info.get("index"),
            "matching_function_call_arguments_chars": call_info.get("arguments_chars"),
            "exceeds_warn_item_chars": item_chars >= warn_item_chars,
        }
        largest_outputs.append(output_record)
        all_outputs.append(output_record)

    largest_outputs.sort(key=lambda item: int(item.get("item_chars") or 0), reverse=True)
    largest_limit = min(
        int(config["largest_items"]),
        max(1, _env_int("DEEPSEEK_PROXY_TOOL_OUTPUT_LARGEST_TRACE_ITEMS", 5)),
    )
    summary["largest_outputs"] = _compact_tool_output_targets_for_trace(
        largest_outputs,
        max_items=largest_limit,
    )
    summary["total_output_exceeds_warn_total"] = (
        int(summary["function_call_output_chars"]) >= int(config["warn_total_chars"])
    )
    summary["trim_dry_run"] = _tool_output_trim_dry_run(
        all_outputs,
        total_output_chars=int(summary["function_call_output_chars"]),
    )
    summary["policy_dry_run"] = _tool_output_policy_dry_run(
        all_outputs,
        total_output_chars=int(summary["function_call_output_chars"]),
    )
    return summary


def _classify_history_message_for_audit(message: Any) -> str:
    if not isinstance(message, dict):
        return "non_dict_message"

    role = str(message.get("role") or "unknown")
    content = _plain_text_from_content(message.get("content", ""))

    if role == "tool":
        return "tool_protocol_message"

    tool_calls = message.get("tool_calls") or []
    if role == "assistant" and isinstance(tool_calls, list) and tool_calls:
        return "assistant_tool_call_message"

    lowered = content.lower()
    flattened_markers = (
        "assistant_requested_tool_calls",
        "tool_outputs:",
        "tool_call_id:",
        "[orphaned tool output ignored by protocol repair]",
        "function_call_output",
    )
    if any(marker in lowered for marker in flattened_markers):
        return "flattened_tool_transcript"

    if role in {"system", "developer"}:
        return "system_or_developer"

    if role == "user":
        return "plain_user_message"

    if role == "assistant":
        return "plain_assistant_message"

    return "other_message"


def _flattened_tool_transcript_retention_markers(text: str) -> list[str]:
    lowered = text.lower()
    marker_specs = [
        ("ERROR", ("error", "exception", "fatal")),
        ("FAILED", ("failed", " failure", "failures")),
        ("Traceback", ("traceback (most recent call last)",)),
        ("AssertionError", ("assertionerror",)),
        ("PASS", (" passed", "passed in", " ok ")),
        ("pytest summary", (" passed in", " failed in", "errors in", "warnings in", "== test session starts ==")),
        ("git hash", ("commit ", "head ->", "origin/", "rev-parse", "sha256")),
        ("commit", ("commit ", "committed", "git commit")),
        ("modified files", ("files changed", "insertions(+)", "deletions(-)", "modified:", "changes not staged")),
        ("exit code", ("exit code", "return code", "status code")),
        ("warning", ("warning", "warnings")),
    ]

    markers: list[str] = []
    for marker, needles in marker_specs:
        if any(needle in lowered for needle in needles):
            markers.append(marker)
    return markers


def _classify_flattened_tool_transcript_semantic_type(text: str) -> str:
    stripped = text.strip()
    lowered = stripped.lower()

    if "traceback (most recent call last)" in lowered or "assertionerror" in lowered:
        return "stacktrace"

    if (
        "diff --git" in lowered
        or "\n@@ " in lowered
        or "\n+++ b/" in lowered
        or "\n--- a/" in lowered
    ):
        return "diff_output"

    if (
        "*** begin patch" in lowered
        or "apply_patch" in lowered
        or "patching file" in lowered
        or "hunk #" in lowered
    ):
        return "patch_output"

    if (
        "\n• running" in lowered
        or "\n• ran" in lowered
        or "\n• viewed" in lowered
        or "\n✔ you approved" in lowered
    ):
        return "chatty_terminal"

    if (
        "pytest" in lowered
        or " passed in " in lowered
        or " failed in " in lowered
        or "collected " in lowered
        or "== test session starts ==" in lowered
    ):
        return "test_output"

    if stripped.startswith("{") or stripped.startswith("["):
        try:
            json.loads(stripped)
            return "json_payload"
        except Exception:
            pass

    if (
        "search result" in lowered
        or "web.run" in lowered
        or "turn0search" in lowered
        or "turn1search" in lowered
        or "sources:" in lowered
    ):
        return "search_result"

    if (
        "$ " in text
        or "=====" in text
        or "kelvin@" in lowered
        or "ps " in lowered
        or "traceback" in lowered
    ):
        return "shell_log"

    return "unknown"


def _flattened_tool_transcript_semantic_risk(
    semantic_type: str,
    retention_markers: list[str],
    *,
    text_chars: int,
) -> str:
    marker_set = set(retention_markers)

    if semantic_type == "test_output" and marker_set and not {"ERROR", "FAILED", "Traceback", "AssertionError"} & marker_set:
        return "low"

    if {"Traceback", "AssertionError", "FAILED"} & marker_set:
        return "medium"

    if semantic_type in {"stacktrace", "patch_output", "diff_output", "json_payload", "search_result"}:
        return "medium"

    if semantic_type == "chatty_terminal":
        return "high"

    if semantic_type == "unknown":
        return "high" if text_chars >= 8000 else "medium"

    if semantic_type == "shell_log":
        return "medium"

    return "medium"


def _flattened_tool_transcript_semantic_audit(messages: Any) -> dict[str, Any]:
    enabled_env = os.environ.get("DEEPSEEK_PROXY_FLATTENED_TOOL_SEMANTIC_AUDIT", "1").strip().lower()
    enabled = enabled_env not in {"0", "false", "off", "no"}
    max_targets = max(
        1,
        _env_int("DEEPSEEK_PROXY_FLATTENED_TOOL_SEMANTIC_AUDIT_TARGETS", 12),
    )

    report: dict[str, Any] = {
        "enabled": enabled,
        "applied": False,
        "strategy": "flattened_tool_transcript_semantic_audit",
        "messages_is_list": isinstance(messages, list),
        "message_count": len(messages) if isinstance(messages, list) else 0,
        "flattened_message_count": 0,
        "flattened_message_chars": 0,
        "semantic_types": {},
        "semantic_risks": {},
        "retention_marker_counts": {},
        "low_risk_count": 0,
        "medium_risk_count": 0,
        "high_risk_count": 0,
        "targets": [],
    }

    if not enabled or not isinstance(messages, list):
        return report

    targets: list[dict[str, Any]] = []

    for index, message in enumerate(messages):
        category = _classify_history_message_for_audit(message)
        if category != "flattened_tool_transcript":
            continue

        role = "non_dict"
        content = ""
        if isinstance(message, dict):
            role = str(message.get("role") or "unknown")
            content = _plain_text_from_content(message.get("content", ""))

        message_chars = _debug_trace_json_chars(message)
        text_chars = len(content)
        semantic_type = _classify_flattened_tool_transcript_semantic_type(content)
        retention_markers = _flattened_tool_transcript_retention_markers(content)
        semantic_risk = _flattened_tool_transcript_semantic_risk(
            semantic_type,
            retention_markers,
            text_chars=text_chars,
        )

        report["flattened_message_count"] = int(report["flattened_message_count"]) + 1
        report["flattened_message_chars"] = int(report["flattened_message_chars"]) + message_chars

        type_bucket = report["semantic_types"].setdefault(semantic_type, {"count": 0, "chars": 0})
        type_bucket["count"] += 1
        type_bucket["chars"] += message_chars

        risk_bucket = report["semantic_risks"].setdefault(semantic_risk, {"count": 0, "chars": 0})
        risk_bucket["count"] += 1
        risk_bucket["chars"] += message_chars

        count_key = f"{semantic_risk}_risk_count"
        report[count_key] = int(report[count_key]) + 1

        for marker in retention_markers:
            report["retention_marker_counts"][marker] = int(report["retention_marker_counts"].get(marker, 0)) + 1

        targets.append(
            {
                "index": index,
                "role": role,
                "history_category": category,
                "chars": message_chars,
                "text_chars": text_chars,
                "semantic_type": semantic_type,
                "semantic_risk": semantic_risk,
                "retention_markers": retention_markers,
            }
        )

    risk_order = {"high": 0, "medium": 1, "low": 2}
    targets.sort(
        key=lambda item: (
            risk_order.get(str(item.get("semantic_risk")), 9),
            -int(item.get("chars") or 0),
        )
    )
    report["targets"] = targets[:max_targets]
    return report


def _history_growth_breakdown(
    messages: Any,
    *,
    input_value: Any = None,
    previous_response_id: str | None = None,
) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "previous_response_id_present": bool(previous_response_id),
        "messages_is_list": isinstance(messages, list),
        "message_count": len(messages) if isinstance(messages, list) else 0,
        "messages_total_chars": _debug_trace_json_chars({"messages": messages}) if isinstance(messages, list) else 0,
        "roles": {},
        "history_categories": {},
        "assistant_tool_call_count": 0,
        "assistant_tool_arguments_chars": 0,
        "input_is_list": isinstance(input_value, list),
        "input_item_count": len(input_value) if isinstance(input_value, list) else 0,
        "input_item_type_counts": {},
        "input_item_type_chars": {},
        "largest_messages": [],
    }

    if isinstance(input_value, list):
        for item in input_value:
            item_type = "non_dict"
            if isinstance(item, dict):
                item_type = str(item.get("type") or "missing_type")
            summary["input_item_type_counts"][item_type] = int(summary["input_item_type_counts"].get(item_type, 0)) + 1
            summary["input_item_type_chars"][item_type] = int(summary["input_item_type_chars"].get(item_type, 0)) + _debug_trace_json_chars(item)

    if not isinstance(messages, list):
        return summary

    largest_messages: list[dict[str, Any]] = []

    for index, message in enumerate(messages):
        if isinstance(message, dict):
            role = str(message.get("role") or "unknown")
            tool_calls = message.get("tool_calls") or []
        else:
            role = "non_dict"
            tool_calls = []

        message_chars = _debug_trace_json_chars(message)
        role_bucket = summary["roles"].setdefault(role, {"count": 0, "chars": 0})
        role_bucket["count"] += 1
        role_bucket["chars"] += message_chars

        category = _classify_history_message_for_audit(message)
        category_bucket = summary["history_categories"].setdefault(category, {"count": 0, "chars": 0})
        category_bucket["count"] += 1
        category_bucket["chars"] += message_chars

        if isinstance(tool_calls, list) and tool_calls:
            summary["assistant_tool_call_count"] = int(summary["assistant_tool_call_count"]) + len(tool_calls)
            for tool_call in tool_calls:
                if not isinstance(tool_call, dict):
                    continue
                function = tool_call.get("function") or {}
                if isinstance(function, dict):
                    summary["assistant_tool_arguments_chars"] = int(summary["assistant_tool_arguments_chars"]) + len(str(function.get("arguments") or ""))

        largest_messages.append(
            {
                "index": index,
                "role": role,
                "history_category": category,
                "chars": message_chars,
            }
        )

    largest_messages.sort(key=lambda item: int(item.get("chars") or 0), reverse=True)
    limit = max(1, _env_int("DEEPSEEK_PROXY_HISTORY_GROWTH_LARGEST_MESSAGES", 8))
    summary["largest_messages"] = largest_messages[:limit]
    return summary


def _semantic_compaction_policy_for_flattened_tool_target(
    target: dict[str, Any],
    *,
    summary_chars: int,
) -> dict[str, Any]:
    semantic_type = str(target.get("semantic_type") or "unknown")
    semantic_risk = str(target.get("semantic_risk") or "medium")
    retention_markers = target.get("retention_markers") or []
    if not isinstance(retention_markers, list):
        retention_markers = []

    marker_set = {str(marker) for marker in retention_markers}
    hard_markers = {
        "ERROR",
        "FAILED",
        "Traceback",
        "AssertionError",
        "git hash",
        "commit",
        "modified files",
        "exit code",
    }
    chars = max(0, int(target.get("chars") or 0))

    decision: dict[str, Any] = {
        "index": target.get("index"),
        "role": target.get("role"),
        "history_category": target.get("history_category"),
        "chars": chars,
        "semantic_type": semantic_type,
        "semantic_risk": semantic_risk,
        "retention_markers": [str(marker) for marker in retention_markers],
        "eligible_for_compaction": False,
        "policy_decision": "preserve",
        "recommended_action": "preserve_original",
        "compression_strategy": "none",
        "estimated_after_chars": chars,
        "estimated_remove_chars": 0,
        "reason": "default_preserve",
    }

    if semantic_risk == "low" and semantic_type == "test_output" and "pytest summary" in marker_set:
        estimated_after = min(chars, max(128, int(summary_chars)))
        estimated_remove = max(0, chars - estimated_after)
        decision.update(
            {
                "eligible_for_compaction": estimated_remove > 0,
                "policy_decision": "compact",
                "recommended_action": "compact_test_output_summary",
                "compression_strategy": "pytest_passed_summary_with_tail",
                "estimated_after_chars": estimated_after,
                "estimated_remove_chars": estimated_remove,
                "reason": "low_risk_passed_test_output",
            }
        )
        return decision

    if semantic_risk == "medium":
        decision.update(
            {
                "policy_decision": "structure_only",
                "recommended_action": "structure_preserving_summary_dry_run_only",
                "compression_strategy": "preserve_markers_and_extract_structure",
                "reason": "medium_risk_requires_marker_preservation",
            }
        )
        return decision

    if semantic_risk == "high":
        decision.update(
            {
                "policy_decision": "preserve",
                "recommended_action": "preserve_high_risk_transcript",
                "compression_strategy": "none",
                "reason": "high_risk_semantic_context",
            }
        )
        return decision

    if hard_markers & marker_set:
        decision.update(
            {
                "policy_decision": "preserve",
                "recommended_action": "preserve_due_to_retention_markers",
                "compression_strategy": "none",
                "reason": "hard_retention_markers_present",
            }
        )
        return decision

    decision["reason"] = "no_safe_policy_match"
    return decision


def _flattened_tool_transcript_semantic_compaction_policy_dry_run(messages: Any) -> dict[str, Any]:
    enabled_env = os.environ.get("DEEPSEEK_PROXY_FLATTENED_TOOL_SEMANTIC_POLICY_DRY_RUN", "1").strip().lower()
    enabled = enabled_env not in {"0", "false", "off", "no"}
    max_targets = max(
        1,
        _env_int("DEEPSEEK_PROXY_FLATTENED_TOOL_SEMANTIC_POLICY_TARGETS", 12),
    )
    summary_chars = max(
        128,
        _env_int("DEEPSEEK_PROXY_FLATTENED_TOOL_SEMANTIC_POLICY_SUMMARY_CHARS", 700),
    )

    report: dict[str, Any] = {
        "enabled": enabled,
        "applied": False,
        "strategy": "flattened_tool_transcript_semantic_compaction_policy_dry_run",
        "messages_is_list": isinstance(messages, list),
        "message_count": len(messages) if isinstance(messages, list) else 0,
        "summary_chars": summary_chars,
        "flattened_message_count": 0,
        "candidate_count": 0,
        "eligible_compaction_count": 0,
        "structure_only_count": 0,
        "preserve_count": 0,
        "would_compact": False,
        "would_compact_count": 0,
        "would_remove_chars_estimate": 0,
        "estimated_messages_chars_before": _debug_trace_json_chars({"messages": messages}) if isinstance(messages, list) else 0,
        "estimated_messages_chars_after": _debug_trace_json_chars({"messages": messages}) if isinstance(messages, list) else 0,
        "policy_decisions": {},
        "targets": [],
    }

    if not enabled or not isinstance(messages, list):
        return report

    semantic_report = _flattened_tool_transcript_semantic_audit(messages)
    semantic_targets = semantic_report.get("targets") or []
    if not isinstance(semantic_targets, list):
        semantic_targets = []

    decisions: list[dict[str, Any]] = []
    for target in semantic_targets:
        if not isinstance(target, dict):
            continue

        decision = _semantic_compaction_policy_for_flattened_tool_target(
            target,
            summary_chars=summary_chars,
        )
        decisions.append(decision)

        report["candidate_count"] = int(report["candidate_count"]) + 1
        policy_decision = str(decision.get("policy_decision") or "preserve")
        report["policy_decisions"][policy_decision] = int(report["policy_decisions"].get(policy_decision, 0)) + 1

        if bool(decision.get("eligible_for_compaction")):
            report["eligible_compaction_count"] = int(report["eligible_compaction_count"]) + 1
        elif policy_decision == "structure_only":
            report["structure_only_count"] = int(report["structure_only_count"]) + 1
        else:
            report["preserve_count"] = int(report["preserve_count"]) + 1

    report["flattened_message_count"] = int(semantic_report.get("flattened_message_count") or 0)

    eligible = [item for item in decisions if bool(item.get("eligible_for_compaction"))]
    would_remove = sum(int(item.get("estimated_remove_chars") or 0) for item in eligible)
    before = int(report["estimated_messages_chars_before"])
    after = max(0, before - would_remove)

    decision_order = {"compact": 0, "structure_only": 1, "preserve": 2}
    risk_order = {"high": 0, "medium": 1, "low": 2}
    decisions.sort(
        key=lambda item: (
            decision_order.get(str(item.get("policy_decision")), 9),
            risk_order.get(str(item.get("semantic_risk")), 9),
            -int(item.get("estimated_remove_chars") or 0),
            -int(item.get("chars") or 0),
        )
    )

    report.update(
        {
            "would_compact": bool(eligible),
            "would_compact_count": len(eligible),
            "would_remove_chars_estimate": would_remove,
            "estimated_messages_chars_after": after,
            "targets": decisions[:max_targets],
        }
    )
    return report


def _flattened_tool_transcript_compaction_dry_run(messages: Any) -> dict[str, Any]:
    enabled_env = os.environ.get("DEEPSEEK_PROXY_FLATTENED_TOOL_COMPACTION_DRY_RUN", "1").strip().lower()
    enabled = enabled_env not in {"0", "false", "off", "no"}

    preserve_recent_messages = max(
        0,
        _env_int("DEEPSEEK_PROXY_FLATTENED_TOOL_COMPACTION_PRESERVE_RECENT_MESSAGES", 20),
    )
    min_message_chars = max(
        1,
        _env_int("DEEPSEEK_PROXY_FLATTENED_TOOL_COMPACTION_MIN_MESSAGE_CHARS", 2000),
    )
    summary_chars = max(
        128,
        _env_int("DEEPSEEK_PROXY_FLATTENED_TOOL_COMPACTION_SUMMARY_CHARS", 1200),
    )
    max_targets = max(
        1,
        _env_int("DEEPSEEK_PROXY_FLATTENED_TOOL_COMPACTION_TARGETS", 8),
    )

    report: dict[str, Any] = {
        "enabled": enabled,
        "applied": False,
        "strategy": "flattened_tool_transcript_summary_dry_run",
        "messages_is_list": isinstance(messages, list),
        "message_count": len(messages) if isinstance(messages, list) else 0,
        "preserve_recent_messages": preserve_recent_messages,
        "min_message_chars": min_message_chars,
        "summary_chars": summary_chars,
        "flattened_message_count": 0,
        "flattened_message_chars": 0,
        "candidate_count": 0,
        "candidate_chars": 0,
        "would_compact": False,
        "would_compact_count": 0,
        "would_remove_chars_estimate": 0,
        "estimated_messages_chars_before": _debug_trace_json_chars({"messages": messages}) if isinstance(messages, list) else 0,
        "estimated_messages_chars_after": _debug_trace_json_chars({"messages": messages}) if isinstance(messages, list) else 0,
        "retained_recent_flattened_count": 0,
        "retained_recent_flattened_chars": 0,
        "targets": [],
    }

    if not enabled or not isinstance(messages, list):
        return report

    cutoff = max(0, len(messages) - preserve_recent_messages)
    targets: list[dict[str, Any]] = []

    for index, message in enumerate(messages):
        category = _classify_history_message_for_audit(message)
        if category != "flattened_tool_transcript":
            continue

        message_chars = _debug_trace_json_chars(message)
        report["flattened_message_count"] = int(report["flattened_message_count"]) + 1
        report["flattened_message_chars"] = int(report["flattened_message_chars"]) + message_chars

        if index >= cutoff:
            report["retained_recent_flattened_count"] = int(report["retained_recent_flattened_count"]) + 1
            report["retained_recent_flattened_chars"] = int(report["retained_recent_flattened_chars"]) + message_chars
            continue

        if message_chars < min_message_chars:
            continue

        estimated_after_chars = min(message_chars, summary_chars)
        estimated_remove_chars = max(0, message_chars - estimated_after_chars)
        if estimated_remove_chars <= 0:
            continue

        role = "non_dict"
        if isinstance(message, dict):
            role = str(message.get("role") or "unknown")

        report["candidate_count"] = int(report["candidate_count"]) + 1
        report["candidate_chars"] = int(report["candidate_chars"]) + message_chars

        targets.append(
            {
                "index": index,
                "role": role,
                "history_category": category,
                "chars": message_chars,
                "estimated_after_chars": estimated_after_chars,
                "estimated_remove_chars": estimated_remove_chars,
                "reason": "old_flattened_tool_transcript_over_min_chars",
            }
        )

    targets.sort(key=lambda item: int(item.get("estimated_remove_chars") or 0), reverse=True)
    would_remove = sum(int(item.get("estimated_remove_chars") or 0) for item in targets)
    before = int(report["estimated_messages_chars_before"])
    after = max(0, before - would_remove)

    report.update(
        {
            "would_compact": bool(targets),
            "would_compact_count": len(targets),
            "would_remove_chars_estimate": would_remove,
            "estimated_messages_chars_after": after,
            "targets": targets[:max_targets],
        }
    )
    return report


def _flattened_tool_payload_compaction_env_config() -> dict[str, Any]:
    mode = os.environ.get("DEEPSEEK_PROXY_FLATTENED_TOOL_PAYLOAD_COMPACTION_MODE", "dry_run").strip().lower()
    if mode not in {"off", "dry_run", "enabled"}:
        mode = "dry_run"

    return {
        "mode": mode,
        "preserve_recent_messages": max(
            0,
            _env_int("DEEPSEEK_PROXY_FLATTENED_TOOL_PAYLOAD_COMPACTION_PRESERVE_RECENT_MESSAGES", 20),
        ),
        "min_message_chars": max(
            1,
            _env_int("DEEPSEEK_PROXY_FLATTENED_TOOL_PAYLOAD_COMPACTION_MIN_MESSAGE_CHARS", 2000),
        ),
        "summary_chars": max(
            512,
            _env_int("DEEPSEEK_PROXY_FLATTENED_TOOL_PAYLOAD_COMPACTION_SUMMARY_CHARS", 1200),
        ),
        "trace_targets": max(
            1,
            _env_int("DEEPSEEK_PROXY_FLATTENED_TOOL_PAYLOAD_COMPACTION_TRACE_TARGETS", 8),
        ),
    }


def _build_flattened_tool_payload_compaction_text(
    *,
    original_text: str,
    message_index: int,
    original_chars: int,
    summary_chars: int,
) -> str:
    header = (
        "[flattened tool transcript compacted by CoDeepSeedeX]\n"
        f"message_index: {message_index}\n"
        f"original_chars: {original_chars}\n"
        "reason: old flattened tool transcript summarized for this upstream payload only\n"
        "persistence: original SQLite history is unchanged\n"
    )

    omitted_marker = "\n--- omitted middle ---\n"
    tail_marker = "\n--- kept tail ---\n"
    head_marker = "\n--- kept head ---\n"

    fixed_chars = len(header) + len(head_marker) + len(omitted_marker) + len(tail_marker) + 80
    available = max(0, int(summary_chars) - fixed_chars)

    if available <= 0:
        compacted = header[: int(summary_chars)]
        return compacted

    head_len = available // 2
    tail_len = available - head_len

    head = original_text[:head_len] if head_len > 0 else ""
    tail = original_text[-tail_len:] if tail_len > 0 else ""
    omitted = max(0, len(original_text) - len(head) - len(tail))

    compacted = (
        header
        + head_marker
        + head
        + omitted_marker
        + f"... {omitted} chars omitted ...\n"
        + tail_marker
        + tail
    )

    if len(compacted) > int(summary_chars):
        compacted = compacted[: int(summary_chars)]

    return compacted


def _flattened_tool_semantic_payload_compaction_env_config() -> dict[str, Any]:
    mode = os.environ.get("DEEPSEEK_PROXY_FLATTENED_TOOL_SEMANTIC_PAYLOAD_COMPACTION_MODE", "dry_run").strip().lower()
    if mode not in {"off", "dry_run", "enabled"}:
        mode = "dry_run"

    return {
        "mode": mode,
        "preserve_recent_messages": max(
            0,
            _env_int("DEEPSEEK_PROXY_FLATTENED_TOOL_SEMANTIC_PAYLOAD_COMPACTION_PRESERVE_RECENT_MESSAGES", 20),
        ),
        "min_message_chars": max(
            1,
            _env_int("DEEPSEEK_PROXY_FLATTENED_TOOL_SEMANTIC_PAYLOAD_COMPACTION_MIN_MESSAGE_CHARS", 2000),
        ),
        "summary_chars": max(
            512,
            _env_int("DEEPSEEK_PROXY_FLATTENED_TOOL_SEMANTIC_PAYLOAD_COMPACTION_SUMMARY_CHARS", 900),
        ),
        "trace_targets": max(
            1,
            _env_int("DEEPSEEK_PROXY_FLATTENED_TOOL_SEMANTIC_PAYLOAD_COMPACTION_TRACE_TARGETS", 8),
        ),
    }


def _semantic_test_output_summary_lines(text: str, *, limit: int = 24) -> list[str]:
    summary_needles = (
        "pytest",
        "passed in",
        "failed in",
        "errors in",
        "warnings in",
        "collected ",
        "== test session starts ==",
        "===== pytest",
    )
    lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        lowered = line.lower()
        if any(needle in lowered for needle in summary_needles):
            lines.append(line[:240])
        if len(lines) >= limit:
            break

    if not lines:
        tail_lines = [line.strip()[:240] for line in text.splitlines()[-limit:] if line.strip()]
        lines.extend(tail_lines)

    return lines[:limit]


def _build_semantic_test_output_payload_compaction_text(
    *,
    original_text: str,
    message_index: int,
    original_chars: int,
    summary_chars: int,
    decision: dict[str, Any],
) -> str:
    semantic_type = str(decision.get("semantic_type") or "unknown")
    semantic_risk = str(decision.get("semantic_risk") or "unknown")
    recommended_action = str(decision.get("recommended_action") or "unknown")
    compression_strategy = str(decision.get("compression_strategy") or "unknown")
    retention_markers = decision.get("retention_markers") or []
    if not isinstance(retention_markers, list):
        retention_markers = []

    header = (
        "[semantic flattened tool transcript compacted by CoDeepSeedeX]\n"
        f"message_index: {message_index}\n"
        f"original_chars: {original_chars}\n"
        f"semantic_type: {semantic_type}\n"
        f"semantic_risk: {semantic_risk}\n"
        f"recommended_action: {recommended_action}\n"
        f"compression_strategy: {compression_strategy}\n"
        f"retention_markers: {', '.join(str(marker) for marker in retention_markers) or 'none'}\n"
        "reason: low-risk passed test output summarized for this upstream payload only\n"
        "persistence: original SQLite history is unchanged\n"
        "--- retained pytest/test summary lines ---\n"
    )

    summary_lines = _semantic_test_output_summary_lines(original_text)
    body = "\n".join(summary_lines).strip()
    if body:
        body += "\n"

    tail_marker = "--- kept tail ---\n"
    fixed_chars = len(header) + len(body) + len(tail_marker) + 80
    available_tail = max(0, int(summary_chars) - fixed_chars)

    if available_tail > 0:
        tail = original_text[-available_tail:]
        compacted = header + body + tail_marker + tail
    else:
        compacted = header + body

    if len(compacted) > int(summary_chars):
        compacted = compacted[: int(summary_chars)]

    return compacted


def _apply_flattened_tool_transcript_semantic_payload_compaction(
    messages: Any,
) -> tuple[Any, dict[str, Any]]:
    config = _flattened_tool_semantic_payload_compaction_env_config()
    mode = str(config["mode"])

    report: dict[str, Any] = {
        "mode": mode,
        "enabled": mode == "enabled",
        "applied": False,
        "reason": None,
        "strategy": "flattened_tool_transcript_semantic_policy_payload_compaction",
        "messages_is_list": isinstance(messages, list),
        "message_count_before": len(messages) if isinstance(messages, list) else 0,
        "message_count_after": len(messages) if isinstance(messages, list) else 0,
        "preserve_recent_messages": int(config["preserve_recent_messages"]),
        "min_message_chars": int(config["min_message_chars"]),
        "summary_chars": int(config["summary_chars"]),
        "flattened_message_count": 0,
        "candidate_count": 0,
        "eligible_policy_count": 0,
        "compacted_count": 0,
        "skipped_policy_count": 0,
        "retained_recent_flattened_count": 0,
        "chars_before": _debug_trace_json_chars({"messages": messages}) if isinstance(messages, list) else 0,
        "chars_after": _debug_trace_json_chars({"messages": messages}) if isinstance(messages, list) else 0,
        "chars_removed": 0,
        "targets": [],
        "error": None,
    }

    report.setdefault("effective_mode", mode)
    report.setdefault("canary_guard", None)

    if not isinstance(messages, list):
        report["reason"] = "messages_not_list"
        return messages, report

    canary_guard = _semantic_payload_canary_guard_for_mode(mode)
    report["canary_guard"] = canary_guard
    if mode == "enabled" and not bool(canary_guard.get("allowed")):
        report["enabled"] = False
        report["effective_mode"] = "dry_run"
        report["reason"] = "semantic_payload_canary_guard_blocked_enabled"
        return messages, report

    if mode != "enabled":
        report["reason"] = "semantic_payload_compaction_mode_not_enabled"
        return messages, report

    try:
        compacted_messages = deepcopy(messages)
        cutoff = max(0, len(compacted_messages) - int(config["preserve_recent_messages"]))
        targets: list[dict[str, Any]] = []

        for index, message in enumerate(compacted_messages):
            category = _classify_history_message_for_audit(message)
            if category != "flattened_tool_transcript":
                continue

            report["flattened_message_count"] = int(report["flattened_message_count"]) + 1
            message_chars = _debug_trace_json_chars(message)

            if index >= cutoff:
                report["retained_recent_flattened_count"] = int(report["retained_recent_flattened_count"]) + 1
                continue

            if message_chars < int(config["min_message_chars"]):
                continue

            if not isinstance(message, dict):
                continue

            content = message.get("content")
            if not isinstance(content, str):
                continue

            report["candidate_count"] = int(report["candidate_count"]) + 1

            semantic_type = _classify_flattened_tool_transcript_semantic_type(content)
            retention_markers = _flattened_tool_transcript_retention_markers(content)
            semantic_risk = _flattened_tool_transcript_semantic_risk(
                semantic_type,
                retention_markers,
                text_chars=len(content),
            )
            policy_target = {
                "index": index,
                "role": str(message.get("role") or "unknown"),
                "history_category": category,
                "chars": message_chars,
                "text_chars": len(content),
                "semantic_type": semantic_type,
                "semantic_risk": semantic_risk,
                "retention_markers": retention_markers,
            }
            decision = _semantic_compaction_policy_for_flattened_tool_target(
                policy_target,
                summary_chars=int(config["summary_chars"]),
            )

            if not bool(decision.get("eligible_for_compaction")):
                report["skipped_policy_count"] = int(report["skipped_policy_count"]) + 1
                continue

            if decision.get("recommended_action") != "compact_test_output_summary":
                report["skipped_policy_count"] = int(report["skipped_policy_count"]) + 1
                continue

            report["eligible_policy_count"] = int(report["eligible_policy_count"]) + 1

            compacted_content = _build_semantic_test_output_payload_compaction_text(
                original_text=content,
                message_index=index,
                original_chars=len(content),
                summary_chars=int(config["summary_chars"]),
                decision=decision,
            )
            if compacted_content == content:
                continue

            before_message_chars = _debug_trace_json_chars(message)
            message["content"] = compacted_content
            after_message_chars = _debug_trace_json_chars(message)
            removed = max(0, before_message_chars - after_message_chars)
            if removed <= 0:
                message["content"] = content
                continue

            report["compacted_count"] = int(report["compacted_count"]) + 1
            target = dict(decision)
            target.update(
                {
                    "index": index,
                    "role": str(message.get("role") or "unknown"),
                    "history_category": category,
                    "chars": before_message_chars,
                    "estimated_after_chars": after_message_chars,
                    "estimated_remove_chars": removed,
                    "reason": "semantic_payload_enabled_low_risk_test_output",
                }
            )
            targets.append(target)

        before = int(report["chars_before"])
        after = _debug_trace_json_chars({"messages": compacted_messages})
        removed_total = max(0, before - after)

        if not targets or removed_total <= 0:
            report["reason"] = "no_semantic_payload_compaction_candidates"
            report["chars_after"] = after
            return messages, report

        report.update(
            {
                "applied": True,
                "reason": "enabled",
                "message_count_after": len(compacted_messages),
                "chars_after": after,
                "chars_removed": removed_total,
                "targets": targets[: int(config["trace_targets"])],
            }
        )
        return compacted_messages, report

    except Exception as exc:
        report["reason"] = "exception_fallback_to_original_messages"
        report["error"] = f"{type(exc).__name__}: {exc}"
        report["applied"] = False
        report["chars_after"] = report["chars_before"]
        report["chars_removed"] = 0
        report["targets"] = []
        return messages, report


def _apply_flattened_tool_transcript_payload_compaction(
    messages: Any,
) -> tuple[Any, dict[str, Any]]:
    config = _flattened_tool_payload_compaction_env_config()
    mode = str(config["mode"])

    report: dict[str, Any] = {
        "mode": mode,
        "enabled": mode == "enabled",
        "applied": False,
        "reason": None,
        "strategy": "flattened_tool_transcript_payload_summary",
        "messages_is_list": isinstance(messages, list),
        "message_count_before": len(messages) if isinstance(messages, list) else 0,
        "message_count_after": len(messages) if isinstance(messages, list) else 0,
        "preserve_recent_messages": int(config["preserve_recent_messages"]),
        "min_message_chars": int(config["min_message_chars"]),
        "summary_chars": int(config["summary_chars"]),
        "flattened_message_count": 0,
        "candidate_count": 0,
        "compacted_count": 0,
        "retained_recent_flattened_count": 0,
        "chars_before": _debug_trace_json_chars({"messages": messages}) if isinstance(messages, list) else 0,
        "chars_after": _debug_trace_json_chars({"messages": messages}) if isinstance(messages, list) else 0,
        "chars_removed": 0,
        "targets": [],
        "error": None,
    }

    if mode != "enabled":
        report["reason"] = "payload_compaction_mode_not_enabled"
        return messages, report

    if not isinstance(messages, list):
        report["reason"] = "messages_not_list"
        return messages, report

    try:
        compacted_messages = deepcopy(messages)
        cutoff = max(0, len(compacted_messages) - int(config["preserve_recent_messages"]))
        targets: list[dict[str, Any]] = []

        for index, message in enumerate(compacted_messages):
            category = _classify_history_message_for_audit(message)
            if category != "flattened_tool_transcript":
                continue

            report["flattened_message_count"] = int(report["flattened_message_count"]) + 1

            message_chars = _debug_trace_json_chars(message)
            if index >= cutoff:
                report["retained_recent_flattened_count"] = int(report["retained_recent_flattened_count"]) + 1
                continue

            if message_chars < int(config["min_message_chars"]):
                continue

            if not isinstance(message, dict):
                continue

            content = message.get("content")
            if not isinstance(content, str):
                continue

            report["candidate_count"] = int(report["candidate_count"]) + 1

            compacted_content = _build_flattened_tool_payload_compaction_text(
                original_text=content,
                message_index=index,
                original_chars=len(content),
                summary_chars=int(config["summary_chars"]),
            )
            if compacted_content == content:
                continue

            before_message_chars = _debug_trace_json_chars(message)
            message["content"] = compacted_content
            after_message_chars = _debug_trace_json_chars(message)
            removed = max(0, before_message_chars - after_message_chars)
            if removed <= 0:
                message["content"] = content
                continue

            report["compacted_count"] = int(report["compacted_count"]) + 1
            targets.append(
                {
                    "index": index,
                    "role": str(message.get("role") or "unknown"),
                    "history_category": category,
                    "chars": before_message_chars,
                    "estimated_after_chars": after_message_chars,
                    "estimated_remove_chars": removed,
                    "reason": "payload_enabled_old_flattened_tool_transcript",
                }
            )

        before = int(report["chars_before"])
        after = _debug_trace_json_chars({"messages": compacted_messages})
        removed_total = max(0, before - after)

        if not targets or removed_total <= 0:
            report["reason"] = "no_payload_compaction_candidates"
            report["chars_after"] = after
            return messages, report

        report.update(
            {
                "applied": True,
                "reason": "enabled",
                "message_count_after": len(compacted_messages),
                "chars_after": after,
                "chars_removed": removed_total,
                "targets": targets[: int(config["trace_targets"])],
            }
        )
        return compacted_messages, report

    except Exception as exc:
        report["reason"] = "exception_fallback_to_original_messages"
        report["error"] = f"{type(exc).__name__}: {exc}"
        report["applied"] = False
        report["chars_after"] = report["chars_before"]
        report["chars_removed"] = 0
        report["targets"] = []
        return messages, report


def _normalize_chat_role(role: str | None) -> str:
    """Map Responses/Codex roles to DeepSeek ChatCompletions roles."""
    if role in {"system", "user", "assistant", "tool", "latest_reminder"}:
        return role
    if role == "developer":
        return "system"
    return "user"


def _deepseek_thinking_config() -> dict[str, str]:
    """Return DeepSeek thinking config.

    Default is disabled because the stable v0.4 path depends on avoiding
    reasoning_content replay requirements. Set DEEPSEEK_THINKING=enabled
    only for experimental thinking-mode runs.
    """
    value = os.environ.get("DEEPSEEK_THINKING", "disabled").strip().lower()
    if value in {"1", "true", "yes", "on", "enabled"}:
        return {"type": "enabled"}
    return {"type": "disabled"}


def _repair_thinking_history_messages(messages: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], bool]:
    """Patch legacy non-thinking assistant history for DeepSeek thinking mode.

    This is a compatibility repair. It cannot reconstruct real reasoning
    generated in a previous disabled-thinking session. It only guarantees the
    DeepSeek-required `reasoning_content` field is present on assistant history
    messages so that thinking-mode continuations do not fail immediately.
    """
    repaired = deepcopy(messages)
    changed = False

    if _deepseek_thinking_config().get("type") == "enabled":
        for msg in repaired:
            if msg.get("role") == "assistant" and "reasoning_content" not in msg:
                msg["reasoning_content"] = ""
                changed = True

    return repaired, changed



def _normalize_deepseek_role(role: Any) -> str:
    """Normalize OpenAI/Codex message roles to DeepSeek ChatCompletions roles."""
    role_str = str(role or "user")

    if role_str == "developer":
        return "system"

    if role_str in {"system", "user", "assistant", "tool", "latest_reminder"}:
        return role_str

    print(f"[deepseek-responses-proxy] mapped unsupported DeepSeek message role {role_str!r} to 'user'")
    return "user"


def _prepare_messages_for_deepseek(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Prepare ChatCompletions messages for DeepSeek.

    In thinking mode, DeepSeek requires assistant history messages to carry
    `reasoning_content`. Codex may send assistant history items in Responses
    input without that field, so we normalize immediately before the upstream
    DeepSeek request.
    """
    prepared, _changed = _repair_thinking_history_messages(messages)
    for message in prepared if "prepared" in locals() else messages:
        message["role"] = _normalize_deepseek_role(message.get("role"))

    return prepared



def _repair_tool_call_message_order(
    messages: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], bool]:
    """Repair ChatCompletions tool-call ordering before sending to DeepSeek.

    ChatCompletions requires every assistant message with tool_calls to be
    immediately followed by tool messages for each tool_call_id. Codex can emit
    real Responses input where a non-tool message, often a reminder/user item,
    is inserted between an assistant tool call and its matching tool output.
    DeepSeek rejects that history.

    This repair moves matching later tool outputs directly after the assistant
    tool-call message. If no matching output exists, it inserts a synthetic
    incomplete-tool result. Orphan tool messages are converted to user messages
    so they do not violate the protocol.
    """
    repaired = False
    repaired_messages: list[dict[str, Any]] = []
    consumed_tool_indexes: set[int] = set()

    def _synthetic_tool_message(call_id: str) -> dict[str, Any]:
        return {
            "role": "tool",
            "tool_call_id": call_id,
            "content": json.dumps(
                {
                    "ok": False,
                    "error": "missing_tool_result_repaired",
                    "message": "Tool call was not completed; inserted by protocol repair.",
                    "tool_call_id": call_id,
                }
            ),
        }

    i = 0
    while i < len(messages):
        if i in consumed_tool_indexes:
            i += 1
            continue

        message = deepcopy(messages[i])
        role = message.get("role")

        if role == "assistant" and message.get("tool_calls"):
            tool_calls = message.get("tool_calls") or []
            expected_call_ids = [
                tool_call.get("id")
                for tool_call in tool_calls
                if tool_call.get("id")
            ]

            repaired_messages.append(message)
            i += 1

            seen_call_ids: set[str] = set()

            # First consume immediately following matching tool messages.
            while i < len(messages) and messages[i].get("role") == "tool":
                tool_message = deepcopy(messages[i])
                tool_call_id = tool_message.get("tool_call_id")

                if tool_call_id in expected_call_ids and tool_call_id not in seen_call_ids:
                    repaired_messages.append(tool_message)
                    seen_call_ids.add(tool_call_id)
                    consumed_tool_indexes.add(i)
                else:
                    repaired = True
                    repaired_messages.append(
                        {
                            "role": "user",
                            "content": (
                                "[orphaned tool output ignored by protocol repair]\n"
                                f"tool_call_id={tool_call_id or 'unknown'}\n"
                                f"content={tool_message.get('content', '')}"
                            ),
                        }
                    )
                    consumed_tool_indexes.add(i)
                i += 1

            # Codex may place a user/reminder item before the matching tool
            # output. Search ahead and move matching tool outputs immediately
            # after the assistant tool_call message.
            for call_id in expected_call_ids:
                if call_id in seen_call_ids:
                    continue

                found_index: int | None = None
                for j in range(i, len(messages)):
                    if j in consumed_tool_indexes:
                        continue
                    candidate = messages[j]

                    # Do not move a tool result across a later assistant
                    # tool_call. That would risk crossing turn boundaries.
                    if candidate.get("role") == "assistant" and candidate.get("tool_calls"):
                        break

                    if (
                        candidate.get("role") == "tool"
                        and candidate.get("tool_call_id") == call_id
                    ):
                        found_index = j
                        break

                if found_index is not None:
                    repaired_messages.append(deepcopy(messages[found_index]))
                    consumed_tool_indexes.add(found_index)
                    seen_call_ids.add(call_id)
                    repaired = True
                    continue

                repaired_messages.append(_synthetic_tool_message(call_id))
                seen_call_ids.add(call_id)
                repaired = True

            continue

        if role == "tool":
            repaired = True
            repaired_messages.append(
                {
                    "role": "user",
                    "content": (
                        "[orphaned tool output ignored by protocol repair]\n"
                        f"tool_call_id={message.get('tool_call_id') or 'unknown'}\n"
                        f"content={message.get('content', '')}"
                    ),
                }
            )
            i += 1
            continue

        repaired_messages.append(message)
        i += 1

    return repaired_messages, repaired


def _flatten_self_contained_tool_messages(
    messages: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], bool]:
    """Convert self-contained tool protocol fragments into plain text.

    Codex can send function_call and function_call_output items in the same
    request without a previous_response_id. If no function tools are available
    for DeepSeek in that request, sending assistant tool_calls/tool messages as
    ChatCompletions protocol can be rejected by DeepSeek. In that case, preserve
    the information as normal text transcript instead of protocol messages.
    """
    flattened = False
    flattened_messages: list[dict[str, Any]] = []

    i = 0
    while i < len(messages):
        message = messages[i]
        role = message.get("role")
        tool_calls = message.get("tool_calls") or []

        if role == "assistant" and tool_calls:
            flattened = True
            transcript_parts: list[str] = []

            content = _plain_text_from_content(message.get("content", ""))
            if content:
                transcript_parts.append(f"assistant_content:\n{content}")

            transcript_parts.append("assistant_requested_tool_calls:")
            for tool_call in tool_calls:
                function = tool_call.get("function") or {}
                transcript_parts.append(
                    "\n".join(
                        [
                            f"- tool_call_id: {tool_call.get('id') or 'unknown'}",
                            f"  name: {function.get('name') or ''}",
                            f"  arguments: {function.get('arguments') or ''}",
                        ]
                    )
                )

            flattened_messages.append(
                {
                    "role": "user",
                    "content": "[tool call transcript]\n" + "\n".join(transcript_parts),
                }
            )
            i += 1
            continue

        if role == "tool":
            flattened = True
            flattened_messages.append(
                {
                    "role": "user",
                    "content": (
                        "[tool output transcript]\n"
                        f"tool_call_id: {message.get('tool_call_id') or 'unknown'}\n"
                        f"output:\n{_stringify_content(message.get('content', ''))}"
                    ),
                }
            )
            i += 1
            continue

        flattened_messages.append(deepcopy(message))
        i += 1

    return flattened_messages, flattened

@dataclass
class StoredResponse:
    response: dict[str, Any]
    chat_messages: list[dict[str, Any]]


class InMemoryResponseStore:
    def __init__(self) -> None:
        self._responses: dict[str, StoredResponse] = {}

    def save(self, response: dict[str, Any], chat_messages: list[dict[str, Any]]) -> None:
        self._responses[response["id"]] = StoredResponse(
            response=deepcopy(response),
            chat_messages=deepcopy(chat_messages),
        )

    def get(self, response_id: str) -> StoredResponse | None:
        stored = self._responses.get(response_id)
        if stored is None:
            return None
        return StoredResponse(response=deepcopy(stored.response), chat_messages=deepcopy(stored.chat_messages))


class SQLiteResponseStore:
    """Persistent response store backed by SQLite.

    This preserves response_id -> response/chat_messages state across proxy
    restarts, which is required for previous_response_id continuations after
    a local proxy restart.
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path).expanduser() if db_path is not None else _default_db_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS responses (
                    response_id TEXT PRIMARY KEY,
                    created_at INTEGER NOT NULL,
                    response_json TEXT NOT NULL,
                    chat_messages_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_responses_created_at ON responses(created_at)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS usage_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at INTEGER NOT NULL,
                    response_id TEXT,
                    previous_response_id TEXT,
                    model TEXT NOT NULL,
                    thinking_enabled INTEGER NOT NULL,
                    prompt_tokens INTEGER NOT NULL,
                    completion_tokens INTEGER NOT NULL,
                    total_tokens INTEGER NOT NULL,
                    cached_tokens INTEGER NOT NULL,
                    reasoning_tokens INTEGER NOT NULL,
                    estimated_cost_usd REAL NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_usage_events_created_at ON usage_events(created_at)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_usage_events_response_id ON usage_events(response_id)"
            )
            self._migrate_usage_events_schema(conn)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_usage_events_purpose ON usage_events(purpose)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_usage_events_request_id ON usage_events(request_id)"
            )

    @staticmethod
    def _ensure_column(
        conn: sqlite3.Connection,
        *,
        table: str,
        column: str,
        ddl: str,
    ) -> None:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        existing = {row["name"] for row in rows}
        if column not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")

    def _migrate_usage_events_schema(self, conn: sqlite3.Connection) -> None:
        self._ensure_column(
            conn,
            table="usage_events",
            column="purpose",
            ddl="TEXT NOT NULL DEFAULT 'final'",
        )
        self._ensure_column(
            conn,
            table="usage_events",
            column="call_index",
            ddl="INTEGER",
        )
        self._ensure_column(
            conn,
            table="usage_events",
            column="request_id",
            ddl="TEXT",
        )
        self._ensure_column(
            conn,
            table="usage_events",
            column="requested_model",
            ddl="TEXT",
        )
        self._ensure_column(
            conn,
            table="usage_events",
            column="effective_model",
            ddl="TEXT",
        )
        self._ensure_column(
            conn,
            table="usage_events",
            column="upstream_model",
            ddl="TEXT",
        )

    def save(self, response: dict[str, Any], chat_messages: list[dict[str, Any]]) -> None:
        response_id = response["id"]
        created_at = int(response.get("created_at") or _now())
        response_json = json.dumps(response, ensure_ascii=False)
        chat_messages_json = json.dumps(chat_messages, ensure_ascii=False)

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO responses (
                    response_id,
                    created_at,
                    response_json,
                    chat_messages_json
                )
                VALUES (?, ?, ?, ?)
                ON CONFLICT(response_id) DO UPDATE SET
                    created_at = excluded.created_at,
                    response_json = excluded.response_json,
                    chat_messages_json = excluded.chat_messages_json
                """,
                (response_id, created_at, response_json, chat_messages_json),
            )

    def get(self, response_id: str) -> StoredResponse | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT response_json, chat_messages_json
                FROM responses
                WHERE response_id = ?
                """,
                (response_id,),
            ).fetchone()

        if row is None:
            return None

        return StoredResponse(
            response=json.loads(row["response_json"]),
            chat_messages=json.loads(row["chat_messages_json"]),
        )

    def record_usage(
        self,
        *,
        response_id: str | None,
        previous_response_id: str | None,
        model: str,
        thinking_enabled: bool,
        usage_numbers: dict[str, int],
        estimated_cost_usd: float,
        purpose: str = "final",
        call_index: int | None = None,
        request_id: str | None = None,
        requested_model: str | None = None,
        effective_model: str | None = None,
        upstream_model: str | None = None,
    ) -> None:
        normalized_purpose = str(purpose or "final").strip() or "final"
        normalized_effective_model = str(effective_model or model).strip() or model
        normalized_upstream_model = str(upstream_model or normalized_effective_model).strip() or normalized_effective_model

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO usage_events (
                    created_at,
                    response_id,
                    previous_response_id,
                    model,
                    thinking_enabled,
                    purpose,
                    call_index,
                    request_id,
                    requested_model,
                    effective_model,
                    upstream_model,
                    prompt_tokens,
                    completion_tokens,
                    total_tokens,
                    cached_tokens,
                    reasoning_tokens,
                    estimated_cost_usd
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _now(),
                    response_id,
                    previous_response_id,
                    model,
                    1 if thinking_enabled else 0,
                    normalized_purpose,
                    call_index,
                    request_id,
                    requested_model,
                    normalized_effective_model,
                    normalized_upstream_model,
                    usage_numbers["prompt_tokens"],
                    usage_numbers["completion_tokens"],
                    usage_numbers["total_tokens"],
                    usage_numbers["cached_tokens"],
                    usage_numbers["reasoning_tokens"],
                    estimated_cost_usd,
                ),
            )

    @staticmethod
    def _usage_filter_where(
        *,
        since: int | None = None,
        until: int | None = None,
        thinking: bool | None = None,
        model: str | None = None,
        purpose: str | None = None,
    ) -> tuple[str, list[Any]]:
        clauses: list[str] = []
        params: list[Any] = []

        if since is not None:
            clauses.append("created_at >= ?")
            params.append(int(since))

        if until is not None:
            clauses.append("created_at <= ?")
            params.append(int(until))

        if thinking is not None:
            clauses.append("thinking_enabled = ?")
            params.append(1 if thinking else 0)

        if model:
            clauses.append("model = ?")
            params.append(model)

        if purpose:
            clauses.append("purpose = ?")
            params.append(purpose)

        if not clauses:
            return "", params

        return " WHERE " + " AND ".join(clauses), params

    def usage_events(
        self,
        limit: int = 100,
        *,
        since: int | None = None,
        until: int | None = None,
        thinking: bool | None = None,
        model: str | None = None,
        purpose: str | None = None,
    ) -> list[dict[str, Any]]:
        where_sql, params = self._usage_filter_where(
            since=since,
            until=until,
            thinking=thinking,
            model=model,
            purpose=purpose,
        )

        safe_limit = max(1, min(int(limit), 1000))

        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT
                    created_at,
                    response_id,
                    previous_response_id,
                    model,
                    thinking_enabled,
                    purpose,
                    call_index,
                    request_id,
                    requested_model,
                    effective_model,
                    upstream_model,
                    prompt_tokens,
                    completion_tokens,
                    total_tokens,
                    cached_tokens,
                    reasoning_tokens,
                    estimated_cost_usd
                FROM usage_events
                {where_sql}
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                [*params, safe_limit],
            ).fetchall()

        return [dict(row) for row in rows]

    def usage_summary(
        self,
        *,
        since: int | None = None,
        until: int | None = None,
        thinking: bool | None = None,
        model: str | None = None,
        purpose: str | None = None,
    ) -> dict[str, Any]:
        where_sql, params = self._usage_filter_where(
            since=since,
            until=until,
            thinking=thinking,
            model=model,
            purpose=purpose,
        )

        with self._connect() as conn:
            row = conn.execute(
                f"""
                SELECT
                    COUNT(*) AS request_count,
                    COALESCE(SUM(prompt_tokens), 0) AS prompt_tokens,
                    COALESCE(SUM(completion_tokens), 0) AS completion_tokens,
                    COALESCE(SUM(total_tokens), 0) AS total_tokens,
                    COALESCE(SUM(cached_tokens), 0) AS cached_tokens,
                    COALESCE(SUM(reasoning_tokens), 0) AS reasoning_tokens,
                    COALESCE(SUM(estimated_cost_usd), 0.0) AS estimated_cost_usd
                FROM usage_events
                {where_sql}
                """,
                params,
            ).fetchone()

        return dict(row)



def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default

    try:
        value = float(raw)
    except ValueError:
        print(f"[deepseek-responses-proxy] invalid {name}={raw!r}; using {default}")
        return default

    if value <= 0:
        print(f"[deepseek-responses-proxy] non-positive {name}={raw!r}; using {default}")
        return default

    return value


def _json_char_size(value: Any) -> int:
    try:
        return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")))
    except Exception:
        return len(str(value))


def _append_context_trim_operation(report: dict[str, Any], operation: dict[str, Any]) -> None:
    operations = report.setdefault("operations", [])
    if len(operations) < 200:
        operations.append(operation)
    else:
        report["operations_truncated"] = True


def _truncate_middle_text(text: str, limit: int) -> tuple[str, bool]:
    if limit < 0:
        limit = 0
    if len(text) <= limit:
        return text, False
    if limit == 0:
        return "", True

    marker = f"\n...[deepseek-proxy context trimmed: original_chars={len(text)}]...\n"
    if limit <= len(marker) + 2:
        return text[:limit], True

    remaining = limit - len(marker)
    head_len = remaining // 2
    tail_len = remaining - head_len
    return text[:head_len] + marker + text[-tail_len:], True


def _context_trim_env_config() -> dict[str, int]:
    return {
        "max_context_chars": _env_int("DEEPSEEK_PROXY_MAX_CONTEXT_CHARS", 1_500_000),
        "max_tool_output_chars": _env_int("DEEPSEEK_PROXY_MAX_TOOL_OUTPUT_CHARS", 60_000),
        "keep_recent_messages": _env_int("DEEPSEEK_PROXY_KEEP_RECENT_MESSAGES", 24),
    }


def _safe_recent_message_start(messages: list[dict[str, Any]], keep_recent_messages: int) -> int:
    if keep_recent_messages <= 0:
        keep_recent_messages = 1

    start = max(0, len(messages) - keep_recent_messages)

    # Do not begin the retained tail with a tool result. If the nominal cut point
    # lands inside an assistant tool_call -> tool output pair, pull the boundary
    # back to include the assistant request as well.
    while start > 0 and isinstance(messages[start], dict) and messages[start].get("role") == "tool":
        start -= 1

    return start


def _trim_message_text_field(
    container: dict[str, Any],
    key: str,
    *,
    limit: int,
    location: str,
    report: dict[str, Any],
) -> bool:
    value = container.get(key)
    if not isinstance(value, str):
        return False

    trimmed_value, changed = _truncate_middle_text(value, limit)
    if not changed:
        return False

    container[key] = trimmed_value
    report["trimmed"] = True
    report["trimmed_fields"] = int(report.get("trimmed_fields", 0)) + 1
    _append_context_trim_operation(
        report,
        {
            "kind": "truncate_text_field",
            "location": location,
            "original_chars": len(value),
            "trimmed_chars": len(trimmed_value),
            "limit": limit,
        },
    )
    return True


def _trim_message_for_context(
    message: dict[str, Any],
    *,
    index: int,
    is_recent: bool,
    max_tool_output_chars: int,
    report: dict[str, Any],
) -> dict[str, Any]:
    trimmed = deepcopy(message)
    role = trimmed.get("role")

    # Tool outputs are the dominant source of Codex context explosions. Trim them
    # even in recent turns, while preserving role, tool_call_id, and ordering.
    if role == "tool":
        _trim_message_text_field(
            trimmed,
            "content",
            limit=max_tool_output_chars,
            location=f"messages[{index}].content",
            report=report,
        )

    # Older plain-text content can also grow without bound. Keep recent content
    # mostly intact, but compact older non-system messages.
    if role not in {"system", "developer", "tool"} and not is_recent:
        _trim_message_text_field(
            trimmed,
            "content",
            limit=max_tool_output_chars,
            location=f"messages[{index}].content",
            report=report,
        )

    # DeepSeek thinking history can accumulate large hidden reasoning payloads.
    # Preserve the field but cap its size.
    _trim_message_text_field(
        trimmed,
        "reasoning_content",
        limit=max_tool_output_chars,
        location=f"messages[{index}].reasoning_content",
        report=report,
    )

    # Function-call arguments can become large for apply_patch or shell-like
    # tools. Only trim old arguments so active/recent tool calls keep fidelity.
    if not is_recent:
        tool_calls = trimmed.get("tool_calls") or []
        if isinstance(tool_calls, list):
            for tool_index, tool_call in enumerate(tool_calls):
                if not isinstance(tool_call, dict):
                    continue
                function = tool_call.get("function") or {}
                if not isinstance(function, dict):
                    continue
                _trim_message_text_field(
                    function,
                    "arguments",
                    limit=max_tool_output_chars,
                    location=f"messages[{index}].tool_calls[{tool_index}].function.arguments",
                    report=report,
                )

    return trimmed


def _compact_old_message_prefix(
    messages: list[dict[str, Any]],
    *,
    keep_recent_messages: int,
    report: dict[str, Any],
) -> list[dict[str, Any]]:
    if len(messages) <= keep_recent_messages:
        return messages

    leading_system: list[dict[str, Any]] = []
    cursor = 0
    while cursor < len(messages):
        message = messages[cursor]
        if isinstance(message, dict) and message.get("role") in {"system", "developer"}:
            leading_system.append(message)
            cursor += 1
            continue
        break

    recent_start = _safe_recent_message_start(messages, keep_recent_messages)
    if recent_start <= cursor:
        return messages

    compacted = messages[cursor:recent_start]
    retained = messages[recent_start:]
    role_counts: dict[str, int] = {}
    compacted_chars = _json_char_size(compacted)
    for message in compacted:
        if isinstance(message, dict):
            role = str(message.get("role") or "unknown")
        else:
            role = "unknown"
        role_counts[role] = role_counts.get(role, 0) + 1

    summary_text = (
        "[deepseek-proxy context compacted]\n"
        f"compacted_message_count: {len(compacted)}\n"
        f"compacted_chars: {compacted_chars}\n"
        f"role_counts: {json.dumps(role_counts, ensure_ascii=False, sort_keys=True)}\n"
        "Older messages were summarized by the proxy to avoid exceeding the "
        "DeepSeek upstream context limit. Recent messages and tool-call protocol "
        "structure are retained."
    )
    summary_message = {"role": "user", "content": summary_text}

    report["trimmed"] = True
    report["compacted_message_count"] = int(report.get("compacted_message_count", 0)) + len(compacted)
    _append_context_trim_operation(
        report,
        {
            "kind": "compact_old_message_prefix",
            "compacted_message_count": len(compacted),
            "compacted_chars": compacted_chars,
            "retained_recent_messages": len(retained),
            "role_counts": role_counts,
        },
    )

    return leading_system + [summary_message] + retained


def _iter_payload_string_fields(payload: dict[str, Any]):
    messages = payload.get("messages")
    if not isinstance(messages, list):
        return

    for index, message in enumerate(messages):
        if not isinstance(message, dict):
            continue
        for key in ("content", "reasoning_content"):
            value = message.get(key)
            if isinstance(value, str):
                yield f"messages[{index}].{key}", message, key, len(value)

        tool_calls = message.get("tool_calls") or []
        if isinstance(tool_calls, list):
            for tool_index, tool_call in enumerate(tool_calls):
                if not isinstance(tool_call, dict):
                    continue
                function = tool_call.get("function") or {}
                if not isinstance(function, dict):
                    continue
                value = function.get("arguments")
                if isinstance(value, str):
                    yield (
                        f"messages[{index}].tool_calls[{tool_index}].function.arguments",
                        function,
                        "arguments",
                        len(value),
                    )


def _aggressively_shrink_payload_to_limit(
    payload: dict[str, Any],
    *,
    max_context_chars: int,
    report: dict[str, Any],
) -> dict[str, Any]:
    # Last-resort safety valve. It never changes roles, ordering, tool_call_id, or
    # function names. It only shortens string fields until the serialized request
    # falls below the configured character budget or no useful string remains.
    for _ in range(100):
        current_chars = _json_char_size(payload)
        if current_chars <= max_context_chars:
            return payload

        fields = list(_iter_payload_string_fields(payload) or [])
        if not fields:
            return payload

        location, container, key, current_len = max(fields, key=lambda item: item[3])
        if current_len <= 256:
            return payload

        excess = current_chars - max_context_chars
        new_limit = max(128, current_len - max(excess + 512, current_len // 2))
        old_value = container[key]
        if not isinstance(old_value, str):
            return payload

        new_value, changed = _truncate_middle_text(old_value, new_limit)
        if not changed:
            return payload

        container[key] = new_value
        report["trimmed"] = True
        report["aggressive_trimmed_fields"] = int(report.get("aggressive_trimmed_fields", 0)) + 1
        _append_context_trim_operation(
            report,
            {
                "kind": "aggressive_truncate_text_field",
                "location": location,
                "original_chars": current_len,
                "trimmed_chars": len(new_value),
                "target_payload_chars": max_context_chars,
            },
        )

    return payload


def _compact_deepseek_payload_context(payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    config = _context_trim_env_config()
    max_context_chars = config["max_context_chars"]
    max_tool_output_chars = config["max_tool_output_chars"]
    keep_recent_messages = config["keep_recent_messages"]

    before_chars = _json_char_size(payload)
    messages = payload.get("messages")
    report: dict[str, Any] = {
        "version": PROXY_VERSION,
        "enabled": True,
        "max_context_chars": max_context_chars,
        "max_tool_output_chars": max_tool_output_chars,
        "keep_recent_messages": keep_recent_messages,
        "before_chars": before_chars,
        "after_chars": before_chars,
        "trimmed": False,
        "message_count_before": len(messages) if isinstance(messages, list) else None,
        "message_count_after": len(messages) if isinstance(messages, list) else None,
        "operations": [],
    }

    if not isinstance(messages, list):
        return payload, report

    trimmed_payload = deepcopy(payload)
    trimmed_messages = trimmed_payload.get("messages")
    if not isinstance(trimmed_messages, list):
        return payload, report

    recent_start = _safe_recent_message_start(trimmed_messages, keep_recent_messages)
    new_messages: list[dict[str, Any]] = []
    for index, message in enumerate(trimmed_messages):
        if not isinstance(message, dict):
            new_messages.append(message)
            continue
        is_recent = index >= recent_start or message.get("role") in {"system", "developer"}
        new_messages.append(
            _trim_message_for_context(
                message,
                index=index,
                is_recent=is_recent,
                max_tool_output_chars=max_tool_output_chars,
                report=report,
            )
        )
    trimmed_payload["messages"] = new_messages

    if _json_char_size(trimmed_payload) > max_context_chars:
        trimmed_payload["messages"] = _compact_old_message_prefix(
            trimmed_payload["messages"],
            keep_recent_messages=keep_recent_messages,
            report=report,
        )

    if _json_char_size(trimmed_payload) > max_context_chars:
        trimmed_payload = _aggressively_shrink_payload_to_limit(
            trimmed_payload,
            max_context_chars=max_context_chars,
            report=report,
        )

    report["after_chars"] = _json_char_size(trimmed_payload)
    final_messages = trimmed_payload.get("messages")
    report["message_count_after"] = len(final_messages) if isinstance(final_messages, list) else None
    report["chars_removed"] = max(0, before_chars - int(report["after_chars"]))

    return trimmed_payload, report


def _context_compaction_env_config() -> dict[str, Any]:
    policy = os.environ.get("DEEPSEEK_PROXY_COMPACT_POLICY", "adaptive").strip().lower()
    if policy not in {"adaptive", "fixed"}:
        print(f"[deepseek-responses-proxy] invalid DEEPSEEK_PROXY_COMPACT_POLICY={policy!r}; using adaptive")
        policy = "adaptive"

    return {
        "enabled": _env_bool("DEEPSEEK_PROXY_COMPACT_ENABLED", True),
        "policy": policy,
        "max_context_chars": _env_int("DEEPSEEK_PROXY_MAX_CONTEXT_CHARS", 1_500_000),
        "trigger_chars": _env_int("DEEPSEEK_PROXY_COMPACT_TRIGGER_CHARS", 900_000),
        "target_chars": _env_int("DEEPSEEK_PROXY_COMPACT_TARGET_CHARS", 280_000),
        "keep_recent_messages": _env_int("DEEPSEEK_PROXY_COMPACT_KEEP_RECENT_MESSAGES", 24),
        "material_chars": _env_int("DEEPSEEK_PROXY_COMPACT_MATERIAL_CHARS", 260_000),
        "max_summary_chars": _env_int("DEEPSEEK_PROXY_COMPACT_MAX_SUMMARY_CHARS", 60_000),
        "min_target_chars": _env_int("DEEPSEEK_PROXY_COMPACT_MIN_TARGET_CHARS", 350_000),
        "max_target_chars": _env_int("DEEPSEEK_PROXY_COMPACT_MAX_TARGET_CHARS", 750_000),
        "min_new_chars": _env_int("DEEPSEEK_PROXY_COMPACT_MIN_NEW_CHARS", 250_000),
        "min_turns": _env_int("DEEPSEEK_PROXY_COMPACT_MIN_TURNS", 4),
        "emergency_ratio": _env_float("DEEPSEEK_PROXY_COMPACT_EMERGENCY_RATIO", 0.92),
        "recent_growth_messages": _env_int("DEEPSEEK_PROXY_COMPACT_RECENT_GROWTH_MESSAGES", 8),
        "expected_growth_turns": _env_int("DEEPSEEK_PROXY_COMPACT_EXPECTED_GROWTH_TURNS", 6),
        "reserve_before_min_chars": _env_int("DEEPSEEK_PROXY_COMPACT_RESERVE_BEFORE_MIN_CHARS", 250_000),
        "reserve_before_max_chars": _env_int("DEEPSEEK_PROXY_COMPACT_RESERVE_BEFORE_MAX_CHARS", 600_000),
        "reserve_after_min_chars": _env_int("DEEPSEEK_PROXY_COMPACT_RESERVE_AFTER_MIN_CHARS", 350_000),
        "reserve_after_max_chars": _env_int("DEEPSEEK_PROXY_COMPACT_RESERVE_AFTER_MAX_CHARS", 750_000),
    }


def _clamp_int(value: int, low: int, high: int) -> int:
    if high < low:
        low, high = high, low
    return max(low, min(high, int(value)))


def _last_persistent_compaction_summary_index(messages: list[dict[str, Any]]) -> int | None:
    marker = "[deepseek-proxy persistent compaction summary]"
    for index in range(len(messages) - 1, -1, -1):
        message = messages[index]
        if not isinstance(message, dict):
            continue
        content = _plain_text_from_content(message.get("content", ""))
        if marker in content:
            return index
    return None


def _recent_growth_stats_for_compaction(
    messages: list[dict[str, Any]],
    *,
    recent_growth_messages: int,
) -> dict[str, Any]:
    recent_growth_messages = max(1, int(recent_growth_messages))
    recent = messages[-recent_growth_messages:] if messages else []
    recent_chars = _json_char_size({"messages": recent}) if recent else 0
    recent_count = len(recent)
    recent_growth_chars_per_turn = int(recent_chars / max(1, recent_count))

    last_summary_index = _last_persistent_compaction_summary_index(messages)
    if last_summary_index is None:
        new_messages = messages
        turns_since_last_compaction = len(messages)
    else:
        new_messages = messages[last_summary_index + 1 :]
        turns_since_last_compaction = len(new_messages)

    new_chars_since_last_compaction = _json_char_size({"messages": new_messages}) if new_messages else 0

    return {
        "recent_message_count": recent_count,
        "recent_growth_chars": recent_chars,
        "recent_growth_chars_per_turn": recent_growth_chars_per_turn,
        "last_compaction_summary_index": last_summary_index,
        "new_chars_since_last_compaction": new_chars_since_last_compaction,
        "turns_since_last_compaction": turns_since_last_compaction,
    }


def _resolve_compaction_budget_policy(
    *,
    messages: list[dict[str, Any]],
    before_chars: int,
    config: dict[str, Any],
) -> dict[str, Any]:
    policy = str(config.get("policy") or "adaptive")
    fixed_trigger = max(1, int(config["trigger_chars"]))
    fixed_target = max(1, int(config["target_chars"]))

    if policy == "fixed":
        should_compact = before_chars > fixed_trigger
        return {
            "policy": "fixed",
            "should_compact": should_compact,
            "reason": "fixed_triggered" if should_compact else "not_triggered",
            "effective_trigger_chars": fixed_trigger,
            "effective_target_chars": fixed_target,
            "emergency_chars": None,
            "reserve_before_send": None,
            "reserve_after_compact": None,
            "growth": _recent_growth_stats_for_compaction(
                messages,
                recent_growth_messages=int(config["recent_growth_messages"]),
            ),
        }

    max_context_chars = max(1, int(config["max_context_chars"]))
    min_target_chars = max(1, int(config["min_target_chars"]))
    max_target_chars = max(min_target_chars, int(config["max_target_chars"]))
    emergency_ratio = float(config["emergency_ratio"])
    if emergency_ratio <= 0 or emergency_ratio > 1:
        emergency_ratio = 0.92

    growth = _recent_growth_stats_for_compaction(
        messages,
        recent_growth_messages=int(config["recent_growth_messages"]),
    )
    growth_per_turn = max(1, int(growth["recent_growth_chars_per_turn"]))

    reserve_before_send = _clamp_int(
        4 * growth_per_turn,
        int(config["reserve_before_min_chars"]),
        int(config["reserve_before_max_chars"]),
    )
    reserve_after_compact = _clamp_int(
        int(config["expected_growth_turns"]) * growth_per_turn,
        int(config["reserve_after_min_chars"]),
        int(config["reserve_after_max_chars"]),
    )

    adaptive_trigger = max(1, max_context_chars - reserve_before_send)
    if "DEEPSEEK_PROXY_COMPACT_TRIGGER_CHARS" in os.environ:
        adaptive_trigger = min(adaptive_trigger, fixed_trigger)

    adaptive_target = _clamp_int(
        max_context_chars - reserve_after_compact,
        min_target_chars,
        max_target_chars,
    )
    if "DEEPSEEK_PROXY_COMPACT_TARGET_CHARS" in os.environ:
        adaptive_target = _clamp_int(
            min(adaptive_target, fixed_target),
            1,
            max_target_chars,
        )

    emergency_chars = max(1, int(max_context_chars * emergency_ratio))
    is_emergency = before_chars >= emergency_chars

    new_chars = int(growth["new_chars_since_last_compaction"])
    turns_since = int(growth["turns_since_last_compaction"])
    min_new_chars = int(config["min_new_chars"])
    min_turns = int(config["min_turns"])
    has_previous_compaction = growth["last_compaction_summary_index"] is not None

    if before_chars <= adaptive_trigger and not is_emergency:
        should_compact = False
        reason = "not_triggered"
    elif is_emergency:
        should_compact = True
        reason = "adaptive_emergency_triggered"
    elif has_previous_compaction and new_chars < min_new_chars and turns_since < min_turns:
        should_compact = False
        reason = "adaptive_cooldown"
    else:
        should_compact = True
        reason = "adaptive_triggered"

    return {
        "policy": "adaptive",
        "should_compact": should_compact,
        "reason": reason,
        "effective_trigger_chars": adaptive_trigger,
        "effective_target_chars": adaptive_target,
        "emergency_chars": emergency_chars,
        "reserve_before_send": reserve_before_send,
        "reserve_after_compact": reserve_after_compact,
        "min_new_chars": min_new_chars,
        "min_turns": min_turns,
        "growth": growth,
    }


def _extract_deepseek_message_text(deepseek_response: dict[str, Any]) -> str:
    try:
        choices = deepseek_response.get("choices") or []
        if not choices:
            return ""
        message = choices[0].get("message") or {}
        return _plain_text_from_content(message.get("content", ""))
    except Exception:
        return ""


def _summarize_large_tool_output_for_compaction(content: str, *, limit: int = 5000) -> str:
    if len(content) <= limit:
        return content

    lower = content.lower()
    facts: list[str] = []
    for needle in [
        "passed",
        "failed",
        "error",
        "traceback",
        "syntaxerror",
        "indentationerror",
        "commit",
        "tag:",
        "git status",
        "git diff",
        "py_compile",
        "pytest",
        "out=",
    ]:
        if needle in lower:
            facts.append(needle)

    marker = (
        f"\n...[tool output summarized for compaction: original_chars={len(content)}, "
        f"detected_terms={json.dumps(facts[:20], ensure_ascii=False)}]...\n"
    )
    remaining = max(0, limit - len(marker))
    head_len = remaining // 2
    tail_len = remaining - head_len
    return content[:head_len] + marker + content[-tail_len:]


def _message_to_compaction_material(message: dict[str, Any], *, index: int) -> str:
    role = str(message.get("role") or "unknown")
    lines = [f"### message[{index}] role={role}"]

    if message.get("name"):
        lines.append(f"name: {message.get('name')}")
    if message.get("tool_call_id"):
        lines.append(f"tool_call_id: {message.get('tool_call_id')}")

    content = _plain_text_from_content(message.get("content", ""))
    if role == "tool":
        content = _summarize_large_tool_output_for_compaction(content, limit=7000)
    else:
        content, _ = _truncate_middle_text(content, 7000)
    if content:
        lines.append("content:")
        lines.append(content)

    reasoning_content = message.get("reasoning_content")
    if isinstance(reasoning_content, str) and reasoning_content:
        trimmed_reasoning, _ = _truncate_middle_text(reasoning_content, 3000)
        lines.append("reasoning_content:")
        lines.append(trimmed_reasoning)

    tool_calls = message.get("tool_calls") or []
    if isinstance(tool_calls, list) and tool_calls:
        lines.append("tool_calls:")
        for tool_index, tool_call in enumerate(tool_calls):
            if not isinstance(tool_call, dict):
                continue
            function = tool_call.get("function") or {}
            function_name = function.get("name") if isinstance(function, dict) else None
            arguments = function.get("arguments") if isinstance(function, dict) else ""
            if not isinstance(arguments, str):
                arguments = json.dumps(arguments, ensure_ascii=False)
            arguments, _ = _truncate_middle_text(arguments, 3000)
            lines.append(
                f"- index={tool_index} id={tool_call.get('id')} "
                f"type={tool_call.get('type')} function={function_name}"
            )
            if arguments:
                lines.append(f"  arguments: {arguments}")

    return "\n".join(lines)


def _build_compaction_material(
    messages: list[dict[str, Any]],
    *,
    material_chars: int,
    keep_recent_messages: int,
) -> tuple[str, int]:
    recent_start = _safe_recent_message_start(messages, keep_recent_messages)
    compactable = messages[:recent_start]
    rendered: list[str] = []
    total = 0

    for index, message in enumerate(compactable):
        if not isinstance(message, dict):
            continue
        chunk = _message_to_compaction_material(message, index=index)
        if total + len(chunk) > material_chars:
            remaining = max(0, material_chars - total)
            if remaining > 500:
                rendered.append(chunk[:remaining] + "\n...[compaction material truncated]...")
            break
        rendered.append(chunk)
        total += len(chunk) + 2

    return "\n\n".join(rendered), len(compactable)


def _compaction_prompt_messages(
    messages: list[dict[str, Any]],
    *,
    material_chars: int,
    keep_recent_messages: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    material, compactable_count = _build_compaction_material(
        messages,
        material_chars=material_chars,
        keep_recent_messages=keep_recent_messages,
    )

    recent_start = _safe_recent_message_start(messages, keep_recent_messages)
    recent_messages = messages[recent_start:]
    recent_material = "\n\n".join(
        _message_to_compaction_material(message, index=recent_start + offset)
        for offset, message in enumerate(recent_messages)
        if isinstance(message, dict)
    )

    system_prompt = (
        "You are a Codex-like conversation compactor for a coding agent. "
        "Summarize the older conversation history so the agent can continue "
        "the same development task after context compaction. Preserve concrete "
        "repo paths, branch/tag/commit names, files changed, commands run, test "
        "results, failures, user constraints, and exact next steps. Do not invent."
    )

    user_prompt = (
        "Compress the OLD CONVERSATION MATERIAL into a durable handoff summary.\n\n"
        "Output plain text with these headings exactly:\n"
        "OBJECTIVE\n"
        "REPOSITORY_STATE\n"
        "COMPLETED_CHANGES\n"
        "FILES_AND_CODE_AREAS\n"
        "TESTS_AND_VALIDATION\n"
        "OPEN_ISSUES\n"
        "USER_CONSTRAINTS\n"
        "NEXT_STEPS\n\n"
        "Rules:\n"
        "- Preserve exact paths, versions, commits, tags, env vars, and command results.\n"
        "- Preserve why decisions were made, not just what changed.\n"
        "- Summarize long command output into facts, not raw logs.\n"
        "- Do not include irrelevant chat.\n"
        "- Do not claim tests passed unless the material says so.\n\n"
        f"OLD CONVERSATION MATERIAL compactable_count={compactable_count}:\n"
        f"{material}\n\n"
        "RECENT MESSAGES KEPT VERBATIM AFTER SUMMARY. Use these only for continuity, "
        "do not repeat them fully:\n"
        f"{recent_material}"
    )

    meta = {
        "compactable_message_count": compactable_count,
        "recent_message_count": len(recent_messages),
        "recent_start": recent_start,
        "material_chars": len(material),
        "recent_material_chars": len(recent_material),
    }

    return (
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        meta,
    )


def _fallback_compaction_summary(
    messages: list[dict[str, Any]],
    *,
    material_chars: int,
    keep_recent_messages: int,
) -> str:
    material, compactable_count = _build_compaction_material(
        messages,
        material_chars=material_chars,
        keep_recent_messages=keep_recent_messages,
    )
    material, _ = _truncate_middle_text(material, 50_000)
    return (
        "OBJECTIVE\n"
        "Continue the existing coding-agent session after local proxy compaction.\n\n"
        "REPOSITORY_STATE\n"
        "The proxy could not obtain an LLM-generated compaction summary, so this "
        "fallback summary preserves compacted older material in truncated form.\n\n"
        "COMPLETED_CHANGES\n"
        "See preserved material below.\n\n"
        "FILES_AND_CODE_AREAS\n"
        "See preserved material below.\n\n"
        "TESTS_AND_VALIDATION\n"
        "See preserved material below.\n\n"
        "OPEN_ISSUES\n"
        "Continue from the latest retained messages.\n\n"
        "USER_CONSTRAINTS\n"
        "Preserve the user's workflow: write command outputs to /tmp files, show "
        "paths/line counts/key summaries, run diff checks, compile checks, pytest, "
        "then commit and tag only after validation.\n\n"
        "NEXT_STEPS\n"
        "Use the recent retained messages as the authoritative immediate task.\n\n"
        f"FALLBACK_COMPACTED_MATERIAL compactable_count={compactable_count}\n"
        f"{material}"
    )


def _leading_system_developer_messages(messages: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    leading: list[dict[str, Any]] = []
    index = 0
    while index < len(messages):
        message = messages[index]
        if isinstance(message, dict) and message.get("role") in {"system", "developer"}:
            leading.append(deepcopy(message))
            index += 1
            continue
        break
    return leading, index


def _build_persistent_compacted_history(
    messages: list[dict[str, Any]],
    *,
    summary_text: str,
    keep_recent_messages: int,
    target_chars: int,
    max_summary_chars: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    leading, leading_end = _leading_system_developer_messages(messages)
    recent_start = max(leading_end, _safe_recent_message_start(messages, keep_recent_messages))
    recent = deepcopy(messages[recent_start:])

    summary_text, summary_was_trimmed = _truncate_middle_text(summary_text, max_summary_chars)
    summary_message = {
        "role": "user",
        "content": (
            "[deepseek-proxy persistent compaction summary]\n"
            "The older conversation history was compacted to keep the Codex-like "
            "agent loop within the DeepSeek context budget. Treat this summary as "
            "authoritative for earlier work, and treat the following recent messages "
            "as verbatim continuation context.\n\n"
            f"{summary_text}"
        ),
    }

    compacted = leading + [summary_message] + recent
    report: dict[str, Any] = {
        "leading_message_count": len(leading),
        "recent_message_count": len(recent),
        "recent_start": recent_start,
        "summary_chars": len(summary_text),
        "summary_was_trimmed": summary_was_trimmed,
        "before_final_shrink_chars": _json_char_size({"messages": compacted}),
        "after_final_shrink_chars": None,
        "final_shrink_report": None,
    }

    if _json_char_size({"messages": compacted}) > target_chars:
        shrink_payload = {"messages": compacted}
        shrink_report: dict[str, Any] = {
            "version": PROXY_VERSION,
            "enabled": True,
            "trimmed": False,
            "operations": [],
        }
        shrink_payload = _aggressively_shrink_payload_to_limit(
            shrink_payload,
            max_context_chars=target_chars,
            report=shrink_report,
        )
        compacted = shrink_payload.get("messages", compacted)
        report["final_shrink_report"] = shrink_report

    report["after_final_shrink_chars"] = _json_char_size({"messages": compacted})
    return compacted, report


async def _compact_chat_history_for_codex_like_persistence(
    *,
    deepseek_client: "DeepSeekClient",
    messages: list[dict[str, Any]],
    request_payload: dict[str, Any] | None,
    previous_response_id: str | None,
    store: Any | None = None,
    response_id: str | None = None,
    usage_call_counter: dict[str, int] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    config = _context_compaction_env_config()
    before_chars = _json_char_size({"messages": messages})
    policy_decision = _resolve_compaction_budget_policy(
        messages=messages,
        before_chars=before_chars,
        config=config,
    )
    effective_trigger_chars = int(policy_decision["effective_trigger_chars"])
    effective_target_chars = int(policy_decision["effective_target_chars"])

    report: dict[str, Any] = {
        "version": PROXY_VERSION,
        "enabled": bool(config["enabled"]),
        "policy": config["policy"],
        "compacted": False,
        "reason": "not_triggered",
        "previous_response_id": previous_response_id,
        "trigger_chars": config["trigger_chars"],
        "target_chars": config["target_chars"],
        "effective_trigger_chars": effective_trigger_chars,
        "effective_target_chars": effective_target_chars,
        "emergency_chars": policy_decision.get("emergency_chars"),
        "keep_recent_messages": config["keep_recent_messages"],
        "material_chars_limit": config["material_chars"],
        "max_summary_chars": config["max_summary_chars"],
        "before_chars": before_chars,
        "after_chars": before_chars,
        "message_count_before": len(messages),
        "message_count_after": len(messages),
        "summary_source": None,
        "policy_decision": policy_decision,
    }

    if not config["enabled"]:
        report["reason"] = "disabled"
        return messages, report

    if not policy_decision["should_compact"]:
        report["reason"] = str(policy_decision["reason"])
        return messages, report

    if len(messages) <= max(2, int(config["keep_recent_messages"])):
        report["reason"] = "too_few_messages"
        return messages, report

    compaction_messages, material_meta = _compaction_prompt_messages(
        messages,
        material_chars=int(config["material_chars"]),
        keep_recent_messages=int(config["keep_recent_messages"]),
    )
    report["material"] = material_meta

    compaction_payload = {
        "model": _select_upstream_model((request_payload or {}).get("model")),
        "messages": compaction_messages,
        "temperature": 0,
        "stream": False,
    }

    summary_text = ""
    try:
        deepseek_response = await _chat_completions_with_usage(
            deepseek_client=deepseek_client,
            store=store,
            payload=compaction_payload,
            purpose="compaction",
            response_id=response_id,
            previous_response_id=previous_response_id,
            request_id=response_id,
            requested_model=(request_payload or {}).get("model"),
            thinking_enabled=_thinking_enabled(),
            call_counter=usage_call_counter,
        )
        summary_text = _extract_deepseek_message_text(deepseek_response)
        report["summary_source"] = "deepseek"
    except Exception as exc:
        report["summary_source"] = "fallback"
        report["summary_error_type"] = type(exc).__name__
        report["summary_error"] = str(exc)[:1000]

    if not summary_text.strip():
        summary_text = _fallback_compaction_summary(
            messages,
            material_chars=int(config["material_chars"]),
            keep_recent_messages=int(config["keep_recent_messages"]),
        )
        if report["summary_source"] != "fallback":
            report["summary_source"] = "fallback_empty_summary"

    compacted_messages, build_report = _build_persistent_compacted_history(
        messages,
        summary_text=summary_text,
        keep_recent_messages=int(config["keep_recent_messages"]),
        target_chars=effective_target_chars,
        max_summary_chars=int(config["max_summary_chars"]),
    )

    report["compacted"] = True
    report["reason"] = str(policy_decision["reason"])
    report["after_chars"] = _json_char_size({"messages": compacted_messages})
    report["message_count_after"] = len(compacted_messages)
    report["chars_removed"] = max(0, before_chars - int(report["after_chars"]))
    report["build"] = build_report

    return compacted_messages, report


def _write_context_compaction_report(report: dict[str, Any]) -> None:
    try:
        debug_dir = Path(".debug")
        debug_dir.mkdir(exist_ok=True)
        (debug_dir / "context_compaction_report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as exc:
        print(f"[deepseek-responses-proxy] failed to write context compaction report: {exc}")


class DeepSeekClient:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.api_key = api_key or os.environ.get("DEEPSEEK_API_KEY", "")
        self.base_url = (base_url or os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")).rstrip("/")
        timeout_seconds = _env_float("DEEPSEEK_PROXY_UPSTREAM_TIMEOUT_SECONDS", 180.0)
        self._client = http_client or httpx.AsyncClient(timeout=timeout_seconds)

    async def user_balance(self) -> dict[str, Any]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        response = await self._client.get(
            f"{self.base_url}/user/balance",
            headers=headers,
        )

        if response.status_code >= 400:
            body = response.text
            print("[deepseek-responses-proxy] DeepSeek balance upstream error")
            print(f"[deepseek-responses-proxy] status={response.status_code}")
            print(f"[deepseek-responses-proxy] body={body}")
            raise HTTPException(
                status_code=502 if response.status_code != 429 else 429,
                detail={
                    "upstream": "deepseek",
                    "status_code": response.status_code,
                    "body": _truncate_error_body(body),
                },
            )

        try:
            return response.json()
        except ValueError as exc:
            raise HTTPException(
                status_code=502,
                detail={
                    "upstream": "deepseek",
                    "error_type": "invalid_json",
                    "message": str(exc),
                },
            ) from exc

    async def chat_completions(self, payload: dict[str, Any]) -> dict[str, Any]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload, context_trimming_report = _compact_deepseek_payload_context(payload)
        self.last_context_trimming_report = context_trimming_report

        # Debug aid: keep the last upstream payload without secrets.
        # This is useful because DeepSeek returns precise 400 error messages
        # for invalid tool schemas or invalid tool-message ordering.
        try:
            from pathlib import Path

            debug_dir = Path(".debug")
            debug_dir.mkdir(exist_ok=True)
            (debug_dir / "last_deepseek_payload.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            (debug_dir / "context_trimming_report.json").write_text(
                json.dumps(context_trimming_report, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:
            print(f"[deepseek-responses-proxy] failed to write debug payload: {exc}")

        response = await self._client.post(
            f"{self.base_url}/chat/completions",
            json=payload,
            headers=headers,
        )

        if response.status_code >= 400:
            body = response.text
            print("[deepseek-responses-proxy] DeepSeek upstream error")
            print(f"[deepseek-responses-proxy] status={response.status_code}")
            print(f"[deepseek-responses-proxy] body={body}")
            raise HTTPException(
                status_code=502,
                detail={
                    "upstream": "deepseek",
                    "status_code": response.status_code,
                    "body": body,
                },
            )

        return response.json()


def _next_usage_call_index(call_counter: dict[str, int] | None) -> int | None:
    if call_counter is None:
        return None
    value = int(call_counter.get("value", 0))
    call_counter["value"] = value + 1
    return value


async def _chat_completions_with_usage(
    *,
    deepseek_client: "DeepSeekClient",
    store: Any | None,
    payload: dict[str, Any],
    purpose: str,
    response_id: str | None,
    previous_response_id: str | None,
    request_id: str | None,
    requested_model: str | None,
    thinking_enabled: bool,
    call_counter: dict[str, int] | None = None,
) -> dict[str, Any]:
    effective_model = str(payload.get("model") or DEFAULT_MODEL)
    call_index = _next_usage_call_index(call_counter)

    _debug_trace_event(
        response_id,
        "upstream_call_started",
        purpose=purpose,
        call_index=call_index,
        requested_model=requested_model,
        effective_model=effective_model,
        thinking_enabled=thinking_enabled,
        payload_summary=_debug_trace_summary(payload, label="chat_payload"),
        message_count=len(payload.get("messages") or []) if isinstance(payload.get("messages"), list) else None,
    )
    started = time.time()
    try:
        deepseek_response = await deepseek_client.chat_completions(payload)
    except Exception as exc:
        _debug_trace_event(
            response_id,
            "upstream_call_failed",
            purpose=purpose,
            call_index=call_index,
            error_type=type(exc).__name__,
            message=str(exc)[:1000],
            elapsed_seconds=time.time() - started,
        )
        raise

    usage_numbers = _extract_usage_numbers(deepseek_response)
    estimated_cost_usd = _estimate_cost_usd(effective_model, usage_numbers)
    trimming_report = getattr(deepseek_client, "last_context_trimming_report", None)
    if isinstance(trimming_report, dict):
        _debug_trace_event(
            response_id,
            "context_trimming_finished",
            purpose=purpose,
            call_index=call_index,
            trimmed=trimming_report.get("trimmed"),
            before_chars=trimming_report.get("before_chars"),
            after_chars=trimming_report.get("after_chars"),
            chars_removed=trimming_report.get("chars_removed"),
            message_count_before=trimming_report.get("message_count_before"),
            message_count_after=trimming_report.get("message_count_after"),
            operations=trimming_report.get("operations"),
        )

    _debug_trace_event(
        response_id,
        "upstream_call_finished",
        purpose=purpose,
        call_index=call_index,
        elapsed_seconds=time.time() - started,
        usage=usage_numbers,
        estimated_cost_usd=estimated_cost_usd,
    )

    if store is not None and hasattr(store, "record_usage"):
        store.record_usage(
            response_id=response_id,
            previous_response_id=previous_response_id,
            model=effective_model,
            thinking_enabled=thinking_enabled,
            usage_numbers=usage_numbers,
            estimated_cost_usd=estimated_cost_usd,
            purpose=purpose,
            call_index=call_index,
            request_id=request_id,
            requested_model=requested_model,
            effective_model=effective_model,
            upstream_model=effective_model,
        )

    return deepseek_response


def _mcp_readonly_tool_names() -> set[str]:
    return {
        "cheap_router_status",
        "router_list_models",
        "router_quota_status",
        "memory_list",
        "memory_report",
        "memory_review_duplicates",
    }


def _mcp_write_tool_names() -> set[str]:
    return {
        "router_add_model",
        "router_set_default_model",
        "router_record_review",
        "memory_remember",
        "memory_update",
        "memory_forget",
    }


def _mcp_tutorial_tool_names() -> set[str]:
    return {
        "start_tutorial_run",
        "search_instructions",
        "read_source",
        "make_execution_plan",
        "revise_plan",
        "synthesize_options",
        "evaluate_sources",
        "record_feedback",
        "final_report",
    }


def _mcp_tool_proxy_name(namespace: str, tool_name: str) -> str:
    return f"{namespace}{tool_name}"


def _mcp_tool_forwarding_class(tool_name: str) -> str | None:
    if tool_name in _mcp_readonly_tool_names():
        return "readonly"
    if tool_name in _mcp_write_tool_names():
        return "write"
    if tool_name in _mcp_tutorial_tool_names():
        return "tutorial"
    return None


def _parse_mcp_proxy_tool_name(function_name: Any) -> dict[str, str] | None:
    """Parse flattened MCP function names such as mcp__server__tool.

    This parser is intentionally generic. It does not assume that a particular
    MCP server is installed, and it does not grant execution permission.
    """
    raw_name = str(function_name or "").strip()
    prefix = "mcp__"
    if not raw_name.startswith(prefix):
        return None

    body = raw_name[len(prefix):]
    server, sep, tool_name = body.partition("__")
    if not sep or not server or not tool_name:
        return None

    return {
        "server": server,
        "name": tool_name,
        "namespace": f"mcp__{server}__",
        "function_name": raw_name,
        "policy_key": f"{server}.{tool_name}",
    }


def _mcp_executor_policy_mode() -> str:
    mode = os.environ.get("DEEPSEEK_PROXY_MCP_POLICY", "codex").strip().lower()
    if mode in {"codex", "allowlist", "off"}:
        return mode
    return "codex"


def _mcp_executor_enabled() -> bool:
    if _mcp_executor_policy_mode() == "off":
        return False
    return _env_bool("DEEPSEEK_PROXY_MCP_EXECUTOR", True)


def _split_env_csv(name: str) -> set[str]:
    raw = os.environ.get(name, "")
    values: set[str] = set()
    for item in raw.split(","):
        normalized = item.strip()
        if normalized:
            values.add(normalized)
    return values


def _mcp_executor_readonly_allowlist() -> set[str]:
    return _split_env_csv("DEEPSEEK_PROXY_MCP_READONLY_ALLOWLIST")


def _mcp_executor_write_allowlist() -> set[str]:
    return _split_env_csv("DEEPSEEK_PROXY_MCP_WRITE_ALLOWLIST")


def _mcp_config_path() -> Path:
    configured = os.environ.get("DEEPSEEK_PROXY_MCP_CONFIG_PATH")
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".codex" / "config.toml"


def _safe_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, (str, int, float, bool))]


def _codex_mcp_config_snapshot(
    path: Path | None = None,
    *,
    include_env_values: bool = False,
) -> dict[str, Any]:
    config_path = path or _mcp_config_path()
    snapshot: dict[str, Any] = {
        "config_path": str(config_path),
        "exists": config_path.exists(),
        "server_count": 0,
        "servers": {},
        "error": None,
    }

    if not config_path.exists():
        return snapshot

    try:
        data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except Exception as exc:
        snapshot["error"] = f"{type(exc).__name__}: {exc}"
        return snapshot

    raw_servers = data.get("mcp_servers") or {}
    if not isinstance(raw_servers, dict):
        snapshot["error"] = "invalid_mcp_servers_root"
        return snapshot

    servers: dict[str, Any] = {}
    for server_name, raw_server in sorted(raw_servers.items()):
        if not isinstance(raw_server, dict):
            continue

        raw_tools = raw_server.get("tools") or {}
        tools: dict[str, Any] = {}
        if isinstance(raw_tools, dict):
            for tool_name, raw_tool in sorted(raw_tools.items()):
                if isinstance(raw_tool, dict):
                    tools[str(tool_name)] = {
                        "approval_mode": str(raw_tool.get("approval_mode") or ""),
                    }

        raw_env = raw_server.get("env") or {}
        env_keys = sorted(str(key) for key in raw_env.keys()) if isinstance(raw_env, dict) else []

        server_info: dict[str, Any] = {
            "command": str(raw_server.get("command") or ""),
            "args": _safe_string_list(raw_server.get("args")),
            "env_vars": _safe_string_list(raw_server.get("env_vars")),
            "env_keys": env_keys,
            "startup_timeout_sec": raw_server.get("startup_timeout_sec"),
            "tool_timeout_sec": raw_server.get("tool_timeout_sec"),
            "tool_count": len(tools),
            "tools": tools,
        }

        if include_env_values and isinstance(raw_env, dict):
            server_info["env"] = {
                str(key): str(value)
                for key, value in raw_env.items()
                if isinstance(key, str)
            }

        servers[str(server_name)] = server_info

    snapshot["servers"] = servers
    snapshot["server_count"] = len(servers)
    return snapshot


def _mcp_executor_backend_type() -> str:
    backend_type = os.environ.get("DEEPSEEK_PROXY_MCP_EXECUTOR_BACKEND", "stdio").strip().lower()
    if backend_type in {"none", "injected", "stdio"}:
        return backend_type
    return "stdio"


def _mcp_stdio_backend_enabled() -> bool:
    return _mcp_executor_backend_type() == "stdio"


def _mcp_executor_status() -> dict[str, Any]:
    backend_type = _mcp_executor_backend_type()
    injected_available = _MCP_EXECUTOR_BACKEND is not None
    executor_enabled = _mcp_executor_enabled()
    stdio_available = executor_enabled and backend_type == "stdio"

    return {
        "enabled": executor_enabled,
        "policy": _mcp_executor_policy_mode(),
        "backend": {
            "type": "injected" if injected_available else backend_type,
            "available": injected_available or stdio_available,
            "production_execution": stdio_available,
        },
        "readonly_allowlist": sorted(_mcp_executor_readonly_allowlist()),
        "write_allowlist": sorted(_mcp_executor_write_allowlist()),
        "discovery": _mcp_discovery_config_status(),
        "codex_config": _codex_mcp_config_snapshot(),
    }


def _mcp_executor_policy_decision(function_name: Any) -> dict[str, Any]:
    parsed = _parse_mcp_proxy_tool_name(function_name)
    if parsed is None:
        return {
            "ok": False,
            "kind": "not_mcp_tool",
            "function_name": str(function_name or ""),
        }

    if not _mcp_executor_enabled():
        return {
            "ok": False,
            "kind": "mcp_executor_disabled",
            "policy": _mcp_executor_policy_mode(),
            **parsed,
        }

    policy_mode = _mcp_executor_policy_mode()
    policy_key = parsed["policy_key"]

    if policy_mode == "codex":
        return {
            "ok": True,
            "kind": "allowed_codex_config",
            "permission": "codex",
            "policy": policy_mode,
            **parsed,
        }

    if policy_mode == "allowlist":
        if policy_key in _mcp_executor_readonly_allowlist():
            return {
                "ok": True,
                "kind": "allowed_readonly",
                "permission": "readonly",
                "policy": policy_mode,
                **parsed,
            }

        if policy_key in _mcp_executor_write_allowlist():
            return {
                "ok": True,
                "kind": "allowed_write",
                "permission": "write",
                "policy": policy_mode,
                **parsed,
            }

        return {
            "ok": False,
            "kind": "mcp_tool_not_allowed",
            "policy": policy_mode,
            **parsed,
        }

    return {
        "ok": False,
        "kind": "mcp_executor_disabled",
        "policy": policy_mode,
        **parsed,
    }


def _mcp_executor_denied_result(function_name: Any) -> dict[str, Any]:
    decision = _mcp_executor_policy_decision(function_name)
    error = str(decision.get("kind") or "mcp_tool_not_allowed")
    message = decision.get("message") or "MCP tool execution is not allowed by proxy policy."

    if decision.get("ok") is True:
        error = "mcp_executor_backend_unavailable"
        message = (
            "MCP tool is allowed by proxy policy, but proxy-side MCP execution "
            "backend is not implemented yet."
        )

    return {
        "ok": False,
        "tool": str(function_name or ""),
        "error": error,
        "mcp": {
            key: decision[key]
            for key in ["server", "name", "namespace", "policy_key", "permission"]
            if key in decision
        },
        "message": message,
    }


_MCP_EXECUTOR_BACKEND: Any | None = None


def _set_mcp_executor_backend_for_tests(backend: Any | None) -> None:
    """Install an in-process MCP executor backend for tests.

    Production MCP execution is intentionally not implemented in v2.5c.
    """
    global _MCP_EXECUTOR_BACKEND
    _MCP_EXECUTOR_BACKEND = backend


async def _execute_mcp_stdio_backend(
    *,
    function_name: str,
    parsed: dict[str, str],
    arguments: dict[str, Any],
    decision: dict[str, Any],
) -> dict[str, Any]:
    config_snapshot = _codex_mcp_config_snapshot(include_env_values=True)

    if not config_snapshot.get("exists"):
        return {
            "ok": False,
            "tool": function_name,
            "error": "mcp_config_missing",
            "mcp": {
                "server": parsed["server"],
                "name": parsed["name"],
                "namespace": parsed["namespace"],
                "policy_key": parsed["policy_key"],
                "permission": decision.get("permission"),
            },
        }

    if config_snapshot.get("error"):
        return {
            "ok": False,
            "tool": function_name,
            "error": "mcp_config_error",
            "message": str(config_snapshot.get("error")),
            "mcp": {
                "server": parsed["server"],
                "name": parsed["name"],
                "namespace": parsed["namespace"],
                "policy_key": parsed["policy_key"],
                "permission": decision.get("permission"),
            },
        }

    servers = config_snapshot.get("servers") or {}
    if not isinstance(servers, dict) or parsed["server"] not in servers:
        return {
            "ok": False,
            "tool": function_name,
            "error": "mcp_server_not_configured",
            "mcp": {
                "server": parsed["server"],
                "name": parsed["name"],
                "namespace": parsed["namespace"],
                "policy_key": parsed["policy_key"],
                "permission": decision.get("permission"),
            },
        }

    from deepseek_responses_proxy.mcp_stdio import (
        call_stdio_mcp_tool,
        discover_stdio_mcp_tools,
        mcp_server_config_from_snapshot,
    )

    server_snapshot = servers[parsed["server"]]
    if not isinstance(server_snapshot, dict):
        return {
            "ok": False,
            "tool": function_name,
            "error": "mcp_server_config_invalid",
            "mcp": {
                "server": parsed["server"],
                "name": parsed["name"],
                "namespace": parsed["namespace"],
                "policy_key": parsed["policy_key"],
                "permission": decision.get("permission"),
            },
        }

    config = mcp_server_config_from_snapshot(parsed["server"], server_snapshot)
    discovery = await discover_stdio_mcp_tools(config, client_version=PROXY_VERSION)
    discovered_tool_names = {
        str(tool.get("name") or "")
        for tool in discovery.get("tools", [])
        if isinstance(tool, dict)
    }

    if not discovery.get("ok"):
        return {
            "ok": False,
            "tool": function_name,
            "error": "mcp_discovery_failed_before_call",
            "discovery": discovery,
            "mcp": {
                "server": parsed["server"],
                "name": parsed["name"],
                "namespace": parsed["namespace"],
                "policy_key": parsed["policy_key"],
                "permission": decision.get("permission"),
            },
        }

    if parsed["name"] not in discovered_tool_names:
        return {
            "ok": False,
            "tool": function_name,
            "error": "mcp_tool_not_discovered",
            "discovery": {
                "ok": True,
                "tool_count": discovery.get("tool_count"),
                "tool_names": sorted(discovered_tool_names),
            },
            "mcp": {
                "server": parsed["server"],
                "name": parsed["name"],
                "namespace": parsed["namespace"],
                "policy_key": parsed["policy_key"],
                "permission": decision.get("permission"),
            },
        }

    call_result = await call_stdio_mcp_tool(
        config,
        tool_name=parsed["name"],
        arguments=arguments,
        client_version=PROXY_VERSION,
    )

    if not call_result.get("ok"):
        return {
            "ok": False,
            "tool": function_name,
            "error": "mcp_stdio_tool_call_failed",
            "call": call_result,
            "mcp": {
                "server": parsed["server"],
                "name": parsed["name"],
                "namespace": parsed["namespace"],
                "policy_key": parsed["policy_key"],
                "permission": decision.get("permission"),
            },
        }

    tool_result = call_result.get("result")
    if isinstance(tool_result, dict) and tool_result.get("isError") is True:
        return {
            "ok": False,
            "tool": function_name,
            "error": "mcp_tool_result_error",
            "result": tool_result,
            "mcp": {
                "server": parsed["server"],
                "name": parsed["name"],
                "namespace": parsed["namespace"],
                "policy_key": parsed["policy_key"],
                "permission": decision.get("permission"),
            },
            "discovery": {
                "ok": True,
                "tool_count": discovery.get("tool_count"),
            },
        }

    return {
        "ok": True,
        "tool": function_name,
        "mcp": {
            "server": parsed["server"],
            "name": parsed["name"],
            "namespace": parsed["namespace"],
            "policy_key": parsed["policy_key"],
            "permission": decision.get("permission"),
        },
        "result": tool_result,
        "discovery": {
            "ok": True,
            "tool_count": discovery.get("tool_count"),
        },
    }


async def _execute_mcp_proxy_tool_call(tool_call: dict[str, Any]) -> dict[str, Any]:
    function = tool_call.get("function") or {}
    name = str(function.get("name") or "")
    decision = _mcp_executor_policy_decision(name)

    if decision.get("ok") is not True:
        return _mcp_executor_denied_result(name)

    arguments = _decode_tool_arguments(function.get("arguments", ""))
    parsed = _parse_mcp_proxy_tool_name(name)
    if parsed is None:
        return _mcp_executor_denied_result(name)

    if _MCP_EXECUTOR_BACKEND is not None:
        try:
            result = await _MCP_EXECUTOR_BACKEND(
                server=parsed["server"],
                tool=parsed["name"],
                arguments=arguments,
                decision=decision,
            )
        except Exception as exc:
            return {
                "ok": False,
                "tool": name,
                "error": "mcp_executor_backend_failed",
                "message": str(exc),
                "mcp": {
                    "server": parsed["server"],
                    "name": parsed["name"],
                    "namespace": parsed["namespace"],
                    "policy_key": parsed["policy_key"],
                    "permission": decision.get("permission"),
                },
            }

        return {
            "ok": True,
            "tool": name,
            "mcp": {
                "server": parsed["server"],
                "name": parsed["name"],
                "namespace": parsed["namespace"],
                "policy_key": parsed["policy_key"],
                "permission": decision.get("permission"),
            },
            "result": result,
        }

    if _mcp_stdio_backend_enabled():
        return await _execute_mcp_stdio_backend(
            function_name=name,
            parsed=parsed,
            arguments=arguments,
            decision=decision,
        )

    return _mcp_executor_denied_result(name)


def _mcp_diagnostic_call_enabled() -> bool:
    return _env_bool("DEEPSEEK_PROXY_MCP_DIAGNOSTIC_CALL", False)


def _mcp_diagnostic_function_name(payload: dict[str, Any]) -> str:
    raw_function_name = str(payload.get("function_name") or "").strip()
    if raw_function_name:
        return raw_function_name

    server = str(payload.get("server") or "").strip()
    tool = str(payload.get("tool") or payload.get("name") or "").strip()
    if server and tool:
        return f"mcp__{server}__{tool}"

    return ""


async def _mcp_diagnostic_call(payload: dict[str, Any]) -> dict[str, Any]:
    function_name = _mcp_diagnostic_function_name(payload)
    parsed = _parse_mcp_proxy_tool_name(function_name)
    arguments = payload.get("arguments") if isinstance(payload.get("arguments"), dict) else {}

    base: dict[str, Any] = {
        "status": "ok",
        "version": PROXY_VERSION,
        "enabled": _mcp_diagnostic_call_enabled(),
        "production_execution": False,
        "tools_call_enabled": False,
        "backend": _mcp_executor_backend_type(),
        "tool": function_name,
    }

    if parsed is not None:
        base["mcp"] = {
            "server": parsed["server"],
            "name": parsed["name"],
            "namespace": parsed["namespace"],
            "policy_key": parsed["policy_key"],
        }

    if not _mcp_diagnostic_call_enabled():
        return {
            **base,
            "ok": False,
            "error": "mcp_diagnostic_call_disabled",
            "message": "Set DEEPSEEK_PROXY_MCP_DIAGNOSTIC_CALL=1 to enable this diagnostic endpoint.",
        }

    if parsed is None:
        return {
            **base,
            "ok": False,
            "error": "invalid_mcp_tool_name",
            "message": "Provide function_name=mcp__server__tool or server/tool fields.",
        }

    if not _mcp_executor_enabled():
        return {
            **base,
            "ok": False,
            "error": "mcp_executor_disabled",
            "message": "Set DEEPSEEK_PROXY_MCP_EXECUTOR=1 before using diagnostic MCP calls.",
        }

    if not _mcp_stdio_backend_enabled():
        return {
            **base,
            "ok": False,
            "error": "mcp_stdio_backend_disabled",
            "message": "Set DEEPSEEK_PROXY_MCP_EXECUTOR_BACKEND=stdio for diagnostic MCP calls.",
        }

    decision = _mcp_executor_policy_decision(function_name)
    if decision.get("ok") is not True:
        denied = _mcp_executor_denied_result(function_name)
        return {
            **base,
            **denied,
            "status": "ok",
            "version": PROXY_VERSION,
            "enabled": True,
            "production_execution": False,
            "tools_call_enabled": False,
            "backend": _mcp_executor_backend_type(),
        }

    result = await _execute_mcp_stdio_backend(
        function_name=function_name,
        parsed=parsed,
        arguments=arguments,
        decision=decision,
    )
    return {
        **base,
        **result,
        "status": "ok",
        "version": PROXY_VERSION,
        "enabled": True,
        "production_execution": False,
        "tools_call_enabled": True,
        "backend": _mcp_executor_backend_type(),
    }


def _normalize_mcp_nested_tool(
    namespace: str,
    nested_tool: dict[str, Any],
    mcp_tool_mapping: dict[str, dict[str, str]] | None = None,
) -> dict[str, Any] | None:
    name = str(nested_tool.get("name") or "").strip()
    if not name:
        return None

    forwarding_class = _mcp_tool_forwarding_class(name)
    if forwarding_class == "readonly":
        enabled = _env_bool("DEEPSEEK_PROXY_FORWARD_MCP_READONLY_TOOLS", True)
    elif forwarding_class == "write":
        enabled = _env_bool("DEEPSEEK_PROXY_FORWARD_MCP_WRITE_TOOLS", True)
    elif forwarding_class == "tutorial":
        enabled = _env_bool("DEEPSEEK_PROXY_FORWARD_MCP_TUTORIAL_TOOLS", True)
    else:
        enabled = False

    if not enabled:
        return None

    mapped_name = _mcp_tool_proxy_name(namespace, name)
    if mcp_tool_mapping is not None:
        mapping = {
            "namespace": namespace,
            "name": name,
        }
        if forwarding_class != "readonly":
            mapping["forwarding_class"] = forwarding_class
        mcp_tool_mapping[mapped_name] = mapping

    parameters = nested_tool.get("parameters") or {
        "type": "object",
        "properties": {},
    }

    if forwarding_class == "write":
        risk_note = (
            "Experimental write-capable MCP bridge. The proxy only restores the "
            "Responses function_call namespace and does not grant approval. Codex "
            "local MCP permissions, AGENTS.md, and approval policy still apply."
        )
    elif forwarding_class == "tutorial":
        risk_note = (
            "Experimental tutorial MCP bridge. The proxy only restores the Responses "
            "function_call namespace and does not grant approval. Codex local MCP "
            "permissions, AGENTS.md, and approval policy still apply."
        )
    else:
        risk_note = (
            "Experimental read-only MCP bridge. Call will be restored to Responses "
            f"function_call namespace={namespace} name={name}."
        )

    return {
        "type": "function",
        "function": {
            "name": mapped_name,
            "description": str(nested_tool.get("description") or "") + "\\n\\n" + risk_note,
            "parameters": parameters,
        },
    }


def _normalize_response_tool(
    tool: dict[str, Any],
    compat_warnings: list[dict[str, Any]] | None = None,
    mcp_tool_mapping: dict[str, dict[str, str]] | None = None,
) -> dict[str, Any] | list[dict[str, Any]] | None:
    """Convert a Responses tool into one or more DeepSeek ChatCompletions tools.

    Codex may include built-in Responses tools such as web_search.
    DeepSeek ChatCompletions cannot execute these built-in tools.
    Unsupported non-function tools are dropped but recorded for audit.
    """
    tool_type = tool.get("type")

    if tool_type == "web_search":
        if compat_warnings is not None:
            compat_warnings.append(
                {
                    "kind": "mapped_tool_type",
                    "tool_type": tool_type,
                    "mapped_to": "proxy_web_search",
                }
            )
        return _web_search_tool_schema()

    if tool_type == "image_generation":
        if compat_warnings is not None:
            compat_warnings.append(
                {
                    "kind": "mapped_tool_type",
                    "tool_type": tool_type,
                    "mapped_to": "proxy_image_generate",
                }
            )
        return _image_generation_tool_schema()

    if tool_type == "namespace":
        namespace = str(tool.get("namespace") or tool.get("name") or "").strip()
        namespace_tools = _namespace_tool_schemas(namespace)
        if namespace_tools is not None:
            if compat_warnings is not None:
                compat_warnings.append(
                    {
                        "kind": "mapped_tool_namespace",
                        "tool_type": tool_type,
                        "namespace": namespace,
                        "mapped_to": [
                            (item.get("function") or {}).get("name")
                            for item in namespace_tools
                        ],
                    }
                )
            return namespace_tools

        nested_tools = tool.get("tools") or []
        if namespace.startswith("mcp__"):
            if (
                _env_bool("DEEPSEEK_PROXY_FORWARD_MCP_READONLY_TOOLS", True)
                or _env_bool("DEEPSEEK_PROXY_FORWARD_MCP_WRITE_TOOLS", True)
                or _env_bool("DEEPSEEK_PROXY_FORWARD_MCP_TUTORIAL_TOOLS", True)
            ):
                mapped_tools = [
                    mapped
                    for nested_tool in nested_tools
                    if (mapped := _normalize_mcp_nested_tool(namespace, nested_tool, mcp_tool_mapping)) is not None
                ]

                if mapped_tools:
                    warning = {
                        "kind": "mapped_mcp_namespace",
                        "tool_type": tool_type,
                        "namespace": namespace,
                        "tool_count": len(nested_tools),
                        "mapped_to": [
                            (item.get("function") or {}).get("name")
                            for item in mapped_tools
                        ],
                        "reason": "experimental read-only MCP namespace mapping with namespace-aware output is enabled",
                    }
                    if compat_warnings is not None:
                        compat_warnings.append(warning)
                    print(f"[deepseek-responses-proxy] mapped MCP namespace tool: {namespace}")
                    return mapped_tools

            warning = {
                "kind": "ignored_mcp_namespace",
                "tool_type": tool_type,
                "namespace": namespace,
                "tool_count": len(nested_tools),
                "tool_names": [
                    str(item.get("name") or "")
                    for item in nested_tools
                    if item.get("name")
                ],
                "reason": "MCP tools are owned by Codex local MCP runtime and are not forwarded to DeepSeek",
            }
            if compat_warnings is not None:
                compat_warnings.append(warning)
            print(f"[deepseek-responses-proxy] ignored MCP namespace tool: {namespace}")
            return None

        warning = {
            "kind": "unsupported_tool_namespace",
            "tool_type": tool_type,
            "namespace": namespace,
            "tool": tool,
        }
        if compat_warnings is not None:
            compat_warnings.append(warning)
        print(f"[deepseek-responses-proxy] ignored unsupported namespace tool: {namespace}")
        return None

    if tool_type == "custom":
        name = str(tool.get("name") or "").strip()
        custom_format = tool.get("format") or {}

        if name == "apply_patch" and _env_bool("DEEPSEEK_PROXY_FORWARD_CUSTOM_APPLY_PATCH", True):
            warning = {
                "kind": "mapped_custom_tool",
                "tool_type": tool_type,
                "name": name,
                "mapped_to": "apply_patch",
                "description": str(tool.get("description") or ""),
                "format": {
                    "type": custom_format.get("type"),
                    "syntax": custom_format.get("syntax"),
                },
                "reason": "experimental custom apply_patch function-tool mapping is enabled",
            }
            if compat_warnings is not None:
                compat_warnings.append(warning)
            print("[deepseek-responses-proxy] mapped custom apply_patch tool experimentally")
            return {
                "type": "function",
                "function": {
                    "name": "apply_patch",
                    "description": (
                        str(tool.get("description") or "Apply a patch to local files.")
                        + "\n\nUse Codex apply_patch format exactly:\n"
                        + "*** Begin Patch\n"
                        + "*** Update File: relative/path\n"
                        + " context lines start with a single space\n"
                        + "+added lines start with plus\n"
                        + "-removed lines start with minus\n"
                        + "*** End Patch"
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "input": {
                                "type": "string",
                                "description": (
                                    "Patch text in Codex apply_patch format. "
                                    "It must start with '*** Begin Patch', use directives such as "
                                    "'*** Update File: relative/path', and end with '*** End Patch'. "
                                    "Inside update hunks, context lines start with a single space, "
                                    "added lines start with '+', and removed lines start with '-'."
                                ),
                            }
                        },
                        "required": ["input"],
                        "additionalProperties": False,
                    },
                },
            }

        warning = {
            "kind": "ignored_custom_tool",
            "tool_type": tool_type,
            "name": name,
            "description": str(tool.get("description") or ""),
            "format": {
                "type": custom_format.get("type"),
                "syntax": custom_format.get("syntax"),
            },
            "reason": "custom freeform tools are executed by Codex locally and are not forwarded to DeepSeek",
        }
        if compat_warnings is not None:
            compat_warnings.append(warning)
        print(f"[deepseek-responses-proxy] ignored custom tool: {name or 'unknown'}")
        return None

    if tool_type != "function":
        warning = {
            "kind": "unsupported_tool_type",
            "tool_type": tool_type,
            "tool": tool,
        }
        if compat_warnings is not None:
            compat_warnings.append(warning)
        print(f"[deepseek-responses-proxy] ignored unsupported tool type: {tool_type}")
        return None

    if "function" in tool:
        function = tool["function"]
        name = function.get("name")
        description = function.get("description", "")
        parameters = function.get("parameters", {"type": "object", "properties": {}})
    else:
        name = tool.get("name")
        description = tool.get("description", "")
        parameters = tool.get("parameters", {"type": "object", "properties": {}})

    if not name:
        warning = {
            "kind": "function_tool_missing_name",
            "tool_type": tool_type,
            "tool": tool,
        }
        if compat_warnings is not None:
            compat_warnings.append(warning)
        print("[deepseek-responses-proxy] ignored function tool with missing name")
        return None

    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": parameters,
        },
    }



def _message_from_response_content(role: str, content: Any) -> dict[str, Any]:
    message = {
        "role": role,
        "content": _plain_text_from_content(content),
    }

    if _thinking_enabled() and role == "assistant":
        message.setdefault("reasoning_content", "")

    return message


_TEXT_PART_TYPES = frozenset({"output_text", "input_text", "text"})


def _plain_text_from_content(content: Any) -> str:
    """Normalize Responses-style text content into plain text.

    Codex/Responses content may appear as:
    - a plain string
    - a JSON-encoded list of text parts
    - a list of {"type": "output_text"|"input_text"|"text", "text": "..."}
    - a single dict containing a text field

    Unknown structures degrade safely to JSON/string representations.
    """
    if content is None:
        return ""

    if isinstance(content, str):
        stripped = content.strip()
        if stripped.startswith("[") and any(part_type in stripped for part_type in _TEXT_PART_TYPES):
            try:
                parsed = json.loads(stripped)
            except (TypeError, json.JSONDecodeError):
                return content
            if isinstance(parsed, list):
                return _plain_text_from_content(parsed)
        return content

    if isinstance(content, list):
        chunks: list[str] = []
        for item in content:
            if isinstance(item, str):
                chunks.append(item)
                continue
            if not isinstance(item, dict):
                continue

            item_type = item.get("type")
            if item_type in _TEXT_PART_TYPES or "text" in item:
                value = item.get("text", "")
                if value is None:
                    continue
                if isinstance(value, str):
                    chunks.append(value)
                else:
                    chunks.append(json.dumps(value, ensure_ascii=False))
        return "".join(chunks)

    if isinstance(content, dict):
        item_type = content.get("type")
        if item_type in _TEXT_PART_TYPES or "text" in content:
            value = content.get("text", "")
            if value is None:
                return ""
            return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        return json.dumps(content, ensure_ascii=False)

    return str(content)

def _input_items_to_messages(input_value: Any) -> list[dict[str, Any]]:
    """Convert Responses input items to DeepSeek ChatCompletions messages.

    Codex may send both `function_call` and `function_call_output` items
    during tool continuation. Consecutive Responses `function_call` items can
    represent parallel tool calls from one assistant turn. ChatCompletions
    requires those parallel calls to be represented as one assistant message
    with multiple `tool_calls`, followed immediately by the matching tool
    outputs.
    """
    if input_value is None:
        return []
    if isinstance(input_value, str):
        return [{"role": "user", "content": input_value}]
    if not isinstance(input_value, list):
        raise HTTPException(status_code=400, detail="input must be a string or list")

    messages: list[dict[str, Any]] = []

    i = 0
    while i < len(input_value):
        item = input_value[i]
        item_type = item.get("type")

        if item_type == "message":
            role = item.get("role", "user")
            messages.append(_message_from_response_content(role, item.get("content", [])))
            i += 1
            continue

        if item_type in {"input_text", "output_text", "text"}:
            role = _normalize_chat_role(item.get("role", "user"))
            messages.append({"role": role, "content": item.get("text", "")})
            i += 1
            continue

        if item_type == "function_call":
            tool_calls: list[dict[str, Any]] = []
            content_parts: list[str] = []

            while i < len(input_value) and input_value[i].get("type") == "function_call":
                call_item = input_value[i]
                call_id = call_item.get("call_id") or call_item.get("id") or _item_id("call")
                name = call_item.get("name", "")
                arguments = call_item.get("arguments", "")

                if not name:
                    print("[deepseek-responses-proxy] ignored function_call input with missing name")
                    i += 1
                    continue

                content = _stringify_content(call_item.get("content") or "")
                if content:
                    content_parts.append(content)

                tool_calls.append(
                    {
                        "id": call_id,
                        "type": "function",
                        "function": {
                            "name": name,
                            "arguments": arguments,
                        },
                    }
                )
                i += 1

            if tool_calls:
                messages.append(
                    {
                        "role": "assistant",
                        "content": "\n".join(content_parts),
                        "tool_calls": tool_calls,
                    }
                )
            continue

        if item_type == "function_call_output":
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": item["call_id"],
                    "content": _stringify_content(item.get("output", "")),
                }
            )
            i += 1
            continue

        if item_type in {"reasoning", "summary_text"}:
            print(f"[deepseek-responses-proxy] ignored unsupported input item type: {item_type}")
            i += 1
            continue

        raise HTTPException(status_code=400, detail=f"Unsupported input item type: {item_type}")

    return messages

def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError:
        print(f"[deepseek-responses-proxy] invalid {name}={raw!r}; using {default}")
        return default
    if value < 0:
        print(f"[deepseek-responses-proxy] negative {name}={raw!r}; using {default}")
        return default
    return value


def _image_generation_tool_schema() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "proxy_image_generate",
            "description": "Generate an image using the configured DeepSeek proxy image provider.",
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string"},
                    "size": {"type": "string"},
                    "n": {"type": "integer"},
                    "quality": {"type": "string"},
                    "style": {"type": "string"},
                },
                "required": ["prompt"],
                "additionalProperties": False,
            },
        },
    }


def _image_provider() -> str:
    provider = (
        os.environ.get("DEEPSEEK_PROXY_IMAGE_PROVIDER")
        or os.environ.get("IMAGE_PROVIDER")
        or "mock"
    )
    return provider.strip().lower() or "mock"


def _image_api_key() -> str:
    return (
        os.environ.get("DEEPSEEK_PROXY_IMAGE_API_KEY")
        or os.environ.get("ZAI_API_KEY")
        or os.environ.get("ZHIPUAI_API_KEY")
        or os.environ.get("ZHIPU_API_KEY")
        or os.environ.get("GLM_API_KEY")
        or ""
    )


def _image_model() -> str:
    return (
        os.environ.get("DEEPSEEK_PROXY_IMAGE_MODEL")
        or os.environ.get("ZAI_IMAGE_MODEL")
        or "cogView-4-250304"
    )


def _image_size(value: Any = None) -> str:
    raw = str(value or os.environ.get("DEEPSEEK_PROXY_IMAGE_SIZE", "1024x1024")).strip()
    if not raw:
        return "1024x1024"
    return raw.replace("*", "x")


def _image_n(value: Any = None) -> int:
    if value is None:
        value = os.environ.get("DEEPSEEK_PROXY_IMAGE_N", "1")
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = 1
    return max(1, min(parsed, 4))


def _image_output_dir() -> Path:
    raw = os.environ.get("DEEPSEEK_PROXY_IMAGE_OUTPUT_DIR") or ".generated/images"
    return Path(raw)


def _image_download_enabled() -> bool:
    return _env_bool("DEEPSEEK_PROXY_IMAGE_DOWNLOAD", False)


def _image_max_artifacts() -> int:
    return _env_int("DEEPSEEK_PROXY_IMAGE_MAX_ARTIFACTS", 100)


def _image_artifact_patterns() -> list[str]:
    return [
        "mock_*.png",
        "glm_*.png",
        "zai_*.png",
        "zhipu_*.png",
        "zhipuai_*.png",
        "bigmodel_*.png",
    ]


def _prune_image_artifacts(output_dir: Path | None = None) -> None:
    limit = _image_max_artifacts()
    if limit <= 0:
        return

    root = output_dir or _image_output_dir()
    if not root.exists() or not root.is_dir():
        return

    candidates: list[Path] = []
    seen: set[Path] = set()

    for pattern in _image_artifact_patterns():
        for path in root.glob(pattern):
            try:
                resolved = path.resolve()
            except Exception:
                resolved = path
            if resolved in seen or not path.is_file():
                continue
            seen.add(resolved)
            candidates.append(path)

    if len(candidates) <= limit:
        return

    def sort_key(path: Path) -> tuple[float, str]:
        try:
            mtime = path.stat().st_mtime
        except OSError:
            mtime = 0.0
        return (mtime, path.name)

    candidates.sort(key=sort_key, reverse=True)

    for path in candidates[limit:]:
        try:
            path.unlink()
        except OSError as exc:
            print(f"[deepseek-responses-proxy] failed to prune generated image artifact {path}: {exc}")


def _image_file_uri(file_path: str | None) -> str | None:
    if not file_path:
        return None
    try:
        return Path(file_path).resolve().as_uri()
    except Exception:
        return None


def _image_artifact_fields(file_path: str | None) -> dict[str, Any]:
    return {
        "file_path": file_path,
        "local_path": file_path,
        "file_uri": _image_file_uri(file_path),
        "downloaded": bool(file_path),
    }


def _write_mock_image_artifact(*, provider: str) -> str | None:
    output_dir = _image_output_dir()
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{provider}_{_now()}_{uuid.uuid4().hex[:8]}.png"
    path = output_dir / filename

    # 1x1 transparent PNG. This avoids external network access in tests while
    # still exercising the same local-artifact output path as real downloads.
    png_bytes = bytes.fromhex(
        "89504e470d0a1a0a"
        "0000000d49484452000000010000000108060000001f15c489"
        "0000000a49444154789c63600000020001e221bc3300000000"
        "49454e44ae426082"
    )

    try:
        path.write_bytes(png_bytes)
    except Exception as exc:
        print(f"[deepseek-responses-proxy] failed to write mock generated image: {exc}")
        return None

    _prune_image_artifacts(output_dir)
    return str(path.resolve())


async def _download_image_url(url: str, *, provider: str) -> str | None:
    if not url:
        return None

    output_dir = _image_output_dir()
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{provider}_{_now()}_{uuid.uuid4().hex[:8]}.png"
    path = output_dir / filename

    try:
        async with httpx.AsyncClient(timeout=_env_float("DEEPSEEK_PROXY_IMAGE_DOWNLOAD_TIMEOUT_SECONDS", 60.0)) as client:
            response = await client.get(url)
            response.raise_for_status()
            path.write_bytes(response.content)
    except Exception as exc:
        print(f"[deepseek-responses-proxy] failed to download generated image: {exc}")
        return None

    _prune_image_artifacts(output_dir)
    return str(path.resolve())


async def _mock_image_generate(arguments: dict[str, Any]) -> dict[str, Any]:
    prompt = str(arguments.get("prompt") or "").strip()
    size = _image_size(arguments.get("size"))
    n = _image_n(arguments.get("n"))

    images: list[dict[str, Any]] = []
    for _ in range(n):
        file_path = None
        if _image_download_enabled():
            file_path = _write_mock_image_artifact(provider="mock")
        images.append(
            {
                "url": "https://example.com/mock-generated-image.png",
                **_image_artifact_fields(file_path),
                "mime_type": "image/png",
            }
        )

    return {
        "ok": True,
        "provider": "mock",
        "model": "mock-image",
        "prompt": prompt,
        "size": size,
        "images": images,
    }


async def _zai_image_generate(arguments: dict[str, Any]) -> dict[str, Any]:
    api_key = _image_api_key()
    provider = _image_provider()
    prompt = str(arguments.get("prompt") or "").strip()
    size = _image_size(arguments.get("size"))
    n = _image_n(arguments.get("n"))

    if not api_key:
        return {
            "ok": False,
            "provider": provider,
            "model": _image_model(),
            "prompt": prompt,
            "error": "missing_api_key",
            "message": "Set DEEPSEEK_PROXY_IMAGE_API_KEY, ZAI_API_KEY, ZHIPUAI_API_KEY, ZHIPU_API_KEY, or GLM_API_KEY.",
            "images": [],
        }

    body: dict[str, Any] = {
        "model": _image_model(),
        "prompt": prompt,
        "size": size,
    }
    if n != 1:
        body["n"] = n

    endpoint = os.environ.get(
        "DEEPSEEK_PROXY_IMAGE_BASE_URL",
        "https://api.z.ai/api/paas/v4/images/generations",
    )

    try:
        async with httpx.AsyncClient(timeout=_env_float("DEEPSEEK_PROXY_IMAGE_TIMEOUT_SECONDS", 120.0)) as client:
            response = await client.post(
                endpoint,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
            response.raise_for_status()
            data = response.json()
    except Exception as exc:
        return {
            "ok": False,
            "provider": provider,
            "model": _image_model(),
            "prompt": prompt,
            "error": "image_generation_failed",
            "message": str(exc),
            "images": [],
        }

    raw_images = data.get("data") or []
    images: list[dict[str, Any]] = []
    for item in raw_images:
        if not isinstance(item, dict):
            continue
        url = item.get("url") or item.get("b64_json") or ""
        file_path = None
        if url and url.startswith("http") and _image_download_enabled():
            file_path = await _download_image_url(url, provider=provider)
        images.append(
            {
                "url": url if url.startswith("http") else None,
                **_image_artifact_fields(file_path),
                "mime_type": "image/png",
                "raw": item,
            }
        )

    return {
        "ok": True,
        "provider": provider,
        "model": _image_model(),
        "prompt": prompt,
        "size": size,
        "images": images,
    }


async def _proxy_image_generate(arguments: dict[str, Any]) -> dict[str, Any]:
    prompt = str(arguments.get("prompt") or "").strip()
    if not prompt:
        return {
            "ok": False,
            "provider": _image_provider(),
            "model": _image_model(),
            "prompt": prompt,
            "error": "missing_prompt",
            "message": "proxy_image_generate requires a non-empty prompt.",
            "images": [],
        }

    provider = _image_provider()

    if provider in {"disabled", "off", "none"}:
        return {
            "ok": False,
            "provider": provider,
            "model": _image_model(),
            "prompt": prompt,
            "error": "image_generation_disabled",
            "message": "Image generation provider is disabled.",
            "images": [],
        }

    if provider == "mock":
        return await _mock_image_generate(arguments)

    if provider in {"glm", "zai", "zhipu", "zhipuai", "bigmodel"}:
        return await _zai_image_generate(arguments)

    return {
        "ok": False,
        "provider": provider,
        "model": _image_model(),
        "prompt": prompt,
        "error": "unsupported_image_provider",
        "message": "Supported providers: mock, glm, zai, zhipu, zhipuai, bigmodel, disabled.",
        "images": [],
    }


def _web_search_tool_schema() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "proxy_web_search",
            "description": "Search the web using the configured DeepSeek proxy search provider.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "max_results": {"type": "integer"},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    }


def _web_search_provider() -> str:
    provider = (
        os.environ.get("DEEPSEEK_PROXY_WEB_SEARCH_PROVIDER")
        or os.environ.get("SEARCH_PROVIDER")
        or "mock"
    )
    return provider.strip().lower() or "mock"


def _web_search_max_results(value: Any = None) -> int:
    if value is None:
        value = os.environ.get("DEEPSEEK_PROXY_WEB_SEARCH_MAX_RESULTS", "5")
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = 5
    return max(1, min(parsed, 10))


def _web_search_timeout_seconds() -> float:
    return _env_float("DEEPSEEK_PROXY_WEB_SEARCH_TIMEOUT_SECONDS", 20.0)


def _serpapi_api_key() -> str:
    return (
        os.environ.get("DEEPSEEK_PROXY_SERPAPI_API_KEY")
        or os.environ.get("SERPAPI_API_KEY")
        or ""
    )


def _normalize_search_result(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": item.get("title") or "",
        "url": item.get("link") or item.get("url") or "",
        "snippet": item.get("snippet") or item.get("description") or "",
        "published_at": item.get("date"),
    }


async def _mock_web_search(query: str, max_results: int) -> dict[str, Any]:
    return {
        "ok": True,
        "provider": "mock",
        "query": query,
        "results": [
            {
                "title": f"Mock search result for {query}",
                "url": "https://example.com/mock-search-result",
                "snippet": "This is a deterministic mock web search result from the DeepSeek proxy.",
                "published_at": None,
            }
        ][:max_results],
    }


async def _serpapi_web_search(query: str, max_results: int) -> dict[str, Any]:
    api_key = _serpapi_api_key()
    if not api_key:
        return {
            "ok": False,
            "provider": "serpapi",
            "query": query,
            "error": "missing_api_key",
            "message": "SERPAPI_API_KEY or DEEPSEEK_PROXY_SERPAPI_API_KEY is required.",
            "results": [],
        }

    params: dict[str, Any] = {
        "engine": os.environ.get("DEEPSEEK_PROXY_WEB_SEARCH_ENGINE", "google"),
        "q": query,
        "api_key": api_key,
        "num": max_results,
    }

    for env_name, param_name in [
        ("DEEPSEEK_PROXY_WEB_SEARCH_GL", "gl"),
        ("DEEPSEEK_PROXY_WEB_SEARCH_HL", "hl"),
        ("DEEPSEEK_PROXY_WEB_SEARCH_LOCATION", "location"),
    ]:
        value = os.environ.get(env_name)
        if value:
            params[param_name] = value

    try:
        async with httpx.AsyncClient(timeout=_web_search_timeout_seconds()) as client:
            response = await client.get("https://serpapi.com/search.json", params=params)
            response.raise_for_status()
            data = response.json()
    except Exception as exc:
        return {
            "ok": False,
            "provider": "serpapi",
            "query": query,
            "error": "web_search_failed",
            "message": str(exc),
            "results": [],
        }

    organic_results = data.get("organic_results") or []
    results = [
        _normalize_search_result(item)
        for item in organic_results[:max_results]
        if isinstance(item, dict)
    ]

    return {
        "ok": True,
        "provider": "serpapi",
        "query": query,
        "results": results,
    }


async def _proxy_web_search(arguments: dict[str, Any]) -> dict[str, Any]:
    query = str(arguments.get("query") or "").strip()
    max_results = _web_search_max_results(arguments.get("max_results"))

    if not query:
        return {
            "ok": False,
            "provider": _web_search_provider(),
            "query": query,
            "error": "missing_query",
            "message": "proxy_web_search requires a non-empty query.",
            "results": [],
        }

    provider = _web_search_provider()

    if provider in {"disabled", "off", "none"}:
        return {
            "ok": False,
            "provider": provider,
            "query": query,
            "error": "web_search_disabled",
            "message": "Web search provider is disabled.",
            "results": [],
        }

    if provider == "mock":
        return await _mock_web_search(query, max_results)

    if provider == "serpapi":
        return await _serpapi_web_search(query, max_results)

    return {
        "ok": False,
        "provider": provider,
        "query": query,
        "error": "unsupported_web_search_provider",
        "message": "Supported providers: mock, serpapi, disabled.",
        "results": [],
    }


def _proxy_function_tool_schema(
    name: str,
    description: str,
    properties: dict[str, Any] | None = None,
    required: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties or {},
                "required": required or [],
                "additionalProperties": False,
            },
        },
    }


def _deepseek_proxy_account_tool_schemas() -> list[dict[str, Any]]:
    usage_filter_properties = {
        "since": {"type": "integer"},
        "until": {"type": "integer"},
        "thinking": {"type": "boolean"},
        "model": {"type": "string"},
    }
    usage_events_properties = {
        **usage_filter_properties,
        "limit": {"type": "integer", "minimum": 1, "maximum": 1000},
    }

    return [
        _proxy_function_tool_schema(
            "proxy_status",
            "Return DeepSeek proxy runtime status without exposing secrets.",
        ),
        _proxy_function_tool_schema(
            "proxy_usage_summary",
            "Return DeepSeek proxy usage summary with optional filters.",
            usage_filter_properties,
        ),
        _proxy_function_tool_schema(
            "proxy_usage_events",
            "Return recent DeepSeek proxy usage ledger events with optional filters.",
            usage_events_properties,
        ),
        _proxy_function_tool_schema(
            "proxy_balance",
            "Return DeepSeek account balance through the configured upstream client.",
        ),
    ]


def _namespace_tool_schemas(namespace: str) -> list[dict[str, Any]] | None:
    if namespace == "deepseek_proxy_account":
        return _deepseek_proxy_account_tool_schemas()
    return None


def _proxy_tool_schemas() -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": "proxy_echo",
                "description": "Echo a value for DeepSeek proxy tool-loop testing.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "value": {"type": "string"},
                    },
                    "required": ["value"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "proxy_time",
                "description": "Return the current Unix timestamp from the proxy.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
            },
        },
    ]


def _decode_tool_arguments(raw_arguments: Any) -> dict[str, Any]:
    if raw_arguments is None or raw_arguments == "":
        return {}
    if isinstance(raw_arguments, dict):
        return raw_arguments
    if not isinstance(raw_arguments, str):
        return {"_raw": raw_arguments}

    try:
        value = json.loads(raw_arguments)
    except json.JSONDecodeError:
        return {"_raw": raw_arguments, "_parse_error": "invalid_json"}

    if isinstance(value, dict):
        return value
    return {"_raw": value}


def _coerce_optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _coerce_optional_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return None


def _proxy_usage_filters(arguments: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    since = _coerce_optional_int(arguments.get("since"))
    until = _coerce_optional_int(arguments.get("until"))
    thinking = _coerce_optional_bool(arguments.get("thinking"))

    model_value = arguments.get("model")
    model = model_value.strip() if isinstance(model_value, str) and model_value.strip() else None

    filters = {
        "since": since,
        "until": until,
        "thinking": thinking,
        "model": model,
    }

    if since is not None and until is not None and until < since:
        return filters, "until must be greater than or equal to since"

    return filters, None


async def _execute_proxy_tool_call(
    tool_call: dict[str, Any],
    *,
    deepseek_client: DeepSeekClient | None = None,
    store: Any | None = None,
) -> dict[str, Any]:
    function = tool_call.get("function") or {}
    name = str(function.get("name") or "")
    arguments = _decode_tool_arguments(function.get("arguments", ""))

    if _parse_mcp_proxy_tool_name(name) is not None:
        return await _execute_mcp_proxy_tool_call(tool_call)

    if name == "proxy_status":
        return {
            "ok": True,
            "tool": name,
            "status": "ok",
            "version": PROXY_VERSION,
            "model_default": DEFAULT_MODEL,
            "thinking": _deepseek_thinking_config(),
            "thinking_enabled": _thinking_enabled(),
            "tool_bridge": _tool_bridge_status(),
            "store": _store_info(store) if store is not None else None,
            "deepseek_base_url": getattr(deepseek_client, "base_url", None) if deepseek_client is not None else None,
        }

    if name == "proxy_usage_summary":
        filters, error = _proxy_usage_filters(arguments)
        if error is not None:
            return {
                "ok": False,
                "tool": name,
                "error": "invalid_usage_filters",
                "message": error,
                "filters": filters,
            }
        if store is None or not hasattr(store, "usage_summary"):
            return {
                "ok": True,
                "tool": name,
                "summary": {
                    "request_count": 0,
                    "estimated_cost_usd": 0.0,
                },
                "filters": filters,
                "note": "current store does not support usage ledger",
            }
        return {
            "ok": True,
            "tool": name,
            "summary": store.usage_summary(
                since=filters["since"],
                until=filters["until"],
                thinking=filters["thinking"],
                model=filters["model"],
            ),
            "filters": filters,
            "pricing_usd_per_1m": _load_model_pricing_usd_per_1m(),
        }

    if name == "proxy_usage_events":
        filters, error = _proxy_usage_filters(arguments)
        if error is not None:
            return {
                "ok": False,
                "tool": name,
                "error": "invalid_usage_filters",
                "message": error,
                "filters": filters,
            }
        if store is None or not hasattr(store, "usage_events"):
            return {
                "ok": True,
                "tool": name,
                "usage_events": [],
                "filters": filters,
                "note": "current store does not support usage ledger",
            }
        raw_limit = _coerce_optional_int(arguments.get("limit"))
        safe_limit = max(1, min(raw_limit if raw_limit is not None else 100, 1000))
        return {
            "ok": True,
            "tool": name,
            "filters": filters,
            "usage_events": store.usage_events(
                limit=safe_limit,
                since=filters["since"],
                until=filters["until"],
                thinking=filters["thinking"],
                model=filters["model"],
            ),
        }

    if name == "proxy_balance":
        if deepseek_client is None or not hasattr(deepseek_client, "user_balance"):
            return {
                "ok": False,
                "tool": name,
                "error": "balance_client_unavailable",
            }
        try:
            balance = await deepseek_client.user_balance()
        except Exception as exc:
            return {
                "ok": False,
                "tool": name,
                "error": "balance_request_failed",
                "message": str(exc),
            }
        return {
            "ok": True,
            "tool": name,
            "upstream": "deepseek",
            "balance": balance,
        }

    if name == "proxy_echo":
        return {
            "ok": True,
            "tool": name,
            "value": arguments.get("value", ""),
        }

    if name == "proxy_time":
        return {
            "ok": True,
            "tool": name,
            "unix_time": _now(),
        }

    if name == "proxy_web_search":
        return await _proxy_web_search(arguments)

    if name == "proxy_image_generate":
        return await _proxy_image_generate(arguments)

    return {
        "ok": False,
        "tool": name,
        "error": "unsupported_proxy_tool",
    }


def _is_mcp_executor_tool_call(tool_call: dict[str, Any]) -> bool:
    function = tool_call.get("function") or {}
    return _parse_mcp_proxy_tool_name(function.get("name")) is not None


def _is_proxy_tool_call(tool_call: dict[str, Any]) -> bool:
    function = tool_call.get("function") or {}
    function_name = str(function.get("name") or "")
    return function_name.startswith("proxy_") or _is_mcp_executor_tool_call(tool_call)


def _tool_result_message(tool_call: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    return {
        "role": "tool",
        "tool_call_id": tool_call.get("id", _item_id("call")),
        "content": json.dumps(result, ensure_ascii=False),
    }


_CODEX_TOOL_PROTOCOL_MARKER = "[deepseek-proxy codex tool protocol]"


def _codex_tool_protocol_env_config() -> dict[str, Any]:
    return {
        "enabled": _env_bool("DEEPSEEK_PROXY_CODEX_TOOL_PROTOCOL_INSTRUCTION", True),
        "role": os.environ.get("DEEPSEEK_PROXY_CODEX_TOOL_PROTOCOL_ROLE", "system").strip() or "system",
    }


def _codex_tool_protocol_instruction_message() -> dict[str, str]:
    config = _codex_tool_protocol_env_config()
    role = str(config.get("role") or "system")
    if role not in {"system", "user"}:
        role = "system"

    return {
        "role": role,
        "content": (
            f"{_CODEX_TOOL_PROTOCOL_MARKER}\n"
            "You are operating inside a Codex-style agent loop. The harness "
            "continues only when you emit structured tool calls. If the next step "
            "requires inspecting files, running commands, using ADB, controlling a "
            "device, taking screenshots, reading UI state, searching, or otherwise "
            "acting on the environment, emit a tool_call in the same response. Do "
            "not narrate future tool use without emitting a tool_call. Return a "
            "plain assistant answer only when no further tool use is needed and "
            "control should return to the user."
        ),
    }


def _messages_with_codex_tool_protocol_instruction(
    messages: list[dict[str, Any]],
    *,
    tools_available: bool,
) -> list[dict[str, Any]]:
    config = _codex_tool_protocol_env_config()
    if not config.get("enabled") or not tools_available:
        return messages

    for message in messages:
        if not isinstance(message, dict):
            continue
        content = _plain_text_from_content(message.get("content", ""))
        if _CODEX_TOOL_PROTOCOL_MARKER in content:
            return messages

    injected = deepcopy(messages)
    insert_at = 0
    while insert_at < len(injected):
        message = injected[insert_at]
        if isinstance(message, dict) and message.get("role") == "system":
            insert_at += 1
            continue
        break

    injected.insert(insert_at, _codex_tool_protocol_instruction_message())
    return injected


def _agent_liveness_env_config() -> dict[str, Any]:
    return {
        "enabled": _env_bool("DEEPSEEK_PROXY_AGENT_LIVENESS_GUARD", True),
        "max_retries": _env_int("DEEPSEEK_PROXY_AGENT_LIVENESS_MAX_RETRIES", 1),
        "content_preview_chars": _env_int("DEEPSEEK_PROXY_AGENT_LIVENESS_PREVIEW_CHARS", 600),
    }


def _assistant_message_needs_liveness_guard(
    assistant_message: dict[str, Any],
    *,
    tools_available: bool,
) -> bool:
    if not tools_available:
        return False
    if assistant_message.get("tool_calls"):
        return False

    content = _plain_text_from_content(assistant_message.get("content", ""))
    stripped = content.strip()
    if len(stripped) < 8:
        return False

    lowered = stripped.lower()

    intent_markers = [
        "now let me",
        "let me ",
        "i'll ",
        "i will ",
        "i’ll ",
        "i am going to",
        "i'm going to",
        "next, i'll",
        "next i will",
        "next, i will",
        "i'll now",
        "i will now",
        "let's ",
        "switch to",
        "try ",
        "use ",
        "fallback to",
        "i'll switch",
        "i will switch",
        "接下来",
        "我来",
        "让我",
        "我将",
        "我会",
        "换用",
        "改用",
        "尝试",
        "先",
        "再",
        "然后",
        "继续",
        "直接",
    ]
    action_markers = [
        "run",
        "check",
        "inspect",
        "dump",
        "execute",
        "test",
        "try",
        "wake",
        "open",
        "read",
        "look",
        "verify",
        "use",
        "call",
        "query",
        "list",
        "grep",
        "search",
        "screenshot",
        "screencap",
        "screen",
        "capture",
        "tap",
        "click",
        "ui",
        "adb",
        "uiautomator",
        "运行",
        "检查",
        "执行",
        "测试",
        "读取",
        "查看",
        "调用",
        "截图",
        "截屏",
        "唤醒",
        "点击",
        " dump",
        "状态",
        "看看",
    ]

    has_intent = any(marker in lowered for marker in intent_markers)
    has_action = any(marker in lowered for marker in action_markers)
    ends_like_continuation = stripped.endswith(":") or stripped.endswith("：") or stripped.endswith("—")

    # Codex-like liveness: the harness only continues on real tool calls.
    # Treat action verbs followed by a continuation marker as unfinished tool
    # intent even when the model did not use explicit "let me" wording.
    return (has_intent and (has_action or ends_like_continuation)) or (
        has_action and ends_like_continuation
    )


def _assistant_message_is_obvious_final_answer(assistant_message: dict[str, Any]) -> bool:
    content = _plain_text_from_content(assistant_message.get("content", "")).strip()
    if not content:
        return False

    lowered = content.lower()
    normalized = " ".join(lowered.replace("。", ".").replace("！", "!").replace("？", "?").split())

    final_markers = [
        "done",
        "complete",
        "completed",
        "finished",
        "all requested checks are complete",
        "task complete",
        "echo complete",
        "status consumed",
        "consumed",
        "no further action",
        "nothing else is needed",
        "i can't continue",
        "i cannot continue",
        "需要你确认",
        "请确认",
        "已完成",
        "完成了",
        "已经完成",
        "检查完成",
        "测试通过",
        "任务完成",
        "无法继续",
        "需要确认",
    ]

    if any(marker in normalized for marker in final_markers):
        return True

    # Short final acknowledgements should not trigger an expensive judge call.
    if len(content) <= 120 and any(
        token in normalized
        for token in [
            "ok.",
            "okay.",
            "done.",
            "complete.",
            "completed.",
            "已完成",
            "完成",
        ]
    ):
        return True

    return False


def _agent_liveness_guard_prompt(
    assistant_message: dict[str, Any],
    *,
    retry_index: int,
    max_retries: int,
    preview_chars: int,
) -> dict[str, str]:
    content = _plain_text_from_content(assistant_message.get("content", ""))
    preview, _changed = _truncate_middle_text(content.strip(), preview_chars)

    return {
        "role": "user",
        "content": (
            "Codex agent-loop protocol correction.\n\n"
            "You are inside a Codex-style agent loop. The harness only executes "
            "structured tool calls. It does not execute narrated future actions.\n\n"
            "Your previous assistant message narrated a concrete next action, but "
            "did not emit a tool_call, so the loop would stop incorrectly.\n\n"
            f"Previous assistant text:\n{preview}\n\n"
            "You must choose exactly one of the following in this response:\n"
            "A. Emit the next concrete tool_call now.\n"
            "B. If no tool is needed, provide the final answer to the user.\n\n"
            "Do not say 'I will', 'let me', 'next I will', '换用', '我来', "
            "'接下来', or any similar future-action text unless this same response "
            "also contains a tool_call.\n\n"
            f"retry_index={retry_index}; max_retries={max_retries}"
        ),
    }


def _agent_liveness_judge_env_config() -> dict[str, Any]:
    raw_model = os.environ.get(
        "DEEPSEEK_PROXY_AGENT_LIVENESS_JUDGE_MODEL",
        "v4-flash-no-thinking",
    ).strip() or "v4-flash-no-thinking"

    return {
        "enabled": _env_bool("DEEPSEEK_PROXY_AGENT_LIVENESS_JUDGE_ENABLED", True),
        "model": raw_model,
        "upstream_model": _normalize_agent_liveness_judge_model(raw_model),
        "thinking": {"type": "disabled"},
        "max_recent_messages": _env_int("DEEPSEEK_PROXY_AGENT_LIVENESS_JUDGE_RECENT_MESSAGES", 4),
        "content_preview_chars": _env_int("DEEPSEEK_PROXY_AGENT_LIVENESS_JUDGE_PREVIEW_CHARS", 1200),
        "trigger_on_ambiguous": _env_bool(
            "DEEPSEEK_PROXY_AGENT_LIVENESS_JUDGE_TRIGGER_ON_AMBIGUOUS",
            False,
        ),
    }


def _normalize_agent_liveness_judge_model(model: str) -> str:
    value = (model or "").strip().lower()
    aliases = {
        "v4-flash-no-thinking": "deepseek-v4-flash",
        "deepseek-v4-flash-no-thinking": "deepseek-v4-flash",
        "v4-flash": "deepseek-v4-flash",
        "flash": "deepseek-v4-flash",
        "v4-pro": "deepseek-v4-pro",
        "pro": "deepseek-v4-pro",
    }
    if value in aliases:
        return aliases[value]
    if value in {"deepseek-v4-flash", "deepseek-v4-pro"}:
        return value
    return "deepseek-v4-flash"


def _recent_messages_for_liveness_judge(
    messages: list[dict[str, Any]],
    *,
    max_recent_messages: int,
    content_preview_chars: int,
) -> list[dict[str, str]]:
    recent: list[dict[str, str]] = []
    for message in reversed(messages):
        if not isinstance(message, dict):
            continue
        role = str(message.get("role") or "unknown")
        if role not in {"user", "assistant", "tool", "system"}:
            continue
        content = _plain_text_from_content(message.get("content", ""))
        if not content:
            continue
        content, _changed = _truncate_middle_text(content, content_preview_chars)
        item: dict[str, str] = {
            "role": role,
            "content": content,
        }
        if message.get("tool_call_id"):
            item["tool_call_id"] = str(message.get("tool_call_id"))
        recent.append(item)
        if len(recent) >= max_recent_messages:
            break
    recent.reverse()
    return recent


def _parse_agent_liveness_judge_json(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    if not raw:
        return {
            "decision": "ambiguous",
            "confidence": 0.0,
            "reason": "empty_judge_response",
            "candidate_trigger_phrases": [],
        }

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            try:
                parsed = json.loads(raw[start : end + 1])
            except json.JSONDecodeError:
                parsed = {}
        else:
            parsed = {}

    if not isinstance(parsed, dict):
        parsed = {}

    decision = str(parsed.get("decision") or "ambiguous").strip().lower()
    if decision not in {"needs_tool_call", "final_answer", "ambiguous"}:
        decision = "ambiguous"

    confidence = parsed.get("confidence", 0.0)
    try:
        confidence = float(confidence)
    except Exception:
        confidence = 0.0

    phrases = parsed.get("candidate_trigger_phrases") or []
    if not isinstance(phrases, list):
        phrases = []
    phrases = [str(item)[:200] for item in phrases if str(item).strip()][:12]

    return {
        "decision": decision,
        "confidence": max(0.0, min(1.0, confidence)),
        "reason": str(parsed.get("reason") or "")[:1200],
        "candidate_trigger_phrases": phrases,
    }


async def _judge_agent_liveness_with_llm(
    *,
    deepseek_client: "DeepSeekClient",
    assistant_message: dict[str, Any],
    messages_for_deepseek: list[dict[str, Any]],
    tools_available: bool,
    store: Any | None = None,
    response_id: str | None = None,
    previous_response_id: str | None = None,
    requested_model: str | None = None,
    usage_call_counter: dict[str, int] | None = None,
) -> dict[str, Any]:
    config = _agent_liveness_judge_env_config()
    report: dict[str, Any] = {
        "enabled": bool(config["enabled"]),
        "model": config["model"],
        "upstream_model": config["upstream_model"],
        "thinking": config["thinking"],
        "tools_available": tools_available,
        "decision": "not_run",
        "confidence": 0.0,
        "reason": "",
        "candidate_trigger_phrases": [],
    }

    if not config["enabled"]:
        report["decision"] = "disabled"
        return report
    if not tools_available:
        report["decision"] = "no_tools_available"
        return report

    assistant_text = _plain_text_from_content(assistant_message.get("content", "")).strip()
    assistant_preview, _changed = _truncate_middle_text(
        assistant_text,
        int(config["content_preview_chars"]),
    )
    recent_messages = _recent_messages_for_liveness_judge(
        messages_for_deepseek,
        max_recent_messages=int(config["max_recent_messages"]),
        content_preview_chars=int(config["content_preview_chars"]),
    )

    system_prompt = (
        "You are a liveness judge for a Codex-style agent loop. Your only job is "
        "to classify whether the latest assistant message is a final answer or an "
        "unfinished environment-action intent that should have been a tool call. "
        "Do not solve the task. Do not propose commands. Return strict JSON only."
    )

    user_prompt = (
        "Classify the latest assistant message.\n\n"
        "Labels:\n"
        "- needs_tool_call: assistant describes, promises, or transitions to an "
        "environment action such as running commands, checking UI, using ADB, "
        "opening apps, tapping, reading files, taking screenshots, dumping state, "
        "using URL schemes/intents, or verifying device state, but no tool_call was emitted.\n"
        "- final_answer: assistant is done, summarizes results, asks user for "
        "clarification, or explicitly cannot continue.\n"
        "- ambiguous: unclear.\n\n"
        "Return JSON exactly like:\n"
        "{\"decision\":\"needs_tool_call|final_answer|ambiguous\","
        "\"confidence\":0.0,"
        "\"reason\":\"short reason\","
        "\"candidate_trigger_phrases\":[\"phrase\"]}\n\n"
        f"tools_available: {tools_available}\n"
        f"recent_messages: {json.dumps(recent_messages, ensure_ascii=False)}\n"
        f"latest_assistant_message: {assistant_preview}"
    )

    judge_payload = {
        "model": config["upstream_model"],
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0,
        "stream": False,
        "thinking": config["thinking"],
    }

    try:
        judge_response = await _chat_completions_with_usage(
            deepseek_client=deepseek_client,
            store=store,
            payload=judge_payload,
            purpose="liveness_judge",
            response_id=response_id,
            previous_response_id=previous_response_id,
            request_id=response_id,
            requested_model=requested_model,
            thinking_enabled=False,
            call_counter=usage_call_counter,
        )
        judge_text = _extract_deepseek_message_text(judge_response)
        parsed = _parse_agent_liveness_judge_json(judge_text)
        report.update(parsed)
        report["raw_response_preview"], _changed = _truncate_middle_text(judge_text, 1200)
    except Exception as exc:
        report["decision"] = "ambiguous"
        report["reason"] = f"judge_error:{type(exc).__name__}:{str(exc)[:500]}"

    return report


def _write_agent_liveness_guard_report(report: dict[str, Any]) -> None:
    try:
        debug_dir = Path(".debug")
        debug_dir.mkdir(exist_ok=True)
        (debug_dir / "agent_liveness_guard_report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as exc:
        print(f"[deepseek-responses-proxy] failed to write agent liveness guard report: {exc}")


def _proxy_agent_liveness_status() -> dict[str, Any]:
    return {
        "config": _agent_liveness_env_config(),
        "judge": {
            "config": _agent_liveness_judge_env_config(),
        },
        "tool_protocol": {
            "config": _codex_tool_protocol_env_config(),
        },
        "last_report": _context_report_summary("agent_liveness_guard_report.json"),
    }


async def _run_chat_with_tool_bridge(
    *,
    deepseek_client: DeepSeekClient,
    chat_payload: dict[str, Any],
    messages_for_deepseek: list[dict[str, Any]],
    history_messages: list[dict[str, Any]],
    model: str,
    deepseek_tools: list[dict[str, Any]] | None,
    reasoning_effort: str | None,
    request_payload: dict[str, Any],
    store: Any | None = None,
    response_id: str | None = None,
    previous_response_id: str | None = None,
    usage_call_counter: dict[str, int] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    deepseek_response = await _chat_completions_with_usage(
        deepseek_client=deepseek_client,
        store=store,
        payload=chat_payload,
        purpose="primary",
        response_id=response_id,
        previous_response_id=previous_response_id,
        request_id=response_id,
        requested_model=request_payload.get("model"),
        thinking_enabled=_thinking_enabled(),
        call_counter=usage_call_counter,
    )

    if not _env_bool("DEEPSEEK_PROXY_TOOL_BRIDGE", True):
        return deepseek_response, history_messages

    max_rounds = _env_int("DEEPSEEK_PROXY_TOOL_MAX_ROUNDS", 3)
    if max_rounds <= 0:
        return deepseek_response, history_messages

    tool_trace: list[dict[str, Any]] = []
    liveness_config = _agent_liveness_env_config()
    liveness_report: dict[str, Any] = {
        "version": PROXY_VERSION,
        "enabled": bool(liveness_config["enabled"]),
        "triggered": False,
        "retry_count": 0,
        "max_retries": int(liveness_config["max_retries"]),
        "tools_available": bool(deepseek_tools),
        "guard_reason": "not_triggered",
        "retry_attempts": [],
    }

    for round_index in range(max_rounds):
        choices = deepseek_response.get("choices") or []
        if not choices:
            liveness_report["guard_reason"] = "no_choices"
            _write_agent_liveness_guard_report(liveness_report)
            return deepseek_response, history_messages

        assistant_message = choices[0].get("message") or {}
        tool_calls = assistant_message.get("tool_calls") or []
        pre_liveness_retry_response = deepseek_response
        liveness_retry_attempted = False

        while (
            not tool_calls
            and bool(liveness_config["enabled"])
            and int(liveness_report["retry_count"]) < int(liveness_config["max_retries"])
        ):
            heuristic_triggered = _assistant_message_needs_liveness_guard(
                assistant_message,
                tools_available=bool(deepseek_tools),
            )
            judge_report: dict[str, Any] | None = None
            judge_decision = "not_run"

            if not heuristic_triggered:
                if _assistant_message_is_obvious_final_answer(assistant_message):
                    liveness_report["guard_reason"] = "obvious_final_answer_no_retry"
                    _debug_trace_event(
                        response_id,
                        "liveness_guard_decision",
                        round_index=round_index + 1,
                        retry_count=int(liveness_report["retry_count"]),
                        should_retry=False,
                        guard_reason=liveness_report["guard_reason"],
                        heuristic_triggered=False,
                        assistant_content_chars=len(_plain_text_from_content(assistant_message.get("content", ""))),
                    )
                    break

                judge_report = await _judge_agent_liveness_with_llm(
                    deepseek_client=deepseek_client,
                    assistant_message=assistant_message,
                    messages_for_deepseek=messages_for_deepseek,
                    tools_available=bool(deepseek_tools),
                    store=store,
                    response_id=response_id,
                    previous_response_id=previous_response_id,
                    requested_model=request_payload.get("model"),
                    usage_call_counter=usage_call_counter,
                )
                liveness_report.setdefault("judge_attempts", []).append(judge_report)
                judge_decision = str(judge_report.get("decision") or "ambiguous")
                trigger_on_ambiguous = bool(
                    _agent_liveness_judge_env_config().get("trigger_on_ambiguous")
                )
                if judge_decision == "needs_tool_call" or (
                    judge_decision == "ambiguous" and trigger_on_ambiguous
                ):
                    liveness_report["guard_reason"] = f"judge_{judge_decision}"
                else:
                    liveness_report["guard_reason"] = f"judge_{judge_decision}_no_retry"
                    _debug_trace_event(
                        response_id,
                        "liveness_guard_decision",
                        round_index=round_index + 1,
                        retry_count=int(liveness_report["retry_count"]),
                        should_retry=False,
                        guard_reason=liveness_report["guard_reason"],
                        heuristic_triggered=False,
                        judge_decision=judge_decision,
                        assistant_content_chars=len(_plain_text_from_content(assistant_message.get("content", ""))),
                    )
                    break
            else:
                liveness_report["guard_reason"] = "assistant_narrated_tool_intent_without_tool_call"

            liveness_retry_attempted = True
            _debug_trace_event(
                response_id,
                "liveness_guard_decision",
                round_index=round_index + 1,
                retry_count=int(liveness_report["retry_count"]),
                should_retry=True,
                guard_reason=liveness_report.get("guard_reason"),
                heuristic_triggered=bool(heuristic_triggered),
                judge_decision=judge_decision,
                assistant_content_chars=len(_plain_text_from_content(assistant_message.get("content", ""))),
            )
            liveness_report["triggered"] = True
            liveness_report["round_index"] = round_index + 1
            liveness_report["retry_count"] = int(liveness_report["retry_count"]) + 1
            content_preview = _plain_text_from_content(assistant_message.get("content", "")).strip()
            content_preview, _changed = _truncate_middle_text(
                content_preview,
                int(liveness_config["content_preview_chars"]),
            )
            liveness_report["initial_content_preview"] = content_preview

            guard_messages = deepcopy(messages_for_deepseek)
            guard_messages.append(deepcopy(assistant_message))
            guard_messages.append(
                _agent_liveness_guard_prompt(
                    assistant_message,
                    retry_index=int(liveness_report["retry_count"]),
                    max_retries=int(liveness_config["max_retries"]),
                    preview_chars=int(liveness_config["content_preview_chars"]),
                )
            )
            guard_payload = _build_chat_payload(
                model=model,
                messages=guard_messages,
                tools=deepseek_tools,
                reasoning_effort=reasoning_effort,
                request_payload=request_payload,
            )
            deepseek_response = await _chat_completions_with_usage(
                deepseek_client=deepseek_client,
                store=store,
                payload=guard_payload,
                purpose="liveness_retry",
                response_id=response_id,
                previous_response_id=previous_response_id,
                request_id=response_id,
                requested_model=request_payload.get("model"),
                thinking_enabled=_thinking_enabled(),
                call_counter=usage_call_counter,
            )
            choices = deepseek_response.get("choices") or []
            if not choices:
                liveness_report["guard_reason"] = "guard_retry_returned_no_choices"
                break
            assistant_message = choices[0].get("message") or {}
            tool_calls = assistant_message.get("tool_calls") or []
            retry_content_preview = _plain_text_from_content(assistant_message.get("content", "")).strip()
            retry_content_preview, _changed = _truncate_middle_text(
                retry_content_preview,
                int(liveness_config["content_preview_chars"]),
            )
            retry_tool_names = []
            if isinstance(tool_calls, list):
                for tool_call in tool_calls:
                    if isinstance(tool_call, dict):
                        function = tool_call.get("function") or {}
                        if isinstance(function, dict):
                            retry_tool_names.append(function.get("name"))
            liveness_report.setdefault("retry_attempts", []).append(
                {
                    "retry_index": int(liveness_report["retry_count"]),
                    "response_has_tool_calls": bool(tool_calls),
                    "response_tool_call_count": len(tool_calls) if isinstance(tool_calls, list) else 0,
                    "response_tool_names": retry_tool_names,
                    "response_content_preview": retry_content_preview,
                }
            )
            if not tool_calls:
                liveness_report["guard_reason"] = "retry_without_tool_call_no_further_retry"
                _debug_trace_event(
                    response_id,
                    "liveness_guard_decision",
                    round_index=round_index + 1,
                    retry_count=int(liveness_report["retry_count"]),
                    should_retry=False,
                    guard_reason=liveness_report["guard_reason"],
                    retry_returned_tool_calls=False,
                    assistant_content_chars=len(_plain_text_from_content(assistant_message.get("content", ""))),
                )
                break

        liveness_report["final_has_tool_calls"] = bool(tool_calls)
        liveness_report["final_tool_call_count"] = len(tool_calls) if isinstance(tool_calls, list) else 0

        if not tool_calls:
            if liveness_retry_attempted:
                liveness_report["guard_reason"] = (
                    f"{liveness_report.get('guard_reason')}"
                    "_retry_without_tool_call_returned_pre_retry_response"
                )
                _write_agent_liveness_guard_report(liveness_report)
                return pre_liveness_retry_response, history_messages

            _write_agent_liveness_guard_report(liveness_report)
            return deepseek_response, history_messages

        if not all(_is_proxy_tool_call(tool_call) for tool_call in tool_calls):
            _write_agent_liveness_guard_report(liveness_report)
            return deepseek_response, history_messages

        assistant_history_item = deepcopy(assistant_message)
        if _thinking_enabled():
            assistant_history_item.setdefault("reasoning_content", "")
        messages_for_deepseek.append(assistant_history_item)
        history_messages.append(deepcopy(assistant_history_item))

        tool_messages: list[dict[str, Any]] = []
        for tool_call in tool_calls:
            result = await _execute_proxy_tool_call(
                tool_call,
                deepseek_client=deepseek_client,
                store=store,
            )
            tool_message = _tool_result_message(tool_call, result)
            tool_messages.append(tool_message)
            tool_trace.append(
                {
                    "round": round_index + 1,
                    "tool_call_id": tool_call.get("id"),
                    "tool_name": (tool_call.get("function") or {}).get("name"),
                    "result": result,
                }
            )

        messages_for_deepseek.extend(tool_messages)
        history_messages.extend(deepcopy(tool_messages))

        try:
            debug_dir = Path(".debug")
            debug_dir.mkdir(exist_ok=True)
            (debug_dir / "last_tool_bridge_trace.json").write_text(
                json.dumps(tool_trace, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:
            print(f"[deepseek-responses-proxy] failed to write tool bridge trace: {exc}")

        chat_payload = _build_chat_payload(
            model=model,
            messages=messages_for_deepseek,
            tools=deepseek_tools,
            reasoning_effort=reasoning_effort,
            request_payload=request_payload,
        )
        deepseek_response = await _chat_completions_with_usage(
            deepseek_client=deepseek_client,
            store=store,
            payload=chat_payload,
            purpose="tool_bridge",
            response_id=response_id,
            previous_response_id=previous_response_id,
            request_id=response_id,
            requested_model=request_payload.get("model"),
            thinking_enabled=_thinking_enabled(),
            call_counter=usage_call_counter,
        )

    liveness_report["guard_reason"] = "max_tool_bridge_rounds_reached"
    _write_agent_liveness_guard_report(liveness_report)
    return deepseek_response, history_messages


def _deepseek_message_to_output_items(
    message: dict[str, Any],
    mcp_tool_mapping: dict[str, dict[str, str]] | None = None,
) -> list[dict[str, Any]]:
    output_items: list[dict[str, Any]] = []

    content = _plain_text_from_content(message.get("content", ""))
    if content:
        output_items.append(
            {
                "id": _item_id("msg"),
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [
                    {
                        "type": "output_text",
                        "text": content,
                        "annotations": [],
                    }
                ],
            }
        )

    for tool_call in message.get("tool_calls", []) or []:
        function = tool_call.get("function") or {}
        function_name = function.get("name", "")
        mcp_mapping = (mcp_tool_mapping or {}).get(function_name)

        output_item = {
            "id": _item_id("fc"),
            "type": "function_call",
            "call_id": tool_call.get("id", _item_id("call")),
            "name": function_name,
            "arguments": function.get("arguments", "{}"),
        }

        if mcp_mapping:
            output_item["name"] = mcp_mapping["name"]
            output_item["namespace"] = mcp_mapping["namespace"]

        output_items.append(output_item)

    return output_items


def _image_result_output_items_from_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Surface generated image URLs/file paths in the final Responses output.

    The tool bridge may successfully generate an image, but the final model
    response may omit the URL. Codex TUI users should not need to inspect
    .debug/last_tool_bridge_trace.json to find generated assets.
    """
    output_items: list[dict[str, Any]] = []

    for message in messages:
        if message.get("role") != "tool":
            continue

        content = _plain_text_from_content(message.get("content"))
        if not isinstance(content, str) or not content.strip():
            continue

        try:
            result = json.loads(content)
        except json.JSONDecodeError:
            continue

        if not isinstance(result, dict):
            continue

        if result.get("provider") not in {"mock", "glm", "zai", "zhipu", "zhipuai", "bigmodel"}:
            continue

        images = result.get("images") or []
        if not images:
            continue

        lines = [
            "Generated image result:",
            f"- Provider: {result.get('provider')}",
            f"- Model: {result.get('model')}",
        ]

        prompt = result.get("prompt")
        if prompt:
            lines.append(f"- Prompt: {prompt}")

        size = result.get("size")
        if size:
            lines.append(f"- Size: {size}")

        for index, image in enumerate(images, start=1):
            if not isinstance(image, dict):
                continue

            url = image.get("url")
            file_path = image.get("file_path")

            if url:
                lines.append(f"- Image {index} URL: {url}")
            if file_path:
                lines.append(f"- Image {index} local path: {file_path}")
                file_uri = image.get("file_uri") or _image_file_uri(file_path)
                if file_uri:
                    lines.append(f"- Image {index} file URI: {file_uri}")
            if file_path:
                lines.append(f"- Image {index} file: {file_path}")

        text = "\n".join(lines)
        output_items.append(
            {
                "id": _item_id("msg"),
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [
                    {
                        "type": "output_text",
                        "text": text,
                        "annotations": [],
                    }
                ],
            }
        )

    return output_items


def _response_output_text(output_items: list[dict[str, Any]]) -> str:
    chunks: list[str] = []
    for item in output_items:
        if item.get("type") != "message":
            continue
        text = _plain_text_from_content(item.get("content", []))
        if text:
            chunks.append(text)
    return "".join(chunks)


def _truncate_error_body(body: str, limit: int = 4000) -> str:
    if len(body) <= limit:
        return body
    return body[:limit] + "...[truncated]"


def _upstream_exception_to_http_exception(exc: Exception) -> HTTPException:
    """Convert upstream DeepSeek/httpx failures into clean proxy errors.

    The route should not leak Python tracebacks to Codex. Keep the upstream
    status/body in detail so the client and logs remain debuggable.
    """
    if isinstance(exc, HTTPException):
        return exc

    if isinstance(exc, httpx.TimeoutException):
        return HTTPException(
            status_code=504,
            detail={
                "upstream": "deepseek",
                "error_type": "timeout",
                "message": str(exc),
            },
        )

    if isinstance(exc, httpx.HTTPStatusError):
        response = exc.response
        status_code = response.status_code
        body = _truncate_error_body(response.text)

        # 429 is useful for callers to distinguish from generic upstream
        # failures. Other upstream HTTP failures are exposed as bad gateway.
        proxy_status = 429 if status_code == 429 else 502

        return HTTPException(
            status_code=proxy_status,
            detail={
                "upstream": "deepseek",
                "status_code": status_code,
                "body": body,
            },
        )

    if isinstance(exc, httpx.RequestError):
        return HTTPException(
            status_code=502,
            detail={
                "upstream": "deepseek",
                "error_type": "network",
                "message": str(exc),
            },
        )

    return HTTPException(
        status_code=502,
        detail={
            "upstream": "deepseek",
            "error_type": "unexpected",
            "message": str(exc),
        },
    )


def _build_response_envelope(
    *,
    response_id: str,
    model: str,
    previous_response_id: str | None,
    output_items: list[dict[str, Any]],
    deepseek_response: dict[str, Any],
) -> dict[str, Any]:
    usage = deepseek_response.get("usage") or {}
    return {
        "id": response_id,
        "object": "response",
        "created_at": _now(),
        "status": "completed",
        "model": model,
        "previous_response_id": previous_response_id,
        "output": output_items,
        "output_text": _response_output_text(output_items),
        "usage": {
            "input_tokens": usage.get("prompt_tokens"),
            "output_tokens": usage.get("completion_tokens"),
            "total_tokens": usage.get("total_tokens"),
        },
    }


def _sse_event(event: str, data: dict[str, Any] | str) -> bytes:
    payload = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n".encode("utf-8")


def _stream_response_events(response: dict[str, Any]):
    """Emit a minimal OpenAI Responses-compatible SSE sequence.

    Codex expects the JSON payload of each SSE event to include a `type`
    field. For response.created / response.completed, Codex also expects
    the response object to be nested under `response`.
    """
    response_id = response["id"]

    yield _sse_event(
        "response.created",
        {
            "type": "response.created",
            "response": response,
        },
    )

    yield _sse_event(
        "response.in_progress",
        {
            "type": "response.in_progress",
            "response": {**response, "status": "in_progress"},
        },
    )

    for output_index, item in enumerate(response.get("output", [])):
        yield _sse_event(
            "response.output_item.added",
            {
                "type": "response.output_item.added",
                "response_id": response_id,
                "output_index": output_index,
                "item": item,
            },
        )

        if item.get("type") == "message":
            for content_index, content in enumerate(item.get("content", [])):
                if content.get("type") != "output_text":
                    continue

                part = {
                    "type": "output_text",
                    "text": "",
                    "annotations": [],
                }

                yield _sse_event(
                    "response.content_part.added",
                    {
                        "type": "response.content_part.added",
                        "response_id": response_id,
                        "item_id": item["id"],
                        "output_index": output_index,
                        "content_index": content_index,
                        "part": part,
                    },
                )

                text = content.get("text", "")

                if text:
                    yield _sse_event(
                        "response.output_text.delta",
                        {
                            "type": "response.output_text.delta",
                            "response_id": response_id,
                            "item_id": item["id"],
                            "output_index": output_index,
                            "content_index": content_index,
                            "delta": text,
                        },
                    )

                yield _sse_event(
                    "response.output_text.done",
                    {
                        "type": "response.output_text.done",
                        "response_id": response_id,
                        "item_id": item["id"],
                        "output_index": output_index,
                        "content_index": content_index,
                        "text": text,
                    },
                )

                yield _sse_event(
                    "response.content_part.done",
                    {
                        "type": "response.content_part.done",
                        "response_id": response_id,
                        "item_id": item["id"],
                        "output_index": output_index,
                        "content_index": content_index,
                        "part": {
                            "type": "output_text",
                            "text": text,
                            "annotations": content.get("annotations", []),
                        },
                    },
                )

        yield _sse_event(
            "response.output_item.done",
            {
                "type": "response.output_item.done",
                "response_id": response_id,
                "output_index": output_index,
                "item": item,
            },
        )

    yield _sse_event(
        "response.completed",
        {
            "type": "response.completed",
            "response": response,
        },
    )

    yield b"data: [DONE]\n\n"


def _build_chat_payload(
    *,
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
    reasoning_effort: str | None = None,
    request_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    messages = _messages_with_codex_tool_protocol_instruction(
        messages,
        tools_available=bool(tools),
    )

    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": False,
        "thinking": _deepseek_thinking_config(),
    }

    if reasoning_effort is not None:
        payload["reasoning_effort"] = reasoning_effort

    if request_payload is not None:
        max_tokens = request_payload.get("max_output_tokens")
        if max_tokens is None:
            max_tokens = request_payload.get("max_tokens")
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        for key in ["temperature", "top_p", "stop", "response_format"]:
            if key in request_payload and request_payload[key] is not None:
                payload[key] = request_payload[key]

    if tools:
        payload["tools"] = tools

    return payload


def _context_report_summary(filename: str) -> dict[str, Any]:
    path = Path(".debug") / filename
    summary: dict[str, Any] = {
        "path": str(path),
        "exists": path.exists(),
    }
    if not path.exists():
        return summary

    try:
        stat = path.stat()
        summary["size_bytes"] = stat.st_size
        summary["mtime"] = int(stat.st_mtime)
    except Exception as exc:
        summary["stat_error"] = str(exc)[:500]

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        summary["read_error"] = str(exc)[:500]
        return summary

    for key in [
        "version",
        "enabled",
        "compacted",
        "trimmed",
        "reason",
        "summary_source",
        "before_chars",
        "after_chars",
        "chars_removed",
        "message_count_before",
        "message_count_after",
        "policy",
        "trigger_chars",
        "target_chars",
        "effective_trigger_chars",
        "effective_target_chars",
        "emergency_chars",
        "max_context_chars",
        "max_tool_output_chars",
        "keep_recent_messages",
        "triggered",
        "retry_count",
        "max_retries",
        "tools_available",
        "round_index",
        "initial_content_preview",
        "final_has_tool_calls",
        "final_tool_call_count",
        "guard_reason",
        "retry_attempts",
        "judge_attempts",
    ]:
        if key in data:
            summary[key] = data[key]

    material = data.get("material")
    if isinstance(material, dict):
        summary["material"] = {
            key: material.get(key)
            for key in [
                "compactable_message_count",
                "recent_message_count",
                "recent_start",
                "material_chars",
                "recent_material_chars",
            ]
            if key in material
        }

    policy_decision = data.get("policy_decision")
    if isinstance(policy_decision, dict):
        growth = policy_decision.get("growth")
        summary["policy_decision"] = {
            key: policy_decision.get(key)
            for key in [
                "policy",
                "should_compact",
                "reason",
                "effective_trigger_chars",
                "effective_target_chars",
                "emergency_chars",
                "reserve_before_send",
                "reserve_after_compact",
                "min_new_chars",
                "min_turns",
            ]
            if key in policy_decision
        }
        if isinstance(growth, dict):
            summary["policy_decision"]["growth"] = {
                key: growth.get(key)
                for key in [
                    "recent_message_count",
                    "recent_growth_chars",
                    "recent_growth_chars_per_turn",
                    "last_compaction_summary_index",
                    "new_chars_since_last_compaction",
                    "turns_since_last_compaction",
                ]
                if key in growth
            }

    build = data.get("build")
    if isinstance(build, dict):
        summary["build"] = {
            key: build.get(key)
            for key in [
                "leading_message_count",
                "recent_message_count",
                "recent_start",
                "summary_chars",
                "summary_was_trimmed",
                "before_final_shrink_chars",
                "after_final_shrink_chars",
            ]
            if key in build
        }

    return summary


def _proxy_context_status() -> dict[str, Any]:
    return {
        "compaction": {
            "config": _context_compaction_env_config(),
            "last_report": _context_report_summary("context_compaction_report.json"),
        },
        "trimming": {
            "config": _context_trim_env_config(),
            "last_report": _context_report_summary("context_trimming_report.json"),
        },
    }


def _tool_bridge_status() -> dict[str, Any]:
    web_provider = _web_search_provider()
    image_provider = _image_provider()

    return {
        "enabled": _env_bool("DEEPSEEK_PROXY_TOOL_BRIDGE", True),
        "max_rounds": _env_int("DEEPSEEK_PROXY_TOOL_MAX_ROUNDS", 3),
        "web_search": {
            "provider": web_provider,
            "is_mock": web_provider == "mock",
            "max_results": _web_search_max_results(),
            "timeout_seconds": _web_search_timeout_seconds(),
            "api_key_configured": bool(_serpapi_api_key()) if web_provider == "serpapi" else None,
        },
        "image_generation": {
            "provider": image_provider,
            "is_mock": image_provider == "mock",
            "model": _image_model(),
            "size": _image_size(),
            "n": _image_n(),
            "download_enabled": _image_download_enabled(),
            "max_artifacts": _image_max_artifacts(),
            "output_dir": str(_image_output_dir()),
            "api_key_configured": bool(_image_api_key()) if image_provider != "mock" else None,
        },
        "mcp_executor": _mcp_executor_status(),
    }


def _mcp_discovery_enabled() -> bool:
    return _env_bool("DEEPSEEK_PROXY_MCP_DISCOVERY", False)


def _mcp_discovery_server_filter() -> set[str]:
    return _split_env_csv("DEEPSEEK_PROXY_MCP_DISCOVERY_SERVERS")


def _mcp_discovery_config_status() -> dict[str, Any]:
    return {
        "enabled": _mcp_discovery_enabled(),
        "endpoint": "/v1/proxy/mcp/discovery",
        "auto_run_in_status": False,
        "server_filter": sorted(_mcp_discovery_server_filter()),
        "operations": ["initialize", "notifications/initialized", "tools/list"],
        "tools_call_enabled": False,
        "production_execution": False,
    }


async def _mcp_discovery_status() -> dict[str, Any]:
    config_snapshot = _codex_mcp_config_snapshot()
    server_filter = _mcp_discovery_server_filter()

    result: dict[str, Any] = {
        "status": "ok",
        "version": PROXY_VERSION,
        "enabled": _mcp_discovery_enabled(),
        "production_execution": False,
        "tools_call_enabled": False,
        "operations": ["initialize", "notifications/initialized", "tools/list"],
        "server_filter": sorted(server_filter),
        "selected_servers": [],
        "codex_config": config_snapshot,
        "discovery_runs": {},
    }

    if not result["enabled"]:
        result["reason"] = "disabled"
        return result

    if not config_snapshot.get("exists"):
        result["reason"] = "config_missing"
        return result

    if config_snapshot.get("error"):
        result["reason"] = "config_error"
        return result

    from deepseek_responses_proxy.mcp_stdio import (
        discover_stdio_mcp_tools,
        mcp_server_config_from_snapshot,
    )

    runtime_snapshot = _codex_mcp_config_snapshot(include_env_values=True)
    runtime_servers = runtime_snapshot.get("servers") or {}
    if not isinstance(runtime_servers, dict):
        result["reason"] = "invalid_runtime_servers"
        return result

    selected_servers: list[str] = []
    discovery_runs: dict[str, Any] = {}

    for server_name, server_snapshot in sorted(runtime_servers.items()):
        if server_filter and server_name not in server_filter:
            continue
        if not isinstance(server_snapshot, dict):
            continue

        selected_servers.append(str(server_name))
        config = mcp_server_config_from_snapshot(str(server_name), server_snapshot)
        discovery_runs[str(server_name)] = await discover_stdio_mcp_tools(
            config,
            client_version=PROXY_VERSION,
        )

    result["selected_servers"] = selected_servers
    result["discovery_runs"] = discovery_runs
    result["reason"] = "completed"
    return result


def create_app(
    *,
    deepseek_client: DeepSeekClient | None = None,
    store: InMemoryResponseStore | None = None,
) -> FastAPI:
    app = FastAPI()
    app.state.deepseek_client = deepseek_client or DeepSeekClient()
    app.state.store = store or SQLiteResponseStore()
    app.state.started_at = _now()
    app.state.repair_count = 0

    @app.get("/healthz")
    async def healthz() -> dict[str, Any]:
        return {
            "status": "ok",
            "version": PROXY_VERSION,
            "thinking": _deepseek_thinking_config(),
        }

    @app.get("/v1/proxy/status")
    async def proxy_status() -> dict[str, Any]:
        return {
            "status": "ok",
            "version": PROXY_VERSION,
            "model_default": DEFAULT_MODEL,
            "thinking": _deepseek_thinking_config(),
            "thinking_enabled": _thinking_enabled(),
            "tool_bridge": _tool_bridge_status(),
            "context": _proxy_context_status(),
            "agent_liveness": _proxy_agent_liveness_status(),
            "semantic_compaction": _semantic_compaction_runtime_status(),
            "store": _store_info(app.state.store),
            "started_at": app.state.started_at,
            "uptime_seconds": max(0, _now() - app.state.started_at),
            "repair_count": app.state.repair_count,
            "deepseek_base_url": getattr(app.state.deepseek_client, "base_url", None),
        }

    @app.get("/v1/proxy/tool-bridge/status")
    async def proxy_tool_bridge_status() -> dict[str, Any]:
        return {
            "status": "ok",
            "version": PROXY_VERSION,
            "tool_bridge": _tool_bridge_status(),
        }

    @app.get("/v1/proxy/mcp/discovery")
    async def proxy_mcp_discovery() -> dict[str, Any]:
        return await _mcp_discovery_status()

    @app.post("/v1/proxy/mcp/diagnostic-call")
    async def proxy_mcp_diagnostic_call(request: Request) -> dict[str, Any]:
        payload = await request.json()
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="request body must be a JSON object")
        return await _mcp_diagnostic_call(payload)

    @app.get("/v1/proxy/balance")
    async def proxy_balance() -> dict[str, Any]:
        try:
            balance = await app.state.deepseek_client.user_balance()
        except Exception as exc:
            raise _upstream_exception_to_http_exception(exc) from exc

        return {
            "status": "ok",
            "upstream": "deepseek",
            "balance": balance,
        }

    @app.get("/v1/proxy/usage")
    async def proxy_usage(
        limit: int = 100,
        since: int | None = None,
        until: int | None = None,
        thinking: bool | None = None,
        model: str | None = None,
        purpose: str | None = None,
    ) -> dict[str, Any]:
        if since is not None and until is not None and until < since:
            raise HTTPException(status_code=400, detail="until must be greater than or equal to since")

        filters = {
            "since": since,
            "until": until,
            "thinking": thinking,
            "model": model,
        }
        if purpose is not None:
            filters["purpose"] = purpose

        if not hasattr(app.state.store, "usage_events"):
            return {
                "status": "ok",
                "usage_events": [],
                "filters": filters,
                "note": "current store does not support usage ledger",
            }

        safe_limit = max(1, min(int(limit), 1000))
        return {
            "status": "ok",
            "filters": filters,
            "usage_events": app.state.store.usage_events(
                limit=safe_limit,
                since=since,
                until=until,
                thinking=thinking,
                model=model,
                purpose=purpose,
            ),
        }

    @app.get("/v1/proxy/usage/summary")
    async def proxy_usage_summary(
        since: int | None = None,
        until: int | None = None,
        thinking: bool | None = None,
        model: str | None = None,
        purpose: str | None = None,
    ) -> dict[str, Any]:
        if since is not None and until is not None and until < since:
            raise HTTPException(status_code=400, detail="until must be greater than or equal to since")

        filters = {
            "since": since,
            "until": until,
            "thinking": thinking,
            "model": model,
        }
        if purpose is not None:
            filters["purpose"] = purpose

        if not hasattr(app.state.store, "usage_summary"):
            return {
                "status": "ok",
                "summary": {
                    "request_count": 0,
                    "estimated_cost_usd": 0.0,
                },
                "filters": filters,
                "note": "current store does not support usage ledger",
            }

        return {
            "status": "ok",
            "summary": app.state.store.usage_summary(
                since=since,
                until=until,
                thinking=thinking,
                model=model,
                purpose=purpose,
            ),
            "filters": filters,
            "pricing_usd_per_1m": _load_model_pricing_usd_per_1m(),
        }

    @app.get("/v1/proxy/debug/status")
    async def proxy_debug_status() -> dict[str, Any]:
        return {
            "status": "ok",
            "version": PROXY_VERSION,
            "debug_trace": _debug_trace_status(),
        }

    @app.get("/v1/proxy/debug/latest")
    async def proxy_debug_latest(limit: int = 200) -> dict[str, Any]:
        return _debug_trace_latest(limit=limit)

    @app.get("/v1/proxy/debug/long-session")
    async def proxy_debug_long_session(limit: int = 200, mode: str = "aggregate") -> dict[str, Any]:
        return _long_session_observability_report(limit=limit, mode=mode)

    @app.get("/v1/models")
    async def list_models() -> dict[str, Any]:
        created = _now()
        return {
            "object": "list",
            "data": [
                {
                    "id": DEFAULT_MODEL,
                    "object": "model",
                    "created": created,
                    "owned_by": "deepseek",
                }
            ],
        }

    @app.get("/v1/responses/{response_id}")
    async def get_response(response_id: str) -> dict[str, Any]:
        stored = app.state.store.get(response_id)
        if stored is None:
            raise HTTPException(status_code=404, detail="response not found")
        return stored.response

    @app.get("/v1/proxy/debug/semantic-selftest")
    async def proxy_debug_semantic_selftest() -> dict[str, Any]:
        return _semantic_compaction_selftest_report()

    @app.get("/v1/proxy/debug/semantic-canary-check")
    async def proxy_debug_semantic_canary_check() -> dict[str, Any]:
        return _semantic_compaction_canary_check_report()

    @app.post("/v1/responses")
    async def create_response(request: Request):
        payload = await request.json()
        response_id = _response_id()
        usage_call_counter: dict[str, int] = {"value": 0}

        _debug_trace_event(
            response_id,
            "request_received",
            payload_summary=_debug_trace_summary(payload, label="responses_payload"),
            request_model=payload.get("model"),
            previous_response_id=payload.get("previous_response_id"),
            stream=bool(payload.get("stream")),
        )

        try:
            debug_dir = Path(".debug")
            debug_dir.mkdir(exist_ok=True)
            (debug_dir / "last_responses_payload.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:
            print(f"[deepseek-responses-proxy] failed to write responses debug payload: {exc}")

        model = _select_upstream_model(payload.get("model"))
        previous_response_id = payload.get("previous_response_id")
        stream = bool(payload.get("stream"))
        tools = payload.get("tools") or []
        compat_warnings: list[dict[str, Any]] = []
        mcp_tool_mapping: dict[str, dict[str, str]] = {}
        deepseek_tools_list: list[dict[str, Any]] = []
        for tool in tools:
            normalized_tool = _normalize_response_tool(tool, compat_warnings, mcp_tool_mapping)
            if isinstance(normalized_tool, list):
                deepseek_tools_list.extend(normalized_tool)
            elif normalized_tool is not None:
                deepseek_tools_list.append(normalized_tool)
        if _env_bool("DEEPSEEK_PROXY_TOOL_BRIDGE", True) and deepseek_tools_list:
            existing_tool_names = {
                ((tool.get("function") or {}).get("name"))
                for tool in deepseek_tools_list
            }
            for proxy_tool in _proxy_tool_schemas():
                proxy_name = (proxy_tool.get("function") or {}).get("name")
                if proxy_name not in existing_tool_names:
                    deepseek_tools_list.append(proxy_tool)
        deepseek_tools = deepseek_tools_list or None

        try:
            debug_dir = Path(".debug")
            debug_dir.mkdir(exist_ok=True)
            (debug_dir / "last_compat_warnings.json").write_text(
                json.dumps(compat_warnings, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:
            print(f"[deepseek-responses-proxy] failed to write compat warnings: {exc}")

        if previous_response_id:
            stored = app.state.store.get(previous_response_id)
            if stored is None:
                raise HTTPException(status_code=404, detail="previous_response_id not found")
            messages = stored.chat_messages

            # If a thinking-mode session resumes from legacy disabled-mode
            # history, patch assistant messages that lack reasoning_content and
            # persist the repaired history back to the response store.
            messages, repaired_history = _repair_thinking_history_messages(messages)
            if repaired_history:
                app.state.store.save(stored.response, messages)
                app.state.repair_count += 1
                print(
                    f"[deepseek-responses-proxy] repaired missing reasoning_content "
                    f"for previous_response_id={previous_response_id}"
                )
        else:
            messages = []

        input_value = payload.get("input")

        # When previous_response_id is present, stored.chat_messages already
        # contains the assistant message with tool_calls from the previous
        # response. Codex may still include function_call items in the new
        # input; passing them through again would duplicate assistant tool_calls.
        if previous_response_id and isinstance(input_value, list):
            input_value = [
                item
                for item in input_value
                if item.get("type") != "function_call"
            ]

        input_value, tool_output_trim_report = _apply_tool_output_safe_trimming(input_value)
        _debug_trace_event(
            response_id,
            "tool_output_trim_applied",
            **tool_output_trim_report,
        )

        messages.extend(_input_items_to_messages(input_value))

        _debug_trace_event(
            response_id,
            "history_loaded",
            previous_response_id=previous_response_id,
            message_count=len(messages),
            history_chars=_json_char_size({"messages": messages}),
            input_summary=_debug_trace_summary(input_value, label="input"),
        )

        messages, repaired_tool_history = _repair_tool_call_message_order(messages)
        if repaired_tool_history:
            app.state.repair_count += 1
            print(
                f"[deepseek-responses-proxy] repaired tool_call message order "
                f"for previous_response_id={previous_response_id}"
            )

        should_flatten_tool_transcripts = (
            _thinking_enabled()
            or (previous_response_id is None and deepseek_tools is None)
        )
        if should_flatten_tool_transcripts:
            messages, flattened_tool_history = _flatten_self_contained_tool_messages(messages)
            if flattened_tool_history:
                app.state.repair_count += 1
                if _thinking_enabled():
                    print(
                        "[deepseek-responses-proxy] flattened tool messages "
                        "for thinking-mode compatibility"
                    )
                else:
                    print(
                        "[deepseek-responses-proxy] flattened self-contained "
                        "tool messages because no DeepSeek tools were available"
                    )

        messages_before_compaction = deepcopy(messages)
        _debug_trace_event(
            response_id,
            "history_growth_breakdown",
            **_history_growth_breakdown(
                messages_before_compaction,
                input_value=input_value,
                previous_response_id=previous_response_id,
            ),
        )
        _debug_trace_event(
            response_id,
            "flattened_tool_transcript_compaction_dry_run",
            **_flattened_tool_transcript_compaction_dry_run(messages_before_compaction),
        )
        _debug_trace_event(
            response_id,
            "flattened_tool_transcript_semantic_audit",
            **_flattened_tool_transcript_semantic_audit(messages_before_compaction),
        )
        _debug_trace_event(
            response_id,
            "flattened_tool_transcript_semantic_policy_dry_run",
            **_flattened_tool_transcript_semantic_compaction_policy_dry_run(messages_before_compaction),
        )
        messages, context_compaction_report = await _compact_chat_history_for_codex_like_persistence(
            deepseek_client=app.state.deepseek_client,
            messages=messages,
            request_payload=payload,
            previous_response_id=previous_response_id,
            store=app.state.store,
            response_id=response_id,
            usage_call_counter=usage_call_counter,
        )
        _write_context_compaction_report(context_compaction_report)
        _debug_trace_event(
            response_id,
            "compaction_finished",
            compacted=context_compaction_report.get("compacted"),
            reason=context_compaction_report.get("reason"),
            policy=context_compaction_report.get("policy"),
            before_chars=context_compaction_report.get("before_chars"),
            after_chars=context_compaction_report.get("after_chars"),
            chars_removed=context_compaction_report.get("chars_removed"),
            message_count_before=context_compaction_report.get("message_count_before"),
            message_count_after=context_compaction_report.get("message_count_after"),
            policy_decision=context_compaction_report.get("policy_decision"),
            summary_source=context_compaction_report.get("summary_source"),
            material=context_compaction_report.get("material"),
        )
        if context_compaction_report.get("compacted"):
            messages, _repaired_after_compaction = _repair_tool_call_message_order(messages)
            if _thinking_enabled():
                messages, _repaired_thinking_after_compaction = _repair_thinking_history_messages(messages)

        payload_messages, semantic_payload_compaction_report = _apply_flattened_tool_transcript_semantic_payload_compaction(messages)
        _debug_trace_event(
            response_id,
            "flattened_tool_transcript_semantic_payload_compaction_applied",
            **semantic_payload_compaction_report,
        )

        payload_messages, flattened_payload_compaction_report = _apply_flattened_tool_transcript_payload_compaction(payload_messages)
        _debug_trace_event(
            response_id,
            "flattened_tool_transcript_payload_compaction_applied",
            **flattened_payload_compaction_report,
        )

        messages_for_deepseek = _prepare_messages_for_deepseek(payload_messages)
        reasoning_effort = _deepseek_reasoning_effort_config(payload)
        chat_payload = _build_chat_payload(
            model=model,
            messages=messages_for_deepseek,
            tools=deepseek_tools,
            reasoning_effort=reasoning_effort,
            request_payload=payload,
        )
        _debug_trace_event(
            response_id,
            "context_budget_breakdown",
            **_context_budget_breakdown(
                request_payload=payload,
                input_value=input_value,
                messages_before_compaction=messages_before_compaction,
                messages_after_compaction=messages,
                messages_for_deepseek=messages_for_deepseek,
                deepseek_tools=deepseek_tools,
                chat_payload=chat_payload,
                context_compaction_report=context_compaction_report,
            ),
        )
        _debug_trace_event(
            response_id,
            "tool_output_budget_breakdown",
            **_tool_output_budget_breakdown(input_value),
        )
        _debug_trace_event(
            response_id,
            "messages_prepared_for_deepseek",
            model=model,
            reasoning_effort=reasoning_effort,
            message_count=len(messages_for_deepseek),
            payload_chars=_json_char_size(chat_payload),
            tool_count=len(deepseek_tools or []),
        )
        try:
            deepseek_response, messages = await _run_chat_with_tool_bridge(
                deepseek_client=app.state.deepseek_client,
                chat_payload=chat_payload,
                messages_for_deepseek=messages_for_deepseek,
                history_messages=messages,
                model=model,
                deepseek_tools=deepseek_tools,
                reasoning_effort=reasoning_effort,
                request_payload=payload,
                store=app.state.store,
                response_id=response_id,
                previous_response_id=previous_response_id,
                usage_call_counter=usage_call_counter,
            )
        except Exception as exc:
            raise _upstream_exception_to_http_exception(exc) from exc

        try:
            assistant_message = deepseek_response["choices"][0]["message"]
        except (KeyError, IndexError) as exc:
            raise HTTPException(status_code=502, detail="invalid DeepSeek response") from exc

        output_items = _deepseek_message_to_output_items(assistant_message, mcp_tool_mapping)
        output_items.extend(_image_result_output_items_from_messages(messages))
        response_body = _build_response_envelope(
            response_id=response_id,
            model=model,
            previous_response_id=previous_response_id,
            output_items=output_items,
            deepseek_response=deepseek_response,
        )
        _debug_trace_event(
            response_id,
            "response_envelope_built",
            output_item_count=len(output_items),
            response_chars=_json_char_size(response_body),
            history_message_count=len(messages),
        )

        next_history = deepcopy(messages)
        assistant_history_item = {"role": "assistant", "content": assistant_message.get("content") or ""}
        if assistant_message.get("tool_calls"):
            assistant_history_item["tool_calls"] = deepcopy(assistant_message["tool_calls"])
        if "reasoning_content" in assistant_message:
            assistant_history_item["reasoning_content"] = assistant_message.get("reasoning_content") or ""
        elif _deepseek_thinking_config().get("type") == "enabled":
            # DeepSeek thinking mode requires assistant history to carry
            # reasoning_content on follow-up turns. Preserve an explicit empty
            # value when the upstream response omits it.
            assistant_history_item["reasoning_content"] = ""
        next_history.append(assistant_history_item)
        app.state.store.save(response_body, next_history)

        if stream:
            return StreamingResponse(_stream_response_events(response_body), media_type="text/event-stream")
        return JSONResponse(response_body)

    return app


app = create_app()
