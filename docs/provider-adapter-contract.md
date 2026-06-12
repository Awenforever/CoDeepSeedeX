# Provider adapter contract

p3.0a2 introduces the first CodeXchange provider adapter contract. This patch does not move runtime routing yet; it creates the stable boundary that later patches will use to move provider-specific behavior out of `codexchange_proxy.app` and `codexchange_proxy.cli`.

## Initial adapters

- `deepseek`: OpenAI-compatible chat completions plus provider-specific reasoning, pricing, balance, and tokenizer capabilities.
- `openai_compatible`: generic OpenAI-compatible chat completions for custom endpoints and providers such as Kimi/Moonshot, Zhipu/BigModel, Z.AI, Qwen/DashScope, xAI/Grok, and OpenAI-compatible routes.

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
- CLI-specific concrete provider ids such as `qwen_singapore` and `zhipu_coding` map to the generic `openai_compatible` adapter until native adapters are added.


## p3.0a5 provider live smoke matrix

`scripts/provider-live-smoke-matrix.py` runs a reproducible provider smoke matrix without printing API keys. Providers without live keys are reported as skipped. When keys are present, the script uses adapter-backed validation metadata from CLI provider configuration and can optionally run a minimal chat completion smoke.

Provider-specific live key variables:

- `COX_LIVE_DS_KEY`
- `COX_LIVE_QWEN_API_KEY`
- `COX_LIVE_KIMI_API_KEY`
- `COX_LIVE_ZHIPU_API_KEY`
- `COX_LIVE_ZAI_API_KEY`
- `COX_LIVE_CUSTOM_API_KEY`
