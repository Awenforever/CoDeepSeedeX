from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .base import ProviderCapabilities, ProviderRoute, UpstreamRequest, ValidationRequest


class OpenAICompatibleProviderAdapter:
    """Generic OpenAI-compatible chat completions adapter."""

    provider_id = "openai_compatible"
    family = "openai_compatible"
    wire_protocol = "openai_chat_completions"
    default_base_url = ""
    api_key_env_names = ("COX_MODEL_API_KEY",)
    capabilities = ProviderCapabilities(
        reasoning=False,
        reasoning_effort=(),
        reasoning_effort_max=False,
        response_reasoning_field=None,
        streaming=True,
        tool_calls=True,
        model_catalog=True,
        pricing=False,
        account_balance=False,
        tokenizer=False,
        native_responses=False,
        notes=("reasoning extensions require explicit provider capability metadata",),
    )

    def normalize_reasoning_effort(self, value: object) -> str | None:
        return None

    def build_chat_payload(self, route: ProviderRoute, responses_request: Mapping[str, Any]) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": route.model,
            "messages": list(responses_request.get("messages") or []),
        }
        for key in ("stream", "tools", "tool_choice", "temperature", "top_p", "max_tokens"):
            if key in responses_request:
                payload[key] = responses_request.get(key)
        return self.sanitize_chat_payload(payload)

    def sanitize_chat_payload(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        cleaned = dict(payload)
        cleaned.pop("reasoning_effort", None)
        cleaned.pop("model_reasoning_effort", None)
        messages = []
        for message in list(cleaned.get("messages") or []):
            if isinstance(message, Mapping):
                item = dict(message)
                item.pop("reasoning_content", None)
                messages.append(item)
            else:
                messages.append(message)
        cleaned["messages"] = messages
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

        cached_tokens = int(prompt_details.get("cached_tokens") or usage.get("cached_tokens") or 0)
        if cached_tokens < 0:
            cached_tokens = 0
        if cached_tokens > prompt_tokens:
            cached_tokens = prompt_tokens

        return {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "cached_tokens": cached_tokens,
            "prompt_cache_hit_tokens": cached_tokens,
            "prompt_cache_miss_tokens": max(0, prompt_tokens - cached_tokens),
            "reasoning_tokens": int(completion_details.get("reasoning_tokens") or usage.get("reasoning_tokens") or 0),
        }

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
            path="/models",
            validation_method="openai_compatible_models",
        )
