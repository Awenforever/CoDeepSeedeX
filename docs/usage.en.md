# Usage Guide

## Common commands

Print version:

    dsproxy --version

Initialize config:

    dsproxy config init

Start thinking proxy:

    dsproxy start --thinking

Check status:

    dsproxy status --thinking

Run diagnostics:

    dsproxy doctor --thinking

Read logs:

    dsproxy logs --thinking --lines 120

Stop:

    dsproxy stop --thinking

## Codex

Install profile:

    dsproxy install-codex-profile

Run:

    codex --profile deepseek-thinking

## Usage ledger

Summary:

    dsproxy usage --thinking --summary

By internal call purpose:

    dsproxy usage --thinking --summary --purpose primary
    dsproxy usage --thinking --summary --purpose tool_bridge
    dsproxy usage --thinking --summary --purpose compaction
    dsproxy usage --thinking --summary --purpose liveness_judge
    dsproxy usage --thinking --summary --purpose liveness_retry

## Purpose fields

primary: main model calls.

tool_bridge: continuation calls after tool execution.

compaction: context compaction summarization calls.

liveness_judge: lightweight calls that decide whether a response should continue with tool calls.

liveness_retry: retry calls triggered by the liveness guard.

