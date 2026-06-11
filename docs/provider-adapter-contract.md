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
