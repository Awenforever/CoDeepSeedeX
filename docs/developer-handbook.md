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

Retired document families must not be reintroduced as active documents: `OPERATIONS.md`, `docs/install.*.md`, `docs/usage.*.md`, `docs/upgrade.*.md`, `docs/security.*.md`, `docs/troubleshooting.*.md`, `docs/handoff-for-developers.*.md`, and `docs/custom_api_handoff.md`. Legacy per-release note fragments under `docs/` stay retired, except the current cumulative Release-note source explicitly maintained for the active public Release, currently `docs/release-notes-v0.3.9-alpha.md`.

If documentation structure changes, tests must be updated to the new contract. Do not keep ghost documents only to satisfy stale tests.

## 2. Project identity and current state

- Local project path: `~/projects/deepseek-responses-proxy`
- GitHub repository: `Awenforever/CoDeepSeedeX`
- Main branch: `master`
- Current public Release: `v0.3.9-alpha`
- Current public Release commit: `80bb0ea`
- GitHub Latest Release: `v0.3.9-alpha`
- GitHub Release title: `CoDeepSeedeX v0.3.9-alpha`
- GitHub Release state: non-draft, non-prerelease, Latest ordinary Release
- GitHub Release flags: `isDraft=false`, `isPrerelease=false`
- Public Release assets: `bootstrap.sh`, `install.sh`
- Current internal development checkpoint: `p2.10a84-token-first-compact-trim-contract` (resolve the exact commit with `git rev-parse --short p2.10a84-token-first-compact-trim-contract^{}`)
- Latest closed documentation sync checkpoint: `p2.10a84-token-first-compact-trim-contract`
- Current public Release note synchronization checkpoint remains `p2.10a83-deepseek-cache-accounting-contract` until `v0.3.9-alpha` is deliberately updated.
- Completed P0 baseline checkpoint: `p2.10a48-weclaw-full-telemetry-contract = 2e0edd0`
- WeClaw status: the current CoDeepSeedeX and WeClaw integration line is closed. The WeClaw side reported no blocking issue after the v0.3.9-alpha Latest validation.
- Release requirement: if WeClaw integration is used, `weclaw_dev` must be at least `v0.1.9-alpha`.
- Public tags that must not move without an explicit Release-update task:
  - `v0.3.9-alpha = 80bb0ea`
  - `v0.3.8-alpha = dfdc629`
  - `v0.3.7-alpha = 466706f`
  - `v0.3.6-alpha = 7fd8fb6`
  - `v0.3.5-alpha = 53897ad`
- Erroneous plain tags `v0.3.5` and `v0.3.9` must not exist.

This handbook is the startup context for new AI-assisted development conversations. It should track current state, stable rules, the active task bus, release rules, and high-value lessons. Detailed timelines belong in `docs/development-log.md`.

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

## 6. Failure-prevention and release lessons

These rules are mandatory development controls. They belong in the handbook because they prevent recurring tool-generated failures.

### 6.1 Avoidable failure classes

1. **Script variable scope.** Shell variables such as `ts`, `out`, and `run_id` do not exist inside Python heredocs unless passed through environment variables. Use one canonical run identifier and read it from `os.environ`.
2. **Source anchors.** Do not patch from memory. When anchors are uncertain, repeated, shifted by a half-applied patch, or embedded in generated shell templates, audit the real source first.
3. **Replacement discipline.** Prefer function-level, section-level, block-level, or AST-based whole replacement. For Python tests and functions, replace the whole `def` by AST line range. For Markdown, replace a whole heading section. For shell templates, replace the whole generated function or heredoc body. Avoid single-line or narrow string anchors except for stable version constants.
4. **Helper function semantics.** Read helper definitions before using them in tests or patch scripts. Do not assume a helper parameter accepts arbitrary text when it expects a function name or structured marker.
5. **Regex boundaries.** Regex patching is acceptable only when the boundary is stable and verified. Tests and functions should normally be replaced as whole blocks.
6. **Pre-test marker checks.** Before pytest, assert that the intended source markers exist and old forbidden markers are gone. This catches half-applied patches before expensive test runs.
7. **Two-phase heavy changes.** For broad installer, wrapper, profile, or Release changes, first patch and test locally. Only after focused and full tests pass should the script commit, tag, push, merge, or rebuild Release assets.
8. **Acceptance criteria must match the user-visible defect.** Do not record a compatibility fallback as a fix when the defect is a visible UI or profile behavior. Example: Plan mode had to write `plan_mode_reasoning_effort = "high"`, not merely map `medium` to `high` inside the proxy.
9. **Integration surfaces are part of every task.** Every development task must explicitly consider install, upgrade, uninstall, rollback, generated wrappers, user config files, Release assets, and VM/user-path validation when the changed behavior can affect them.
10. **Runtime observations outrank assumptions.** For terminal, wrapper, and Codex TUI behavior, validate with isolated runtime probes before patching. This prevented guessing around Windows Terminal title behavior and showed that tab color was not a current wrapper-path feature.
11. **Test environment contamination.** A dirty developer shell can make full tests fail for reasons unrelated to the patch. In p2.10a36, exported variables such as `DEEPSEEK_PROXY_MODEL`, `DEEPSEEK_PROXY_FORCE_MODEL`, `DEEPSEEK_PROXY_IMAGE_PROVIDER`, `DEEPSEEK_PROXY_IMAGE_DOWNLOAD`, and real provider API keys changed default model/provider behavior and caused unrelated full-suite failures. Before treating full-suite failures as patch evidence, record relevant environment overrides, rerun the failing subset and full suite under a sanitized environment, and only then decide whether the patch or the local environment is responsible.
12. **AnyCodeX future-name boundary.** CoDeepSeedeX remains the current project and public product name. AnyCodeX is a future plan name and possible future brand, not a current code, command, tag, branch, installer, wrapper, public-path, or user-facing documentation name. Do not introduce AnyCodeX into user-facing surfaces before an explicit maintainer-approved rename task. Future architecture work may describe the target as AnyCodeX-level generalized provider architecture inside developer-only planning docs.
13. **Full-source-first audit rule.** For source or documentation changes, prefer asking the maintainer to upload complete source files and source documents first. If direct upload is inconvenient, the read-only audit command should copy the full relevant source/document contents into `/tmp` files and list those files for upload. `grep`, `rg`, and narrow snippets may help build a file list, but they must not be the primary basis for patch design. Patch design must be based on actually inspected full files or complete function/module/section context.
### 6.2 Release-specific guardrails

- Do not hard-code runtime version paths. The runtime file is `deepseek_responses_proxy/app.py`.
- Do not assume only one Python file contains version metadata. Runtime code and tests can both contain version strings.
- Version files have separate roles: runtime public/internal version, package PEP440 version, version consistency tests, and CLI output tests.
- Runtime version metadata is dual-track. User installations from a public Release tag report the public `v~` tag and the internal `p~` tag that existed when that Release was cut. Developer checkout runtime on `master` keeps the same public `v~` until the next Release, while internal `p~` advances with the latest internal tag.
- Release scripts must be idempotent and resume-aware.
- Git push must use HTTPS and timeout controls to avoid SSH 22 stalls.
- Public release tags should be pushed late to avoid half-published states.
- `gh release view --json` must not rely on fields unsupported by the installed `gh` version, such as `isLatest`.
- Release notes must not duplicate the GitHub Release title.
- Documentation refactors must update the test contract. Do not keep ghost documents only because stale tests read them.
- The developer handbook must not become a long archive. Keep stable rules here and send chronology to `docs/development-log.md`.

### 6.3 Upgrade and uninstall scope rule

Any development task that can affect an installed user environment must include install, upgrade, and uninstall in the design review. At minimum, check whether the change touches one-line bootstrap, `scripts/install.sh`, `dsproxy upgrade`, generated `dsproxy` or `codex` wrappers, `~/.codex/config.toml`, local env files, manifest-backed rollback, source archive fallback, and Release assets.

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

### 8.1 Provider bridge terminology contract

The provider handoff section must explicitly preserve these bridge terms because tests and future maintainers use them as stable anchors:

- Web search tool bridge
- Image generation tool bridge

The Web search tool bridge may perform live provider checks and can consume quota.

The Image generation tool bridge can perform non-generating validation by default. Real image generation must be explicitly requested through:

```bash
dsproxy doctor providers --live --allow-spend
```

### 8.2 Model configuration command contract

Documentation and tests must preserve the current model configuration command example:

```bash
dsproxy config set-model deepseek-v4-pro
```

Do not restore old hyphenated configuration commands.

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

## 11. Current major-line summary: p2.10 / v0.3.9-alpha

p2.10 spans the `v0.3.8-alpha` line through the closed `v0.3.9-alpha` Latest Release and the subsequent p2.10a81 documentation-state synchronization.

Current verified public Release baseline:

- `v0.3.9-alpha = 80bb0ea`
- `p2.10a80-docs-release-latest = 80bb0ea`
- GitHub Release title: `CoDeepSeedeX v0.3.9-alpha`
- GitHub Release state: non-draft, non-prerelease, Latest ordinary Release
- Release assets: `bootstrap.sh`, `install.sh`
- Erroneous plain tags `v0.3.9` and `v0.3.5` are absent.
- `dsproxy --version` from the p2.10a80 public Release reports `public version: v0.3.9-alpha | 80bb0ea` and `internal version: p2.10a80-docs-release-latest | 80bb0ea`.

Current developer checkpoint:

- `p2.10a81-handbook-current-state-sync` is the active internal documentation/version-metadata checkpoint after this handbook sync.
- Public Release metadata remains anchored to `v0.3.9-alpha = 80bb0ea`; do not move the public tag or GitHub Release for this documentation-only node.
- Developer checkout runtime may report `internal version: p2.10a81-handbook-current-state-sync | <checkpoint commit>` while the public version line remains `v0.3.9-alpha | 80bb0ea`.

User-visible changes since `v0.3.8-alpha`:

- WeClaw integration is backed by a dsproxy-owned telemetry contract. WeClaw can consume profile, model, effort, context-window, usage aggregation, pricing metadata, estimated cost, provider balance, auxiliary model-call accounting, and compaction status through stable CLI and HTTP surfaces.
- `dsproxy status [thinking] --weclaw-json` prefers the runtime `/v1/proxy/weclaw/status` endpoint when the proxy is reachable, and falls back to structured unavailable fields when it is not.
- `dsproxy profile status <profile> --json` and `dsproxy profile set-effort <profile> <effort> --json` provide machine-readable profile and effort state for integration clients.
- Runtime payload guard fields expose Compact and Trim progress as character-level dsproxy runtime behavior. They must not be merged with token-level context-window fields.
- DeepSeek profile-tokenizer accounting is available as local display and drift-analysis data. Provider usage remains billing-authoritative.
- `dsproxy tokenizer sync deepseek --json` and `dsproxy tokenizer status deepseek --json` manage user-machine tokenizer resources.
- Prompt segmentation semantics distinguish latest ordinary `user`, `user_history`, `tool_output`, `environment`, `system`, `developer`, and compaction summary categories.
- Prompt reconciliation now exposes `details_origin_breakdown` so WeClaw Details can display token origins such as user, history, system, environment, tools schema, and protocol overhead instead of a `classified~x/y` subtotal.
- Pricing and cost contracts are CNY-first for DeepSeek V4. The Chinese official pricing page is the primary source, with English USD pricing kept as fallback and future internationalization support.
- Session cost uses the per-turn ledger and must not be recomputed from the currently active model price.
- Reasoning output cost is explicitly unavailable when the provider does not expose separately priced reasoning output.

Release requirement for `v0.3.9-alpha`:

- Requires `weclaw_dev >= v0.1.9-alpha` if WeClaw integration is used.

## 12. New conversation startup checklist

Start with a read-only audit before changing anything:

```bash
git branch --show-current
git rev-parse --short HEAD
git rev-parse --short origin/master
git status --short
git rev-parse --short v0.3.9-alpha^{}
git rev-parse --short p2.10a80-docs-release-latest^{}
git rev-parse --short p2.10a84-token-first-compact-trim-contract^{} || true
git rev-parse --short refs/tags/v0.3.9^{} || true
git rev-parse --short refs/tags/v0.3.5^{} || true
gh release view v0.3.9-alpha --json tagName,name,isDraft,isPrerelease,targetCommitish,assets,publishedAt
gh api repos/Awenforever/CoDeepSeedeX/releases/latest --jq '{tag_name:.tag_name,name:.name,draft:.draft,prerelease:.prerelease,target_commitish:.target_commitish,assets:[.assets[].name]}'
dsproxy --version
```

Expected current public Release baseline:

```text
worktree clean
v0.3.9-alpha=80bb0ea
p2.10a80-docs-release-latest=80bb0ea
current_internal_checkpoint=p2.10a84-token-first-compact-trim-contract
GitHub Latest Release=v0.3.9-alpha
isDraft=false
isPrerelease=false
assets=[bootstrap.sh, install.sh]
public version: v0.3.9-alpha | 80bb0ea
internal version: p2.10a83-deepseek-cache-accounting-contract | <current checkpoint commit>
```

Then read `docs/developer-handbook.md`. Read `docs/development-log.md` only when historical trace-back is needed.

## 13. Install and fallback entrypoints

Latest Release bootstrap:

```bash
curl -fsSL https://github.com/Awenforever/CoDeepSeedeX/releases/latest/download/bootstrap.sh | bash
```

Resolved tag fallback:

```bash
tag="v0.3.9-alpha"
curl -fsSL https://github.com/Awenforever/CoDeepSeedeX/raw/refs/tags/${tag}/bootstrap.sh | bash
```

Pinned Release-asset bootstrap:

```bash
curl -fsSL https://github.com/Awenforever/CoDeepSeedeX/releases/download/v0.3.9-alpha/bootstrap.sh | bash -s -- --install-ref v0.3.9-alpha
```

## 14. Long-term mainline task checklist

This checklist is the durable anti-drift task ledger. It must be updated after every planning decision, major implementation checkpoint, release preparation, or handoff.

| ID | Mainline task | Expected indicator | Current version / anchor | Current status | Last updated | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| P0 | WeClaw full telemetry baseline | WeClaw can consume profile, model, effort, context, usage aggregation, pricing, cost, balance, Details, tokenizer status, and compaction from dsproxy-owned CLI/HTTP contracts. | `v0.3.9-alpha = 80bb0ea` | Closed | 2026-05-19 | WeClaw side reported no blocking issue. VM installation and runtime validation passed after v0.3.9-alpha was promoted to Latest. |
| P0.4 | Token shadow accounting and token-vs-char drift observability | Token-level status, local tokenizer estimates, provider usage, and char-level payload guards remain explicitly separated. | `p2.10a65` to `p2.10a68` | Implemented for DeepSeek profile-tokenizer accounting and prompt segmentation | 2026-05-18 | Provider usage remains billing-authoritative. Local tokenizer accounting is for display and drift analysis. |
| P0.5 | Semantic payload compaction hardening | Dry-run, canary, telemetry, rollback, and forbidden-content rules exist before any mutation of user intent or patch-critical payloads. | Plan captured at `p2.10a52-semantic-payload-compaction-tui-plan` | Planned, not active | 2026-05-18 | Do not implement until a concrete requirement reopens this line. |
| P0.6 | Codex TUI third-party profile command compatibility | Manual compact path evidence remains compatible with ordinary Responses traffic unless future auto-compact evidence proves otherwise. | Evidence captured at `p2.10a53-tui-compact-path-evidence-sync` | Partially closed | 2026-05-18 | Do not add `/responses/compact` without fresh evidence. |
| P1 | AnyCodeX-level generalized provider architecture | Evidence-based adapter and capability plan that preserves existing CoDeepSeedeX public surfaces. | `p2.10a40-generalized-provider-architecture-audit-report` | Planned, not active | 2026-05-18 | AnyCodeX remains a future direction only. |
| P2 | `v0.3.9-alpha` public Latest Release | GitHub Latest Release exists with `prerelease=false`, assets `bootstrap.sh` and `install.sh`, Release notes without duplicate title, and WeClaw minimum version requirement. | `v0.3.9-alpha = 80bb0ea` | Completed | 2026-05-19 | Release notes include `Requires weclaw_dev >= v0.1.9-alpha if WeClaw integration is used.` |
| Process | Full-source-first patch discipline | Patch design is based on uploaded full files or complete copied source/document files, not on grep/rg snippets. | Handbook rule 6.1.13 | Active rule | 2026-05-18 | `grep` and `rg` may identify candidate files only. |

Checklist maintenance rules:

1. Update this table whenever a new plan is accepted, a task closes, or a release/handoff changes the active priority.
2. Do not let inserted tasks silently replace the mainline. Inserted tasks must return to this checklist when they close.
3. Handoff content must include this table or an exact summary of its active rows.
4. A task is not complete until its expected indicator has evidence in logs, tests, tags, release state, or accepted downstream feedback.

## p2.10a64 Pre-release upgrade and uninstall documentation closure

p2.10a64 closes the audit gap found after P0: pre-release upgrade was already covered by `dsproxy upgrade --alpha`, `--tag`, and `--dry-run`, but the full product uninstall path was only exposed by `scripts/install.sh --uninstall` and was not clear enough in README.

Current decision:
- Keep the product-level uninstall entrypoint in the installer.
- Do not add a separate `dsproxy uninstall` command in this node.
- Document ordinary uninstall as `bash ~/.local/share/deepseek-responses-proxy/scripts/install.sh --uninstall`.
- Document full removal as `bash ~/.local/share/deepseek-responses-proxy/scripts/install.sh --uninstall --remove-files`.
- Explicitly document that uninstall removes managed Codex profiles, the CoDeepSeedeX codex wrapper, the dsproxy wrapper, and optionally the install directory, env file, and install manifest.
- Explicitly document that unrelated user files and non-CoDeepSeedeX configuration must not be deleted.

After p2.10a64 passes tests, the next step is VM validation for the combined user paths:
- pre-release upgrade through `dsproxy upgrade --alpha`
- explicit pre-release upgrade through `dsproxy upgrade --tag v0.3.9-alpha`
- ordinary uninstall
- full `--remove-files` uninstall

## p2.10a63 P0 release-state documentation sync

p2.10a63 is a docs/version-metadata-only closure node after publishing `v0.3.9-alpha` to `p2.10a62`.

Trusted current state after the public pre-release update:
- `master = origin/master = ac63043`
- `p2.10a62-weclaw-runtime-payload-guard = ac63043`
- `v0.3.9-alpha = ac63043` as a public annotated pre-release tag, with peeled commit `ac63043`
- `v0.3.8-alpha = dfdc629`, unchanged
- forbidden plain tags `v0.3.9` and `v0.3.5` remain absent
- GitHub Release `CoDeepSeedeX v0.3.9-alpha` is non-draft, pre-release, and has `bootstrap.sh` and `install.sh` assets

P0 closure judgment:
- CoDeepSeedeX P0 implementation is closed.
- CoDeepSeedeX P0 public pre-release delivery is closed.
- WeClaw-facing delivery is closed from the CoDeepSeedeX side and is now waiting for WeClaw-side validation.
- New findings from WeClaw validation should start the next explicit requirement round, not reopen this P0 scope by default.

## p2.10a62 WeClaw runtime payload guard

p2.10a62 adds a WeClaw-facing char-level runtime payload guard contract. `runtime_payload_guard` exposes display-ready Compact and Trim progress using runtime in-memory snapshots, not debug files and not token totals.

The Compact numerator comes from the latest in-process context compaction report generated by `_compact_chat_history_for_codex_like_persistence()`, using `after_chars` as exact `runtime_context_builder` chars. The Trim numerator comes from the latest in-process trimming report generated by `_compact_deepseek_payload_context()` inside `DeepSeekClient.chat_completions()`, using `after_chars` as exact `live_request_payload` chars. If no model request has been observed in the running route, the contract returns machine-readable unavailable reasons and actions.

Do not derive Compact/Trim progress from provider token totals, session totals, debug files, SQLite, or Codex private profile data.

## p2.10a61 README structure cleanup

p2.10a61 cleans the user-facing README files by separating user workflows from developer history. README files should cover install, verification, configuration, providers, pricing, upgrades, WeClaw compatibility, and documentation entry points. Long release histories, internal contract debates, and development lessons belong in `docs/development-log.md` or this handbook, not in README.

The cleanup also removes Markdown structure pollution caused by shell comments rendered as headings, removes Brave as a user-facing provider setup path, and keeps public pre-release `v0.3.9-alpha` unmoved at `4a96283`.

## p2.10a60 WeClaw status context and pricing contract

p2.10a60 addresses WeClaw fourth-round status requirements on the CoDeepSeedeX side. Runtime WeClaw status now exposes a usable context numerator without fabricating Codex internal context-window usage: `context_window.used_tokens` is populated from the latest primary upstream provider `prompt_tokens` when available, and is explicitly labelled as `estimated_current_context_from_latest_upstream_prompt_tokens`. It must not be replaced with `session_total` prompt tokens.

Pricing status now separates the current price values, their source trust, the official reference URL, and the official-cache refresh state. Bundled fallback prices are labelled as `bundled_official_docs_snapshot`; only a persisted `dsproxy pricing refresh --write-cache --json` cache is treated as a freshly fetched `official_docs_html` source. Cost estimates expose the pricing source kind, source URL, source trust, and official-pricing availability so WeClaw can avoid presenting default estimates as live official prices.

Context limit reporting now includes `context_window.limit_explanation`, covering `display_limit_tokens`, `model_context_window_tokens`, `auto_compact_token_limit`, and model-catalog context values. This is the dsproxy-owned explanation for 750k vs 1M style differences: WeClaw should use `display_limit_tokens` as the displayed denominator and keep `model_context_window_tokens` as the full declared profile window. If another denominator such as 950k appears, it must map to one of these explicit fields or be treated as external to the current dsproxy contract.

## p2.10a59 WeClaw token attribution boundary contract

p2.10a59 records the audited token attribution boundary for WeClaw third-round status display. The audit found that dsproxy can report exact provider usage totals and exact dsproxy model-call purpose attribution, but it does not yet have an audited tokenizer or per-prompt-segment ledger for user/tool/environment/history splits.

Contract changes:

1. `tokens.taxonomy.version` is now `3`.
2. `tokens.attribution.provider_usage_totals` marks aggregate provider fields as exact.
3. `tokens.attribution.purpose_attribution` marks dsproxy `purpose`, `call_index`, `request_id`, and model attribution as exact.
4. `tokens.attribution.prompt_subcategory_split` explicitly reports `available=false`, `precision=unavailable`, and `reason=provider_usage_is_aggregate_without_prompt_subcategory_breakdown`.
5. `tokens.prompt_subcategory_split` mirrors the same unavailable contract for simpler WeClaw consumption.
6. `tokens.attribution.context_window_used_tokens` explicitly remains unavailable and points WeClaw back to `context_window.used_tokens`.
7. This node does not introduce a tokenizer, does not estimate user/tool/env/history tokens, and does not derive context-window used tokens from session totals.

Boundary: WeClaw may show exact aggregate provider totals and exact purpose-level totals. It must not display fabricated prompt subcategory token splits.

## p2.10a58 guarded official pricing refresh

p2.10a58 implements a guarded pricing refresh path for WeClaw round3. The official V4 pricing source is the human DeepSeek documentation page at `https://api-docs.deepseek.com/quick_start/pricing`, not a stable pricing API. The older `pricing-details-usd` and `pricing-details-cny` pages still describe legacy `deepseek-chat` and `deepseek-reasoner` pricing and must not be used as the V4 source.

Contract additions:

1. `dsproxy pricing refresh --json` now fetches and validates the official DeepSeek pricing HTML, but it does not write cache data by default.
2. `dsproxy pricing refresh --json --write-cache` atomically writes validated pricing to the user pricing cache, or to an explicit `--cache-path`.
3. Refresh failures preserve any existing cache and return structured `reason`, `error_type`, `source_url`, `source_kind`, `writes_cache=false`, and `old_cache_preserved=true`.
4. `pricing show --json` can report `source_url`, `source_kind`, `fetched_at`, `expires_at`, `ttl_seconds`, and `is_stale` when the selected pricing source contains metadata.
5. The implementation labels the source as `official_docs_html`, not as a stable API.
6. The project default `config/pricing.json` is not modified by default refresh behavior.

This node does not implement a vendor-stable pricing API because no such V4 pricing API was evidenced during the p2.10a58 audit.

## p2.10a57 WeClaw round3 contract foundation

p2.10a57 is a low-risk contract foundation node for the WeClaw third-round requirements. It preserves p2.10a55 compatibility and adds machine-readable diagnostics rather than implementing high-risk token estimation, live pricing refresh, or semantic payload compaction enablement.

Contract additions:

1. WeClaw-facing profile and runtime status now expose `diagnostics` with `degraded_fields`, `warnings`, and `actions`.
2. `context_window.used_tokens` remains unavailable, but now carries stable `used_tokens_action` and `used_tokens_precision=unavailable`.
3. `context_window.model_catalog` can bind a managed Codex profile `model_catalog_json` entry to the effective model when a readable catalog is present. If unavailable, it reports `reason` and `action`.
4. Pricing contract fields now include `source_url`, `ttl_seconds`, and a stable `refresh` object with `action`, `source_kind`, `requires_live_network`, and `writes_cache=false`.
5. `dsproxy pricing show --json` returns the current static pricing cache. `dsproxy pricing refresh --json` exists but returns structured `not_implemented` without network access or cache writes.
6. Runtime WeClaw status mirrors `compaction.semantic_compaction` to top-level `semantic_compaction` and enriches rollout state with `action` and `missing_events`.
7. This node does not infer context used tokens from session usage, does not split prompt subcategories without a tokenizer, does not implement official live pricing refresh, and does not enable semantic payload compaction.

Release state: no public Release tag is moved, no GitHub Release is created, and no Release assets are rebuilt.

## p2.10a55 WeClaw runtime status contract closure

p2.10a55 fixes the second-round WeClaw full telemetry gap found after real WeClaw integration. The key runtime bug was that `GET /v1/proxy/weclaw/status` used `create_app()` closure parameters for `store` and `deepseek_client`, while the actual running objects are held in `app.state.store` and `app.state.deepseek_client`.

Implemented contract changes:

1. Runtime WeClaw status now aggregates usage from `app.state.store`, so Codex/ACP requests recorded in the running SQLite usage ledger can surface through `tokens.last_turn`, `tokens.session_total`, and `tokens.auxiliary_model_calls`.
2. Runtime WeClaw status now queries balance through `app.state.deepseek_client`, with no API-key status downgraded to actionable `not_configured` instead of a generic client-unavailable reason.
3. Balance unavailable responses now include `status`, `provider`, `reason`, `action`, `updated_at`, `currency`, `amount`, and `display`.
4. Cost responses now distinguish usage, pricing, and stale-pricing availability through `usage_available`, `pricing_available`, `pricing_stale`, `reason`, `missing`, and pricing timestamp fields.
5. Context-window responses now include `used_tokens=null`, `used_tokens_available=false`, and `used_tokens_source=not_reported` so WeClaw does not infer context usage from session totals.
6. Model-conflict responses now include `display_hint`, `diagnostic_hint`, and `user_visible=false`, allowing normal WeClaw status to hide internal model-drift diagnostics while verbose status can show them.
7. CLI fallback status mirrors the new context and balance unavailable fields when the runtime WeClaw endpoint is unreachable.

The patch does not move the public `v0.3.9-alpha` Release tag and does not rebuild Release assets.

## p2.10a54 token shadow accounting plan

p2.10a54 is a documentation and version-metadata sync node. It records the decision that dsproxy should not directly replace existing character-based runtime compaction with token-based triggering. Instead, it should add a token shadow accounting and drift-observability layer before semantic payload compaction implementation.

### Decision

Keep the current dsproxy runtime payload guard as character-based:

1. persistent compaction remains a proxy-side payload safety valve,
2. trimming remains a proxy-side hard guard,
3. `runtime_compaction` and `runtime_trimming` continue to report `unit=chars`,
4. existing char guards continue to protect serialized payloads, tool outputs, JSON, reasoning content, and function arguments even when token estimates are unavailable.

Add token shadow accounting before implementing semantic payload compaction:

1. expose token-level context window values from Codex profile and Codex status as token fields,
2. keep provider-returned usage as the authoritative cost and token source when available,
3. add local token estimates only as estimates with explicit confidence and source,
4. report token-vs-char drift so maintainers can see whether char guards are early, late, or aligned,
5. keep WeClaw display fields separated into token-level context window and char-level proxy payload guard.

### Required contract boundary

Future status and WeClaw contracts should keep these concepts separate:

```json
{
  "context_window": {
    "unit": "tokens",
    "limit_tokens": 750000,
    "used_tokens_reported": null,
    "source": "codex_profile|codex_status|provider_usage"
  },
  "runtime_payload_guard": {
    "unit": "chars",
    "effective_trigger_chars": null,
    "max_context_chars": null,
    "source": "dsproxy_runtime"
  },
  "token_shadow": {
    "available": false,
    "estimated": true,
    "input_tokens_estimated": null,
    "confidence": "low|medium|high",
    "source": "local_estimator|provider_usage|codex_status"
  },
  "drift": {
    "token_to_char_ratio": null,
    "risk": "unknown|early_char_compaction|late_char_compaction|aligned"
  }
}
```

The exact schema can change during implementation, but the unit separation must not be weakened. Token context windows, character payload guards, provider usage, and cost attribution must stay distinct.

### Implementation prerequisites

Before semantic payload compaction is implemented, the maintainer must audit and define:

1. which token source is available for each route: Codex status, provider usage, local estimator, or none,
2. whether local estimation is model-specific or generic,
3. how estimates are labelled so they are never confused with provider usage,
4. how compact turns are attributed in usage and cost summaries,
5. how WeClaw displays token context, char payload guard, compact events, and costs,
6. how drift warnings should behave when token estimates and char guards disagree.

### Future trigger policy

Do not switch runtime compaction to token triggering in one step. The safe sequence is:

1. observe only,
2. report token shadow values and drift,
3. add warnings when token risk and char risk diverge,
4. evaluate real traces,
5. only then consider dual-threshold triggering based on chars or token-risk evidence.

This keeps existing safety behavior while addressing the semantic drift between Codex token windows and dsproxy character guards.

## p2.10a53 TUI compact path evidence sync

p2.10a53 is a documentation and version-metadata sync node. It records manual Codex TUI evidence collected after p2.10a52. It does not implement new runtime behavior, does not move public Release tags, and does not rebuild Release assets.

### Evidence captured

Manual isolated Codex TUI testing under `codex --profile deepseek` confirmed:

1. The TUI starts with the `deepseek` profile and reaches the dsproxy-backed provider.
2. A normal short request, `reply ok exactly`, succeeds through the profile.
3. Manual `/compact` succeeds and displays `Context compacted`.
4. Manual `/fork` was previously observed to fork the current chat.
5. `/status` works and reports token-level context information from Codex.
6. The manual compact path capture found no `responses/compact` or `/responses/compact` marker in the TUI transcript.
7. Codex-side logs show `codex.op="compact"`, `session_task.compact`, `model_client.stream_responses_api`, `wire_api=responses`, `http.method="POST"`, and `api.path="responses"`.
8. The dsproxy listener on port 8000 is the local uvicorn process for `deepseek_responses_proxy.app:app`, and proxy access logs show ordinary `POST /v1/responses HTTP/1.1` requests.

### Updated interpretation

Current evidence indicates that manual `/compact` in Codex CLI `0.130.0` with `codex --profile deepseek` uses the ordinary Responses route, not a dedicated `/responses/compact` route. Therefore, there is no current evidence requiring a dsproxy `/responses/compact` compatibility surface for manual `/compact`.

This conclusion is limited to manual `/compact` in a short isolated TUI session. It does not prove that Codex auto-compact near `model_auto_compact_token_limit` follows the same route. Auto-compact remains unverified because the test did not push the session near the token threshold.

### Remaining P0.6 work

P0.6 remains partially open for:

1. auto-compact route capture near the token threshold,
2. repeated or long-session compact stability,
3. compact prompt and summary quality if payload-level debug tracing is enabled,
4. usage and cost attribution for compact turns,
5. whether WeClaw should display compact turns separately from normal turns.

Do not prioritize implementation of a `/responses/compact` compatibility endpoint unless future evidence shows that auto-compact or a newer Codex CLI version calls that route and fails.

## p2.10a52 semantic payload compaction and TUI compatibility plan

p2.10a52 is a planning and documentation node. It does not implement semantic payload compaction, does not validate the Codex TUI matrix yet, and must not move public Release tags or rebuild Release assets.

### Scope

This plan records two inserted tasks that must not silently replace the active WeClaw task bus:

1. `P0.5 semantic payload compaction hardening`: after WeClaw second-round requirements and before AnyCodeX-level architecture work, unless a high-risk TUI compaction failure forces escalation.
2. `P0.6 Codex TUI third-party profile command compatibility`: run an isolated TUI command matrix for `codex --profile deepseek` and verify native `/compact`, auto-compact, `/fork`, `/resume`, `/model`, `/status`, `/diff`, `/review`, approval, sandbox, and related commands.

### Current unit boundary

Codex profile context fields are token-level declarations. `model_context_window` and `model_auto_compact_token_limit` must be treated as tokens. dsproxy runtime compaction, trimming, and semantic payload compaction are character-level payload guards. WeClaw and CLI displays must not merge token windows and character budgets into a single progress bar unless unit and source are explicit.

### Semantic payload compaction requirements

Before implementation, the maintainer must approve a concrete checklist covering:

1. Eligible payload classes. Initial candidates are low-risk flattened tool transcripts, repeated long terminal output, long pytest output, and repetitive shell logs.
2. Forbidden payload classes. Do not compact user requirements, task plans, patch scripts, git state, commit/tag/Release state, root-cause conclusions, test assertions, key error stack frames, API key semantics, or recent high-value conversation state.
3. Auditability. Every dry-run and applied event must report message index, semantic type, risk level, retention markers, chars before, chars after, chars removed, and whether the original payload was preserved.
4. Usage and cost impact. Provider token usage remains the source of truth. Cost estimation remains based on the usage ledger and pricing cache. Token savings must not be claimed as exact unless an audited tokenizer or provider-backed comparison exists.
5. WeClaw impact. WeClaw may receive a separate semantic payload compaction section with `unit=chars`, mode, safety, eligible count, applied count, chars removed, and rollout blockers. It must remain separate from token-level context window fields.
6. Debug and observability. `debug budget`, long-session observability, runtime status, and WeClaw status must expose semantic dry-run and applied events without hiding existing persistent compaction or trimming fields.
7. Rollback. Default mode remains dry-run. Enabled mode requires explicit environment gates, canary checks, and local invariant checks. Any exception or non-beneficial compaction must return the original messages.

### Mandatory implementation checklist

Implementation must complete these items before it is considered done:

1. Full-source audit of `deepseek_responses_proxy/app.py`, `deepseek_responses_proxy/cli.py`, `tests/test_context_trimming.py`, `tests/test_context_runtime_observability.py`, `tests/test_cli.py`, `tests/test_weclaw_full_telemetry_contract.py`, and `tests/test_usage_ledger.py`.
2. Close the current dry-run event gap so semantic audit, policy dry-run, and payload dry-run events are present when candidates exist.
3. Add structured status fields for semantic payload compaction without breaking existing `compaction`, `runtime_compaction`, `runtime_trimming`, `tokens`, `pricing`, `cost`, or `balance` fields.
4. Add focused tests for low-risk compaction, forbidden-content preservation, recent-message preservation, dry-run-only default, canary-gated enabled mode, and exception fallback.
5. Reassess token/cost/usage reporting after payload mutation and document that provider usage remains authoritative.
6. Run sanitized focused tests and full tests before any merge.

### Required implementation report

When implemented, the report must include branch, commit, internal tag, public tag unchanged status, exact enabled mode, dry-run closure evidence, canary state, eligible and forbidden payload classes, chars before/after, chars removed, token/cost accounting impact, WeClaw field changes, focused tests, full tests, and remaining risks.

### Codex TUI compatibility requirements

The TUI matrix must verify at least `/help`, `/status`, `/model`, `/compact`, auto-compact, `/fork`, `/resume`, `/diff`, `/review`, `/approval`, `/sandbox`, and `/clear` under `codex --profile deepseek`.

The matrix must record whether each command is local-only, uses ordinary Responses requests, uses `/responses/compact`, depends on OpenAI or ChatGPT private surfaces, depends on session store or provider filtering, or needs dsproxy compatibility work.

If native `/compact` or auto-compact fails for the third-party profile, dsproxy must not rely on character-level persistent compaction as an automatic substitute unless the request actually reaches dsproxy through a compatible path. The follow-up design must choose one of these approaches with evidence:

1. Force or guide inline compact through ordinary Responses requests.
2. Implement a compatible `/responses/compact` surface after capturing the real request/response contract.
3. Provide a wrapper or integration-level guard that prevents unsupported TUI commands from damaging the session and gives a clear recovery path.

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

Do not label untested or auth-failed model providers as unsupported. After the model API matrix is complete, open a dedicated architecture branch to assess which CoDeepSeedeX layers are reusable and which are DeepSeek-specific. The likely branch is `work/p2.10-generalized-provider-architecture-audit`. That assessment must cover provider adapters, reasoning/thinking fields such as `reasoning_content`, stream event normalization, model catalog metadata, Codex `/model` display, and the broader goal of evolving CoDeepSeedeX into a more general AnyCodeX-level generalized provider architecture.

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

- Start the next major design line as `work/p2.10-generalized-provider-architecture-audit`.
- The audit must not guess from memory. It should start with a read-only audit of `app.py`, `cli.py`, runtime config loading, stream conversion, model catalog, provider config, tool bridge, tests, and docs.
- The goal is to assess whether CoDeepSeedeX should be generalized into an AnyCodeX-level generalized provider architecture.
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

## p2.10a11 model provider support labels

Only the native DeepSeek model provider may be labeled `Supported` in installer and configuration UX. Other model providers, including Kimi, Zhipu / BigModel, Z.AI, and Qwen / DashScope, must be labeled `Experimental` until they pass full Codex workflow validation. API key validation, endpoint reachability, or a single model response is not enough to claim support because Codex compatibility also depends on streaming behavior, tool calls, reasoning semantics, context-window behavior, error recovery, and cost behavior.

Policy statement: API connectivity is not equivalent to full Codex workflow support.

## p2.10a12 bootstrap install-ref source banner

Fresh VM pre-release installation must not rely on GitHub Latest. When `bootstrap.sh --install-ref <tag>` or `DEEPSEEK_PROXY_INSTALL_REF=<tag>` is set, bootstrap must first download `https://github.com/Awenforever/CoDeepSeedeX/releases/download/<tag>/install.sh`, then fall back to raw/tag clone paths only if needed. Bootstrap and install screens must display source information under the banner so operators can tell whether they are running Latest, a specific release tag, or a local checkout.

## p2.10a13 installer UI compaction

Interactive installer screens should avoid printing full release asset URLs under the logo. Keep the visible UI compact: show the product name and public version near the banner, and write bootstrap/installer source details to logs. Arrow-key menus must render to and read from `/dev/tty`, not stdout, because stdout is often captured by tee/log wrappers during VM validation.

## p2.10a13 public commit resolution

Runtime public commit metadata should resolve the configured public Release tag when Git metadata is available, instead of requiring a static self-referential commit hash in source. This avoids repeated test churn when a pre-release tag is rebuilt to a new commit. The fallback remains in source for non-Git installations.

## p2.10a14 installer source log variable

When moving installer source details out of the interactive UI, write them to the existing `INSTALL_LOG` variable. Do not introduce `LOG_FILE`; the installer runs with `set -u`, so undefined variables abort fresh VM installs.

## p2.10a15 installer provider flow

Guided installer menus should first ask for a provider family, then show endpoint, region, Token API, or Coding Plan API choices only when that family requires disambiguation. Yes/No menus must use plain rendering and must not inherit provider status labels such as Supported. The installer logo should show the active install ref beside CoDeepSeedeX. If Git clone or `git fetch --tags origin` fails during VM installation, the installer may fall back to a tagged GitHub/codeload source archive for the requested install ref.

## p2.10a16 installer logo heredoc

ASCII art in shell scripts must use quoted heredocs when it contains backticks, backslashes, or dollar signs. `bash -n` does not catch command substitution triggered inside an unquoted heredoc at runtime, so installer banner changes should include a runtime smoke test for the rendered function.

## p2.10a17 installer menu rendering

Arrow-key menus must not rely on long raw lines wrapping correctly. Render each option as one terminal-width bounded row, truncate before printing, and use a full-row highlight for the selected item. Numeric shortcuts for listed option values should return immediately, including `0` for skip/back. The global menu help hint should appear once per installer run, and guided configuration blocks should be visually separated.

## p2.10a18 installer minimal arrow UI

Installer menus must have exactly one active `read_menu_choice_from_tty()` implementation. Do not leave duplicate shell function definitions because Bash will use the later definition and silently override the intended renderer. The guided installer menu is arrow-only: use `↑/↓` or `j/k`, `Enter` to select, and `Backspace` to go back or skip. Do not advertise or implement numeric/text fallback for TTY menus. Dim helper text and default-value hints, and keep bootstrap prerequisite checks in logs when the install script repeats equivalent checks.

## p2.10a18 CLI version metadata source

CLI version metadata must use constants imported from `deepseek_responses_proxy.app` directly. Declared internal version wins over any existing p-tag on HEAD. Do not read version metadata through `from deepseek_responses_proxy import app`, because the package-level `app` name can refer to the FastAPI application object and not the `deepseek_responses_proxy.app` module. If that happens, the CLI can silently fall back to git tag inference and report the previous internal tag while source tests still pass.

## p2.10a19 installer menu column alignment

Selected and unselected menu rows must keep option values in the same visual column. Because the selected marker uses `▶ `, the unselected marker column should use two spaces rather than three. Keep this covered by a text-level installer test.

## p2.10a20 installer secret prompt semantics

Secret prompts must distinguish a newly typed secret from an empty submission that keeps an existing secret. Empty input with a default secret must not be reported as newly received characters and must not trigger validation as if the user pasted the key. Helper text such as optional/hidden/keep-existing instructions should be dim. The Codex wrapper prompt should explain that after installation users can run `codex --profile deepseek` or `codex --profile deepseek-thinking`, with the wrapper handling local dsproxy backend startup or refresh.

## p2.10a21 installer wrapper help placement

Prompt-specific explanatory text should be rendered by the menu renderer immediately under the prompt and before the global keybinding hint. Do not print prompt-specific help as a standalone line before invoking the menu, because it visually detaches the explanation from the question.

## p2.10a22 installer port label and effort surface

Installer UI should call the 8000 profile `Non-Thinking`, not `Stable`, because the user-facing concept is the DeepSeek thinking mode rather than release stability. CoDeepSeedeX-owned profile install and upgrade paths should not write `medium` for DeepSeek profiles. `low` and `medium` remain accepted compatibility inputs from Codex or older commands and are normalized to DeepSeek `high`.

## p2.10a23 installer runtime call coverage

Installer tests must not only assert that a call string exists; they must also assert the called shell function is defined before use. Runtime-only branches such as image API validation can pass `bash -n` while still failing with `command not found`. Pre-release install tests may rebuild and move the same public alpha tag repeatedly, so installer checkout refresh should use force tag fetches for managed install directories instead of failing on `would clobber existing tag`.


## p2.10a24 installer output and live image validation

Installer TTY output should follow a Pixi-like separation of human-readable progress and detailed logs: compact sections, dim explanatory lines, no raw source URLs near the logo, and a combined `Install logs` section for bootstrap and install logs. Image API setup is now an explicit live validation path: it warns that one safe image will be generated and may consume provider credits, then saves the generated artifact under `/tmp`. Avoid reintroducing non-generating image probes as the guided installer gate.

### p2.10a25 installer polish rule

For source archive installs, do not rely on `.git` being present for version metadata. The installer should resolve the target ref commit when possible and persist it through the generated env file consumed by the dsproxy wrapper. Existing non-git install directories should go directly to source archive fallback instead of first printing a git clone fatal message. DeepSeek Codex profiles must explicitly set `plan_mode_reasoning_effort = "high"` so native Codex Plan mode does not surface unsupported `medium` semantics. The proxy still accepts legacy or Codex-originated `medium` and maps it to DeepSeek `high` as a compatibility fallback.

### p2.10a26 wrapper startup, Plan mode, and uninstall rule

Codex wrapper startup is fail-closed for CoDeepSeedeX-managed profiles. When `codex --profile deepseek` or `codex --profile deepseek-thinking` is launched, the wrapper must start the matching proxy route and then verify `dsproxy status` for that route. If startup and status both fail, the wrapper must print a concise error and not enter Codex against an empty port.

DeepSeek Codex profiles must write both `model_reasoning_effort` and `plan_mode_reasoning_effort`. `plan_mode_reasoning_effort` is pinned to `high` because Codex native Plan mode reads that dedicated config key. Do not document Plan mode as merely showing `medium` while proxy-side aliases repair it.

Uninstall must restore the previous Codex command when `CODEX_WRAPPER_BACKUP` is present in the install manifest. Any wrapper rewrite must preserve manifest-backed rollback: remove the CoDeepSeedeX wrapper first, then move the saved backup back to the original wrapper path.


## p2.10a28 dsproxy-owned WeClaw profile contract

CoDeepSeedeX / `dsproxy` owns Codex profile files and DeepSeek runtime configuration. WeClaw must not edit `~/.codex/config.toml` or infer model, effort, context-window, token, cost, pricing, balance, or compaction state from private files.

`dsproxy config set-effort max` stores `DEEPSEEK_REASONING_EFFORT=max` for the DeepSeek side and writes Codex-compatible `model_reasoning_effort = "xhigh"` to managed Codex profiles. `xhigh` remains accepted as a compatibility input and normalizes to DeepSeek `max`. `low`, `medium`, `minimal`, and `none` are compatibility inputs that normalize to DeepSeek/Codex `high` for this proxy path.

Machine-readable contract surfaces:
- `dsproxy profile status [profile] --json`
- `dsproxy profile set-effort <profile> <effort> --json`
- `dsproxy status [thinking] --weclaw-json`

The WeClaw status contract must report unavailable token, pricing, cost, balance, auxiliary-token, and compaction fields as structured `available=false` or `missing=[...]` values until dsproxy has audited exact data sources. Do not make WeClaw guess these values.


## p2.10a29 WeClaw runtime contract unification

`dsproxy` must expose model and context source-of-truth fields for WeClaw instead of relying on WeClaw to parse private Codex files. The WeClaw-facing contract must distinguish:
- `codex_model`: the model declared in the Codex profile.
- `effective_model`: the model actually selected by dsproxy for upstream calls.
- `force_model_enabled`: whether `DEEPSEEK_PROXY_FORCE_MODEL` overrides the Codex request model.
- `model_conflict`: whether the Codex profile model differs from the effective upstream model.

When `model_conflict=true`, WeClaw should display `effective_model` and may show `codex_model` only as a diagnostic detail.

Context fields must distinguish token-level Codex declarations from char-level dsproxy runtime controls. Codex profile fields such as `model_context_window` and `model_auto_compact_token_limit` are token-level declarations. Runtime compaction/trimming status from `/v1/proxy/status.context` is char-level behavior. Do not combine these values without explicitly labeling units and source.

Installed Codex wrappers may be stale after source updates. `dsproxy profile refresh-wrapper --json` refreshes a CoDeepSeedeX-managed wrapper from the install manifest while preserving manifest-backed rollback metadata. Unknown user-owned wrappers must not be overwritten unless the operator explicitly passes `--force`.


## p2.10a30-p2.10a34 wrapper, profile, and WeClaw contract closure

Managed Codex profile `model` values must match each profile's effective upstream model. `dsproxy profile repair --managed-only --json` repairs `deepseek` and `deepseek-thinking` by computing each profile's effective model through the same profile contract used by `profile status`. `codex_model`, `effective_model`, and `model_conflict` remain diagnostics. Normal managed state should have `model_conflict=false`.

The WeClaw-facing model and context contract is owned by dsproxy. WeClaw should use `effective_model`, inspect `model_conflict`, and consume context fields with their explicit source and unit. Codex profile context values such as `model_context_window` and `model_auto_compact_token_limit` are token-level declarations. Runtime compaction and trimming controls are char-level behavior and must not be merged without labeling.

Installed Codex wrappers may be stale after source updates. `dsproxy profile refresh-wrapper --json` refreshes a CoDeepSeedeX-managed wrapper from the install manifest and preserves manifest-backed rollback metadata. Unknown user-owned wrappers must not be overwritten unless the operator explicitly passes `--force`.

The current tab-title design is the p2.10a34 design. Do not resurrect earlier pre-start or three-shot delayed title strategies. The wrapper must:
- avoid setting the title before Codex startup
- start and verify the matching dsproxy route
- schedule a bounded runtime title keeper after route preparation
- allow `/dev/tty` title writes even when stdout is redirected
- run the real Codex binary as a foreground command, not with `exec`
- record the keeper PID
- stop and wait for the keeper after Codex returns
- return the original Codex status

Lessons from this sequence:
- Windows Terminal tab titles can be changed by OSC writes to the active TTY, but Codex may overwrite titles during startup.
- A background job with stdout redirected to `/dev/null` must not use `[ -t 1 ]` as the only gate when it intends to write `/dev/tty`.
- A fixed time limit is not a lifecycle boundary. Keeper processes must be tied to the real Codex command lifecycle with PID cleanup.
- Do not add tab-color behavior to the wrapper without a verified current-tab runtime mechanism. `wt --tabColor` is a new-tab or split-pane launch parameter, not a proven current-tab wrapper control.
- Future wrapper and installer patches should replace whole shell functions or generated wrapper templates, not narrow escaped fragments.

## p2.10a35 documentation and replacement discipline

p2.10a35 is a documentation and handoff synchronization node after p2.10a34. It updates the current state, condenses superseded wrapper title experiments into the current effective p2.10a34 design, records the replacement-discipline rule, and prepares the next conversation handoff.

Do not treat this as a public Release. It must not move `v0.3.8-alpha` or rebuild Release assets unless the maintainer explicitly starts a Release task.

## p2.10a36 release-state documentation sync

p2.10a36 synchronizes documentation with the verified GitHub Release state. `v0.3.8-alpha` remains the public alpha Release tag at `dfdc629`, but the GitHub Release is currently non-draft and non-prerelease. This update changes current-state wording and README migration notes only.

Do not treat this as a Release rebuild. It must not move `v0.3.8-alpha`, recreate the GitHub Release, or upload new Release assets.

## p2.10a38 version metadata and name boundary

p2.10a38 updates developer runtime internal version metadata to `p2.10a38-version-metadata-name-boundary` and records the AnyCodeX future-name boundary. Public version metadata remains `v0.3.8-alpha`.

This is not a Release rebuild. It must not move `v0.3.8-alpha`, recreate the GitHub Release, or upload new Release assets.

## p2.10a40 generalized provider architecture audit report

The p2.10a40 audit is an internal planning checkpoint, not a broad runtime refactor. It converts the read-only evidence collection into an implementation order for a future AnyCodeX-level generalized provider architecture while keeping the current project name CoDeepSeedeX.

Evidence-based findings:

1. The runtime core remains a large monolith in `deepseek_responses_proxy/app.py`. Upstream model calls still pass through `DeepSeekClient`.
2. Runtime configuration is still DeepSeek-named: `DEEPSEEK_API_KEY`, `DEEPSEEK_BASE_URL`, `DEEPSEEK_PROXY_MODEL`, `DEEPSEEK_PROXY_FORCE_MODEL`, `DEEPSEEK_THINKING`, and `DEEPSEEK_REASONING_EFFORT`.
3. Thinking behavior is DeepSeek-specific. The active seams include `_deepseek_thinking_config`, `_repair_thinking_history_messages`, `_prepare_messages_for_deepseek`, `reasoning_content`, and DeepSeek ChatCompletions role/tool-call repair.
4. CLI and installer provider catalogs are more generalized than the runtime core. They already distinguish DeepSeek, Kimi, Zhipu / BigModel, Z.AI, Qwen / DashScope regional endpoints, and custom OpenAI-compatible providers.
5. Web search and image generation already have provider dispatch layers, but they are tool-provider bridges rather than a general model-provider abstraction.
6. WeClaw-facing contracts should remain stable while the internal provider architecture evolves. `effective_model`, `codex_model`, `model_conflict`, context-window units, and profile repair contracts must not be broken.

Implementation order:

1. Add provider-capability metadata first. It should describe supported request shape, reasoning strategy, stream event mapping, tool-call constraints, usage fields, and model catalog behavior.
2. Add an upstream adapter interface after metadata exists. Do not rename `DeepSeekClient` globally in one patch. Introduce an adapter boundary and migrate call sites incrementally.
3. Separate reasoning/thinking strategy from the model provider. DeepSeek `reasoning_content` repair should become one strategy, not the default assumption for every provider.
4. Separate stream normalization from provider transport. Responses stream events should be generated from a provider-neutral event model.
5. Keep tool bridge replacement as a related but separate layer. Web search, image generation, and future third-party tool replacement should not be collapsed into the model-provider adapter.
6. After each step, run sanitized focused tests and full tests. Do not attribute failures to the patch until environment overrides have been audited.

## p2.10a41 long-term task bus and WeClaw acceptance audit

This task bus is the durable mainline tracker for new conversations and inserted tasks.

Current priority state after p2.10a49:

1. P0 current state: the first WeClaw full telemetry contract baseline is complete at p2.10a48 and has been accepted by the WeClaw side for initial integration.
2. P0 next step: wait for WeClaw's second-round audited requirements. Continue in a new conversation, starting from a read-only state audit before any patch.
3. P1 next default direction if no WeClaw second-round task is active: AnyCodeX-level generalized provider architecture audit/refactor planning.
4. P2 follow-up: public Release preparation only when the maintainer explicitly asks for a Release.

Anti-drift rules:

1. Inserted tasks such as documentation sync, version metadata updates, naming-boundary cleanup, and release-state fixes may interrupt the mainline, but they must return to this task-bus priority after they close.
2. A future architecture audit or refactor must not break the accepted WeClaw contract surfaces.
3. Every handoff must include this task bus, current P0 status, accepted fields, precision boundaries, and pending second-round WeClaw requirements.
4. Completion claims require evidence: exact CLI or HTTP command, JSON output shape, field source, precision status, tests run, and remaining gaps.

Accepted WeClaw baseline after p2.10a48:

1. `config set-effort` and `profile set-effort` do not write `model_reasoning_effort = "max"` into Codex profiles.
2. `profile status --json` gives WeClaw authoritative profile, model, effort, thinking, context-window, and health fields.
3. `status --weclaw-json` and runtime HTTP WeClaw status expose profile, model, context, token taxonomy, usage aggregation, pricing, cost, balance, and compaction status.
4. HTTP WeClaw endpoints exist and are accepted:
   - `GET /v1/proxy/weclaw/profile-status?profile=deepseek-thinking`
   - `GET /v1/proxy/weclaw/status?profile=deepseek-thinking`
5. Ready fields include `model.effective_model`, `model.codex_model`, `model.model_conflict`, `model.force_model_enabled`, `effort.user_facing`, `effort.deepseek_reasoning_effort`, `effort.codex_model_reasoning_effort`, `context_window.effective_safe_window_tokens`, `tokens.last_turn`, `tokens.session_total`, `tokens.auxiliary_model_calls`, `pricing`, `cost`, `balance`, and `compaction`.
6. Precision boundary: provider-reported token totals and dsproxy purpose attribution are reported. Cost is estimated from dsproxy pricing cache. Prompt subcategory splits such as user/tool/environment/history remain not-reported/unavailable unless a future audited tokenizer layer is added.
7. Isolated/sanitized tests are required when checking model attribution because exported `DEEPSEEK_PROXY_MODEL` and `DEEPSEEK_PROXY_FORCE_MODEL` can intentionally change effective model behavior.

## p2.10a43-effort-json-refresh-control effort JSON and refresh control


This patch keeps the P0 WeClaw acceptance mainline active.

Contract changes:

1. `dsproxy config set-effort <effort> --json` is accepted for CLI/help consistency. The command already prints JSON, so this is a parser-contract fix rather than an output-format change.
2. `dsproxy config set-effort <effort> --no-refresh` and `dsproxy profile set-effort <profile> <effort> --no-refresh` save the env/profile changes without refreshing live proxy processes.
3. The no-refresh path reuses the existing post-config apply disabled mode and returns `post_config_apply.status = "skipped"`.
4. The core effort mapping remains unchanged: DeepSeek/env effort may be `max`, Codex profile effort must be `xhigh`, compatibility inputs normalize to DeepSeek `high`, and `plan_mode_reasoning_effort` stays `high`.

WeClaw guidance:

- Use `profile set-effort <profile> <effort> --json --no-refresh` when changing one active profile from an integration test or non-interactive workflow.
- Use `config set-effort <effort> --profile <profile> --json --no-refresh` when preserving the legacy config command path.
- Omit `--no-refresh` only when the user intentionally wants running proxy processes refreshed after configuration changes.

## p2.10a44-doc-marker-discipline-cleanup documentation marker discipline cleanup

This patch cleans up documentation debt from p2.10a43.

Documentation discipline:

1. Do not add marker-only compatibility notes to make a validation string pass.
2. Verification markers must be derived from real source, tests, and document text.
3. If validation and real content differ, fix the validation rule or fix the intended content. Do not add non-semantic prose to satisfy a marker.
4. Before each patch, audit the exact source or document fragment being changed, the replacement rule, and the validation rule together.
5. Required markers should use real command contracts when possible. For p2.10a43, the real contracts are `dsproxy config set-effort <effort> --json`, `dsproxy profile set-effort <profile> <effort> --no-refresh`, and `post_config_apply.status = "skipped"`.

6. Stable handbook rules must be placed under numbered handbook chapters or under explicitly versioned history sections. Do not leave unnumbered standalone islands between numbered chapters and historical sections.

## p2.10a45-handbook-section-structure-cleanup handbook section structure cleanup

This patch cleans up the handbook section hierarchy after reviewing the full English and Chinese handbook text.

Structural decision:

1. `Provider bridge terminology contract` is not a standalone top-level chapter. It belongs under section 8 because it defines provider/tool bridge terminology.
2. `Model configuration command contract` is not a standalone top-level chapter. It also belongs under section 8 because it defines provider/model configuration command contract examples.
3. Stable handbook rules must be placed under numbered handbook chapters, while chronological implementation notes remain in versioned `p*` sections.
4. Future documentation patches should prefer full-text review when the structure is under discussion. Regex or grep snippets are insufficient for chapter hierarchy decisions.

## p2.10a46 WeClaw contract final acceptance

p2.10a46 completed the P0 WeClaw contract acceptance checkpoint.

Final state:

- `master = origin/master = 3e6b922`.
- `p2.10a46-weclaw-usage-test-env-isolation = 3e6b922`.
- `v0.3.8-alpha = dfdc629`, unchanged.
- Worktree clean after merge.
- No public Release tag was moved, no GitHub Release was created, and no Release assets were rebuilt.
- Focused WeClaw acceptance passed with all final acceptance flags true.
- Sanitized full tests passed with `435 passed`.

Accepted WeClaw contract surfaces:

```text
CLI:
dsproxy profile status <profile> --json
dsproxy profile set-effort <profile> <effort> --json
dsproxy status [thinking] --weclaw-json

HTTP:
GET /v1/proxy/weclaw/profile-status?profile=deepseek-thinking
GET /v1/proxy/weclaw/status?profile=deepseek-thinking
```

Ready fields:

- `model.effective_model`
- `model.codex_model`
- `model.model_conflict`
- `model.force_model_enabled`
- `effort.user_facing`
- `effort.deepseek_reasoning_effort`
- `effort.codex_model_reasoning_effort`
- `context_window.effective_safe_window_tokens`
- runtime compaction and trimming fields with explicit `unit=chars`

Structured degraded fields:

- `tokens.last_turn`
- `tokens.session_total`
- `tokens.auxiliary_model_calls`
- `pricing`
- `cost`
- balance-in-status

Test isolation lesson:

- Usage ledger model-attribution tests must clear `DEEPSEEK_PROXY_MODEL`, `DEEPSEEK_PROXY_FORCE_MODEL`, and `DEEPSEEK_MODEL` when they assert request-model attribution.
- Full-suite results from a developer shell must not be trusted until model, provider, image, web-search, and API-key environment variables are sanitized.
- Do not repair this class of failure by changing production model selection semantics.

## p2.10a48 WeClaw full telemetry contract

p2.10a48 reopens P0 after the p2.10a46 basic-contract checkpoint and implements the first full telemetry contract surface for WeClaw.

Implemented contract changes:

- Runtime HTTP `GET /v1/proxy/weclaw/status?profile=deepseek-thinking` now aggregates usage ledger data into `tokens.last_turn`, `tokens.session_total`, and `tokens.auxiliary_model_calls`.
- Runtime HTTP WeClaw status now exposes pricing cache metadata, estimated cost fields, and provider balance data.
- CLI `dsproxy status thinking --weclaw-json` prefers the runtime WeClaw status endpoint when the proxy is reachable and falls back to structured unavailable fields when it is not.
- Token counts are provider-reported exact totals from the dsproxy usage ledger.
- Cost fields are estimates from dsproxy pricing cache and are not provider invoice data.
- Prompt subcategory split such as user/tool/environment/history remains marked as not provider-reported unless a future audited tokenizer layer is added.

## p2.10a49 final handoff sync

p2.10a49 is the final handoff synchronization node for the completed p2.10a48 WeClaw full telemetry contract line.

Final handoff state:

- `master = origin/master = 2e0edd0` before the p2.10a49 documentation sync.
- `p2.10a48-weclaw-full-telemetry-contract = 2e0edd0`.
- `v0.3.8-alpha = dfdc629`, unchanged.
- WeClaw accepted the p2.10a48 reporting baseline and started initial integration.
- WeClaw second-round requirements will be proposed after their audit and should continue in a new conversation.
- This node updates the current-state blocks, task bus, development log, and runtime internal version metadata for handoff continuity.
- This node is not a public Release and must not move `v0.3.8-alpha`, create a GitHub Release, or rebuild Release assets.

New-conversation instruction:

- Start with a read-only audit of branch, HEAD, origin/master, worktree, `p2.10a49-final-handoff-sync`, `p2.10a48-weclaw-full-telemetry-contract`, and `v0.3.8-alpha`.
- Read `docs/developer-handbook.md` first.
- Treat p2.10a48 as the accepted first WeClaw full telemetry baseline.
- Continue second-round WeClaw requirements only after their concrete audited request is available.


## p2.10a65 Profile tokenizer accounting

p2.10a65 starts the profile-aware tokenizer accounting line for WeClaw. It adds a dsproxy-owned local tokenizer layer for DeepSeek profiles, backed by the official DeepSeek V3 tokenizer JSON resource and the Python `tokenizers` package.

Contract boundary:

- Provider `usage` fields remain authoritative for billing and aggregate prompt, completion, cache, and reasoning token totals.
- `tokens.profile_tokenizer` and `tokens.prompt_subcategory_split` are local profile-tokenizer estimates. They are suitable for WeClaw display and drift analysis, but they must not be treated as invoice data.
- Prompt subcategory splits use dsproxy message boundaries after payload assembly. They count message text, reasoning content, and tool-call names or arguments with the active DeepSeek tokenizer. Chat-template overhead is not assigned to a subcategory.
- Codex TUI token accounting is not claimed as replaced. Current evidence from `codex --profile deepseek debug models` did not show DeepSeek model catalog entries, so dsproxy exposes its own correct parallel accounting for integration clients.
- Char-level `runtime_payload_guard`, Compact, and Trim remain separate from token-level profile accounting.


## p2.10a66 Tokenizer resource installer sync

p2.10a66 changes tokenizer resource delivery from repository-bundled large JSON files to installer/user-machine synchronization. The runtime now looks for managed tokenizer resources under `DEEPSEEK_PROXY_TOKENIZER_RESOURCE_DIR` or `DEEPSEEK_PROXY_INSTALL_DIR/resources/tokenizers`, and the CLI exposes `dsproxy tokenizer status` and `dsproxy tokenizer sync deepseek --json`.

The official archive is still the DeepSeek token-usage documentation archive whose internal directory is named `deepseek_v3_tokenizer`. CoDeepSeedeX labels the local binding as `deepseek_official_current` to avoid claiming that it is a V4-specific tokenizer. Provider `usage` remains billing-authoritative; profile tokenizer accounting remains a local estimate for WeClaw display and drift analysis.


## p2.10a67 Status tokenizer contract consistency

p2.10a67 fixes the WeClaw status tokenizer contract boundary. `tokens.profile_tokenizer.available` now reports tokenizer resource and runtime binding availability, independently from whether the route has observed an assembled prompt. `tokens.profile_tokenizer.summary.available` reports whether an assembled prompt has been observed and summarized.

When the tokenizer resource is available but the route has not yet observed an assembled prompt, `tokens.prompt_subcategory_split.available` remains false with `reason=profile_tokenizer_available_but_no_observed_prompt` and `categories={}`. When the tokenizer resource is unavailable, the reason comes from the tokenizer contract, for example `profile_tokenizer_json_not_found`.

This prevents WeClaw from seeing a contradictory status where `dsproxy tokenizer status deepseek --json` is available but `tokens.profile_tokenizer.available` is false without a specific explanation.


## p2.10a68 Prompt Segment Ledger Audit

p2.10a68 fixes the prompt subcategory semantics for WeClaw Details. Codex can encode memory, environment, AGENTS instructions, tool-call transcripts, tool-output transcripts, and historical context as `role=user` messages. Therefore dsproxy must not classify every `role=user` message as the latest user input.

The tokenizer split now treats `user` as the latest ordinary user segment after excluding known Codex-injected environment and tool transcript markers. Earlier ordinary user segments go into `user_history`. `[tool call transcript]` and `[tool output transcript]` go into `tool_output`. AGENTS, memory, and environment-context user-role blocks go into `environment`.

The WeClaw contract also exposes `tokens.latest_prompt_segmentation` and `tokens.prompt_subcategory_split.latest_prompt_segmentation`, containing sanitized segment records with role, source, category, token_count, char_count, preview, and sha256. Full content must not be exposed in normal status.


## p2.10a69 Pricing Currency and Turn Ledger

p2.10a69 fixes the WeClaw Pricing/Cost contract. Pricing remains sourced from DeepSeek official USD prices, but dsproxy now exposes source currency, display currency, FX metadata, converted display amounts, and structured per-million-token price objects. When the account balance is CNY, status display contracts expose CNY amounts so WeClaw does not perform USD/CNY conversion.

Cost remains estimated, but it is explicitly sourced from the per-turn usage ledger (`usage_events.estimated_cost_usd`). Session cost is the sum of historical turn-level estimated costs and must not be recomputed from the currently active model price. The usage ledger now records route, effort, pricing model, pricing currency, pricing source kind, pricing updated timestamp, and per-turn price fields for new events.

Reasoning output cost is not split unless the provider exposes separate reasoning pricing. The contract reports `reasoning_cost_available=false` with a reason instead of asking WeClaw to infer it.


## p2.10a70 Pricing CNY Primary Source

p2.10a70 changes the DeepSeek pricing source priority. The Chinese official pricing page is the primary source for V4 Flash/Pro prices and uses CNY per million tokens. The English pricing page is retained as a USD fallback/i18n source.

Default bundled prices are now:
- deepseek-v4-flash: cache hit 0.02 CNY/M, cache miss 1 CNY/M, output 2 CNY/M.
- deepseek-v4-pro: cache hit 0.025 CNY/M, cache miss 3 CNY/M, output 6 CNY/M.

The p2.10a69 FX fields remain in the contract, but they are not the default DeepSeek CNY path. FX conversion is used only when the active pricing source is USD and the display currency is CNY. WeClaw must continue to consume dsproxy structured pricing/cost fields and must not perform its own currency conversion.

Primary pricing URL: https://api-docs.deepseek.com/zh-cn/quick_start/pricing/
Fallback/i18n pricing URL: https://api-docs.deepseek.com/quick_start/pricing/

## p2.10a71 Pre-release Release Notes Closeout

Current closeout target: update `v0.3.9-alpha` from the current master after p2.10a71 validation. The Release note must be cumulative from `v0.3.8-alpha` to the current pre-release state, but it must remain user-facing and feature-focused.

Do include functional changes:
- WeClaw context, runtime payload guard, Compact/Trim progress, and context-window estimate fields.
- DeepSeek profile-tokenizer accounting and user-machine tokenizer sync/status commands.
- WeClaw Details prompt segmentation semantics, including latest `user`, `user_history`, `tool_output`, and `environment`.
- CNY-first Pricing/Cost contracts, DeepSeek Chinese official price source, cash estimate, and per-turn ledger cost semantics.
- Reasoning-cost unavailable semantics when providers do not expose separately priced reasoning output.

Do not include development-only details:
- internal p-tags,
- test counts,
- documentation maintenance work,
- command-script recovery details,
- implementation churn,
- release-note editing process.

The `v0.3.9-alpha` Release note must be updated cumulatively on top of the existing Release body. Do not replace it with a short delta that loses earlier v0.3.9-alpha features such as `runtime_payload_guard`, Compact/Trim, context-window limit explanation, pricing refresh, and WeClaw status contract fields.

## p2.10a72 Handbook Latest-state sync

p2.10a72 synchronizes the English and Chinese developer handbooks after the `v0.3.9-alpha` closeout and VM validation. It is a documentation-only state correction node.

Trusted current state after this node:

- `master = origin/master = 6ea67b2`
- `v0.3.9-alpha = 6ea67b2`
- `p2.10a71-docs-prerelease-notes = 6ea67b2`
- GitHub Release `CoDeepSeedeX v0.3.9-alpha` is non-draft, non-prerelease, and the GitHub Latest Release.
- Release assets are exactly `bootstrap.sh` and `install.sh`.
- Erroneous plain tags `v0.3.9` and `v0.3.5` are absent.
- `dsproxy --version` reports public and internal versions at `6ea67b2`.
- VM installation and runtime validation passed.

This node does not move public Release tags, does not rebuild Release assets, and does not create a GitHub Release.


## p2.10a73 WeClaw status primary-scope contract

p2.10a73 separates latest primary model-call status from latest-any and auxiliary model calls for WeClaw status consumption. It adds usage ledger `session_id` support, `tokens.latest_primary_turn`, `tokens.latest_any_model_call`, `tokens.latest_auxiliary_call`, current-session filtering through `--session-id`, and explicit Compact/Trim `progress_*` fields. Pricing and discount parsing are intentionally deferred to a later node.


## p2.10a74 DeepSeek pricing discount contract

p2.10a74 makes DeepSeek pricing CNY-first and discount-aware.

Contract changes:

1. `dsproxy pricing refresh --json` defaults to the Chinese official pricing page.
2. The parser recognizes the current effective price, original struck-through price, discount label, discount rate, and official discount validity window.
3. `config/pricing.json` stores the bundled official CNY snapshot using current effective prices.
4. `pricing.effective_prices`, `pricing.original_prices`, `pricing.discount`, and `pricing.prices_display` are exposed for WeClaw.
5. WeClaw should display current effective prices and must not infer the discount window or recompute historical turn costs.


## p2.10a75 upgrade, current-session cost, prompt segmentation, and retention progress

p2.10a75 closes the WeClaw p89 contract gaps:

1. `dsproxy upgrade` now follows WeClaw-style same-version semantics: after checking the remote release tag commit, it skips when the target public version and commit match the current runtime, and reinstalls when the same public version points to a different release commit. `--force` / `--force-reinstall` bypasses the skip.
2. `cost.session` is an explicit current-session cost object. Route/profile totals are no longer silently labeled as session cost.
3. Prompt segmentation is session-scoped when `--session-id` is supplied. Route-latest prompt segmentation is not reused for a different active session.
4. Compact/Trim primary progress fields now describe information retention: post-compaction/post-trim chars over raw uncompressed chars. Capacity/trigger progress is exposed separately as `capacity_progress_*`.


## p2.10a76 Tokens aux and Details coverage contract

p2.10a76 closes the WeClaw p92/p93 contract gaps:

1. `tokens.auxiliary_model_calls` now returns an explicit current-session zero object when the active session has no auxiliary model calls: `available=true`, `scope=current_session`, `total_tokens=0`, `model_call_count=0`, and `reason=no_auxiliary_model_call_in_current_session`.
2. `tokens.prompt_subcategory_split` now reports coverage metadata against `latest_primary_turn.summary.prompt_tokens`: `categories_sum_tokens`, `provider_reference_tokens`, `provider_reference_field`, `delta_tokens`, `coverage_complete`, `coverage_scope`, `coverage_basis`, and `delta_reason`.
3. Details remain a local profile-tokenizer estimate over message content and tool-call arguments after dsproxy payload assembly. They are not a complete conservation breakdown of provider prompt tokens unless `coverage_complete=true`.


## p2.10a77 Prompt reconciliation contract

p2.10a77 extends WeClaw Details from simple partial coverage into prompt reconciliation:

1. `tokens.prompt_reconciliation` compares three totals: `prompt_subcategory_split.categories_sum_tokens`, `local_full_observed_prompt_tokens`, and provider-reported `latest_primary_turn.summary.prompt_tokens`.
2. The contract exposes `delta_breakdown`, `delta_status`, `is_accounting_suspect`, `recommended_action`, and a sanitized `prompt_segment_audit`.
3. dsproxy does not assign provider/local deltas to `other_prompt` unless those tokens correspond to observable prompt segments.
4. If local observed prompt tokens match the classified category sum but provider prompt tokens are much larger, dsproxy reports the delta as unexplained provider/template/tokenizer-layer difference and recommends `run_prompt_reconciliation_trace`.
5. The embedded minimum experiment matrix is a live-trace plan, not a fabricated result. Provider prompt usage requires real provider calls.


## p2.10a78 Prompt delta root-cause accounting

p2.10a78 changes prompt reconciliation from an `unknown` alarm into local root-cause accounting:

1. dsproxy now passes the full DeepSeek chat payload into profile-tokenizer accounting, not only `messages`.
2. `observable_payload.components` separately tokenizes message content, serialized messages, tool schema, tool choice, response format, request options, and full serialized payload.
3. `local_full_observed_prompt_tokens` now includes locally observable prompt-bearing API fields such as `tools_schema` in addition to message content.
4. `delta_breakdown.tools_schema_tokens` can explain the common gap where provider `prompt_tokens` exceed Details categories because tool/function schemas are prompt tokens but not message-content Details.
5. Remaining provider delta after observable payload accounting is still reported separately as provider/template/tokenizer overhead; it is not assigned to `other_prompt`.


## p2.10a79 Details origin breakdown

p2.10a79 changes the WeClaw-facing Details contract from a subtotal-centric view to a source-origin view:

1. `prompt_reconciliation.details_origin_breakdown` exposes display-ready token origins: user, history, tool output, system, developer, compaction summary, environment, runtime injected, other prompt, tools schema, message/protocol overhead, and provider residual.
2. `should_display_classified_total=false`; WeClaw should not show a `classified~x/y` subtotal by default.
3. The observed ~8.1k gap is explained primarily by `tools_schema_tokens`, with the remaining visible difference explained by message JSON/protocol/request-option overhead and a small provider/tokenizer residual.
4. `provider_residual` must not be assigned to `other_prompt`; hide it when `abs_tokens` is within tolerance.


## p2.10a80 Docs and latest release handoff

p2.10a80 updates public/user-facing documentation and moves the existing `v0.3.9-alpha` Latest Release to the current master after p2.10a79. The cumulative release notes are maintained in `docs/release-notes-v0.3.9-alpha.md` and on the GitHub Release page. Public tag `v0.3.9-alpha` is intentionally moved only in this release step.

Final verified p2.10a80 Release state:

- `master = origin/master = 80bb0ea`
- `p2.10a80-docs-release-latest = 80bb0ea`
- `v0.3.9-alpha = 80bb0ea`
- GitHub Release `CoDeepSeedeX v0.3.9-alpha` is non-draft, non-prerelease, and the GitHub Latest Release.
- Release assets are exactly `bootstrap.sh` and `install.sh`.
- Erroneous plain tags `v0.3.9` and `v0.3.5` are absent.
- Full tests passed before the Release update.

## p2.10a81 Handbook current-state sync

p2.10a81 is a documentation and runtime internal-version sync after p2.10a80. It corrects stale handbook startup state from `6ea67b2` / `p2.10a71-docs-prerelease-notes` to the p2.10a80 public Release baseline at `80bb0ea`, clarifies that the current cumulative release-note source is the only active release-note file under `docs/`, and advances the developer internal checkpoint to `p2.10a81-handbook-current-state-sync`.

This node must not move `v0.3.9-alpha`, recreate the GitHub Release, or rebuild Release assets.


## p2.10a82 Append-only upstream payload trace

p2.10a82 adds an opt-in append-only upstream payload trace for diagnosing what Codex sends through the active profile route. Set `DEEPSEEK_PROXY_PAYLOAD_TRACE_DIR` to an absolute directory under `/tmp` to enable it.

The trace is local-only and disabled by default. Each `DeepSeekClient.chat_completions()` call writes one JSON event containing sanitized raw payload, payload summary, request purpose metadata, duplicate-content hashes, role character totals, tools schema size, and the context trimming report. The trace does not change prompt assembly, model selection, compaction, trimming, provider calls, pricing, or Release metadata.

This node is for observability only. It must not be treated as a payload reduction, prompt cache, or semantic compaction implementation. Public `v0.3.9-alpha` remains at `80bb0ea`.


## p2.10a83 DeepSeek cache accounting contract

Adds provider-authoritative DeepSeek prompt cache hit/miss accounting to the usage ledger, WeClaw status, and cost contract. Session, last-turn, and auxiliary cache sections expose request-level `prompt_cache_hit_tokens`, `prompt_cache_miss_tokens`, and cache hit ratio. Cost remains per-turn ledger based and uses hit/miss input prices rather than treating all prompt tokens as cache miss or cache hit. DeepSeek ChatCompletions payloads now set a stable hashed `user_id` by default and canonicalize tools schema ordering to protect DeepSeek context-cache reuse. Segment-level origin splits remain local estimates; provider cache hit/miss is request-level authoritative.

## p2.10a84 Token-first Compact/Trim context contract

p2.10a84 changes the active context-window contract from an auto-compact-threshold display to a token-first model-window display.

Rules:

1. Managed Codex profiles keep `model_context_window = 1000000` for the DeepSeek V4 profile line.
2. Managed Codex profiles derive `model_auto_compact_token_limit` from the only managed ratio, `auto_compact_ratio = 0.90`, so the default threshold is `900000`.
3. WeClaw and CLI status must display `context_window.display_limit_tokens` from `model_context_window_tokens`, not from `model_auto_compact_token_limit`.
4. `model_auto_compact_token_limit` is exposed as `auto_compact_threshold_tokens` and remains a trigger threshold, not a context-window denominator.
5. Char-level `runtime_payload_guard`, Compact, and Trim fields remain available as fallback/debug payload guards with `unit=chars`; they must not be merged into the token-level context window.
6. Legacy explicit `--auto-compact-token-limit` input is accepted only for compatibility and ignored by managed profile generation; the threshold is derived from the ratio.

Release boundary: this node does not move public `v0.3.9-alpha`, does not rebuild Release assets, and does not update GitHub Release notes.
