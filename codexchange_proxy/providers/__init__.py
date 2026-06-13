"""Provider adapter contracts for CodeXchange."""

from .base import (
    ProviderAdapter,
    ProviderCapabilities,
    ProviderRoute,
    UpstreamRequest,
    ValidationRequest,
)
from .deepseek import DeepSeekProviderAdapter
from .kimi import KimiProviderAdapter
from .openai_compatible import OpenAICompatibleProviderAdapter
from .qwen import QwenProviderAdapter
from .zai import ZaiProviderAdapter
from .zhipu import ZhipuProviderAdapter
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
    "KimiProviderAdapter",
    "OpenAICompatibleProviderAdapter",
    "QwenProviderAdapter",
    "ZaiProviderAdapter",
    "ZhipuProviderAdapter",
    "canonical_provider_id",
    "get_provider_adapter",
    "provider_registry_status",
    "supported_provider_ids",
]
