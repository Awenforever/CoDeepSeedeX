from __future__ import annotations

from .base import ProviderCapabilities, ValidationRequest
from .openai_compatible import OpenAICompatibleProviderAdapter


class ZaiProviderAdapter(OpenAICompatibleProviderAdapter):
    """Z.AI OpenAI-compatible adapter.

    The first native Z.AI adapter keeps the same OpenAI-compatible chat payload
    behavior as the generic adapter. Its purpose is to carry plan-specific
    endpoint metadata and preserve the observed distinction between validation
    availability and chat quota/entitlement failures.
    """

    family = "zai"
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
            "uses OpenAI-compatible chat completions; Z.AI endpoints differ by plan",
            "HTTP 429 during chat should be treated as quota, rate-limit, or account entitlement evidence",
        ),
    )

    def __init__(
        self,
        *,
        provider_id: str,
        plan: str,
        endpoint_scope: str,
        default_base_url: str,
        default_model: str,
    ) -> None:
        self.provider_id = provider_id
        self.plan = plan
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
                "plan": self.plan,
                "endpoint_scope": self.endpoint_scope,
            }
        )
        return status

    def validation_request(self) -> ValidationRequest:
        return ValidationRequest(
            method="GET",
            path="/models",
            validation_method="zai_openai_compatible_models",
        )
