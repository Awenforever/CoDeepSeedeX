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


DEFAULT_MODEL = "deepseek-v4-flash"
PROXY_VERSION = "v0.9-usage-ledger"

# USD per 1M tokens. Keep this table small and explicit.
# Source should be periodically checked against DeepSeek official pricing.
MODEL_PRICING_USD_PER_1M: dict[str, dict[str, float]] = {
    "deepseek-v4-flash": {
        "input_cache_hit": 0.0028,
        "input_cache_miss": 0.14,
        "output": 0.28,
    }
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


def _estimate_cost_usd(model: str, usage_numbers: dict[str, int]) -> float:
    pricing = MODEL_PRICING_USD_PER_1M.get(model)
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


def _prepare_messages_for_deepseek(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Prepare ChatCompletions messages for DeepSeek.

    In thinking mode, DeepSeek requires assistant history messages to carry
    `reasoning_content`. Codex may send assistant history items in Responses
    input without that field, so we normalize immediately before the upstream
    DeepSeek request.
    """
    prepared, _changed = _repair_thinking_history_messages(messages)
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

    def usage_events(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM usage_events
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def usage_summary(self) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT
                    COUNT(*) AS request_count,
                    COALESCE(SUM(prompt_tokens), 0) AS prompt_tokens,
                    COALESCE(SUM(completion_tokens), 0) AS completion_tokens,
                    COALESCE(SUM(total_tokens), 0) AS total_tokens,
                    COALESCE(SUM(cached_tokens), 0) AS cached_tokens,
                    COALESCE(SUM(reasoning_tokens), 0) AS reasoning_tokens,
                    COALESCE(SUM(estimated_cost_usd), 0.0) AS estimated_cost_usd
                FROM usage_events
                """
            ).fetchone()

            by_model_rows = conn.execute(
                """
                SELECT
                    model,
                    COUNT(*) AS request_count,
                    COALESCE(SUM(total_tokens), 0) AS total_tokens,
                    COALESCE(SUM(estimated_cost_usd), 0.0) AS estimated_cost_usd
                FROM usage_events
                GROUP BY model
                ORDER BY estimated_cost_usd DESC
                """
            ).fetchall()

        return {
            "request_count": int(row["request_count"]),
            "prompt_tokens": int(row["prompt_tokens"]),
            "completion_tokens": int(row["completion_tokens"]),
            "total_tokens": int(row["total_tokens"]),
            "cached_tokens": int(row["cached_tokens"]),
            "reasoning_tokens": int(row["reasoning_tokens"]),
            "estimated_cost_usd": float(row["estimated_cost_usd"]),
            "by_model": [dict(r) for r in by_model_rows],
        }

    def cleanup_older_than(self, cutoff_created_at: int) -> int:
        """Delete rows older than cutoff_created_at. Returns deleted row count."""
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM responses WHERE created_at < ?",
                (cutoff_created_at,),
            )
            return int(cur.rowcount or 0)


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
        self._client = http_client or httpx.AsyncClient(timeout=60.0)

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


def _normalize_response_tool(tool: dict[str, Any]) -> dict[str, Any] | None:
    """Convert a Responses function tool into a DeepSeek ChatCompletions tool.

    Codex may include built-in Responses tools such as web_search.
    DeepSeek ChatCompletions cannot execute these built-in tools.
    Unsupported non-function tools are intentionally ignored instead of
    failing the whole request.
    """
    tool_type = tool.get("type")

    if tool_type != "function":
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
    role = _normalize_chat_role(role)
    if isinstance(content, str):
        return {"role": role, "content": content}
    if isinstance(content, list):
        text_parts: list[str] = []
        for part in content:
            part_type = part.get("type")
            if part_type in {"input_text", "output_text", "text"}:
                text_parts.append(part.get("text", ""))
        return {"role": role, "content": "".join(text_parts)}
    raise HTTPException(status_code=400, detail=f"Unsupported message content: {content!r}")


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
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": False,
        "thinking": _deepseek_thinking_config(),
    }
    if tools:
        payload["tools"] = tools
    return payload


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
            "store": _store_info(app.state.store),
            "started_at": app.state.started_at,
            "uptime_seconds": max(0, _now() - app.state.started_at),
            "repair_count": app.state.repair_count,
            "deepseek_base_url": getattr(app.state.deepseek_client, "base_url", None),
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
    async def proxy_usage(limit: int = 100) -> dict[str, Any]:
        if not hasattr(app.state.store, "usage_events"):
            return {
                "status": "ok",
                "usage_events": [],
                "note": "current store does not support usage ledger",
            }

        safe_limit = max(1, min(int(limit), 1000))
        return {
            "status": "ok",
            "usage_events": app.state.store.usage_events(limit=safe_limit),
        }

    @app.get("/v1/proxy/usage/summary")
    async def proxy_usage_summary() -> dict[str, Any]:
        if not hasattr(app.state.store, "usage_summary"):
            return {
                "status": "ok",
                "summary": {
                    "request_count": 0,
                    "estimated_cost_usd": 0.0,
                },
                "note": "current store does not support usage ledger",
            }

        return {
            "status": "ok",
            "summary": app.state.store.usage_summary(),
            "pricing_usd_per_1m": MODEL_PRICING_USD_PER_1M,
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
        model = payload.get("model") or DEFAULT_MODEL
        previous_response_id = payload.get("previous_response_id")
        stream = bool(payload.get("stream"))
        tools = payload.get("tools") or []
        deepseek_tools_list: list[dict[str, Any]] = []
        for tool in tools:
            normalized_tool = _normalize_response_tool(tool)
            if normalized_tool is not None:
                deepseek_tools_list.append(normalized_tool)
        deepseek_tools = deepseek_tools_list or None

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

        messages_for_deepseek = _prepare_messages_for_deepseek(messages)
        chat_payload = _build_chat_payload(model=model, messages=messages_for_deepseek, tools=deepseek_tools)
        try:
            deepseek_response = await app.state.deepseek_client.chat_completions(chat_payload)
        except Exception as exc:
            raise _upstream_exception_to_http_exception(exc) from exc

        try:
            assistant_message = deepseek_response["choices"][0]["message"]
        except (KeyError, IndexError) as exc:
            raise HTTPException(status_code=502, detail="invalid DeepSeek response") from exc

        output_items = _deepseek_message_to_output_items(assistant_message)
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
