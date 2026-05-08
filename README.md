# CoDeepSeedeX

[中文说明](README.zh-CN.md) | English

<!-- CODEEPSEEDEX_LOGO_START -->
<p align="center">
  <img src="docs/logo.png" alt="CoDeepSeedeX logo" width="220">
</p>
<!-- CODEEPSEEDEX_LOGO_END -->

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

## ⬆️ Upgrade

CoDeepSeedeX supports two compatible upgrade paths.

### Path A: `dsproxy upgrade`

Use this when your installed version already includes the `upgrade` command:

```bash
dsproxy upgrade
```

Preview first:

```bash
dsproxy upgrade --dry-run
```

By default, `dsproxy upgrade` updates the git checkout to the latest `master` from `origin`, reinstalls the package, refreshes the `deepseek` and `deepseek-thinking` Codex profiles, and restarts the local proxies.

If you intentionally need a fixed release or branch, pass an explicit ref:

```bash
dsproxy upgrade --tag <tag-or-branch>
```

### Path B: rerun the one-line installer

Use this when upgrading from older releases such as `v0.1.0-alpha`, or when `dsproxy upgrade` is not available:

```bash
curl -fsSL https://raw.githubusercontent.com/Awenforever/CoDeepSeedeX/master/scripts/install.sh | bash
```

This path is intentionally compatible with Path A. The installer tracks the current `master` one-line installer, refreshes the installation and profiles, and preserves local env and Codex configuration by default.

Verify after either path:

```bash
dsproxy --version
dsproxy doctor --thinking
curl -sS http://127.0.0.1:8000/healthz
curl -sS http://127.0.0.1:8001/healthz
```

## 🔌 MCP behavior in v2.6a+

CoDeepSeedeX treats Codex MCP configuration as the default trust boundary.

- Default MCP policy: `codex`
- Default MCP backend: `stdio`
- Proxy-side MCP allowlists are not required by default
- Write-capable MCP tools are not rejected by default
- The target server must exist in `~/.codex/config.toml`
- The target tool must be exposed by the server's runtime `tools/list`
- Currently supported MCP transport: stdio `command` + `args`
- Not yet supported: HTTP/SSE/remote MCP transports

## 🚀 Quick start

After installation:

    codex --profile deepseek
    codex --profile deepseek-thinking

If you accepted the recommended codex wrapper, these commands automatically start the matching local proxy before launching Codex.

Continue a previous Codex conversation:

    codex --profile deepseek-thinking resume

## 🧠 deepseek vs deepseek-thinking

The difference is simple:

- `deepseek` sends Codex requests to DeepSeek with thinking disabled.
- `deepseek-thinking` sends Codex requests to DeepSeek with thinking enabled.

They are two Codex profiles that point to two local CoDeepSeedeX proxy modes.

| Profile | Local port | DeepSeek mode | Recommended use |
|---|---:|---|---|
| `deepseek` | 8000 | non-thinking | quick edits, lightweight tasks, lower-cost use |
| `deepseek-thinking` | 8001 | thinking | long tasks, multi-step coding, tool-heavy agent loops |

In other words, `deepseek-thinking` does not mean a different Codex. It means CoDeepSeedeX asks the upstream DeepSeek model to run in thinking mode.

## 🤖 Supported DeepSeek models

CoDeepSeedeX currently targets the official DeepSeek V4 API model names.

The same DeepSeek V4 model can be used in two modes:

- non-thinking mode: DeepSeek returns the answer directly.
- thinking mode: DeepSeek performs an explicit reasoning phase before returning the answer.

| Upstream model | non-thinking mode | thinking mode | Recommended CoDeepSeedeX use |
|---|---|---|---|
| `deepseek-v4-pro` | Supported | Supported | Best default for `deepseek-thinking`, long coding tasks, stronger reasoning |
| `deepseek-v4-flash` | Supported | Supported | Best default for `deepseek`, faster and lower-cost tasks |

Legacy compatibility names:

| Legacy name | Meaning in practice | Status |
|---|---|---|
| `deepseek-chat` | `deepseek-v4-flash` with thinking disabled | compatibility name |
| `deepseek-reasoner` | `deepseek-v4-flash` with thinking enabled | compatibility name |

CoDeepSeedeX defaults:

| Codex profile | Default upstream model | DeepSeek mode |
|---|---|---|
| `deepseek` | `deepseek-v4-flash` | non-thinking |
| `deepseek-thinking` | `deepseek-v4-pro` | thinking |

Use `dsproxy config set-model deepseek-v4-pro` or `dsproxy config set-model deepseek-v4-flash` to switch the upstream model. Use `/model` inside Codex TUI to change Codex-side model or reasoning settings when available.

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
    dsproxy config set-effort max

View usage:

    dsproxy usage --thinking --summary

Full CLI help:

    dsproxy -H
### 🤝 WeClaw integration

<!-- CODEEPSEEDEX_WECLAW_DEV_INTEGRATION_START -->

CoDeepSeedeX can be used together with [weclaw_dev](https://github.com/Awenforever/weclaw_dev) as the DeepSeek/Codex runtime backend for WeClaw-style chat and automation workflows.

Current integration boundary:

- WeClaw can route user messages to Codex profiles backed by CoDeepSeedeX.
- CoDeepSeedeX provides the local DeepSeek Responses-compatible proxy, runtime model controls, MCP tool bridging, and upgrade path.
- WeClaw remains responsible for the messaging surface, session routing, command UX, and user-facing bot behavior.
- CoDeepSeedeX does not replace WeClaw, and WeClaw does not change CoDeepSeedeX proxy internals.

<!-- CODEEPSEEDEX_WECLAW_DEV_INTEGRATION_END -->

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
