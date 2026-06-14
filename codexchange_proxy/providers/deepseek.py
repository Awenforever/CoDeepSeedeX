from __future__ import annotations

from collections.abc import Mapping
import re
import time
from pathlib import Path
from typing import Any

from .base import ProviderCapabilities, ProviderRoute, UpstreamRequest, ValidationRequest


class DeepSeekProviderAdapter:
    """DeepSeek model API adapter.

    This adapter is intentionally small in p3.0a2. Runtime call routing still lives in
    codexchange_proxy.app. Follow-up patches will move the matching runtime functions
    behind this adapter without changing external contracts.
    """

    provider_id = "deepseek"
    family = "deepseek"
    wire_protocol = "openai_chat_completions"
    default_base_url = "https://api.deepseek.com"
    official_pricing_url = "https://api-docs.deepseek.com/zh-cn/quick_start/pricing/"
    official_pricing_url_en = "https://api-docs.deepseek.com/zh-cn/quick_start/pricing//"
    api_key_env_names = ("COX_MODEL_API_KEY",)
    official_tokenizer_kind = "deepseek_official_current"
    legacy_tokenizer_kind = "deepseek_v3"
    tokenizer_env_names = ("COX_PROFILE_TOKENIZER_JSON", "COX_DEEPSEEK_TOKENIZER_JSON")
    tokenizer_archive_name = "deepseek_v3_tokenizer.zip"
    capabilities = ProviderCapabilities(
        reasoning=True,
        reasoning_effort=("low", "medium", "high", "max"),
        reasoning_effort_max=True,
        response_reasoning_field="reasoning_content",
        streaming=True,
        tool_calls=True,
        model_catalog=True,
        pricing=True,
        account_balance=True,
        tokenizer=True,
        native_responses=False,
        notes=("uses OpenAI-compatible chat completions with provider-specific reasoning extensions",),
    )

    def normalize_reasoning_effort(self, value: object) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip().lower()
        if not normalized:
            return None
        if normalized == "xhigh":
            return "max"
        if normalized in {"low", "medium", "high", "max"}:
            return normalized
        return None

    def build_chat_payload(self, route: ProviderRoute, responses_request: Mapping[str, Any]) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": route.model,
            "messages": list(responses_request.get("messages") or []),
        }
        if "stream" in responses_request:
            payload["stream"] = bool(responses_request.get("stream"))
        if "tools" in responses_request:
            payload["tools"] = responses_request.get("tools")
        if "tool_choice" in responses_request:
            payload["tool_choice"] = responses_request.get("tool_choice")
        effort = self.normalize_reasoning_effort(
            responses_request.get("reasoning_effort")
            or responses_request.get("model_reasoning_effort")
            or (route.extra or {}).get("reasoning_effort")
        )
        if effort:
            payload["reasoning_effort"] = effort
        return self.sanitize_chat_payload(payload)


    def sanitize_chat_payload(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        cleaned = dict(payload)
        messages = []
        for message in list(cleaned.get("messages") or []):
            if isinstance(message, Mapping):
                # DeepSeek reasoning mode requires preserving assistant
                # reasoning_content in request history. Generic/OpenAI-compatible
                # adapters strip this provider-specific extension instead.
                messages.append(dict(message))
            else:
                messages.append(message)
        cleaned["messages"] = messages
        effort = self.normalize_reasoning_effort(cleaned.get("reasoning_effort"))
        if effort:
            cleaned["reasoning_effort"] = effort
        else:
            cleaned.pop("reasoning_effort", None)
        return cleaned


    def parse_usage(self, upstream_payload: Mapping[str, Any]) -> dict[str, int]:
        usage = upstream_payload.get("usage")
        if not isinstance(usage, Mapping):
            usage = {}

        prompt_tokens = int(usage.get("prompt_tokens") or 0)
        completion_tokens = int(usage.get("completion_tokens") or 0)
        total_tokens = int(usage.get("total_tokens") or prompt_tokens + completion_tokens)

        prompt_details = usage.get("prompt_tokens_details")
        if not isinstance(prompt_details, Mapping):
            prompt_details = {}
        completion_details = usage.get("completion_tokens_details")
        if not isinstance(completion_details, Mapping):
            completion_details = {}

        prompt_cache_hit_tokens = int(
            usage.get("prompt_cache_hit_tokens")
            if usage.get("prompt_cache_hit_tokens") is not None
            else prompt_details.get("cached_tokens")
            or usage.get("cached_tokens")
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

        return {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "cached_tokens": prompt_cache_hit_tokens,
            "prompt_cache_hit_tokens": prompt_cache_hit_tokens,
            "prompt_cache_miss_tokens": prompt_cache_miss_tokens,
            "reasoning_tokens": int(
                completion_details.get("reasoning_tokens")
                or usage.get("reasoning_tokens")
                or 0
            ),
        }

    def message_reasoning_text(self, message: Mapping[str, Any]) -> str:
        value = message.get("reasoning_content")
        return value if isinstance(value, str) else ""


    def tokenizer_resource_metadata(self) -> dict[str, Any]:
        return {
            "provider": self.provider_id,
            "tokenizer": True,
            "tokenizer_kind": self.official_tokenizer_kind,
            "legacy_tokenizer_kind": self.legacy_tokenizer_kind,
            "env_names": list(self.tokenizer_env_names),
            "managed_resource_subpath": f"{self.official_tokenizer_kind}/tokenizer.json",
            "legacy_managed_resource_subpath": f"{self.legacy_tokenizer_kind}/tokenizer.json",
            "package_resource_subpath": f"{self.official_tokenizer_kind}/tokenizer.json",
            "legacy_package_resource_subpath": f"{self.legacy_tokenizer_kind}/tokenizer.json",
            "source_archive_name": self.tokenizer_archive_name,
            "unit": "tokens",
            "precision": "local_profile_tokenizer_estimate",
            "billing_authoritative": False,
            "sync_action": "run cox tokenizer sync deepseek --json or set COX_DEEPSEEK_TOKENIZER_JSON",
        }

    def profile_tokenizer_kind_for_model(self, model: str | None, provider: str | None = None) -> str | None:
        provider_key = str(provider or self.provider_id).strip().lower()
        model_key = str(model or "").strip().lower()
        if provider_key in {self.provider_id, "deepseek-v3", "deepseek-v4"} or model_key.startswith("deepseek-"):
            return self.official_tokenizer_kind
        return None

    def tokenizer_provider_kind(self, provider: str | None = None) -> str | None:
        return self.profile_tokenizer_kind_for_model(None, provider or self.provider_id)

    def tokenizer_json_candidates(
        self,
        kind: str,
        *,
        resource_root: Path,
        package_root: Path,
        env_get: Any,
    ) -> list[tuple[Path, str]]:
        candidates: list[tuple[Path, str]] = []
        for name in self.tokenizer_env_names:
            raw = env_get(name)
            if raw:
                candidates.append((Path(raw).expanduser(), f"env.{name}"))

        candidates.append((resource_root / kind / "tokenizer.json", "managed_resource"))

        if kind == self.official_tokenizer_kind:
            candidates.append((resource_root / self.legacy_tokenizer_kind / "tokenizer.json", "legacy_managed_resource"))

        candidates.append((package_root / kind / "tokenizer.json", "package_resource"))
        if kind == self.official_tokenizer_kind:
            candidates.append((package_root / self.legacy_tokenizer_kind / "tokenizer.json", "legacy_package_resource"))

        return candidates

    def profile_tokenizer_contract(
        self,
        model: str | None,
        provider: str | None = None,
        *,
        resource_root: Path,
        package_root: Path,
        env_get: Any,
        tokenizers_error: str | None = None,
    ) -> dict[str, Any]:
        provider_value = str(provider or env_get("COX_MODEL_PROVIDER") or self.provider_id)
        kind = self.profile_tokenizer_kind_for_model(model, provider_value)
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
        for path, source_kind in self.tokenizer_json_candidates(
            kind,
            resource_root=resource_root,
            package_root=package_root,
            env_get=env_get,
        ):
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
                "action": self.tokenizer_resource_metadata()["sync_action"],
                "checked": checked,
            }

        if tokenizers_error:
            return {
                "available": False,
                "unit": "tokens",
                "model": str(model or "") or None,
                "provider": provider_value,
                "tokenizer_kind": kind,
                "source": str(selected_path),
                "source_kind": selected_source,
                "reason": "python_tokenizers_package_unavailable",
                "error": tokenizers_error,
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


    def upstream_request(self, route: ProviderRoute, responses_request: Mapping[str, Any]) -> UpstreamRequest:
        return UpstreamRequest(
            method="POST",
            path="/chat/completions",
            json=self.build_chat_payload(route, responses_request),
        )


    def official_pricing_source(self) -> dict[str, str]:
        return {
            "provider": self.provider_id,
            "source_url": self.official_pricing_url,
            "source_url_en": self.official_pricing_url_en,
            "source_kind": "official_docs_html",
            "parser": "deepseek_official_docs_html_bilingual_v3_discount_aware",
            "currency": "CNY",
            "unit": "per_million_tokens",
        }

    def discount_window_from_pricing_text(self, text: str, *, clean_pricing_html_cell: Any) -> dict[str, Any]:
        compact = clean_pricing_html_cell(text)
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

    def parse_official_pricing_html(
        self,
        text: str,
        *,
        include_metadata: bool = False,
        clean_pricing_html_cell: Any,
        parse_pricing_cell_details: Any,
    ) -> dict[str, Any]:
        compact = re.sub(r"\s+", " ", text)
        table_match = None
        for match in re.finditer(r"<table\b.*?</table>", compact, flags=re.IGNORECASE | re.DOTALL):
            table = match.group(0)
            if "deepseek-v4-flash" in table and "deepseek-v4-pro" in table:
                table_match = table
                break

        if table_match is None:
            text_rows = clean_pricing_html_cell(text)
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
                    clean_pricing_html_cell(cell)
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
        discount_window = self.discount_window_from_pricing_text(
            text,
            clean_pricing_html_cell=clean_pricing_html_cell,
        )

        for row in table_rows:
            joined = " ".join(row).upper()
            joined_raw = " ".join(row)
            if (
                "MAX OUTPUT" in joined
                or "MAXIMUM" in joined
                or "最大输出" in joined_raw
                or "输出长度" in joined_raw
            ):
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
                    details_list.append(parse_pricing_cell_details(cell))
                except ValueError:
                    continue

            if len(details_list) < 2:
                continue

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

    def refresh_pricing_from_official_docs(
        self,
        *,
        model: str | None = None,
        source_url: str | None = None,
        write_cache: bool = False,
        cache_path: str | Path | None = None,
        timeout: float = 20.0,
        default_model: str,
        fetch_text_url: Any,
        parse_official_pricing_html: Any,
        pricing_cache_path: Any,
        pricing_now_iso: Any,
        pricing_ttl_seconds: Any,
        pricing_parse_iso_timestamp: Any,
        pricing_iso_from_timestamp: Any,
        write_pricing_cache_atomic: Any,
    ) -> dict[str, Any]:
        effective_source_url = source_url or self.official_pricing_url
        fetched_at = pricing_now_iso()
        ttl_seconds = pricing_ttl_seconds()
        target_path = Path(cache_path).expanduser() if cache_path else pricing_cache_path()

        try:
            text = fetch_text_url(effective_source_url, timeout=timeout)
        except Exception as exc:
            return {
                "status": "error",
                "available": False,
                "reason": "official_pricing_fetch_failed",
                "error_type": type(exc).__name__,
                "error": str(exc)[:1000],
                "source_url": effective_source_url,
                "source_kind": "official_docs_html",
                "writes_cache": False,
                "cache_path": str(target_path),
                "old_cache_preserved": True,
            }

        try:
            prices = parse_official_pricing_html(text, include_metadata=True)
        except Exception as exc:
            return {
                "status": "error",
                "available": False,
                "reason": "official_pricing_parse_failed",
                "error_type": type(exc).__name__,
                "error": str(exc)[:1000],
                "source_url": effective_source_url,
                "source_kind": "official_docs_html",
                "writes_cache": False,
                "cache_path": str(target_path),
                "old_cache_preserved": True,
            }

        cache_written = False
        if write_cache:
            try:
                write_pricing_cache_atomic(
                    prices,
                    path=target_path,
                    source_url=effective_source_url,
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
                    "source_url": effective_source_url,
                    "source_kind": "official_docs_html",
                    "writes_cache": False,
                    "cache_path": str(target_path),
                    "old_cache_preserved": True,
                    "validated_prices": prices,
                }

        model_key = str(model or default_model)
        model_prices = prices.get(model_key)
        model_metadata = (prices.get("__model_metadata__") or {}).get(model_key, {}) if isinstance(prices.get("__model_metadata__"), dict) else {}
        expires_ts = (pricing_parse_iso_timestamp(fetched_at) or time.time()) + ttl_seconds
        all_model_keys = sorted(key for key in prices if isinstance(key, str) and not key.startswith("__"))

        return {
            "status": "ok",
            "available": True,
            "reason": None,
            "action": "validated official DeepSeek pricing HTML; add --write-cache to persist the cache" if not cache_written else "validated and persisted official DeepSeek pricing cache",
            "source_url": effective_source_url,
            "source_kind": "official_docs_html",
            "fetched_at": fetched_at,
            "updated_at": fetched_at,
            "expires_at": pricing_iso_from_timestamp(expires_ts),
            "ttl_seconds": ttl_seconds,
            "currency": "CNY",
            "unit": "per_million_tokens",
            "unit_legacy": "per_1m_tokens",
            "parser": "deepseek_official_docs_html_bilingual_v3_discount_aware",
            "pricing": {
                "available": bool(model_prices),
                "provider": self.provider_id,
                "model": model_key,
                "currency": "CNY",
                "unit": "per_million_tokens",
                "source": "official_deepseek_pricing_docs",
                "source_url": effective_source_url,
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


    def status_capabilities(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "family": self.family,
            "wire_protocol": self.wire_protocol,
            "default_base_url": self.default_base_url,
            "api_key_env_names": list(self.api_key_env_names),
            "capabilities": self.capabilities.as_dict(),
        }

    def validation_request(self) -> ValidationRequest:
        return ValidationRequest(
            method="GET",
            path="/user/balance",
            validation_method="account_balance_probe",
        )
