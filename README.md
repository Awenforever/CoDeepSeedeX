# CodeXchange

[中文说明](README.zh-CN.md) | English

<!-- COX_LOGO_START -->
<p align="center">
  <img src="docs/logo.png" alt="CodeXchange logo" width="220">
</p>
<!-- COX_LOGO_END -->

CodeXchange is a local OpenAI Responses-compatible provider exchange for running Codex across managed and custom model API providers. It keeps the normal `codex` CLI, exposes the `cox` command for setup, status, upgrade, provider diagnostics, model routing, tool routing, pricing, and WeClaw integration, and treats DeepSeek as one provider rather than the product boundary.

## Requirements

Install Node.js and OpenAI Codex CLI first, then make sure `node` and `codex` are on your `PATH`.

```bash
node --version
codex --version
```

If Codex CLI is not installed yet:

```bash
npm install -g @openai/codex
```

## Install

Default channel, using the GitHub Latest Release asset:

```bash
curl -fsSL https://github.com/Awenforever/CoDeepSeedeX/releases/latest/download/bootstrap.sh | bash
```

Pinned current Latest Release tag (`v0.4.7-alpha`):

```bash
curl -fsSL https://github.com/Awenforever/CoDeepSeedeX/releases/download/v0.4.7-alpha/bootstrap.sh | bash -s -- --install-ref v0.4.7-alpha
```

Fallback downloader for unstable GitHub Release assets, raw GitHub, or CDN routing:

```bash
tag="v0.4.7-alpha"
tmp="$(mktemp -d)"
bs="$tmp/bootstrap.sh"
(
  curl -fL --retry 5 --retry-all-errors --retry-delay 3 "https://github.com/Awenforever/CoDeepSeedeX/releases/download/${tag}/bootstrap.sh" -o "$bs" ||
  curl -fL --retry 5 --retry-all-errors --retry-delay 3 "https://github.com/Awenforever/CoDeepSeedeX/raw/refs/tags/${tag}/bootstrap.sh" -o "$bs" ||
  curl -fL --retry 5 --retry-all-errors --retry-delay 3 "https://raw.githubusercontent.com/Awenforever/CoDeepSeedeX/${tag}/bootstrap.sh" -o "$bs" ||
  curl -fL --retry 5 --retry-all-errors --retry-delay 3 "https://cdn.jsdelivr.net/gh/Awenforever/CoDeepSeedeX@${tag}/bootstrap.sh" -o "$bs" ||
  curl -fL --retry 5 --retry-all-errors --retry-delay 3 "https://fastly.jsdelivr.net/gh/Awenforever/CoDeepSeedeX@${tag}/bootstrap.sh" -o "$bs"
) && bash "$bs" --install-ref "$tag"
```

The installer places CodeXchange under `~/.local/share/codexchange`, creates the `cox` command, creates the primary Codex profile `cox`, and can install a narrow `codex` wrapper for CodeXchange-managed profiles and provider-backed profiles. It also writes shell startup snippets so new terminals prefer `~/.local/bin/cox` and `~/.local/bin/codex`.

## Verify

```bash
cox --version
cox status
cox status thinking
```

Expected version output has two lines:

```text
public version: v0.x.y-alpha | <public-release-commit>
internal version: p2.x-topic | <internal-commit>
```

Start Codex through the managed profiles:

```bash
codex --profile cox
```

## Configure model API

Use the guided menu when you are not sure which provider or option to configure:

```bash
cox config wizard
```

Show saved settings without printing secret values:

```bash
cox config show
```

Configure the model provider used by Codex itself:

```bash
cox config set-model --provider deepseek
cox config set-model --provider kimi
cox config set-model --provider zhipu
cox config set-model --provider zhipu-coding
cox config set-model --provider zai
cox config set-model --provider zai-coding
cox config set-model --provider qwen-beijing
cox config set-model --provider qwen-singapore
cox config set-model --provider qwen-us
```

Non-interactive form, using a fake key for documentation only:

```bash
cox config set-model --provider deepseek --value sk-fake-deepseek-api-key
```

Custom provider examples:

```bash
cox config set-model provider-model-name --provider custom --base-url https://api.example.com/v1 --skip-validation
cox config set-model provider-model-name --provider custom --base-url https://api.example.com/v1 --value sk-fake-custom-api-key --skip-validation
cox config set-model qwen3-coder-plus --provider custom --base-url https://coding-intl.dashscope.aliyuncs.com/v1 --skip-validation
```

API keys are stored locally in the CodeXchange env file with restrictive file permissions. Interactive commands use a hidden prompt for secret input; the hidden prompt only prevents the key from being printed on screen and is not cryptographic encryption. API keys are passed with `--value` or hidden prompt input, not as a positional argument.

## Optional tool providers

Supported web search providers in the guided flow are SerpAPI, Tavily, Exa, and Firecrawl.

```bash
cox config set-web-search-api-key --provider serpapi
cox config set-web-search-api-key --provider tavily
cox config set-web-search-api-key --provider exa
cox config set-web-search-api-key --provider firecrawl
```

Non-interactive web search example, using a fake key for documentation only:

```bash
cox config set-web-search-api-key --provider serpapi --value fake-serpapi-api-key --skip-validation
```

Supported image generation providers include ZhipuAI/BigModel, Z.AI, Qwen Image/DashScope, Stability AI, and fal.ai.

```bash
cox config set-image-api-key --provider zhipu
cox config set-image-api-key --provider zai
cox config set-image-api-key --provider qwen_image
cox config set-image-api-key --provider stability
cox config set-image-api-key --provider fal
```

Non-interactive image provider example, using a fake key for documentation only:

```bash
cox config set-image-api-key --provider zhipu --value fake-zhipu-api-key --skip-validation
```

Qwen Image regional provider names are documented explicitly for validation and troubleshooting:

```text
qwen_image_beijing    # Beijing
qwen_image_singapore  # Singapore
qwen_image_us         # US Virginia
Germany Frankfurt     # documented unsupported region reference
```

Provider diagnostics:

```bash
cox doctor providers --json
cox doctor providers --live --allow-spend --json
```

Live provider diagnostics may call external APIs and may consume quota or credits.

## Run and stop proxy

```bash
cox start
cox start thinking
cox status
cox status thinking
cox stop
cox stop thinking
```

`cox` is the primary managed CodeXchange route. Provider-backed profiles such as `deepseek`, `qwen-us`, or custom provider ids are independent Codex profiles resolved through the generic provider routing contract.

## Pricing and cost metadata

Show the current local pricing table and metadata:

```bash
cox pricing show --json
```

Fetch and validate DeepSeek official pricing HTML without writing cache:

```bash
cox pricing refresh --json
```

Fetch and persist the validated official pricing cache:

```bash
cox pricing refresh --write-cache --json
```

Cost estimates must keep their pricing source visible. Bundled fallback prices are labelled separately from a freshly fetched `official_docs_html` cache.

## Upgrade

Default upgrade path follows the GitHub Latest Release:

```bash
cox upgrade
cox upgrade --dry-run
```

Future alpha/pre-release upgrade path follows the newest non-draft GitHub pre-release, when one exists:

```bash
cox upgrade --alpha
```

Explicit tag or ref:

```bash
cox upgrade --tag v0.4.7-alpha
```

Do not combine `--alpha` and `--tag`.

Managed tokenizer resources are ignored by the upgrade dirty-worktree guard, so a clean release install can be upgraded without passing `--allow-dirty`.

Older installations that do not have `cox upgrade` should rerun the installer. Source-archive/non-git installs on versions with the p2.14a9 fallback can also use `cox upgrade --alpha`; the command reruns the release bootstrap installer with the resolved `--install-ref`.

## Uninstall

The product-level uninstall entrypoint is the installer, not `cox uninstall`.

Remove CodeXchange integration while preserving configuration files and the install directory:

```bash
bash ~/.local/share/codexchange/scripts/install.sh --uninstall
```

Remove the integration and also remove the CodeXchange install directory, env file, and install manifest:

```bash
bash ~/.local/share/codexchange/scripts/install.sh --uninstall --remove-files
```

Uninstall scope:

```text
- removes the managed Codex profiles `deepseek` and `cox`
- removes the CodeXchange-managed `codex` wrapper and restores the previous `codex` command backup when available
- removes the `cox` wrapper installed by CodeXchange
- with `--remove-files`, also removes `~/.local/share/codexchange`, the CodeXchange env file, and the install manifest
```

The uninstaller must not delete unrelated user files or non-CodeXchange configuration.

## WeClaw integration

CodeXchange can serve as the DeepSeek/Codex runtime backend for `weclaw_dev`.

If WeClaw integration is used with the current CodeXchange public Release, WeClaw must be at least:

```text
weclaw_dev >= v0.1.9-alpha
```

Machine-readable status contract:

```bash
cox status thinking --weclaw-json
```

Important fields exposed for WeClaw include:

```text
context_window.used_tokens
context_window.latest_upstream_prompt_tokens
context_window.limit_explanation
tokens.attribution
pricing.source_trust
pricing.official_reference_url
pricing.official_source
cost.pricing_source_kind
cost.official_pricing_available
diagnostics.degraded_fields
semantic_compaction
```

`context_window.used_tokens` is an explicitly labelled estimate from the latest upstream provider `prompt_tokens` when available. It is not Codex internal context-window usage, and it must not be replaced with cumulative session totals.

## Security and data boundaries

CodeXchange stores local configuration under your user account and modifies user-level Codex profile files only when installing, upgrading, refreshing profiles, or changing configuration.

Do not put real API keys directly in shell history unless you intentionally accept that risk. Prefer hidden prompts or a secure secret workflow.

## Documentation

User entry points:

```text
README.md
README.zh-CN.md
```

Maintainer entry points:

```text
docs/developer-handbook.md
docs/developer-handbook.zh-CN.md
docs/development-log.md
```

Historical release notes and long development records belong in `docs/development-log.md`, not in this README.

## WeClaw status telemetry

CodeXchange exposes structured WeClaw status telemetry through `cox status thinking --weclaw-json`.

Current WeClaw-facing fields include:
- token usage from provider-reported usage totals,
- local DeepSeek profile-tokenizer estimates for Details,
- sanitized prompt segmentation for `user`, `user_history`, `tool_output`, `environment`, and related buckets,
- CNY-first Pricing/Cost fields based on DeepSeek's Chinese official pricing page,
- per-turn cost ledger semantics so mixed model or route sessions are not recalculated using the current active model price,
- token-first context-window display using the full managed `model_context_window_tokens`, with the auto-compact threshold exposed separately;
- token-only Compact and Trim runtime progress through `runtime_payload_guard`;
- redacted Compact prompt fingerprints and dry-run material classification for compaction auditability;
- Compact audit metadata through runtime/WeClaw status and CLI fallback surfaces;
- Compact audit dry-run metadata for skipped compaction reports without model calls or payload mutation;
- HTTP end-to-end regression coverage for Compact audit visibility through WeClaw status;
- token-first TRIM dry-run with type enum, first-image protection, and static-block protection;
- type-aware production TRIM for low-risk text payloads with redacted status metadata;
- image semantic envelopes for non-protected image payloads with first-image preservation;
- GitHub source-backed Codex native local Compact prompt alignment, with remote `responses/compact` explicitly treated as provider-gated and not claimed for the third-party DeepSeek route.

WeClaw clients should consume the structured JSON fields and should not recalculate token categories, currency conversion, or session cost locally.

### v0.4.7-alpha

The current public release improves custom OpenAI-compatible provider support, fixes custom reasoning-only responses, and keeps image payloads from being compacted or trimmed.


### Provider-backed Codex profiles

```bash
cox provider add --name ustc --base-url https://api.llm.ustc.edu.cn/v1 --model deepseek-v4-flash-ascend --value sk-your-key --skip-validation --use
codex --profile ustc
```

When adding a custom provider in the guided wizard, the provider name becomes the local provider id/profile id after slug normalization. CodeXchange does not modify Codex's native `/model` list; use `cox provider add-model/use` or a provider-backed profile for model switching.

Codex TUI `/model` integration is not claimed here; use `cox provider add-model/use` or provider-backed profiles until Codex behavior proves profile-level model catalogs are honored.
