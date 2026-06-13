from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Mapping, Protocol, runtime_checkable

WireProtocol = Literal[
    "openai_responses",
    "openai_chat_completions",
    "anthropic_messages",
]

ProviderFamily = Literal[
    "deepseek",
    "kimi",
    "openai_compatible",
    "qwen",
    "zhipu",
    "zai",
    "anthropic",
    "xai",
    "custom",
]


@dataclass(frozen=True)
class ProviderCapabilities:
    """Provider-level capability metadata consumed by routing and diagnostics."""

    reasoning: bool = False
    reasoning_effort: tuple[str, ...] = ()
    reasoning_effort_max: bool = False
    response_reasoning_field: str | None = None
    streaming: bool = True
    tool_calls: bool = True
    model_catalog: bool = False
    pricing: bool = False
    account_balance: bool = False
    tokenizer: bool = False
    native_responses: bool = False
    notes: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "reasoning": self.reasoning,
            "reasoning_effort": list(self.reasoning_effort),
            "reasoning_effort_max": self.reasoning_effort_max,
            "response_reasoning_field": self.response_reasoning_field,
            "streaming": self.streaming,
            "tool_calls": self.tool_calls,
            "model_catalog": self.model_catalog,
            "pricing": self.pricing,
            "account_balance": self.account_balance,
            "tokenizer": self.tokenizer,
            "native_responses": self.native_responses,
            "notes": list(self.notes),
        }


@dataclass(frozen=True)
class ProviderRoute:
    """Runtime route information independent from a specific upstream SDK."""

    provider_id: str
    base_url: str
    model: str
    api_key_env: str = "COX_MODEL_API_KEY"
    profile: str | None = None
    extra: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class UpstreamRequest:
    """Normalized outbound request description for adapter tests and routing."""

    method: str
    path: str
    json: dict[str, Any]
    headers: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ValidationRequest:
    """Minimal provider validation probe description."""

    method: str
    path: str
    validation_method: str
    expected_status: tuple[int, ...] = (200,)


@runtime_checkable
class ProviderAdapter(Protocol):
    provider_id: str
    family: ProviderFamily
    wire_protocol: WireProtocol
    default_base_url: str
    api_key_env_names: tuple[str, ...]
    capabilities: ProviderCapabilities

    def normalize_reasoning_effort(self, value: object) -> str | None:
        ...

    def build_chat_payload(self, route: ProviderRoute, responses_request: Mapping[str, Any]) -> dict[str, Any]:
        ...

    def sanitize_chat_payload(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        ...

    def parse_usage(self, upstream_payload: Mapping[str, Any]) -> dict[str, int]:
        ...

    def status_capabilities(self) -> dict[str, Any]:
        ...

    def validation_request(self) -> ValidationRequest:
        ...
