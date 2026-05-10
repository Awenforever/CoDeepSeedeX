# Operations Guide

This document describes daily operation for `deepseek-responses-proxy`.

## Project path

```bash
cd ~/projects/deepseek-responses-proxy
```

## Stable profile

Start:

```bash
dsproxy-start
```

Stop:

```bash
dsproxy-stop
```

Status:

```bash
dsproxy-status
```

Logs:

```bash
dsproxy-log
```

Use with Codex:

```bash
codex --profile deepseek
```

Default port:

```text
8000
```

Default SQLite database:

```text
~/.local/state/deepseek-responses-proxy/responses.sqlite3
```

## Thinking profile

Start:

```bash
dsproxy-start-thinking
```

Stop:

```bash
dsproxy-stop-thinking
```

Status:

```bash
dsproxy-status-thinking
```

Logs:

```bash
dsproxy-log-thinking
```

Use with Codex:

```bash
codex --profile deepseek-thinking
```

Default port:

```text
8001
```

Default SQLite database:

```text
~/.local/state/deepseek-responses-proxy/responses-thinking.sqlite3
```

## Status checks

Stable:

```bash
curl -sS http://127.0.0.1:8000/healthz | python3 -m json.tool
curl -sS http://127.0.0.1:8000/v1/proxy/status | python3 -m json.tool
```

Thinking:

```bash
curl -sS http://127.0.0.1:8001/healthz | python3 -m json.tool
curl -sS http://127.0.0.1:8001/v1/proxy/status | python3 -m json.tool
```

## Balance and usage

Official DeepSeek balance through stable proxy:

```bash
curl -sS http://127.0.0.1:8000/v1/proxy/balance | python3 -m json.tool
```

Stable usage summary:

```bash
curl -sS http://127.0.0.1:8000/v1/proxy/usage/summary | python3 -m json.tool
```

Recent stable usage events:

```bash
curl -sS "http://127.0.0.1:8000/v1/proxy/usage?limit=20" | python3 -m json.tool
```

Thinking usage summary:

```bash
curl -sS http://127.0.0.1:8001/v1/proxy/usage/summary | python3 -m json.tool
```

Recent thinking usage events:

```bash
curl -sS "http://127.0.0.1:8001/v1/proxy/usage?limit=20" | python3 -m json.tool
```

## Debug trace

Debug trace mode records a structured JSONL activity timeline for each Responses request. It is intended for diagnosing context trimming, Codex-like persistent compaction, tool bridge rounds, upstream calls, and final response-envelope construction.

Enable it only when diagnosing a local proxy session:

```bash
DEEPSEEK_PROXY_DEBUG_TRACE=1 dsproxy-start
DEEPSEEK_PROXY_DEBUG_TRACE=1 dsproxy-start-thinking
```

Useful optional settings:

```bash
DEEPSEEK_PROXY_DEBUG_DIR=.debug/traces
DEEPSEEK_PROXY_DEBUG_CONTENT=none      # metadata only
DEEPSEEK_PROXY_DEBUG_CONTENT=preview   # default, redacted previews
DEEPSEEK_PROXY_DEBUG_CONTENT=full      # high risk, local temporary use only
DEEPSEEK_PROXY_DEBUG_PREVIEW_CHARS=1200
DEEPSEEK_PROXY_DEBUG_MAX_EVENT_CHARS=8000
```

Inspect the trace state through HTTP:

```bash
curl -sS http://127.0.0.1:8000/v1/proxy/debug/status | python3 -m json.tool
curl -sS http://127.0.0.1:8000/v1/proxy/debug/latest | python3 -m json.tool
curl -sS 'http://127.0.0.1:8001/v1/proxy/debug/latest?limit=50' | python3 -m json.tool
```

Inspect through the CLI:

```bash
dsproxy debug status
dsproxy debug latest
dsproxy debug budget
dsproxy debug status --thinking
dsproxy debug latest --thinking --limit 50
dsproxy debug budget --thinking --limit 100
```

Trace files are written under the configured debug trace directory, by default:

```text
.debug/traces/trace-<response_id>.jsonl
.debug/traces/latest.json
```

Important safety notes:

* Default content mode is `preview`, which redacts secret-like keys and summarizes large fields.
* Use `DEEPSEEK_PROXY_DEBUG_CONTENT=none` for safest metadata-only diagnostics.
* Avoid `DEEPSEEK_PROXY_DEBUG_CONTENT=full` unless running locally for a short, controlled diagnostic session.
* Debug traces should not be committed.


Real flattened-tool transcript payload compaction is disabled by default. Set `DEEPSEEK_PROXY_FLATTENED_TOOL_PAYLOAD_COMPACTION_MODE=enabled` to compact old `flattened_tool_transcript` messages only in the upstream payload copy. The `flattened_tool_transcript_payload_compaction_applied` trace event records whether it changed the payload. SQLite response history remains unchanged. The `flattened_tool_transcript_compaction_dry_run` trace event estimates how many characters could be removed by summarizing old flattened tool transcripts. It is dry-run only and does not alter payloads or persisted SQLite response history. The `history_growth_breakdown` trace event audits accumulated chat history by role and by history category, including flattened tool transcripts, assistant tool-call messages, tool protocol messages, plain user messages, and plain assistant messages. It is audit-only and does not alter payloads or persisted SQLite response history. Real tool-output trimming is disabled by default. Set `DEEPSEEK_PROXY_TOOL_OUTPUT_TRIM_MODE=enabled` to rewrite oversized `function_call_output.output` fields before they are converted into chat messages. The `tool_output_trim_applied` trace event records whether trimming actually changed the request and how many characters were removed. Tool output budget diagnostics are included in `dsproxy debug budget`. The category policy dry-run report `policy_dry_run` classifies tool outputs into `shell_command`, `interactive_shell`, `search`, `file_read`, `user_interaction`, `image_payload`, or `unknown`. Image viewing tools such as `view_image` are classified as `image_payload` so large encoded or textual image payloads can be capped separately. Unknown tools still use a conservative fallback policy, so the feature can run on other users' machines without depending on a fixed local tool list. The dry-run trimming report estimates how many characters would be removed if tool output trimming were enabled, but it does not alter upstream payloads. Relevant knobs: `DEEPSEEK_PROXY_TOOL_OUTPUT_TRIM_MODE=off|dry_run|enabled`, `DEEPSEEK_PROXY_TOOL_OUTPUT_MAX_ITEM_CHARS`, `DEEPSEEK_PROXY_TOOL_OUTPUT_MAX_TOTAL_CHARS`, `DEEPSEEK_PROXY_TOOL_OUTPUT_KEEP_HEAD_CHARS`, `DEEPSEEK_PROXY_TOOL_OUTPUT_KEEP_TAIL_CHARS`, and image-specific overrides such as `DEEPSEEK_PROXY_TOOL_OUTPUT_IMAGE_PAYLOAD_MAX_ITEM_CHARS`. They identify how much of the Responses input is made of `function_call` and `function_call_output` items, and list the largest tool outputs by `call_id`, tool name and character size. This mode is audit-only and does not truncate tool outputs by default.

Context budget diagnostics are available after a traced request:

```bash
dsproxy debug budget --thinking --limit 100
```

The budget view extracts the latest `context_budget_breakdown` event and the primary upstream usage from the latest trace. Use it to see whether context growth is dominated by tools, conversation history, compaction summaries, or current input.

Events currently include, when applicable:

* `request_received`
* `history_loaded`
* `compaction_finished`
* `context_budget_breakdown`
* `tool_output_budget_breakdown`
* `messages_prepared_for_deepseek`
* `context_trimming_finished`
* `upstream_call_started`
* `upstream_call_finished`
* `upstream_call_failed`
* `response_envelope_built`


## Health check

Default stable proxy check:

```bash
./health_check.sh
```

Check another port:

```bash
BASE_URL=http://127.0.0.1:8001/v1 ./health_check.sh
```

Include official balance check:

```bash
CHECK_DEEPSEEK_BALANCE=1 ./health_check.sh
```

## Safe resume practice

Stable:

```bash
codex --profile deepseek resume --last
```

Thinking:

```bash
codex --profile deepseek-thinking resume --last
```

Safer when crossing profiles:

```bash
codex --profile deepseek resume <session_id>
codex --profile deepseek-thinking resume <session_id>
```

Avoid relying on `--last` when both profiles have recent sessions in the same directory.

## Development rule

Before editing:

```bash
git status --short
```

Expected output should be empty.

After editing:

```bash
git diff --check
TMPDIR=~/projects/deepseek-responses-proxy/.tmp PYTHONPATH=. python -m pytest -q -s
./health_check.sh
```

For endpoint or protocol changes, also run real Codex regression described in `REGRESSION.md`.

## Release rule

A release tag should only be created after:

1. Working tree is clean before development.
2. Intended changes are reviewed with `git diff`.
3. `git diff --check` passes.
4. Unit tests pass.
5. `health_check.sh` passes.
6. Real Codex regression passes.
7. Commit message clearly describes the change.
8. Tag name matches the version chain.

## Pricing configuration

The proxy estimates local usage cost from a pricing table.

Default file:

```bash
config/pricing.json
```

Override with:

```bash
export DEEPSEEK_PROXY_PRICING_PATH=/path/to/pricing.json
```

Expected format:

```json
{
  "deepseek-v4-flash": {
    "input_cache_hit": 0.0028,
    "input_cache_miss": 0.14,
    "output": 0.28
  }
}
```

Values are USD per 1M tokens. If the file is missing or invalid, the proxy falls back to the built-in default table.

## Runtime scripts and Codex wrapper

Runtime script templates are tracked under `scripts/`.

Install or refresh local scripts:

```bash
cd ~/projects/deepseek-responses-proxy
scripts/install-runtime-scripts.sh
```

Installed commands:

```text
dsproxy-start
dsproxy-start-thinking
dsproxy-stop
dsproxy-stop-thinking
dsproxy-status
dsproxy-status-thinking
```

The scripts always bypass system HTTP proxies for localhost checks by using:

```bash
curl --noproxy '*'
```

They also export:

```bash
NO_PROXY=127.0.0.1,localhost,...
no_proxy=127.0.0.1,localhost,...
```

This is required because system proxy variables can otherwise redirect localhost health checks and produce false 502 Bad Gateway errors.

For Codex auto-start, copy the function from:

```bash
scripts/codex-wrapper.bash
```

into ~/.bashrc.

Expected behavior:

```text
codex --profile deepseek
  starts stable proxy on port 8000

codex --profile deepseek-thinking
  starts stable proxy on port 8000
  starts thinking proxy on port 8001
```

The thinking wrapper starts both proxies because the DeepSeek account/usage skill queries both profiles by default.

For thinking mode, `dsproxy-start-thinking` sets:

```bash
DEEPSEEK_THINKING=enabled
DEEPSEEK_REASONING_EFFORT=high
```

Override reasoning effort with:

```bash
DEEPSEEK_REASONING_EFFORT=high dsproxy-start-thinking
```

## Model and reasoning-effort switching

Use `dsproxy-config` to switch the runtime model and DeepSeek reasoning effort.

Examples:

```bash
dsproxy-config show
dsproxy-config set-model deepseek-v4-pro
dsproxy-config set-model deepseek-v4-flash
dsproxy-config set-effort max
dsproxy-config set-effort high
dsproxy-config set model deepseek-v4-pro effort high
```

`dsproxy-config` updates:

```text
~/.config/deepseek-responses-proxy/env
~/.codex/config.toml
```

Model behavior:

```text
DEEPSEEK_PROXY_MODEL=deepseek-v4-pro
```

overrides the incoming Codex model field before forwarding to DeepSeek.

Reasoning effort behavior:

```text
DEEPSEEK_REASONING_EFFORT=high
```

makes the thinking proxy send:

```json
{
  "thinking": {"type": "enabled"},
  "reasoning_effort": "max"
}
```

Use `max` for the strongest DeepSeek reasoning mode and `high` for the lower thinking effort.

### Applying model and effort changes immediately

Configuration-changing `dsproxy-config` commands automatically restart the thinking proxy.

This command:

```bash
dsproxy-config set model deepseek-v4-pro effort max
```

is equivalent to:

```bash
dsproxy-config set model deepseek-v4-pro effort max
dsproxy-stop-thinking
dsproxy-start-thinking
```

Use this only when you want the new model or reasoning effort to affect the currently running thinking proxy.

To update config files without restarting the thinking proxy:

```bash
DEEPSEEK_PROXY_CONFIG_RESTART_THINKING=0 dsproxy-config set model deepseek-v4-pro effort max
```

## Experimental model catalog

An experimental Codex model catalog is available at:

```text
experiments/model-catalog/deepseek-proxy-models.json
```

Use it for one Codex session without writing it into the permanent Codex config:

```bash
codex --profile deepseek-thinking \
  -c model_catalog_json='"/home/kelvin/projects/deepseek-responses-proxy/experiments/model-catalog/deepseek-proxy-models.json"'
```

Expected behavior:

```text
/model shows DeepSeek V4 Pro and DeepSeek V4 Flash
/status can show deepseek-v4-pro or deepseek-v4-flash with reasoning high/xhigh
```

When xhigh is selected, the proxy maps it to the DeepSeek upstream value:

```json
{
  "reasoning_effort": "max"
}
```

`summary off`in Codex status means OpenAI-style reasoning summaries are disabled. It does not disable DeepSeek thinking mode.

## DeepSeek V4 context window

DeepSeek V4 Pro and DeepSeek V4 Flash are configured with a 1M-token context window.

Repository catalog values:

```text
context_window = 1000000
max_context_window = 1000000
auto_compact_token_limit = 750000
```

Local Codex profile values should match:

```toml
model_context_window = 1000000
model_auto_compact_token_limit = 750000
tool_output_token_limit = 12000
```

The auto-compact threshold is intentionally below the full model context window to leave room for system instructions, tool results, and multi-turn growth.

## Tool bridge, namespace, and image artifact operations

Current stable behavior:

* `DEEPSEEK_PROXY_TOOL_BRIDGE=1` enables local execution of proxy tools returned by DeepSeek.
* `web_search` is mapped to `proxy_web_search`.
* `image_generation` is mapped to `proxy_image_generate`.
* `namespace=deepseek_proxy_account` is expanded into `proxy_status`, `proxy_usage_summary`, `proxy_usage_events`, and `proxy_balance`.
* Unknown namespaces remain unsupported and are recorded as `unsupported_tool_namespace`.

Provider status endpoints:

```bash
curl --noproxy '*' -sS http://127.0.0.1:8000/v1/proxy/status | python3 -m json.tool
curl --noproxy '*' -sS http://127.0.0.1:8000/v1/proxy/tool-bridge/status | python3 -m json.tool
```

Image generation environment:

```bash
DEEPSEEK_PROXY_IMAGE_PROVIDER=mock
DEEPSEEK_PROXY_IMAGE_MODEL=cogView-4-250304
DEEPSEEK_PROXY_IMAGE_SIZE=1024x1024
DEEPSEEK_PROXY_IMAGE_DOWNLOAD=0
DEEPSEEK_PROXY_IMAGE_OUTPUT_DIR=.generated/images
DEEPSEEK_PROXY_IMAGE_MAX_ARTIFACTS=100
```

Use `DEEPSEEK_PROXY_IMAGE_DOWNLOAD=1` to store generated image artifacts locally. Returned image records include `url`, `file_path`, `local_path`, `file_uri`, `downloaded`, and `mime_type` when available.

Operational smoke tests:

```bash
scripts/proxy-stress-test.py --profile stable --scale small || true

python3 - <<'CHECK'
from pathlib import Path
import json
latest = sorted(Path(".debug").glob("stress_report_*.json"), reverse=True)[0]
data = json.loads(latest.read_text(encoding="utf-8"))
for r in data["results"]:
    if "namespace" in r["name"]:
        print(r["name"], r["ok"], r.get("compat_warning_kinds"), r.get("upstream_tools_count"))
CHECK
```

Expected namespace stress semantics:

* `supported_namespace_tool` reports `mapped_tool_namespace`.
* `unsupported_namespace_tool` reports `unsupported_tool_namespace`.

## Codex apply_patch and MCP compatibility operations

Stable default behavior:

    DEEPSEEK_PROXY_FORWARD_CUSTOM_APPLY_PATCH=0

With the default setting, Codex `custom apply_patch` is ignored and recorded as `ignored_custom_tool`.

Experimental apply_patch bridge:

    DEEPSEEK_PROXY_FORWARD_CUSTOM_APPLY_PATCH=1

This exposes `apply_patch` to DeepSeek as a function tool using the Codex-required `input` argument. It has been verified in a real Codex session to modify a file through Codex's local apply_patch executor.

MCP namespace policy:

    MCP namespaces are audit-only.
    MCP tools are not executed through function-tool flattening.
    `cheap_router_status` failed with `unsupported call`.
    `mcp__cheap_llm__cheap_router_status` failed with `unsupported call`.

Do not enable MCP execution by mapping namespace tools into plain function tools. Future work should either use Codex's native MCP calling protocol, if exposed, or implement an explicit proxy-side MCP executor with a strict allowlist and separate write-permission gate.

## Codex tool forwarding defaults

As of v2.3a2, Codex tool forwarding is default-open for DeepSeek profiles:

- `DEEPSEEK_PROXY_FORWARD_CUSTOM_APPLY_PATCH=1`
- `DEEPSEEK_PROXY_FORWARD_MCP_READONLY_TOOLS=1`
- `DEEPSEEK_PROXY_FORWARD_MCP_WRITE_TOOLS=1`
- `DEEPSEEK_PROXY_FORWARD_MCP_TUTORIAL_TOOLS=1`

Set any flag to `0` to disable that forwarding class.

This only forwards tool schemas to DeepSeek and restores namespace-aware function calls. The proxy does not execute MCP tools directly and does not bypass Codex local MCP runtime, AGENTS.md, approval policy, or MCP server permissions.



## Runtime long-session observability

`debug long-session` is a read-only view over recent debug-trace events. It does not call the upstream model, does not write SQLite, and does not mutate payloads. By default it uses aggregate mode and scans recent `trace-*.jsonl` files from the active debug directory.

```bash
dsproxy debug long-session --thinking --limit 200 --mode aggregate
```

Latest-only fallback remains available when you need to inspect just the current `latest.json` target:

```bash
dsproxy debug long-session --thinking --limit 200 --mode latest
```

The report summarizes:

- recent `context_budget_breakdown` growth
- semantic payload compaction event counts
- semantic payload characters removed
- canary-blocked semantic payload attempts
- recent `tool_output_budget_breakdown` status
- aggregate `tool_output_trim_applied` counts, removed chars, category breakdown, and image payload trim count
- primary upstream usage prompt-token trend
- a rollout recommendation such as `collect_more_trace_data`, `continue_dry_run_observation`, `keep_dry_run_or_fix_canary`, or `monitor_limited_enabled_session`

Use this after long Codex or WeClaw sessions before enabling semantic payload compaction.


## Semantic compaction rollout

Semantic flattened-tool compaction is staged and conservative.

Pipeline:

1. `flattened_tool_transcript_semantic_audit`
   - classifies flattened tool transcripts by semantic type and risk.
2. `flattened_tool_transcript_semantic_policy_dry_run`
   - estimates whether a semantic payload compaction would be safe.
3. `flattened_tool_transcript_semantic_payload_compaction_applied`
   - only rewrites the upstream payload copy when explicitly enabled.

Default behavior is safe:

```bash
DEEPSEEK_PROXY_FLATTENED_TOOL_SEMANTIC_PAYLOAD_COMPACTION_MODE=dry_run
```

To inspect rollout readiness:

```bash
dsproxy status --thinking
dsproxy debug budget --thinking
dsproxy debug semantic --thinking
```

Only enable for a limited session after `semantic_compaction.rollout.safe_to_enable_payload_compaction` is true:

```bash
DEEPSEEK_PROXY_FLATTENED_TOOL_SEMANTIC_PAYLOAD_COMPACTION_MODE=enabled
```



Self-test without upstream calls:

```bash
dsproxy debug semantic --self-test --thinking
```

The self-test constructs local low-risk, medium-risk, and high-risk flattened tool transcript samples. It verifies that only low-risk passed pytest output would be compacted under enabled simulation, while stack traces, chatty terminal transcripts, recent messages, SQLite history, and original Responses history remain untouched.



Canary rollout check:

```bash
dsproxy debug semantic --canary-check --thinking
```

A limited enabled session now requires both environment variables:

```bash
DEEPSEEK_PROXY_FLATTENED_TOOL_SEMANTIC_PAYLOAD_CANARY_ALLOW_ENABLED=1
DEEPSEEK_PROXY_FLATTENED_TOOL_SEMANTIC_PAYLOAD_COMPACTION_MODE=enabled
```

If `MODE=enabled` is set without the canary allow variable, the runtime guard falls back to dry-run behavior and reports `semantic_payload_canary_guard_blocked_enabled`.




### Semantic compaction stability audit

The semantic compaction rollout is intentionally conservative. The stable request-path order is:

1. `flattened_tool_transcript_semantic_audit`
2. `flattened_tool_transcript_semantic_policy_dry_run`
3. `flattened_tool_transcript_semantic_payload_compaction_applied`
4. `flattened_tool_transcript_payload_compaction_applied`
5. `context_budget_breakdown`

Minimum safe rollout flow:

```bash
DEEPSEEK_PROXY_FLATTENED_TOOL_SEMANTIC_PAYLOAD_COMPACTION_MODE=dry_run
dsproxy debug semantic --self-test --thinking
dsproxy debug semantic --canary-check --thinking
```

For a limited enabled session, both variables are required:

```bash
DEEPSEEK_PROXY_FLATTENED_TOOL_SEMANTIC_PAYLOAD_CANARY_ALLOW_ENABLED=1
DEEPSEEK_PROXY_FLATTENED_TOOL_SEMANTIC_PAYLOAD_COMPACTION_MODE=enabled
```

Rollback is immediate by returning to dry-run:

```bash
DEEPSEEK_PROXY_FLATTENED_TOOL_SEMANTIC_PAYLOAD_COMPACTION_MODE=dry_run
```

Stability constraints:

- Semantic payload compaction must only rewrite the upstream payload copy.
- Original Responses history and SQLite history must remain unchanged.
- Default mode must remain `dry_run`.
- Canary guard must block `enabled` unless the explicit allow variable is set.
- Medium-risk and high-risk flattened tool transcripts must remain preserved.

Safety boundaries:

- SQLite history is not rewritten.
- Original Responses history is not rewritten.
- Only the upstream DeepSeek payload copy may be compacted.
- The enabled semantic payload compactor only compacts low-risk passed test output summaries.
- Medium-risk or high-risk transcripts are preserved.
