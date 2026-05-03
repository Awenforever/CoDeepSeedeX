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
