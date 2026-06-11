"""Provider adapter contracts for CodeXchange."""

from .base import (
    ProviderAdapter,
    ProviderCapabilities,
    ProviderRoute,
    UpstreamRequest,
    ValidationRequest,
)
from .deepseek import DeepSeekProviderAdapter
from .openai_compatible import OpenAICompatibleProviderAdapter
from .registry import (
    canonical_provider_id,
    get_provider_adapter,
    provider_registry_status,
    supported_provider_ids,
)

__all__ = [
    "ProviderAdapter",
    "ProviderCapabilities",
    "ProviderRoute",
    "UpstreamRequest",
    "ValidationRequest",
    "DeepSeekProviderAdapter",
    "OpenAICompatibleProviderAdapter",
    "canonical_provider_id",
    "get_provider_adapter",
    "provider_registry_status",
    "supported_provider_ids",
]
