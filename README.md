# CoDeepSeedeX

[中文文档](README.zh-CN.md) | [English](README.md)

Local OpenAI Responses-compatible proxy for running Codex with DeepSeek models.

## One-line install

    curl -fsSL https://raw.githubusercontent.com/Awenforever/CoDeepSeedeX/master/scripts/install.sh | bash

The installer asks for the stable proxy port, thinking proxy port and DeepSeek API key. The API key is entered with hidden input and stored in a chmod 600 local env file. This is not cryptographic encryption.

After installation:

    dsproxy start --thinking
    codex --profile deepseek-thinking

Continue a previous Codex conversation:

    codex --profile deepseek-thinking resume

## What this project does

CoDeepSeedeX is a local experimental OpenAI Responses-compatible proxy for using Codex with DeepSeek upstream models.

It provides:

- Responses-compatible local API for Codex
- DeepSeek ChatCompletions upstream bridge
- Codex tool-call normalization and protocol hardening
- Default-open Codex tool forwarding
- Context trimming and persistent local compaction
- Agent-loop liveness recovery
- Lightweight LLM liveness judge
- Usage attribution by internal call purpose
- Adaptive compaction budget policy
- dsproxy CLI for start, stop, status, doctor, logs, usage and Codex profile bootstrap

## Daily shell commands

Check proxy health:

    dsproxy doctor --thinking

Check DeepSeek balance:

    dsproxy balance

Show local proxy configuration:

    dsproxy config show

Switch DeepSeek upstream model:

    dsproxy config set-model deepseek-v4-pro
    dsproxy config set-model deepseek-v4-flash

Change Codex reasoning effort:

    dsproxy config set-effort medium
    dsproxy config set-effort high
    dsproxy config set-effort xhigh

Start or stop the thinking proxy:

    dsproxy start --thinking
    dsproxy stop --thinking

View usage ledger:

    dsproxy usage --thinking --summary
    dsproxy usage --thinking --summary --purpose primary
    dsproxy usage --thinking --summary --purpose tool_bridge
    dsproxy usage --thinking --summary --purpose compaction
    dsproxy usage --thinking --summary --purpose liveness_judge

Show full CLI help:

    dsproxy -H

## Codex TUI commands

After entering Codex with:

    codex --profile deepseek-thinking

you can also use Codex TUI slash commands.

Check current session and runtime status:

    /status

Switch model or reasoning effort inside Codex:

    /model

Use planning mode before implementation work:

    /plan

These slash commands are handled by Codex itself. dsproxy provides the local model endpoint and helper configuration, but the TUI commands are Codex-side controls.

## Install from source

    git clone https://github.com/Awenforever/CoDeepSeedeX.git ~/deepseek-responses-proxy
    cd ~/deepseek-responses-proxy
    python3 -m venv .venv
    .venv/bin/python -m pip install -e .

Initialize:

    .venv/bin/dsproxy config init
    .venv/bin/dsproxy install-codex-profile

Start:

    export DEEPSEEK_API_KEY="..."
    .venv/bin/dsproxy start --thinking
    .venv/bin/dsproxy doctor --thinking

## Security notice

Run only on localhost. Do not expose the proxy to a public network.

Codex may call tools, modify files, execute commands and access MCP servers depending on your Codex configuration.

Read:

- docs/security.en.md
- docs/security.zh-CN.md

## Status

Technical preview. Recommended public release label:

    v0.1.0-alpha

This is not a production-stable replacement for native Codex.
