# Real long-session behavioral validation

This document records the controlled real Codex long-session behavioral validation flow for CoDeepSeedeX thinking mode.

## Purpose

The runtime behavioral check verifies whether long-session observability still preserves enough development state after tool-output trimming has occurred.

Use:

```bash
dsproxy debug behavioral --thinking --limit 200 --timeout 5
```

A healthy result for the current rollout is usually:

```json
{
  "behavioral": {
    "status": "ready",
    "recommendation": "ready_for_real_long_session_behavioral_test",
    "blockers": []
  }
}
```

## Sandbox boundary discovered in v2.7a31

Codex `workspace-write` sandbox cannot reliably access the host WSL loopback listener at `127.0.0.1:8001`.

Observed facts:

1. Outside Codex sandbox, `curl http://127.0.0.1:8001/healthz` succeeds.
2. Inside Codex `workspace-write` sandbox, the same request can fail with a connection error.
3. Inside Codex `workspace-write` sandbox, `dsproxy debug behavioral --thinking` can return `blocked` because the local proxy endpoint is unreachable.
4. With `codex exec --dangerously-bypass-approvals-and-sandbox`, Codex can access `127.0.0.1:8001`.
5. In bypass mode, the real long-session smoke passed and the repository remained clean.

Therefore, a `blocked` result from inside `workspace-write` is not sufficient evidence that the proxy or `debug behavioral` command is broken. First confirm whether the execution environment can reach `127.0.0.1:8001`.

## Current real-smoke acceptance criteria

A passing real long-session smoke should show:

- Codex ran the controlled large-output command.
- `dsproxy debug behavioral --thinking` returned `ready` or another expected non-endpoint-failure state.
- Codex final JSON parsed successfully.
- Codex did not wrap the final answer in Markdown fences.
- Codex preserved branch, working tree state, version, pytest result, behavioral status, trim count, and removed character count.
- The repository remained clean after the run.

## Guarded smoke script

Use the checked-in smoke runner instead of copying a long inline command:

```bash
scripts/real-long-session-behavioral-smoke.sh --dry-run
scripts/real-long-session-behavioral-smoke.sh --allow-bypass
```

The real run refuses to execute unless `--allow-bypass` is provided.

## Safety note

The bypass mode is intentionally powerful:

```bash
codex exec --profile deepseek-thinking --dangerously-bypass-approvals-and-sandbox
```

Use it only for controlled local validation. The prompt must restrict Codex to read-only repository commands, a controlled large-output command, and local behavioral checks. It must not print environment variables, write repository files, or commit anything.

## Non-goals

This smoke does not prove full semantic compaction. It validates the current tool-output trimming and long-session observability path under a controlled real Codex session.

Large image payload validation remains separate. If `image_payload_trim_count` is zero, that only means the latest real session did not exercise large image payload trimming.
