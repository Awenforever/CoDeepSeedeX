# Troubleshooting

## Proxy is not reachable

Symptom:

```text
curl: Failed to connect to 127.0.0.1 port 8000
```

Check stable proxy:

```bash
dsproxy-status
dsproxy-log
```

Check thinking proxy:

```bash
dsproxy-status-thinking
dsproxy-log-thinking
```

Manual check:

```bash
curl -sS http://127.0.0.1:8000/healthz | python3 -m json.tool
curl -sS http://127.0.0.1:8001/healthz | python3 -m json.tool
```

## Missing DeepSeek API key

Symptom:

```text
DeepSeek upstream authentication error
```

Check that `DEEPSEEK_API_KEY` is available in the environment used to start the proxy.

Manual startup example:

```bash
export DEEPSEEK_API_KEY='your-key'
PYTHONPATH=. python -m uvicorn deepseek_responses_proxy.app:app --host 127.0.0.1 --port 8000
```

## Codex says model metadata was not found

Symptom:

```text
Model metadata for `deepseek-v4-flash` not found. Defaulting to fallback metadata.
```

Current interpretation:

```text
Usually harmless for basic text and tool-call workflows.
```

Watch for context-window, tool-capability, or token-budgeting side effects.

## Unsupported built-in tools are ignored

Expected log examples:

```text
[deepseek-responses-proxy] ignored unsupported namespace tool: unknown_namespace_for_stress_test

`web_search` and `image_generation` should no longer be reported as unsupported when `DEEPSEEK_PROXY_TOOL_BRIDGE=1`; they map to `proxy_web_search` and `proxy_image_generate`. The whitelisted namespace `deepseek_proxy_account` should map to `mapped_tool_namespace`. Unknown namespaces are still dropped and recorded as `unsupported_tool_namespace`.
```

Reason:

```text
DeepSeek Chat Completions cannot execute OpenAI-hosted built-in tools.
```

This is expected unless Codex depends on those tools for the task.

## Thinking mode rejects old history

Possible upstream error:

```text
The `reasoning_content` in the thinking mode must be passed back to the API.
```

Current repair behavior:

```text
The proxy repairs legacy assistant messages by adding empty reasoning_content fields.
```

If the session still fails, start a fresh thinking session:

```bash
cd /tmp
mkdir -p codex-thinking-fresh
cd codex-thinking-fresh
codex --profile deepseek-thinking
```

## Resume opened the wrong profile history

Avoid this pattern when both profiles were recently used:

```bash
codex --profile deepseek-thinking resume --last
```

Safer pattern:

```bash
codex --profile deepseek-thinking resume <session_id>
```

## Health check text response fails

Run:

```bash
./health_check.sh
```

Then inspect temporary output:

```bash
cat /tmp/ds_proxy_health_text.json
cat /tmp/ds_proxy_health_stream.txt
```

Check logs:

```bash
dsproxy-log
```

## Balance endpoint fails

Run:

```bash
curl -sS http://127.0.0.1:8000/v1/proxy/status | python3 -m json.tool
curl -sS http://127.0.0.1:8000/v1/proxy/balance | python3 -m json.tool
```

Possible causes:

* missing or invalid DeepSeek API key
* upstream DeepSeek account issue
* network error
* upstream endpoint changed

## Usage summary is empty

Usage records are written only after successful proxy requests with usage fields returned by DeepSeek.

Generate one request:

```bash
curl -sS http://127.0.0.1:8000/v1/responses \
  -H "Content-Type: application/json" \
  -d '{"model":"deepseek-v4-flash","input":"Reply exactly: ok"}' \
  | python3 -m json.tool
```

Then check:

```bash
curl -sS http://127.0.0.1:8000/v1/proxy/usage/summary | python3 -m json.tool
```

## Pytest cannot import the package

Use:

```bash
cd ~/projects/deepseek-responses-proxy
source .venv/bin/activate
TMPDIR=~/projects/deepseek-responses-proxy/.tmp PYTHONPATH=. python -m pytest -q -s
```

## Dirty worktree before development

Check:

```bash
git status --short
```

If unexpected runtime files appear, confirm `.gitignore` covers them before continuing.

Do not commit:

* `.venv/`
* `.tmp/`
* `.debug/`
* `backups/`
* `proxy.log`
* `proxy.pid`
* `proxy-thinking.log`
* `proxy-thinking.pid`
* `*.sqlite`
* `*.sqlite3`
* `*.db`

## Codex starts but proxy is unreachable

If `codex --profile deepseek-thinking` opens the TUI but `/healthz` fails, separate Codex startup from proxy startup.

Check host-side runtime status:

```bash
dsproxy-status
dsproxy-status-thinking
curl --noproxy '*' -sS http://127.0.0.1:8000/healthz | python3 -m json.tool
curl --noproxy '*' -sS http://127.0.0.1:8001/healthz | python3 -m json.tool
```

If ports are down, start explicitly:

```bash
dsproxy start
dsproxy start thinking
```

If `curl` returns `502 Bad Gateway` for localhost, check proxy variables. Local checks must bypass system proxies:

```bash
curl --noproxy '*' -sS http://127.0.0.1:8000/healthz
curl --noproxy '*' -sS http://127.0.0.1:8001/healthz
```

The tracked script templates in `scripts/` already apply this behavior. Reinstall them with:

```bash
scripts/install-runtime-scripts.sh
```

## Image generation artifacts

If `DEEPSEEK_PROXY_IMAGE_DOWNLOAD=1`, generated image results should include local artifact fields:

```json
{
  "file_path": "...",
  "local_path": "...",
  "file_uri": "file://...",
  "downloaded": true
}
```

Check runtime configuration with:

```bash
curl --noproxy '*' -sS http://127.0.0.1:8000/v1/proxy/tool-bridge/status | python3 -m json.tool
```

If `.generated/images` grows unexpectedly, set:

```bash
DEEPSEEK_PROXY_IMAGE_MAX_ARTIFACTS=100
```

Set it to `0` to disable automatic pruning. The pruning logic only removes proxy-generated filenames with known prefixes and does not delete unrelated user files.

## Codex apply_patch or MCP tool issues

If DeepSeek does not call `apply_patch`, confirm that the proxy was started with:

    DEEPSEEK_PROXY_FORWARD_CUSTOM_APPLY_PATCH=1

If `apply_patch` returns an argument error such as `missing field input`, the proxy is running an older build that exposed `patch` instead of Codex's required `input` argument. Restart the proxy on a build at or after `v2.1a3a2-apply-patch-description-guidance`.

If `apply_patch` returns patch-format errors, check that the model used Codex apply_patch format:

    *** Begin Patch
    *** Update File: relative/path
     context lines start with a single space
    +added lines start with plus
    -removed lines start with minus
    *** End Patch

If MCP tools such as `cheap_router_status` or `mcp__cheap_llm__cheap_router_status` return `unsupported call`, this is expected. MCP namespace tools are currently compressed for audit but not executable through function-tool flattening.

## Codex tool forwarding defaults

As of v2.3a2, Codex tool forwarding is default-open for DeepSeek profiles:

- `DEEPSEEK_PROXY_FORWARD_CUSTOM_APPLY_PATCH=1`
- `DEEPSEEK_PROXY_FORWARD_MCP_READONLY_TOOLS=1`
- `DEEPSEEK_PROXY_FORWARD_MCP_WRITE_TOOLS=1`
- `DEEPSEEK_PROXY_FORWARD_MCP_TUTORIAL_TOOLS=1`

Set any flag to `0` to disable that forwarding class.

This only forwards tool schemas to DeepSeek and restores namespace-aware function calls. The proxy does not execute MCP tools directly and does not bypass Codex local MCP runtime, AGENTS.md, approval policy, or MCP server permissions.

## Command-risk and C4gate troubleshooting

If normal development commands appear blocked, first check `proxy_status.command_risk_policy`.

Expected behavior:

- Project-local edits, `apply_patch`, file writes, cache cleanup, `/tmp` cleanup, dependency installation, and project-local cleanup should not be blocked by the proxy command-risk gate.
- Only `C4_catastrophic_or_out_of_sandbox` should be suppressed when `DEEPSEEK_PROXY_COMMAND_RISK_POLICY_MODE=enabled`.
- C4 examples include root/home/drive deletion, disk formatting, block-device overwrite, production database drop, and force-push to protected branches.
- Suppressed C4 actions are not resumed by “continue”.

For diagnosis, inspect `.debug/user_tool_command_risk_report.json`.
