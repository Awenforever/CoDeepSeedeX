from __future__ import annotations

from collections.abc import Mapping
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
    api_key_env_names = ("COX_MODEL_API_KEY",)
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

    def upstream_request(self, route: ProviderRoute, responses_request: Mapping[str, Any]) -> UpstreamRequest:
        return UpstreamRequest(
            method="POST",
            path="/chat/completions",
            json=self.build_chat_payload(route, responses_request),
        )

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
