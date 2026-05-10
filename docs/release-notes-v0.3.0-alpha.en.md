# CoDeepSeedeX v0.3.0-alpha

## Summary

Internal milestone: `v2.7a32-real-session-validation-hardening`.

This release focuses on context efficiency and long-session reliability for Codex + DeepSeek thinking mode. The main improvement is that oversized tool outputs are trimmed before they repeatedly re-enter the model context, reducing context pressure in long, tool-heavy development sessions.

## What changed for long sessions

- Thinking-mode startup now enables a limited rollout of tool-output trimming by default.
- Oversized shell and interactive-shell outputs can be compacted before they are sent back into model context.
- Large structured tool outputs are normalized before trimming where possible.
- Image-payload style tool outputs have a dedicated 12000-character cap in addition to the general tool-output trimming path.
- Long-session debug traces are aggregated into a behavioral readiness summary with blockers, context-budget signals, prompt-token signals, and tool-output trim metrics.
- `dsproxy debug behavioral --thinking` gives a compact view of whether the current long-session state is ready, blocked, or needs more trace data.

## Expected user impact

For long Codex sessions, especially sessions that repeatedly run tests, shell diagnostics, or log-heavy commands, CoDeepSeedeX should now spend less context on oversized tool outputs. This improves the chance that the session can continue without exhausting the prompt budget.

The trade-off is intentional: the middle of very large tool outputs may be omitted. The retained head and tail usually preserve the command result, summary, and most recent error context. If the full output matters, save it to a file and inspect or attach that file explicitly.

## Validation and diagnostics

This release adds:

- `docs/real-long-session-validation.md`
- `scripts/real-long-session-behavioral-smoke.sh`
- `dsproxy debug behavioral --thinking --limit 200 --timeout 5`

The smoke script is primarily for maintainers and controlled local validation. Most users only need the behavioral debug command when diagnosing long-session behavior.

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

- This release improves tool-output trimming and long-session observability. It does not claim full semantic compaction parity with native Codex.
- The full middle content of very large tool outputs may be removed. Save exact logs to files when exact reproduction is required.
- Large image-payload real-session validation remains separate.
- The guarded real smoke uses a powerful Codex bypass mode and should only be used for controlled local validation.
