#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PROJECT = Path(__file__).resolve().parents[1]
DEBUG_DIR = PROJECT / ".debug"


@dataclass
class CaseResult:
    name: str
    base_url: str
    status: int | None
    ok: bool
    error: str | None
    response_id: str | None
    output_preview: str | None
    request_keys: list[str]
    upstream_keys: list[str]
    upstream_model: str | None
    upstream_thinking: Any
    upstream_reasoning_effort: Any
    upstream_tools_count: int
    upstream_has_response_format: bool
    upstream_has_temperature: bool
    upstream_has_top_p: bool
    upstream_has_max_tokens: bool
    compat_warning_count: int
    compat_warning_kinds: list[str]


def http_json(method: str, url: str, payload: dict[str, Any] | None = None, timeout: int = 120) -> tuple[int, Any]:
    data = None
    headers = {"Content-Type": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            if not raw:
                return resp.status, None
            return resp.status, json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(raw)
        except Exception:
            body = raw
        return exc.code, body
    except urllib.error.URLError as exc:
        return None, {"error": repr(exc)}
    except OSError as exc:
        return None, {"error": repr(exc)}


def http_stream(url: str, payload: dict[str, Any], timeout: int = 120) -> tuple[int, str]:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")


def read_debug_payload(name: str) -> dict[str, Any]:
    p = DEBUG_DIR / name
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"_debug_read_error": str(exc)}


def project_context(scale: str) -> str:
    file_count = {"small": 8, "medium": 40, "large": 120}[scale]
    parts = [
        "You are reviewing a medium-to-large Python/FastAPI proxy project.",
        "Focus on protocol compatibility, tool-call safety, streaming behavior, and state recovery.",
        "Synthetic file inventory:",
    ]
    for i in range(file_count):
        parts.append(
            f"- module_{i:03d}.py: handles route group {i % 9}, "
            f"state table {i % 5}, compatibility branch {i % 7}."
        )
    parts.append("Return a concise risk summary with the top 3 compatibility concerns.")
    return "\n".join(parts)


def function_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "name": "read_project_file",
        "description": "Read a project file by relative path.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "max_lines": {"type": "integer"},
            },
            "required": ["path"],
            "additionalProperties": False,
        },
    }


def web_search_tool() -> dict[str, Any]:
    return {"type": "web_search"}


def image_generation_tool() -> dict[str, Any]:
    return {"type": "image_generation"}


def supported_namespace_tool() -> dict[str, Any]:
    return {"type": "namespace", "namespace": "deepseek_proxy_account"}


def unsupported_tools() -> list[dict[str, Any]]:
    return [
        {"type": "namespace", "namespace": "unknown_namespace_for_stress_test"},
    ]


def build_cases(scale: str) -> list[tuple[str, dict[str, Any], bool]]:
    ctx = project_context(scale)
    return [
        (
            "basic_text",
            {
                "model": "deepseek-v4-pro",
                "input": "Reply exactly: ok",
            },
            False,
        ),
        (
            "medium_project_context",
            {
                "model": "deepseek-v4-pro",
                "input": ctx,
            },
            False,
        ),
        (
            "request_model_flash",
            {
                "model": "deepseek-v4-flash",
                "input": "Reply exactly: flash-ok",
            },
            False,
        ),
        (
            "function_tool",
            {
                "model": "deepseek-v4-pro",
                "input": "Use available tools only if needed. Reply exactly: tool-ok",
                "tools": [function_tool()],
                "tool_choice": "auto",
                "parallel_tool_calls": True,
            },
            False,
        ),
        (
            "web_search_tool",
            {
                "model": "deepseek-v4-pro",
                "input": "Reply exactly: web-search-ok",
                "tools": [web_search_tool()],
                "tool_choice": "auto",
            },
            False,
        ),
        (
            "image_generation_tool",
            {
                "model": "deepseek-v4-pro",
                "input": "Reply exactly: image-generation-ok",
                "tools": [image_generation_tool()],
                "tool_choice": "auto",
            },
            False,
        ),
        (
            "supported_namespace_tool",
            {
                "model": "deepseek-v4-pro",
                "input": "Use the proxy_status tool if useful, then reply exactly: namespace-ok",
                "tools": [supported_namespace_tool()],
                "tool_choice": "auto",
            },
            False,
        ),
        (
            "unsupported_namespace_tool",
            {
                "model": "deepseek-v4-pro",
                "input": "Reply exactly: unsupported-ok",
                "tools": unsupported_tools(),
                "tool_choice": "auto",
            },
            False,
        ),
        (
            "responses_options",
            {
                "model": "deepseek-v4-pro",
                "input": "Return a JSON object exactly like {\\\"status\\\":\\\"options-ok\\\"}.",
                "max_output_tokens": 64,
                "temperature": 0.2,
                "top_p": 0.9,
                "response_format": {"type": "json_object"},
            },
            False,
        ),
        (
            "reasoning_top_level_xhigh",
            {
                "model": "deepseek-v4-pro",
                "input": "Reply exactly: reasoning-ok",
                "model_reasoning_effort": "xhigh",
            },
            False,
        ),
        (
            "reasoning_dict_high",
            {
                "model": "deepseek-v4-pro",
                "input": "Reply exactly: reasoning-dict-ok",
                "reasoning": {"effort": "high"},
            },
            False,
        ),
        (
            "stream_basic",
            {
                "model": "deepseek-v4-pro",
                "input": "Reply exactly: stream-ok",
                "stream": True,
            },
            True,
        ),
    ]


def run_case(base_url: str, name: str, payload: dict[str, Any], stream: bool) -> CaseResult:
    DEBUG_DIR.mkdir(exist_ok=True)
    for fn in ["last_responses_payload.json", "last_deepseek_payload.json"]:
        try:
            (DEBUG_DIR / fn).unlink()
        except FileNotFoundError:
            pass

    url = f"{base_url.rstrip('/')}/responses"
    status: int | None = None
    body: Any = None
    error: str | None = None
    response_id: str | None = None
    output_preview: str | None = None

    try:
        if stream:
            status, text = http_stream(url, payload)
            body = text
            output_preview = text[:300]
        else:
            status, body = http_json("POST", url, payload)
            if isinstance(body, dict):
                response_id = body.get("id")
                output_preview = (body.get("output_text") or json.dumps(body)[:300])[:300]
            else:
                output_preview = str(body)[:300]
    except Exception as exc:
        error = repr(exc)

    request_payload = read_debug_payload("last_responses_payload.json")
    upstream = read_debug_payload("last_deepseek_payload.json")
    compat_warnings_raw = read_debug_payload("last_compat_warnings.json")
    compat_warnings = compat_warnings_raw if isinstance(compat_warnings_raw, list) else []

    return CaseResult(
        name=name,
        base_url=base_url,
        status=status,
        ok=bool(status and 200 <= status < 300 and not error),
        error=error if error else None if status and 200 <= status < 300 else json.dumps(body, ensure_ascii=False)[:1000],
        response_id=response_id,
        output_preview=output_preview,
        request_keys=sorted(request_payload.keys()),
        upstream_keys=sorted(upstream.keys()),
        upstream_model=upstream.get("model"),
        upstream_thinking=upstream.get("thinking"),
        upstream_reasoning_effort=upstream.get("reasoning_effort"),
        upstream_tools_count=len(upstream.get("tools") or []),
        upstream_has_response_format="response_format" in upstream,
        upstream_has_temperature="temperature" in upstream,
        upstream_has_top_p="top_p" in upstream,
        upstream_has_max_tokens="max_tokens" in upstream,
        compat_warning_count=len(compat_warnings),
        compat_warning_kinds=[
            str(item.get("kind")) for item in compat_warnings if isinstance(item, dict)
        ],
    )


def root_url_from_base_url(base_url: str) -> str:
    base = base_url.rstrip("/")
    if base.endswith("/v1"):
        return base[:-3]
    return base


def run_previous_response_case(base_url: str) -> list[CaseResult]:
    first_payload = {
        "model": "deepseek-v4-pro",
        "input": "Reply exactly: first-ok",
    }
    first = run_case(base_url, "previous_response_seed", first_payload, False)
    if not first.response_id:
        return [first]

    second_payload = {
        "model": "deepseek-v4-pro",
        "previous_response_id": first.response_id,
        "input": "Continue and reply exactly: second-ok",
    }
    second = run_case(base_url, "previous_response_continue", second_payload, False)
    return [first, second]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stable-url", default="http://127.0.0.1:8000/v1")
    parser.add_argument("--thinking-url", default="http://127.0.0.1:8001/v1")
    parser.add_argument("--profile", choices=["stable", "thinking", "both"], default="both")
    parser.add_argument("--scale", choices=["small", "medium", "large"], default="medium")
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    urls: list[tuple[str, str]] = []
    if args.profile in {"stable", "both"}:
        urls.append(("stable", args.stable_url))
    if args.profile in {"thinking", "both"}:
        urls.append(("thinking", args.thinking_url))

    results: list[dict[str, Any]] = []
    started_at = int(time.time())

    for profile, base_url in urls:
        print(f"===== {profile} {base_url} =====")
        status, health = http_json("GET", f"{root_url_from_base_url(base_url)}/healthz")
        print(f"healthz status={status} body={health}")

        for name, payload, stream in build_cases(args.scale):
            result = run_case(base_url, f"{profile}:{name}", payload, stream)
            results.append(result.__dict__)
            print(
                f"{result.name}: status={result.status} ok={result.ok} "
                f"model={result.upstream_model} effort={result.upstream_reasoning_effort} "
                f"tools={result.upstream_tools_count} warnings={result.compat_warning_count} upstream_keys={result.upstream_keys}"
            )

        for result in run_previous_response_case(base_url):
            result.name = f"{profile}:{result.name}"
            results.append(result.__dict__)
            print(
                f"{result.name}: status={result.status} ok={result.ok} "
                f"id={result.response_id} model={result.upstream_model}"
            )

    report = {
        "created_at": started_at,
        "scale": args.scale,
        "results": results,
        "summary": {
            "total": len(results),
            "ok": sum(1 for r in results if r["ok"]),
            "failed": sum(1 for r in results if not r["ok"]),
            "dropped_or_unmapped_fields": [
                "response_format" if not any(r["upstream_has_response_format"] for r in results) else None,
                "temperature" if not any(r["upstream_has_temperature"] for r in results) else None,
                "top_p" if not any(r["upstream_has_top_p"] for r in results) else None,
                "max_output_tokens->max_tokens" if not any(r["upstream_has_max_tokens"] for r in results) else None,
            ],
        },
    }
    report["summary"]["dropped_or_unmapped_fields"] = [
        x for x in report["summary"]["dropped_or_unmapped_fields"] if x
    ]

    out = Path(args.output) if args.output else DEBUG_DIR / f"stress_report_{started_at}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"===== REPORT =====")
    print(out)
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))

    return 0 if report["summary"]["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
