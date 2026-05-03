# DeepSeek Responses Proxy for Codex

A local FastAPI proxy that lets the current OpenAI Codex CLI use DeepSeek official Chat Completions models through Codex's required `wire_api = "responses"` interface.

Codex now expects a Responses-compatible provider. DeepSeek official API primarily exposes Chat Completions. This project bridges that protocol gap:

```text
Codex CLI
→ local /v1/responses proxy
→ DeepSeek /chat/completions
→ proxy maps DeepSeek output back to OpenAI Responses format
→ Codex CLI
```

## Current baseline

Current feature baseline:

```text
v0.9-usage-cost-ledger
```

Recommended next development line:

```text
v1.0-docs-ops-hardening
```

## Profiles

### Stable profile

```bash
codex --profile deepseek
```

Use this for daily low-cost Codex work.

Default local proxy:

```text
http://127.0.0.1:8000
```

Default SQLite state:

```text
~/.local/state/deepseek-responses-proxy/responses.sqlite3
```

Thinking mode:

```text
disabled
```

### Thinking profile

```bash
codex --profile deepseek-thinking
```

Use this for more complex reasoning tasks where DeepSeek thinking mode is useful.

Default local proxy:

```text
http://127.0.0.1:8001
```

Default SQLite state:

```text
~/.local/state/deepseek-responses-proxy/responses-thinking.sqlite3
```

Thinking mode:

```text
enabled
```

Important limitation: thinking history repair can add missing empty `reasoning_content` fields for compatibility, but it cannot recover true reasoning content that was never generated.

## Runtime commands

Stable proxy:

```bash
dsproxy-start
dsproxy-stop
dsproxy-status
dsproxy-log
```

Thinking proxy:

```bash
dsproxy-start-thinking
dsproxy-stop-thinking
dsproxy-status-thinking
dsproxy-log-thinking
```

Manual stable startup:

```bash
cd ~/projects/deepseek-responses-proxy
source .venv/bin/activate
export DEEPSEEK_API_KEY='your-key'

PYTHONPATH=. python -m uvicorn deepseek_responses_proxy.app:app \
  --host 127.0.0.1 \
  --port 8000
```

Manual thinking startup:

```bash
cd ~/projects/deepseek-responses-proxy
source .venv/bin/activate
export DEEPSEEK_API_KEY='your-key'
export DEEPSEEK_THINKING=enabled
export DEEPSEEK_PROXY_DB_PATH="$HOME/.local/state/deepseek-responses-proxy/responses-thinking.sqlite3"

PYTHONPATH=. python -m uvicorn deepseek_responses_proxy.app:app \
  --host 127.0.0.1 \
  --port 8001
```

## API endpoints

Responses-compatible subset:

```text
POST /v1/responses
GET /v1/responses/{response_id}
GET /v1/models
```

Proxy utility endpoints:

```text
GET /healthz
GET /v1/proxy/status
GET /v1/proxy/balance
GET /v1/proxy/usage
GET /v1/proxy/usage/summary
```

Common checks:

```bash
curl -sS http://127.0.0.1:8000/healthz | python3 -m json.tool
curl -sS http://127.0.0.1:8000/v1/proxy/status | python3 -m json.tool
curl -sS http://127.0.0.1:8000/v1/proxy/balance | python3 -m json.tool
curl -sS http://127.0.0.1:8000/v1/proxy/usage/summary | python3 -m json.tool
curl -sS "http://127.0.0.1:8000/v1/proxy/usage?limit=20" | python3 -m json.tool
```

Use port `8001` for thinking mode.

## Implemented capabilities

* Text responses
* Minimal SSE streaming
* Codex function calls
* `function_call_output` continuation
* `previous_response_id` continuation
* SQLite response state
* Response retrieval by ID
* DeepSeek upstream error normalization
* `developer` role normalization to `system`
* Unsupported built-in tool filtering
* Thinking mode switch
* Thinking-mode legacy history repair
* Runtime status endpoint
* DeepSeek official balance query endpoint
* Local token usage and estimated cost ledger

## Usage and estimated cost ledger

The proxy records usage fields returned by DeepSeek and estimates local cost.

```bash
curl -sS http://127.0.0.1:8000/v1/proxy/usage/summary | python3 -m json.tool
curl -sS "http://127.0.0.1:8000/v1/proxy/usage?limit=20" | python3 -m json.tool
```

Recorded fields include:

* `created_at`
* `response_id`
* `previous_response_id`
* `model`
* `thinking_enabled`
* `prompt_tokens`
* `completion_tokens`
* `total_tokens`
* `cached_tokens`
* `reasoning_tokens`
* `estimated_cost_usd`

The current estimate uses a local pricing table for `deepseek-v4-flash`. Check DeepSeek official pricing regularly because local estimates can diverge from final billing.

## Health check

```bash
cd ~/projects/deepseek-responses-proxy
./health_check.sh
```

Optional official DeepSeek balance check:

```bash
CHECK_DEEPSEEK_BALANCE=1 ./health_check.sh
```

## Regression after changes

```bash
cd ~/projects/deepseek-responses-proxy
source .venv/bin/activate

TMPDIR=~/projects/deepseek-responses-proxy/.tmp \
PYTHONPATH=. \
python -m pytest -q -s

./health_check.sh
```

Then run real Codex regression from a temporary directory:

```bash
cd /tmp
mkdir -p codex-regression-test
cd codex-regression-test
codex --profile deepseek
```

Use these prompts:

```text
Reply exactly: ok
Run `pwd` and tell me the working directory.
Create a file named test.txt containing exactly "ok", read it back, then delete it.
```

For thinking mode:

```bash
cd /tmp
mkdir -p codex-thinking-regression-test
cd codex-thinking-regression-test
codex --profile deepseek-thinking
```

Use the same prompts.

## Known limitations

* This is not a complete OpenAI Responses API implementation.
* OpenAI-hosted built-in tools are not supported.
* Unsupported tool types such as `web_search`, `image_generation`, and `namespace` are ignored.
* DeepSeek thinking mode is useful but not a full replacement for official Codex models.
* Model metadata warnings from Codex may be harmless but should be watched.
* High-risk production refactors should still receive independent review from an official Codex model or GPT-5.5 WebChat.

## Project hygiene

Do not commit runtime files, logs, databases, backups, virtual environments, or debug payloads.

Before every development stage:

```bash
git status --short
```

After every code change:

```bash
python -m pytest -q -s
./health_check.sh
```

Before every release tag, also run real Codex regression.

See also:

```text
OPERATIONS.md
REGRESSION.md
TROUBLESHOOTING.md
```
