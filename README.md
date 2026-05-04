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
* Built-in `web_search` and `image_generation` tools are mapped to proxy tools when `DEEPSEEK_PROXY_TOOL_BRIDGE=1`. The whitelisted namespace `deepseek_proxy_account` is expanded into `proxy_status`, `proxy_usage_summary`, `proxy_usage_events`, and `proxy_balance`. Unknown namespaces and unsupported tool types are still dropped with structured compatibility warnings.
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

## Pricing configuration

Local estimated cost is calculated from config/pricing.json.

```json
{
  "deepseek-v4-flash": {
    "input_cache_hit": 0.0028,
    "input_cache_miss": 0.14,
    "output": 0.28
  }
}
```

Override the path with:

```json
export DEEPSEEK_PROXY_PRICING_PATH=/path/to/pricing.json
```

Values are USD per 1M tokens. If the config is missing or invalid, the proxy falls back to the built-in default pricing table.

## Tool bridge provider and artifact status

Current versions expose tool bridge status through:

```bash
curl --noproxy '*' -sS http://127.0.0.1:8000/v1/proxy/status | python3 -m json.tool
curl --noproxy '*' -sS http://127.0.0.1:8000/v1/proxy/tool-bridge/status | python3 -m json.tool
```

The status payload reports whether the tool bridge is enabled, web search provider, image provider, image model, image size, image download mode, output directory, and image artifact retention limit. It reports only boolean key presence such as `api_key_configured`, never raw API keys.

Supported bridge mappings:

* `{"type":"web_search"}` maps to `proxy_web_search`.
* `{"type":"image_generation"}` maps to `proxy_image_generate`.
* `{"type":"namespace","namespace":"deepseek_proxy_account"}` expands to `proxy_status`, `proxy_usage_summary`, `proxy_usage_events`, and `proxy_balance`.

Unknown namespaces remain unsupported and are recorded as `unsupported_tool_namespace`.

Image artifact controls:

```bash
DEEPSEEK_PROXY_IMAGE_PROVIDER=mock|glm|zai|zhipu|zhipuai|bigmodel
DEEPSEEK_PROXY_IMAGE_MODEL=cogView-4-250304
DEEPSEEK_PROXY_IMAGE_SIZE=1024x1024
DEEPSEEK_PROXY_IMAGE_DOWNLOAD=0|1
DEEPSEEK_PROXY_IMAGE_OUTPUT_DIR=.generated/images
DEEPSEEK_PROXY_IMAGE_MAX_ARTIFACTS=100
```

When `DEEPSEEK_PROXY_IMAGE_DOWNLOAD=1`, generated image results include `file_path`, `local_path`, `file_uri`, and `downloaded`. The proxy prunes only known proxy-generated image filenames, such as `mock_*.png`, `glm_*.png`, and `zai_*.png`, leaving unrelated user files in the output directory untouched.

## Codex custom tool and MCP compatibility

Codex may send `apply_patch` as a Responses `custom` tool. By default, the proxy keeps this tool ignored and records it as `ignored_custom_tool`. To experimentally forward it to DeepSeek as a function tool, enable:

    DEEPSEEK_PROXY_FORWARD_CUSTOM_APPLY_PATCH=1

When enabled, the proxy maps `custom apply_patch` to a function tool named `apply_patch` with the Codex-required `input` argument. The exposed description instructs the model to use Codex apply_patch format with `*** Begin Patch`, `*** Update File: relative/path`, and `*** End Patch`.

MCP namespaces are not executed by the proxy. They are compressed into audit warnings such as `ignored_mcp_namespace` so debug files remain small. Experiments showed that flattening MCP tools into function names such as `cheap_router_status` or `mcp__cheap_llm__cheap_router_status` results in Codex returning `unsupported call`. Therefore MCP tool execution remains disabled unless a future Codex-native MCP call protocol or explicit proxy-side MCP executor is implemented.
