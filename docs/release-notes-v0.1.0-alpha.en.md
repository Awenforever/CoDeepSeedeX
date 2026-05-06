# Release Notes: v0.1.0-alpha

This is the first planned public technical preview of deepseek-responses-proxy.

## Highlights

- Local Responses-compatible proxy for Codex
- DeepSeek upstream bridge
- Codex-oriented tool-call normalization and protocol hardening
- Context trimming and persistent local compaction
- Adaptive compaction budget policy
- Agent-loop liveness guard
- LLM-based liveness judge
- Usage ledger with internal call attribution
- dsproxy CLI
- Codex profile bootstrap
- Preview install scripts
- English and Chinese documentation

## Known limitations

- This is not a production-stable replacement for native Codex
- Windows native installation is still experimental
- scripts/install.sh still needs the final public repository URL before one-line installation
- DeepSeek behavior is not identical to native Codex models
- Compaction is text-summary based and cannot reproduce Codex encrypted compaction internals

## Recommended audience

Technical users who understand Codex, local proxies, environment variables and the risks of tool-calling agents.

## Safety

Run only on localhost. Do not expose the proxy to a public network.
