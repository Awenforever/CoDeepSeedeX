# CoDeepSeedeX v0.3.0-alpha

## Summary

Internal milestone: `v2.7a32-real-session-validation-hardening`.

This release focuses on long-session reliability for Codex + DeepSeek thinking mode. It closes the loop from tool-output trimming to runtime observability, behavioral readiness checks, and a guarded real Codex smoke test.

## Highlights

- Added `dsproxy debug behavioral` as a compact runtime readiness check for long sessions.
- Aggregated long-session debug traces into actionable behavioral status, blockers, context-budget signals, prompt-token signals, and tool-output trim metrics.
- Hardened thinking-mode tool-output trimming rollout for shell and interactive-shell heavy sessions.
- Preserved structured tool-output trimming for image payloads, with image-specific caps still staged by rollout configuration.
- Added `docs/real-long-session-validation.md` for real long-session validation.
- Added `scripts/real-long-session-behavioral-smoke.sh` as a guarded smoke runner.
- Documented the Codex `workspace-write` sandbox boundary for local WSL proxy access at `127.0.0.1:8001`.

## Validation

The guarded smoke runner supports:

```bash
scripts/real-long-session-behavioral-smoke.sh --dry-run
scripts/real-long-session-behavioral-smoke.sh --allow-bypass
```

The real smoke uses `codex exec --dangerously-bypass-approvals-and-sandbox` because Codex `workspace-write` sandbox cannot reliably reach the host WSL listener at `127.0.0.1:8001`.

## Upgrade

Latest upgrade:

```bash
dsproxy upgrade
```

Preview:

```bash
dsproxy upgrade --dry-run
```

Older releases without `dsproxy upgrade` can rerun the one-line installer:

```bash
curl -fsSL https://raw.githubusercontent.com/Awenforever/CoDeepSeedeX/master/scripts/install.sh | bash
```

## Known limitations

- This release validates tool-output trimming and long-session observability. It does not claim full semantic compaction parity with native Codex.
- Large image-payload real-session validation remains separate.
- The guarded real smoke uses a powerful Codex bypass mode and should only be used for controlled local validation.
