# CoDeepSeedeX Developer Handbook

This is the primary developer handbook. It is written in English because it is the main startup context for future AI-assisted development conversations. The Chinese mirror is `docs/developer-handbook.zh-CN.md`.

This handbook is not a historical archive. It keeps the current operating model, project map, release rules, high-priority lessons, and a concise summary of the current major development line. Detailed long-term records belong in `docs/development-log.md`.

## 1. Documentation architecture

Active user-facing documents:

- `README.md`: English user entry.
- `README.zh-CN.md`: Chinese user entry.
- `TROUBLESHOOTING.md`: user-facing troubleshooting.

Active maintainer documents:

- `docs/developer-handbook.md`: English primary handbook and AI startup context.
- `docs/developer-handbook.zh-CN.md`: Chinese mirror for the human maintainer.
- `docs/development-log.md`: detailed long-term development log, read only when historical trace-back is needed.

Retired document families must not be reintroduced as active documents: `OPERATIONS.md`, `docs/install.*.md`, `docs/usage.*.md`, `docs/upgrade.*.md`, `docs/security.*.md`, `docs/troubleshooting.*.md`, `docs/handoff-for-developers.*.md`, `docs/custom_api_handoff.md`, and per-release note files under `docs/`.

If documentation structure changes, tests must be updated to the new contract. Do not keep ghost documents only to satisfy stale tests.

## 2. Project identity and current state

- Local project path: `~/projects/deepseek-responses-proxy`
- GitHub repository: `Awenforever/CoDeepSeedeX`
- Main branch: `master`
- Current public release: `v0.3.7-alpha`
- Public release commit: `466706f`
- Release internal tag: `p2.9a18-release-v0.3.7-alpha`
- Current documentation baseline before p2.9a21: `p2.9a20-docs-consolidation = b160525`
- Older public tags must not move:
  - `v0.3.6-alpha = 7fd8fb6`
  - `v0.3.5-alpha = 53897ad`
- Erroneous plain tag `v0.3.5` must not exist.

After p2.9a21, `master`, `origin/master`, and `p2.9a21-handbook-bilingual-restoration` should point to the same new commit.

## 3. Key file map

- `deepseek_responses_proxy/app.py`: runtime core, Responses-compatible API, DeepSeek bridge, tool bridge, provider dispatch, version metadata, debug trace.
- `deepseek_responses_proxy/cli.py`: `dsproxy` CLI, config, provider setup, post-config proxy refresh, doctor commands, upgrade logic.
- `scripts/install.sh`: installer, installed checkout sync, venv setup, wrappers, Codex profiles, config initialization, local file backup.
- `bootstrap.sh`: one-line bootstrap entrypoint, dependency handling, install.sh acquisition and fallback.
- `tests/`: regression tests, document contract tests, provider and installer tests.
- `README.md` / `README.zh-CN.md`: user instructions.
- `TROUBLESHOOTING.md`: user troubleshooting.
- `docs/development-log.md`: detailed chronological record.

## 4. Version and tag rules

`dsproxy --version` must expose two version sources:

```text
public version: v0.3.x-alpha | <public_release_commit>
internal version: p2.9aN-topic | <internal_commit>
```

For user installations from a public Release tag, the internal version line reports the `p~` tag that was current at the moment that Release tag was created. For a developer checkout running from `master`, the public version line remains the latest published public Release until the next Release, while the internal version line must track the latest internal `p~` tag on `master`.

Public release tags use the `v0.3.x-alpha` form during alpha. Do not create plain `v0.3.x` public tags. Internal development tags use the `p` prefix, such as `p2.9a21-handbook-bilingual-restoration`, and must not create GitHub Releases.

Package versions in `pyproject.toml` use PEP440, for example `0.3.7a0`.

Files that usually need synchronized version edits during release:

- `deepseek_responses_proxy/app.py`
- `pyproject.toml`
- `tests/test_version_metadata.py`
- `tests/test_cli.py`

Each file has its own role. Do not force every version-related file to contain both public and internal tags.

## 5. Release state machine

A release must be treated as a state machine, not as a temporary one-off script.

Required sequence:

1. Read-only audit: branch, HEAD, origin/master, worktree, existing public tags, target public tag, GitHub Release state, version string distribution, test file existence.
2. Synchronize version metadata.
3. Run static checks and focused tests.
4. Run full tests.
5. Commit release preparation.
6. Push work branch.
7. Push internal tag.
8. Fast-forward master.
9. Push master.
10. Push public release tag.
11. Create GitHub Release and upload `bootstrap.sh` and `install.sh`.
12. Verify release assets, tags, old tags, and absence of erroneous plain tags.
13. Refresh local runtime with `--install-ref master`.
14. Verify `dsproxy --version` and `codex --profile deepseek-thinking app-server --help`.

Push over HTTPS by default. Do not rely on SSH port 22. Every network step must have a timeout.

GitHub Release notes must not repeat the release title. The body should start with `Highlights:`, `Changes:`, `Fixes:`, `Install:`, or `Validation:`.

## 6. Release lessons learned

These are high-priority lessons that must remain in the handbook, not only in the long development log.

### v0.3.7-alpha release mistakes

1. Do not hard-code runtime version paths. The runtime file is `deepseek_responses_proxy/app.py`, not root-level `app.py`.
2. Do not assume only one Python file contains version metadata. Runtime code and tests can both contain version strings.
3. Version files have separate roles: runtime public/internal version, package PEP440 version, version consistency tests, and CLI output tests. Runtime version metadata is dual-track: public Release runtime is fixed at the public `v~` tag and the internal `p~` tag that existed when that Release was cut; developer checkout runtime on `master` keeps the same current public `v~` until the next Release, but its internal `p~` version must advance with the latest `master` internal tag. Therefore, after post-Release documentation or maintenance commits, the developer machine may correctly show a newer internal `p~` than users running the latest public Release.
4. Updating `pyproject.toml` requires updating package-version assertions in tests.
5. Focused test lists must filter nonexistent test files before invoking pytest.
6. Release scripts must be idempotent and resume-aware.
7. Git push must use HTTPS and timeout controls to avoid SSH 22 stalls.
8. Public release tags should be pushed late to avoid half-published states.
9. `gh release view` must not rely on fields unsupported by the installed `gh` version, such as `isLatest`.
10. Release notes must not duplicate the GitHub Release title.
11. Documentation refactors must update the test contract. Do not keep ghost documents just because stale tests read them.
12. The developer handbook must not become a long archive. Keep it as AI startup context and send detailed chronology to `docs/development-log.md`.

## 7. Installer and local file ownership rules

The installer must back up local files before overwriting them. Important paths:

- `~/.config/deepseek-responses-proxy/env`
- `~/.local/bin/dsproxy`
- `~/.local/bin/codex`
- `~/.codex/config.toml`
- dirty and untracked files inside the installed checkout

Unknown user-owned `codex` or `dsproxy` files under `~/.local/bin` must not be silently overwritten. Known CoDeepSeedeX-managed wrappers may be backed up and refreshed.

If a user-modified installed checkout blocks upgrade, back up dirty changes as a patch and untracked files as an archive, then sync to the requested release ref.

## 8. Provider and custom API handoff

Provider-related behavior must remain consistent across runtime, CLI, installer, README, and tests.

Key paths:

- `deepseek_responses_proxy/app.py`
- `deepseek_responses_proxy/cli.py`
- `scripts/install.sh`
- `README.md`
- `README.zh-CN.md`
- `TROUBLESHOOTING.md`

Web search validation may perform a live low-result query and can consume quota.

Image validation is often non-generating and does not prove real image generation works. Real image generation checks require explicit consent:

```bash
dsproxy doctor providers --live --allow-spend
```

Do not add a separate `dsproxy config test-provider --kind web-search|image --provider <name>` command unless explicitly requested.

Zhipu and Z.AI image endpoints must remain separated. Do not mix domestic ZhipuAI, international Z.AI, GLM, and CogView assumptions.

Provider diagnostics must not treat a generic image API key as proof that every image provider is configured. `DEEPSEEK_PROXY_IMAGE_API_KEY` is a compatibility key for the currently selected `DEEPSEEK_PROXY_IMAGE_PROVIDER`; provider-specific variables such as `ZAI_API_KEY`, `DASHSCOPE_API_KEY`, `STABILITY_API_KEY`, and `FAL_KEY` remain authoritative for unselected providers.

Qwen/DashScope provider diagnostics must respect regional image endpoints. `DEEPSEEK_PROXY_IMAGE_BASE_URL` and `DASHSCOPE_IMAGE_ENDPOINT` must override the Beijing default during both non-generation validation and live image probe payload construction.

## 9. VM GitHub proxy playbook

When a VMware NAT VM cannot reliably reach GitHub, do not guess. Audit the route, DNS, curl, git, proxy listener, and Windows host listener.

Known working pattern for the affected VM:

```text
VM -> 192.168.231.1:7896 -> Windows portproxy -> 127.0.0.1:7892 -> Jilianyun
```

GitHub-specific proxy settings are acceptable inside the VM. Do not treat jsDelivr failures as blocking when GitHub Release assets and `git ls-remote` are stable.

## 10. Documentation maintenance rules

The handbook is an AI startup pack:

- Keep stable rules, current state, project map, release rules, testing rules, and high-priority lessons.
- Keep only one current major-line summary in detail.
- Move older detailed chronology to `docs/development-log.md`.
- Keep English as the primary handbook.
- Maintain the Chinese mirror for the human maintainer.
- Do not reintroduce fragmented handoff, operations, install, usage, upgrade, security, troubleshooting, or release-note documents under `docs/`.
- If a test still reads a retired path, update the test contract instead of preserving a ghost document.

## 11. Current major-line summary: p2.9 / v0.3.7-alpha

p2.9 covered:

- Provider endpoint cleanup and validation semantics.
- Zhipu/Z.AI image provider separation.
- `dsproxy doctor providers` live probe matrix.
- Installer repair for affected machines and same-version rerun.
- Installed checkout sync to selected release refs.
- Local bin ownership guards.
- VM GitHub proxy documentation.
- `v0.3.7-alpha` release.
- SerpAPI live web search probe passed with `dsproxy doctor providers --kind web-search --provider serpapi --live --allow-spend`.
- Zhipu live image generation probe passed with `dsproxy doctor providers --kind image --provider zhipu --live --allow-spend`.
- Release lessons written into maintainer docs.
- p2.9a20 documentation consolidation.
- p2.9a21 restoration of English-primary developer handbook and Chinese mirror.

Detailed chronology belongs in `docs/development-log.md`.

## 12. New conversation startup checklist

At the start of a new development conversation, run a read-only audit:

```bash
git branch --show-current
git rev-parse --short HEAD
git rev-parse --short origin/master
git status --short
git rev-parse --short v0.3.7-alpha^{}
git rev-parse --short p2.9a20-docs-consolidation^{}
```

Then read `docs/developer-handbook.md`. Read `docs/development-log.md` only if historical trace-back is needed.

## 13. Install and fallback entrypoints

Latest Release bootstrap:

```bash
curl -fsSL https://github.com/Awenforever/CoDeepSeedeX/releases/latest/download/bootstrap.sh | bash
```

Resolved tag fallback:

```bash
tag="v0.3.7-alpha"
curl -fsSL https://github.com/Awenforever/CoDeepSeedeX/raw/refs/tags/${tag}/bootstrap.sh | bash
```

## Provider bridge terminology contract

The provider handoff section must explicitly preserve these bridge terms because tests and future maintainers use them as stable anchors:

- Web search tool bridge
- Image generation tool bridge

The Web search tool bridge may perform live provider checks and can consume quota.

The Image generation tool bridge can perform non-generating validation by default. Real image generation must be explicitly requested through:

```bash
dsproxy doctor providers --live --allow-spend
```

## p2.9a22 runtime version metadata policy

`gh release view --json` does not support the `isLatest` field. This is a command schema limitation, not an installed GitHub CLI version issue. Release checks must use compatible fields such as `tagName`, `name`, `url`, `publishedAt`, `isDraft`, `isPrerelease`, `targetCommitish`, and `assets`. If Latest status must be checked, use a separate compatible method instead of `gh release view --json isLatest`.

Runtime version metadata follows a dual-track policy. User installations from a public Release tag report the public `v~` tag and the internal `p~` tag that existed when that Release tag was created. Developer checkout runtime on `master` keeps the latest published public `v~` until the next public Release, but its internal `p~` version must advance with the latest internal tag on `master`. Therefore, after a public Release, documentation or maintenance commits can correctly make the developer machine show a newer internal `p~` than the latest public Release used by users.

## p2.9a23 script scope safety note

When generating shell commands that embed a Python heredoc, shell variables such as `ts`, `out`, or other Bash locals are not automatically available inside Python. Either pass them explicitly through environment variables, for example `UPDATE_TS="$ts" python3 - <<'PY...'`, or generate the value inside Python, for example `datetime.datetime.now().strftime(...)`. Never reference a shell-only variable directly inside the Python heredoc. This exact mistake caused `NameError: name 'ts' is not defined` in the development-entrypoint wrapper repair script before any intended wrapper rewrite happened.

For scripts that modify real HOME paths, keep the fail-before-write pattern: complete all variable setup inside the executing language, validate preconditions, create backups, and only then write the target file.

## p2.9a24 helper signature safety note

Generated Python helper functions inside shell-driven commands must have signatures that cover every later call site. If a helper is later called as `run(..., env=sanitized)`, then the helper must be defined with `env=None` and must pass it through to `subprocess.run`. The same applies to other keyword parameters such as `timeout`, `check`, or `allow_fail`. This exact mistake caused `TypeError: run() got an unexpected keyword argument 'env'` in a read-only mainline resume audit.

Before giving the user a generated command, statically scan the command for helper definitions and call sites. Check that every keyword argument used later is accepted by the helper signature. For long commands, prefer defining helpers with the superset signature used across the script.

### Qwen/DashScope regional image live matrix

p2.9a30-qwen-region-live-matrix-doc-sync records the current Qwen Image regional live-probe result:

- Beijing: passed with `qwen-image-2.0-pro`, HTTP 200, image evidence present.
- Singapore: passed with `qwen-image-2.0-pro`, HTTP 200, image evidence present.
- US Virginia: regional endpoint override works, but `qwen-image-2.0-pro` and `qwen-image-2.0-pro-2026-03-03` return `Model not exist`.
- Germany Frankfurt: regional workspace endpoint override works, but `qwen-image-2.0-pro` returns `Model not exist`.

Do not interpret the US/Germany result as a generic DashScope failure. It means the tested Qwen Image model is not available on those endpoints. If US/Germany image generation is required, test Wan image/text-to-image as a separate provider mode instead of mixing it into `qwen_image`.

### p2.9a34 Brave provider surface removal

Brave Search is no longer advertised or guided as a web search provider because API key creation requires a paid subscription and there is no free live-probe path. Remove it from README examples, guided/public configuration surfaces, `doctor providers` default matrix, and new-user configuration docs. Keep low-level runtime compatibility separate from the public provider catalog unless the maintainer explicitly asks to delete it.

### p2.9a37 web search live matrix

p2.9a37-web-search-live-matrix-doc-sync records the current web search provider live-probe status:

- SerpAPI: configured as the existing primary web search path.
- Tavily: live probe passed, endpoint `https://api.tavily.com/search`, HTTP 200, `functional_validation=performed`.
- Exa: live probe passed, endpoint `https://api.exa.ai/search`, HTTP 200, `functional_validation=performed`.
- Firecrawl: live probe passed, endpoint `https://api.firecrawl.dev/v2/search`, HTTP 200, `functional_validation=performed`.
- Brave Search: abandoned for the public configuration surface because API key creation requires a paid subscription and there is no free live-probe path.

Current public/guided web search providers are SerpAPI, Tavily, Exa, and Firecrawl. Do not reintroduce Brave into README, config wizard choices, or `doctor providers` default matrices unless the maintainer explicitly reverses this decision.

### p2.9a38 image provider live matrix

p2.9a38-image-provider-live-matrix-doc-sync records the current image provider live-probe status:

- Qwen Image / Beijing: live probe passed with `qwen-image-2.0-pro`, HTTP 200, image evidence present.
- Qwen Image / Singapore: live probe passed with `qwen-image-2.0-pro`, HTTP 200, image evidence present.
- Qwen Image / US Virginia: regional endpoint override works, but `qwen-image-2.0-pro` and `qwen-image-2.0-pro-2026-03-03` returned `Model not exist`.
- Qwen Image / Germany Frankfurt: regional workspace endpoint override works, but `qwen-image-2.0-pro` returned `Model not exist`.
- Stability AI: official API use is allowed in principle, but the current WSL/CLI live probe is blocked at the Cloudflare layer with Error 1010 `browser_signature_banned`. Do not bypass or retry aggressively. Use official support, allowlist, or another sanctioned integration path.
- fal.ai: provider endpoint and account were reached, but live generation failed because the account balance was exhausted. Retest after top-up.

Interpretation: Qwen Image is validated for Beijing and Singapore. US Virginia and Germany are model-availability failures for the tested Qwen Image models, not endpoint override failures. Stability is an access-layer/WAF block, not a confirmed API/auth failure. fal.ai is an account-balance failure, not a code or auth-path failure.

### p2.9a39 model API live matrix

p2.9a39-model-api-live-matrix-doc-sync records the current model API verification matrix.

Current model API status:

- DeepSeek: existing primary path and release baseline.
- Kimi / Moonshot: endpoint reachable at `https://api.moonshot.ai/v1/models`, but the provided key returned HTTP 401 `Invalid Authentication`. This is not a confirmed code-path failure. Mark it as endpoint reachable but not verified until a valid Moonshot key is available.
- GLM / Zhipu / Z.AI: verified at `/models` level.
  - Domestic BigModel general endpoint passed: `https://open.bigmodel.cn/api/paas/v4`.
  - Domestic BigModel Coding Plan endpoint passed: `https://open.bigmodel.cn/api/coding/paas/v4`.
  - Z.AI general endpoint passed: `https://api.z.ai/api/paas/v4`.
  - Z.AI Coding Plan endpoint passed: `https://api.z.ai/api/coding/paas/v4`.
  - Both the domestic BigModel key and the Z.AI key passed against all four endpoints in the current matrix.
- Qwen / DashScope pay-as-you-go: verified at `/models` level.
  - Beijing passed: `https://dashscope.aliyuncs.com/compatible-mode/v1`, model `qwen-plus`.
  - Singapore passed: `https://dashscope-intl.aliyuncs.com/compatible-mode/v1`, model `qwen-plus`.
  - US Virginia passed: `https://dashscope-us.aliyuncs.com/compatible-mode/v1`, model `qwen-plus-us`.
- Qwen Coding Plan and Token Plan: not script-tested because the official usage constraints distinguish these from ordinary automation-style API probes. Treat them as separate guided configuration paths that require tool-path validation rather than generic script live-probe validation.
- Custom provider: verified as a mechanism through the GLM/Zhipu/Z.AI matrix and the Qwen pay-as-you-go matrix.

Provider documentation and setup wording must use these states instead of a binary supported/unsupported label:

- `verified`: live `/models` validation passed.
- `endpoint reachable but auth failed`: endpoint and code path reached, but supplied credentials failed.
- `implemented but not yet verified`: implementation exists but no successful live validation yet.
- `not script-tested`: official usage constraints or workflow constraints prevent ordinary script probes.
- `abandoned`: intentionally removed from public/guided surfaces.

Do not label untested or auth-failed model providers as unsupported. After the model API matrix is complete, open a dedicated architecture branch to assess which CoDeepSeedeX layers are reusable and which are DeepSeek-specific. The likely branch is `work/p2.10-anycodex-provider-architecture-audit`. That assessment must cover provider adapters, reasoning/thinking fields such as `reasoning_content`, stream event normalization, model catalog metadata, Codex `/model` display, and the broader goal of evolving CoDeepSeedeX into a more general AnyCodex-style provider architecture.

### p2.9a40 config guide provider surface repair

p2.9a40-config-guide-provider-surface-repair updates the public configuration surface after the web search, image provider, and model API matrices:

- README and README.zh-CN must not list Brave Search as a configurable public/guided web search provider.
- Installer and configuration guidance must present model providers by explicit site and plan, not by ambiguous `glm` or `qwen` shortcuts.
- Zhipu / BigModel domestic general, Zhipu / BigModel domestic Coding Plan, Z.AI international general, and Z.AI international Coding Plan must be shown separately.
- Qwen / DashScope pay-as-you-go regions must be shown separately as Beijing, Singapore, and US Virginia.
- Qwen Coding Plan and Token Plan remain separate guided paths. They should not be treated as ordinary script-probed pay-as-you-go endpoints.
- The old `glm` and `qwen` aliases remain internal canonicalization/backward-config helpers, but public CLI choices and recommended documentation commands must use explicit site and plan provider names.

### p2.9a41 post-p2.9a40 handoff sync

p2.9a41-post-p2.9a40-handoff-sync records the state after the provider-surface repair line.

Current repository state after p2.9a40:

- `master`, `origin/master`, `work/p2.9a40-config-guide-provider-surface-repair`, and internal tag `p2.9a40-config-guide-provider-surface-repair` point to `cd8e4d9`.
- Public release tag `v0.3.7-alpha` remains at `466706f` and must not be moved unless the maintainer explicitly starts a new public release.
- Erroneous plain public tag `v0.3.5` remains absent.
- p2.9a40 passed `git diff --check`, `bash -n bootstrap.sh`, `bash -n scripts/install.sh`, focused provider/config tests, broader provider/config tests, and full tests with `363 passed`.

Provider-surface state after p2.9a40:

- Brave Search has been removed from README, README.zh-CN, installer guided configuration, and installer validation choices.
- Public model API setup uses explicit site and plan provider names:
  - `zhipu`
  - `zhipu-coding`
  - `zai`
  - `zai-coding`
  - `qwen-beijing`
  - `qwen-singapore`
  - `qwen-us`
- The ambiguous `glm` and `qwen` shortcuts are not recommended public commands. They may remain only as internal canonicalization or backward-config helpers.
- p2.10a6 repaired `scripts/install.sh` so guided installer model API setup uses the same explicit provider surface and added `tests/test_installer_model_provider_surface.py` to prevent regression.
- `p2.10a7-doc-sync` synchronized README, developer handbook, and development-log records for the p2.10a6 installer surface repair.
- p2.10a7 synchronized README, developer handbook, and development-log records for the p2.10a6 installer surface repair.
- README and tests should continue distinguishing provider states such as verified, endpoint reachable but auth failed, implemented but not yet verified, not script-tested, and abandoned.

Next development direction:

- Start the next major design line as `work/p2.10-anycodex-provider-architecture-audit`.
- The audit must not guess from memory. It should start with a read-only audit of `app.py`, `cli.py`, runtime config loading, stream conversion, model catalog, provider config, tool bridge, tests, and docs.
- The goal is to assess whether CoDeepSeedeX should be generalized into an AnyCodex-style provider architecture.
- Key DeepSeek-specific areas to inspect include `reasoning_content`, reasoning or thinking event handling, thinking profile behavior, Responses-to-chat conversion, stream event normalization, tool-call repair, model catalog assumptions, `/model` UI expectations, and Codex profile wrapper behavior.
- Tool replacement should be treated as a broader layer: web search, image generation, and future third-party tools should be able to transparently replace native Codex tools that are unreachable or unavailable, rather than being a SerpAPI-only bridge.

### p2.10a2 config refresh and effort UX rule

Successful local config writes that change API keys, model selection, or reasoning effort must apply a CoDeepSeedeX-only post-config hook. The hook may refresh already-running local stable/thinking `dsproxy` processes and report `all updates applied`; it must not start proxies that were not already running. WeClaw resume automation is deliberately out of scope for CoDeepSeedeX changes and must be handled in the WeClaw development line.

DeepSeek-facing effort UX should not recommend `medium`. `low` and `medium` may remain accepted compatibility inputs from Codex or old commands, but CoDeepSeedeX stores and forwards them as `high` for the DeepSeek proxy path. User-facing examples should prefer `high`, `xhigh`, or `max` according to the intended behavior.

### p2.10a3 provider validation and region status rule

Non-generation provider probes may intentionally send an empty or metadata-only payload. When such a probe receives an HTTP 200 response that still contains a structured provider error body, and no authentication error is detected, CoDeepSeedeX treats it as accepted probe evidence rather than a generic validation failure. This classification is only for non-generation validation and must not be described as a successful real image generation test.

Qwen Image region support must be explicit. Beijing and Singapore are user-selectable Qwen Image providers. US Virginia and Germany Frankfurt remain listed so users can see the region decision, but they must report a model-unavailable status for qwen-image-2.0-pro instead of failing as if CoDeepSeedeX were broken.

### p2.10a4 config menu model-provider UX

`dsproxy config set-model` is now the primary model API configuration entrypoint. It can set the model provider, upstream model, and optional API key in one command. `dsproxy config set-api-key` remains as a compatibility alias for existing scripts, but new docs and installer guidance should point users to `set-model`.

Rules:
- Do not remove `set-api-key` until a later explicit compatibility-break decision.
- Keep `set-model <model>` working for the old DeepSeek model-only flow.
- Use `set-model <model> --provider custom --base-url <url>` for custom OpenAI-compatible providers.
- Keep README, README.zh-CN, installer guidance, CLI help, and tests synchronized when provider setup commands change.

### p2.10a5 post-config UX consistency

After changing model API setup to `dsproxy config set-model`, the public configuration surface must remain internally consistent:
- `configuration_status.commands.model_api` must list the same public provider families as the supported model provider list, including coding-plan and regional Qwen entries.
- README and README.zh-CN must not recommend `dsproxy config set-api-key --provider custom` for new custom model API setup.
- Custom OpenAI-compatible model API examples must use `dsproxy config set-model <model> --provider custom --base-url <url>`.
- Compatibility mentions of `set-api-key` may remain only when they explicitly describe the legacy alias.

## p2.10a8 alpha upgrade and Codex tab title policy

`dsproxy upgrade` must continue to resolve GitHub Latest Release by default. `dsproxy upgrade --alpha` resolves the newest non-draft GitHub pre-release from the releases list API. This is the maintainer VM validation path: publish a pre-release first, test it with `dsproxy upgrade --alpha` on a VM, then promote the same GitHub Release to Latest only after validation passes.

The Codex wrapper installed by `scripts/install.sh` sets a random terminal tab title for `codex --profile deepseek` and `codex --profile deepseek-thinking`. The title format is `[emoji]CoDeepSeedeX`, using the maintainer-provided emoji candidate list. Keep this in the wrapper rather than proxy startup code, because the wrapper owns the user terminal before it executes the real Codex binary.

## p2.10a10 installer provider selection UI

Guided installer provider menus should prefer arrow-key navigation with Enter confirmation, while retaining numeric and text input as fallback for non-TTY or incompatible terminals. Public provider names must stay explicit by provider family and region. In particular, Qwen / DashScope model and image providers must not collapse back into a single generic `qwen` entry when regional endpoints or availability differ.
