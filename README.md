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
