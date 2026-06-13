from __future__ import annotations

from .base import ProviderCapabilities, ValidationRequest
from .openai_compatible import OpenAICompatibleProviderAdapter


class KimiProviderAdapter(OpenAICompatibleProviderAdapter):
    """Kimi / Moonshot OpenAI-compatible adapter.

    The first native Kimi adapter keeps the same OpenAI-compatible chat payload
    behavior as the generic adapter. It carries provider-specific metadata so
    validation, status, installer, and smoke evidence no longer classify Kimi
    as an undifferentiated OpenAI-compatible route.
    """

    provider_id = "kimi"
    family = "kimi"
    default_base_url = "https://api.moonshot.ai/v1"
    default_model = "kimi-latest"
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
            "uses OpenAI-compatible chat completions; Kimi/Moonshot endpoint is provider-specific",
            "HTTP 401 during live smoke should be treated as key, account, or permission evidence before adapter changes",
        ),
    )

    def status_capabilities(self) -> dict[str, object]:
        status = super().status_capabilities()
        status.update(
            {
                "provider_id": self.provider_id,
                "family": self.family,
                "default_base_url": self.default_base_url,
                "default_model": self.default_model,
                "endpoint_scope": "Moonshot OpenAI-compatible API",
            }
        )
        return status

    def validation_request(self) -> ValidationRequest:
        return ValidationRequest(
            method="GET",
            path="/models",
            validation_method="kimi_openai_compatible_models",
        )
