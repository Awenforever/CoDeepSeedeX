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
