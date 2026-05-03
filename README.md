# DeepSeek Responses Proxy for Codex

This project provides a local OpenAI Responses-compatible proxy for Codex.

Codex requires `wire_api = "responses"`, while DeepSeek official API primarily exposes Chat Completions. This proxy bridges:

Codex `/v1/responses`
→ local FastAPI proxy
→ DeepSeek `/chat/completions`

## Current verified capabilities

- Text responses
- Minimal SSE streaming
- Basic Codex tool calls
- `function_call_output` continuation
- `developer` role normalization to `system`
- Skipping unsupported built-in tools such as `web_search`
- DeepSeek thinking mode disabled by default

## Run proxy

```bash
cd ~/projects/deepseek-responses-proxy
source .venv/bin/activate
export DEEPSEEK_API_KEY='your-key'

PYTHONPATH=. python -m uvicorn deepseek_responses_proxy.app:app \
  --host 127.0.0.1 \
  --port 8000
```

# Use with Codex
```bash
codex --profile deepseek
```

# Health check
```bash
./health_check.sh
```

# Known limitations
- Not a full OpenAI Responses API implementation
- No native web search
- No OpenAI-hosted built-in tools
- In-memory response state
- DeepSeek thinking mode is disabled
- Experimental compatibility layer, not a full replacement for official Codex models

## Thinking profile

The stable default profile should keep DeepSeek thinking disabled:

```bash
codex --profile deepseek
```

An experimental thinking-enabled profile can run through a separate proxy port and database:

```bash
codex --profile deepseek-thinking
```

Recommended separation:

deepseek: port 8000, thinking disabled, default daily use
deepseek-thinking: port 8001, thinking enabled, separate SQLite database, experimental use

Thinking mode uses:

```bash
DEEPSEEK_THINKING=enabled
DEEPSEEK_PROXY_DB_PATH=~/.local/state/deepseek-responses-proxy/responses-thinking.sqlite3
```

Known caution:

- Do not mix disabled-mode sessions and thinking-mode sessions.
- Do not use resume --last across different profiles.
- Prefer a fresh session when switching between deepseek and deepseek-thinking.

## Balance check

The proxy exposes DeepSeek's official balance endpoint:

```bash
curl -sS http://127.0.0.1:8000/v1/proxy/balance | python3 -m json.tool
```

This reports current DeepSeek account balance. It is not a full spending ledger. DeepSeek bills API usage by token usage and model pricing, deducting fees from the account balance.

Optional health check:

```bash
CHECK_DEEPSEEK_BALANCE=1 ./health_check.sh
```
