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


### API key and model metadata

The installer stores the DeepSeek API key in the local env file, by default `~/.config/deepseek-responses-proxy/env`, with restricted file permissions. Use:

```bash
dsproxy config show
dsproxy config set-api-key
dsproxy config test-api-key
dsproxy config set-web-search-api-key --provider serpapi
dsproxy config set-image-api-key --provider glm
```

The installer also connects that env file and the `dsproxy` wrapper directory to your shell profile so new terminals can find `dsproxy` and Codex can see `DEEPSEEK_API_KEY`. If the current shell still cannot find `dsproxy`, open a new terminal or source the shell profile printed by the installer.

Codex profiles installed by the script include the project model catalog metadata so `deepseek-v4-pro` and `deepseek-v4-flash` do not fall back to unknown-model metadata.

## 🚀 Quick start

After installation:

    codex --profile deepseek
    codex --profile deepseek-thinking

If you accepted the recommended codex wrapper, these commands automatically start the matching local proxy before launching Codex.

Continue a previous Codex conversation:

    codex --profile deepseek-thinking resume

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

## 🧠 Long session compaction behavior in v2.7a+

CoDeepSeedeX v2.7a+ reduces repeated context growth in long `deepseek-thinking` sessions by trimming oversized tool outputs before they are sent back into the model context.

Behavior summary:

- `deepseek-thinking` enables tool-output trimming by default.
- `deepseek` stable mode remains unchanged.
- Oversized `shell_command` and `interactive_shell` outputs are trimmed with head/tail retention.
- Large structured tool outputs are serialized compactly before trimming when possible.
- `image_payload` outputs have an additional 12000-character item cap.
- Trimming runs before previous-response function-call filtering, so outputs can still be classified while duplicate assistant tool-call replay remains avoided.

Latest real validation snapshot:

| Metric | Value |
| --- | --- |
| Trimmed categories | `shell_command`, `interactive_shell` |
| Characters removed by applied trimming | `44822` |
| Latest observed context size | `270012` chars |
| Max observed context size | `405107` chars |
| Removed chars vs latest context | about `16.6%` |
| Removed chars vs max context | about `11.1%` |

These numbers are a latest aggregate-trace snapshot, not a fixed compression ratio and not the total lifetime saving. Because previous tool outputs are replayed across later turns, removing oversized historical output reduces repeated context growth in subsequent requests. The cumulative prompt-budget effect can be larger than the one-time removed-char count.

Trade-off: the middle of very large outputs may be omitted. The retained head and tail usually preserve command setup, summaries, exits and recent error context. If exact full output matters, save it to a file and inspect or attach that file explicitly.

Inspect current long-session state:

```bash
dsproxy debug behavioral --thinking --limit 200 --timeout 5
```

## 🧩 Current compaction strategy

Tool outputs are classified before trimming. Only oversized outputs are rewritten.

| Category | Typical source | Current behavior |
| --- | --- | --- |
| `shell_command` | Non-interactive shell commands, tests, logs | Trim oversized outputs with head/tail retention. The middle may be omitted. |
| `interactive_shell` | Long-running or PTY-style command sessions | Trim oversized outputs with head/tail retention, preserving recent interaction context where possible. |
| `image_payload` | Image-view or image-returning tools with large structured payloads | Serialize structured output compactly where possible, then apply an image-specific 12000-character item cap. |
| `search` | Web/search style tool outputs | Classified separately so future policies do not treat search results as raw shell logs. Oversized output follows conservative trimming. |
| `file_read` | File inspection or file-read tools | Classified separately to preserve file-reading semantics. Oversized output follows conservative trimming. |
| `user_interaction` | Prompts, approvals or user-facing interaction tool outputs | Classified separately and handled conservatively because it may contain interaction state. |
| `unknown` | Tools without a known category | Uses conservative fallback trimming only when oversized, so the proxy can run without a fixed local tool list. |

Structured list/dict tool outputs are serialized to compact JSON before trimming. This helps large structured payloads enter the same budget path as plain text output.

For controlled maintainer validation, see `docs/real-long-session-validation.md`.

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

### C4 command-risk gate visibility

The proxy exposes command-risk policy status through `proxy_status` as `command_risk_policy`.

`DEEPSEEK_PROXY_COMMAND_RISK_POLICY_MODE` supports:

- `off`: disables command-risk policy reporting and gating.
- `dry_run`: records risk reports without changing tool execution.
- `enabled`: enables the C4 suppress-only gate.

The gate is intentionally Codex-aligned. Normal development operations such as project-local `apply_patch`, project file writes, cache cleanup, `/tmp` cleanup, dependency installation, and project-local destructive operations remain Codex-governed. The proxy suppresses only `C4_catastrophic_or_out_of_sandbox` operations, such as root/home/drive deletion, disk formatting, block-device overwrite, production database drop, or force-push to protected branches.

C4 suppression is suppress-only. It returns an assistant explanation and does not support automatic resume through “continue”.
