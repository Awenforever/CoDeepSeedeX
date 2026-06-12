from __future__ import annotations

from .base import ProviderCapabilities, ValidationRequest
from .openai_compatible import OpenAICompatibleProviderAdapter


class QwenProviderAdapter(OpenAICompatibleProviderAdapter):
    """Qwen/DashScope regional OpenAI-compatible adapter.

    The first native Qwen adapter keeps the same OpenAI-compatible chat payload
    behavior as the generic adapter. Its purpose is to carry region-specific
    defaults and diagnostics without forcing every user into one region.
    """

    family = "qwen"
    wire_protocol = "openai_chat_completions"
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
        notes=(
            "uses OpenAI-compatible chat completions; Qwen/DashScope API keys are region-scoped",
        ),
    )

    def __init__(
        self,
        *,
        provider_id: str,
        region: str,
        region_code: str,
        endpoint_scope: str,
        default_base_url: str,
        default_model: str,
    ) -> None:
        self.provider_id = provider_id
        self.region = region
        self.region_code = region_code
        self.endpoint_scope = endpoint_scope
        self.default_base_url = default_base_url
        self.default_model = default_model

    def status_capabilities(self) -> dict[str, object]:
        status = super().status_capabilities()
        status.update(
            {
                "provider_id": self.provider_id,
                "family": self.family,
                "default_base_url": self.default_base_url,
                "default_model": self.default_model,
                "region": self.region,
                "region_code": self.region_code,
                "endpoint_scope": self.endpoint_scope,
            }
        )
        return status

    def validation_request(self) -> ValidationRequest:
        return ValidationRequest(
            method="GET",
            path="/models",
            validation_method="qwen_openai_compatible_models",
        )
