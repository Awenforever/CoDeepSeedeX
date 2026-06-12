#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urljoin


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


DEFAULT_PROVIDERS = (
    "deepseek",
    "qwen-singapore",
    "kimi",
    "zhipu",
    "zai",
    "custom",
)

PROVIDER_KEY_ENVS = {
    "deepseek": ("COX_LIVE_DS_KEY", "COX_MODEL_API_KEY"),
    "qwen-singapore": ("COX_LIVE_QWEN_API_KEY",),
    "qwen-beijing": ("COX_LIVE_QWEN_API_KEY",),
    "qwen-us": ("COX_LIVE_QWEN_API_KEY",),
    "kimi": ("COX_LIVE_KIMI_API_KEY",),
    "zhipu": ("COX_LIVE_ZHIPU_API_KEY",),
    "zhipu-coding": ("COX_LIVE_ZHIPU_API_KEY",),
    "zai": ("COX_LIVE_ZAI_API_KEY",),
    "zai-coding": ("COX_LIVE_ZAI_API_KEY",),
    "custom": ("COX_LIVE_CUSTOM_API_KEY",),
}

PROVIDER_BASE_URL_ENVS = {
    "deepseek": ("COX_LIVE_DS_URL", "COX_MODEL_BASE_URL"),
    "qwen-singapore": ("COX_LIVE_QWEN_BASE_URL",),
    "qwen-beijing": ("COX_LIVE_QWEN_BASE_URL",),
    "qwen-us": ("COX_LIVE_QWEN_BASE_URL",),
    "kimi": ("COX_LIVE_KIMI_BASE_URL",),
    "zhipu": ("COX_LIVE_ZHIPU_BASE_URL",),
    "zhipu-coding": ("COX_LIVE_ZHIPU_BASE_URL",),
    "zai": ("COX_LIVE_ZAI_BASE_URL",),
    "zai-coding": ("COX_LIVE_ZAI_BASE_URL",),
    "custom": ("COX_LIVE_CUSTOM_BASE_URL",),
}

PROVIDER_MODEL_ENVS = {
    "deepseek": ("COX_LIVE_DS_CHAT_MODEL", "COX_MODEL_NAME"),
    "qwen-singapore": ("COX_LIVE_QWEN_MODEL",),
    "qwen-beijing": ("COX_LIVE_QWEN_MODEL",),
    "qwen-us": ("COX_LIVE_QWEN_MODEL",),
    "kimi": ("COX_LIVE_KIMI_MODEL",),
    "zhipu": ("COX_LIVE_ZHIPU_MODEL",),
    "zhipu-coding": ("COX_LIVE_ZHIPU_MODEL",),
    "zai": ("COX_LIVE_ZAI_MODEL",),
    "zai-coding": ("COX_LIVE_ZAI_MODEL",),
    "custom": ("COX_LIVE_CUSTOM_MODEL",),
}


@dataclass(frozen=True)
class ResolvedSecret:
    value: str | None
    env_name: str | None


def _first_env(names: tuple[str, ...]) -> ResolvedSecret:
    for name in names:
        value = os.environ.get(name)
        if value:
            return ResolvedSecret(value=value, env_name=name)
    return ResolvedSecret(value=None, env_name=None)


def _first_env_value(names: tuple[str, ...]) -> tuple[str | None, str | None]:
    resolved = _first_env(names)
    return resolved.value, resolved.env_name


def _join_url(base_url: str, path: str) -> str:
    base = base_url.rstrip("/") + "/"
    return urljoin(base, path.lstrip("/"))


def _request_json(
    *,
    method: str,
    url: str,
    api_key: str,
    payload: Mapping[str, Any] | None = None,
    timeout_seconds: float = 20.0,
    insecure_tls: bool = False,
) -> dict[str, Any]:
    data = None
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
        "User-Agent": "CodeXchange-provider-live-smoke/1",
    }
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
    context = ssl._create_unverified_context() if insecure_tls else None
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds, context=context) as response:
            raw = response.read(512_000)
            elapsed_ms = int((time.monotonic() - started) * 1000)
            parsed: Any
            try:
                parsed = json.loads(raw.decode("utf-8", errors="replace")) if raw else None
            except json.JSONDecodeError:
                parsed = None
            return {
                "ok": 200 <= int(response.status) < 300,
                "status_code": int(response.status),
                "elapsed_ms": elapsed_ms,
                "body_kind": type(parsed).__name__ if parsed is not None else "empty_or_non_json",
                "top_level_keys": sorted(parsed.keys())[:20] if isinstance(parsed, dict) else [],
                "error": "",
            }
    except urllib.error.HTTPError as exc:
        raw = exc.read(200_000)
        elapsed_ms = int((time.monotonic() - started) * 1000)
        parsed_error: Any
        try:
            parsed_error = json.loads(raw.decode("utf-8", errors="replace")) if raw else None
        except json.JSONDecodeError:
            parsed_error = None
        return {
            "ok": False,
            "status_code": int(exc.code),
            "elapsed_ms": elapsed_ms,
            "body_kind": type(parsed_error).__name__ if parsed_error is not None else "empty_or_non_json",
            "top_level_keys": sorted(parsed_error.keys())[:20] if isinstance(parsed_error, dict) else [],
            "error": "http_error",
        }
    except Exception as exc:
        elapsed_ms = int((time.monotonic() - started) * 1000)
        return {
            "ok": False,
            "status_code": None,
            "elapsed_ms": elapsed_ms,
            "body_kind": "none",
            "top_level_keys": [],
            "error": f"{type(exc).__name__}:{str(exc)[:180]}",
        }


def _provider_config(provider: str) -> dict[str, Any]:
    cli = importlib.import_module("codexchange_proxy.cli")
    return dict(cli._model_api_provider_config(provider))


def _chat_payload(model: str) -> dict[str, Any]:
    return {
        "model": model,
        "messages": [
            {"role": "user", "content": "Reply exactly: ok"}
        ],
        "max_tokens": 8,
        "temperature": 0,
        "stream": False,
    }


def run_provider(
    provider: str,
    *,
    include_chat: bool,
    timeout_seconds: float,
    insecure_tls: bool,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "provider": provider,
        "configured": False,
        "key_env": None,
        "base_url_env": None,
        "model_env": None,
        "base_url": None,
        "model": None,
        "adapter_provider_id": None,
        "adapter_family": None,
        "wire_protocol": None,
        "validation_method": None,
        "validation_path": None,
        "validation": {"ok": False, "skipped": True, "reason": "not_started"},
        "chat": {"ok": False, "skipped": True, "reason": "not_requested"},
    }

    try:
        config = _provider_config(provider)
    except Exception as exc:
        result["validation"] = {
            "ok": False,
            "skipped": True,
            "reason": f"provider_config_error:{type(exc).__name__}:{str(exc)[:180]}",
        }
        result["chat"] = {"ok": False, "skipped": True, "reason": "provider_config_error"}
        return result

    base_url_override, base_url_env = _first_env_value(PROVIDER_BASE_URL_ENVS.get(provider, ()))
    model_override, model_env = _first_env_value(PROVIDER_MODEL_ENVS.get(provider, ()))
    key = _first_env(PROVIDER_KEY_ENVS.get(provider, ()))

    base_url = str(base_url_override or config.get("base_url") or "").rstrip("/")
    model = str(model_override or config.get("model") or "")

    result.update(
        {
            "configured": bool(key.value),
            "key_env": key.env_name,
            "base_url_env": base_url_env,
            "model_env": model_env,
            "base_url": base_url,
            "model": model,
            "adapter_provider_id": config.get("adapter_provider_id"),
            "adapter_family": config.get("adapter_family"),
            "wire_protocol": config.get("wire_protocol"),
            "validation_method": config.get("validation_method"),
            "validation_path": config.get("validation_path"),
        }
    )

    if not key.value:
        result["validation"] = {"ok": False, "skipped": True, "reason": "no_api_key"}
        result["chat"] = {"ok": False, "skipped": True, "reason": "no_api_key"}
        return result

    if not base_url:
        result["validation"] = {"ok": False, "skipped": True, "reason": "missing_base_url"}
        result["chat"] = {"ok": False, "skipped": True, "reason": "missing_base_url"}
        return result

    validation_path = str(config.get("validation_path") or "/models")
    validation_method = str(config.get("validation_http_method") or "GET")
    result["validation"] = _request_json(
        method=validation_method,
        url=_join_url(base_url, validation_path),
        api_key=key.value,
        timeout_seconds=timeout_seconds,
        insecure_tls=insecure_tls,
    )

    if include_chat:
        if not model:
            result["chat"] = {"ok": False, "skipped": True, "reason": "missing_model"}
        else:
            result["chat"] = _request_json(
                method="POST",
                url=_join_url(base_url, "/chat/completions"),
                api_key=key.value,
                payload=_chat_payload(model),
                timeout_seconds=timeout_seconds,
                insecure_tls=insecure_tls,
            )

    return result


def build_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    validation_ok = sum(1 for item in results if item.get("validation", {}).get("ok") is True)
    validation_skipped = sum(1 for item in results if item.get("validation", {}).get("skipped") is True)
    chat_ok = sum(1 for item in results if item.get("chat", {}).get("ok") is True)
    chat_skipped = sum(1 for item in results if item.get("chat", {}).get("skipped") is True)
    return {
        "providers_total": len(results),
        "validation_ok": validation_ok,
        "validation_skipped": validation_skipped,
        "validation_failed": len(results) - validation_ok - validation_skipped,
        "chat_ok": chat_ok,
        "chat_skipped": chat_skipped,
        "chat_failed": len(results) - chat_ok - chat_skipped,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run provider live smoke checks without printing API keys.")
    parser.add_argument("--providers", nargs="*", default=list(DEFAULT_PROVIDERS))
    parser.add_argument("--chat", action="store_true", help="Also run a minimal chat completion smoke.")
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--output", default="")
    parser.add_argument("--insecure-tls", action="store_true")
    parser.add_argument(
        "--allow-provider-failures",
        action="store_true",
        help="Return success when evidence is written even if one or more configured providers fail.",
    )
    args = parser.parse_args(argv)

    results = [
        run_provider(
            provider,
            include_chat=args.chat,
            timeout_seconds=args.timeout,
            insecure_tls=args.insecure_tls,
        )
        for provider in args.providers
    ]

    payload = {
        "stage": "p3.0a5-provider-live-smoke-matrix",
        "chat_requested": bool(args.chat),
        "summary": build_summary(results),
        "results": results,
    }

    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    print(text)
    failed = payload["summary"]["validation_failed"] + payload["summary"]["chat_failed"]
    if failed and args.allow_provider_failures:
        return 0
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
