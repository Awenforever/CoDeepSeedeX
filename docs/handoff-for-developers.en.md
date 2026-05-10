# Developer Handoff

## Current scope

deepseek-responses-proxy is a local Responses-compatible proxy for Codex.

It is not intended to be a generic model gateway. The priority is improving the codex --profile deepseek-thinking experience.

## Version line

- v2.3a1 output_text content normalization
- v2.3a2 default-open Codex tool forwarding
- v2.3a3 context trimming
- v2.3a4 persistent local compaction
- v2.3a5 runtime observability
- v2.3a6 agent loop liveness guard
- v2.3a7 tool-call protocol hardening
- v2.3a8 Codex tool protocol instruction and liveness judge
- v2.3a9 internal usage attribution
- v2.3a10 adaptive compaction budget policy
- v2.4a1 dsproxy CLI and config foundation
- v2.4a1a1 CLI start version and port guard
- v2.4a2 install scripts and Codex profile bootstrap
- v2.4a3 docs and release guide

## Invariants

- Bind to 127.0.0.1 by default
- Preserve Responses envelope compatibility
- Preserve function_call and tool_call pairing
- Never treat an old service as a ready new service
- Usage ledger should record internal upstream calls
- Codex profile installation should preserve user config where possible

## Pre-release checklist

- Confirm scripts/install.sh points to the public GitHub repository URL
- Check README links
- Test fresh clone installation
- Test WSL
- Test missing API key diagnostics
- Test Codex profile install and uninstall
- Run a secret scan

## v0.3.0-alpha long-session reliability handoff

- Runtime release line: `v0.3.0-alpha`.
- Internal milestone: `v2.7a32-real-session-validation-hardening`.
- `dsproxy debug behavioral --thinking` is the compact runtime readiness check for long Codex thinking sessions.
- `docs/real-long-session-validation.md` records the real-session validation boundary and acceptance criteria.
- `scripts/real-long-session-behavioral-smoke.sh --dry-run` validates the guarded smoke runner without invoking Codex.
- `scripts/real-long-session-behavioral-smoke.sh --allow-bypass` runs the controlled real smoke. It intentionally uses `codex exec --dangerously-bypass-approvals-and-sandbox` because Codex `workspace-write` sandbox cannot reliably reach the host WSL listener at `127.0.0.1:8001`.
- Do not interpret a sandbox-local `blocked` behavioral result as a proxy failure until localhost reachability from that execution environment is confirmed.
