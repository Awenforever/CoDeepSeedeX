# Architecture

## Overview

Codex talks to the local proxy through an OpenAI Responses-style API.

    Codex CLI
      -> Responses API
    deepseek-responses-proxy
      -> ChatCompletions API
    DeepSeek upstream

## Main modules

deepseek_responses_proxy/app.py contains the FastAPI application.

deepseek_responses_proxy/cli.py provides the dsproxy command line interface.

SQLite stores response history and usage ledger events.

.debug stores context trimming, compaction, tool bridge and liveness guard reports.

## Key capabilities

- Responses envelope translation
- tool_call and function_call protocol repair
- Codex tool forwarding
- Context trimming
- Persistent local compaction
- Liveness guard and LLM judge
- Usage attribution by internal call purpose
- Adaptive compaction budget policy

## Usage attribution

Since v2.3a9, every upstream DeepSeek call records a usage event.

Important fields:

- purpose
- call_index
- requested_model
- effective_model
- upstream_model
- prompt_tokens
- completion_tokens
- total_tokens
