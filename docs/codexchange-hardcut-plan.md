# CodeXchange / CoX hard-cut migration contract

CodeXchange means Codex Exchange. The short form is CoX, pronounced Co-Ex, and the command is `cox`.

This branch starts the p3.0 hard-cut line. The product boundary is no longer a single upstream model family. The runtime is a generic local provider exchange for Codex, with model providers, tool providers, image providers, and web-search providers treated as separate capability groups.

## Current p3.0a1 scope

- Product name: CodeXchange.
- CLI command: `cox`.
- Python package: `codexchange_proxy`.
- Configuration prefix: `COX_`.
- Install/config/cache/state paths use `codexchange`.
- Primary managed Codex profile: `cox`.
- Provider-backed Codex profiles use provider ids such as `deepseek`, `qwen-us`, or custom ids.
- DeepSeek remains a provider, not the product boundary.

## Deferred p3.0 follow-up work

- Split provider-specific request/stream/tool/reasoning handling into provider adapters.
- Move DeepSeek pricing, tokenizer, balance, reasoning, and chat-completions extensions into a dedicated provider module.
- Replace generic start/status route names that still expose reasoning-mode history with capability-oriented route naming.
- Rebuild release assets only after install, upgrade, uninstall, and real Codex wrapper validation pass.
