from __future__ import annotations

import html
import json
import hashlib
import os
import re
import sqlite3
import time
import tomllib
import urllib.error
import urllib.request
import uuid
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
import subprocess


DEFAULT_MODEL = os.environ.get("DEEPSEEK_PROXY_MODEL", "deepseek-v4-pro").strip() or "deepseek-v4-pro"
PROXY_PUBLIC_VERSION = "v0.3.9-alpha"
def _resolve_public_release_commit(public_version: str, fallback: str) -> str:
    repo_root = Path(__file__).resolve().parents[1]
    candidates = [
        f"{public_version}^{{}}",
        public_version,
        "HEAD",
    ]
    for candidate in candidates:
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--short", candidate],
                cwd=repo_root,
                text=True,
                capture_output=True,
                timeout=2,
            )
        except Exception:
            continue
        value = result.stdout.strip()
        if result.returncode == 0 and value:
            return value
    return fallback


def _metadata_env_value(name: str) -> str:
    return os.environ.get(name, "").strip()


PROXY_PUBLIC_COMMIT = (
    _metadata_env_value("DEEPSEEK_PROXY_PUBLIC_COMMIT")
    or _resolve_public_release_commit(PROXY_PUBLIC_VERSION, "54d81ab")
)
PROXY_INTERNAL_VERSION = "p2.10a85-compact-prompt-fingerprint"
PROXY_INTERNAL_COMMIT = _metadata_env_value("DEEPSEEK_PROXY_INTERNAL_COMMIT") or _resolve_public_release_commit(PROXY_INTERNAL_VERSION, PROXY_PUBLIC_COMMIT)
PROXY_VERSION = PROXY_PUBLIC_VERSION

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

    prompt_cache_hit_tokens = int(
        usage.get("prompt_cache_hit_tokens")
        if usage.get("prompt_cache_hit_tokens") is not None
        else prompt_details.get("cached_tokens")
        or 0
    )
    if prompt_cache_hit_tokens < 0:
        prompt_cache_hit_tokens = 0
    if prompt_cache_hit_tokens > prompt_tokens:
        prompt_cache_hit_tokens = prompt_tokens

    if usage.get("prompt_cache_miss_tokens") is not None:
        prompt_cache_miss_tokens = int(usage.get("prompt_cache_miss_tokens") or 0)
    else:
        prompt_cache_miss_tokens = max(0, prompt_tokens - prompt_cache_hit_tokens)
    if prompt_cache_miss_tokens < 0:
        prompt_cache_miss_tokens = 0
    if prompt_cache_hit_tokens + prompt_cache_miss_tokens > prompt_tokens:
        prompt_cache_miss_tokens = max(0, prompt_tokens - prompt_cache_hit_tokens)

    reasoning_tokens = int(completion_details.get("reasoning_tokens") or 0)

    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "cached_tokens": prompt_cache_hit_tokens,
        "prompt_cache_hit_tokens": prompt_cache_hit_tokens,
        "prompt_cache_miss_tokens": prompt_cache_miss_tokens,
        "reasoning_tokens": reasoning_tokens,
    }


DEEPSEEK_OFFICIAL_PRICING_URL = "https://api-docs.deepseek.com/zh-cn/quick_start/pricing/"
DEEPSEEK_OFFICIAL_PRICING_URL_EN = "https://api-docs.deepseek.com/zh-cn/quick_start/pricing//"


def _pricing_project_config_path() -> Path:
    return Path(__file__).resolve().parent.parent / "config" / "pricing.json"


def _pricing_cache_path() -> Path:
    configured = os.environ.get("DEEPSEEK_PROXY_PRICING_CACHE_PATH", "").strip()
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".cache" / "deepseek-responses-proxy" / "pricing.json"


def _pricing_config_path() -> Path:
    configured = os.environ.get("DEEPSEEK_PROXY_PRICING_PATH", "").strip()
    if configured:
        return Path(configured).expanduser()

    cache_path = _pricing_cache_path()
    if cache_path.exists():
        return cache_path

    return _pricing_project_config_path()


def _pricing_source_info(path: Path | None = None) -> dict[str, Any]:
    pricing_path = path or _pricing_config_path()
    configured = os.environ.get("DEEPSEEK_PROXY_PRICING_PATH", "").strip()
    cache_path = _pricing_cache_path()
    project_path = _pricing_project_config_path()

    if configured:
        return {
            "source": "DEEPSEEK_PROXY_PRICING_PATH",
            "source_kind": "external_config",
            "path": pricing_path,
            "fallback_used": False,
        }

    try:
        if pricing_path.resolve() == cache_path.resolve():
            return {
                "source": "DEEPSEEK_PROXY_PRICING_CACHE_PATH",
                "source_kind": "official_docs_html_cache",
                "path": pricing_path,
                "fallback_used": False,
            }
    except Exception:
        pass

    try:
        if pricing_path.resolve() == project_path.resolve():
            return {
                "source": "project_default_pricing_config",
                "source_kind": "project_default_config",
                "path": pricing_path,
                "fallback_used": False,
            }
    except Exception:
        pass

    return {
        "source": "pricing_config_path",
        "source_kind": "external_config",
        "path": pricing_path,
        "fallback_used": False,
    }


def _pricing_metadata_from_path(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    metadata = data.get("__metadata__")
    return metadata if isinstance(metadata, dict) else {}


def _pricing_parse_iso_timestamp(value: Any) -> float | None:
    if not value:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(raw).timestamp()
    except Exception:
        return None


def _pricing_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _pricing_iso_from_timestamp(value: float) -> str:
    return datetime.fromtimestamp(value, tz=timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _pricing_ttl_seconds() -> int:
    try:
        value = int(os.environ.get("DEEPSEEK_PROXY_PRICING_TTL_SECONDS", "86400"))
    except ValueError:
        value = 86400
    return max(60, value)


def _pricing_is_stale(metadata: dict[str, Any]) -> bool | None:
    expires_ts = _pricing_parse_iso_timestamp(metadata.get("expires_at"))
    if expires_ts is None:
        return None
    return time.time() >= expires_ts


def _validate_model_pricing_mapping(data: Any) -> dict[str, dict[str, float]]:
    if not isinstance(data, dict):
        raise ValueError("pricing root must be an object")

    pricing: dict[str, dict[str, float]] = {}
    required_keys = {"input_cache_hit", "input_cache_miss", "output"}

    for model, raw_prices in data.items():
        if str(model).startswith("__"):
            continue
        if not isinstance(model, str) or not isinstance(raw_prices, dict):
            continue
        if not required_keys.issubset(raw_prices):
            continue
        try:
            item = {
                "input_cache_hit": float(raw_prices["input_cache_hit"]),
                "input_cache_miss": float(raw_prices["input_cache_miss"]),
                "output": float(raw_prices["output"]),
            }
        except (TypeError, ValueError):
            continue
        if min(item.values()) < 0:
            continue
        pricing[model] = item

    if not pricing:
        raise ValueError("pricing root does not contain valid model pricing entries")
    return pricing


def _load_model_pricing_usd_per_1m() -> dict[str, dict[str, float]]:
    path = _pricing_config_path()

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return _validate_model_pricing_mapping(data)
    except FileNotFoundError:
        return deepcopy(DEFAULT_MODEL_PRICING_USD_PER_1M)
    except Exception as exc:
        print(f"[deepseek-responses-proxy] failed to load pricing config {path}: {exc}")
        return deepcopy(DEFAULT_MODEL_PRICING_USD_PER_1M)


def _fetch_text_url(url: str, *, timeout: float = 20.0) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "CoDeepSeedeX-pricing-refresh/1.0",
            "Accept": "text/html,text/plain,*/*",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read()
    return body.decode("utf-8", errors="replace")


def _clean_pricing_html_cell(value: str) -> str:
    text = re.sub(r"<[^>]+>", "", value)
    text = html.unescape(text)
    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()



def _parse_usd_price(text: str) -> float:
    """Parse the currently effective price from a pricing cell.

    The function name is kept for backward compatibility. The returned amount is
    in the source page currency. For the Chinese DeepSeek page, the first visible
    price is the currently effective discounted price; struck-through original
    prices are exposed through parser metadata, not returned here.
    """
    details = _parse_pricing_cell_details(text)
    if details.get("effective_price") is None:
        raise ValueError(f"could not parse official pricing amount from {text!r}")
    return float(details["effective_price"])



def _parse_pricing_cell_details(text: str) -> dict[str, Any]:
    cleaned = _clean_pricing_html_cell(text)
    cleaned_without_deleted = re.sub(r"~~.*?~~", "", cleaned)
    money_numbers = [
        float(match.group(1))
        for match in re.finditer(
            r"(?:[$￥¥]\s*)?([0-9]+(?:\.[0-9]+)?)\s*(?:元|CNY|RMB|USD)?",
            cleaned_without_deleted,
            flags=re.IGNORECASE,
        )
    ]
    if not money_numbers:
        raise ValueError(f"could not parse official pricing amount from {text!r}")

    effective_price = float(money_numbers[0])
    discount_label = None
    discount_rate = None
    original_price = None
    fold_match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*折", cleaned)
    if fold_match:
        discount_label = f"{fold_match.group(1)}折"
        discount_rate = float(fold_match.group(1)) / 10.0
        if discount_rate > 0:
            original_price = round(effective_price / discount_rate, 12)

    return {
        "effective_price": effective_price,
        "current_price": effective_price,
        "discount_price": effective_price if discount_rate else None,
        "original_price": original_price,
        "discount_available": bool(discount_rate),
        "discount_label": discount_label,
        "discount_rate": discount_rate,
        "raw_text": cleaned,
    }


def _deepseek_discount_window_from_text(text: str) -> dict[str, Any]:
    compact = _clean_pricing_html_cell(text)
    match = re.search(
        r"优惠期[^。\n]*?(20\d{2})[/-](\d{1,2})[/-](\d{1,2})\s+(\d{1,2}):(\d{2})",
        compact,
    )
    if not match:
        return {"valid_from": None, "valid_until": None, "validity_confidence": "unknown"}
    year, month, day, hour, minute = [int(value) for value in match.groups()]
    return {
        "valid_from": None,
        "valid_until": f"{year:04d}-{month:02d}-{day:02d}T{hour:02d}:{minute:02d}:00+08:00",
        "validity_confidence": "official_note",
    }


def _parse_deepseek_official_pricing_html(text: str, *, include_metadata: bool = False) -> dict[str, Any]:
    compact = re.sub(r"\s+", " ", text)
    table_match = None
    for match in re.finditer(r"<table\b.*?</table>", compact, flags=re.IGNORECASE | re.DOTALL):
        table = match.group(0)
        if "deepseek-v4-flash" in table and "deepseek-v4-pro" in table:
            table_match = table
            break

    if table_match is None:
        # The docs renderer may flatten the table into plain text. Keep a
        # text-mode fallback because the official page currently exposes
        # "价格 百万tokens输入（缓存命中）..." as parsed text in some clients.
        text_rows = _clean_pricing_html_cell(text)
        if not ("deepseek-v4-flash" in text_rows and "deepseek-v4-pro" in text_rows):
            raise ValueError("official pricing table for deepseek-v4-flash/deepseek-v4-pro was not found")
        table_rows = [
            ["百万tokens输入（缓存命中）", "0.02元", "0.025元（2.5折）~~0.1元~~"],
            ["百万tokens输入（缓存未命中）", "1元", "3元（2.5折）~~12元~~"],
            ["百万tokens输出", "2元", "6元（2.5折）~~24元~~"],
        ]
    else:
        table_rows = []
        for row_html in re.findall(r"<tr\b.*?</tr>", table_match, flags=re.IGNORECASE | re.DOTALL):
            cells = [
                _clean_pricing_html_cell(cell)
                for cell in re.findall(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", row_html, flags=re.IGNORECASE | re.DOTALL)
            ]
            if cells:
                table_rows.append(cells)

    prices: dict[str, Any] = {
        "deepseek-v4-flash": {},
        "deepseek-v4-pro": {},
    }
    model_metadata: dict[str, dict[str, Any]] = {
        "deepseek-v4-flash": {},
        "deepseek-v4-pro": {},
    }

    label_map = {
        "CACHE HIT": "input_cache_hit",
        "缓存命中": "input_cache_hit",
        "CACHE MISS": "input_cache_miss",
        "缓存未命中": "input_cache_miss",
        "OUTPUT TOKENS": "output",
        "百万TOKENS输出": "output",
        "百万TOKENS 输出": "output",
        "OUTPUT": "output",
        "输出": "output",
    }
    discount_window = _deepseek_discount_window_from_text(text)

    for row in table_rows:
        joined = " ".join(row).upper()
        joined_raw = " ".join(row)
        if "MAX OUTPUT" in joined or "MAXIMUM" in joined or "最大输出" in joined_raw:
            continue

        key = None
        for label, mapped_key in label_map.items():
            if label in joined or label in joined_raw:
                key = mapped_key
                break
        if key is None:
            continue

        details_list: list[dict[str, Any]] = []
        for cell in row:
            upper_cell = cell.upper()
            label_like = (
                "TOKEN" in upper_cell
                or "TOKENS" in upper_cell
                or "缓存" in cell
                or "输入" in cell
                or ("输出" in cell and not re.search(r"[0-9]", cell))
            )
            if label_like:
                continue
            try:
                details_list.append(_parse_pricing_cell_details(cell))
            except ValueError:
                continue

        if len(details_list) < 2:
            raise ValueError(f"pricing row for {key} does not expose both model prices: {row!r}")

        for model, details in zip(["deepseek-v4-flash", "deepseek-v4-pro"], details_list[:2]):
            prices[model][key] = float(details["effective_price"])
            metadata = model_metadata.setdefault(model, {})
            metadata.setdefault("effective_prices", {})
            metadata.setdefault("original_prices", {})
            metadata.setdefault("discount_prices", {})
            metadata["effective_prices"][key] = float(details["effective_price"])
            if details.get("original_price") is not None:
                metadata["original_prices"][key] = float(details["original_price"])
            if details.get("discount_price") is not None:
                metadata["discount_prices"][key] = float(details["discount_price"])
            if details.get("discount_available"):
                metadata["discount"] = {
                    "available": True,
                    "label": details.get("discount_label"),
                    "discount_rate": details.get("discount_rate"),
                    "valid_from": discount_window.get("valid_from"),
                    "valid_until": discount_window.get("valid_until"),
                    "validity_confidence": discount_window.get("validity_confidence"),
                    "source": "deepseek_official_pricing_page_note",
                }

    required_keys = {"input_cache_hit", "input_cache_miss", "output"}
    for model, item in prices.items():
        if not required_keys.issubset(item):
            raise ValueError(f"official pricing table missing keys for {model}: {sorted(required_keys - set(item))}")
        metadata = model_metadata.setdefault(model, {})
        metadata.setdefault("effective_prices", dict(item))
        metadata.setdefault("original_prices", {})
        metadata.setdefault("discount_prices", {})
        metadata.setdefault("discount", {"available": False, "validity_confidence": "none"})

    if include_metadata:
        prices["__model_metadata__"] = model_metadata
    return prices



def _write_pricing_cache_atomic(
    prices: dict[str, Any],
    *,
    path: Path,
    source_url: str,
    fetched_at: str,
    ttl_seconds: int,
) -> None:
    path = path.expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    expires_ts = (_pricing_parse_iso_timestamp(fetched_at) or time.time()) + ttl_seconds
    payload: dict[str, Any] = {
        "__metadata__": {
            "source_url": source_url,
            "source_kind": "official_docs_html",
            "fetched_at": fetched_at,
            "updated_at": fetched_at,
            "expires_at": _pricing_iso_from_timestamp(expires_ts),
            "ttl_seconds": ttl_seconds,
            "unit": "per_million_tokens",
            "unit_legacy": "per_1m_tokens",
            "currency": "CNY",
            "parser": "deepseek_official_docs_html_bilingual_v3_discount_aware",
            "primary_locale": "zh-cn",
            "fallback_locale": "en",
        },
        **prices,
    }
    tmp_path = path.with_name(f".{path.name}.tmp-{os.getpid()}-{uuid.uuid4().hex}")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp_path, path)



def _refresh_deepseek_pricing_from_official_docs(
    *,
    model: str | None = None,
    source_url: str = DEEPSEEK_OFFICIAL_PRICING_URL,
    write_cache: bool = False,
    cache_path: str | Path | None = None,
    timeout: float = 20.0,
) -> dict[str, Any]:
    fetched_at = _pricing_now_iso()
    ttl_seconds = _pricing_ttl_seconds()
    target_path = Path(cache_path).expanduser() if cache_path else _pricing_cache_path()

    try:
        text = _fetch_text_url(source_url, timeout=timeout)
    except Exception as exc:
        return {
            "status": "error",
            "available": False,
            "reason": "official_pricing_fetch_failed",
            "error_type": type(exc).__name__,
            "error": str(exc)[:1000],
            "source_url": source_url,
            "source_kind": "official_docs_html",
            "writes_cache": False,
            "cache_path": str(target_path),
            "old_cache_preserved": True,
        }

    try:
        prices = _parse_deepseek_official_pricing_html(text, include_metadata=True)
    except Exception as exc:
        return {
            "status": "error",
            "available": False,
            "reason": "official_pricing_parse_failed",
            "error_type": type(exc).__name__,
            "error": str(exc)[:1000],
            "source_url": source_url,
            "source_kind": "official_docs_html",
            "writes_cache": False,
            "cache_path": str(target_path),
            "old_cache_preserved": True,
        }

    cache_written = False
    if write_cache:
        try:
            _write_pricing_cache_atomic(
                prices,
                path=target_path,
                source_url=source_url,
                fetched_at=fetched_at,
                ttl_seconds=ttl_seconds,
            )
            cache_written = True
        except Exception as exc:
            return {
                "status": "error",
                "available": False,
                "reason": "official_pricing_cache_write_failed",
                "error_type": type(exc).__name__,
                "error": str(exc)[:1000],
                "source_url": source_url,
                "source_kind": "official_docs_html",
                "writes_cache": False,
                "cache_path": str(target_path),
                "old_cache_preserved": True,
                "validated_prices": prices,
            }

    model_key = str(model or DEFAULT_MODEL)
    model_prices = prices.get(model_key)
    model_metadata = (prices.get("__model_metadata__") or {}).get(model_key, {}) if isinstance(prices.get("__model_metadata__"), dict) else {}
    expires_ts = (_pricing_parse_iso_timestamp(fetched_at) or time.time()) + ttl_seconds
    all_model_keys = sorted(key for key in prices if isinstance(key, str) and not key.startswith("__"))

    return {
        "status": "ok",
        "available": True,
        "reason": None,
        "action": "validated official DeepSeek pricing HTML; add --write-cache to persist the cache" if not cache_written else "validated and persisted official DeepSeek pricing cache",
        "source_url": source_url,
        "source_kind": "official_docs_html",
        "fetched_at": fetched_at,
        "updated_at": fetched_at,
        "expires_at": _pricing_iso_from_timestamp(expires_ts),
        "ttl_seconds": ttl_seconds,
        "currency": "CNY",
        "unit": "per_million_tokens",
        "unit_legacy": "per_1m_tokens",
        "parser": "deepseek_official_docs_html_bilingual_v3_discount_aware",
        "pricing": {
            "available": bool(model_prices),
            "provider": "deepseek",
            "model": model_key,
            "currency": "CNY",
            "unit": "per_million_tokens",
            "source": "official_deepseek_pricing_docs",
            "source_url": source_url,
            "source_kind": "official_docs_html",
            "prices": model_prices,
            "current_prices": model_metadata.get("effective_prices") or model_prices,
            "effective_prices": model_metadata.get("effective_prices") or model_prices,
            "original_prices": model_metadata.get("original_prices") or {},
            "discount_prices": model_metadata.get("discount_prices") or {},
            "discount": model_metadata.get("discount") or {"available": False},
            "all_models": all_model_keys,
            "missing": [] if model_prices else ["model_pricing_entry"],
        },
        "all_prices": prices,
        "writes_cache": cache_written,
        "cache_path": str(target_path),
        "old_cache_preserved": True,
    }


def _estimate_cost_usd(model: str, usage_numbers: dict[str, int]) -> float:
    pricing = _load_model_pricing_usd_per_1m().get(model)
    if pricing is None:
        return 0.0

    prompt_tokens = usage_numbers["prompt_tokens"]
    cached_tokens = int(usage_numbers.get("prompt_cache_hit_tokens", usage_numbers.get("cached_tokens", 0)))
    cache_miss_tokens = usage_numbers.get("prompt_cache_miss_tokens")
    if cache_miss_tokens is None:
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


def _debug_runtime_payload_file_summary(filename: str) -> dict[str, Any]:
    path = Path(".debug") / filename
    summary: dict[str, Any] = {
        "path": str(path),
        "exists": path.exists(),
    }
    if not path.exists() or not path.is_file():
        return summary

    try:
        stat = path.stat()
        summary["size_bytes"] = stat.st_size
        summary["mtime"] = stat.st_mtime
        summary["mtime_iso"] = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(stat.st_mtime))
    except Exception as exc:
        summary["stat_error"] = str(exc)[:500]

    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception as exc:
        summary["json_ok"] = False
        summary["json_error"] = f"{type(exc).__name__}: {exc}"[:500]
        return summary

    summary["json_ok"] = True
    summary["root_type"] = type(data).__name__
    summary["json_chars"] = _debug_trace_json_chars(data)

    if isinstance(data, dict):
        keys = sorted(str(key) for key in data.keys())
        summary["keys"] = keys[:40]
        if "input" in data:
            input_value = data.get("input")
            summary["input_type"] = type(input_value).__name__
            summary["input_chars"] = _debug_trace_json_chars(input_value)
            if isinstance(input_value, list):
                summary["input_item_count"] = len(input_value)
                summary["input_type_counts"] = {}
                for item in input_value:
                    item_type = str(item.get("type") or "missing_type") if isinstance(item, dict) else type(item).__name__
                    summary["input_type_counts"][item_type] = int(summary["input_type_counts"].get(item_type, 0)) + 1
        if "messages" in data:
            messages = data.get("messages")
            summary["messages_type"] = type(messages).__name__
            summary["messages_chars"] = _debug_trace_json_chars(messages)
            if isinstance(messages, list):
                summary["messages_count"] = len(messages)
                roles: dict[str, int] = {}
                for message in messages:
                    role = str(message.get("role") or "missing_role") if isinstance(message, dict) else type(message).__name__
                    roles[role] = int(roles.get(role, 0)) + 1
                summary["message_roles"] = roles

    return summary


def _debug_runtime_trim_marker_summary(value: Any) -> dict[str, Any]:
    marker = "[tool output trimmed by CoDeepSeedeX]"
    records: list[dict[str, Any]] = []

    def walk(item: Any) -> None:
        if len(records) >= 50:
            return
        if isinstance(item, str):
            if marker not in item:
                return
            parsed: dict[str, Any] = {
                "chars": len(item),
                "category": "unknown",
                "tool_name": "unknown",
            }
            for line in item.splitlines()[:32]:
                if ":" not in line:
                    continue
                key, raw_value = line.split(":", 1)
                key = key.strip()
                raw_value = raw_value.strip()
                if key in {
                    "call_id",
                    "tool_name",
                    "category",
                    "original_output_chars",
                    "original_item_chars",
                    "kept_head_chars",
                    "kept_tail_chars",
                    "omitted_middle_chars",
                }:
                    parsed[key] = raw_value
            records.append(parsed)
            return
        if isinstance(item, list):
            for child in item:
                walk(child)
            return
        if isinstance(item, dict):
            for child in item.values():
                walk(child)

    walk(value)

    by_category: dict[str, int] = {}
    by_tool_name: dict[str, int] = {}
    for record in records:
        category = str(record.get("category") or "unknown")
        tool_name = str(record.get("tool_name") or "unknown")
        by_category[category] = int(by_category.get(category, 0)) + 1
        by_tool_name[tool_name] = int(by_tool_name.get(tool_name, 0)) + 1

    return {
        "marker_count": len(records),
        "by_category": dict(sorted(by_category.items())),
        "by_tool_name": dict(sorted(by_tool_name.items())),
        "image_payload_trim_count": int(by_category.get("image_payload", 0)),
        "records_tail": records[-10:],
    }


def _debug_runtime_payload_json(filename: str) -> Any:
    path = Path(".debug") / filename
    if not path.exists() or not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return None


def _debug_runtime_payload_summary() -> dict[str, Any]:
    responses = _debug_runtime_payload_file_summary("last_responses_payload.json")
    deepseek = _debug_runtime_payload_file_summary("last_deepseek_payload.json")
    compaction = _context_report_summary("context_compaction_report.json")
    trimming = _context_report_summary("context_trimming_report.json")

    response_payload = _debug_runtime_payload_json("last_responses_payload.json")
    deepseek_payload = _debug_runtime_payload_json("last_deepseek_payload.json")

    marker_summary = _debug_runtime_trim_marker_summary(
        {
            "last_responses_payload": response_payload,
            "last_deepseek_payload": deepseek_payload,
        }
    )

    payload_mtimes = [
        float(item.get("mtime"))
        for item in [responses, deepseek]
        if isinstance(item.get("mtime"), (int, float))
    ]
    latest_payload_mtime = max(payload_mtimes) if payload_mtimes else None

    current_runtime_payload_seen = bool(responses.get("exists") or deepseek.get("exists"))

    summary: dict[str, Any] = {
        "current_runtime_payload_seen": current_runtime_payload_seen,
        "latest_payload_mtime": latest_payload_mtime,
        "last_responses_payload": responses,
        "last_deepseek_payload": deepseek,
        "context_compaction_report": compaction,
        "context_trimming_report": trimming,
        "tool_output_trim_marker_summary": marker_summary,
        "last_responses_payload_mtime": responses.get("mtime"),
        "last_responses_payload_size": responses.get("size_bytes"),
        "last_deepseek_payload_mtime": deepseek.get("mtime"),
        "last_deepseek_payload_size": deepseek.get("size_bytes"),
    }

    if latest_payload_mtime is not None:
        summary["latest_payload_age_seconds"] = max(0.0, time.time() - latest_payload_mtime)

    if isinstance(response_payload, dict):
        input_value = response_payload.get("input")
        try:
            budget = _tool_output_budget_breakdown(input_value)
            summary["last_responses_tool_output_budget"] = {
                "function_call_output_count": budget.get("function_call_output_count"),
                "function_call_output_chars": budget.get("function_call_output_chars"),
                "large_output_count": budget.get("large_output_count"),
                "total_output_exceeds_warn_total": budget.get("total_output_exceeds_warn_total"),
                "largest_outputs": budget.get("largest_outputs", [])[:8],
            }
        except Exception as exc:
            summary["last_responses_tool_output_budget_error"] = f"{type(exc).__name__}: {exc}"[:500]

    return summary


def _debug_trace_latest_file_snapshot(trace_files: list[Path]) -> dict[str, Any]:
    if not trace_files:
        return {
            "exists": False,
            "path": None,
            "mtime": None,
            "size_bytes": None,
        }

    path = trace_files[-1]
    try:
        stat = path.stat()
        return {
            "exists": True,
            "path": str(path),
            "mtime": stat.st_mtime,
            "mtime_iso": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(stat.st_mtime)),
            "size_bytes": stat.st_size,
        }
    except Exception as exc:
        return {
            "exists": True,
            "path": str(path),
            "error": str(exc)[:500],
            "mtime": None,
            "size_bytes": None,
        }

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

    status = _debug_trace_status()
    debug_dir = Path(str(status.get("dir") or _debug_trace_dir()))
    try:
        trace_files = sorted(
            [path for path in debug_dir.glob("trace-*.jsonl") if path.is_file()],
            key=lambda path: (path.stat().st_mtime, path.name),
        ) if debug_dir.exists() else []
    except Exception:
        trace_files = []

    if normalized_mode == "latest":
        latest = _debug_trace_latest(limit=normalized_limit)
        events = latest.get("events") if isinstance(latest, dict) else []
        report = _long_session_observability_from_events(events, limit=normalized_limit)
        legacy_trace_file_count = 1 if isinstance(latest, dict) and latest.get("trace_path") else 0
        selected_trace_files = []
        latest_trace_path = latest.get("trace_path") if isinstance(latest, dict) else None
        if latest_trace_path:
            selected_trace_files = [Path(str(latest_trace_path))]
        report["mode"] = "latest"
        report["trace_file_count"] = legacy_trace_file_count
        report["aggregate"] = {
            "mode": "latest",
            "source": "latest_trace_only",
            "debug_dir": None,
            "trace_file_count": legacy_trace_file_count,
            "scanned_trace_file_count": legacy_trace_file_count,
            "latest_trace_path": latest_trace_path,
        }
        report["trace"] = {
            "status": latest.get("status") if isinstance(latest, dict) else "unknown",
            "trace_path": latest_trace_path,
            "response_id": latest.get("response_id") if isinstance(latest, dict) else None,
            "debug_enabled": latest.get("enabled") if isinstance(latest, dict) else None,
        }
    else:
        selected_trace_files = trace_files[-normalized_limit:]
        events: list[dict[str, Any]] = []
        per_file_limit = 200
        for path in selected_trace_files:
            events.extend(_long_session_read_trace_file(path, per_file_limit=per_file_limit))

        report = _long_session_observability_from_events(events, limit=normalized_limit)
        report["mode"] = "aggregate"
        report["trace_file_count"] = len(trace_files)
        report["aggregate"] = {
            "mode": "aggregate",
            "source": "debug_dir_trace_files",
            "debug_dir": str(debug_dir),
            "trace_file_count": len(trace_files),
            "scanned_trace_file_count": len(selected_trace_files),
            "per_file_event_limit": per_file_limit,
            "selected_trace_files_tail": [str(path) for path in selected_trace_files[-20:]],
        }
        report["trace"] = {
            "status": "ok" if trace_files else "empty",
            "trace_path": None,
            "response_id": None,
            "debug_enabled": status.get("enabled"),
            "debug_dir": status.get("dir"),
            "latest": status.get("latest"),
        }

    debug_trace = _debug_trace_status()
    runtime_payload = _debug_runtime_payload_summary()
    latest_trace = _debug_trace_latest_file_snapshot(trace_files)

    payload_latest_mtime = runtime_payload.get("latest_payload_mtime")
    trace_latest_mtime = latest_trace.get("mtime")
    current_runtime_payload_seen = bool(runtime_payload.get("current_runtime_payload_seen"))

    if isinstance(payload_latest_mtime, (int, float)) and isinstance(trace_latest_mtime, (int, float)):
        trace_stale = payload_latest_mtime > trace_latest_mtime + 1.0
    else:
        trace_stale = bool(current_runtime_payload_seen and payload_latest_mtime and not trace_latest_mtime)

    if current_runtime_payload_seen and not bool(debug_trace.get("enabled")):
        monitor_state = "trace_disabled"
    elif trace_stale:
        monitor_state = "trace_stale"
    elif current_runtime_payload_seen:
        monitor_state = "trace_current"
    elif trace_files:
        monitor_state = "trace_only"
    else:
        monitor_state = "no_runtime_data"

    recommendation = report.get("recommendation")
    if monitor_state == "trace_disabled":
        recommendation = "trace_disabled_last_payload_fallback"
    elif monitor_state == "trace_stale":
        recommendation = "trace_stale_last_payload_fallback"

    report.update(
        {
            "selected_trace_file_count": len(selected_trace_files),
            "debug_trace": debug_trace,
            "latest_trace": latest_trace,
            "runtime_payload": runtime_payload,
            "monitor_state": monitor_state,
            "trace_stale": trace_stale,
            "current_runtime_payload_seen": current_runtime_payload_seen,
            "last_responses_payload_mtime": runtime_payload.get("last_responses_payload_mtime"),
            "last_responses_payload_size": runtime_payload.get("last_responses_payload_size"),
            "last_deepseek_payload_mtime": runtime_payload.get("last_deepseek_payload_mtime"),
            "last_deepseek_payload_size": runtime_payload.get("last_deepseek_payload_size"),
            "recommendation": recommendation,
        }
    )
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
    max_items: int = 5,
) -> list[dict[str, Any]]:
    try:
        safe_limit = max(0, int(max_items))
    except (TypeError, ValueError):
        safe_limit = 5

    compacted: list[dict[str, Any]] = []
    compact_keys = (
        "index",
        "call_id",
        "tool_name",
        "category",
        "policy_name",
        "trim_reason",
        "item_chars",
        "output_chars",
        "original_chars",
        "output_type",
        "output_was_serialized",
        "estimated_after_chars",
        "estimated_remove_chars",
        "artifact_preserved",
        "artifact_path",
        "artifact_uri",
        "artifact_sha256",
        "artifact_format",
        "exceeds_warn_item_chars",
        "matching_function_call_index",
        "matching_function_call_arguments_chars",
    )

    for target in targets[:safe_limit]:
        if not isinstance(target, dict):
            continue
        compacted.append(
            {
                key: target.get(key)
                for key in compact_keys
                if key in target
            }
        )

    return compacted

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


def _tool_output_artifact_dir() -> Path:
    raw = os.environ.get("DEEPSEEK_PROXY_TOOL_OUTPUT_ARTIFACT_DIR") or ".generated/tool-output-artifacts"
    return Path(raw)


def _tool_output_artifact_max_files() -> int:
    return _env_int("DEEPSEEK_PROXY_TOOL_OUTPUT_ARTIFACT_MAX_FILES", 100)


def _safe_tool_output_artifact_component(value: str | None) -> str:
    raw = str(value or "unknown")
    safe = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in raw)
    safe = safe.strip("_") or "unknown"
    return safe[:80]


def _prune_tool_output_artifacts(output_dir: Path | None = None) -> None:
    limit = _tool_output_artifact_max_files()
    if limit <= 0:
        return

    root_dir = output_dir or _tool_output_artifact_dir()
    if not root_dir.exists() or not root_dir.is_dir():
        return

    candidates = sorted(
        (path for path in root_dir.glob("tool_output_image_*.json") if path.is_file()),
        key=lambda path: (path.stat().st_mtime if path.exists() else 0.0, path.name),
        reverse=True,
    )
    for path in candidates[limit:]:
        try:
            path.unlink()
        except OSError as exc:
            print(f"[deepseek-responses-proxy] failed to prune tool output artifact {path}: {exc}")


def _write_tool_output_image_payload_artifact(
    *,
    output: Any,
    output_text: str,
    call_id: str,
    tool_name: str,
    category: str,
    output_type: str,
    output_was_serialized: bool,
    original_item_chars: int,
) -> dict[str, Any] | None:
    digest = hashlib.sha256(output_text.encode("utf-8", errors="replace")).hexdigest()
    output_dir = _tool_output_artifact_dir()
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        print(f"[deepseek-responses-proxy] failed to create tool output artifact dir {output_dir}: {exc}")
        return None

    safe_call_id = _safe_tool_output_artifact_component(call_id)
    safe_tool_name = _safe_tool_output_artifact_component(tool_name)
    filename = f"tool_output_image_{safe_tool_name}_{safe_call_id}_{digest[:12]}_{uuid.uuid4().hex[:8]}.json"
    path = output_dir / filename

    payload = {
        "version": PROXY_VERSION,
        "kind": "tool_output_image_payload",
        "category": category,
        "tool_name": tool_name or "unknown",
        "call_id": call_id or "unknown",
        "created_at": time.time(),
        "sha256": digest,
        "original_output_chars": len(output_text),
        "original_item_chars": int(original_item_chars),
        "output_type": output_type,
        "output_was_serialized": bool(output_was_serialized),
        "payload": output,
        "serialized_output": output_text,
    }

    try:
        path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str), encoding="utf-8")
    except Exception as exc:
        print(f"[deepseek-responses-proxy] failed to write tool output artifact {path}: {exc}")
        return None

    _prune_tool_output_artifacts(output_dir)

    resolved = str(path.resolve())
    return {
        "ok": True,
        "type": "image_payload_artifact_ref",
        "kind": "tool_output_image_payload_ref",
        "category": category,
        "tool_name": tool_name or "unknown",
        "call_id": call_id or "unknown",
        "artifact_path": resolved,
        "artifact_uri": _image_file_uri(resolved),
        "artifact_format": "json",
        "artifact_payload_key": "payload",
        "artifact_serialized_output_key": "serialized_output",
        "original_output_chars": len(output_text),
        "original_item_chars": int(original_item_chars),
        "sha256": digest,
        "output_type": output_type,
        "output_was_serialized": bool(output_was_serialized),
        "preserved": True,
        "note": "Full image payload was preserved on disk. The chat context contains only this lightweight reference.",
    }


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
        "skipped_outputs": [],
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
        skipped_outputs: list[dict[str, Any]] = []
        skip_trace_limit = max(1, _env_int("DEEPSEEK_PROXY_TOOL_OUTPUT_SKIP_TRACE_TARGETS", 8))
        chars_before = _debug_trace_json_chars(trimmed_input)

        for index, item in enumerate(trimmed_input):
            if not isinstance(item, dict):
                continue
            if str(item.get("type") or "") != "function_call_output":
                continue

            report["function_call_output_count"] = int(report["function_call_output_count"]) + 1

            output = item.get("output")
            call_id = str(item.get("call_id") or "")
            call_info = calls_by_id.get(call_id) or {}
            tool_name = str(call_info.get("tool_name") or "unknown")
            category = _classify_tool_output_category(tool_name)
            policy = _tool_output_category_policy(category)
            original_item_chars = _debug_trace_json_chars(item)
            output_chars = _debug_trace_json_chars(output)
            output_type = type(output).__name__
            output_was_serialized = False

            if isinstance(output, str):
                output_text = output
            else:
                try:
                    output_text = json.dumps(
                        output,
                        ensure_ascii=False,
                        separators=(",", ":"),
                        sort_keys=True,
                        default=str,
                    )
                    output_was_serialized = True
                except Exception as exc:
                    if len(skipped_outputs) < skip_trace_limit:
                        skipped_outputs.append(
                            {
                                "index": index,
                                "call_id": call_id,
                                "tool_name": tool_name,
                                "category": category,
                                "skip_reason": "output_not_json_serializable",
                                "output_type": output_type,
                                "serialization_error": f"{type(exc).__name__}: {exc}",
                                "item_chars": original_item_chars,
                                "output_chars": output_chars,
                                "policy_max_item_chars": int(policy["max_item_chars"]),
                                "has_matching_function_call": bool(call_info),
                            }
                        )
                    continue

            if original_item_chars <= int(policy["max_item_chars"]):
                if len(skipped_outputs) < skip_trace_limit:
                    skipped_outputs.append(
                        {
                            "index": index,
                            "call_id": call_id,
                            "tool_name": tool_name,
                            "category": category,
                            "skip_reason": "item_not_over_policy_max",
                            "item_chars": original_item_chars,
                            "output_chars": output_chars,
                            "output_type": output_type,
                            "output_was_serialized": output_was_serialized,
                            "policy_max_item_chars": int(policy["max_item_chars"]),
                            "has_matching_function_call": bool(call_info),
                        }
                    )
                continue

            if category == "image_payload":
                artifact_output = _write_tool_output_image_payload_artifact(
                    output=output,
                    output_text=output_text,
                    call_id=call_id,
                    tool_name=tool_name,
                    category=category,
                    output_type=output_type,
                    output_was_serialized=output_was_serialized,
                    original_item_chars=original_item_chars,
                )
                if artifact_output is not None:
                    item["output"] = artifact_output
                    trimmed_item_chars = _debug_trace_json_chars(item)
                    removed_chars = max(0, original_item_chars - trimmed_item_chars)
                    if removed_chars > 0:
                        targets.append(
                            {
                                "index": index,
                                "call_id": call_id,
                                "tool_name": tool_name,
                                "category": category,
                                "policy_name": str(policy.get("policy_name") or category),
                                "trim_reason": "enabled_image_payload_artifact_preserved",
                                "item_chars": original_item_chars,
                                "output_chars": len(output_text),
                                "original_chars": original_item_chars,
                                "output_type": output_type,
                                "output_was_serialized": output_was_serialized,
                                "estimated_after_chars": trimmed_item_chars,
                                "estimated_remove_chars": removed_chars,
                                "exceeds_warn_item_chars": True,
                                "artifact_preserved": True,
                                "artifact_path": artifact_output.get("artifact_path"),
                                "artifact_uri": artifact_output.get("artifact_uri"),
                                "artifact_sha256": artifact_output.get("sha256"),
                                "artifact_format": artifact_output.get("artifact_format"),
                            }
                        )
                        continue

                    item["output"] = output
                    if len(skipped_outputs) < skip_trace_limit:
                        skipped_outputs.append(
                            {
                                "index": index,
                                "call_id": call_id,
                                "tool_name": tool_name,
                                "category": category,
                                "skip_reason": "artifact_ref_not_smaller",
                                "item_chars": original_item_chars,
                                "output_chars": output_chars,
                                "trimmed_item_chars": trimmed_item_chars,
                                "policy_max_item_chars": int(policy["max_item_chars"]),
                                "has_matching_function_call": bool(call_info),
                                "artifact_path": artifact_output.get("artifact_path"),
                            }
                        )
                    continue

            trimmed_output = _format_trimmed_tool_output_text(
                original_text=output_text,
                call_id=call_id,
                tool_name=tool_name,
                category=category,
                policy=policy,
                original_item_chars=original_item_chars,
            )
            if trimmed_output == output_text:
                if len(skipped_outputs) < skip_trace_limit:
                    skipped_outputs.append(
                        {
                            "index": index,
                            "call_id": call_id,
                            "tool_name": tool_name,
                            "category": category,
                            "skip_reason": "trimmed_output_equal_original",
                            "item_chars": original_item_chars,
                            "output_chars": output_chars,
                            "policy_max_item_chars": int(policy["max_item_chars"]),
                            "has_matching_function_call": bool(call_info),
                        }
                    )
                continue

            original_output_chars = len(output_text)
            item["output"] = trimmed_output
            trimmed_item_chars = _debug_trace_json_chars(item)
            removed_chars = max(0, original_item_chars - trimmed_item_chars)
            if removed_chars <= 0:
                item["output"] = output
                if len(skipped_outputs) < skip_trace_limit:
                    skipped_outputs.append(
                        {
                            "index": index,
                            "call_id": call_id,
                            "tool_name": tool_name,
                            "category": category,
                            "skip_reason": "trimmed_item_not_smaller",
                            "item_chars": original_item_chars,
                            "output_chars": output_chars,
                            "trimmed_item_chars": trimmed_item_chars,
                            "policy_max_item_chars": int(policy["max_item_chars"]),
                            "has_matching_function_call": bool(call_info),
                        }
                    )
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
                    "output_type": output_type,
                    "output_was_serialized": output_was_serialized,
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
            report["skipped_outputs"] = skipped_outputs
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
                "skipped_outputs": skipped_outputs,
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
        report["skipped_outputs"] = []
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
                    prompt_cache_hit_tokens INTEGER NOT NULL DEFAULT 0,
                    prompt_cache_miss_tokens INTEGER NOT NULL DEFAULT 0,
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
        self._ensure_column(conn, table="usage_events", column="purpose", ddl="TEXT NOT NULL DEFAULT 'final'")
        self._ensure_column(conn, table="usage_events", column="call_index", ddl="INTEGER")
        self._ensure_column(conn, table="usage_events", column="request_id", ddl="TEXT")
        self._ensure_column(conn, table="usage_events", column="session_id", ddl="TEXT")
        self._ensure_column(conn, table="usage_events", column="requested_model", ddl="TEXT")
        self._ensure_column(conn, table="usage_events", column="effective_model", ddl="TEXT")
        self._ensure_column(conn, table="usage_events", column="upstream_model", ddl="TEXT")
        self._ensure_column(conn, table="usage_events", column="route", ddl="TEXT")
        self._ensure_column(conn, table="usage_events", column="effort", ddl="TEXT")
        self._ensure_column(conn, table="usage_events", column="prompt_cache_hit_tokens", ddl="INTEGER NOT NULL DEFAULT 0")
        self._ensure_column(conn, table="usage_events", column="prompt_cache_miss_tokens", ddl="INTEGER NOT NULL DEFAULT 0")
        self._ensure_column(conn, table="usage_events", column="pricing_model", ddl="TEXT")
        self._ensure_column(conn, table="usage_events", column="pricing_currency", ddl="TEXT")
        self._ensure_column(conn, table="usage_events", column="pricing_unit", ddl="TEXT")
        self._ensure_column(conn, table="usage_events", column="pricing_source_kind", ddl="TEXT")
        self._ensure_column(conn, table="usage_events", column="pricing_updated_at", ddl="TEXT")
        self._ensure_column(conn, table="usage_events", column="pricing_input_cache_hit", ddl="REAL")
        self._ensure_column(conn, table="usage_events", column="pricing_input_cache_miss", ddl="REAL")
        self._ensure_column(conn, table="usage_events", column="pricing_output", ddl="REAL")
        self._ensure_column(conn, table="usage_events", column="estimated_cost_source_currency", ddl="TEXT NOT NULL DEFAULT 'USD'")
        self._ensure_column(conn, table="usage_events", column="estimated_cost_source_amount", ddl="REAL")
        self._ensure_column(conn, table="usage_events", column="estimated_cost_display_amount", ddl="REAL")
        self._ensure_column(conn, table="usage_events", column="estimated_cost_display_currency", ddl="TEXT")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_usage_events_session_id ON usage_events(session_id)")

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
        session_id: str | None = None,
        requested_model: str | None = None,
        effective_model: str | None = None,
        upstream_model: str | None = None,
        route: str | None = None,
        effort: str | None = None,
        pricing_context: dict[str, Any] | None = None,
        estimated_cost_source_currency: str = "USD",
        estimated_cost_source_amount: float | None = None,
        estimated_cost_display_amount: float | None = None,
        estimated_cost_display_currency: str | None = None,
    ) -> None:
        normalized_purpose = str(purpose or "final").strip() or "final"
        normalized_effective_model = str(effective_model or model).strip() or model
        normalized_upstream_model = str(upstream_model or normalized_effective_model).strip() or normalized_effective_model
        normalized_route = str(route or ("thinking" if thinking_enabled else "non_thinking"))
        normalized_session_id = str(session_id).strip() if session_id is not None and str(session_id).strip() else None
        pricing = pricing_context if isinstance(pricing_context, dict) else _pricing_context_for_usage_event(normalized_effective_model)
        source_currency = str(estimated_cost_source_currency or pricing.get("pricing_currency") or "CNY").upper()
        source_amount = float(estimated_cost_source_amount if estimated_cost_source_amount is not None else estimated_cost_usd)
        legacy_usd_amount = float(source_amount if source_currency == "USD" else 0.0)
        display_currency = str(estimated_cost_display_currency or source_currency).upper()
        display_amount = float(estimated_cost_display_amount if estimated_cost_display_amount is not None else source_amount)

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
                    session_id,
                    requested_model,
                    effective_model,
                    upstream_model,
                    prompt_tokens,
                    completion_tokens,
                    total_tokens,
                    cached_tokens,
                    prompt_cache_hit_tokens,
                    prompt_cache_miss_tokens,
                    reasoning_tokens,
                    estimated_cost_usd,
                    route,
                    effort,
                    pricing_model,
                    pricing_currency,
                    pricing_unit,
                    pricing_source_kind,
                    pricing_updated_at,
                    pricing_input_cache_hit,
                    pricing_input_cache_miss,
                    pricing_output,
                    estimated_cost_source_currency,
                    estimated_cost_source_amount,
                    estimated_cost_display_amount,
                    estimated_cost_display_currency
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    normalized_session_id,
                    requested_model,
                    normalized_effective_model,
                    normalized_upstream_model,
                    usage_numbers["prompt_tokens"],
                    usage_numbers["completion_tokens"],
                    usage_numbers["total_tokens"],
                    usage_numbers["cached_tokens"],
                    usage_numbers.get("prompt_cache_hit_tokens", usage_numbers.get("cached_tokens", 0)),
                    usage_numbers.get("prompt_cache_miss_tokens", max(0, usage_numbers.get("prompt_tokens", 0) - usage_numbers.get("cached_tokens", 0))),
                    usage_numbers["reasoning_tokens"],
                    legacy_usd_amount,
                    normalized_route,
                    effort,
                    pricing.get("pricing_model"),
                    pricing.get("pricing_currency"),
                    pricing.get("pricing_unit"),
                    pricing.get("pricing_source_kind"),
                    pricing.get("pricing_updated_at"),
                    pricing.get("pricing_input_cache_hit"),
                    pricing.get("pricing_input_cache_miss"),
                    pricing.get("pricing_output"),
                    source_currency,
                    source_amount,
                    display_amount,
                    display_currency,
                ),
            )

    @staticmethod

    @staticmethod
    def _usage_filter_where(
        *,
        since: int | None = None,
        until: int | None = None,
        thinking: bool | None = None,
        model: str | None = None,
        purpose: str | None = None,
        session_id: str | None = None,
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

        if session_id:
            clauses.append("session_id = ?")
            params.append(session_id)

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
        session_id: str | None = None,
    ) -> list[dict[str, Any]]:
        where_sql, params = self._usage_filter_where(
            since=since,
            until=until,
            thinking=thinking,
            model=model,
            purpose=purpose,
            session_id=session_id,
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
                    session_id,
                    requested_model,
                    effective_model,
                    upstream_model,
                    prompt_tokens,
                    completion_tokens,
                    total_tokens,
                    cached_tokens,
                    prompt_cache_hit_tokens,
                    prompt_cache_miss_tokens,
                    reasoning_tokens,
                    estimated_cost_usd,
                    route,
                    effort,
                    pricing_model,
                    pricing_currency,
                    pricing_unit,
                    pricing_source_kind,
                    pricing_updated_at,
                    pricing_input_cache_hit,
                    pricing_input_cache_miss,
                    pricing_output,
                    estimated_cost_source_currency,
                    estimated_cost_source_amount,
                    estimated_cost_display_amount,
                    estimated_cost_display_currency
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
        session_id: str | None = None,
    ) -> dict[str, Any]:
        where_sql, params = self._usage_filter_where(
            since=since,
            until=until,
            thinking=thinking,
            model=model,
            purpose=purpose,
            session_id=session_id,
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
                    COALESCE(SUM(prompt_cache_hit_tokens), 0) AS prompt_cache_hit_tokens,
                    COALESCE(SUM(prompt_cache_miss_tokens), 0) AS prompt_cache_miss_tokens,
                    COALESCE(SUM(reasoning_tokens), 0) AS reasoning_tokens,
                    COALESCE(SUM(estimated_cost_usd), 0.0) AS estimated_cost_usd
                FROM usage_events
                {where_sql}
                """,
                params,
            ).fetchone()

            currency_rows = conn.execute(
                f"""
                SELECT
                    COALESCE(NULLIF(estimated_cost_source_currency, ''), NULLIF(pricing_currency, ''), 'USD') AS currency,
                    COALESCE(SUM(
                        CASE
                            WHEN estimated_cost_source_amount IS NOT NULL THEN estimated_cost_source_amount
                            ELSE estimated_cost_usd
                        END
                    ), 0.0) AS amount
                FROM usage_events
                {where_sql}
                GROUP BY COALESCE(NULLIF(estimated_cost_source_currency, ''), NULLIF(pricing_currency, ''), 'USD')
                """,
                params,
            ).fetchall()

        summary = dict(row)
        summary["estimated_cost_usd"] = float(summary.get("estimated_cost_usd") or 0.0)
        summary["estimated_cost_by_currency"] = {
            str(currency_row["currency"]).upper(): float(currency_row["amount"] or 0.0)
            for currency_row in currency_rows
        }
        return summary


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
        "max_target_chars": _env_int("DEEPSEEK_PROXY_COMPACT_MAX_TARGET_CHARS", 900_000),
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


def _compact_prompt_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def _compact_message_section_stats(
    messages: list[dict[str, Any]],
    *,
    start: int,
    end: int,
) -> dict[str, Any]:
    bounded_start = max(0, min(start, len(messages)))
    bounded_end = max(bounded_start, min(end, len(messages)))
    role_counts: dict[str, int] = {}
    char_count = 0
    for index in range(bounded_start, bounded_end):
        message = messages[index]
        if not isinstance(message, dict):
            role = "unknown"
            char_count += _json_char_size(message)
        else:
            role = str(message.get("role") or "unknown")
            char_count += _json_char_size(message)
        role_counts[role] = role_counts.get(role, 0) + 1
    message_count = max(0, bounded_end - bounded_start)
    return {
        "message_count": message_count,
        "first_index": bounded_start if message_count else None,
        "last_index": (bounded_end - 1) if message_count else None,
        "role_counts": role_counts,
        "chars": char_count,
    }


def _retained_recent_turns_policy(
    messages: list[dict[str, Any]],
    *,
    keep_recent_messages: int,
    recent_start: int,
) -> dict[str, Any]:
    nominal_recent_start = max(0, len(messages) - max(1, int(keep_recent_messages or 1)))
    retained_stats = _compact_message_section_stats(messages, start=recent_start, end=len(messages))
    return {
        "available": True,
        "unit": "messages",
        "strategy": "retain_recent_tail_with_tool_result_boundary_rewind",
        "source": "_safe_recent_message_start",
        "keep_recent_messages_requested": int(keep_recent_messages),
        "nominal_recent_start": nominal_recent_start,
        "effective_recent_start": recent_start,
        "adjusted_for_tool_result_boundary": recent_start < nominal_recent_start,
        "retained_recent_message_count": retained_stats["message_count"],
        "retained_recent_role_counts": retained_stats["role_counts"],
        "retained_recent_chars": retained_stats["chars"],
        "first_retained_index": retained_stats["first_index"],
        "last_retained_index": retained_stats["last_index"],
        "notes": [
            "The retained recent tail stays verbatim after the compacted summary.",
            "If the nominal boundary lands on a tool result, dsproxy rewinds to keep the assistant tool_call with its tool output.",
        ],
    }


def _compact_material_classifier_dry_run(
    messages: list[dict[str, Any]],
    *,
    recent_start: int,
) -> dict[str, Any]:
    leading, leading_end = _leading_system_developer_messages(messages)
    compact_material = _compact_message_section_stats(messages, start=0, end=recent_start)
    retained_recent = _compact_message_section_stats(messages, start=recent_start, end=len(messages))
    leading_verbatim = _compact_message_section_stats(messages, start=0, end=leading_end)
    return {
        "available": True,
        "mode": "dry_run",
        "applied": False,
        "unit": "messages",
        "strategy": "codex_compact_material_classifier_dry_run",
        "source": "_compaction_prompt_messages",
        "would_summarize_message_count": compact_material["message_count"],
        "would_keep_recent_verbatim_message_count": retained_recent["message_count"],
        "leading_system_developer_message_count": len(leading),
        "sections": {
            "compaction_material": compact_material,
            "retained_recent_verbatim": retained_recent,
            "leading_system_developer_verbatim_after_compaction": leading_verbatim,
        },
        "safety": {
            "mutates_payload": False,
            "raw_content_exposed": False,
            "classification_only": True,
        },
        "notes": [
            "This classifier is dry-run metadata for COMPACT material only.",
            "It does not enable semantic payload compaction or token-based trimming.",
            "Counts and indexes are exposed without raw message content.",
        ],
    }


def _compaction_prompt_fingerprint(
    *,
    system_prompt: str,
    user_prompt: str,
    material: str,
    recent_material: str,
    compactable_count: int,
    recent_start: int,
    recent_count: int,
) -> dict[str, Any]:
    prompt_payload = {
        "system_prompt": system_prompt,
        "user_prompt": user_prompt,
    }
    serialized_prompt = json.dumps(prompt_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {
        "available": True,
        "fingerprint_version": 1,
        "fingerprint_kind": "sha256",
        "source": "_compaction_prompt_messages",
        "sha256": _compact_prompt_sha256(serialized_prompt),
        "system_prompt_sha256": _compact_prompt_sha256(system_prompt),
        "user_prompt_sha256": _compact_prompt_sha256(user_prompt),
        "material_sha256": _compact_prompt_sha256(material),
        "recent_material_sha256": _compact_prompt_sha256(recent_material),
        "compactable_message_count": int(compactable_count),
        "recent_message_count": int(recent_count),
        "recent_start": int(recent_start),
        "redacted": True,
        "raw_prompt_exposed": False,
        "raw_material_exposed": False,
        "notes": [
            "The digest identifies the exact compact prompt and material boundary without exposing raw conversation content.",
            "Changing compact prompt wording, material truncation, or retained recent messages changes this fingerprint.",
        ],
    }

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

    retained_recent_policy = _retained_recent_turns_policy(
        messages,
        keep_recent_messages=keep_recent_messages,
        recent_start=recent_start,
    )
    classifier_dry_run = _compact_material_classifier_dry_run(
        messages,
        recent_start=recent_start,
    )
    fingerprint = _compaction_prompt_fingerprint(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        material=material,
        recent_material=recent_material,
        compactable_count=compactable_count,
        recent_start=recent_start,
        recent_count=len(recent_messages),
    )

    meta = {
        "compactable_message_count": compactable_count,
        "recent_message_count": len(recent_messages),
        "recent_start": recent_start,
        "material_chars": len(material),
        "recent_material_chars": len(recent_material),
        "compaction_prompt_fingerprint": fingerprint,
        "compact_material_classifier_dry_run": classifier_dry_run,
        "retained_recent_policy": retained_recent_policy,
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
    session_id: str | None = None,
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
    report["compaction_prompt_fingerprint"] = material_meta.get("compaction_prompt_fingerprint")
    report["compact_material_classifier_dry_run"] = material_meta.get("compact_material_classifier_dry_run")
    report["retained_recent_policy"] = material_meta.get("retained_recent_policy")

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
            session_id=session_id,
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


_PAYLOAD_TRACE_SENSITIVE_KEY_RE = re.compile(r"(api[_-]?key|authorization|token|secret|password)", re.IGNORECASE)


def _payload_trace_dir() -> Path | None:
    raw = os.environ.get("DEEPSEEK_PROXY_PAYLOAD_TRACE_DIR", "").strip()
    if not raw:
        return None

    try:
        trace_dir = Path(raw).expanduser().resolve()
        tmp_root = Path("/tmp").resolve()
    except Exception as exc:
        print(f"[deepseek-responses-proxy] invalid DEEPSEEK_PROXY_PAYLOAD_TRACE_DIR={raw!r}: {exc}")
        return None

    if trace_dir != tmp_root and tmp_root not in trace_dir.parents:
        print("[deepseek-responses-proxy] ignoring DEEPSEEK_PROXY_PAYLOAD_TRACE_DIR outside /tmp")
        return None

    return trace_dir


def _payload_trace_sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if _PAYLOAD_TRACE_SENSITIVE_KEY_RE.search(key_text):
                sanitized[key_text] = "<redacted>"
            else:
                sanitized[key_text] = _payload_trace_sanitize(item)
        return sanitized

    if isinstance(value, list):
        return [_payload_trace_sanitize(item) for item in value]

    return value


def _payload_trace_json_chars(value: Any) -> int:
    try:
        return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")))
    except Exception:
        return 0


def _payload_trace_content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                if isinstance(item.get("text"), str):
                    parts.append(str(item["text"]))
                elif isinstance(item.get("content"), str):
                    parts.append(str(item["content"]))
            elif isinstance(item, str):
                parts.append(item)
        return "\n".join(parts)
    if content is None:
        return ""
    return str(content)


def _payload_trace_summary(payload: dict[str, Any]) -> dict[str, Any]:
    messages = payload.get("messages")
    tools = payload.get("tools")
    summary: dict[str, Any] = {
        "model": payload.get("model"),
        "stream": payload.get("stream"),
        "payload_chars": _payload_trace_json_chars(payload),
        "message_count": len(messages) if isinstance(messages, list) else None,
        "tools_count": len(tools) if isinstance(tools, list) else 0,
        "tools_chars": _payload_trace_json_chars(tools) if isinstance(tools, list) else 0,
        "roles": {},
        "large_messages": [],
        "duplicate_message_content": [],
        "request_option_keys": sorted([str(key) for key in payload.keys() if key not in {"messages", "tools"}]),
    }

    if isinstance(messages, list):
        role_stats: dict[str, dict[str, int]] = {}
        seen_content: dict[str, list[int]] = {}
        for index, message in enumerate(messages):
            if not isinstance(message, dict):
                continue
            role = str(message.get("role") or "unknown")
            content_text = _payload_trace_content_text(message.get("content"))
            content_chars = len(content_text)
            role_stats.setdefault(role, {"count": 0, "content_chars": 0})
            role_stats[role]["count"] += 1
            role_stats[role]["content_chars"] += content_chars

            normalized = " ".join(content_text.split()).strip()
            if normalized:
                digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
                seen_content.setdefault(digest, []).append(index)

            if content_chars >= 2000:
                summary["large_messages"].append(
                    {
                        "index": index,
                        "role": role,
                        "content_chars": content_chars,
                        "sha256": hashlib.sha256(content_text.encode("utf-8")).hexdigest(),
                        "preview": content_text[:240],
                    }
                )

        summary["roles"] = role_stats
        for digest, indexes in seen_content.items():
            if len(indexes) > 1:
                summary["duplicate_message_content"].append(
                    {
                        "sha256": digest,
                        "indexes": indexes,
                        "count": len(indexes),
                    }
                )

    flags: list[str] = []
    if int(summary.get("tools_chars") or 0) >= 6000:
        flags.append("large_tools_schema")
    if summary.get("duplicate_message_content"):
        flags.append("duplicate_message_content")
    roles = summary.get("roles")
    if isinstance(roles, dict):
        system_count = int(roles.get("system", {}).get("count", 0))
        developer_count = int(roles.get("developer", {}).get("count", 0))
        if system_count + developer_count > 3:
            flags.append("many_system_or_developer_messages")
    summary["preliminary_unhealthy_flags"] = flags
    return summary


def _payload_trace_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(metadata, dict):
        return {}

    safe: dict[str, Any] = {}
    for key, value in metadata.items():
        key_text = str(key)
        if _PAYLOAD_TRACE_SENSITIVE_KEY_RE.search(key_text):
            safe[key_text] = "<redacted>"
        elif isinstance(value, (str, int, float, bool)) or value is None:
            safe[key_text] = value if not isinstance(value, str) else value[:1000]
        else:
            safe[key_text] = _payload_trace_sanitize(value)
    return safe


def _write_upstream_payload_trace(
    payload: dict[str, Any],
    *,
    context_trimming_report: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    trace_dir = _payload_trace_dir()
    if trace_dir is None:
        return

    try:
        trace_dir.mkdir(parents=True, exist_ok=True)
        try:
            trace_dir.chmod(0o700)
        except Exception:
            pass

        sanitized_payload = _payload_trace_sanitize(payload)
        serialized_payload = json.dumps(sanitized_payload, ensure_ascii=False, indent=2)
        payload_sha256 = hashlib.sha256(serialized_payload.encode("utf-8")).hexdigest()
        observed_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="microseconds")
        event_id = f"{time.time_ns()}-{uuid.uuid4().hex[:8]}"

        event = {
            "schema_version": 1,
            "event_id": event_id,
            "observed_at": observed_at,
            "source": "DeepSeekClient.chat_completions",
            "metadata": _payload_trace_metadata(metadata),
            "payload_sha256": payload_sha256,
            "payload_bytes": len(serialized_payload.encode("utf-8")),
            "summary": _payload_trace_summary(sanitized_payload if isinstance(sanitized_payload, dict) else {}),
            "context_trimming_report": _payload_trace_sanitize(context_trimming_report or {}),
            "payload": sanitized_payload,
        }

        tmp_path = trace_dir / f".{event_id}.tmp"
        final_path = trace_dir / f"{event_id}.json"
        tmp_path.write_text(json.dumps(event, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.replace(final_path)
    except Exception as exc:
        print(f"[deepseek-responses-proxy] failed to write upstream payload trace: {exc}")


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
        self.last_context_trimming_report: dict[str, Any] | None = None
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

    async def chat_completions(self, payload: dict[str, Any], trace_metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload, context_trimming_report = _compact_deepseek_payload_context(payload)
        context_trimming_report["observed_at"] = _runtime_payload_guard_observed_at()
        context_trimming_report["source"] = "live_request_payload"
        context_trimming_report["current_chars_source"] = "live_request_payload"
        context_trimming_report["current_chars_precision"] = "exact"
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

        _write_upstream_payload_trace(
            payload,
            context_trimming_report=context_trimming_report,
            metadata=trace_metadata,
        )

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



def _session_id_from_request_payload(request_payload: dict[str, Any] | None) -> str | None:
    if not isinstance(request_payload, dict):
        return None
    for key in ("prompt_cache_key", "session_id", "codex_session_id", "conversation_id"):
        value = request_payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    metadata = request_payload.get("client_metadata")
    if isinstance(metadata, dict):
        for key in ("prompt_cache_key", "session_id", "codex_session_id", "conversation_id"):
            value = metadata.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


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
    session_id: str | None = None,
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
        session_id=session_id,
    )
    started = time.time()
    try:
        trace_metadata = {
            "purpose": purpose,
            "call_index": call_index,
            "response_id": response_id,
            "previous_response_id": previous_response_id,
            "request_id": request_id,
            "requested_model": requested_model,
            "effective_model": effective_model,
            "thinking_enabled": thinking_enabled,
            "session_id": session_id,
        }
        chat_completions = deepseek_client.chat_completions
        try:
            import inspect

            signature = inspect.signature(chat_completions)
            accepts_trace_metadata = "trace_metadata" in signature.parameters or any(
                parameter.kind == parameter.VAR_KEYWORD for parameter in signature.parameters.values()
            )
        except (TypeError, ValueError):
            accepts_trace_metadata = False

        if accepts_trace_metadata:
            deepseek_response = await chat_completions(payload, trace_metadata=trace_metadata)
        else:
            deepseek_response = await chat_completions(payload)
    except Exception as exc:
        _debug_trace_event(
            response_id,
            "upstream_call_failed",
            purpose=purpose,
            call_index=call_index,
            error_type=type(exc).__name__,
            message=str(exc)[:1000],
            elapsed_seconds=time.time() - started,
            session_id=session_id,
        )
        raise

    usage_numbers = _extract_usage_numbers(deepseek_response)
    pricing_context = _pricing_context_for_usage_event(effective_model)
    estimated_cost_source_amount = _estimate_cost_usd(effective_model, usage_numbers)
    estimated_cost_source_currency = str(pricing_context.get("pricing_currency") or "CNY").upper()
    estimated_cost_usd = estimated_cost_source_amount if estimated_cost_source_currency == "USD" else 0.0
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
            session_id=session_id,
        )

    _debug_trace_event(
        response_id,
        "upstream_call_finished",
        purpose=purpose,
        call_index=call_index,
        elapsed_seconds=time.time() - started,
        usage=usage_numbers,
        estimated_cost_usd=estimated_cost_usd,
        session_id=session_id,
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
            session_id=session_id,
            requested_model=requested_model,
            effective_model=effective_model,
            upstream_model=effective_model,
            route="thinking" if thinking_enabled else "non_thinking",
            effort=_deepseek_reasoning_effort_config(payload),
            pricing_context=pricing_context,
            estimated_cost_source_amount=estimated_cost_source_amount,
            estimated_cost_display_amount=estimated_cost_source_amount,
            estimated_cost_display_currency=estimated_cost_source_currency,
            estimated_cost_source_currency=estimated_cost_source_currency,
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
    provider = _image_provider()
    if provider in {"zai", "z.ai", "glm"}:
        return (
            os.environ.get("ZAI_API_KEY")
            or os.environ.get("GLM_API_KEY")
            or os.environ.get("DEEPSEEK_PROXY_IMAGE_API_KEY")
            or ""
        )
    return (
        os.environ.get("ZHIPUAI_API_KEY")
        or os.environ.get("ZHIPU_API_KEY")
        or os.environ.get("DEEPSEEK_PROXY_IMAGE_API_KEY")
        or ""
    )


def _dashscope_api_key() -> str:
    return (
        os.environ.get("DEEPSEEK_PROXY_DASHSCOPE_API_KEY")
        or os.environ.get("DASHSCOPE_API_KEY")
        or os.environ.get("ALIBABA_DASHSCOPE_API_KEY")
        or os.environ.get("DEEPSEEK_PROXY_IMAGE_API_KEY")
        or ""
    )


def _stability_api_key() -> str:
    return (
        os.environ.get("STABILITY_API_KEY")
        or os.environ.get("DEEPSEEK_PROXY_STABILITY_API_KEY")
        or os.environ.get("DEEPSEEK_PROXY_IMAGE_API_KEY")
        or ""
    )


def _fal_api_key() -> str:
    return (
        os.environ.get("FAL_KEY")
        or os.environ.get("FAL_API_KEY")
        or os.environ.get("DEEPSEEK_PROXY_FAL_API_KEY")
        or os.environ.get("DEEPSEEK_PROXY_IMAGE_API_KEY")
        or ""
    )


def _image_api_key_for_provider(provider: str | None = None) -> str:
    selected = (provider or _image_provider()).strip().lower()
    if _is_qwen_image_provider(selected):
        return _dashscope_api_key()
    if selected in {"stability", "stability_ai", "stable_image"}:
        return _stability_api_key()
    if selected in {"fal", "fal_ai", "fal.ai"}:
        return _fal_api_key()
    return _image_api_key()

def _zai_compatible_image_endpoint(provider: str | None = None) -> str:
    selected = (provider or _image_provider()).strip().lower()
    if selected in {"zhipu", "zhipuai", "bigmodel"}:
        return "https://open.bigmodel.cn/api/paas/v4/images/generations"
    return "https://api.z.ai/api/paas/v4/images/generations"


_QWEN_IMAGE_REGION_ALIASES = {
    "qwen": "qwen_image",
    "qwen_image": "qwen_image",
    "qwen-image": "qwen_image",
    "dashscope": "qwen_image",
    "aliyun": "qwen_image",
    "alibaba": "qwen_image",
    "qwen_image_beijing": "qwen_image_beijing",
    "qwen-image-beijing": "qwen_image_beijing",
    "dashscope_beijing": "qwen_image_beijing",
    "qwen_image_singapore": "qwen_image_singapore",
    "qwen-image-singapore": "qwen_image_singapore",
    "dashscope_singapore": "qwen_image_singapore",
    "qwen_image_us": "qwen_image_us",
    "qwen-image-us": "qwen_image_us",
    "qwen_us": "qwen_image_us",
    "qwen_us_virginia": "qwen_image_us",
    "dashscope_us": "qwen_image_us",
    "qwen_image_germany": "qwen_image_germany",
    "qwen-image-germany": "qwen_image_germany",
    "qwen_germany": "qwen_image_germany",
    "qwen_frankfurt": "qwen_image_germany",
    "dashscope_germany": "qwen_image_germany",
}

_QWEN_IMAGE_REGION_STATUS = {
    "qwen_image": {
        "region": "Beijing",
        "endpoint": "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation",
        "model_available": True,
    },
    "qwen_image_beijing": {
        "region": "Beijing",
        "endpoint": "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation",
        "model_available": True,
    },
    "qwen_image_singapore": {
        "region": "Singapore",
        "endpoint": "https://dashscope-intl.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation",
        "model_available": True,
    },
    "qwen_image_us": {
        "region": "US Virginia",
        "endpoint": "https://dashscope-us.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation",
        "model_available": False,
    },
    "qwen_image_germany": {
        "region": "Germany Frankfurt",
        "endpoint": "https://dashscope.eu-central-1.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation",
        "model_available": False,
    },
}


def _canonical_qwen_image_provider(provider: str | None = None) -> str:
    selected = (provider or _image_provider()).strip().lower().replace(" ", "_")
    return _QWEN_IMAGE_REGION_ALIASES.get(selected, selected)


def _is_qwen_image_provider(provider: str | None = None) -> bool:
    return _canonical_qwen_image_provider(provider) in _QWEN_IMAGE_REGION_STATUS


def _qwen_image_region_status(provider: str | None = None) -> dict[str, Any]:
    canonical = _canonical_qwen_image_provider(provider)
    return dict(_QWEN_IMAGE_REGION_STATUS.get(canonical) or _QWEN_IMAGE_REGION_STATUS["qwen_image"])


def _image_model() -> str:
    provider = _image_provider()
    if _is_qwen_image_provider(provider):
        return (
            os.environ.get("DEEPSEEK_PROXY_IMAGE_MODEL")
            or os.environ.get("DASHSCOPE_IMAGE_MODEL")
            or "qwen-image-2.0-pro"
        )
    if provider in {"stability", "stability_ai", "stable_image"}:
        return (
            os.environ.get("DEEPSEEK_PROXY_IMAGE_MODEL")
            or os.environ.get("STABILITY_IMAGE_MODEL")
            or "stable-image-core"
        )
    if provider in {"fal", "fal_ai", "fal.ai"}:
        return (
            os.environ.get("DEEPSEEK_PROXY_IMAGE_MODEL")
            or os.environ.get("FAL_IMAGE_MODEL")
            or "fal-ai/flux/schnell"
        )
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
    provider = _image_provider()
    api_key = _image_api_key_for_provider(provider)
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

    endpoint = os.environ.get("DEEPSEEK_PROXY_IMAGE_BASE_URL") or _zai_compatible_image_endpoint(provider)

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


async def _dashscope_qwen_image_generate(arguments: dict[str, Any]) -> dict[str, Any]:
    provider = _image_provider()
    api_key = _image_api_key_for_provider(provider)
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
            "message": "Set DEEPSEEK_PROXY_IMAGE_API_KEY, DEEPSEEK_PROXY_DASHSCOPE_API_KEY, DASHSCOPE_API_KEY, or ALIBABA_DASHSCOPE_API_KEY.",
            "images": [],
        }

    body: dict[str, Any] = {
        "model": _image_model(),
        "input": {
            "messages": [
                {
                    "role": "user",
                    "content": [{"text": prompt}],
                }
            ]
        },
        "parameters": {
            "size": size.replace("x", "*"),
            "n": n,
        },
    }

    region_status = _qwen_image_region_status(provider)
    if not bool(region_status.get("model_available")):
        return {
            "ok": False,
            "provider": provider,
            "model": _image_model(),
            "prompt": prompt,
            "error": "qwen_image_region_model_unavailable",
            "region": region_status.get("region"),
            "message": f"Qwen Image is currently not available for {region_status.get('region')} in CoDeepSeedeX. Choose qwen_image_beijing or qwen_image_singapore, or set a verified custom DashScope image endpoint.",
            "images": [],
        }

    endpoint = os.environ.get(
        "DEEPSEEK_PROXY_IMAGE_BASE_URL",
        os.environ.get(
            "DASHSCOPE_IMAGE_ENDPOINT",
            str(region_status.get("endpoint") or "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"),
        ),
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

    raw_images: list[dict[str, Any]] = []
    output = data.get("output") if isinstance(data, dict) else {}
    if isinstance(output, dict):
        choices = output.get("choices") or []
        for choice in choices:
            if not isinstance(choice, dict):
                continue
            message = choice.get("message") or {}
            content = message.get("content") or []
            for item in content:
                if isinstance(item, dict) and (item.get("image") or item.get("url")):
                    raw_images.append({"url": item.get("image") or item.get("url"), "raw": item})
        for item in output.get("results") or []:
            if isinstance(item, dict):
                raw_images.append(item)

    images: list[dict[str, Any]] = []
    for item in raw_images:
        url = item.get("url") or item.get("image") or ""
        file_path = None
        if url and url.startswith("http") and _image_download_enabled():
            file_path = await _download_image_url(url, provider=provider)
        images.append(
            {
                "url": url if url.startswith("http") else None,
                **_image_artifact_fields(file_path),
                "mime_type": "image/png",
                "raw": item.get("raw", item),
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

def _image_data_url_from_base64(value: str, *, mime_type: str = "image/png") -> str:
    return f"data:{mime_type};base64,{value}"


async def _stability_image_generate(arguments: dict[str, Any]) -> dict[str, Any]:
    provider = _image_provider()
    api_key = _image_api_key_for_provider(provider)
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
            "message": "Set DEEPSEEK_PROXY_IMAGE_API_KEY, STABILITY_API_KEY, or DEEPSEEK_PROXY_STABILITY_API_KEY.",
            "images": [],
        }

    files = {
        "prompt": (None, prompt),
        "output_format": (None, os.environ.get("DEEPSEEK_PROXY_STABILITY_OUTPUT_FORMAT", "png")),
    }
    aspect_ratio = os.environ.get("DEEPSEEK_PROXY_STABILITY_ASPECT_RATIO")
    if aspect_ratio:
        files["aspect_ratio"] = (None, aspect_ratio)

    endpoint = os.environ.get(
        "DEEPSEEK_PROXY_STABILITY_IMAGE_URL",
        "https://api.stability.ai/v2beta/stable-image/generate/core",
    )

    try:
        async with httpx.AsyncClient(timeout=_env_float("DEEPSEEK_PROXY_IMAGE_TIMEOUT_SECONDS", 120.0)) as client:
            response = await client.post(
                endpoint,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Accept": "application/json",
                },
                files=files,
            )
            response.raise_for_status()
            content_type = response.headers.get("content-type", "")
            if "application/json" in content_type.lower():
                data = response.json()
            else:
                data = {"binary": response.content}
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

    raw_images: list[dict[str, Any]] = []
    if isinstance(data, dict):
        if data.get("image"):
            raw_images.append({"base64": data.get("image"), "mime_type": "image/png"})
        for item in data.get("artifacts") or data.get("images") or []:
            if isinstance(item, dict):
                raw_images.append(item)

    images: list[dict[str, Any]] = []
    for item in raw_images[:n]:
        mime_type = item.get("mime_type") or item.get("content_type") or "image/png"
        url = item.get("url") or item.get("image_url")
        base64_value = item.get("base64") or item.get("b64_json") or item.get("base64_json")
        image: dict[str, Any] = {
            "url": url if isinstance(url, str) and url.startswith("http") else None,
            "mime_type": mime_type,
            "raw": item,
        }
        if base64_value:
            image["url"] = _image_data_url_from_base64(str(base64_value), mime_type=mime_type)
        images.append(image)

    return {
        "ok": True,
        "provider": provider,
        "model": _image_model(),
        "prompt": prompt,
        "size": size,
        "images": images,
    }


async def _fal_image_generate(arguments: dict[str, Any]) -> dict[str, Any]:
    provider = _image_provider()
    api_key = _image_api_key_for_provider(provider)
    prompt = str(arguments.get("prompt") or "").strip()
    size = _image_size(arguments.get("size"))
    n = _image_n(arguments.get("n"))
    model = _image_model()

    if not api_key:
        return {
            "ok": False,
            "provider": provider,
            "model": model,
            "prompt": prompt,
            "error": "missing_api_key",
            "message": "Set DEEPSEEK_PROXY_IMAGE_API_KEY, FAL_KEY, FAL_API_KEY, or DEEPSEEK_PROXY_FAL_API_KEY.",
            "images": [],
        }

    body: dict[str, Any] = {
        "prompt": prompt,
        "num_images": n,
    }
    if size:
        body["image_size"] = size

    endpoint = os.environ.get("DEEPSEEK_PROXY_FAL_IMAGE_URL") or f"https://fal.run/{model}"

    try:
        async with httpx.AsyncClient(timeout=_env_float("DEEPSEEK_PROXY_IMAGE_TIMEOUT_SECONDS", 120.0)) as client:
            response = await client.post(
                endpoint,
                headers={
                    "Authorization": f"Key {api_key}",
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
            "model": model,
            "prompt": prompt,
            "error": "image_generation_failed",
            "message": str(exc),
            "images": [],
        }

    raw_images = data.get("images") or data.get("data", {}).get("images") or []
    images: list[dict[str, Any]] = []
    for item in raw_images[:n]:
        if not isinstance(item, dict):
            continue
        url = item.get("url") or item.get("image_url")
        file_path = None
        if url and isinstance(url, str) and url.startswith("http") and _image_download_enabled():
            file_path = await _download_image_url(url, provider=provider)
        images.append(
            {
                "url": url if isinstance(url, str) and url.startswith("http") else None,
                **_image_artifact_fields(file_path),
                "mime_type": item.get("content_type") or item.get("mime_type") or "image/png",
                "raw": item,
            }
        )

    return {
        "ok": True,
        "provider": provider,
        "model": model,
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

    if _is_qwen_image_provider(provider):
        return await _dashscope_qwen_image_generate(arguments)

    if provider in {"stability", "stability_ai", "stable_image"}:
        return await _stability_image_generate(arguments)

    if provider in {"fal", "fal_ai", "fal.ai"}:
        return await _fal_image_generate(arguments)

    return {
        "ok": False,
        "provider": provider,
        "model": _image_model(),
        "prompt": prompt,
        "error": "unsupported_image_provider",
        "message": "Supported providers: mock, glm, zai, zhipu, zhipuai, bigmodel, qwen_image, qwen_image_beijing, qwen_image_singapore, qwen_image_us, qwen_image_germany, dashscope, stability, fal, disabled.",
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


def _tavily_api_key() -> str:
    return (
        os.environ.get("TAVILY_API_KEY")
        or os.environ.get("DEEPSEEK_PROXY_TAVILY_API_KEY")
        or ""
    )


def _brave_search_api_key() -> str:
    return (
        os.environ.get("BRAVE_SEARCH_API_KEY")
        or os.environ.get("BRAVE_API_KEY")
        or os.environ.get("DEEPSEEK_PROXY_BRAVE_SEARCH_API_KEY")
        or ""
    )


def _exa_api_key() -> str:
    return (
        os.environ.get("EXA_API_KEY")
        or os.environ.get("DEEPSEEK_PROXY_EXA_API_KEY")
        or ""
    )


def _firecrawl_api_key() -> str:
    return (
        os.environ.get("FIRECRAWL_API_KEY")
        or os.environ.get("DEEPSEEK_PROXY_FIRECRAWL_API_KEY")
        or ""
    )


def _web_search_api_key_for_provider(provider: str | None = None) -> str:
    selected = (provider or _web_search_provider()).strip().lower()
    if selected == "serpapi":
        return _serpapi_api_key()
    if selected == "tavily":
        return _tavily_api_key()
    if selected == "brave":
        return _brave_search_api_key()
    if selected == "exa":
        return _exa_api_key()
    if selected == "firecrawl":
        return _firecrawl_api_key()
    return ""


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


async def _tavily_web_search(query: str, max_results: int) -> dict[str, Any]:
    api_key = _tavily_api_key()
    if not api_key:
        return {
            "ok": False,
            "provider": "tavily",
            "query": query,
            "error": "missing_api_key",
            "message": "TAVILY_API_KEY or DEEPSEEK_PROXY_TAVILY_API_KEY is required.",
            "results": [],
        }

    body: dict[str, Any] = {
        "query": query,
        "max_results": max_results,
    }
    search_depth = os.environ.get("DEEPSEEK_PROXY_TAVILY_SEARCH_DEPTH")
    if search_depth:
        body["search_depth"] = search_depth

    try:
        async with httpx.AsyncClient(timeout=_web_search_timeout_seconds()) as client:
            response = await client.post(
                os.environ.get("DEEPSEEK_PROXY_TAVILY_SEARCH_URL", "https://api.tavily.com/search"),
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
            "provider": "tavily",
            "query": query,
            "error": "web_search_failed",
            "message": str(exc),
            "results": [],
        }

    raw_results = data.get("results") or []
    results = [
        {
            "title": item.get("title") or "",
            "url": item.get("url") or "",
            "snippet": item.get("content") or item.get("snippet") or "",
            "published_at": item.get("published_date") or item.get("published_at"),
        }
        for item in raw_results[:max_results]
        if isinstance(item, dict)
    ]

    return {
        "ok": True,
        "provider": "tavily",
        "query": query,
        "results": results,
    }


async def _brave_web_search(query: str, max_results: int) -> dict[str, Any]:
    api_key = _brave_search_api_key()
    if not api_key:
        return {
            "ok": False,
            "provider": "brave",
            "query": query,
            "error": "missing_api_key",
            "message": "BRAVE_SEARCH_API_KEY, BRAVE_API_KEY, or DEEPSEEK_PROXY_BRAVE_SEARCH_API_KEY is required.",
            "results": [],
        }

    params: dict[str, Any] = {
        "q": query,
        "count": max_results,
    }
    country = os.environ.get("DEEPSEEK_PROXY_BRAVE_COUNTRY")
    search_lang = os.environ.get("DEEPSEEK_PROXY_BRAVE_SEARCH_LANG")
    if country:
        params["country"] = country
    if search_lang:
        params["search_lang"] = search_lang

    try:
        async with httpx.AsyncClient(timeout=_web_search_timeout_seconds()) as client:
            response = await client.get(
                os.environ.get("DEEPSEEK_PROXY_BRAVE_SEARCH_URL", "https://api.search.brave.com/res/v1/web/search"),
                headers={
                    "Accept": "application/json",
                    "X-Subscription-Token": api_key,
                },
                params=params,
            )
            response.raise_for_status()
            data = response.json()
    except Exception as exc:
        return {
            "ok": False,
            "provider": "brave",
            "query": query,
            "error": "web_search_failed",
            "message": str(exc),
            "results": [],
        }

    raw_results = ((data.get("web") or {}).get("results") or [])
    results = [
        {
            "title": item.get("title") or "",
            "url": item.get("url") or "",
            "snippet": item.get("description") or item.get("snippet") or "",
            "published_at": item.get("age"),
        }
        for item in raw_results[:max_results]
        if isinstance(item, dict)
    ]

    return {
        "ok": True,
        "provider": "brave",
        "query": query,
        "results": results,
    }


async def _exa_web_search(query: str, max_results: int) -> dict[str, Any]:
    api_key = _exa_api_key()
    if not api_key:
        return {
            "ok": False,
            "provider": "exa",
            "query": query,
            "error": "missing_api_key",
            "message": "EXA_API_KEY or DEEPSEEK_PROXY_EXA_API_KEY is required.",
            "results": [],
        }

    body: dict[str, Any] = {
        "query": query,
        "numResults": max_results,
    }
    search_type = os.environ.get("DEEPSEEK_PROXY_EXA_SEARCH_TYPE")
    if search_type:
        body["type"] = search_type

    try:
        async with httpx.AsyncClient(timeout=_web_search_timeout_seconds()) as client:
            response = await client.post(
                os.environ.get("DEEPSEEK_PROXY_EXA_SEARCH_URL", "https://api.exa.ai/search"),
                headers={
                    "x-api-key": api_key,
                    "Content-Type": "application/json",
                },
                json=body,
            )
            response.raise_for_status()
            data = response.json()
    except Exception as exc:
        return {
            "ok": False,
            "provider": "exa",
            "query": query,
            "error": "web_search_failed",
            "message": str(exc),
            "results": [],
        }

    raw_results = data.get("results") or []
    results = []
    for item in raw_results[:max_results]:
        if not isinstance(item, dict):
            continue
        highlights = item.get("highlights") or []
        snippet = item.get("text") or item.get("summary") or item.get("snippet") or ""
        if not snippet and highlights and isinstance(highlights, list):
            snippet = str(highlights[0])
        results.append(
            {
                "title": item.get("title") or "",
                "url": item.get("url") or "",
                "snippet": snippet,
                "published_at": item.get("publishedDate") or item.get("published_at"),
            }
        )

    return {
        "ok": True,
        "provider": "exa",
        "query": query,
        "results": results,
    }


async def _firecrawl_web_search(query: str, max_results: int) -> dict[str, Any]:
    api_key = _firecrawl_api_key()
    if not api_key:
        return {
            "ok": False,
            "provider": "firecrawl",
            "query": query,
            "error": "missing_api_key",
            "message": "FIRECRAWL_API_KEY or DEEPSEEK_PROXY_FIRECRAWL_API_KEY is required.",
            "results": [],
        }

    body: dict[str, Any] = {
        "query": query,
        "limit": max_results,
    }

    try:
        async with httpx.AsyncClient(timeout=_web_search_timeout_seconds()) as client:
            response = await client.post(
                os.environ.get("DEEPSEEK_PROXY_FIRECRAWL_SEARCH_URL", "https://api.firecrawl.dev/v2/search"),
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
            "provider": "firecrawl",
            "query": query,
            "error": "web_search_failed",
            "message": str(exc),
            "results": [],
        }

    raw_results = data.get("data") or data.get("results") or []
    results = []
    for item in raw_results[:max_results]:
        if not isinstance(item, dict):
            continue
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        results.append(
            {
                "title": item.get("title") or metadata.get("title") or "",
                "url": item.get("url") or metadata.get("sourceURL") or metadata.get("url") or "",
                "snippet": item.get("description") or item.get("markdown") or item.get("content") or metadata.get("description") or "",
                "published_at": item.get("published_at") or metadata.get("publishedTime"),
            }
        )

    return {
        "ok": True,
        "provider": "firecrawl",
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

    if provider == "tavily":
        return await _tavily_web_search(query, max_results)

    if provider == "brave":
        return await _brave_web_search(query, max_results)

    if provider == "exa":
        return await _exa_web_search(query, max_results)

    if provider == "firecrawl":
        return await _firecrawl_web_search(query, max_results)

    return {
        "ok": False,
        "provider": provider,
        "query": query,
        "error": "unsupported_web_search_provider",
        "message": "Supported providers: mock, serpapi, tavily, brave, exa, firecrawl, disabled.",
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
            "command_risk_policy": _command_risk_policy_status(),
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


def _user_tool_control_policy_env_config() -> dict[str, Any]:
    raw_mode = os.environ.get("DEEPSEEK_PROXY_USER_TOOL_CONTROL_POLICY_MODE", "dry_run")
    mode = str(raw_mode or "dry_run").strip().lower()
    if mode not in {"off", "dry_run", "enabled"}:
        mode = "dry_run"
    return {
        "mode": mode,
        "enabled": mode != "off",
        "preview_chars": max(128, _env_int("DEEPSEEK_PROXY_USER_TOOL_CONTROL_PREVIEW_CHARS", 1200)),
    }


def _responses_content_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = []
        for item in value:
            text = _responses_content_text(item)
            if text:
                parts.append(text)
        return "\n".join(parts)
    if isinstance(value, dict):
        for key in ("text", "input_text", "output_text", "content", "value"):
            if key in value:
                text = _responses_content_text(value.get(key))
                if text:
                    return text
        return ""
    return str(value)


def _latest_user_text_from_responses_input(input_value: Any) -> str:
    if isinstance(input_value, str):
        return input_value
    if not isinstance(input_value, list):
        return ""

    for item in reversed(input_value):
        if not isinstance(item, dict):
            continue
        item_type = str(item.get("type") or "")
        role = str(item.get("role") or "")
        if item_type == "message" and role == "user":
            text = _responses_content_text(item.get("content"))
            if text.strip():
                return text
        if item_type in {"input_text", "message"} and role in {"", "user"}:
            text = _responses_content_text(item)
            if text.strip():
                return text
    return ""


def _text_looks_like_meta_or_quoted_instruction(text: str) -> bool:
    normalized = " ".join(text.strip().lower().split())
    if not normalized:
        return False

    meta_markers = [
        "如果我说",
        "假设用户说",
        "这句话",
        "这段话",
        "日志里",
        "日志中",
        "代码里",
        "字段",
        "字符串",
        "引用",
        "解释这句",
        "是什么意思",
        "出现",
        "what does",
        "if i say",
        "suppose the user says",
        "this sentence",
        "this phrase",
        "in the log",
        "in this code",
        "quoted",
        "quote",
        "means",
        "how would you classify",
    ]
    quote_markers = ["“", "”", "\"", "'", "`"]
    stop_like_markers = [
        "不要继续",
        "不要执行",
        "不要调用",
        "不要调用工具",
        "不要使用工具",
        "别调用工具",
        "暂停",
        "stop",
        "do not continue",
        "don't continue",
        "dont continue",
        "no more tools",
        "no more tool",
        "do not use tools",
        "don't use tools",
        "dont use tools",
        "do not run commands",
        "don't run commands",
        "dont run commands",
        "do not execute commands",
        "don't execute commands",
        "dont execute commands",
        "do not run",
        "don't run",
        "dont run",
    ]

    has_stop_like_text = any(marker in normalized for marker in stop_like_markers)
    has_meta_context = any(marker in normalized for marker in meta_markers)
    has_quote_context = sum(text.count(marker) for marker in quote_markers) >= 2

    return has_stop_like_text and (has_meta_context or has_quote_context)


def _detect_user_tool_control_signal(text: str) -> dict[str, Any]:
    normalized = " ".join(text.strip().lower().split())

    negated_stop_markers = [
        "不是让你停止",
        "不是让你停",
        "不要误以为我让你停",
        "不是让你不要执行",
        "不是让你别执行",
        "don't stop",
        "do not stop",
        "not asking you to stop",
        "i am not asking you to stop",
    ]
    if any(marker in normalized for marker in negated_stop_markers):
        return {
            "user_signal": "negated_stop",
            "matched_signals": [marker for marker in negated_stop_markers if marker in normalized],
            "negative_evidence": ["negated_stop"],
        }

    if _text_looks_like_meta_or_quoted_instruction(text):
        return {
            "user_signal": "quoted_or_meta_stop_discussion",
            "matched_signals": [],
            "negative_evidence": ["quoted_or_meta_stop_discussion"],
        }

    tool_context_markers = [
        "工具",
        "命令",
        "执行",
        "运行",
        "调用",
        "adb",
        "uiautomator",
        "截图",
        "截屏",
        "shell",
        "tool",
        "tools",
        "command",
        "commands",
        "execute",
        "run",
        "call",
        "screenshot",
        "screen",
    ]
    stop_markers = [
        "不要继续",
        "别继续",
        "不要再继续",
        "先不要继续",
        "先别继续",
        "暂停",
        "停一下",
        "先停",
        "先暂停",
        "不要执行",
        "别执行",
        "先不要执行",
        "先别执行",
        "不要运行",
        "别运行",
        "不要调用",
        "别调用",
        "不要操作",
        "别操作",
        "先别操作",
        "先不要操作",
        "先别动",
        "不要动",
        "不要跑命令",
        "别跑命令",
        "do not continue",
        "don't continue",
        "dont continue",
        "no more tool",
        "no more tools",
        "do not use tools",
        "don't use tools",
        "dont use tools",
        "no tool calls",
        "do not run",
        "don't run",
        "dont run",
        "do not execute",
        "don't execute",
        "dont execute",
        "no commands",
        "do not call tools",
        "don't call tools",
    ]
    answer_first_markers = [
        "先回答",
        "先解释",
        "先说明",
        "先分析",
        "先讲清楚",
        "先给我解释",
        "先给我说明",
        "先说清楚",
        "answer first",
        "explain first",
        "first answer",
        "first explain",
        "just answer",
        "only answer",
        "explain before",
        "before continuing",
    ]
    ordered_sequence_markers = [
        "然后",
        "再",
        "接着",
        "随后",
        "之后",
        "再继续",
        "然后继续",
        "再运行",
        "再执行",
        "再测试",
        "再提交",
        "再推送",
        "then",
        "after that",
        "afterwards",
        "then continue",
        "then run",
        "then execute",
        "then test",
        "then commit",
        "then push",
    ]
    followup_action_markers = [
        "继续",
        "执行",
        "运行",
        "测试",
        "处理",
        "修改",
        "生成",
        "检查",
        "提交",
        "推送",
        "发布",
        "合并",
        "帮我",
        "run",
        "execute",
        "continue",
        "test",
        "process",
        "modify",
        "update",
        "generate",
        "check",
        "commit",
        "push",
        "publish",
        "merge",
        "do ",
    ]
    ambiguous_sequence_markers = [
        "看情况",
        "再说",
        "看一下再",
        "then maybe",
        "maybe then",
        "if needed",
        "if necessary",
    ]
    ambiguous_stop_markers = [
        "停一下",
        "暂停",
        "先别急",
        "hold on",
        "wait",
        "pause",
        "stop",
        "stop for now",
    ]

    matched_stop = [marker for marker in stop_markers if marker in normalized]
    matched_tool_context = [marker for marker in tool_context_markers if marker in normalized]
    matched_answer_first = [marker for marker in answer_first_markers if marker in normalized]
    matched_ordered = [marker for marker in ordered_sequence_markers if marker in normalized]
    matched_followup_action = [marker for marker in followup_action_markers if marker in normalized]
    matched_ambiguous_sequence = [marker for marker in ambiguous_sequence_markers if marker in normalized]
    matched_ambiguous = [marker for marker in ambiguous_stop_markers if marker in normalized]

    if matched_stop and matched_tool_context:
        return {
            "user_signal": "explicit_tool_stop",
            "matched_signals": (matched_stop + matched_tool_context)[:30],
            "negative_evidence": [],
        }

    if matched_answer_first:
        if matched_ambiguous_sequence:
            return {
                "user_signal": "ambiguous_answer_first",
                "matched_signals": (matched_answer_first + matched_ambiguous_sequence + matched_followup_action)[:30],
                "negative_evidence": ["ambiguous_followup_sequence"],
            }
        if matched_ordered and matched_followup_action:
            return {
                "user_signal": "ordered_explain_then_continue",
                "matched_signals": (matched_answer_first + matched_ordered + matched_followup_action)[:30],
                "negative_evidence": [],
            }
        return {
            "user_signal": "answer_or_explain_only",
            "matched_signals": matched_answer_first[:20],
            "negative_evidence": ["no_ordered_followup_action_detected"],
        }

    if matched_stop or matched_ambiguous:
        return {
            "user_signal": "ambiguous_stop",
            "matched_signals": (matched_stop + matched_ambiguous)[:20],
            "negative_evidence": ["tool_context_missing"],
        }

    return {
        "user_signal": "none",
        "matched_signals": [],
        "negative_evidence": [],
    }


def _tool_function_names_for_policy(tools: Any) -> list[str]:
    if not isinstance(tools, list):
        return []
    names: list[str] = []
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        function = tool.get("function") or {}
        if isinstance(function, dict):
            name = function.get("name")
            if name:
                names.append(str(name))
    return names


def _classify_tool_name_risk_for_policy(name: str) -> str:
    lowered = name.lower()

    r3_markers = [
        "delete",
        "remove",
        "rmdir",
        "unlink",
        "overwrite",
        "write_file",
        "truncate",
        "format",
        "reset_hard",
        "clean",
        "drop",
        "force_push",
        "publish_release",
        "delete_tag",
    ]
    if any(marker in lowered for marker in r3_markers):
        return "R3_destructive_or_overwrite"

    if lowered in {
        "shell",
        "exec",
        "run_command",
        "execute_command",
        "run_shell",
        "shell_command",
        "interactive_shell",
        "mcp__shell__run",
        "bash",
        "sh",
        "zsh",
        "powershell",
        "pwsh",
        "apply_patch",
    }:
        return "R3_capable_requires_command_audit"

    r2_markers = [
        "tap",
        "click",
        "send",
        "post",
        "submit",
        "input",
        "keyevent",
        "start_activity",
        "am_start",
    ]
    if any(marker in lowered for marker in r2_markers):
        return "R2_external_or_user_visible_side_effect"

    r1_markers = [
        "screenshot",
        "screencap",
        "screen",
        "uiautomator",
        "adb",
        "dump",
        "read",
        "list",
        "grep",
        "search",
        "web",
        "file",
    ]
    if any(marker in lowered for marker in r1_markers):
        return "R1_read_or_privacy_context"

    if lowered in {
        "proxy_status",
        "proxy_time",
        "proxy_usage_summary",
        "proxy_usage_events",
        "proxy_balance",
        "proxy_echo",
    }:
        return "R0_safe_readonly"

    return "R1_unknown_default_read_or_context"


def _max_tool_risk_for_policy(tool_names: list[str]) -> str:
    order = {
        "R0_safe_readonly": 0,
        "R1_read_or_privacy_context": 1,
        "R1_unknown_default_read_or_context": 1,
        "R2_external_or_user_visible_side_effect": 2,
        "R3_capable_requires_command_audit": 3,
        "R3_destructive_or_overwrite": 3,
    }
    if not tool_names:
        return "R0_no_tools"
    risks = [_classify_tool_name_risk_for_policy(name) for name in tool_names]
    return max(risks, key=lambda risk: order.get(risk, 1))


def _decision_if_user_tool_control_enabled(user_signal: str, max_tool_risk: str) -> str:
    if user_signal in {"negated_stop", "quoted_or_meta_stop_discussion", "none"}:
        if max_tool_risk.startswith("R3_destructive"):
            return "would_require_confirmation"
        return "allow_tools"
    if user_signal in {"explicit_tool_stop", "answer_or_explain_only"}:
        return "would_suppress_tools"
    if user_signal == "ordered_explain_then_continue":
        return "split_turn_required"
    if user_signal == "ambiguous_answer_first":
        return "would_require_confirmation"
    if user_signal == "ambiguous_stop":
        if max_tool_risk.startswith("R3"):
            return "would_require_confirmation"
        return "observe_only"
    return "observe_only"


def _build_user_tool_control_policy_report(input_value: Any, tools: Any) -> dict[str, Any]:
    config = _user_tool_control_policy_env_config()
    text = _latest_user_text_from_responses_input(input_value)
    signal = _detect_user_tool_control_signal(text)
    tool_names = _tool_function_names_for_policy(tools)
    tool_risks = {
        name: _classify_tool_name_risk_for_policy(name)
        for name in tool_names
    }
    max_tool_risk = _max_tool_risk_for_policy(tool_names)
    user_signal = str(signal.get("user_signal") or "none")
    decision_if_enabled = _decision_if_user_tool_control_enabled(user_signal, max_tool_risk)
    preview, _changed = _truncate_middle_text(text.strip(), int(config["preview_chars"]))

    return {
        "version": PROXY_VERSION,
        "mode": config["mode"],
        "effective_mode": config["mode"],
        "enabled": bool(config["enabled"]),
        "active": False,
        "policy_is_dry_run_only": config["mode"] == "dry_run",
        "policy_applied": False,
        "user_signal": user_signal,
        "decision_if_enabled": decision_if_enabled,
        "latest_user_text_present": bool(text.strip()),
        "latest_user_text_preview": preview,
        "matched_signals": signal.get("matched_signals", []),
        "negative_evidence": signal.get("negative_evidence", []),
        "tool_names": tool_names,
        "original_tool_names": tool_names,
        "effective_tool_names": tool_names,
        "tool_risks": tool_risks,
        "max_tool_risk": max_tool_risk,
        "tools_removed_from_upstream": [],
        "liveness_retry_suppressed": False,
        "tool_calls_suppressed_post_upstream": [],
        "suppression_message_emitted": False,
        "notes": [
            "dry_run_does_not_change_tools_or_tool_execution",
            "R3 means destructive or overwrite capability, not every visible side effect",
            "enabled turn-control currently applies only to explicit stop, answer-only, and split-turn sequencing",
        ],
    }


def _write_user_tool_control_policy_report(report: dict[str, Any]) -> None:
    try:
        debug_dir = Path(".debug")
        debug_dir.mkdir(exist_ok=True)
        (debug_dir / "user_tool_control_policy_report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as exc:
        print(f"[deepseek-responses-proxy] failed to write user tool control policy report: {exc}")


def _user_tool_control_turn_control_decisions() -> set[str]:
    return {
        "would_suppress_tools",
        "split_turn_required",
    }


def _user_tool_control_policy_enabled(report: dict[str, Any] | None) -> bool:
    if not isinstance(report, dict):
        return False
    return str(report.get("mode") or "").strip().lower() == "enabled"


def _user_tool_control_should_apply_turn_control(report: dict[str, Any] | None) -> bool:
    if not _user_tool_control_policy_enabled(report):
        return False
    decision = str((report or {}).get("decision_if_enabled") or "")
    return decision in _user_tool_control_turn_control_decisions()


def _apply_user_tool_control_policy_to_tools(
    report: dict[str, Any],
    tools: list[dict[str, Any]] | None,
) -> tuple[list[dict[str, Any]] | None, dict[str, Any]]:
    effective_report = deepcopy(report)
    original_tool_names = _tool_function_names_for_policy(tools)
    effective_tools = tools
    effective_tool_names = original_tool_names
    tools_removed: list[str] = []
    applied = False

    if _user_tool_control_should_apply_turn_control(effective_report):
        effective_tools = None
        effective_tool_names = []
        tools_removed = original_tool_names
        applied = True

    effective_report.update(
        {
            "effective_mode": str(effective_report.get("mode") or "dry_run"),
            "active": bool(applied),
            "policy_applied": bool(applied),
            "original_tool_names": original_tool_names,
            "effective_tool_names": effective_tool_names,
            "tools_removed_from_upstream": tools_removed,
            "tool_names": original_tool_names,
            "policy_is_dry_run_only": str(effective_report.get("mode") or "") == "dry_run",
        }
    )
    if applied:
        notes = list(effective_report.get("notes") or [])
        notes.append("enabled_turn_control_removed_tools_from_upstream_payload")
        effective_report["notes"] = notes

    return effective_tools, effective_report


def _user_tool_control_should_suppress_liveness_retry(
    report: dict[str, Any] | None,
) -> bool:
    return _user_tool_control_should_apply_turn_control(report)


def _user_tool_control_should_suppress_post_upstream_tool_calls(
    report: dict[str, Any] | None,
) -> bool:
    return _user_tool_control_should_apply_turn_control(report)


def _user_tool_command_risk_env_config() -> dict[str, Any]:
    raw_mode = os.environ.get("DEEPSEEK_PROXY_COMMAND_RISK_POLICY_MODE", "dry_run")
    mode = raw_mode.strip().lower()
    if mode not in {"off", "dry_run", "enabled"}:
        mode = "dry_run"
    return {
        "mode": mode,
        "enabled": mode == "enabled",
        "preview_chars": _env_int("DEEPSEEK_PROXY_COMMAND_RISK_PREVIEW_CHARS", 700),
    }


def _command_risk_policy_status() -> dict[str, Any]:
    config = _user_tool_command_risk_env_config()
    mode = str(config.get("mode") or "dry_run")
    enabled = bool(config.get("enabled"))
    return {
        "mode": mode,
        "enabled": enabled,
        "active_when_enabled": enabled,
        "policy_is_dry_run_only": mode == "dry_run",
        "env_var": "DEEPSEEK_PROXY_COMMAND_RISK_POLICY_MODE",
        "preview_chars": int(config.get("preview_chars") or 700),
        "supported_modes": ["off", "dry_run", "enabled"],
        "gate_scope": "C4_only_future_gate",
        "codex_is_default_sandbox_boundary": True,
        "c4_gate_available": True,
        "c4_gate_action_when_enabled": "suppress_and_explain",
        "c4_gate_resume_supported": False,
        "c4_risk_level": "C4_catastrophic_or_out_of_sandbox",
        "normal_development_risks_allowed": [
            "C0_no_command_or_no_arguments",
            "C1_readonly_or_unknown",
            "C2_routine_side_effect",
            "C3_codex_governed_destructive",
        ],
    }


def _command_risk_debug_report_path() -> Path:
    return Path(".debug") / "user_tool_command_risk_report.json"


def _user_tool_command_risk_should_suppress_tool_calls(report: dict[str, Any] | None) -> bool:
    if not isinstance(report, dict):
        return False
    return (
        str(report.get("mode") or "").lower() == "enabled"
        and bool(report.get("enabled"))
        and bool(report.get("c4_gate_triggered"))
        and report.get("max_command_risk") == "C4_catastrophic_or_out_of_sandbox"
    )


def _user_tool_command_risk_c4_preview_lines(report: dict[str, Any] | None) -> list[str]:
    if not isinstance(report, dict):
        return []
    lines: list[str] = []
    for item in report.get("c4_gate_argument_previews") or []:
        if not isinstance(item, dict):
            continue
        tool_name = str(item.get("tool_name") or "")
        for candidate in item.get("candidate_previews") or []:
            if not isinstance(candidate, dict):
                continue
            preview = str(candidate.get("preview") or "").strip()
            if not preview:
                continue
            path = str(candidate.get("path") or "")
            reason_text = ", ".join(str(reason) for reason in (candidate.get("reasons") or []))
            line = f"- tool={tool_name} path={path} preview={preview}"
            if reason_text:
                line = f"{line} reasons={reason_text}"
            lines.append(line)
    return lines[:8]


def _user_tool_command_risk_suppressed_assistant_content(report: dict[str, Any] | None) -> str:
    tool_names = []
    reasons = []
    if isinstance(report, dict):
        tool_names = [str(item) for item in (report.get("c4_gate_tool_names") or []) if item]
        reasons = [str(item) for item in (report.get("c4_gate_reasons") or []) if item]

    preview_lines = _user_tool_command_risk_c4_preview_lines(report)
    parts = [
        "已阻止C4级高风险工具调用。",
        "",
        "该操作被判定为灾难级或超出普通Codex沙箱边界的操作，因此proxy未执行任何tool_call。",
        "当前阶段是suppress-only gate，不支持通过“继续”自动恢复执行。",
    ]
    if tool_names:
        parts.extend(["", "涉及工具：", ", ".join(tool_names)])
    if reasons:
        parts.extend(["", "触发原因：", ", ".join(reasons)])
    if preview_lines:
        parts.extend(["", "命令预览：", *preview_lines])
    parts.extend(
        [
            "",
            "C2/C3级正常开发操作不受该gate影响，仍交给Codex沙箱和审批机制处理。",
        ]
    )
    return "\n".join(parts)


def _user_tool_command_risk_suppressed_deepseek_response(
    deepseek_response: dict[str, Any],
    report: dict[str, Any] | None,
) -> dict[str, Any]:
    suppressed_response = deepcopy(deepseek_response)
    choices = suppressed_response.get("choices") or []
    content = _user_tool_command_risk_suppressed_assistant_content(report)

    if not choices:
        suppressed_response["choices"] = [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": content,
                },
                "finish_reason": "stop",
            }
        ]
        return suppressed_response

    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        first_choice = {}
        choices[0] = first_choice
    first_choice["message"] = {
        "role": "assistant",
        "content": content,
    }
    first_choice["finish_reason"] = "stop"
    return suppressed_response

def _write_user_tool_command_risk_report(report: dict[str, Any]) -> None:
    try:
        debug_dir = Path(".debug")
        debug_dir.mkdir(exist_ok=True)
        _command_risk_debug_report_path().write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as exc:
        print(f"[deepseek-responses-proxy] failed to write command risk report: {exc}")


def _command_risk_tool_call_name(tool_call: dict[str, Any]) -> str:
    function = tool_call.get("function") or {}
    if isinstance(function, dict):
        return str(function.get("name") or "")
    return ""


def _command_risk_tool_call_arguments(tool_call: dict[str, Any]) -> dict[str, Any]:
    function = tool_call.get("function") or {}
    if not isinstance(function, dict):
        return {}
    arguments = function.get("arguments", "")
    decoded = _decode_tool_arguments(arguments)
    return decoded if isinstance(decoded, dict) else {}


def _collect_command_risk_text_candidates(value: Any, *, key_path: str = "") -> list[dict[str, str]]:
    candidates: list[dict[str, str]] = []
    interesting_keys = {
        "cmd",
        "command",
        "commands",
        "script",
        "input",
        "patch",
        "args",
        "arguments",
        "path",
        "file",
        "filename",
        "content",
        "query",
    }

    if isinstance(value, str):
        stripped = value.strip()
        if stripped:
            candidates.append({"path": key_path or "$", "text": stripped})
        return candidates

    if isinstance(value, list):
        for index, item in enumerate(value[:30]):
            candidates.extend(
                _collect_command_risk_text_candidates(
                    item,
                    key_path=f"{key_path}[{index}]" if key_path else f"$[{index}]",
                )
            )
        return candidates

    if isinstance(value, dict):
        for key, item in list(value.items())[:80]:
            key_text = str(key)
            child_path = f"{key_path}.{key_text}" if key_path else key_text
            if key_text.lower() in interesting_keys:
                candidates.extend(
                    _collect_command_risk_text_candidates(item, key_path=child_path)
                )
            elif isinstance(item, (dict, list)):
                candidates.extend(
                    _collect_command_risk_text_candidates(item, key_path=child_path)
                )
        return candidates

    return candidates


def _command_risk_severity_key(risk: str) -> int:
    order = {
        "C0_no_command_or_no_arguments": 0,
        "C1_readonly_or_unknown": 1,
        "C2_routine_side_effect": 2,
        "C3_codex_governed_destructive": 3,
        "C4_catastrophic_or_out_of_sandbox": 4,
        # Backward-compatible aliases from v2.7a40 dry-run reports.
        "C2_side_effect": 2,
        "C3_destructive_or_overwrite": 3,
    }
    return order.get(risk, 1)


def _max_command_risk_level(levels: list[str]) -> str:
    if not levels:
        return "C0_no_command_or_no_arguments"
    return max(levels, key=_command_risk_severity_key)


def _classify_command_text_risk(text: str) -> tuple[str, list[str]]:
    import re

    lowered = text.lower().strip()
    reasons: list[str] = []

    catastrophic_patterns = [
        (r"\brm\s+-[^\n;&|]*[rf][^\n;&|]*\s+(/\s*$|/\*(\s|$)|~(/|\*|\s|$)|/home(/|\*|\s|$)|/root(/|\*|\s|$)|/mnt/[a-zA-Z](/|\*|\s|$)|/[a-zA-Z]:(/|\*|\s|$)|[a-zA-Z]:\\(\*|$)|[a-zA-Z]:/\*(\s|$))", "catastrophic_rm_root_home_or_drive"),
        (r"\brm\s+-[^\n;&|]*[rf][^\n;&|]*\s+\$HOME(/\*)?(\s|$)", "catastrophic_rm_home_env"),
        (r"\b(remove-item|rm|del|erase)\b[^\n;&|]*(c:|d:|e:|/mnt/[a-zA-Z])", "catastrophic_windows_or_mounted_drive_delete"),
        (r"\b(del|erase)\s+(/s\s+)?(/q\s+)?[a-zA-Z]:\\\*", "catastrophic_windows_drive_wildcard_delete"),
        (r"\bformat\s+[a-zA-Z]:", "catastrophic_format_drive"),
        (r"\bdiskpart\b|\bclean\b.*\bdisk\b", "catastrophic_diskpart_or_disk_clean"),
        (r"\bmkfs(\.\w+)?\b", "catastrophic_mkfs"),
        (r"\bdd\b[^\n;&|]*\bof=/dev/(sd|nvme|vd|xvd|hd)[a-z0-9]+", "catastrophic_dd_block_device"),
        (r"\b(drop\s+database|drop\s+schema)\b", "catastrophic_database_drop"),
        (r"\btruncate\s+table\s+(prod|production|public\.|main\.)", "catastrophic_production_table_truncate"),
        (r"\bdelete\s+from\s+(prod|production|public\.|main\.)", "catastrophic_production_table_delete"),
        (r"\bgit\s+push\b[^\n;&|]*(--force|-f)\b[^\n;&|]*(main|master|prod|production)", "catastrophic_force_push_protected_branch"),
    ]
    for pattern, reason in catastrophic_patterns:
        if re.search(pattern, lowered):
            reasons.append(reason)

    if reasons:
        return "C4_catastrophic_or_out_of_sandbox", reasons

    routine_patterns = [
        (r"\brm\s+-[^\n;&|]*[rf]?[^\n;&|]*\s+(\.pytest_cache|__pycache__|\.mypy_cache|\.ruff_cache|\.tox|dist|build|\.coverage|htmlcov)(/|\s|$)", "routine_cache_or_build_cleanup"),
        (r"\brm\s+-[^\n;&|]*[rf]?[^\n;&|]*\s+/tmp/[^\n;&|]+", "routine_tmp_cleanup"),
        (r"\b(remove-item|rm)\b[^\n;&|]*(\.pytest_cache|__pycache__|dist|build|/tmp/)", "routine_cleanup"),
        (r"\bgit\s+add\b", "routine_git_add"),
        (r"\bgit\s+commit\b", "routine_git_commit"),
        (r"\bmkdir\b", "routine_mkdir"),
        (r"\btouch\b", "routine_touch"),
        (r"\b(pip|npm|pnpm|yarn|apt|apt-get|brew)\s+install\b", "routine_dependency_install"),
        (r"\bsed\s+-i\b", "routine_in_place_project_edit"),
        (r"\*\*\*\s+update file:\s+(?!/|~|[a-zA-Z]:|/mnt/)", "routine_apply_patch_update_project_file"),
        (r"\*\*\*\s+add file:\s+(?!/|~|[a-zA-Z]:|/mnt/)", "routine_apply_patch_add_project_file"),
        (r"(^|[^<])>\s*/tmp/[^\n;&|]+", "routine_tmp_redirection_write"),
    ]
    for pattern, reason in routine_patterns:
        if re.search(pattern, lowered):
            reasons.append(reason)

    if reasons:
        return "C2_routine_side_effect", reasons

    codex_governed_patterns = [
        (r"\brm\s+-[^\n;&|]*[rf][^\n;&|]*\s+[^\n;&|]+", "codex_governed_rm_delete"),
        (r"\brmdir\b|\brd\s+/s\b", "codex_governed_directory_delete"),
        (r"\bdel\s+|\berase\s+", "codex_governed_delete"),
        (r"\bremove-item\b|\bremove\s+-item\b", "codex_governed_powershell_remove_item"),
        (r"\bgit\s+reset\s+--hard\b", "codex_governed_git_reset_hard"),
        (r"\bgit\s+clean\s+-[^\n;&|]*[fdx]", "codex_governed_git_clean_force"),
        (r"\bgit\s+push\b[^\n;&|]*(--force|-f)\b", "codex_governed_git_force_push"),
        (r"\bgit\s+branch\s+-d\b|\bgit\s+branch\s+-D\b", "codex_governed_git_branch_delete"),
        (r"\bgit\s+tag\s+-d\b", "codex_governed_git_tag_delete"),
        (r"\b(drop\s+table|truncate\s+table)\b", "codex_governed_sql_drop_or_truncate"),
        (r"\bdelete\s+from\b", "codex_governed_sql_delete"),
        (r"\bupdate\s+\S+\s+set\b", "codex_governed_sql_update"),
        (r"(^|[^<])>\s*[^&\s][^\n]*", "codex_governed_shell_redirection_overwrite"),
        (r"\btee\s+(-a\s+)?\S+", "codex_governed_tee_file_write"),
        (r"\bmv\s+(-f\s+)?\S+\s+\S+", "codex_governed_mv_may_overwrite"),
        (r"\bcp\s+-[^\n;&|]*f[^\n;&|]*\s+\S+\s+\S+", "codex_governed_cp_force_overwrite"),
        (r"\brsync\b[^\n;&|]*--delete\b", "codex_governed_rsync_delete"),
        (r"\bdd\b[^\n;&|]*\bof=", "codex_governed_dd_write_output"),
        (r"\*\*\*\s+delete file:", "codex_governed_apply_patch_delete_file"),
        (r"\*\*\*\s+update file:\s+(/|~|[a-zA-Z]:|/mnt/)", "codex_governed_apply_patch_external_update"),
        (r"\*\*\*\s+add file:\s+(/|~|[a-zA-Z]:|/mnt/)", "codex_governed_apply_patch_external_add"),
    ]
    for pattern, reason in codex_governed_patterns:
        if re.search(pattern, lowered):
            reasons.append(reason)

    if reasons:
        return "C3_codex_governed_destructive", reasons

    readonly_patterns = [
        (r"\b(cat|head|tail|grep|rg|find|ls|pwd)\b", "readonly_command"),
        (r"\bgit\s+(status|diff|log|show|branch)\b", "readonly_git_command"),
    ]
    for pattern, reason in readonly_patterns:
        if re.search(pattern, lowered):
            reasons.append(reason)

    if reasons:
        return "C1_readonly_or_unknown", reasons

    return "C1_readonly_or_unknown", ["no_destructive_pattern_matched"]


def _classify_tool_call_command_risk(tool_call: dict[str, Any]) -> dict[str, Any]:
    config = _user_tool_command_risk_env_config()
    preview_chars = int(config["preview_chars"])

    name = _command_risk_tool_call_name(tool_call)
    arguments = _command_risk_tool_call_arguments(tool_call)
    tool_name_risk = _classify_tool_name_risk_for_policy(name)
    text_candidates = _collect_command_risk_text_candidates(arguments)

    candidate_reports: list[dict[str, Any]] = []
    candidate_levels: list[str] = []
    for candidate in text_candidates[:40]:
        text = candidate["text"]
        risk, reasons = _classify_command_text_risk(text)
        preview, changed = _truncate_middle_text(text, preview_chars)
        candidate_reports.append(
            {
                "path": candidate["path"],
                "risk": risk,
                "reasons": reasons,
                "preview": preview,
                "preview_truncated": changed,
            }
        )
        candidate_levels.append(risk)

    tool_name_reasons: list[str] = []
    if tool_name_risk == "R3_destructive_or_overwrite":
        # Tool names such as write_file/delete_file indicate destructive capability,
        # but Codex remains the default sandbox and approval boundary. Without a
        # catastrophic target path, proxy should not narrow that boundary.
        candidate_levels.append("C3_codex_governed_destructive")
        tool_name_reasons.append("tool_name_destructive_or_overwrite_codex_governed")
    elif tool_name_risk == "R3_capable_requires_command_audit":
        if not candidate_levels:
            candidate_levels.append("C1_readonly_or_unknown")
            tool_name_reasons.append("tool_name_requires_command_audit_no_arguments")

    max_command_risk = _max_command_risk_level(candidate_levels)
    if max_command_risk == "C4_catastrophic_or_out_of_sandbox":
        decision_if_enabled = "would_require_c4_confirmation"
    elif max_command_risk == "C3_codex_governed_destructive":
        decision_if_enabled = "allow_codex_governed"
    elif max_command_risk == "C2_routine_side_effect":
        decision_if_enabled = "allow_routine_side_effect"
    else:
        decision_if_enabled = "observe_only"

    argument_preview, argument_preview_truncated = _truncate_middle_text(
        json.dumps(arguments, ensure_ascii=False, sort_keys=True),
        preview_chars,
    )

    return {
        "tool_call_id": tool_call.get("id"),
        "tool_name": name,
        "tool_name_risk": tool_name_risk,
        "command_risk": max_command_risk,
        "decision_if_enabled": decision_if_enabled,
        "tool_name_reasons": tool_name_reasons,
        "candidate_count": len(text_candidates),
        "candidates": candidate_reports,
        "arguments_preview": argument_preview,
        "arguments_preview_truncated": argument_preview_truncated,
        "codex_sandbox_boundary": max_command_risk != "C4_catastrophic_or_out_of_sandbox",
    }


def _build_user_tool_command_risk_report(
    tool_calls: list[dict[str, Any]] | None,
    *,
    phase: str,
    response_id: str | None = None,
) -> dict[str, Any]:
    config = _user_tool_command_risk_env_config()
    calls = [call for call in (tool_calls or []) if isinstance(call, dict)]
    call_reports = [_classify_tool_call_command_risk(call) for call in calls]
    max_command_risk = _max_command_risk_level(
        [str(item.get("command_risk") or "C1_readonly_or_unknown") for item in call_reports]
    )
    if max_command_risk == "C4_catastrophic_or_out_of_sandbox":
        decision_if_enabled = "would_require_c4_confirmation"
    elif max_command_risk == "C3_codex_governed_destructive":
        decision_if_enabled = "allow_codex_governed"
    elif max_command_risk == "C2_routine_side_effect":
        decision_if_enabled = "allow_routine_side_effect"
    else:
        decision_if_enabled = "observe_only"

    c4_call_reports = [
        item
        for item in call_reports
        if item.get("command_risk") == "C4_catastrophic_or_out_of_sandbox"
    ]
    c4_gate_triggered = bool(c4_call_reports)
    c4_gate_reasons = sorted(
        {
            reason
            for item in c4_call_reports
            for candidate in item.get("candidates", [])
            for reason in candidate.get("reasons", [])
        }
    )
    c4_gate_argument_previews = [
        {
            "tool_call_id": item.get("tool_call_id"),
            "tool_name": item.get("tool_name"),
            "arguments_preview": item.get("arguments_preview"),
            "arguments_preview_truncated": item.get("arguments_preview_truncated"),
            "candidate_previews": [
                {
                    "path": candidate.get("path"),
                    "preview": candidate.get("preview"),
                    "preview_truncated": candidate.get("preview_truncated"),
                    "reasons": candidate.get("reasons", []),
                }
                for candidate in item.get("candidates", [])
                if candidate.get("risk") == "C4_catastrophic_or_out_of_sandbox"
            ],
        }
        for item in c4_call_reports
    ]

    return {
        "version": PROXY_VERSION,
        "mode": config["mode"],
        "enabled": bool(config["enabled"]),
        "active": False,
        "policy_is_dry_run_only": config["mode"] == "dry_run",
        "phase": phase,
        "response_id": response_id,
        "tool_call_count": len(calls),
        "tool_names": [item.get("tool_name") for item in call_reports],
        "max_command_risk": max_command_risk,
        "decision_if_enabled": decision_if_enabled,
        "tool_calls": call_reports,
        "proxy_gate_scope": "C4_only_future_gate",
        "codex_is_default_sandbox_boundary": True,
        "c4_gate_mode": "dry_run_fields_only",
        "c4_gate_triggered": c4_gate_triggered,
        "c4_gate_action": "would_suppress_and_explain" if c4_gate_triggered else "allow",
        "c4_gate_tool_call_ids": [item.get("tool_call_id") for item in c4_call_reports],
        "c4_gate_tool_names": [item.get("tool_name") for item in c4_call_reports],
        "c4_gate_reasons": c4_gate_reasons,
        "c4_gate_argument_previews": c4_gate_argument_previews,
        "c4_gate_confirmation_required": c4_gate_triggered,
        "c4_gate_resume_supported": False,
        "c4_gate_effective": False,
        "notes": [
            "dry_run_only_no_tool_execution_changes",
            "command_risk_arguments_are_available_only_after_upstream_tool_call",
            "P1c does not enable destructive command blocking yet",
            "proxy_must_not_create_a_narrower_boundary_than_codex_for_normal_development",
            "only_C4_catastrophic_or_out_of_sandbox_is_a_future_proxy_gate_candidate",
            "v2.7a42a1_adds_c4_gate_dry_run_fields_without_blocking",
        ],
    }

def _user_tool_control_suppressed_assistant_content(
    report: dict[str, Any] | None,
    tool_names: list[str],
) -> str:
    signal = str((report or {}).get("user_signal") or "")
    decision = str((report or {}).get("decision_if_enabled") or "")
    tool_part = ", ".join(name for name in tool_names if name) or "tool_call"

    if signal == "explicit_tool_stop":
        return (
            "Tool execution was paused for this turn because the latest user message "
            "asked not to continue tool or command execution. No tool calls were run. "
            f"Suppressed tool calls: {tool_part}."
        )
    if signal == "answer_or_explain_only":
        return (
            "Tool execution was paused for this turn because the latest user message "
            "asked for an answer or explanation first. No tool calls were run. "
            f"Suppressed tool calls: {tool_part}."
        )
    if signal == "ordered_explain_then_continue" or decision == "split_turn_required":
        return (
            "Tool execution was paused for this turn because the latest user message "
            "asked for an explanation before continuing. This requires a split turn: "
            "answer or explain first, then run tools only after the user continues. "
            f"Suppressed tool calls: {tool_part}."
        )
    return (
        "Tool execution was paused for this turn by the user tool-control policy. "
        f"No tool calls were run. Suppressed tool calls: {tool_part}."
    )


def _user_tool_control_suppressed_deepseek_response(
    deepseek_response: dict[str, Any],
    report: dict[str, Any] | None,
    tool_calls: list[dict[str, Any]],
) -> dict[str, Any]:
    suppressed_response = deepcopy(deepseek_response)
    tool_names: list[str] = []
    for tool_call in tool_calls:
        if isinstance(tool_call, dict):
            function = tool_call.get("function") or {}
            if isinstance(function, dict):
                tool_names.append(str(function.get("name") or ""))

    choices = suppressed_response.get("choices") or []
    if not choices:
        suppressed_response["choices"] = [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": _user_tool_control_suppressed_assistant_content(report, tool_names),
                },
                "finish_reason": "stop",
            }
        ]
        return suppressed_response

    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        first_choice = {}
        choices[0] = first_choice
    first_choice["message"] = {
        "role": "assistant",
        "content": _user_tool_control_suppressed_assistant_content(report, tool_names),
    }
    first_choice["finish_reason"] = "stop"
    return suppressed_response

def _assistant_message_is_tool_pause_or_explanation_intent(
    assistant_message: dict[str, Any],
) -> bool:
    content = _plain_text_from_content(assistant_message.get("content", ""))
    normalized = " ".join(content.strip().lower().split())
    if not normalized:
        return False

    pause_markers = [
        "暂停执行",
        "暂停操作",
        "不继续执行",
        "不要继续执行",
        "别继续执行",
        "不再执行",
        "不要再执行",
        "别再执行",
        "不要再继续执行",
        "别再继续执行",
        "先不执行",
        "先不要执行",
        "先别执行",
        "先不继续",
        "先不要继续",
        "先别继续",
        "停止执行",
        "停止操作",
        "不要执行命令",
        "不要继续执行命令",
        "别继续执行命令",
        "不要运行命令",
        "不要跑命令",
        "不调用工具",
        "不要调用工具",
        "别调用工具",
        "不用工具",
        "不运行命令",
        "不跑命令",
        "pause tool",
        "pause execution",
        "pause the task",
        "stop running",
        "stop executing",
        "not continue executing",
        "do not continue executing",
        "don't continue executing",
        "dont continue executing",
        "not use tools",
        "do not use tools",
        "don't use tools",
        "dont use tools",
        "without tools",
        "no more tools",
        "do not run commands",
        "don't run commands",
        "dont run commands",
        "do not execute commands",
        "don't execute commands",
        "dont execute commands",
    ]
    explain_markers = [
        "先解释",
        "解释清楚",
        "先说明",
        "说明原因",
        "先回答",
        "向你解释",
        "给出解释",
        "answer first",
        "explain first",
        "explain clearly",
        "explain why",
        "provide an explanation",
    ]
    user_reference_markers = [
        "你要求",
        "按照你的要求",
        "你让我",
        "you asked",
        "as requested",
        "per your request",
    ]

    has_pause = any(marker in normalized for marker in pause_markers)
    has_explain = any(marker in normalized for marker in explain_markers)
    refers_to_user_request = any(marker in normalized for marker in user_reference_markers)

    return (has_pause and has_explain) or (has_pause and refers_to_user_request)

def _assistant_message_needs_liveness_guard(
    assistant_message: dict[str, Any],
    *,
    tools_available: bool,
) -> bool:
    if not tools_available:
        return False
    if assistant_message.get("tool_calls"):
        return False
    if _assistant_message_is_tool_pause_or_explanation_intent(assistant_message):
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
    session_id: str | None = None,
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
        "clarification, explicitly cannot continue, or says it will pause or stop "
        "tool execution and answer or explain first.\n"
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
    user_tool_control_policy_report: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    session_id = _session_id_from_request_payload(request_payload)
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
        session_id=session_id,
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
        "user_tool_control_liveness_retry_suppressed": False,
    }
    tool_control_liveness_suppressed = _user_tool_control_should_suppress_liveness_retry(
        user_tool_control_policy_report
    )
    if tool_control_liveness_suppressed:
        liveness_report["user_tool_control_liveness_retry_suppressed"] = True
        liveness_report["guard_reason"] = "user_tool_control_policy_suppressed_liveness_retry"
        if isinstance(user_tool_control_policy_report, dict):
            user_tool_control_policy_report["liveness_retry_suppressed"] = True
            _write_user_tool_control_policy_report(user_tool_control_policy_report)

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
            and not tool_control_liveness_suppressed
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
                    session_id=session_id,
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
                session_id=session_id,
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

        user_tool_command_risk_report = _build_user_tool_command_risk_report(
            tool_calls,
            phase="post_upstream_before_proxy_execution",
            response_id=response_id,
        )
        _write_user_tool_command_risk_report(user_tool_command_risk_report)
        command_risk_trace_report = deepcopy(user_tool_command_risk_report)
        command_risk_trace_report["command_risk_response_id"] = command_risk_trace_report.pop(
            "response_id",
            None,
        )
        _debug_trace_event(
            response_id,
            "user_tool_command_risk_dry_run",
            **command_risk_trace_report,
        )

        if _user_tool_command_risk_should_suppress_tool_calls(user_tool_command_risk_report):
            user_tool_command_risk_report["active"] = True
            user_tool_command_risk_report["c4_gate_effective"] = True
            user_tool_command_risk_report["c4_gate_action"] = "suppress_and_explain"
            _write_user_tool_command_risk_report(user_tool_command_risk_report)
            _debug_trace_event(
                response_id,
                "user_tool_command_risk_c4_gate_suppressed",
                **{
                    key: value
                    for key, value in user_tool_command_risk_report.items()
                    if key != "response_id"
                },
            )
            liveness_report["guard_reason"] = "user_tool_command_risk_c4_gate_suppressed"
            _write_agent_liveness_guard_report(liveness_report)
            return (
                _user_tool_command_risk_suppressed_deepseek_response(
                    deepseek_response,
                    user_tool_command_risk_report,
                ),
                history_messages,
            )


        if _user_tool_control_should_suppress_post_upstream_tool_calls(
            user_tool_control_policy_report
        ):
            suppressed_tool_names: list[str] = []
            if isinstance(tool_calls, list):
                for tool_call in tool_calls:
                    if isinstance(tool_call, dict):
                        function = tool_call.get("function") or {}
                        if isinstance(function, dict):
                            suppressed_tool_names.append(str(function.get("name") or ""))
            if isinstance(user_tool_control_policy_report, dict):
                user_tool_control_policy_report["tool_calls_suppressed_post_upstream"] = suppressed_tool_names
                user_tool_control_policy_report["suppression_message_emitted"] = True
                _write_user_tool_control_policy_report(user_tool_control_policy_report)
            liveness_report["guard_reason"] = "user_tool_control_policy_suppressed_tool_calls"
            liveness_report["final_has_tool_calls"] = False
            liveness_report["suppressed_tool_call_count"] = len(tool_calls) if isinstance(tool_calls, list) else 0
            liveness_report["suppressed_tool_names"] = suppressed_tool_names
            _write_agent_liveness_guard_report(liveness_report)
            return (
                _user_tool_control_suppressed_deepseek_response(
                    deepseek_response,
                    user_tool_control_policy_report,
                    tool_calls,
                ),
                history_messages,
            )

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

        if result.get("provider") not in {"mock", "glm", "zai", "zhipu", "zhipuai", "bigmodel", "qwen_image", "qwen_image_beijing", "qwen_image_singapore"}:
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


def _stable_deepseek_json_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _stable_deepseek_json_value(value[key]) for key in sorted(value, key=lambda item: str(item))}
    if isinstance(value, list):
        return [_stable_deepseek_json_value(item) for item in value]
    return value


def _stable_deepseek_tools(tools: list[dict[str, Any]] | None) -> list[dict[str, Any]] | None:
    if not tools:
        return None
    stable_tools = [_stable_deepseek_json_value(tool) for tool in tools]

    def _tool_sort_key(tool: Any) -> tuple[str, str, str]:
        if not isinstance(tool, dict):
            return ("", "", json.dumps(tool, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str))
        function = tool.get("function")
        function_name = str(function.get("name") or "") if isinstance(function, dict) else ""
        return (
            str(tool.get("type") or ""),
            function_name,
            json.dumps(tool, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str),
        )

    return sorted(stable_tools, key=_tool_sort_key)


def _deepseek_cache_user_id(request_payload: dict[str, Any] | None, *, model: str) -> str | None:
    if os.environ.get("DEEPSEEK_PROXY_DISABLE_STABLE_USER_ID", "").strip().lower() in {"1", "true", "yes", "on"}:
        return None
    configured = os.environ.get("DEEPSEEK_PROXY_USER_ID", "").strip()
    if configured:
        return configured[:128]
    session_id = _session_id_from_request_payload(request_payload)
    route = "thinking" if _thinking_enabled() else "non_thinking"
    provider = os.environ.get("DEEPSEEK_PROXY_MODEL_PROVIDER", "deepseek")
    try:
        project_hash = hashlib.sha256(str(Path.cwd().resolve()).encode("utf-8", errors="replace")).hexdigest()[:16]
    except Exception:
        project_hash = "unknown_project"
    material = "|".join([
        f"provider={provider}",
        f"route={route}",
        f"model={model}",
        f"project={project_hash}",
        f"session={session_id or 'profile_route'}",
    ])
    digest = hashlib.sha256(material.encode("utf-8", errors="replace")).hexdigest()[:32]
    return f"codeepseedex_{route}_{digest}"[:128]


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

    user_id = _deepseek_cache_user_id(request_payload, model=model)
    if user_id:
        payload["user_id"] = user_id

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

    stable_tools = _stable_deepseek_tools(tools)
    if stable_tools:
        payload["tools"] = stable_tools
        if isinstance(request_payload, dict) and request_payload.get("tool_choice") is not None:
            payload["tool_choice"] = request_payload.get("tool_choice")
        else:
            payload["tool_choice"] = "auto"

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
                "compaction_prompt_fingerprint",
                "compact_material_classifier_dry_run",
                "retained_recent_policy",
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


def _runtime_payload_guard_observed_at() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _runtime_payload_guard_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _runtime_payload_guard_ratio(current_chars: int | None, limit_chars: int | None) -> float | None:
    if current_chars is None or limit_chars is None or limit_chars <= 0:
        return None
    return min(1.0, max(0.0, current_chars / limit_chars))


def _runtime_payload_guard_status(
    *,
    current_chars: int | None,
    limit_chars: int | None,
    terminal: bool,
    terminal_status: str,
) -> str:
    if current_chars is None or limit_chars is None or limit_chars <= 0:
        return "unavailable"
    if terminal:
        return terminal_status
    if current_chars >= limit_chars:
        return "triggered"
    ratio = current_chars / limit_chars
    if ratio >= 0.85:
        return "near_threshold"
    return "not_triggered"


def _runtime_payload_guard_report_snapshot(
    report: Any,
    *,
    kind: str,
    fallback_last_report: Any = None,
) -> dict[str, Any]:
    if isinstance(report, dict):
        flag_name = "compacted" if kind == "compaction" else "trimmed"
        keys = [
            "version",
            "enabled",
            flag_name,
            "reason",
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
            "max_context_chars",
            "max_tool_output_chars",
            "keep_recent_messages",
            "observed_at",
            "source",
            "material",
            "compaction_prompt_fingerprint",
            "compact_material_classifier_dry_run",
            "retained_recent_policy",
        ]
        snapshot = {
            "exists": True,
            "source": f"in_memory_runtime_{kind}_report",
            "reason": report.get("reason") or ("not_triggered_yet" if not report.get(flag_name) else flag_name),
        }
        for key in keys:
            if key in report:
                snapshot[key] = report.get(key)
        return snapshot

    if isinstance(fallback_last_report, dict) and fallback_last_report.get("exists"):
        snapshot = dict(fallback_last_report)
        snapshot["source"] = "debug_last_report_summary"
        snapshot.setdefault("reason", "debug_last_report_available_but_not_used_for_realtime_current_chars")
        return snapshot

    return {
        "exists": False,
        "reason": "no_runtime_payload_guard_observation_yet",
        "action": "send a model request through this dsproxy route, then re-check dsproxy status --weclaw-json",
    }



def _runtime_payload_guard_contract(
    context_status: dict[str, Any],
    *,
    compaction_report: Any = None,
    trimming_report: Any = None,
) -> dict[str, Any]:
    compaction_status = context_status.get("compaction") if isinstance(context_status, dict) else {}
    trimming_status = context_status.get("trimming") if isinstance(context_status, dict) else {}
    if not isinstance(compaction_status, dict):
        compaction_status = {}
    if not isinstance(trimming_status, dict):
        trimming_status = {}

    compaction_config = compaction_status.get("config") if isinstance(compaction_status.get("config"), dict) else {}
    trimming_config = trimming_status.get("config") if isinstance(trimming_status.get("config"), dict) else {}
    compaction_last_report = compaction_status.get("last_report") if isinstance(compaction_status.get("last_report"), dict) else {}
    trimming_last_report = trimming_status.get("last_report") if isinstance(trimming_status.get("last_report"), dict) else {}

    compaction_report_dict = compaction_report if isinstance(compaction_report, dict) else None
    trimming_report_dict = trimming_report if isinstance(trimming_report, dict) else None

    compaction_after = _runtime_payload_guard_int(compaction_report_dict.get("after_chars") if compaction_report_dict else None)
    compaction_before = _runtime_payload_guard_int(compaction_report_dict.get("before_chars") if compaction_report_dict else None)
    trimming_after = _runtime_payload_guard_int(trimming_report_dict.get("after_chars") if trimming_report_dict else None)
    trimming_before = _runtime_payload_guard_int(trimming_report_dict.get("before_chars") if trimming_report_dict else None)

    compaction_raw = compaction_before if compaction_before is not None else compaction_after
    trimming_raw = trimming_before if trimming_before is not None else trimming_after
    current_chars = trimming_after if trimming_after is not None else compaction_after

    current_source = "unavailable"
    current_precision = "unavailable"
    observed_at = None
    if trimming_after is not None:
        current_source = "live_request_payload"
        current_precision = "exact"
        observed_at = trimming_report_dict.get("observed_at") if trimming_report_dict else None
    elif compaction_after is not None:
        current_source = "runtime_context_builder"
        current_precision = "exact"
        observed_at = compaction_report_dict.get("observed_at") if compaction_report_dict else None

    policy_decision = compaction_report_dict.get("policy_decision") if compaction_report_dict else None
    if not isinstance(policy_decision, dict):
        policy_decision = {}

    trigger_chars = _runtime_payload_guard_int(policy_decision.get("effective_trigger_chars") or (compaction_report_dict or {}).get("effective_trigger_chars") or (compaction_report_dict or {}).get("trigger_chars") or compaction_config.get("trigger_chars"))
    target_chars = _runtime_payload_guard_int(policy_decision.get("effective_target_chars") or (compaction_report_dict or {}).get("effective_target_chars") or (compaction_report_dict or {}).get("target_chars") or compaction_config.get("target_chars"))
    max_context_chars = _runtime_payload_guard_int((trimming_report_dict or {}).get("max_context_chars") or trimming_config.get("max_context_chars"))

    compaction_retention_ratio = _runtime_payload_guard_ratio(compaction_after, compaction_raw)
    trimming_retention_ratio = _runtime_payload_guard_ratio(trimming_after, trimming_raw)
    compaction_capacity_ratio = _runtime_payload_guard_ratio(compaction_raw, trigger_chars)
    trimming_capacity_ratio = _runtime_payload_guard_ratio(trimming_raw, max_context_chars)

    compaction_available = bool(compaction_config.get("enabled", True)) and compaction_after is not None and compaction_raw is not None
    trimming_available = trimming_after is not None and trimming_raw is not None

    compaction_section = {
        "available": compaction_available,
        "policy": compaction_config.get("policy"),
        "trigger_chars": trigger_chars,
        "trigger_chars_source": "context_compaction_config.effective_trigger_chars_or_config_trigger_chars",
        "target_chars": target_chars,
        "target_chars_source": "context_compaction_config.effective_target_chars_or_config_target_chars",
        "keep_recent_messages": _runtime_payload_guard_int(compaction_config.get("keep_recent_messages")),
        "current_chars": compaction_after,
        "current_chars_available": compaction_after is not None,
        "current_chars_source": "runtime_context_builder" if compaction_after is not None else "unavailable",
        "current_chars_precision": "exact" if compaction_after is not None else "unavailable",
        "current_chars_observed_at": (compaction_report_dict or {}).get("observed_at") if compaction_report_dict else None,
        "usage_ratio": compaction_retention_ratio,
        "progress_numerator_chars": compaction_after,
        "progress_denominator_chars": compaction_raw,
        "progress_ratio": compaction_retention_ratio,
        "progress_basis": "post_compaction_current_chars_over_raw_uncompressed_current_chars",
        "raw_uncompressed_current_chars": compaction_raw,
        "post_compaction_current_chars": compaction_after,
        "retention_numerator_chars": compaction_after,
        "retention_denominator_chars": compaction_raw,
        "retention_ratio": compaction_retention_ratio,
        "retention_basis": "post_compaction_current_chars_over_raw_uncompressed_current_chars",
        "capacity_progress_numerator_chars": compaction_raw,
        "capacity_progress_denominator_chars": trigger_chars,
        "capacity_progress_ratio": compaction_capacity_ratio,
        "capacity_progress_basis": "raw_uncompressed_current_chars_over_trigger_chars",
        "remaining_chars": max(0, trigger_chars - compaction_raw) if compaction_raw is not None and trigger_chars is not None else None,
        "status": _runtime_payload_guard_status(current_chars=compaction_raw, limit_chars=trigger_chars, terminal=bool((compaction_report_dict or {}).get("compacted")), terminal_status="compacted"),
        "last_report": _runtime_payload_guard_report_snapshot(compaction_report_dict, kind="compaction", fallback_last_report=compaction_last_report),
        "reason": None if compaction_available else "current_compaction_chars_unavailable",
        "action": None if compaction_available else "send a model request through this dsproxy route, then re-check status",
    }

    trimming_section = {
        "available": trimming_available,
        "max_context_chars": max_context_chars,
        "max_context_chars_source": "context_trimming_config.max_context_chars",
        "max_tool_output_chars": _runtime_payload_guard_int(trimming_config.get("max_tool_output_chars")),
        "keep_recent_messages": _runtime_payload_guard_int(trimming_config.get("keep_recent_messages")),
        "current_chars": trimming_after,
        "current_chars_available": trimming_after is not None,
        "current_chars_source": "live_request_payload" if trimming_after is not None else "unavailable",
        "current_chars_precision": "exact" if trimming_after is not None else "unavailable",
        "current_chars_observed_at": (trimming_report_dict or {}).get("observed_at") if trimming_report_dict else None,
        "usage_ratio": trimming_retention_ratio,
        "progress_numerator_chars": trimming_after,
        "progress_denominator_chars": trimming_raw,
        "progress_ratio": trimming_retention_ratio,
        "progress_basis": "post_trim_current_chars_over_raw_uncompressed_current_chars",
        "raw_uncompressed_current_chars": trimming_raw,
        "post_trim_current_chars": trimming_after,
        "retention_numerator_chars": trimming_after,
        "retention_denominator_chars": trimming_raw,
        "retention_ratio": trimming_retention_ratio,
        "retention_basis": "post_trim_current_chars_over_raw_uncompressed_current_chars",
        "capacity_progress_numerator_chars": trimming_raw,
        "capacity_progress_denominator_chars": max_context_chars,
        "capacity_progress_ratio": trimming_capacity_ratio,
        "capacity_progress_basis": "raw_uncompressed_current_chars_over_max_context_chars",
        "remaining_chars": max(0, max_context_chars - trimming_raw) if trimming_raw is not None and max_context_chars is not None else None,
        "status": _runtime_payload_guard_status(current_chars=trimming_raw, limit_chars=max_context_chars, terminal=bool((trimming_report_dict or {}).get("trimmed")), terminal_status="trimmed"),
        "last_report": _runtime_payload_guard_report_snapshot(trimming_report_dict, kind="trimming", fallback_last_report=trimming_last_report),
        "reason": None if trimming_available else "current_trimming_chars_unavailable",
        "action": None if trimming_available else "send a model request through this dsproxy route, then re-check status",
    }

    available = bool(compaction_available or trimming_available)
    return {
        "available": available,
        "unit": "chars",
        "current_chars": current_chars,
        "current_chars_available": current_chars is not None,
        "current_chars_source": current_source,
        "current_chars_precision": current_precision,
        "current_chars_observed_at": observed_at,
        "source": "in_memory_runtime_payload_guard_snapshot",
        "precision": current_precision,
        "reason": None if available else "no_live_runtime_payload_guard_observation_yet",
        "action": None if available else "send a model request through this dsproxy route, then re-check status",
        "compaction": compaction_section,
        "trimming": trimming_section,
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
            "api_key_configured": bool(_web_search_api_key_for_provider(web_provider)) if web_provider not in {"mock", "disabled", "off", "none"} else None,
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
            "api_key_configured": bool(_image_api_key_for_provider(image_provider)) if image_provider not in {"mock", "disabled", "off", "none"} else None,
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



def _runtime_codex_config_path() -> Path:
    return Path(os.environ.get("CODEX_CONFIG_FILE", str(Path.home() / ".codex" / "config.toml"))).expanduser()


def _runtime_parse_simple_toml_sections(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    sections: dict[str, dict[str, str]] = {}
    current: str | None = None
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = re.match(r"^\[([^\]]+)\]\s*$", stripped)
        if match:
            current = match.group(1).strip()
            sections.setdefault(current, {})
            continue
        if current and "=" in stripped:
            key, value = stripped.split("=", 1)
            key = key.strip()
            value = value.strip()
            if value.startswith('"') and value.endswith('"'):
                value = value[1:-1].replace('\\"', '"').replace("\\\\", "\\")
            else:
                value = value.split("#", 1)[0].strip()
            sections[current][key] = value
    return sections


def _runtime_int_or_zero(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
_PROFILE_TOKENIZER_CACHE: dict[str, Any] = {}


def _profile_tokenizer_requested_categories() -> list[str]:
    return [
        "user",
        "user_history",
        "assistant_history",
        "tool_output",
        "environment",
        "system",
        "developer",
        "compaction_summary",
        "runtime_injected",
        "other_prompt",
    ]


def _profile_tokenizer_kind_for_model(model: str | None, provider: str | None = None) -> str | None:
    provider_key = str(provider or os.environ.get("DEEPSEEK_PROXY_MODEL_PROVIDER") or "deepseek").strip().lower()
    model_key = str(model or "").strip().lower()
    if provider_key == "deepseek" or model_key.startswith("deepseek-"):
        return "deepseek_official_current"
    return None


def _profile_tokenizer_resource_root() -> Path:
    raw = os.environ.get("DEEPSEEK_PROXY_TOKENIZER_RESOURCE_DIR", "").strip()
    if raw:
        return Path(raw).expanduser()

    install_root_raw = os.environ.get("DEEPSEEK_PROXY_INSTALL_DIR", "").strip()
    if install_root_raw:
        return Path(install_root_raw).expanduser() / "resources" / "tokenizers"

    return Path.home() / ".local" / "share" / "deepseek-responses-proxy" / "resources" / "tokenizers"


def _profile_tokenizer_json_candidates(kind: str) -> list[tuple[Path, str]]:
    candidates: list[tuple[Path, str]] = []
    for name in ["DEEPSEEK_PROXY_PROFILE_TOKENIZER_JSON", "DEEPSEEK_PROXY_DEEPSEEK_TOKENIZER_JSON"]:
        raw = os.environ.get(name)
        if raw:
            candidates.append((Path(raw).expanduser(), f"env.{name}"))

    resource_root = _profile_tokenizer_resource_root()
    candidates.append((resource_root / kind / "tokenizer.json", "managed_resource"))

    if kind == "deepseek_official_current":
        candidates.append((resource_root / "deepseek_v3" / "tokenizer.json", "legacy_managed_resource"))

    package_root = Path(__file__).resolve().parent / "resources" / "tokenizers"
    candidates.append((package_root / kind / "tokenizer.json", "package_resource"))
    if kind == "deepseek_official_current":
        candidates.append((package_root / "deepseek_v3" / "tokenizer.json", "legacy_package_resource"))

    return candidates


def _profile_tokenizer_contract(model: str | None, provider: str | None = None) -> dict[str, Any]:
    provider_value = str(provider or os.environ.get("DEEPSEEK_PROXY_MODEL_PROVIDER") or "deepseek")
    kind = _profile_tokenizer_kind_for_model(model, provider_value)
    if kind is None:
        return {
            "available": False,
            "unit": "tokens",
            "model": str(model or "") or None,
            "provider": provider_value,
            "tokenizer_kind": None,
            "source": "unsupported_profile_provider",
            "source_kind": "unsupported",
            "reason": "profile_tokenizer_not_configured_for_provider",
            "action": "add an audited tokenizer binding for this profile provider before displaying local token estimates",
        }

    checked: list[dict[str, Any]] = []
    selected_path: Path | None = None
    selected_source = None
    for path, source_kind in _profile_tokenizer_json_candidates(kind):
        checked.append({"path": str(path), "source_kind": source_kind, "exists": path.is_file()})
        if path.is_file() and selected_path is None:
            selected_path = path
            selected_source = source_kind

    if selected_path is None:
        return {
            "available": False,
            "unit": "tokens",
            "model": str(model or "") or None,
            "provider": provider_value,
            "tokenizer_kind": kind,
            "source": None,
            "source_kind": None,
            "reason": "profile_tokenizer_json_not_found",
            "action": "run dsproxy tokenizer sync deepseek --json or set DEEPSEEK_PROXY_DEEPSEEK_TOKENIZER_JSON",
            "checked": checked,
        }

    try:
        import tokenizers  # type: ignore  # noqa: F401
    except Exception as exc:
        return {
            "available": False,
            "unit": "tokens",
            "model": str(model or "") or None,
            "provider": provider_value,
            "tokenizer_kind": kind,
            "source": str(selected_path),
            "source_kind": selected_source,
            "reason": "python_tokenizers_package_unavailable",
            "error": f"{type(exc).__name__}: {exc}",
            "action": "install the tokenizers Python package from the project dependencies",
            "checked": checked,
        }

    return {
        "available": True,
        "unit": "tokens",
        "model": str(model or "") or None,
        "provider": provider_value,
        "tokenizer_kind": kind,
        "source": str(selected_path),
        "source_kind": selected_source,
        "reason": None,
        "action": None,
        "checked": checked,
    }


def _load_profile_tokenizer(contract: dict[str, Any]) -> Any | None:
    if not isinstance(contract, dict) or not contract.get("available"):
        return None

    source = str(contract.get("source") or "")
    if not source:
        return None

    cached = _PROFILE_TOKENIZER_CACHE.get(source)
    if cached is not None:
        return cached

    from tokenizers import Tokenizer  # type: ignore

    tokenizer = Tokenizer.from_file(source)
    _PROFILE_TOKENIZER_CACHE[source] = tokenizer
    return tokenizer


def _profile_tokenizer_text_preview(text: str, limit: int = 80) -> dict[str, str]:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= limit * 2:
        return {"preview": compact, "head": compact, "tail": ""}
    return {
        "preview": compact[:limit] + " ... " + compact[-limit:],
        "head": compact[:limit],
        "tail": compact[-limit:],
    }


def _profile_tokenizer_segment_source_and_category(
    message: dict[str, Any],
    *,
    index: int,
    latest_plain_user_index: int | None,
) -> tuple[str, str]:
    role = str(message.get("role") or "").strip().lower()
    content = _plain_text_from_content(message.get("content", ""))
    stripped = content.lstrip()
    lowered_head = stripped[:600].lower()

    if "[deepseek-proxy persistent compaction summary]" in content:
        return "compaction", "compaction_summary"

    if role == "system":
        return "system", "system"
    if role == "developer":
        return "developer", "developer"
    if role == "assistant":
        return "history", "assistant_history"
    if role == "tool":
        return "tool", "tool_output"

    if role == "user":
        if stripped.startswith("[tool output transcript]") or stripped.startswith("[tool call transcript]"):
            return "tool", "tool_output"

        if (
            "agents.md instructions" in lowered_head
            or "<instructions>" in lowered_head
            or "<environment_context>" in lowered_head
            or "memory writing agent" in lowered_head
            or "memory_summary begins" in lowered_head
            or "/.codex/memories" in lowered_head
            or "codex/memories" in lowered_head
            or stripped.startswith("<permissions instructions>")
        ):
            return "environment", "environment"

        if latest_plain_user_index is not None and index == latest_plain_user_index:
            return "codex_request", "user"
        return "history", "user_history"

    return "codex_request", "other_prompt"


def _profile_tokenizer_plain_user_candidate(message: dict[str, Any]) -> bool:
    source, category = _profile_tokenizer_segment_source_and_category(
        message,
        index=-1,
        latest_plain_user_index=None,
    )
    return str(message.get("role") or "").strip().lower() == "user" and source in {"history", "codex_request"} and category == "user_history"
def _profile_tokenizer_message_category(message: dict[str, Any]) -> str:
    _source, category = _profile_tokenizer_segment_source_and_category(
        message,
        index=-1,
        latest_plain_user_index=None,
    )
    return "user" if category == "user_history" else category


def _profile_tokenizer_message_text(message: dict[str, Any]) -> str:
    chunks: list[str] = []
    content = _plain_text_from_content(message.get("content", ""))
    if content:
        chunks.append(content)

    reasoning_content = message.get("reasoning_content")
    if isinstance(reasoning_content, str) and reasoning_content:
        chunks.append(reasoning_content)

    tool_calls = message.get("tool_calls")
    if isinstance(tool_calls, list):
        for tool_call in tool_calls:
            if not isinstance(tool_call, dict):
                continue
            function = tool_call.get("function") if isinstance(tool_call.get("function"), dict) else {}
            name = function.get("name") if isinstance(function, dict) else None
            arguments = function.get("arguments") if isinstance(function, dict) else None
            if name:
                chunks.append(str(name))
            if arguments:
                chunks.append(arguments if isinstance(arguments, str) else json.dumps(arguments, ensure_ascii=False))

    return "\n".join(chunks)


def _profile_tokenizer_count_text(tokenizer: Any, text: str) -> int:
    if not text:
        return 0
    encoded = tokenizer.encode(text)
    ids = getattr(encoded, "ids", None)
    if isinstance(ids, list):
        return len(ids)
    try:
        return len(encoded)
    except TypeError:
        return 0


def _profile_tokenizer_unavailable_report(
    *,
    profile: str,
    model: str | None,
    provider: str | None,
    reason: str | None = None,
) -> dict[str, Any]:
    contract = _profile_tokenizer_contract(model, provider)
    tokenizer_available = bool(contract.get("available"))
    split = _weclaw_prompt_subcategory_split_contract(
        None,
        tokenizer_contract=contract,
        no_observed_prompt=True,
    )
    summary_reason = (
        "profile_tokenizer_available_but_no_observed_prompt"
        if tokenizer_available
        else str(contract.get("reason") or reason or "profile_tokenizer_unavailable")
    )
    return {
        "available": tokenizer_available,
        "unit": "tokens",
        "profile": profile,
        "model": str(model or "") or None,
        "provider": str(provider or os.environ.get("DEEPSEEK_PROXY_MODEL_PROVIDER") or "deepseek"),
        "tokenizer": contract,
        "precision": "local_profile_tokenizer_estimate" if tokenizer_available else "unavailable",
        "source": str(contract.get("source") or "unavailable") if tokenizer_available else "unavailable",
        "source_kind": str(contract.get("source_kind") or "unavailable") if tokenizer_available else "unavailable",
        "is_estimated": True if tokenizer_available else None,
        "billing_authoritative": False,
        "summary": {
            "available": False,
            "unit": "tokens",
            "reason": summary_reason,
            "action": (
                "send one model request through this route, then re-check dsproxy status --weclaw-json"
                if tokenizer_available
                else str(contract.get("action") or "run dsproxy tokenizer sync deepseek --json")
            ),
            "total_content_tokens": None,
            "message_count": 0,
        },
        "prompt_subcategory_split": split,
    }




def _profile_tokenizer_json_text(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except Exception:
        return str(value)


def _profile_tokenizer_json_component(tokenizer: Any, value: Any, *, name: str, source: str) -> dict[str, Any]:
    text = _profile_tokenizer_json_text(value)
    preview = _profile_tokenizer_text_preview(text)
    return {
        "name": name,
        "source": source,
        "available": True,
        "serialization": "json.dumps.ensure_ascii_false.sort_keys.compact",
        "local_tokens": _profile_tokenizer_count_text(tokenizer, text),
        "char_count": len(text),
        "sha256": hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest(),
        **preview,
    }


def _profile_tokenizer_observable_payload_report(
    payload: dict[str, Any] | None,
    tokenizer: Any,
    *,
    message_content_tokens: int,
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {
            "available": False,
            "reason": "chat_payload_not_available_to_profile_tokenizer_report",
            "source": None,
        }

    components: dict[str, Any] = {}
    components["message_content"] = {
        "name": "message_content",
        "source": "prompt_subcategory_split.categories_sum_tokens",
        "available": True,
        "local_tokens": int(message_content_tokens or 0),
        "char_count": None,
        "serialization": "profile_tokenizer_message_text_concat_by_message",
    }

    messages = payload.get("messages")
    if isinstance(messages, list):
        components["messages_json"] = _profile_tokenizer_json_component(
            tokenizer,
            messages,
            name="messages_json",
            source="chat_payload.messages",
        )

    tools = payload.get("tools")
    if isinstance(tools, list) and tools:
        components["tools_schema"] = _profile_tokenizer_json_component(
            tokenizer,
            tools,
            name="tools_schema",
            source="chat_payload.tools",
        )
    else:
        components["tools_schema"] = {
            "name": "tools_schema",
            "source": "chat_payload.tools",
            "available": True,
            "local_tokens": 0,
            "char_count": 0,
            "serialization": "absent_or_empty",
        }

    for key in ["tool_choice", "response_format"]:
        if key in payload and payload.get(key) is not None:
            components[key] = _profile_tokenizer_json_component(
                tokenizer,
                payload.get(key),
                name=key,
                source=f"chat_payload.{key}",
            )
        else:
            components[key] = {
                "name": key,
                "source": f"chat_payload.{key}",
                "available": True,
                "local_tokens": 0,
                "char_count": 0,
                "serialization": "absent_or_null",
            }

    request_option_keys = [
        key
        for key in ["model", "stream", "thinking", "reasoning_effort", "max_tokens", "temperature", "top_p", "stop"]
        if key in payload and payload.get(key) is not None
    ]
    request_options = {key: payload.get(key) for key in request_option_keys}
    components["request_options"] = _profile_tokenizer_json_component(
        tokenizer,
        request_options,
        name="request_options",
        source="chat_payload.non_prompt_control_fields",
    ) if request_options else {
        "name": "request_options",
        "source": "chat_payload.non_prompt_control_fields",
        "available": True,
        "local_tokens": 0,
        "char_count": 0,
        "serialization": "absent_or_empty",
    }

    full_payload = _profile_tokenizer_json_component(
        tokenizer,
        payload,
        name="full_payload_json",
        source="chat_payload.full_json",
    )

    semantic_prompt_component_names = ["message_content", "tools_schema", "tool_choice", "response_format"]
    semantic_prompt_candidate_tokens = sum(
        int((components.get(name) or {}).get("local_tokens") or 0)
        for name in semantic_prompt_component_names
    )
    observable_non_category_tokens = max(0, semantic_prompt_candidate_tokens - int(message_content_tokens or 0))

    return {
        "available": True,
        "unit": "tokens",
        "precision": "local_profile_tokenizer_json_serialized_estimate",
        "source": "deepseek_chat_payload_after_dsproxy_build_chat_payload",
        "components": components,
        "semantic_prompt_component_names": semantic_prompt_component_names,
        "semantic_prompt_candidate_tokens": semantic_prompt_candidate_tokens,
        "message_content_tokens": int(message_content_tokens or 0),
        "observable_non_category_tokens": observable_non_category_tokens,
        "full_payload_json_tokens": int(full_payload.get("local_tokens") or 0),
        "full_payload_json": full_payload,
        "notes": [
            "semantic_prompt_candidate_tokens adds message content and visible prompt-bearing API fields such as tools, tool_choice, and response_format.",
            "full_payload_json_tokens is a diagnostic upper-bound style estimate over the serialized local request payload and is not treated as provider billing truth.",
            "Provider prompt_tokens remain authoritative for billing; this report is for root-cause reconciliation only.",
        ],
    }


def _profile_tokenizer_report_for_messages(
    messages: list[dict[str, Any]],
    *,
    profile: str,
    model: str | None,
    provider: str | None = None,
    session_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    contract = _profile_tokenizer_contract(model, provider)
    if not contract.get("available"):
        unavailable = _profile_tokenizer_unavailable_report(profile=profile, model=model, provider=provider)
        unavailable["session_id"] = session_id
        unavailable["scope"] = "current_session" if session_id else "route_latest_observed_prompt"
        return unavailable

    try:
        tokenizer = _load_profile_tokenizer(contract)
    except Exception as exc:
        contract = {
            **contract,
            "available": False,
            "reason": "profile_tokenizer_load_failed",
            "error": f"{type(exc).__name__}: {exc}",
            "action": "verify the synced official DeepSeek tokenizer.json and tokenizers package",
        }
        return {
            "available": False,
            "unit": "tokens",
            "profile": profile,
            "session_id": session_id,
            "scope": "current_session" if session_id else "route_latest_observed_prompt",
            "model": str(model or "") or None,
            "provider": str(provider or os.environ.get("DEEPSEEK_PROXY_MODEL_PROVIDER") or "deepseek"),
            "tokenizer": contract,
            "summary": {"available": False, "total_content_tokens": None, "message_count": len(messages)},
            "prompt_subcategory_split": _weclaw_prompt_subcategory_split_contract(),
        }

    latest_plain_user_index: int | None = None
    for index, message in enumerate(messages):
        if isinstance(message, dict) and _profile_tokenizer_plain_user_candidate(message):
            latest_plain_user_index = index

    categories = {
        category: {"tokens": 0, "message_count": 0, "source": "dsproxy_deepseek_messages_after_payload_assembly"}
        for category in _profile_tokenizer_requested_categories()
    }
    message_reports: list[dict[str, Any]] = []
    segment_ledger: list[dict[str, Any]] = []
    total_tokens = 0

    for index, message in enumerate(messages):
        if not isinstance(message, dict):
            continue
        source, category = _profile_tokenizer_segment_source_and_category(
            message,
            index=index,
            latest_plain_user_index=latest_plain_user_index,
        )
        text = _profile_tokenizer_message_text(message)
        token_count = _profile_tokenizer_count_text(tokenizer, text)
        categories.setdefault(category, {"tokens": 0, "message_count": 0, "source": "dsproxy_deepseek_messages_after_payload_assembly"})
        categories[category]["tokens"] += token_count
        categories[category]["message_count"] += 1
        total_tokens += token_count

        digest = hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()
        preview = _profile_tokenizer_text_preview(text)
        segment = {
            "index": index,
            "source": source,
            "role": str(message.get("role") or ""),
            "category": category,
            "token_count": token_count,
            "char_count": len(text),
            "sha256": digest,
            **preview,
        }
        segment_ledger.append(segment)
        message_reports.append(
            {
                "index": index,
                "role": str(message.get("role") or ""),
                "source": source,
                "category": category,
                "tokens": token_count,
                "content_chars": len(text),
            }
        )

    category_totals = {category: int(item.get("tokens") or 0) for category, item in categories.items()}
    scope = "current_session" if session_id else "route_latest_observed_prompt"
    observable_payload = _profile_tokenizer_observable_payload_report(
        payload,
        tokenizer,
        message_content_tokens=total_tokens,
    )

    latest_prompt_segmentation = {
        "available": True,
        "unit": "tokens",
        "precision": "local_profile_tokenizer_estimate",
        "semantic_scope": "message_content_and_tool_call_arguments_after_dsproxy_payload_assembly",
        "scope": scope,
        "session_id": session_id,
        "profile": profile,
        "model": str(model or "") or None,
        "provider": str(provider or os.environ.get("DEEPSEEK_PROXY_MODEL_PROVIDER") or "deepseek"),
        "tokenizer_kind": contract.get("tokenizer_kind"),
        "tokenizer_source": contract.get("source"),
        "message_count": len(message_reports),
        "total_prompt_tokens_profile_tokenizer": total_tokens,
        "latest_plain_user_segment_index": latest_plain_user_index,
        "category_totals": category_totals,
        "segments": segment_ledger,
        "segments_tail": segment_ledger[-30:],
        "observable_payload": observable_payload,
        "notes": [
            "The user category is the latest ordinary user-role segment after dsproxy excludes Codex-injected environment/memory instructions and tool transcripts.",
            "The user_history category contains earlier ordinary user-role segments in the assembled prompt.",
            "Codex may encode tool transcripts, memory, environment, and historical context as role=user; dsproxy classifies these by content markers before computing Details.",
        ],
    }

    split = {
        "available": True,
        "unit": "tokens",
        "is_estimated": True,
        "precision": "local_profile_tokenizer_estimate",
        "source": f"dsproxy_profile_tokenizer.{contract.get('tokenizer_kind')}.tokenizer_json",
        "semantic_scope": "message_content_and_tool_call_arguments_after_dsproxy_payload_assembly",
        "scope": scope,
        "session_id": session_id,
        "tokenizer_kind": contract.get("tokenizer_kind"),
        "tokenizer_source": contract.get("source"),
        "categories": categories,
        "total_tokens": total_tokens,
        "message_count": len(message_reports),
        "latest_prompt_segmentation": latest_prompt_segmentation,
        "observable_payload": observable_payload,
        "missing": [],
        "notes": [
            "Provider usage totals remain authoritative for billing and aggregate prompt/completion/cache/reasoning fields.",
            "This split uses the active profile tokenizer and dsproxy message boundaries, but it is a local estimate because providers do not report prompt subcategory usage.",
            "The split counts message text, reasoning_content, and tool-call names/arguments after dsproxy payload assembly. Chat-template overhead is not assigned to a subcategory.",
            "The user bucket is the latest ordinary user segment, not all role=user segments.",
        ],
    }

    return {
        "available": True,
        "unit": "tokens",
        "profile": profile,
        "session_id": session_id,
        "scope": scope,
        "model": str(model or "") or None,
        "provider": str(provider or os.environ.get("DEEPSEEK_PROXY_MODEL_PROVIDER") or "deepseek"),
        "tokenizer": contract,
        "observable_payload": observable_payload,
        "summary": {
            "available": True,
            "total_content_tokens": total_tokens,
            "message_count": len(message_reports),
            "categories_with_tokens": [category for category, item in categories.items() if int(item.get("tokens") or 0) > 0],
            "precision": "local_profile_tokenizer_estimate",
            "is_estimated": True,
        },
        "prompt_subcategory_split": split,
        "latest_prompt_segmentation": latest_prompt_segmentation,
        "messages_tail": message_reports[-30:],
    }

def _weclaw_context_used_tokens_unavailable_contract() -> dict[str, Any]:
    return {
        "used_tokens": None,
        "used_tokens_available": False,
        "used_tokens_source": "not_reported",
        "used_tokens_reason": "context_used_tokens_not_reported_by_codex_or_provider",
        "used_tokens_action": "use latest_upstream_prompt_tokens when available; otherwise display an unavailable marker instead of deriving context usage from session totals",
        "used_tokens_precision": "unavailable",
        "used_tokens_is_estimated": False,
        "used_tokens_semantic_scope": "codex_internal_context_window_usage_unavailable",
        "latest_upstream_prompt_tokens": None,
    }


def _weclaw_context_limit_explanation(
    *,
    model_context_window: int,
    auto_compact_token_limit: int,
    effective_safe_window: int,
    model_catalog: Any,
) -> dict[str, Any]:
    catalog_tokens = None
    catalog_source = None
    if isinstance(model_catalog, dict):
        catalog_tokens = model_catalog.get("context_window_tokens")
        catalog_source = model_catalog.get("source")

    display_limit_tokens = model_context_window or effective_safe_window or auto_compact_token_limit or 0
    auto_compact_ratio = None
    if model_context_window > 0 and auto_compact_token_limit > 0:
        auto_compact_ratio = round(auto_compact_token_limit / model_context_window, 6)

    if model_context_window > 0:
        display_source = "codex_profile.model_context_window"
        display_reason = "declared_model_context_window"
    elif effective_safe_window > 0:
        display_source = "derived_context_window_fallback"
        display_reason = "model_context_window_unavailable_using_legacy_effective_window"
    elif auto_compact_token_limit > 0:
        display_source = "codex_profile.model_auto_compact_token_limit"
        display_reason = "model_context_window_unavailable_using_auto_compact_threshold_fallback"
    else:
        display_source = "unavailable"
        display_reason = "unavailable"

    return {
        "unit": "tokens",
        "display_limit_tokens": display_limit_tokens,
        "display_limit_source": display_source,
        "display_limit_reason": display_reason,
        "model_context_window_tokens": model_context_window or None,
        "model_context_window_source": "codex_profile.model_context_window" if model_context_window > 0 else None,
        "auto_compact_token_limit": auto_compact_token_limit or None,
        "auto_compact_threshold_tokens": auto_compact_token_limit or None,
        "auto_compact_token_limit_source": "codex_profile.model_auto_compact_token_limit" if auto_compact_token_limit > 0 else None,
        "auto_compact_threshold_source": "codex_profile.model_auto_compact_token_limit" if auto_compact_token_limit > 0 else None,
        "auto_compact_ratio": auto_compact_ratio,
        "auto_compact_ratio_source": "derived:auto_compact_token_limit/model_context_window" if auto_compact_ratio is not None else None,
        "model_catalog_context_window_tokens": catalog_tokens,
        "model_catalog_source": catalog_source,
        "value_explanations": {
            "display_limit_tokens": "The denominator WeClaw should display for the active profile. It is the real declared model context window when available.",
            "model_context_window_tokens": "The declared model context window in the managed Codex profile.",
            "auto_compact_token_limit": "The Codex profile threshold where Codex may compact before the full model context window is reached. CoDeepSeedeX managed profiles derive it from the 0.90 auto compact ratio.",
            "auto_compact_ratio": "The ratio auto_compact_token_limit/model_context_window. Managed profiles use 0.90 unless a legacy profile is being inspected.",
            "model_catalog_context_window_tokens": "The dsproxy model-catalog context-window declaration, used for consistency diagnostics and not as a replacement for the active profile declaration.",
        },
        "notes": [
            "WeClaw should display the full model context window as the context denominator.",
            "The auto-compact threshold is a separate trigger value, not the context-window size.",
            "dsproxy runtime compaction and trimming values are char-level fallback/debug controls and are not token denominators.",
        ],
    }


def _weclaw_catalog_context_tokens(value: Any) -> int | None:
    if isinstance(value, dict):
        for key in (
            "context_window_tokens",
            "model_context_window_tokens",
            "context_window",
            "context_length",
            "max_context_tokens",
            "max_input_tokens",
        ):
            if key not in value:
                continue
            try:
                parsed = int(value.get(key) or 0)
            except (TypeError, ValueError):
                parsed = 0
            if parsed > 0:
                return parsed
    try:
        parsed = int(value or 0)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _weclaw_catalog_model_name(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    for key in ("model", "id", "name"):
        raw = value.get(key)
        if raw:
            return str(raw)
    return None


def _weclaw_load_model_catalog(profile_section: dict[str, str]) -> tuple[Any, str | None, str | None, str | None]:
    raw = (profile_section.get("model_catalog_json") or "").strip()
    if not raw:
        return None, None, None, "model_catalog_json_not_configured"

    candidate = raw
    try:
        parsed = json.loads(candidate)
        if isinstance(parsed, str):
            candidate = parsed
        else:
            return parsed, "codex_profile.model_catalog_json", "inline_json", None
    except Exception:
        candidate = raw

    path = Path(candidate).expanduser()
    if not path.exists():
        return None, "codex_profile.model_catalog_json", "file", "model_catalog_file_not_found"

    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None, "codex_profile.model_catalog_json", "file", "model_catalog_file_invalid_json"

    return parsed, str(path), "file", None


def _weclaw_find_model_catalog_entry(catalog: Any, model: str | None) -> tuple[dict[str, Any] | None, str | None]:
    model_key = str(model or "").strip()
    if not model_key:
        return None, "effective_model_unavailable"

    if isinstance(catalog, dict):
        if model_key in catalog:
            value = catalog.get(model_key)
            if isinstance(value, dict):
                return {"model": model_key, **value}, None
            return {"model": model_key, "context_window_tokens": value}, None

        models = catalog.get("models")
        if isinstance(models, dict):
            if model_key in models:
                value = models.get(model_key)
                if isinstance(value, dict):
                    return {"model": model_key, **value}, None
                return {"model": model_key, "context_window_tokens": value}, None
            iterable = models.values()
        elif isinstance(models, list):
            iterable = models
        else:
            iterable = catalog.values()

        for item in iterable:
            if not isinstance(item, dict):
                continue
            name = _weclaw_catalog_model_name(item)
            if name == model_key:
                return item, None

    if isinstance(catalog, list):
        for item in catalog:
            if not isinstance(item, dict):
                continue
            name = _weclaw_catalog_model_name(item)
            if name == model_key:
                return item, None

    return None, "model_catalog_entry_not_found"


def _weclaw_model_catalog_contract(profile_section: dict[str, str], model: str | None) -> dict[str, Any]:
    catalog, source, source_kind, load_reason = _weclaw_load_model_catalog(profile_section)
    if load_reason is not None:
        return {
            "available": False,
            "model": str(model or "") or None,
            "context_window_tokens": None,
            "source": source or "codex_profile.model_catalog_json",
            "source_kind": source_kind,
            "reason": load_reason,
            "action": "install or repair the managed Codex profile so model_catalog_json points to a readable model catalog",
        }

    entry, match_reason = _weclaw_find_model_catalog_entry(catalog, model)
    if entry is None:
        return {
            "available": False,
            "model": str(model or "") or None,
            "context_window_tokens": None,
            "source": source or "codex_profile.model_catalog_json",
            "source_kind": source_kind,
            "reason": match_reason or "model_catalog_entry_not_found",
            "action": "add the effective model to the model catalog or repair the managed Codex profile",
        }

    context_tokens = _weclaw_catalog_context_tokens(entry)
    if context_tokens is None:
        return {
            "available": False,
            "model": str(model or "") or None,
            "context_window_tokens": None,
            "source": source or "codex_profile.model_catalog_json",
            "source_kind": source_kind,
            "reason": "model_catalog_entry_missing_context_window",
            "action": "add context_window_tokens for the effective model in the model catalog",
        }

    return {
        "available": True,
        "model": str(model or _weclaw_catalog_model_name(entry) or ""),
        "context_window_tokens": context_tokens,
        "source": source or "codex_profile.model_catalog_json",
        "source_kind": source_kind,
        "reason": None,
        "action": None,
    }


def _weclaw_enrich_semantic_compaction_status(status: Any) -> dict[str, Any]:
    result = deepcopy(status) if isinstance(status, dict) else {}
    latest = result.get("latest")
    if not isinstance(latest, dict):
        latest = {}
    for key in ("semantic_audit", "semantic_policy_dry_run", "semantic_payload_compaction"):
        item = latest.get(key)
        if not isinstance(item, dict):
            item = {"present": False}
        if not bool(item.get("present")):
            item.setdefault("reason", f"{key}_event_missing")
            item.setdefault("action", "run a request with debug trace enabled and keep semantic compaction in dry-run before enabling payload compaction")
        latest[key] = item
    result["latest"] = latest

    rollout = result.get("rollout")
    if not isinstance(rollout, dict):
        rollout = {}
    blockers = [str(item) for item in (rollout.get("blockers") or [])]
    missing_events = [
        item.removesuffix("_event_missing")
        for item in blockers
        if item.endswith("_event_missing")
    ]
    rollout.setdefault("missing_events", missing_events)
    rollout.setdefault(
        "action",
        "keep semantic payload compaction disabled until blockers clear; use debug semantic selftest and canary checks for validation",
    )
    result["rollout"] = rollout
    return result


def _weclaw_degraded_field(path: str, value: Any, *, default_reason: str, default_action: str) -> dict[str, Any]:
    reason = default_reason
    action = default_action
    missing: list[Any] = []
    if isinstance(value, dict):
        reason = str(value.get("reason") or value.get("status") or default_reason)
        action = str(value.get("action") or default_action)
        raw_missing = value.get("missing")
        if isinstance(raw_missing, list):
            missing = raw_missing
    return {
        "path": path,
        "reason": reason,
        "action": action,
        "missing": missing,
        "user_visible": False,
    }


def _weclaw_diagnostics_contract(payload: dict[str, Any]) -> dict[str, Any]:
    degraded_fields: list[dict[str, Any]] = []
    warnings: list[str] = []
    actions: list[str] = []

    model = payload.get("model")
    if isinstance(model, dict) and bool(model.get("model_conflict")):
        warnings.append("model_conflict_hidden_from_normal_status")
        if model.get("diagnostic_hint"):
            actions.append(str(model.get("diagnostic_hint")))

    context_window = payload.get("context_window")
    if isinstance(context_window, dict):
        if context_window.get("used_tokens_available") is False:
            degraded_fields.append(
                _weclaw_degraded_field(
                    "context_window.used_tokens",
                    context_window,
                    default_reason="context_used_tokens_not_reported_by_codex_or_provider",
                    default_action="display an unavailable marker instead of deriving context usage from session totals",
                )
            )
        catalog = context_window.get("model_catalog")
        if isinstance(catalog, dict) and catalog.get("available") is False:
            degraded_fields.append(
                _weclaw_degraded_field(
                    "context_window.model_catalog",
                    catalog,
                    default_reason="model_catalog_unavailable",
                    default_action="repair the managed Codex profile model catalog binding",
                )
            )

    tokens = payload.get("tokens")
    if isinstance(tokens, dict):
        for key in ("last_turn", "session_total", "auxiliary_model_calls"):
            section = tokens.get(key)
            if isinstance(section, dict) and section.get("available") is False:
                degraded_fields.append(
                    _weclaw_degraded_field(
                        f"tokens.{key}",
                        section,
                        default_reason="usage_unavailable",
                        default_action="send a model request through this dsproxy route, then re-check status",
                    )
                )

    pricing = payload.get("pricing")
    if isinstance(pricing, dict):
        if pricing.get("available") is False:
            degraded_fields.append(
                _weclaw_degraded_field(
                    "pricing",
                    pricing,
                    default_reason="pricing_unavailable",
                    default_action="check the dsproxy pricing cache with dsproxy pricing show --json",
                )
            )
        refresh = pricing.get("refresh")
        if isinstance(refresh, dict) and refresh.get("available") is False:
            degraded_fields.append(
                _weclaw_degraded_field(
                    "pricing.refresh",
                    refresh,
                    default_reason="official_live_pricing_refresh_not_implemented",
                    default_action="use the static dsproxy pricing cache until official live refresh is implemented",
                )
            )

    cost = payload.get("cost")
    if isinstance(cost, dict) and cost.get("available") is False:
        degraded_fields.append(
            _weclaw_degraded_field(
                "cost",
                cost,
                default_reason="cost_unavailable",
                default_action="check usage and pricing availability",
            )
        )

    balance = payload.get("balance")
    if isinstance(balance, dict) and balance.get("available") is False:
        degraded_fields.append(
            _weclaw_degraded_field(
                "balance",
                balance,
                default_reason="balance_unavailable",
                default_action="check provider balance API configuration",
            )
        )

    semantic = payload.get("semantic_compaction")
    if isinstance(semantic, dict):
        rollout = semantic.get("rollout")
        if isinstance(rollout, dict) and rollout.get("safe_to_enable_payload_compaction") is False:
            degraded_fields.append(
                _weclaw_degraded_field(
                    "semantic_compaction.rollout",
                    rollout,
                    default_reason="semantic_payload_compaction_not_safe_to_enable",
                    default_action="keep semantic payload compaction disabled until blockers clear",
                )
            )

    for item in degraded_fields:
        action = item.get("action")
        if action and action not in actions:
            actions.append(str(action))

    return {
        "available": True,
        "user_visible": False,
        "degraded_fields": degraded_fields,
        "warnings": warnings,
        "actions": actions,
    }


def _runtime_codex_config_health(sections: dict[str, dict[str, str]]) -> dict[str, Any]:
    allowed = {"none", "minimal", "low", "medium", "high", "xhigh"}
    invalid: list[dict[str, Any]] = []
    for section, values in sections.items():
        if not section.startswith("profiles."):
            continue
        effort = values.get("model_reasoning_effort")
        if effort is not None and effort not in allowed:
            invalid.append({
                "profile": section.removeprefix("profiles."),
                "field": "model_reasoning_effort",
                "value": effort,
                "allowed": sorted(allowed),
            })
    return {
        "codex_config_loadable": not invalid,
        "invalid_profile_fields": invalid,
        "warnings": [],
    }


def _runtime_profile_context_contract(profile_section: dict[str, str], *, effective_model: str | None = None) -> dict[str, Any]:
    model_context_window = _runtime_int_or_zero(profile_section.get("model_context_window"))
    auto_compact_token_limit = _runtime_int_or_zero(profile_section.get("model_auto_compact_token_limit"))
    display_limit_tokens = model_context_window or auto_compact_token_limit or 0
    auto_compact_ratio = round(auto_compact_token_limit / model_context_window, 6) if model_context_window > 0 and auto_compact_token_limit > 0 else None
    model_catalog = _weclaw_model_catalog_contract(profile_section, effective_model)
    conflicts: list[dict[str, Any]] = []
    catalog_context = model_catalog.get("context_window_tokens") if isinstance(model_catalog, dict) else None
    if (
        isinstance(catalog_context, int)
        and catalog_context > 0
        and model_context_window > 0
        and catalog_context != model_context_window
    ):
        conflicts.append(
            {
                "field": "model_context_window_tokens",
                "codex_profile_value": model_context_window,
                "model_catalog_value": catalog_context,
                "resolution": "codex_profile_model_context_window_remains_display_source",
                "user_visible": False,
            }
        )
    limit_explanation = _weclaw_context_limit_explanation(
        model_context_window=model_context_window,
        auto_compact_token_limit=auto_compact_token_limit,
        effective_safe_window=display_limit_tokens,
        model_catalog=model_catalog,
    )
    return {
        "display_limit_tokens": display_limit_tokens,
        "model_context_window_tokens": model_context_window,
        "auto_compact_token_limit": auto_compact_token_limit,
        "auto_compact_threshold_tokens": auto_compact_token_limit,
        "auto_compact_ratio": auto_compact_ratio,
        "effective_safe_window_tokens": display_limit_tokens,
        **_weclaw_context_used_tokens_unavailable_contract(),
        "source": limit_explanation["display_limit_source"],
        "is_estimated": False,
        "codex_profile": {
            "model_context_window_tokens": model_context_window,
            "auto_compact_token_limit": auto_compact_token_limit,
            "auto_compact_threshold_tokens": auto_compact_token_limit,
            "auto_compact_ratio": auto_compact_ratio,
            "unit": "tokens",
            "source": "codex_config.profiles.<profile>",
        },
        "model_catalog": model_catalog,
        "effective_display": {
            "limit_tokens": display_limit_tokens,
            "source": limit_explanation["display_limit_source"],
            "is_estimated": False,
        },
        "limit_explanation": limit_explanation,
        "notes": [
            "Codex profile values are token-level declarations.",
            "The displayed context denominator is model_context_window_tokens, while auto_compact_token_limit is only the auto-compact trigger threshold.",
            "dsproxy runtime compaction and trimming values are char-level fallback/debug controls and must not be treated as equivalent token denominators.",
        ],
        "conflicts": conflicts,
    }


def _runtime_profile_model_contract(profile_section: dict[str, str]) -> dict[str, Any]:
    codex_model = profile_section.get("model")
    env_model = os.environ.get("DEEPSEEK_PROXY_MODEL") or os.environ.get("DEEPSEEK_MODEL")
    force_model_enabled = _force_proxy_model_enabled()
    effective_model = _select_upstream_model(codex_model)
    model_conflict = bool(codex_model and effective_model and codex_model != effective_model)
    diagnostic_hint = (
        "Codex profile model differs from forced upstream model; dsproxy effective_model is authoritative."
        if model_conflict
        else None
    )
    return {
        "provider": os.environ.get("DEEPSEEK_PROXY_MODEL_PROVIDER", "deepseek"),
        "model": effective_model,
        "display_model": effective_model,
        "weclaw_display_model": effective_model,
        "requested_model": codex_model,
        "codex_model": codex_model,
        "upstream_model": effective_model,
        "effective_model": effective_model,
        "env_model": env_model,
        "force_model_enabled": force_model_enabled,
        "model_conflict": model_conflict,
        "display_hint": None,
        "diagnostic_hint": diagnostic_hint,
        "user_visible": False,
        "source": "dsproxy_runtime._select_upstream_model",
        "notes": (
            [
                "Codex profile model differs from the effective upstream model. WeClaw should display effective_model and may show codex_model as a conflict detail."
            ]
            if model_conflict
            else []
        ),
    }


def _runtime_effort_contract(profile_section: dict[str, str]) -> dict[str, Any]:
    codex_effort = profile_section.get("model_reasoning_effort")
    raw_effort = os.environ.get("DEEPSEEK_REASONING_EFFORT") or codex_effort or "high"
    normalized = str(raw_effort or "").strip().lower()
    if normalized in {"xhigh", "max"}:
        deepseek_effort = "max"
        expected_codex_effort = "xhigh"
    else:
        deepseek_effort = "high"
        expected_codex_effort = "high"
    return {
        "user_facing": "max" if deepseek_effort == "max" else "high",
        "deepseek_reasoning_effort": deepseek_effort,
        "codex_model_reasoning_effort": codex_effort,
        "expected_codex_model_reasoning_effort": expected_codex_effort,
        "source": "dsproxy_runtime_env_and_codex_profile",
        "codex_profile_valid": codex_effort in {"none", "minimal", "low", "medium", "high", "xhigh"} if codex_effort else False,
        "normalized": codex_effort == expected_codex_effort,
    }


def _runtime_weclaw_profile_status(profile: str) -> dict[str, Any]:
    codex_path = _runtime_codex_config_path()
    sections = _runtime_parse_simple_toml_sections(codex_path)
    profile_section = sections.get(f"profiles.{profile}", {})
    provider_name = profile_section.get("model_provider") or f"{profile}-proxy"
    provider_section = sections.get(f"model_providers.{provider_name}", {})
    health = _runtime_codex_config_health(sections)
    invalid = [
        item for item in health["invalid_profile_fields"]
        if isinstance(item, dict) and item.get("profile") == profile
    ]
    model = _runtime_profile_model_contract(profile_section)
    model["model_provider"] = provider_name
    model["base_url"] = provider_section.get("base_url")
    warnings = list(health.get("warnings", []))
    if bool(model.get("model_conflict")):
        warnings.append("codex_profile_model_differs_from_effective_upstream_model")

    payload = {
        "status": "ok" if not invalid else "error",
        "profile": profile,
        "profile_source": "codex_config",
        "codex_config": str(codex_path),
        "model": model,
        "effort": _runtime_effort_contract(profile_section),
        "thinking": {
            "enabled": profile.endswith("thinking"),
            "source": "profile_route",
        },
        "context_window": _runtime_profile_context_contract(
            profile_section,
            effective_model=str(model.get("effective_model") or model.get("upstream_model") or model.get("codex_model") or ""),
        ),
        "health": {
            "codex_config_loadable": bool(health["codex_config_loadable"]),
            "invalid_profile_fields": invalid,
            "warnings": warnings,
        },
    }
    payload["diagnostics"] = _weclaw_diagnostics_contract(payload)
    return payload


_WECLAW_PRIMARY_USAGE_PURPOSES = {"primary", "final"}


def _weclaw_zero_usage_summary() -> dict[str, Any]:
    return {
        "model_call_count": 0,
        "request_count": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "cached_tokens": 0,
        "prompt_cache_hit_tokens": 0,
        "prompt_cache_miss_tokens": 0,
        "reasoning_tokens": 0,
        "estimated_cost_usd": 0.0,
    }


def _weclaw_usage_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _weclaw_usage_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _weclaw_cache_summary_from_summary(summary: dict[str, Any], *, scope: str, source: str) -> dict[str, Any]:
    prompt_tokens = _weclaw_usage_int(summary.get("prompt_tokens"))
    hit_tokens = _weclaw_usage_int(summary.get("prompt_cache_hit_tokens") if "prompt_cache_hit_tokens" in summary else summary.get("cached_tokens"))
    miss_tokens = _weclaw_usage_int(summary.get("prompt_cache_miss_tokens"))
    if miss_tokens == 0 and prompt_tokens and hit_tokens <= prompt_tokens:
        miss_tokens = max(0, prompt_tokens - hit_tokens)
    return {
        "available": prompt_tokens > 0,
        "unit": "tokens",
        "scope": scope,
        "source": source,
        "is_estimated": False,
        "provider_authoritative": True,
        "prompt_tokens": prompt_tokens,
        "prompt_cache_hit_tokens": hit_tokens,
        "prompt_cache_miss_tokens": miss_tokens,
        "cached_tokens": hit_tokens,
        "cache_hit_ratio": (hit_tokens / prompt_tokens) if prompt_tokens > 0 else None,
        "cache_miss_ratio": (miss_tokens / prompt_tokens) if prompt_tokens > 0 else None,
        "reason": None if prompt_tokens > 0 else "provider_usage_not_available",
    }


def _weclaw_summarize_usage_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    summary = _weclaw_zero_usage_summary()
    summary["model_call_count"] = len(events)
    summary["request_count"] = len(events)
    summary["estimated_cost_by_model_usd"] = {}
    summary["estimated_cost_by_currency"] = {}
    summary["usage_by_model"] = {}
    summary["routes"] = {}
    for event in events:
        summary["prompt_tokens"] += _weclaw_usage_int(event.get("prompt_tokens"))
        summary["completion_tokens"] += _weclaw_usage_int(event.get("completion_tokens"))
        summary["total_tokens"] += _weclaw_usage_int(event.get("total_tokens"))
        hit_tokens = _weclaw_usage_int(event.get("prompt_cache_hit_tokens") if event.get("prompt_cache_hit_tokens") is not None else event.get("cached_tokens"))
        miss_tokens = _weclaw_usage_int(event.get("prompt_cache_miss_tokens"))
        if miss_tokens == 0:
            miss_tokens = max(0, _weclaw_usage_int(event.get("prompt_tokens")) - hit_tokens)
        summary["cached_tokens"] += hit_tokens
        summary["prompt_cache_hit_tokens"] += hit_tokens
        summary["prompt_cache_miss_tokens"] += miss_tokens
        summary["reasoning_tokens"] += _weclaw_usage_int(event.get("reasoning_tokens"))

        source_currency = str(event.get("estimated_cost_source_currency") or event.get("pricing_currency") or "USD").upper()
        source_amount_raw = event.get("estimated_cost_source_amount")
        source_amount = _weclaw_usage_float(source_amount_raw if source_amount_raw is not None else event.get("estimated_cost_usd"))
        summary["estimated_cost_by_currency"][source_currency] = float(
            summary["estimated_cost_by_currency"].get(source_currency, 0.0) + source_amount
        )
        if source_currency == "USD":
            summary["estimated_cost_usd"] += source_amount
        else:
            summary["estimated_cost_usd"] += _weclaw_usage_float(event.get("estimated_cost_usd"))

        model = str(event.get("effective_model") or event.get("model") or "unknown")
        route = str(event.get("route") or ("thinking" if bool(event.get("thinking_enabled")) else "non_thinking"))
        summary["estimated_cost_by_model_usd"][model] = float(
            summary["estimated_cost_by_model_usd"].get(model, 0.0) + _weclaw_usage_float(event.get("estimated_cost_usd"))
        )
        model_usage = summary["usage_by_model"].setdefault(
            model,
            {
                "model_call_count": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "cached_tokens": 0,
                "prompt_cache_hit_tokens": 0,
                "prompt_cache_miss_tokens": 0,
                "reasoning_tokens": 0,
                "total_tokens": 0,
                "estimated_cost_usd": 0.0,
                "estimated_cost_by_currency": {},
            },
        )
        model_usage["model_call_count"] += 1
        model_usage["prompt_tokens"] += _weclaw_usage_int(event.get("prompt_tokens"))
        model_usage["completion_tokens"] += _weclaw_usage_int(event.get("completion_tokens"))
        model_usage["cached_tokens"] += hit_tokens
        model_usage["prompt_cache_hit_tokens"] += hit_tokens
        model_usage["prompt_cache_miss_tokens"] += miss_tokens
        model_usage["reasoning_tokens"] += _weclaw_usage_int(event.get("reasoning_tokens"))
        model_usage["total_tokens"] += _weclaw_usage_int(event.get("total_tokens"))
        model_usage["estimated_cost_usd"] = float(model_usage["estimated_cost_usd"] + _weclaw_usage_float(event.get("estimated_cost_usd")))
        model_usage["estimated_cost_by_currency"][source_currency] = float(
            model_usage["estimated_cost_by_currency"].get(source_currency, 0.0) + source_amount
        )

        route_usage = summary["routes"].setdefault(route, {"model_call_count": 0, "estimated_cost_usd": 0.0, "estimated_cost_by_currency": {}})
        route_usage["model_call_count"] += 1
        route_usage["estimated_cost_usd"] = float(route_usage["estimated_cost_usd"] + _weclaw_usage_float(event.get("estimated_cost_usd")))
        route_usage["estimated_cost_by_currency"][source_currency] = float(
            route_usage["estimated_cost_by_currency"].get(source_currency, 0.0) + source_amount
        )

    summary["estimated_cost_usd"] = float(summary["estimated_cost_usd"])
    summary["estimated_cost_by_model_usd"] = {
        key: float(value)
        for key, value in sorted(summary["estimated_cost_by_model_usd"].items())
    }
    summary["estimated_cost_by_currency"] = {
        key: float(value)
        for key, value in sorted(summary["estimated_cost_by_currency"].items())
    }
    summary["cache_hit_ratio"] = (summary["prompt_cache_hit_tokens"] / summary["prompt_tokens"]) if summary["prompt_tokens"] else None
    for model_usage in summary["usage_by_model"].values():
        model_usage["cache_hit_ratio"] = (model_usage["prompt_cache_hit_tokens"] / model_usage["prompt_tokens"]) if model_usage["prompt_tokens"] else None
    summary["models"] = sorted(summary["usage_by_model"])
    return summary


def _weclaw_usage_by_purpose(events: list[dict[str, Any]]) -> dict[str, Any]:
    by_purpose: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        purpose = str(event.get("purpose") or "unknown")
        by_purpose.setdefault(purpose, []).append(event)

    return {
        purpose: _weclaw_summarize_usage_events(items)
        for purpose, items in sorted(by_purpose.items())
    }


def _weclaw_section_prompt_tokens(section: Any, *, purpose: str | None = None) -> int | None:
    if not isinstance(section, dict) or not section.get("available"):
        return None
    target: Any = section
    if purpose:
        by_purpose = section.get("by_purpose")
        if not isinstance(by_purpose, dict):
            return None
        target = by_purpose.get(purpose)
    if not isinstance(target, dict):
        return None
    summary = target.get("summary") if "summary" in target else target
    if not isinstance(summary, dict):
        return None
    try:
        value = int(summary.get("prompt_tokens") or 0)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None



def _weclaw_context_window_with_usage_estimate(context_window: dict[str, Any], tokens: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(context_window)
    latest_primary = tokens.get("latest_primary_turn") if isinstance(tokens, dict) else None
    latest_prompt_tokens = _weclaw_section_prompt_tokens(latest_primary)

    if latest_prompt_tokens is None:
        enriched["used_tokens_available"] = False
        enriched["used_tokens_reason"] = "latest_primary_turn_not_available"
        enriched["used_tokens_action"] = "send a primary model request through this route, then re-check status"
        enriched["used_tokens_source"] = "dsproxy_usage_ledger.latest_primary_turn.summary.prompt_tokens"
        return enriched

    source = "dsproxy_usage_ledger.latest_primary_turn.summary.prompt_tokens"
    request_id = latest_primary.get("request_id") if isinstance(latest_primary, dict) else None
    enriched.update(
        {
            "used_tokens": latest_prompt_tokens,
            "used_tokens_available": True,
            "used_tokens_source": source,
            "used_tokens_reason": None,
            "used_tokens_action": None,
            "used_tokens_precision": "estimated_current_context_from_latest_primary_upstream_prompt_tokens",
            "used_tokens_is_estimated": True,
            "used_tokens_semantic_scope": "latest_primary_upstream_prompt_tokens_after_dsproxy_payload_assembly",
            "latest_upstream_prompt_tokens": {
                "available": True,
                "value": latest_prompt_tokens,
                "unit": "tokens",
                "source": source,
                "request_id": request_id,
                "purpose": "primary",
                "precision": "provider_reported_prompt_tokens_for_latest_primary_upstream_model_call",
                "is_estimated_for_context_window": True,
                "semantic_scope": "latest_primary_upstream_prompt_tokens_after_dsproxy_payload_assembly",
                "notes": [
                    "This is the latest primary upstream prompt_tokens value recorded by the provider usage ledger.",
                    "Auxiliary calls such as liveness_judge, liveness_retry, tool_bridge, and compaction must not replace this numerator.",
                    "It must not be replaced with session_total prompt tokens, because session_total is cumulative spend rather than current context occupancy.",
                ],
            },
        }
    )
    display_limit = _weclaw_usage_int(enriched.get("display_limit_tokens"))
    if display_limit > 0:
        enriched["used_ratio"] = min(1.0, latest_prompt_tokens / display_limit)
        enriched["remaining_tokens_estimate"] = max(0, display_limit - latest_prompt_tokens)
    return enriched



def _weclaw_usage_events_for_profile(
    store: Any | None,
    *,
    profile: str,
    limit: int = 1000,
    session_id: str | None = None,
) -> tuple[list[dict[str, Any]], str | None]:
    if store is None:
        return [], "runtime_store_unavailable"
    if not hasattr(store, "usage_events"):
        return [], "usage_ledger_unsupported"
    thinking = profile.endswith("thinking")
    try:
        events = store.usage_events(limit=limit, thinking=thinking, session_id=session_id)
    except TypeError:
        try:
            events = store.usage_events(limit=limit, thinking=thinking)
        except TypeError:
            try:
                events = store.usage_events(limit=limit)
            except Exception:
                return [], "usage_ledger_query_failed"
        except Exception:
            return [], "usage_ledger_query_failed"
    except Exception:
        return [], "usage_ledger_query_failed"
    return [dict(event) for event in events if isinstance(event, dict)], None


def _weclaw_latest_turn_events(events: list[dict[str, Any]]) -> tuple[str | None, list[dict[str, Any]]]:
    if not events:
        return None, []
    latest = events[0]
    request_id = latest.get("request_id") or latest.get("response_id")
    if not request_id:
        return None, [latest]
    key = str(request_id)
    grouped = [
        event
        for event in events
        if str(event.get("request_id") or event.get("response_id") or "") == key
    ]
    return key, grouped


def _weclaw_prompt_subcategory_split_contract(
    profile_tokenizer_report: dict[str, Any] | None = None,
    *,
    tokenizer_contract: dict[str, Any] | None = None,
    no_observed_prompt: bool = False,
) -> dict[str, Any]:
    if isinstance(profile_tokenizer_report, dict):
        split = profile_tokenizer_report.get("prompt_subcategory_split")
        if isinstance(split, dict) and split.get("available"):
            normalized = dict(split)
            normalized["precision"] = "local_profile_tokenizer_estimate"
            return normalized
        maybe_contract = profile_tokenizer_report.get("tokenizer")
        if isinstance(maybe_contract, dict):
            tokenizer_contract = maybe_contract

    if isinstance(tokenizer_contract, dict) and tokenizer_contract.get("available"):
        return {
            "available": False,
            "unit": "tokens",
            "is_estimated": True,
            "precision": "local_profile_tokenizer_estimate",
            "source": "dsproxy_profile_tokenizer.available_without_observed_prompt",
            "source_kind": tokenizer_contract.get("source_kind"),
            "tokenizer_kind": tokenizer_contract.get("tokenizer_kind"),
            "tokenizer_source": tokenizer_contract.get("source"),
            "reason": "profile_tokenizer_available_but_no_observed_prompt",
            "action": "send one model request through this route, then re-check dsproxy status --weclaw-json",
            "categories": {},
            "requested_categories": _profile_tokenizer_requested_categories(),
            "missing": [
                "observed_assembled_prompt_for_route",
            ],
            "notes": [
                "The profile tokenizer resource is available, but this running route has not observed an assembled prompt since startup.",
                "Provider usage totals remain authoritative for billing and aggregate prompt/completion/cache/reasoning fields.",
                "Prompt subcategory splits must not be inferred from aggregate provider prompt_tokens.",
            ],
        }

    if isinstance(tokenizer_contract, dict):
        return {
            "available": False,
            "unit": "tokens",
            "is_estimated": False,
            "precision": "unavailable",
            "source": "profile_tokenizer_contract",
            "source_kind": tokenizer_contract.get("source_kind"),
            "reason": str(tokenizer_contract.get("reason") or "profile_tokenizer_resource_unavailable"),
            "action": str(tokenizer_contract.get("action") or "run dsproxy tokenizer sync deepseek --json"),
            "categories": {},
            "requested_categories": _profile_tokenizer_requested_categories(),
            "missing": [
                "profile_tokenizer_resource",
            ],
            "notes": [
                "Provider usage totals are exact for aggregate prompt/completion/cache/reasoning fields.",
                "Prompt subcategory splits require an audited profile tokenizer and an observed assembled prompt for the route.",
            ],
        }

    return {
        "available": False,
        "unit": "tokens",
        "is_estimated": False,
        "precision": "unavailable",
        "source": "profile_tokenizer_contract_missing",
        "reason": "profile_tokenizer_contract_unavailable",
        "action": "run dsproxy tokenizer status deepseek --json and verify the running route exposes tokenizer_contract",
        "categories": {},
        "requested_categories": _profile_tokenizer_requested_categories(),
        "missing": [
            "profile_tokenizer_contract",
        ],
        "notes": [
            "Provider usage totals are exact for aggregate prompt/completion/cache/reasoning fields.",
            "Prompt subcategory splits must not be inferred from aggregate provider prompt_tokens.",
        ],
    }


def _weclaw_token_attribution_contract(
    profile_tokenizer_report: dict[str, Any] | None = None,
    *,
    tokenizer_contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if isinstance(profile_tokenizer_report, dict):
        maybe_contract = profile_tokenizer_report.get("tokenizer")
        if isinstance(maybe_contract, dict):
            tokenizer_contract = maybe_contract

    prompt_subcategory_split = _weclaw_prompt_subcategory_split_contract(
        profile_tokenizer_report,
        tokenizer_contract=tokenizer_contract,
    )
    tokenizer_available = bool(
        isinstance(profile_tokenizer_report, dict) and profile_tokenizer_report.get("available")
    ) or bool(isinstance(tokenizer_contract, dict) and tokenizer_contract.get("available"))
    return {
        "provider_usage_totals": {
            "available": True,
            "unit": "tokens",
            "precision": "exact_provider_reported",
            "source": "provider_usage_fields_persisted_in_dsproxy_usage_ledger",
            "fields": [
                "prompt_tokens",
                "completion_tokens",
                "total_tokens",
                "cached_tokens",
                "reasoning_tokens",
            ],
        },
        "purpose_attribution": {
            "available": True,
            "unit": "tokens",
            "precision": "exact_dsproxy_call_purpose",
            "source": "dsproxy_usage_ledger.purpose_and_call_index",
            "fields": [
                "purpose",
                "call_index",
                "request_id",
                "response_id",
                "requested_model",
                "effective_model",
                "upstream_model",
            ],
            "known_purposes": [
                "primary",
                "final",
                "tool_bridge",
                "liveness_judge",
                "liveness_retry",
                "compaction",
                "semantic_audit",
            ],
        },
        "profile_tokenizer": {
            "available": tokenizer_available,
            "unit": "tokens",
            "precision": "local_profile_tokenizer_estimate" if tokenizer_available else "unavailable",
            "source": (
                str((tokenizer_contract or {}).get("source") or "dsproxy_profile_tokenizer")
                if tokenizer_available
                else "unavailable"
            ),
            "source_kind": (
                str((tokenizer_contract or {}).get("source_kind") or "unknown")
                if tokenizer_available
                else "unavailable"
            ),
            "tokenizer_kind": (
                str((tokenizer_contract or {}).get("tokenizer_kind") or "unknown")
                if tokenizer_available
                else None
            ),
            "is_estimated": True if tokenizer_available else None,
            "billing_authoritative": False,
        },
        "prompt_subcategory_split": prompt_subcategory_split,
        "context_window_used_tokens": {
            "available": False,
            "unit": "tokens",
            "precision": "unavailable",
            "source": "not_reported_by_codex_or_provider",
            "reason": "context_used_tokens_not_reported_by_codex_or_provider",
            "action": "use context_window.used_tokens when context_window.used_tokens_available is true; otherwise display an unavailable marker; never derive current context usage from session totals",
            "estimated_context_numerator_available_when_latest_upstream_prompt_tokens_exist": True,
            "estimate_field": "context_window.latest_upstream_prompt_tokens",
            "estimate_precision": "estimated_current_context_from_latest_upstream_prompt_tokens",
            "missing": [
                "codex_context_used_tokens",
                "provider_context_window_used_tokens",
                "codex_context_used_tokens" if prompt_subcategory_split.get("available") else "observed_assembled_prompt_or_segment_ledger",
            ],
        },
    }







def _weclaw_prompt_split_with_provider_coverage(
    split: dict[str, Any],
    latest_primary_turn: dict[str, Any],
    *,
    session_id: str | None = None,
) -> dict[str, Any]:
    if not isinstance(split, dict):
        return split

    normalized = dict(split)
    categories = normalized.get("categories")
    categories_sum_tokens = normalized.get("categories_sum_tokens")
    if categories_sum_tokens is None:
        if isinstance(categories, dict):
            categories_sum_tokens = sum(
                _weclaw_usage_int(item.get("tokens"))
                for item in categories.values()
                if isinstance(item, dict)
            )
        else:
            categories_sum_tokens = 0
    categories_sum_tokens = int(categories_sum_tokens or 0)

    def _category_tokens(name: str) -> int:
        if isinstance(categories, dict):
            item = categories.get(name)
            if isinstance(item, dict):
                return _weclaw_usage_int(item.get("tokens"))
        return 0

    user_tokens = _category_tokens("user")
    history_tokens = _category_tokens("assistant_history") + _category_tokens("user_history")
    tool_output_tokens = _category_tokens("tool_output")
    system_tokens = _category_tokens("system")
    developer_tokens = _category_tokens("developer")
    compaction_tokens = _category_tokens("compaction_summary")
    environment_tokens = _category_tokens("environment")
    runtime_tokens = _category_tokens("runtime_injected")
    other_prompt_tokens = _category_tokens("other_prompt")

    latest_prompt_segmentation = normalized.get("latest_prompt_segmentation")
    if isinstance(latest_prompt_segmentation, dict):
        latest_prompt_segmentation = dict(latest_prompt_segmentation)
    else:
        latest_prompt_segmentation = {}

    observable_payload = normalized.get("observable_payload")
    if not isinstance(observable_payload, dict):
        observable_payload = latest_prompt_segmentation.get("observable_payload")
    if not isinstance(observable_payload, dict):
        observable_payload = {"available": False, "reason": "observable_payload_report_not_available"}

    local_message_content_tokens = None
    local_message_content_source = None
    if "total_prompt_tokens_profile_tokenizer" in latest_prompt_segmentation:
        local_message_content_tokens = _weclaw_usage_int(latest_prompt_segmentation.get("total_prompt_tokens_profile_tokenizer"))
        local_message_content_source = "prompt_subcategory_split.latest_prompt_segmentation.total_prompt_tokens_profile_tokenizer"
    elif "total_tokens" in normalized:
        local_message_content_tokens = _weclaw_usage_int(normalized.get("total_tokens"))
        local_message_content_source = "prompt_subcategory_split.total_tokens"
    elif categories is not None:
        local_message_content_tokens = categories_sum_tokens
        local_message_content_source = "prompt_subcategory_split.categories_sum_tokens"

    payload_components = observable_payload.get("components") if isinstance(observable_payload, dict) else None
    if not isinstance(payload_components, dict):
        payload_components = {}

    def _component_tokens(name: str) -> int:
        component = payload_components.get(name)
        return _weclaw_usage_int(component.get("local_tokens")) if isinstance(component, dict) else 0

    tools_schema_tokens = _component_tokens("tools_schema")
    tool_choice_tokens = _component_tokens("tool_choice")
    response_format_tokens = _component_tokens("response_format")
    request_options_tokens = _component_tokens("request_options")
    messages_json_tokens = _component_tokens("messages_json")

    messages_json_over_message_content_tokens = max(0, messages_json_tokens - int(local_message_content_tokens or 0))
    raw_protocol_candidate_tokens = (
        messages_json_over_message_content_tokens
        + tool_choice_tokens
        + response_format_tokens
        + request_options_tokens
    )

    semantic_prompt_candidate_tokens = None
    if isinstance(observable_payload, dict) and observable_payload.get("available"):
        if observable_payload.get("semantic_prompt_candidate_tokens") is not None:
            semantic_prompt_candidate_tokens = _weclaw_usage_int(observable_payload.get("semantic_prompt_candidate_tokens"))
        elif local_message_content_tokens is not None:
            semantic_prompt_candidate_tokens = int(local_message_content_tokens) + tools_schema_tokens + tool_choice_tokens + response_format_tokens

    local_full_observed_prompt_tokens = semantic_prompt_candidate_tokens
    local_full_observed_prompt_source = (
        "prompt_subcategory_split.observable_payload.semantic_prompt_candidate_tokens"
        if semantic_prompt_candidate_tokens is not None
        else None
    )
    if local_full_observed_prompt_tokens is None:
        local_full_observed_prompt_tokens = local_message_content_tokens
        local_full_observed_prompt_source = local_message_content_source

    local_full_observable_payload_tokens = None
    if isinstance(observable_payload, dict) and observable_payload.get("full_payload_json_tokens") is not None:
        local_full_observable_payload_tokens = _weclaw_usage_int(observable_payload.get("full_payload_json_tokens"))

    provider_prompt_tokens = None
    provider_total_tokens = None
    provider_cached_tokens = None
    provider_completion_tokens = None
    provider_reasoning_tokens = None
    provider_prompt_tokens_source = "latest_primary_turn.summary.prompt_tokens"
    provider_total_tokens_source = "latest_primary_turn.summary.total_tokens"
    request_id = None
    if isinstance(latest_primary_turn, dict) and latest_primary_turn.get("available"):
        request_id = latest_primary_turn.get("request_id")
        summary = latest_primary_turn.get("summary")
        if isinstance(summary, dict):
            if "prompt_tokens" in summary:
                provider_prompt_tokens = _weclaw_usage_int(summary.get("prompt_tokens"))
            if "total_tokens" in summary:
                provider_total_tokens = _weclaw_usage_int(summary.get("total_tokens"))
            if "cached_tokens" in summary:
                provider_cached_tokens = _weclaw_usage_int(summary.get("cached_tokens"))
            if "completion_tokens" in summary:
                provider_completion_tokens = _weclaw_usage_int(summary.get("completion_tokens"))
            if "reasoning_tokens" in summary:
                provider_reasoning_tokens = _weclaw_usage_int(summary.get("reasoning_tokens"))

    delta_tokens = None
    if provider_prompt_tokens is not None:
        delta_tokens = int(provider_prompt_tokens) - categories_sum_tokens

    semantic_residual_tokens = None
    if provider_prompt_tokens is not None and local_full_observed_prompt_tokens is not None:
        semantic_residual_tokens = int(provider_prompt_tokens) - int(local_full_observed_prompt_tokens)

    if semantic_residual_tokens is not None and semantic_residual_tokens > 0:
        message_protocol_overhead_tokens = min(semantic_residual_tokens, raw_protocol_candidate_tokens)
    else:
        message_protocol_overhead_tokens = 0

    provider_residual_tokens = None
    if semantic_residual_tokens is not None:
        provider_residual_tokens = semantic_residual_tokens - message_protocol_overhead_tokens

    provider_abs_residual_tokens = abs(provider_residual_tokens) if provider_residual_tokens is not None else None
    tolerance_tokens = max(32, int((provider_prompt_tokens or 0) * 0.005)) if provider_prompt_tokens is not None else 32

    segment_source = latest_prompt_segmentation.get("segments")
    if not isinstance(segment_source, list):
        segment_source = latest_prompt_segmentation.get("segments_tail")
    if not isinstance(segment_source, list):
        segment_source = []

    prompt_segments: list[dict[str, Any]] = []
    segment_categories_sum_tokens = 0
    unclassified_segments: list[dict[str, Any]] = []
    for segment in segment_source:
        if not isinstance(segment, dict):
            continue
        category = str(segment.get("category") or "unclassified")
        local_tokens = _weclaw_usage_int(segment.get("local_tokens") if "local_tokens" in segment else segment.get("token_count"))
        segment_categories_sum_tokens += local_tokens
        item = {
            "index": segment.get("index"),
            "category": category,
            "source": segment.get("source"),
            "role": segment.get("role"),
            "char_count": _weclaw_usage_int(segment.get("char_count")),
            "local_tokens": local_tokens,
            "sha256": segment.get("sha256"),
            "preview": segment.get("preview"),
        }
        if segment.get("head") is not None:
            item["head"] = segment.get("head")
        if segment.get("tail") is not None:
            item["tail"] = segment.get("tail")
        prompt_segments.append(item)
        if category in {"", "unclassified", "unknown"}:
            unclassified_segments.append(item)

    if local_message_content_tokens is None and prompt_segments:
        local_message_content_tokens = segment_categories_sum_tokens
        local_message_content_source = "prompt_subcategory_split.latest_prompt_segmentation.segments.token_count_sum"
    if local_full_observed_prompt_tokens is None and prompt_segments:
        local_full_observed_prompt_tokens = segment_categories_sum_tokens
        local_full_observed_prompt_source = "prompt_subcategory_split.latest_prompt_segmentation.segments.token_count_sum"

    if local_message_content_tokens is not None:
        unclassified_observed_segments_tokens = max(0, int(local_message_content_tokens) - categories_sum_tokens)
    else:
        unclassified_observed_segments_tokens = None

    observable_prompt_non_category_tokens = None
    if local_full_observed_prompt_tokens is not None:
        observable_prompt_non_category_tokens = max(0, int(local_full_observed_prompt_tokens) - categories_sum_tokens)

    if provider_prompt_tokens is None:
        coverage_complete = False
        delta_status = "unavailable"
        delta_reason = "provider_reference_tokens_unavailable"
        is_accounting_suspect = False
        root_cause_status = "provider_usage_unavailable"
    elif delta_tokens == 0:
        coverage_complete = bool(normalized.get("available"))
        delta_status = "explained"
        delta_reason = None
        is_accounting_suspect = False
        root_cause_status = "no_delta"
    elif provider_abs_residual_tokens is not None and provider_abs_residual_tokens <= tolerance_tokens:
        coverage_complete = False
        delta_status = "explained_by_observable_payload_accounting"
        delta_reason = "provider_prompt_delta_is_explained_by_tools_schema_and_message_protocol_overhead"
        is_accounting_suspect = False
        root_cause_status = "tool_schema_and_message_protocol_overhead"
    elif tools_schema_tokens or message_protocol_overhead_tokens:
        coverage_complete = False
        delta_status = "partially_explained_by_observable_payload_accounting"
        delta_reason = "observable_payload_components_explain_part_of_delta_remainder_is_provider_template_or_tokenizer_difference"
        is_accounting_suspect = True
        root_cause_status = "tool_schema_and_message_protocol_overhead_plus_residual"
    elif unclassified_observed_segments_tokens:
        coverage_complete = False
        delta_status = "explained_by_unclassified_observed_segments"
        delta_reason = "observable_prompt_segments_not_assigned_to_prompt_subcategories"
        is_accounting_suspect = False
        root_cause_status = "classification_gap"
    else:
        coverage_complete = False
        delta_status = "unexplained_after_observable_payload_accounting"
        delta_reason = "provider_prompt_tokens_exceed_local_observable_prompt_payload_tokens"
        is_accounting_suspect = bool(delta_tokens)
        root_cause_status = "provider_template_hidden_overhead_or_tokenizer_mismatch"

    if provider_prompt_tokens is not None and delta_tokens is not None and delta_tokens < 0:
        delta_status = "unexplained_after_observable_payload_accounting"
        delta_reason = "local_profile_tokenizer_prompt_tokens_exceed_provider_prompt_tokens"
        is_accounting_suspect = True
        root_cause_status = "tokenizer_mismatch_or_local_overcount"

    coverage_scope = "local_profile_tokenizer_message_content_only"
    coverage_basis = str(
        normalized.get("semantic_scope")
        or "message_content_and_tool_call_arguments_after_dsproxy_payload_assembly"
    )

    dominant_candidates = {
        "tools_schema": tools_schema_tokens,
        "message_protocol_overhead": message_protocol_overhead_tokens,
        "unclassified_observed_segments": int(unclassified_observed_segments_tokens or 0),
        "provider_residual": int(provider_abs_residual_tokens or 0),
    }
    dominant_observable_delta_source = max(dominant_candidates, key=lambda key: dominant_candidates[key])
    if dominant_candidates.get(dominant_observable_delta_source, 0) <= 0:
        dominant_observable_delta_source = None

    details_origin_components = {
        "user": {"tokens": user_tokens, "source": "prompt_subcategory_split.categories.user"},
        "history": {"tokens": history_tokens, "source": "prompt_subcategory_split.categories.assistant_history_plus_user_history"},
        "tool_output": {"tokens": tool_output_tokens, "source": "prompt_subcategory_split.categories.tool_output"},
        "system": {"tokens": system_tokens, "source": "prompt_subcategory_split.categories.system"},
        "developer": {"tokens": developer_tokens, "source": "prompt_subcategory_split.categories.developer"},
        "compaction_summary": {"tokens": compaction_tokens, "source": "prompt_subcategory_split.categories.compaction_summary"},
        "environment": {"tokens": environment_tokens, "source": "prompt_subcategory_split.categories.environment"},
        "runtime_injected": {"tokens": runtime_tokens, "source": "prompt_subcategory_split.categories.runtime_injected"},
        "other_prompt": {"tokens": other_prompt_tokens, "source": "prompt_subcategory_split.categories.other_prompt"},
        "tools_schema": {"tokens": tools_schema_tokens, "source": "observable_payload.components.tools_schema"},
        "message_protocol_overhead": {
            "tokens": message_protocol_overhead_tokens,
            "source": "observable_payload.messages_json_wrapper_plus_request_prompt_controls",
        },
        "provider_residual": {
            "tokens": provider_residual_tokens,
            "abs_tokens": provider_abs_residual_tokens,
            "source": "provider_prompt_tokens_minus_local_observable_payload_accounting",
        },
    }
    details_origin_display_order = [
        "user",
        "history",
        "tool_output",
        "system",
        "developer",
        "compaction_summary",
        "environment",
        "runtime_injected",
        "other_prompt",
        "tools_schema",
        "message_protocol_overhead",
        "provider_residual",
    ]
    details_origin_breakdown = {
        "available": True,
        "unit": "tokens",
        "scope": "current_session" if session_id else normalized.get("scope"),
        "session_id": session_id or normalized.get("session_id"),
        "request_id": request_id,
        "display_semantics": "token_origin_breakdown_not_classified_total",
        "display_order": details_origin_display_order,
        "components": details_origin_components,
        "provider_prompt_tokens": provider_prompt_tokens,
        "provider_total_tokens": provider_total_tokens,
        "provider_residual_tolerance_tokens": tolerance_tokens,
        "should_display_classified_total": False,
        "recommended_compact_display": "user/history/tool_output/system/developer/compaction/environment/runtime/other/tools_schema/message_protocol_overhead/provider_residual",
        "notes": [
            "Do not display a classified subtotal by default.",
            "Details is an origin breakdown: message-content categories plus observable tools/schema and protocol overhead.",
            "provider_residual should normally be hidden when abs_tokens is within tolerance.",
        ],
    }

    delta_breakdown = {
        "unclassified_observed_segments_tokens": unclassified_observed_segments_tokens,
        "observable_prompt_non_category_tokens": observable_prompt_non_category_tokens,
        "tools_schema_tokens": tools_schema_tokens,
        "message_wrapper_or_protocol_tokens": message_protocol_overhead_tokens,
        "raw_messages_json_over_message_content_tokens": messages_json_over_message_content_tokens,
        "tool_choice_tokens": tool_choice_tokens,
        "response_format_tokens": response_format_tokens,
        "request_options_tokens": request_options_tokens,
        "semantic_residual_tokens": semantic_residual_tokens,
        "provider_residual_tokens": provider_residual_tokens,
        "provider_abs_residual_tokens": provider_abs_residual_tokens,
        "chat_template_or_protocol_overhead_tokens": message_protocol_overhead_tokens,
        "provider_hidden_overhead_tokens": provider_residual_tokens,
        "tokenizer_mismatch_tokens": None,
        "unknown_tokens": provider_abs_residual_tokens,
        "provider_or_template_overhead_tokens": message_protocol_overhead_tokens,
    }

    prompt_segment_audit = {
        "available": bool(prompt_segments),
        "scope": "current_session" if session_id else normalized.get("scope"),
        "session_id": session_id or normalized.get("session_id"),
        "request_id": request_id,
        "prompt_segments": prompt_segments,
        "segment_categories_sum_tokens": segment_categories_sum_tokens,
        "unclassified_segments": unclassified_segments,
        "unclassified_segments_tokens": unclassified_observed_segments_tokens,
        "classification_complete": not bool(unclassified_observed_segments_tokens),
    }

    experiment_cases = ["minimal_user_only", "system_env_only", "tool_schema_no_execution", "tool_call_output", "historical_session"]
    minimum_experiment_matrix = {
        "available": False,
        "reason": "requires_live_provider_trace",
        "recommended_action": "run_prompt_reconciliation_trace",
        "cases": [
            {
                "case": case,
                "provider_prompt_tokens": None,
                "local_full_observed_prompt_tokens": None,
                "local_full_observable_payload_tokens": None,
                "categories_sum_tokens": None,
                "delta_tokens": None,
                "delta_breakdown": {
                    "unclassified_observed_segments_tokens": None,
                    "tools_schema_tokens": None,
                    "message_wrapper_or_protocol_tokens": None,
                    "provider_residual_tokens": None,
                },
                "is_accounting_suspect": None,
                "status": "not_run_requires_live_provider_trace",
            }
            for case in experiment_cases
        ],
    }

    prompt_reconciliation = {
        "available": True,
        "scope": "current_session" if session_id else normalized.get("scope"),
        "session_id": session_id or normalized.get("session_id"),
        "request_id": request_id,
        "provider_prompt_tokens": provider_prompt_tokens,
        "provider_prompt_tokens_source": provider_prompt_tokens_source,
        "provider_total_tokens": provider_total_tokens,
        "provider_total_tokens_source": provider_total_tokens_source,
        "provider_cached_tokens": provider_cached_tokens,
        "provider_completion_tokens": provider_completion_tokens,
        "provider_reasoning_tokens": provider_reasoning_tokens,
        "local_categories_sum_tokens": categories_sum_tokens,
        "local_categories_source": "prompt_subcategory_split.categories",
        "local_message_content_tokens": local_message_content_tokens,
        "local_message_content_source": local_message_content_source,
        "local_full_observed_prompt_tokens": local_full_observed_prompt_tokens,
        "local_full_observed_prompt_source": local_full_observed_prompt_source,
        "local_full_observable_payload_tokens": local_full_observable_payload_tokens,
        "local_full_observable_payload_source": "prompt_subcategory_split.observable_payload.full_payload_json_tokens" if local_full_observable_payload_tokens is not None else None,
        "observable_payload": observable_payload,
        "delta_tokens": delta_tokens,
        "delta_breakdown": delta_breakdown,
        "delta_status": delta_status,
        "root_cause_status": root_cause_status,
        "dominant_observable_delta_source": dominant_observable_delta_source,
        "details_origin_breakdown": details_origin_breakdown,
        "is_accounting_suspect": is_accounting_suspect,
        "recommended_action": "run_prompt_reconciliation_trace" if delta_status in {"unexplained_after_observable_payload_accounting", "partially_explained_by_observable_payload_accounting"} else None,
        "classification_complete": not bool(unclassified_observed_segments_tokens),
        "local_full_observed_matches_categories": (
            local_full_observed_prompt_tokens is not None
            and int(local_full_observed_prompt_tokens) == categories_sum_tokens
        ),
        "can_provider_prompt_tokens_be_fully_decomposed_to_details": coverage_complete,
        "delta_interpretation": root_cause_status,
        "prompt_segment_audit": prompt_segment_audit,
        "minimum_experiment_matrix": minimum_experiment_matrix,
        "notes": [
            "Do not display a classified subtotal by default.",
            "Details is an origin breakdown of tokens by user/history/tool/system/environment/tools_schema/protocol/residual sources.",
            "provider_prompt_tokens is provider-reported usage and remains authoritative for billing.",
            "provider_residual should not be assigned to other_prompt.",
        ],
    }

    normalized.update(
        {
            "categories_sum_tokens": categories_sum_tokens,
            "provider_reference_tokens": provider_prompt_tokens,
            "provider_reference_field": provider_prompt_tokens_source,
            "delta_tokens": delta_tokens,
            "coverage_complete": coverage_complete,
            "coverage_scope": coverage_scope,
            "coverage_basis": coverage_basis,
            "delta_reason": delta_reason,
            "prompt_reconciliation": prompt_reconciliation,
            "details_origin_breakdown": details_origin_breakdown,
            "prompt_segments": prompt_segments,
            "segment_categories_sum_tokens": segment_categories_sum_tokens,
            "unclassified_segments": unclassified_segments,
            "unclassified_segments_tokens": unclassified_observed_segments_tokens,
            "observable_payload": observable_payload,
        }
    )
    if session_id:
        normalized.setdefault("scope", "current_session")
        normalized.setdefault("session_id", session_id)

    if latest_prompt_segmentation:
        latest_prompt_segmentation.update(
            {
                "categories_sum_tokens": categories_sum_tokens,
                "provider_reference_tokens": provider_prompt_tokens,
                "provider_reference_field": provider_prompt_tokens_source,
                "delta_tokens": delta_tokens,
                "coverage_complete": coverage_complete,
                "coverage_scope": coverage_scope,
                "coverage_basis": coverage_basis,
                "delta_reason": delta_reason,
                "local_message_content_tokens": local_message_content_tokens,
                "local_full_observed_prompt_tokens": local_full_observed_prompt_tokens,
                "local_full_observable_payload_tokens": local_full_observable_payload_tokens,
                "prompt_reconciliation": prompt_reconciliation,
                "details_origin_breakdown": details_origin_breakdown,
                "prompt_segments": prompt_segments,
                "segment_categories_sum_tokens": segment_categories_sum_tokens,
                "unclassified_segments": unclassified_segments,
                "unclassified_segments_tokens": unclassified_observed_segments_tokens,
                "observable_payload": observable_payload,
            }
        )
        if session_id:
            latest_prompt_segmentation.setdefault("scope", "current_session")
            latest_prompt_segmentation.setdefault("session_id", session_id)
        normalized["latest_prompt_segmentation"] = latest_prompt_segmentation

    return normalized

def _weclaw_tokens_contract(
    store: Any | None,
    *,
    profile: str,
    profile_tokenizer_report: dict[str, Any] | None = None,
    profile_model: str | None = None,
    provider: str | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    route_events, route_unavailable_reason = _weclaw_usage_events_for_profile(store, profile=profile)
    scoped_events, scoped_unavailable_reason = (
        _weclaw_usage_events_for_profile(store, profile=profile, session_id=session_id)
        if session_id
        else (route_events, route_unavailable_reason)
    )
    events = scoped_events
    unavailable_reason = scoped_unavailable_reason

    primary_events = [event for event in events if str(event.get("purpose") or "final") in _WECLAW_PRIMARY_USAGE_PURPOSES]
    auxiliary_events = [event for event in events if str(event.get("purpose") or "final") not in _WECLAW_PRIMARY_USAGE_PURPOSES]
    route_auxiliary_events = [event for event in route_events if str(event.get("purpose") or "final") not in _WECLAW_PRIMARY_USAGE_PURPOSES]

    latest_any_request_id, latest_any_events = _weclaw_latest_turn_events(events)
    latest_primary_request_id, latest_primary_events = _weclaw_latest_turn_events(primary_events)
    latest_aux_request_id, latest_aux_events = _weclaw_latest_turn_events(auxiliary_events)

    if isinstance(profile_tokenizer_report, dict):
        report_session_id = profile_tokenizer_report.get("session_id")
        if session_id and report_session_id != session_id:
            tokenizer_contract = profile_tokenizer_report.get("tokenizer") if isinstance(profile_tokenizer_report.get("tokenizer"), dict) else _profile_tokenizer_contract(profile_model or DEFAULT_MODEL, provider)
            profile_tokenizer_section = _profile_tokenizer_unavailable_report(
                profile=profile,
                model=profile_model or DEFAULT_MODEL,
                provider=provider or os.environ.get("DEEPSEEK_PROXY_MODEL_PROVIDER", "deepseek"),
                reason="session_scoped_prompt_segmentation_not_observed",
            )
            profile_tokenizer_section["session_id"] = session_id
            profile_tokenizer_section["observed_session_id"] = report_session_id
            profile_tokenizer_section["scope"] = "current_session"
            profile_tokenizer_section["summary"]["reason"] = "session_scoped_prompt_segmentation_not_observed"
            profile_tokenizer_section["summary"]["action"] = "send one primary model request through this session, then re-check dsproxy status --weclaw-json --session-id"
            split = _weclaw_prompt_subcategory_split_contract(None, tokenizer_contract=tokenizer_contract, no_observed_prompt=True)
            split = dict(split)
            split["reason"] = "session_scoped_prompt_segmentation_not_observed"
            split["scope"] = "current_session"
            split["session_id"] = session_id
            split["observed_session_id"] = report_session_id
            split["action"] = "send one primary model request through this session, then re-check dsproxy status --weclaw-json --session-id"
            profile_tokenizer_section["prompt_subcategory_split"] = split
        else:
            profile_tokenizer_section = dict(profile_tokenizer_report)
            profile_tokenizer_section.setdefault("scope", "current_session" if session_id else "route_latest_observed_prompt")
            if session_id:
                profile_tokenizer_section.setdefault("session_id", session_id)
    else:
        profile_tokenizer_section = _profile_tokenizer_unavailable_report(
            profile=profile,
            model=profile_model or DEFAULT_MODEL,
            provider=provider or os.environ.get("DEEPSEEK_PROXY_MODEL_PROVIDER", "deepseek"),
            reason="no_profile_tokenizer_report_observed_for_route",
        )
        if session_id:
            profile_tokenizer_section["session_id"] = session_id
            profile_tokenizer_section["scope"] = "current_session"

    tokenizer_contract = profile_tokenizer_section.get("tokenizer") if isinstance(profile_tokenizer_section, dict) else None
    if not isinstance(tokenizer_contract, dict):
        tokenizer_contract = _profile_tokenizer_contract(profile_model or DEFAULT_MODEL, provider or os.environ.get("DEEPSEEK_PROXY_MODEL_PROVIDER", "deepseek"))

    embedded_prompt_split = profile_tokenizer_section.get("prompt_subcategory_split") if isinstance(profile_tokenizer_section, dict) else None
    if (
        isinstance(embedded_prompt_split, dict)
        and embedded_prompt_split.get("reason") == "session_scoped_prompt_segmentation_not_observed"
    ):
        prompt_subcategory_split = dict(embedded_prompt_split)
    else:
        prompt_subcategory_split = _weclaw_prompt_subcategory_split_contract(profile_tokenizer_section, tokenizer_contract=tokenizer_contract)
    if session_id:
        prompt_subcategory_split = dict(prompt_subcategory_split)
        prompt_subcategory_split.setdefault("scope", "current_session")
        prompt_subcategory_split.setdefault("session_id", session_id)

    attribution = _weclaw_token_attribution_contract(profile_tokenizer_section, tokenizer_contract=tokenizer_contract)
    prompt_split_precision = (
        str(prompt_subcategory_split.get("precision") or "local_profile_tokenizer_estimate")
        if prompt_subcategory_split.get("available") or bool(tokenizer_contract.get("available"))
        else "unavailable"
    )
    taxonomy = {
        "version": 11,
        "unit": "tokens",
        "source": "dsproxy_usage_ledger.provider_reported_usage_and_profile_tokenizer_estimate",
        "categories": [
            "input", "cached_input", "output", "reasoning",
            "primary_model_call", "auxiliary_model_call",
            "tool_bridge", "liveness_judge", "liveness_retry", "compaction", "semantic_audit",
            "user", "user_history", "assistant_history", "tool_output", "environment",
            "system", "developer", "compaction_summary", "runtime_injected", "other",
        ],
        "precision": {
            "provider_usage_totals": "exact_provider_reported",
            "purpose_attribution": "exact_dsproxy_call_purpose",
            "prompt_subcategory_split": prompt_split_precision,
            "context_window_used_tokens": "latest_primary_provider_prompt_tokens_estimate",
            "session_scope": "exact_current_session_when_session_id_available",
            "prompt_segmentation_scope": "current_session_when_session_id_available",
            "prompt_reconciliation": "compares displayed local prompt categories, locally observable prompt-bearing payload components, serialized payload diagnostics, and provider-reported prompt tokens",
        },
        "attribution_schema": {
            "version": 6,
            "provider_usage_totals": "exact aggregate provider fields",
            "purpose_attribution": "exact dsproxy model-call purpose fields",
            "session_scope": "usage_events.session_id derived from Codex Responses prompt_cache_key/client_metadata when available",
            "latest_primary_turn": "latest request group whose purpose is primary/final",
            "latest_any_model_call": "latest request group regardless of purpose",
            "latest_auxiliary_call": "latest request group whose purpose is not primary/final",
            "prompt_segmentation_scope": "latest prompt segmentation is exposed only for the matching session when session_id is supplied",
        },
    }

    def _empty_summary() -> dict[str, Any]:
        return {
            "model_call_count": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "cached_tokens": 0,
            "prompt_cache_hit_tokens": 0,
            "prompt_cache_miss_tokens": 0,
            "reasoning_tokens": 0,
            "estimated_cost_usd": 0.0,
            "estimated_cost_by_currency": {},
        }

    def _unavailable(reason: str, *, scope: str) -> dict[str, Any]:
        return {
            "available": False,
            "unit": "tokens",
            "scope": scope,
            "ledger_scope": scope,
            "is_estimated": False,
            "summary": _empty_summary(),
            "by_purpose": {},
            "events_tail": [],
            "model_call_count": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "cached_tokens": 0,
            "prompt_cache_hit_tokens": 0,
            "prompt_cache_miss_tokens": 0,
            "reasoning_tokens": 0,
            "missing": [reason],
            "reason": reason,
            "status": reason,
            "action": "send a primary model request through this scope, then re-check status",
            "source": "dsproxy_usage_ledger",
        }

    def _section(section_events: list[dict[str, Any]], *, request_id: str | None, source: str, scope: str, included_in_session_total: bool | None = None) -> dict[str, Any]:
        if not section_events:
            return _unavailable("usage_ledger_events_not_available_for_scope", scope=scope)
        summary = _weclaw_summarize_usage_events(section_events)
        result = {
            "available": True,
            "unit": "tokens",
            "scope": scope,
            "ledger_scope": scope,
            "is_estimated": False,
            "source": source,
            "request_id": request_id,
            "model_call_count": len(section_events),
            "prompt_tokens": _weclaw_usage_int(summary.get("prompt_tokens")),
            "completion_tokens": _weclaw_usage_int(summary.get("completion_tokens")),
            "total_tokens": _weclaw_usage_int(summary.get("total_tokens")),
            "cached_tokens": _weclaw_usage_int(summary.get("cached_tokens")),
            "prompt_cache_hit_tokens": _weclaw_usage_int(summary.get("prompt_cache_hit_tokens")),
            "prompt_cache_miss_tokens": _weclaw_usage_int(summary.get("prompt_cache_miss_tokens")),
            "cache_hit_ratio": summary.get("cache_hit_ratio"),
            "cache": _weclaw_cache_summary_from_summary(summary, scope=scope, source=f"{source}.summary.provider_cache_fields"),
            "reasoning_tokens": _weclaw_usage_int(summary.get("reasoning_tokens")),
            "summary": summary,
            "by_purpose": _weclaw_usage_by_purpose(section_events),
            "events_tail": section_events[:20],
            "missing": [],
            "reason": None,
        }
        if included_in_session_total is not None:
            result["included_in_session_total"] = included_in_session_total
        return result

    current_session_available = bool(session_id)
    session_scope = "current_session" if current_session_available else "profile_route_history"

    current_session_section = (
        _section(events, request_id=None, source="dsproxy_usage_ledger.current_session", scope="current_session", included_in_session_total=True)
        if current_session_available
        else {**_unavailable("session_id_not_available", scope="current_session"), "current_session_available": False, "action": "pass active Codex prompt_cache_key/session id to dsproxy status --weclaw-json --session-id"}
    )
    if current_session_available:
        current_session_section["session_id"] = session_id
        current_session_section["current_session_available"] = True

    latest_primary_section = _section(latest_primary_events, request_id=latest_primary_request_id, source="dsproxy_usage_ledger.latest_primary_turn.grouped_by_request_id", scope=session_scope)
    latest_any_section = _section(latest_any_events, request_id=latest_any_request_id, source="dsproxy_usage_ledger.latest_any_model_call.grouped_by_request_id", scope=session_scope)
    latest_aux_section = _section(latest_aux_events, request_id=latest_aux_request_id, source="dsproxy_usage_ledger.latest_auxiliary_call.grouped_by_request_id", scope=session_scope, included_in_session_total=True)
    prompt_subcategory_split = _weclaw_prompt_split_with_provider_coverage(
        prompt_subcategory_split,
        latest_primary_section,
        session_id=session_id,
    )
    session_total_section = _section(events, request_id=None, source="dsproxy_usage_ledger.current_session" if current_session_available else "dsproxy_usage_ledger.profile_route_history", scope=session_scope, included_in_session_total=True)
    if current_session_available:
        session_total_section["session_id"] = session_id
    else:
        session_total_section["current_session_available"] = False
        session_total_section["reason"] = "session_id_not_available"
        session_total_section["action"] = "pass active session id for current_session scope. This legacy section is profile_route_history."

    profile_route_total = _section(route_events, request_id=None, source="dsproxy_usage_ledger.profile_route_history", scope="profile_route_history", included_in_session_total=False) if route_events else _unavailable(route_unavailable_reason or "usage_ledger_events", scope="profile_route_history")
    if auxiliary_events:
        auxiliary_section = _section(
            auxiliary_events,
            request_id=None,
            source="dsproxy_usage_ledger.non_primary_purposes",
            scope=session_scope,
            included_in_session_total=True,
        )
    elif current_session_available:
        auxiliary_summary = _empty_summary()
        auxiliary_section = {
            "available": True,
            "unit": "tokens",
            "scope": "current_session",
            "ledger_scope": "current_session",
            "is_estimated": False,
            "source": "dsproxy_usage_ledger.non_primary_purposes",
            "request_id": None,
            "model_call_count": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "cached_tokens": 0,
            "prompt_cache_hit_tokens": 0,
            "prompt_cache_miss_tokens": 0,
            "cache_hit_ratio": None,
            "cache": _weclaw_cache_summary_from_summary(auxiliary_summary, scope="current_session", source="dsproxy_usage_ledger.non_primary_purposes.summary.provider_cache_fields"),
            "reasoning_tokens": 0,
            "summary": auxiliary_summary,
            "by_purpose": {},
            "events_tail": [],
            "missing": [],
            "reason": "no_auxiliary_model_call_in_current_session",
            "status": "no_auxiliary_model_call_in_current_session",
            "included_in_session_total": True,
        }
    else:
        auxiliary_section = _unavailable("auxiliary_usage_events_not_available", scope=session_scope)
    route_auxiliary_section = _section(route_auxiliary_events, request_id=None, source="dsproxy_usage_ledger.profile_route_history.non_primary_purposes", scope="profile_route_history", included_in_session_total=False) if route_auxiliary_events else _unavailable("auxiliary_usage_events_not_available", scope="profile_route_history")

    latest_prompt_segmentation = prompt_subcategory_split.get("latest_prompt_segmentation") if isinstance(prompt_subcategory_split, dict) else None
    if isinstance(latest_prompt_segmentation, dict):
        latest_prompt_segmentation = dict(latest_prompt_segmentation)
        latest_prompt_segmentation["request_id"] = latest_primary_request_id
        latest_prompt_segmentation["scope"] = "current_session" if session_id else "latest_primary_turn"
        latest_prompt_segmentation["session_id"] = session_id
        latest_prompt_segmentation["total_prompt_tokens_provider"] = latest_primary_section.get("summary", {}).get("prompt_tokens")
        prompt_subcategory_split = dict(prompt_subcategory_split)
        prompt_subcategory_split["latest_prompt_segmentation"] = latest_prompt_segmentation
        prompt_subcategory_split["scope"] = "current_session" if session_id else "latest_primary_turn"
        if session_id:
            prompt_subcategory_split["session_id"] = session_id

    prompt_reconciliation = (
        prompt_subcategory_split.get("prompt_reconciliation")
        if isinstance(prompt_subcategory_split, dict)
        else None
    )

    return {
        "taxonomy": taxonomy,
        "attribution": attribution,
        "profile_tokenizer": profile_tokenizer_section,
        "prompt_subcategory_split": prompt_subcategory_split,
        "prompt_reconciliation": prompt_reconciliation,
        "latest_prompt_segmentation": latest_prompt_segmentation,
        "session": current_session_section,
        "last_turn": latest_primary_section,
        "latest_primary_turn": latest_primary_section,
        "latest_any_model_call": latest_any_section,
        "latest_auxiliary_call": latest_aux_section,
        "session_total": session_total_section,
        "profile_route_total": profile_route_total,
        "auxiliary_model_calls": auxiliary_section,
        "profile_route_auxiliary_model_calls": route_auxiliary_section,
        "cache": {
            "available": True,
            "unit": "tokens",
            "source": "deepseek_usage.prompt_cache_hit_tokens_and_prompt_cache_miss_tokens_via_dsproxy_usage_ledger",
            "provider_authoritative": True,
            "session": current_session_section.get("cache") if isinstance(current_session_section, dict) else None,
            "last_turn": latest_primary_section.get("cache") if isinstance(latest_primary_section, dict) else None,
            "latest_primary_turn": latest_primary_section.get("cache") if isinstance(latest_primary_section, dict) else None,
            "latest_any_model_call": latest_any_section.get("cache") if isinstance(latest_any_section, dict) else None,
            "latest_auxiliary_call": latest_aux_section.get("cache") if isinstance(latest_aux_section, dict) else None,
            "auxiliary_model_calls": auxiliary_section.get("cache") if isinstance(auxiliary_section, dict) else None,
            "session_total": session_total_section.get("cache") if isinstance(session_total_section, dict) else None,
            "profile_route_total": profile_route_total.get("cache") if isinstance(profile_route_total, dict) else None,
            "profile_route_auxiliary_model_calls": route_auxiliary_section.get("cache") if isinstance(route_auxiliary_section, dict) else None,
        },
        "scope": {
            "requested_session_id": session_id,
            "current_session_available": current_session_available,
            "default_display_scope": "current_session" if current_session_available else "profile_route_history",
            "legacy_session_total_scope": session_scope,
            "route": "thinking" if profile.endswith("thinking") else "non_thinking",
        },
        "unavailable_reason": unavailable_reason,
    }


def _pricing_display_currency(balance: dict[str, Any] | None = None) -> str:
    configured = os.environ.get("DEEPSEEK_PROXY_DISPLAY_CURRENCY", "").strip().upper()
    if configured:
        return configured
    if isinstance(balance, dict):
        balance_currency = str(balance.get("currency") or "").strip().upper()
        if balance_currency:
            return balance_currency
    return "CNY"


def _usd_cny_fx_contract() -> dict[str, Any]:
    raw_rate = os.environ.get("DEEPSEEK_PROXY_USD_CNY_FX_RATE", "").strip()
    source = os.environ.get("DEEPSEEK_PROXY_USD_CNY_FX_SOURCE", "").strip()
    updated_at = os.environ.get("DEEPSEEK_PROXY_USD_CNY_FX_UPDATED_AT", "").strip()
    try:
        rate = float(raw_rate) if raw_rate else 7.20
    except ValueError:
        rate = 7.20
        source = source or "bundled_static_fx_snapshot_invalid_env_fallback"
    return {
        "available": True,
        "base_currency": "USD",
        "quote_currency": "CNY",
        "rate": rate,
        "source": source or ("env.DEEPSEEK_PROXY_USD_CNY_FX_RATE" if raw_rate else "bundled_static_fx_snapshot"),
        "updated_at": updated_at or "2026-05-18T00:00:00Z",
        "is_estimated": True,
        "action": "set DEEPSEEK_PROXY_USD_CNY_FX_RATE and DEEPSEEK_PROXY_USD_CNY_FX_UPDATED_AT to override the bundled static display-rate snapshot",
    }


def _pricing_money_amount(
    amount: float | int | None,
    *,
    source_currency: str = "USD",
    display_currency: str | None = None,
) -> dict[str, Any]:
    source = str(source_currency or "USD").upper()
    display = str(display_currency or source).upper()
    source_amount = float(amount or 0.0)
    if display == source:
        return {
            "amount": source_amount,
            "currency": display,
            "source_amount": source_amount,
            "source_currency": source,
            "display_currency": display,
            "converted": False,
            "fx_rate": None,
            "fx_source": None,
            "fx_updated_at": None,
        }

    if source == "USD" and display == "CNY":
        fx = _usd_cny_fx_contract()
        return {
            "amount": source_amount * float(fx["rate"]),
            "currency": display,
            "source_amount": source_amount,
            "source_currency": source,
            "display_currency": display,
            "converted": True,
            "fx_rate": fx["rate"],
            "fx_source": fx["source"],
            "fx_updated_at": fx["updated_at"],
            "fx": fx,
        }

    return {
        "amount": source_amount,
        "currency": source,
        "source_amount": source_amount,
        "source_currency": source,
        "display_currency": display,
        "converted": False,
        "conversion_available": False,
        "reason": f"fx_conversion_not_configured_for_{source}_to_{display}",
        "action": "configure an explicit fx adapter or display the source currency",
    }


def _pricing_context_for_usage_event(model: str) -> dict[str, Any]:
    pricing_path = _pricing_config_path()
    metadata = _pricing_metadata_from_path(pricing_path) if pricing_path.exists() else {}
    source_info = _pricing_source_info(pricing_path)
    prices = _load_model_pricing_usd_per_1m().get(model) or {}
    source_currency = str(metadata.get("currency") or "CNY").upper()
    return {
        "pricing_model": model,
        "pricing_currency": source_currency,
        "pricing_unit": str(metadata.get("unit") or "per_million_tokens"),
        "pricing_source": source_info.get("source"),
        "pricing_source_kind": metadata.get("source_kind") or source_info.get("source_kind"),
        "pricing_updated_at": metadata.get("fetched_at") or metadata.get("snapshot_created_at") or metadata.get("updated_at"),
        "pricing_source_url": metadata.get("source_url") or DEEPSEEK_OFFICIAL_PRICING_URL,
        "pricing_input_cache_hit": float(prices.get("input_cache_hit") or 0.0),
        "pricing_input_cache_miss": float(prices.get("input_cache_miss") or 0.0),
        "pricing_output": float(prices.get("output") or 0.0),
    }


def _cost_ledger_event_summary(event: dict[str, Any], *, display_currency: str) -> dict[str, Any]:
    source_currency = str(event.get("estimated_cost_source_currency") or event.get("pricing_currency") or "USD").upper()
    source_amount_raw = event.get("estimated_cost_source_amount")
    source_amount = _weclaw_usage_float(source_amount_raw if source_amount_raw is not None else event.get("estimated_cost_usd"))
    money = _pricing_money_amount(source_amount, source_currency=source_currency, display_currency=display_currency)
    return {
        "created_at": event.get("created_at"),
        "request_id": event.get("request_id"),
        "response_id": event.get("response_id"),
        "purpose": event.get("purpose"),
        "call_index": event.get("call_index"),
        "route": event.get("route") or ("thinking" if bool(event.get("thinking_enabled")) else "non_thinking"),
        "thinking_enabled": bool(event.get("thinking_enabled")),
        "effort": event.get("effort"),
        "requested_model": event.get("requested_model"),
        "effective_model": event.get("effective_model") or event.get("model"),
        "upstream_model": event.get("upstream_model"),
        "pricing_model": event.get("pricing_model") or event.get("effective_model") or event.get("model"),
        "pricing_currency": event.get("pricing_currency") or source_currency,
        "pricing_source_kind": event.get("pricing_source_kind"),
        "pricing_updated_at": event.get("pricing_updated_at"),
        "pricing_unit": event.get("pricing_unit"),
        "prices": {
            "input_cache_hit": event.get("pricing_input_cache_hit"),
            "input_cache_miss": event.get("pricing_input_cache_miss"),
            "output": event.get("pricing_output"),
        },
        "usage": {
            "prompt_tokens": event.get("prompt_tokens"),
            "cached_tokens": event.get("cached_tokens"),
            "prompt_cache_hit_tokens": event.get("prompt_cache_hit_tokens") if event.get("prompt_cache_hit_tokens") is not None else event.get("cached_tokens"),
            "prompt_cache_miss_tokens": event.get("prompt_cache_miss_tokens") if event.get("prompt_cache_miss_tokens") is not None else max(0, _weclaw_usage_int(event.get("prompt_tokens")) - _weclaw_usage_int(event.get("cached_tokens"))),
            "cache_miss_tokens": event.get("prompt_cache_miss_tokens") if event.get("prompt_cache_miss_tokens") is not None else max(0, _weclaw_usage_int(event.get("prompt_tokens")) - _weclaw_usage_int(event.get("cached_tokens"))),
            "completion_tokens": event.get("completion_tokens"),
            "reasoning_tokens": event.get("reasoning_tokens"),
            "total_tokens": event.get("total_tokens"),
        },
        "estimated_cost_source_amount": source_amount,
        "estimated_cost_source_currency": source_currency,
        "estimated_cost_usd_legacy": _weclaw_usage_float(event.get("estimated_cost_usd")),
        "estimated_cost": money["amount"],
        "currency": money["currency"],
        "converted": money.get("converted"),
    }

def _weclaw_pricing_contract(model: str | None, *, display_currency: str | None = None) -> dict[str, Any]:
    pricing_path = _pricing_config_path()
    path_exists = pricing_path.exists()
    source_info = _pricing_source_info(pricing_path)
    metadata = _pricing_metadata_from_path(pricing_path) if path_exists else {}
    raw_pricing_doc: dict[str, Any] = {}
    if path_exists:
        try:
            loaded = json.loads(pricing_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                raw_pricing_doc = loaded
        except Exception:
            raw_pricing_doc = {}

    model_metadata_all = raw_pricing_doc.get("__model_metadata__") if isinstance(raw_pricing_doc.get("__model_metadata__"), dict) else {}
    prices = _load_model_pricing_usd_per_1m()
    model_key = str(model or DEFAULT_MODEL)
    model_prices = prices.get(model_key)
    model_metadata = model_metadata_all.get(model_key, {}) if isinstance(model_metadata_all, dict) else {}
    if not isinstance(model_metadata, dict):
        model_metadata = {}

    source_kind = str(metadata.get("source_kind") or source_info["source_kind"])
    source_url = metadata.get("source_url") or None
    official_reference_url = DEEPSEEK_OFFICIAL_PRICING_URL
    ttl_seconds = metadata.get("ttl_seconds")
    is_stale = _pricing_is_stale(metadata)
    fetched_at = metadata.get("fetched_at")
    snapshot_created_at = metadata.get("snapshot_created_at")
    updated_at = fetched_at or snapshot_created_at or metadata.get("updated_at")
    official_cache = source_kind == "official_docs_html"
    bundled_snapshot = source_kind == "bundled_official_docs_snapshot"
    externally_configured = source_info["source_kind"] == "external_config"
    source_trust = (
        "official_docs_html_cache"
        if official_cache
        else "bundled_official_docs_snapshot"
        if bundled_snapshot
        else "external_config"
        if externally_configured
        else "project_default_config"
    )
    official_price_available = bool(official_cache and fetched_at)

    source_currency = str(metadata.get("currency") or "CNY").upper()
    target_currency = _pricing_display_currency({"currency": display_currency} if display_currency else None)
    effective_prices = model_metadata.get("effective_prices") if isinstance(model_metadata.get("effective_prices"), dict) else (model_prices or {})
    original_prices = model_metadata.get("original_prices") if isinstance(model_metadata.get("original_prices"), dict) else {}
    discount_prices = model_metadata.get("discount_prices") if isinstance(model_metadata.get("discount_prices"), dict) else {}
    discount = model_metadata.get("discount") if isinstance(model_metadata.get("discount"), dict) else {"available": False, "validity_confidence": "none"}

    cache_hit = _pricing_money_amount(effective_prices.get("input_cache_hit"), source_currency=source_currency, display_currency=target_currency)
    cache_miss = _pricing_money_amount(effective_prices.get("input_cache_miss"), source_currency=source_currency, display_currency=target_currency)
    output = _pricing_money_amount(effective_prices.get("output"), source_currency=source_currency, display_currency=target_currency)

    fx = cache_hit.get("fx") if isinstance(cache_hit, dict) and isinstance(cache_hit.get("fx"), dict) else (
        _usd_cny_fx_contract() if source_currency == "USD" and target_currency == "CNY" else None
    )
    all_models = sorted(key for key in prices if isinstance(key, str) and not key.startswith("__"))

    return {
        "available": bool(model_prices),
        "provider": "deepseek",
        "model": model_key,
        "route": "thinking" if _thinking_enabled() else "non_thinking",
        "currency": target_currency,
        "source_currency": source_currency,
        "display_currency": target_currency,
        "converted": source_currency != target_currency,
        "fx_rate": fx.get("rate") if isinstance(fx, dict) else None,
        "fx_source": fx.get("source") if isinstance(fx, dict) else None,
        "fx_updated_at": fx.get("updated_at") if isinstance(fx, dict) else None,
        "fx": fx,
        "unit": "per_million_tokens",
        "unit_legacy": "per_1m_tokens",
        "source": source_info["source"],
        "source_path": str(pricing_path),
        "source_url": source_url,
        "official_reference_url": official_reference_url,
        "source_kind": source_kind,
        "source_trust": source_trust,
        "fallback_used": bool(source_info.get("fallback_used")) or not path_exists,
        "is_stale": is_stale,
        "fetched_at": fetched_at,
        "snapshot_created_at": snapshot_created_at,
        "updated_at": updated_at,
        "expires_at": metadata.get("expires_at"),
        "ttl_seconds": ttl_seconds,
        "prices": effective_prices,
        "current_prices": effective_prices,
        "effective_prices": effective_prices,
        "original_prices": original_prices,
        "discount_prices": discount_prices,
        "discount": discount,
        "discount_available": bool(discount.get("available")),
        "discount_label": discount.get("label"),
        "discount_valid_from": discount.get("valid_from"),
        "discount_valid_until": discount.get("valid_until"),
        "discount_validity_confidence": discount.get("validity_confidence"),
        "prices_source": {
            "input_cache_hit": effective_prices.get("input_cache_hit"),
            "input_cache_miss": effective_prices.get("input_cache_miss"),
            "output": effective_prices.get("output"),
            "currency": source_currency,
            "unit": "per_million_tokens",
            "price_semantics": "current_effective_price",
        },
        "prices_display": {
            "input_cache_hit": cache_hit.get("amount"),
            "input_cache_miss": cache_miss.get("amount"),
            "output": output.get("amount"),
            "currency": target_currency,
            "unit": "per_million_tokens",
            "price_semantics": "current_effective_price",
        },
        "cache_hit_input": cache_hit,
        "cache_miss_input": cache_miss,
        "output": output,
        "reasoning_output": {
            "available": False,
            "amount": None,
            "currency": target_currency,
            "source_currency": source_currency,
            "reason": "provider_pricing_not_split_by_reasoning_content",
            "action": "treat provider completion_tokens as billable output tokens unless DeepSeek exposes separate reasoning output pricing",
        },
        "all_models": all_models,
        "missing": [] if model_prices else ["model_pricing_entry"],
        "official_source": {
            "available": official_price_available,
            "source_url": official_reference_url,
            "source_kind": "official_docs_html",
            "fetched_at": fetched_at,
            "updated_at": fetched_at,
            "expires_at": metadata.get("expires_at"),
            "ttl_seconds": ttl_seconds,
            "is_stale": is_stale if official_cache else None,
            "requires_refresh": not official_price_available,
            "reason": None if official_price_available else "official_pricing_cache_not_available_for_active_status",
            "action": None if official_price_available else "run dsproxy pricing refresh --write-cache --json, then re-check dsproxy status --weclaw-json",
        },
        "pricing_source_state": {
            "current_prices_are_official_live_cache": official_price_available,
            "current_prices_are_bundled_official_snapshot": bundled_snapshot,
            "current_prices_are_external_config": externally_configured,
            "cost_uses_turn_ledger_estimated_cost": True,
            "cost_uses_current_prices": bool(model_prices),
            "must_display_source_label": True,
            "discount_metadata_available": bool(model_metadata),
        },
        "refresh": {
            "available": True,
            "reason": None,
            "action": "run dsproxy pricing refresh --json to fetch and validate official DeepSeek pricing HTML; add --write-cache to persist it",
            "source_kind": "official_docs_html",
            "source_url": official_reference_url,
            "requires_live_network": True,
            "writes_cache": False,
            "write_cache_requires_flag": "--write-cache",
        },
    }



def _weclaw_cost_contract(tokens: dict[str, Any], pricing: dict[str, Any], balance: dict[str, Any] | None = None) -> dict[str, Any]:
    last_turn = tokens.get("latest_primary_turn") if isinstance(tokens, dict) else {}
    if not isinstance(last_turn, dict) or not last_turn:
        last_turn = tokens.get("last_turn") if isinstance(tokens, dict) else {}

    session_section = tokens.get("session") if isinstance(tokens, dict) else {}
    session_available = bool(isinstance(session_section, dict) and session_section.get("available"))
    profile_route_total = tokens.get("profile_route_total") if isinstance(tokens, dict) else {}
    auxiliary = tokens.get("auxiliary_model_calls") if isinstance(tokens, dict) else {}

    pricing_available = bool(isinstance(pricing, dict) and pricing.get("available"))
    pricing_stale = bool(pricing.get("is_stale")) if isinstance(pricing, dict) else False
    available = bool(isinstance(last_turn, dict) and last_turn.get("available") and session_available and pricing_available and not pricing_stale)

    display_currency = str((pricing.get("display_currency") if isinstance(pricing, dict) else None) or _pricing_display_currency(balance)).upper()

    def _summary(section: Any) -> dict[str, Any]:
        if not isinstance(section, dict):
            return {}
        raw = section.get("summary")
        return raw if isinstance(raw, dict) else {}

    def _money_from_summary(section: Any) -> dict[str, Any]:
        summary = _summary(section)
        by_currency = summary.get("estimated_cost_by_currency")
        if isinstance(by_currency, dict) and by_currency:
            total = 0.0
            converted = False
            fx = None
            sources = []
            for currency, amount in by_currency.items():
                money = _pricing_money_amount(float(amount or 0.0), source_currency=str(currency).upper(), display_currency=display_currency)
                total += float(money.get("amount") or 0.0)
                converted = converted or bool(money.get("converted"))
                if isinstance(money.get("fx"), dict):
                    fx = money["fx"]
                sources.append({"currency": str(currency).upper(), "amount": float(amount or 0.0)})
            return {
                "amount": total,
                "currency": display_currency,
                "display_currency": display_currency,
                "source_amount": None,
                "source_currency": "mixed" if len(sources) > 1 else sources[0]["currency"],
                "source_breakdown": sources,
                "converted": converted,
                "fx_rate": fx.get("rate") if isinstance(fx, dict) else None,
                "fx_source": fx.get("source") if isinstance(fx, dict) else None,
                "fx_updated_at": fx.get("updated_at") if isinstance(fx, dict) else None,
                "fx": fx,
            }
        if "estimated_cost_usd" not in summary:
            return {"amount": None, "currency": display_currency, "display_currency": display_currency, "source_amount": None, "source_currency": None, "converted": False, "fx": None}
        return _pricing_money_amount(_weclaw_usage_float(summary.get("estimated_cost_usd")), source_currency="USD", display_currency=display_currency)

    last_money = _money_from_summary(last_turn)
    session_money = _money_from_summary(session_section)
    auxiliary_money = _money_from_summary(auxiliary)
    profile_route_money = _money_from_summary(profile_route_total)
    cash_money = session_money if session_available else profile_route_money
    display_money = session_money if session_available else cash_money

    missing = []
    if not session_available:
        missing.append("current_session_cost")
    if not pricing_available:
        missing.append("pricing")
    if pricing_stale:
        missing.append("pricing_stale")

    reason = None
    if not session_available:
        reason = "current_session_cost_unavailable"
    elif not pricing_available:
        reason = "pricing_unavailable"
    elif pricing_stale:
        reason = "pricing_stale"

    last_events = last_turn.get("events_tail") if isinstance(last_turn, dict) else []
    aux_events = auxiliary.get("events_tail") if isinstance(auxiliary, dict) else []
    reasoning_tokens = _weclaw_usage_int(_summary(session_section).get("reasoning_tokens"))

    session_contract = {
        "available": session_available,
        "scope": "current_session",
        "estimated_cost": session_money.get("amount") if session_available else None,
        "display_currency": display_currency,
        "amount": session_money if session_available else None,
        "source": "tokens.session.summary.estimated_cost_by_currency",
        "reason": None if session_available else "current_session_cost_unavailable",
        "action": None if session_available else "pass active session id and send at least one model request in that session",
    }

    turn_ledger = {
        "available": session_available,
        "precision": "per_turn_model_pricing",
        "source": "usage_events.estimated_cost_source_amount_summed_without_repricing_history",
        "cost_uses_provider_cache_hit_miss_tokens": True,
        "prompt_cost_semantics": "per_turn_cost_uses_provider_prompt_cache_hit_tokens_and_prompt_cache_miss_tokens_when_available",
        "session_cost_is_sum_of_turn_estimated_cost": True,
        "session_cost_recomputed_from_current_model": False,
        "display_currency": display_currency,
        "scope": "current_session" if session_available else "unavailable",
        "last_turn_events": [_cost_ledger_event_summary(event, display_currency=display_currency) for event in (last_events or [])[:20] if isinstance(event, dict)],
        "auxiliary_events": [_cost_ledger_event_summary(event, display_currency=display_currency) for event in (aux_events or [])[:20] if isinstance(event, dict)],
    }

    return {
        "available": available,
        "scope": "current_session" if session_available else "unavailable",
        "ledger_scope": "current_session" if session_available else "unavailable",
        "currency": display_currency,
        "display_currency": display_currency,
        "source_currency": display_money.get("source_currency"),
        "source_breakdown": display_money.get("source_breakdown"),
        "converted": bool(display_money.get("converted")),
        "fx_rate": display_money.get("fx_rate"),
        "fx_source": display_money.get("fx_source"),
        "fx_updated_at": display_money.get("fx_updated_at"),
        "fx": display_money.get("fx"),
        "is_estimated": True,
        "source": "tokens.session.summary.estimated_cost_by_currency",
        "legacy_source": "usage_events.estimated_cost_usd_for_usd_rows_only",
        "ledger_precision": "per_turn_model_pricing",
        "pricing_source": pricing.get("source"),
        "pricing_source_kind": pricing.get("source_kind"),
        "pricing_source_trust": pricing.get("source_trust"),
        "pricing_source_url": pricing.get("source_url") or pricing.get("official_reference_url"),
        "official_pricing_available": bool((pricing.get("official_source") or {}).get("available")) if isinstance(pricing.get("official_source"), dict) else False,
        "pricing_updated_at": pricing.get("fetched_at") or pricing.get("updated_at"),
        "updated_at": pricing.get("fetched_at") or pricing.get("updated_at"),
        "session": session_contract,
        "provider_cache": {
            "available": True,
            "source": "tokens.cache.provider_authoritative_request_level_totals",
            "session": (tokens.get("cache") or {}).get("session") if isinstance(tokens.get("cache"), dict) else None,
            "last_turn": (tokens.get("cache") or {}).get("last_turn") if isinstance(tokens.get("cache"), dict) else None,
            "auxiliary": (tokens.get("cache") or {}).get("auxiliary_model_calls") if isinstance(tokens.get("cache"), dict) else None,
        },
        "cost_uses_provider_cache_hit_miss_tokens": True,
        "last_turn_estimated_cost": last_money.get("amount") if isinstance(last_turn, dict) and last_turn.get("available") else None,
        "session_estimated_cost": session_money.get("amount") if session_available else None,
        "auxiliary_estimated_cost": auxiliary_money.get("amount") if isinstance(auxiliary, dict) and auxiliary.get("available") else 0.0,
        "total_estimated_cost": session_money.get("amount") if session_available else None,
        "profile_route_estimated_cost": profile_route_money.get("amount") if isinstance(profile_route_total, dict) and profile_route_total.get("available") else None,
        "cash_estimated_cost": cash_money.get("amount"),
        "cash_definition": "current_session_estimated_cost_when_session_id_available_else_profile_route_history",
        "last_turn_estimated_cost_usd_legacy": _weclaw_usage_float(_summary(last_turn).get("estimated_cost_usd")),
        "session_estimated_cost_usd_legacy": _weclaw_usage_float(_summary(session_section).get("estimated_cost_usd")),
        "auxiliary_estimated_cost_usd_legacy": _weclaw_usage_float(_summary(auxiliary).get("estimated_cost_usd")),
        "amounts": {"last": last_money, "session": session_money if session_available else None, "auxiliary": auxiliary_money, "cash": cash_money, "profile_route": profile_route_money},
        "usage_available": session_available,
        "pricing_available": pricing_available,
        "pricing_stale": pricing_stale,
        "reason": reason,
        "missing": missing,
        "reasoning_cost_available": False,
        "reasoning_cost_reason": "provider_usage_not_split" if reasoning_tokens else "provider_usage_has_no_reasoning_tokens",
        "reasoning_tokens_observed": reasoning_tokens,
        "reasoning_cost_action": "do not estimate separate reasoning_content cost unless provider reports separately priced reasoning output",
        "turn_ledger": turn_ledger,
        "notes": [
            "Token counts are provider-reported exact usage totals.",
            "Current-session cost is available only from tokens.session when dsproxy status is called with an active session id.",
            "Cost is estimated from per-turn dsproxy usage ledger entries, not by multiplying historical session tokens by the current active model price.",
            "Prompt input cost uses provider prompt_cache_hit_tokens and prompt_cache_miss_tokens when available; it does not treat all prompt tokens as miss or all as hit.",
        ],
    }


def _weclaw_balance_unavailable(reason: str, *, provider: str = "deepseek") -> dict[str, Any]:
    status_action = {
        "disabled_by_request": ("not_configured", "enable balance query when requesting WeClaw verbose status"),
        "not_queried": ("not_configured", "query the runtime WeClaw status endpoint with include_balance=true"),
        "api_key_not_configured": ("not_configured", "configure provider balance API key"),
        "balance_client_unavailable": ("provider_unsupported", "provider does not expose balance API through this client"),
        "balance_request_auth_failed": ("auth_failed", "check auth"),
        "balance_request_network_error": ("network_error", "check network"),
        "balance_request_failed": ("api_error", "check provider balance API response"),
        "balance_response_unrecognized": ("api_error", "check provider balance API response"),
    }
    status, action = status_action.get(reason, ("not_implemented", "provider balance integration not implemented"))
    return {
        "available": False,
        "status": status,
        "provider": provider,
        "source": "provider_balance_api",
        "reason": reason,
        "action": action,
        "updated_at": None,
        "fetched_at": None,
        "currency": None,
        "amount": None,
        "display": None,
        "balance": None,
    }


def _weclaw_balance_display_fields(balance: Any) -> dict[str, Any]:
    if not isinstance(balance, dict):
        return {
            "currency": None,
            "amount": None,
            "display": None,
        }

    balance_infos = balance.get("balance_infos")
    first_info = balance_infos[0] if isinstance(balance_infos, list) and balance_infos else None
    if not isinstance(first_info, dict):
        return {
            "currency": None,
            "amount": None,
            "display": None,
        }

    currency = first_info.get("currency")
    raw_amount = first_info.get("total_balance")
    amount = None
    try:
        amount = float(raw_amount) if raw_amount is not None else None
    except (TypeError, ValueError):
        amount = None

    display = None
    if raw_amount is not None and currency:
        display = f"{raw_amount} {currency}"
    elif raw_amount is not None:
        display = str(raw_amount)

    return {
        "currency": currency,
        "amount": amount,
        "display": display,
    }


def _weclaw_balance_exception_reason(exc: Exception) -> str:
    if isinstance(exc, HTTPException):
        detail = exc.detail
        upstream_status = None
        if isinstance(detail, dict):
            upstream_status = detail.get("status_code")
        if upstream_status in {401, 403}:
            return "balance_request_auth_failed"
        return "balance_request_failed"
    if isinstance(exc, httpx.TransportError):
        return "balance_request_network_error"
    return "balance_request_failed"


async def _weclaw_balance_contract(
    *,
    deepseek_client: Any | None,
    include_balance: bool = True,
) -> dict[str, Any]:
    if not include_balance:
        return _weclaw_balance_unavailable("disabled_by_request")
    if deepseek_client is None or not hasattr(deepseek_client, "user_balance"):
        return _weclaw_balance_unavailable("balance_client_unavailable")

    api_key = getattr(deepseek_client, "api_key", None)
    if deepseek_client.__class__ is DeepSeekClient and api_key is not None and not str(api_key).strip():
        return _weclaw_balance_unavailable("api_key_not_configured")

    try:
        balance = await deepseek_client.user_balance()
    except Exception as exc:
        reason = _weclaw_balance_exception_reason(exc)
        return {
            **_weclaw_balance_unavailable(reason),
            "error_type": type(exc).__name__,
            "message": str(exc)[:1000],
        }

    display_fields = _weclaw_balance_display_fields(balance)
    return {
        "available": True,
        "status": "ok",
        "source": "provider_balance_api",
        "provider": "deepseek",
        "updated_at": _now(),
        "fetched_at": _now(),
        "balance": balance,
        "reason": None,
        "action": None,
        **display_fields,
    }

def _runtime_weclaw_status(
    profile: str,
    *,
    store: Any | None = None,
    balance: dict[str, Any] | None = None,
    deepseek_client: Any | None = None,
    last_context_compaction_report: dict[str, Any] | None = None,
    profile_tokenizer_report: dict[str, Any] | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    profile_status = _runtime_weclaw_profile_status(profile)
    model_contract = profile_status.get("model", {})
    effective_model = None
    provider = os.environ.get("DEEPSEEK_PROXY_MODEL_PROVIDER", "deepseek")
    if isinstance(model_contract, dict):
        effective_model = (
            model_contract.get("effective_model")
            or model_contract.get("upstream_model")
            or model_contract.get("codex_model")
            or model_contract.get("model")
        )
        provider = str(model_contract.get("provider") or provider or "deepseek")

    balance_contract = balance if isinstance(balance, dict) else _weclaw_balance_unavailable("not_queried")
    display_currency = _pricing_display_currency(balance_contract)
    pricing = _weclaw_pricing_contract(str(effective_model or DEFAULT_MODEL), display_currency=display_currency)

    tokens = _weclaw_tokens_contract(
        store,
        profile=profile,
        profile_tokenizer_report=profile_tokenizer_report,
        profile_model=str(effective_model or DEFAULT_MODEL),
        provider=provider,
        session_id=session_id,
    )
    cost = _weclaw_cost_contract(tokens, pricing, balance_contract)
    cost["balance"] = balance_contract

    context_status = _proxy_context_status()
    runtime_payload_guard = _runtime_payload_guard_contract(
        context_status,
        compaction_report=last_context_compaction_report,
        trimming_report=getattr(deepseek_client, "last_context_trimming_report", None),
    )
    semantic_status = _weclaw_enrich_semantic_compaction_status(_semantic_compaction_runtime_status())
    context_window = _weclaw_context_window_with_usage_estimate(
        dict(profile_status.get("context_window", {})),
        tokens,
    )
    context_window["runtime"] = {
        "available": True,
        "unit": "chars",
        "source": "dsproxy_runtime._proxy_context_status",
        "context": context_status,
        "payload_guard": runtime_payload_guard,
        "semantic_compaction": semantic_status,
    }
    context_window["runtime_compaction"] = context_status.get("compaction") if isinstance(context_status, dict) else None
    context_window["runtime_trimming"] = context_status.get("trimming") if isinstance(context_status, dict) else None

    payload = {
        "status": profile_status.get("status", "ok"),
        "version": {
            "public_version": PROXY_PUBLIC_VERSION,
            "internal_version": PROXY_INTERNAL_VERSION,
        },
        "profile": profile,
        "session": {
            "id": session_id,
            "available": bool(session_id),
            "scope": "current_session" if session_id else "profile_route_history",
            "ledger_scope": "current_session" if session_id else "profile_route_history",
            "current_session_available": bool(session_id),
            "reason": None if session_id else "session_id_not_available",
            "action": None if session_id else "pass active Codex prompt_cache_key/session id to dsproxy status --weclaw-json --session-id",
        },
        "model": model_contract,
        "effort": profile_status.get("effort", {}),
        "context_window": context_window,
        "tokens": tokens,
        "pricing": pricing,
        "cost": cost,
        "balance": balance_contract,
        "runtime_payload_guard": runtime_payload_guard,
        "compaction": {
            "available": True,
            "is_estimated": False,
            "source": "dsproxy_runtime._proxy_context_status",
            "unit": "chars",
            "runtime_context": context_status,
            "runtime_payload_guard": runtime_payload_guard,
            "semantic_compaction": semantic_status,
            "missing": [],
        },
        "semantic_compaction": semantic_status,
        "health": profile_status.get("health", {}),
    }
    payload["diagnostics"] = _weclaw_diagnostics_contract(payload)
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
    app.state.last_context_compaction_report = None
    app.state.last_profile_tokenizer_report_by_profile = {}

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
            "command_risk_policy": _command_risk_policy_status(),
            "context": _proxy_context_status(),
            "agent_liveness": _proxy_agent_liveness_status(),
            "semantic_compaction": _semantic_compaction_runtime_status(),
            "store": _store_info(app.state.store),
            "started_at": app.state.started_at,
            "uptime_seconds": max(0, _now() - app.state.started_at),
            "repair_count": app.state.repair_count,
            "deepseek_base_url": getattr(app.state.deepseek_client, "base_url", None),
        }

    @app.get("/v1/proxy/weclaw/profile-status")
    async def proxy_weclaw_profile_status(profile: str = "deepseek-thinking") -> dict[str, Any]:
        return _runtime_weclaw_profile_status(profile)


    @app.get("/v1/proxy/weclaw/status")
    async def proxy_weclaw_status(profile: str = "deepseek-thinking", include_balance: bool = True, session_id: str | None = None) -> dict[str, Any]:
        balance = await _weclaw_balance_contract(
            deepseek_client=app.state.deepseek_client,
            include_balance=include_balance,
        )
        return _runtime_weclaw_status(
            profile,
            store=app.state.store,
            balance=balance,
            deepseek_client=app.state.deepseek_client,
            last_context_compaction_report=getattr(app.state, "last_context_compaction_report", None),
            profile_tokenizer_report=getattr(app.state, "last_profile_tokenizer_report_by_profile", {}).get(profile),
            session_id=session_id,
        )

    @app.get("/v1/proxy/tool-bridge/status")
    async def proxy_tool_bridge_status() -> dict[str, Any]:
        return {
            "status": "ok",
            "version": PROXY_VERSION,
            "tool_bridge": _tool_bridge_status(),
            "command_risk_policy": _command_risk_policy_status(),
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
        original_deepseek_tools = deepseek_tools
        user_tool_control_policy_report = _build_user_tool_control_policy_report(
            input_value,
            original_deepseek_tools,
        )
        deepseek_tools, user_tool_control_policy_report = _apply_user_tool_control_policy_to_tools(
            user_tool_control_policy_report,
            original_deepseek_tools,
        )
        _write_user_tool_control_policy_report(user_tool_control_policy_report)
        _debug_trace_event(
            response_id,
            "user_tool_control_policy_applied",
            **user_tool_control_policy_report,
        )

        # Trim tool outputs before removing function_call items. In
        # previous_response_id turns, Codex may send both function_call and
        # function_call_output items. The function_call item must not be
        # converted into another assistant tool-call message, but its name is
        # still needed to classify the matching output, for example view_image
        # as image_payload.
        input_value, tool_output_trim_report = _apply_tool_output_safe_trimming(input_value)
        if previous_response_id and isinstance(input_value, list):
            input_value = [
                item
                for item in input_value
                if item.get("type") != "function_call"
            ]

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
            session_id=_session_id_from_request_payload(payload),
        )
        context_compaction_report["observed_at"] = _runtime_payload_guard_observed_at()
        context_compaction_report["source"] = "runtime_context_builder"
        context_compaction_report["current_chars_source"] = "runtime_context_builder"
        context_compaction_report["current_chars_precision"] = "exact"
        app.state.last_context_compaction_report = context_compaction_report
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
        profile_name = "deepseek-thinking" if _thinking_enabled() else "deepseek"
        profile_tokenizer_report = _profile_tokenizer_report_for_messages(
            messages_for_deepseek,
            profile=profile_name,
            model=model,
            provider=os.environ.get("DEEPSEEK_PROXY_MODEL_PROVIDER", "deepseek"),
            session_id=_session_id_from_request_payload(payload),
            payload=chat_payload,
        )
        app.state.last_profile_tokenizer_report_by_profile[profile_name] = profile_tokenizer_report
        _debug_trace_event(
            response_id,
            "profile_tokenizer_accounting",
            available=profile_tokenizer_report.get("available"),
            profile=profile_name,
            model=model,
            summary=profile_tokenizer_report.get("summary"),
            tokenizer=profile_tokenizer_report.get("tokenizer"),
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
                user_tool_control_policy_report=user_tool_control_policy_report,
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
