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
