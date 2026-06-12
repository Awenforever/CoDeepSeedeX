# Provider live smoke evidence

This document records p3.0a6 live smoke observations and the interpretation rules used before provider-specific adapter changes.

## Evidence interpretation rules

- `200` on validation and chat means the provider route is compatible with the current adapter contract.
- `401` means key, region, account permission, or endpoint/key pairing should be checked before changing adapter code.
- `429` means quota, rate-limit, or account entitlement should be checked before changing adapter code.
- `404` usually means the configured base URL already includes a path segment such as `/chat/completions`; custom OpenAI-compatible base URLs must be API roots.

## p3.0a6 / p3.0a6b observations

| Provider | Validation | Chat | Interpretation |
|---|---:|---:|---|
| deepseek | 200 | 200 | DeepSeek adapter path works. |
| zhipu | 200 | 200 | OpenAI-compatible adapter path works for BigModel. |
| qwen-beijing | 200 | 200 | OpenAI-compatible adapter path works for domestic DashScope keys. |
| custom | 200 | 200 | Custom OpenAI-compatible route works when base URL is the API root. |
| qwen-singapore | 401 | 401 | Same key that passes qwen-beijing fails Singapore endpoint; treat as region/key mismatch. |
| kimi | 401 | 401 | Treat as key/account/permission issue before adapter changes. |
| zai | 200 | 429 | Validation path works; chat needs quota/rate-limit/account entitlement recheck. |

## Custom provider base URL rule

Correct:

```text
COX_LIVE_CUSTOM_BASE_URL=https://api.llm.ustc.edu.cn/v1
COX_LIVE_CUSTOM_MODEL=deepseek-v4-flash-ascend
```

Incorrect:

```text
COX_LIVE_CUSTOM_BASE_URL=https://api.llm.ustc.edu.cn/v1/chat/completions
```

The smoke matrix appends `/models` and `/chat/completions` automatically.
