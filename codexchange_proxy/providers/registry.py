from __future__ import annotations

from .base import ProviderAdapter
from .deepseek import DeepSeekProviderAdapter
from .openai_compatible import OpenAICompatibleProviderAdapter
from .qwen import QwenProviderAdapter
from .zai import ZaiProviderAdapter
from .zhipu import ZhipuProviderAdapter

_DEEPSEEK = DeepSeekProviderAdapter()
_OPENAI_COMPATIBLE = OpenAICompatibleProviderAdapter()
_QWEN_BEIJING = QwenProviderAdapter(
    provider_id="qwen_beijing",
    region="Beijing",
    region_code="cn-beijing",
    endpoint_scope="domestic DashScope",
    default_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    default_model="qwen-plus",
)
_QWEN_SINGAPORE = QwenProviderAdapter(
    provider_id="qwen_singapore",
    region="Singapore",
    region_code="ap-southeast-1",
    endpoint_scope="international DashScope",
    default_base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
    default_model="qwen-plus",
)
_QWEN_US = QwenProviderAdapter(
    provider_id="qwen_us",
    region="US Virginia",
    region_code="us-east-1",
    endpoint_scope="US DashScope",
    default_base_url="https://dashscope-us.aliyuncs.com/compatible-mode/v1",
    default_model="qwen-plus-us",
)
_ZHIPU_GENERAL = ZhipuProviderAdapter(
    provider_id="zhipu",
    plan="domestic general",
    endpoint_scope="BigModel Token API",
    default_base_url="https://open.bigmodel.cn/api/paas/v4",
    default_model="glm-5.1",
)
_ZHIPU_CODING = ZhipuProviderAdapter(
    provider_id="zhipu_coding",
    plan="domestic Coding Plan",
    endpoint_scope="BigModel Coding Plan",
    default_base_url="https://open.bigmodel.cn/api/coding/paas/v4",
    default_model="glm-5.1",
)
_ZAI_GENERAL = ZaiProviderAdapter(
    provider_id="zai",
    plan="international general",
    endpoint_scope="Z.AI Token API",
    default_base_url="https://api.z.ai/api/paas/v4",
    default_model="glm-5.1",
)
_ZAI_CODING = ZaiProviderAdapter(
    provider_id="zai_coding",
    plan="international Coding Plan",
    endpoint_scope="Z.AI Coding Plan",
    default_base_url="https://api.z.ai/api/coding/paas/v4",
    default_model="glm-4.7",
)

_ALIAS_TO_CANONICAL = {
    "deepseek": "deepseek",
    "deepseek_v4": "deepseek",
    "openai_compatible": "openai_compatible",
    "openai-compatible": "openai_compatible",
    "custom": "openai_compatible",
    "openai": "openai_compatible",
    "kimi": "openai_compatible",
    "moonshot": "openai_compatible",
    "zhipu": "zhipu",
    "zhipuai": "zhipu",
    "bigmodel": "zhipu",
    "zhipu_domestic": "zhipu",
    "bigmodel_domestic": "zhipu",
    "zhipu_coding": "zhipu_coding",
    "zhipu-coding": "zhipu_coding",
    "bigmodel_coding": "zhipu_coding",
    "bigmodel-coding": "zhipu_coding",
    "zai": "zai",
    "z_ai": "zai",
    "z.ai": "zai",
    "glm": "zai",
    "zai_general": "zai",
    "zai_coding": "zai_coding",
    "zai-coding": "zai_coding",
    "z.ai_coding": "zai_coding",
    "z.ai-coding": "zai_coding",
    "glm_coding": "zai_coding",
    "qwen": "openai_compatible",
    "dashscope": "openai_compatible",
    "qwen_beijing": "qwen_beijing",
    "qwen-beijing": "qwen_beijing",
    "dashscope_beijing": "qwen_beijing",
    "dashscope-beijing": "qwen_beijing",
    "qwen_singapore": "qwen_singapore",
    "qwen-singapore": "qwen_singapore",
    "qwen_intl": "qwen_singapore",
    "qwen-intl": "qwen_singapore",
    "dashscope_singapore": "qwen_singapore",
    "dashscope-singapore": "qwen_singapore",
    "qwen_us": "qwen_us",
    "qwen-us": "qwen_us",
    "qwen_us_virginia": "qwen_us",
    "qwen-us-virginia": "qwen_us",
    "dashscope_us": "qwen_us",
    "dashscope-us": "qwen_us",
    "xai": "openai_compatible",
    "grok": "openai_compatible",
}

_ADAPTERS: dict[str, ProviderAdapter] = {
    "deepseek": _DEEPSEEK,
    "openai_compatible": _OPENAI_COMPATIBLE,
    "qwen_beijing": _QWEN_BEIJING,
    "qwen_singapore": _QWEN_SINGAPORE,
    "qwen_us": _QWEN_US,
    "zhipu": _ZHIPU_GENERAL,
    "zhipu_coding": _ZHIPU_CODING,
    "zai": _ZAI_GENERAL,
    "zai_coding": _ZAI_CODING,
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
