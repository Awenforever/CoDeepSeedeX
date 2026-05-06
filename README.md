# deepseek-responses-proxy

A local experimental OpenAI Responses-compatible proxy for using Codex with DeepSeek upstream models.

The project focuses on making:

    codex --profile deepseek-thinking

closer to the native Codex experience.

## Status

Technical preview. Recommended public release label:

    v0.1.0-alpha

This is not a production-stable replacement for native Codex.

## Features

- Responses-compatible local API for Codex
- DeepSeek ChatCompletions upstream bridge
- Codex tool-call normalization and protocol hardening
- Default-open Codex tool forwarding
- Context trimming and persistent local compaction
- Agent-loop liveness guard
- Lightweight LLM liveness judge
- Internal usage attribution by purpose
- Adaptive compaction budget policy
- dsproxy CLI for start, stop, status, doctor, logs, usage and Codex profile bootstrap

## Security notice

Run only on localhost. Do not expose the proxy to a public network.

Codex may call tools, modify files, execute commands and access MCP servers depending on your Codex configuration.

Read:

    docs/security.en.md
    docs/security.zh-CN.md

## Requirements

- Linux, macOS or WSL
- Python 3.11+
- Git
- Codex CLI
- DEEPSEEK_API_KEY

Windows native support is experimental. WSL is recommended.

## Install from source

    git clone <repo-url> ~/deepseek-responses-proxy
    cd ~/deepseek-responses-proxy
    python3 -m venv .venv
    .venv/bin/python -m pip install -e .

## Initialize

    .venv/bin/dsproxy config init
    .venv/bin/dsproxy install-codex-profile

## Start

    export DEEPSEEK_API_KEY="..."
    .venv/bin/dsproxy start --thinking
    .venv/bin/dsproxy doctor --thinking

## Use with Codex

    codex --profile deepseek-thinking

## Usage ledger

    .venv/bin/dsproxy usage --thinking --summary
    .venv/bin/dsproxy usage --thinking --summary --purpose primary
    .venv/bin/dsproxy usage --thinking --summary --purpose tool_bridge
    .venv/bin/dsproxy usage --thinking --summary --purpose compaction
    .venv/bin/dsproxy usage --thinking --summary --purpose liveness_judge

## Documentation

- English install guide: docs/install.en.md
- Chinese install guide: docs/install.zh-CN.md
- English usage guide: docs/usage.en.md
- Chinese usage guide: docs/usage.zh-CN.md
- Troubleshooting: docs/troubleshooting.en.md and docs/troubleshooting.zh-CN.md
- Security: docs/security.en.md and docs/security.zh-CN.md
- Architecture: docs/architecture.en.md and docs/architecture.zh-CN.md
- Developer handoff: docs/handoff-for-developers.en.md and docs/handoff-for-developers.zh-CN.md
