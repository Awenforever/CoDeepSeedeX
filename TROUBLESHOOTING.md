# Troubleshooting

This is the user-facing troubleshooting entry for CodeXchange. Maintainer-only workflow notes are kept in `docs/developer-handbook.zh-CN.md`.

## Port already in use

Check local proxy processes:

```bash
cox status
cox status thinking
```

Stop and restart:

```bash
cox stop
cox stop thinking
cox start
cox start thinking
```

## CLI version and service version mismatch

Check both CLI and runtime:

```bash
cox --version
curl -sS http://127.0.0.1:8000/healthz
curl -sS http://127.0.0.1:8001/healthz
```

If the installed checkout is stale, rerun the installer or use `cox upgrade`.

## API key validation fails during config or install

Expected behavior:

- Failed validation does not save the key.
- `cox config wizard` and the installer allow skipping a provider and configuring it later.
- `--skip-validation` stores the key without a network probe and should be used only when the provider is temporarily unreachable or when you intentionally accept the risk.

Check provider names and retry with the explicit provider:

```bash
cox config set-web-search-api-key --provider serpapi --value YOUR_KEY
cox config set-image-api-key --provider zhipu --value YOUR_KEY
```

Notes:

- Web search validation may perform a small live query and may consume quota.
- Image validation is usually non-generating and does not prove real image generation.
- Use live diagnostics only when you accept possible quota consumption:

```bash
cox doctor providers --live --allow-spend
```

## Missing Codex profile

Reinstall profiles by rerunning the installer, then verify:

```bash
codex --profile deepseek
codex --profile cox
```

## Codex still shows GPT models

Check that the active Codex profile is the CodeXchange profile and that the wrapper is first on `PATH`:

```bash
command -v codex
codex --profile cox
```

Inside Codex TUI, `/model` should reflect the configured DeepSeek profile. If it does not, check `~/.codex/config.toml` and the wrapper path.

## VM GitHub access is unstable

If a VM cannot reliably reach GitHub directly, use a VM-reachable host proxy. For VMware NAT with 极连云, the known stable pattern is:

```text
VM -> 192.168.231.1:7896 -> Windows portproxy -> 127.0.0.1:7892 -> 极连云
```

Then configure GitHub-specific proxy settings in the VM.

## Security notes

- Keep the proxy bound to localhost unless you fully understand the exposure.
- Do not paste API keys into logs.
- Do not publish local env files.
- Review tool execution carefully because Codex may run commands and modify files depending on profile configuration.

## Maintainer notes

For release, tag, handoff, and development workflow troubleshooting, see `docs/developer-handbook.zh-CN.md`.

## Install and repair entrypoint

Use the Latest Release bootstrap entrypoint:

```bash
curl -fsSL https://github.com/Awenforever/CoDeepSeedeX/releases/latest/download/bootstrap.sh | bash
```


### Release tag fallback

When the Latest Release asset path is unavailable, use the resolved release tag fallback. Replace the tag below with the exact release you intend to install:

```bash
tag="v0.3.8-alpha"
curl -fsSL https://github.com/Awenforever/CoDeepSeedeX/raw/refs/tags/${tag}/bootstrap.sh | bash
```

## Maintainer documentation

Maintainer notes are kept in `docs/developer-handbook.md`. The Chinese mirror is `docs/developer-handbook.zh-CN.md`. Detailed long-term records are in `docs/development-log.md`.

## Codex entrypoint, PATH, and Node.js

If `codex --profile cox` reports a configuration load error or runs the system Codex directly, first check the entrypoints:

```bash
command -v node
command -v codex
command -v cox
codex --version
cox --version
```

A healthy CodeXchange install should resolve `cox` to `~/.local/bin/cox` and, when the wrapper is enabled, `codex` to `~/.local/bin/codex`. If the current shell still resolves `/usr/local/bin/codex`, open a new terminal or put `~/.local/bin` before system paths. CodeXchange detects missing Node.js and prints a targeted diagnostic, but it does not install or patch Node/Codex itself.
