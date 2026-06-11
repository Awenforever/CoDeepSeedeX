from __future__ import annotations

from .base import ProviderAdapter
from .deepseek import DeepSeekProviderAdapter
from .openai_compatible import OpenAICompatibleProviderAdapter

_DEEPSEEK = DeepSeekProviderAdapter()
_OPENAI_COMPATIBLE = OpenAICompatibleProviderAdapter()

_ALIAS_TO_CANONICAL = {
    "deepseek": "deepseek",
    "deepseek_v4": "deepseek",
    "openai_compatible": "openai_compatible",
    "openai-compatible": "openai_compatible",
    "custom": "openai_compatible",
    "openai": "openai_compatible",
    "kimi": "openai_compatible",
    "moonshot": "openai_compatible",
    "zhipu": "openai_compatible",
    "bigmodel": "openai_compatible",
    "zai": "openai_compatible",
    "z_ai": "openai_compatible",
    "qwen": "openai_compatible",
    "dashscope": "openai_compatible",
    "xai": "openai_compatible",
    "grok": "openai_compatible",
}

_ADAPTERS: dict[str, ProviderAdapter] = {
    "deepseek": _DEEPSEEK,
    "openai_compatible": _OPENAI_COMPATIBLE,
}


def canonical_provider_id(provider: str | None) -> str:
    selected = str(provider or "deepseek").strip().lower().replace(" ", "_")
    return _ALIAS_TO_CANONICAL.get(selected.replace("-", "_"), _ALIAS_TO_CANONICAL.get(selected, selected))


def get_provider_adapter(provider: str | None) -> ProviderAdapter:
    canonical = canonical_provider_id(provider)
    try:
        return _ADAPTERS[canonical]
    except KeyError as exc:
        supported = ", ".join(supported_provider_ids())
        raise ValueError(f"unsupported_provider_adapter:{canonical}; supported={supported}") from exc


def supported_provider_ids() -> list[str]:
    return sorted(_ADAPTERS)


def provider_registry_status() -> dict[str, object]:
    return {
        "available": True,
        "default_provider": "deepseek",
        "supported_provider_ids": supported_provider_ids(),
        "aliases": dict(sorted(_ALIAS_TO_CANONICAL.items())),
        "adapters": {
            provider_id: adapter.status_capabilities()
            for provider_id, adapter in sorted(_ADAPTERS.items())
        },
    }
