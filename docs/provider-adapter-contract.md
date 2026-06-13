# Provider adapter contract

p3.0a2 introduces the first CodeXchange provider adapter contract. This patch does not move runtime routing yet; it creates the stable boundary that later patches will use to move provider-specific behavior out of `codexchange_proxy.app` and `codexchange_proxy.cli`.

## Initial adapters

- `deepseek`: OpenAI-compatible chat completions plus provider-specific reasoning, pricing, balance, and tokenizer capabilities.
- `openai_compatible`: generic OpenAI-compatible chat completions for custom endpoints and providers such as Kimi/Moonshot, xAI/Grok, and OpenAI-compatible routes.

## Boundary

Generic runtime code should depend on `ProviderAdapter` methods instead of hard-coding provider rules:

- `build_chat_payload`
- `sanitize_chat_payload`
- `parse_usage`
- `normalize_reasoning_effort`
- `status_capabilities`
- `validation_request`

## Follow-up extraction order

1. Move reasoning-effort normalization and request sanitization behind the adapter.
2. Move usage parsing and response reasoning extraction behind the adapter.
3. Move pricing, balance, and tokenizer resource handling into provider-specific modules.
4. Add native Anthropic Messages adapter after the OpenAI-compatible path is stable.


## p3.0a3 runtime wiring

The first runtime wiring patch keeps legacy function names for compatibility but routes the following decisions through provider adapters:

- DeepSeek reasoning-effort normalization.
- DeepSeek usage parsing.
- DeepSeek reasoning text extraction.
- Chat payload sanitization before the existing capability-profile filter.
- DeepSeek adapter preserves assistant `reasoning_content` in request history; generic OpenAI-compatible adapters strip it.

Pricing, balance, and tokenizer handling remain in their existing modules until later provider-specific extraction patches.


## p3.0a4 CLI validation wiring

CLI model-provider configuration now exposes adapter-backed validation metadata:

- `validation_method`
- `validation_path`
- `validation_http_method`
- `validation_expected_status`
- `adapter_provider_id`
- `adapter_family`
- `wire_protocol`
- `adapter_capabilities`

DeepSeek keeps the account-balance validation probe. Generic OpenAI-compatible providers use the `/models` validation probe exposed by `OpenAICompatibleProviderAdapter`.
- CLI-specific concrete provider ids map according to available native adapters: Qwen region ids `qwen_beijing`, `qwen_singapore`, and `qwen_us` use native `qwen` adapters, while Kimi/Moonshot, custom, and other OpenAI-compatible routes still use the generic `openai_compatible` adapter until native adapters are added.


## p3.0a5 provider live smoke matrix

`scripts/provider-live-smoke-matrix.py` runs a reproducible provider smoke matrix without printing API keys. Providers without live keys are reported as skipped. When keys are present, the script uses adapter-backed validation metadata from CLI provider configuration and can optionally run a minimal chat completion smoke.

Provider-specific live key variables:

- `COX_LIVE_DS_KEY`
- `COX_LIVE_QWEN_API_KEY`
- `COX_LIVE_KIMI_API_KEY`
- `COX_LIVE_ZHIPU_API_KEY`
- `COX_LIVE_ZAI_API_KEY`
- `COX_LIVE_CUSTOM_API_KEY`

### Evidence-mode live smoke

Use `--allow-provider-failures` during evidence collection when failed provider responses are expected and should be captured as data rather than treated as command failure. Keep the default non-zero exit behavior for CI or release checks.


## Qwen native adapter skeleton

Concrete Qwen/DashScope model API regions use native adapter ids:

- `qwen_beijing`
- `qwen_singapore`
- `qwen_us`

These adapters intentionally keep OpenAI-compatible Chat Completions payload behavior while carrying region-specific defaults, validation metadata, and diagnostics. The ambiguous compatibility aliases `qwen` and `dashscope` remain non-region-specific compatibility aliases that resolve through the generic `openai_compatible` adapter path with a selection warning; user-facing configuration should prefer explicit region provider ids.


## Provider adapter status matrix

Model API configuration status exposes stable adapter metadata for diagnostics:

- `adapter_status`: the currently configured model provider adapter row.
- `adapter_provider_id`: the currently configured provider adapter id.
- `adapter_family`: the currently configured provider adapter family.
- `adapter_kind`: `native` or `generic` for the currently configured model provider.
- `adapter_matrix`: one row per supported public model provider.
- `adapter_matrix_summary`: total/native/generic provider counts and provider lists.
- `adapter_matrix_compact`: compact rows with provider, adapter kind, adapter family, and adapter id.
- `adapter_matrix_display`: preformatted rows for quick CLI inspection.

The current adapter matrix after the Qwen, Zhipu, and Z.AI native adapter skeletons is:

| Provider | Adapter kind | Adapter family |
|---|---:|---|
| `deepseek` | native | `deepseek` |
| `qwen-beijing` | native | `qwen` |
| `qwen-singapore` | native | `qwen` |
| `qwen-us` | native | `qwen` |
| `kimi` | generic | `openai_compatible` |
| `zhipu` | native | `zhipu` |
| `zhipu-coding` | native | `zhipu` |
| `zai` | native | `zai` |
| `zai-coding` | native | `zai` |
| `custom` | generic | `openai_compatible` |


## Zhipu native adapters

The Zhipu native adapter skeletons keep OpenAI-compatible Chat Completions payload behavior while carrying plan-specific endpoint metadata:

- `zhipu`: domestic general Token API, `https://open.bigmodel.cn/api/paas/v4`, default model `glm-5.1`.
- `zhipu_coding`: domestic Coding Plan API, `https://open.bigmodel.cn/api/coding/paas/v4`, default model `glm-5.1`.

Validation remains `GET /models` with `zhipu_openai_compatible_models`.


## Z.AI native adapters

The Z.AI native adapter skeletons keep OpenAI-compatible Chat Completions payload behavior while carrying plan-specific endpoint metadata:

- `zai`: international general Token API, `https://api.z.ai/api/paas/v4`, default model `glm-5.1`.
- `zai_coding`: international Coding Plan API, `https://api.z.ai/api/coding/paas/v4`, default model `glm-4.7`.

Validation remains `GET /models` with `zai_openai_compatible_models`. Historical live evidence showed `/models` validation working while chat returned HTTP 429; treat 429 as quota, rate-limit, or account-entitlement evidence rather than endpoint-shape evidence.
