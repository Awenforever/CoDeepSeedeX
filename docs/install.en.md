# Installation Guide

## Recommended environment

Linux, macOS or WSL is recommended.

Requirements:

- Python 3.11+
- Git
- Codex CLI
- DEEPSEEK_API_KEY

## Install from source

    git clone <repo-url> ~/deepseek-responses-proxy
    cd ~/deepseek-responses-proxy
    python3 -m venv .venv
    .venv/bin/python -m pip install -e .

## Initialize configuration

    .venv/bin/dsproxy config init

Default config path:

    ~/.config/deepseek-responses-proxy/config.toml

## Install Codex profile

    .venv/bin/dsproxy install-codex-profile

Default target:

    ~/.codex/config.toml

Generated profile:

    deepseek-thinking

## Start proxy

    export DEEPSEEK_API_KEY="..."
    .venv/bin/dsproxy start --thinking
    .venv/bin/dsproxy doctor --thinking

## Run Codex

    codex --profile deepseek-thinking

## Preview installer

    bash scripts/install.sh

Before public release, replace the placeholder repository URL in scripts/install.sh.
