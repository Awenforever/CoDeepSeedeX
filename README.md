# CoDeepSeedeX

[中文说明](README.zh-CN.md) | English

Local OpenAI Responses-compatible proxy for running Codex with DeepSeek models.

## ✅ Prerequisites

Before installing CoDeepSeedeX, make sure the OpenAI Codex CLI is already installed and the `codex` command is available on your `PATH`.

    codex --version

If Codex CLI is not installed yet, install it first:

    npm install -g @openai/codex

Then run the CoDeepSeedeX installer.

## ⚡ One-line install

    curl -fsSL https://raw.githubusercontent.com/Awenforever/CoDeepSeedeX/master/scripts/install.sh | bash

The installer will:

- install CoDeepSeedeX into `~/.local/share/deepseek-responses-proxy`
- create the `dsproxy` command
- create two Codex profiles: `deepseek` and `deepseek-thinking`
- optionally install a safe `codex` wrapper for these two profiles only
- ask for stable/thinking ports and your DeepSeek API key
- save the API key in a local `chmod 600` env file

The API key uses hidden input. It is not printed to the terminal. This is local permission-based storage, not cryptographic encryption.

## 🚀 Quick start

After installation:

    codex --profile deepseek
    codex --profile deepseek-thinking

If you accepted the recommended codex wrapper, these commands automatically start the matching local proxy before launching Codex.

Continue a previous Codex conversation:

    codex --profile deepseek-thinking resume

## 🧠 deepseek vs deepseek-thinking

| Profile | Local port | Mode | Recommended use |
|---|---:|---|---|
| `deepseek` | 8000 | stable proxy | quick edits, lightweight tasks, lower-cost use |
| `deepseek-thinking` | 8001 | thinking proxy | long tasks, multi-step coding, tool-heavy agent loops |

Both profiles use the local CoDeepSeedeX proxy. The difference is the local endpoint and runtime mode.

## 🤖 Supported DeepSeek models

CoDeepSeedeX currently targets the official DeepSeek V4 API model names.

| Upstream model | Thinking mode | Non-thinking mode | Recommended CoDeepSeedeX use |
|---|---|---|---|
| `deepseek-v4-pro` | Supported | Supported | Best default for `deepseek-thinking`, long coding tasks, stronger reasoning |
| `deepseek-v4-flash` | Supported | Supported | Best default for `deepseek`, faster and lower-cost tasks |

Legacy compatibility names:

| Legacy name | Current mapping | Status |
|---|---|---|
| `deepseek-chat` | non-thinking mode of `deepseek-v4-flash` | compatibility name, scheduled for deprecation |
| `deepseek-reasoner` | thinking mode of `deepseek-v4-flash` | compatibility name, scheduled for deprecation |

CoDeepSeedeX defaults:

| Codex profile | Default upstream model | Default mode |
|---|---|---|
| `deepseek` | `deepseek-v4-flash` | stable / lightweight mode |
| `deepseek-thinking` | `deepseek-v4-pro` | thinking-oriented mode |

Notes:

- DeepSeek V4 models support both thinking and non-thinking modes.
- `deepseek-thinking` is the recommended profile for long agentic coding tasks.
- `deepseek` is the recommended profile for quick edits, lighter usage and lower cost.
- Use `dsproxy config set-model deepseek-v4-pro` or `dsproxy config set-model deepseek-v4-flash` to switch the upstream model.
- Use `/model` inside Codex TUI to change Codex-side model or reasoning settings when available.

## 🧭 Codex TUI commands

Inside Codex TUI:

    /status

Show current session and runtime status.

    /model

Switch model or reasoning effort inside Codex.

    /plan

Use planning mode before implementation work.

You can also type natural-language requests such as:

    check balance

Codex will usually call local tools to run `dsproxy balance`. The most deterministic shell command is still:

    dsproxy balance

## 🔧 Shell operations

Check proxy health:

    dsproxy doctor --thinking

Show DeepSeek balance:

    dsproxy balance

Show local configuration:

    dsproxy config show

Switch DeepSeek upstream model:

    dsproxy config set-model deepseek-v4-pro
    dsproxy config set-model deepseek-v4-flash

Change Codex reasoning effort:

    dsproxy config set-effort medium
    dsproxy config set-effort high
    dsproxy config set-effort xhigh

View usage:

    dsproxy usage --thinking --summary

Full CLI help:

    dsproxy -H

## 🧹 Uninstall and restore

Remove CoDeepSeedeX Codex profiles and wrappers:

    bash scripts/install.sh --uninstall

If the installer replaced an existing `codex` command in the install bin directory, it records a backup path and restores it during uninstall when possible.

By default, uninstall removes the integration wrappers and Codex profiles. It does not delete the installed source directory or the local env file. To remove those as well:

    bash scripts/install.sh --uninstall --remove-files

## 📦 Install from source

    git clone https://github.com/Awenforever/CoDeepSeedeX.git ~/deepseek-responses-proxy
    cd ~/deepseek-responses-proxy
    python3 -m venv .venv
    .venv/bin/python -m pip install -e .

Initialize:

    .venv/bin/dsproxy config init
    .venv/bin/dsproxy install-codex-profile --name deepseek --base-url http://127.0.0.1:8000/v1
    .venv/bin/dsproxy install-codex-profile --name deepseek-thinking --base-url http://127.0.0.1:8001/v1

## 🔐 Security

CoDeepSeedeX is designed for localhost use. Do not expose it to a public network.

Codex may call tools, modify files, execute commands and access MCP servers depending on your Codex configuration.

Read:

- docs/security.en.md
- docs/security.zh-CN.md
