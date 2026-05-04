from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse


DEFAULT_MODEL = os.environ.get("DEEPSEEK_PROXY_MODEL", "deepseek-v4-pro").strip() or "deepseek-v4-pro"
PROXY_VERSION = "v1.9-namespace-tool-registry"

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
    immediately followed by tool messages for each tool_call_id. Codex can leave
    a previous response at an intermediate state where the assistant requested a
    tool call, but the next request does not provide the matching
    function_call_output. Instead of sending invalid history upstream, insert a
    synthetic tool message that explicitly marks the call as incomplete.

    This is a protocol repair only. It does not fabricate a successful tool
    result.
    """
    repaired = False
    repaired_messages: list[dict[str, Any]] = []

    i = 0
    while i < len(messages):
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

            while i < len(messages) and messages[i].get("role") == "tool":
                tool_message = deepcopy(messages[i])
                tool_call_id = tool_message.get("tool_call_id")

                if tool_call_id in expected_call_ids and tool_call_id not in seen_call_ids:
                    repaired_messages.append(tool_message)
                    seen_call_ids.add(tool_call_id)
                else:
                    repaired = True
                    repaired_messages.append(
                        {
                            "role": "user",
                            "content": (
                                "[orphaned tool output ignored by protocol repair]\n"
                                f"tool_call_id={tool_call_id or 'unknown'}\n"
                                f"{_stringify_content(tool_message.get('content', ''))}"
                            ),
                        }
                    )

                i += 1

            for call_id in expected_call_ids:
                if call_id not in seen_call_ids:
                    repaired = True
                    repaired_messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call_id,
                            "content": (
                                "[tool call was not completed before the conversation "
                                "continued; no tool output is available]"
                            ),
                        }
                    )

            continue

        if role == "tool":
            repaired = True
            repaired_messages.append(
                {
                    "role": "user",
                    "content": (
                        "[orphaned tool output ignored by protocol repair]\n"
                        f"tool_call_id={message.get('tool_call_id') or 'unknown'}\n"
                        f"{_stringify_content(message.get('content', ''))}"
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

            content = _stringify_content(message.get("content", ""))
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
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO usage_events (
                    created_at,
                    response_id,
                    previous_response_id,
                    model,
                    thinking_enabled,
                    prompt_tokens,
                    completion_tokens,
                    total_tokens,
                    cached_tokens,
                    reasoning_tokens,
                    estimated_cost_usd
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _now(),
                    response_id,
                    previous_response_id,
                    model,
                    1 if thinking_enabled else 0,
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
    ) -> list[dict[str, Any]]:
        where_sql, params = self._usage_filter_where(
            since=since,
            until=until,
            thinking=thinking,
            model=model,
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
    ) -> dict[str, Any]:
        where_sql, params = self._usage_filter_where(
            since=since,
            until=until,
            thinking=thinking,
            model=model,
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


def _normalize_response_tool(
    tool: dict[str, Any],
    compat_warnings: list[dict[str, Any]] | None = None,
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
        "content": _stringify_content(content),
    }

    if _thinking_enabled() and role == "assistant":
        message.setdefault("reasoning_content", "")

    return message

def _input_items_to_messages(input_value: Any) -> list[dict[str, Any]]:
    """Convert Responses input items to DeepSeek ChatCompletions messages.

    Codex may send both `function_call` and `function_call_output` items
    during tool continuation. When `previous_response_id` is present, the
    stored history should already contain the assistant tool_call message.
    Still, we support `function_call` here for robustness and for cases where
    Codex sends a self-contained continuation input.
    """
    if input_value is None:
        return []
    if isinstance(input_value, str):
        return [{"role": "user", "content": input_value}]
    if not isinstance(input_value, list):
        raise HTTPException(status_code=400, detail="input must be a string or list")

    messages: list[dict[str, Any]] = []

    for item in input_value:
        item_type = item.get("type")

        if item_type == "message":
            role = item.get("role", "user")
            messages.append(_message_from_response_content(role, item.get("content", [])))
            continue

        if item_type in {"input_text", "output_text", "text"}:
            role = _normalize_chat_role(item.get("role", "user"))
            messages.append({"role": role, "content": item.get("text", "")})
            continue

        if item_type == "function_call":
            # Responses function_call item:
            # {"type":"function_call","call_id":"...","name":"...","arguments":"..."}
            # ChatCompletions equivalent:
            # assistant message with tool_calls.
            call_id = item.get("call_id") or item.get("id") or _item_id("call")
            name = item.get("name", "")
            arguments = item.get("arguments", "")

            if not name:
                print("[deepseek-responses-proxy] ignored function_call input with missing name")
                continue

            messages.append(
                {
                    "role": "assistant",
                    "content": item.get("content") or "",
                    "tool_calls": [
                        {
                            "id": call_id,
                            "type": "function",
                            "function": {
                                "name": name,
                                "arguments": arguments,
                            },
                        }
                    ],
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
            continue

        # Some Responses streams may include bookkeeping items that DeepSeek
        # cannot consume directly. Ignore known non-message items rather than
        # failing the whole request.
        if item_type in {"reasoning", "summary_text"}:
            print(f"[deepseek-responses-proxy] ignored unsupported input item type: {item_type}")
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

    return str(path)


async def _mock_image_generate(arguments: dict[str, Any]) -> dict[str, Any]:
    prompt = str(arguments.get("prompt") or "").strip()
    size = _image_size(arguments.get("size"))
    n = _image_n(arguments.get("n"))

    return {
        "ok": True,
        "provider": "mock",
        "model": "mock-image",
        "prompt": prompt,
        "size": size,
        "images": [
            {
                "url": "https://example.com/mock-generated-image.png",
                "file_path": None,
                "mime_type": "image/png",
            }
            for _ in range(n)
        ],
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
                "file_path": file_path,
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
    name = function.get("name", "")
    arguments = _decode_tool_arguments(function.get("arguments", ""))

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


def _is_proxy_tool_call(tool_call: dict[str, Any]) -> bool:
    function = tool_call.get("function") or {}
    name = function.get("name", "")
    return name.startswith("proxy_")


def _tool_result_message(tool_call: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    return {
        "role": "tool",
        "tool_call_id": tool_call.get("id", _item_id("call")),
        "content": json.dumps(result, ensure_ascii=False),
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
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    deepseek_response = await deepseek_client.chat_completions(chat_payload)

    if not _env_bool("DEEPSEEK_PROXY_TOOL_BRIDGE", True):
        return deepseek_response, history_messages

    max_rounds = _env_int("DEEPSEEK_PROXY_TOOL_MAX_ROUNDS", 3)
    if max_rounds <= 0:
        return deepseek_response, history_messages

    tool_trace: list[dict[str, Any]] = []

    for round_index in range(max_rounds):
        choices = deepseek_response.get("choices") or []
        if not choices:
            return deepseek_response, history_messages

        assistant_message = choices[0].get("message") or {}
        tool_calls = assistant_message.get("tool_calls") or []
        if not tool_calls:
            return deepseek_response, history_messages

        if not all(_is_proxy_tool_call(tool_call) for tool_call in tool_calls):
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
        deepseek_response = await deepseek_client.chat_completions(chat_payload)

    return deepseek_response, history_messages


def _deepseek_message_to_output_items(message: dict[str, Any]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    content = message.get("content")
    if content:
        output.append(
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
        output.append(
            {
                "id": _item_id("fc"),
                "type": "function_call",
                "call_id": tool_call["id"],
                "name": function.get("name", ""),
                "arguments": function.get("arguments", ""),
                "status": "completed",
            }
        )
    return output



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

        content = message.get("content")
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
        for content in item.get("content", []):
            if content.get("type") == "output_text":
                chunks.append(content.get("text", ""))
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
            "output_dir": str(_image_output_dir()),
            "api_key_configured": bool(_image_api_key()) if image_provider != "mock" else None,
        },
    }


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
    ) -> dict[str, Any]:
        if since is not None and until is not None and until < since:
            raise HTTPException(status_code=400, detail="until must be greater than or equal to since")

        filters = {
            "since": since,
            "until": until,
            "thinking": thinking,
            "model": model,
        }

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
            ),
        }

    @app.get("/v1/proxy/usage/summary")
    async def proxy_usage_summary(
        since: int | None = None,
        until: int | None = None,
        thinking: bool | None = None,
        model: str | None = None,
    ) -> dict[str, Any]:
        if since is not None and until is not None and until < since:
            raise HTTPException(status_code=400, detail="until must be greater than or equal to since")

        filters = {
            "since": since,
            "until": until,
            "thinking": thinking,
            "model": model,
        }

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
            ),
            "filters": filters,
            "pricing_usd_per_1m": _load_model_pricing_usd_per_1m(),
        }

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

    @app.post("/v1/responses")
    async def create_response(request: Request):
        payload = await request.json()

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
        deepseek_tools_list: list[dict[str, Any]] = []
        for tool in tools:
            normalized_tool = _normalize_response_tool(tool, compat_warnings)
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

        messages.extend(_input_items_to_messages(input_value))

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

        messages_for_deepseek = _prepare_messages_for_deepseek(messages)
        reasoning_effort = _deepseek_reasoning_effort_config(payload)
        chat_payload = _build_chat_payload(
            model=model,
            messages=messages_for_deepseek,
            tools=deepseek_tools,
            reasoning_effort=reasoning_effort,
            request_payload=payload,
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
            )
        except Exception as exc:
            raise _upstream_exception_to_http_exception(exc) from exc

        try:
            assistant_message = deepseek_response["choices"][0]["message"]
        except (KeyError, IndexError) as exc:
            raise HTTPException(status_code=502, detail="invalid DeepSeek response") from exc

        output_items = _deepseek_message_to_output_items(assistant_message)
        output_items.extend(_image_result_output_items_from_messages(messages))
        response_id = _response_id()
        response_body = _build_response_envelope(
            response_id=response_id,
            model=model,
            previous_response_id=previous_response_id,
            output_items=output_items,
            deepseek_response=deepseek_response,
        )

        if hasattr(app.state.store, "record_usage"):
            usage_numbers = _extract_usage_numbers(deepseek_response)
            estimated_cost_usd = _estimate_cost_usd(model, usage_numbers)
            app.state.store.record_usage(
                response_id=response_id,
                previous_response_id=previous_response_id,
                model=model,
                thinking_enabled=_thinking_enabled(),
                usage_numbers=usage_numbers,
                estimated_cost_usd=estimated_cost_usd,
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
