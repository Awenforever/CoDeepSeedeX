# CodeXchange Developer Handbook

This is the primary developer handbook and the preferred startup context for future AI-assisted development conversations. The Chinese mirror is `docs/developer-handbook.zh-CN.md`.

This handbook is not a historical archive. It keeps the current operating model, project map, release rules, high-priority lessons, and the current handoff state. Detailed chronological records belong in `docs/development-log.md`.

## 1. Documentation architecture

Active user-facing documents:

- `README.md`: English user entry.
- `README.zh-CN.md`: Chinese user entry.
- `TROUBLESHOOTING.md`: user-facing troubleshooting.

Active maintainer documents:

- `docs/developer-handbook.md`: English primary handbook and AI startup context.
- `docs/developer-handbook.zh-CN.md`: Chinese mirror for the human maintainer.
- `docs/development-log.md`: complete chronological development log, read when historical trace-back is needed.

Retired document families must not be reintroduced as active documents: `OPERATIONS.md`, `docs/install.*.md`, `docs/usage.*.md`, `docs/upgrade.*.md`, `docs/security.*.md`, `docs/troubleshooting.*.md`, `docs/handoff-for-developers.*.md`, and `docs/custom_api_handoff.md`. Legacy per-release note fragments under `docs/` stay retired. Public GitHub Release text is maintained on the GitHub Release page; release automation may use a temporary notes file under `/tmp`, but the repository must not keep a long-lived per-release note source. If documentation structure changes, tests must be updated to the new contract. Do not keep ghost documents only to satisfy stale tests.

## 2. Current trusted state

- Local project path: `~/projects/codexchange`
- GitHub repository: `Awenforever/CoDeepSeedeX`
- Primary branch: `master`
- Current public Release: `v0.4.3-alpha`
- Current public Release kind: ordinary GitHub Latest alpha Release, with `isPrerelease=false`
- Current public Release commit: `tag-managed p2.22 closeout release update`
- GitHub Latest ordinary Release: `v0.4.3-alpha`
- GitHub Release title: `CodeXchange v0.4.3-alpha`
- GitHub Release state: `isDraft=false`, `isPrerelease=false`
- Public Release assets: `bootstrap.sh`, `install.sh`
- Public Release asset digests:
  - `bootstrap.sh` sha256: `257456d2724519bf94ad09f4dce038ac23e8fd5ab9da4b117f1ae637164590a4`
  - `install.sh` sha256: `3456aac1f06a45e78c60feb32c12765fb3f8bd38bdb36dd4dead10f3e91de596`
- Current internal development checkpoint: `p2.22a16-release-v043-alpha-update-to-p222-closeout`
- Latest runtime checkpoint included in the public Release: `p2.21a4-codex-wrapper-nonfatal-split-profile`
- Latest closed documentation sync checkpoint: `p2.21a6-docs-public-tag-state-sync`
- Latest provider/profile abstraction checkpoint: `p2.20a2-provider-profile-primary-only-and-real-entry`
- Latest closed ghost audit tool checkpoint: `p2.19a23-profile-drift-failclosed-guard`
- Latest closed test contract pruning checkpoint: `p2.19a14-test-contract-pruning`
- Latest closed provider alias boundary checkpoint: `p2.19a15-provider-alias-boundary`
- Latest closed legacy threshold boundary checkpoint: `p2.19a16-legacy-threshold-boundary`
- Latest closed wrapper path hygiene checkpoint: `p2.19a17-wrapper-path-hygiene`
- Latest closed real-HOME profile model consistency checkpoint: `p2.19a19-real-home-profile-model-consistency`
- Latest closed status JSON and upstream model leakage checkpoint: `p2.19a21-status-json-and-upstream-model-leakage`
- Latest closed profile drift fail-closed guard checkpoint: `p2.19a23-profile-drift-failclosed-guard`
- Current public Release note synchronization checkpoint: `p2.21a4-codex-wrapper-nonfatal-split-profile`
- WeClaw requirement: Requires `weclaw_dev >= v0.1.9-alpha` if WeClaw integration is used.
- Public tags that must not move without an explicit Release-update task:
  - `v0.4.3-alpha = <pending>`
  - `v0.3.9-alpha = 82a4428`
  - `v0.3.8-alpha = dfdc629`
  - `v0.3.7-alpha = 466706f`
  - `v0.3.6-alpha = 7fd8fb6`
  - `v0.3.5-alpha = 53897ad`
- Erroneous plain tags `v0.4.0`, `v0.3.5`, and `v0.3.9` must not exist.

Current closeout evidence:

- Public tag `v0.4.3-alpha = <pending>`.
- Internal checkpoint included in the public Release: `p2.20a2-provider-profile-primary-only-and-real-entry = b11a1c4`.
- GitHub Release is non-draft and non-prerelease.
- GitHub Latest API returns `v0.4.3-alpha`.
- Release assets are exactly `bootstrap.sh` and `install.sh`.
- `cox --version` from the refreshed release line reports `public version: v0.4.3-alpha | b11a1c4`.
- The `p2.19a24` real Codex entry re-test passed after deliberately drifting both managed split profiles to `glm-5.1`; the entry path repaired them and used `deepseek-v4-flash-ascend` without 403/access-denied, default-model leakage, or a `/tmp` wrapper chain.
- This documentation sync may advance `master` beyond the public Release commit. The public `v0.4.3-alpha` tag is being refreshed by this explicit Release-update task to the p2.22 closeout release commit.

## 3. Key file map

- `codexchange_proxy/app.py`: runtime core, Responses-compatible API, DeepSeek/custom provider bridge, tool bridge, provider dispatch, version metadata, debug trace.
- `codexchange_proxy/cli.py`: `cox` CLI, configuration, provider setup, custom provider registry, post-config refresh, doctor commands, upgrade logic.
- `scripts/install.sh`: installer, installed checkout sync, venv setup, wrappers, Codex profiles, guided UI, config initialization, local file backup.
- `bootstrap.sh`: one-line bootstrap entrypoint, dependency handling, install.sh acquisition and fallback.
- `scripts/codex-wrapper.bash`: maintained wrapper template surface where applicable.
- `scripts/audit-ghost-contracts.py`: read-only ghost contract audit tool.
- `config/pricing.json`: bundled pricing snapshot.
- `experiments/model-catalog/cox-proxy-models.json`: managed model catalog.
- `tests/`: regression tests, document contract tests, provider tests, installer tests, upgrade tests, and runtime contract tests.
- `README.md` / `README.zh-CN.md`: user instructions.
- `TROUBLESHOOTING.md`: user troubleshooting.
- `docs/development-log.md`: complete chronological record.

## 4. Current user-visible release surface

### Python subprocess and shell built-ins

subprocess shell-builtin probe rule: when a Python patch, validation, or release script needs shell-only syntax or a shell built-in, invoke it through an explicit shell. For example, use:

```python
subprocess.run(["bash", "-lc", "command -v gh"], ...)
```

Do not write:

```python
subprocess.run(["command", "-v", "gh"], ...)
```

`command` is a shell built-in, not a guaranteed executable on `PATH`; calling it directly from Python can raise `FileNotFoundError` before any useful release or validation action runs. The same rule applies to shell functions and shell-only features such as `source`, `alias`, `set`, `shopt`, `ulimit`, and compound shell syntax. When shell semantics are unnecessary, prefer a direct executable probe such as `shutil.which("gh")` or `subprocess.run(["gh", "--version"], ...)`.


`v0.4.3-alpha` currently covers these user-visible areas:

1. Guided installer and `cox config wizard`
   - Language is part of the guided flow.
   - Model API, Web search API, Image generation API, and Codex wrapper steps use the same arrow-key UI contract.
   - Web search and Image generation steps have step-local hints and do not leak custom model provider summaries.
   - Completion pages summarize the result and keep normal installation one-command oriented.

2. Custom OpenAI-compatible providers
   - Users can assign display-only custom provider names.
   - Multiple custom providers and multiple models per provider are supported through the custom provider registry.
   - The active provider/model is mirrored to the legacy env contract for runtime compatibility.
   - Base URLs pasted with `/chat/completions` are normalized to the OpenAI-compatible `/v1` base URL.
   - Model API validation uses the configured provider/base URL/model context and no longer falls back to DeepSeek official balance checks for custom providers.
   - Model/API-key input guards reject URL/path/control-character/API-key-like strings as model ids.

3. Codex compatibility and wrapper reliability
   - Codex CLI `< 0.134.0` uses legacy `[profiles.*]` tables in `~/.codex/config.toml`.
   - Codex CLI `>= 0.134.0` uses split profile files.
   - Managed profile repair must preserve the layout required by the installed Codex CLI.
   - The generated Codex wrapper resolves the real Codex binary and must not point `REAL_CODEX` at another CodeXchange wrapper or a `/tmp/codexchange-*` test wrapper.
   - Wrapper startup can repair managed profiles, but it must fail closed on persistent profile conflicts.

4. Status and diagnostics
   - `cox profile status` reports profile source and profile layout consistently.
   - For legacy Codex profile tables, `context_window.codex_profile.source` must be `codex_profile.legacy_profile_table`.
   - Managed profile context remains `model_context_window=1000000` and `model_auto_compact_token_limit=900000`.
   - `cox config show
`cox config status` is a read-only alias for `cox config show` and returns the same JSON payload.` and `cox config test-api-key` expose validation method and URL without logging API-key material.

5. Provider bridges
   - Web search tool bridge
   - Image generation tool bridge
   - Web search validation can consume quota.
   - Image generation default validation may be non-generating; real image generation requires explicit `cox doctor providers --live --allow-spend`.

6. Security and logs
   - API keys must remain redacted in logs and status.
   - Real provider E2E scripts must not log signed image URLs, temporary provider URLs, or query-string tokens.

## 5. Version and tag rules

`cox --version` must expose two version sources:

```text
public version: v0.x.y-alpha | <public_release_commit>
internal version: p2.9aN-topic | <internal_commit>
```

For user installations from a public Release tag, the internal version line reports the `p~` tag current when that Release tag was created. For a developer checkout running from `master`, the public version line remains the latest published public Release until the next Release, while the internal version line tracks the latest internal `p~` tag on `master`.

Public release tags use the `v0.x.y-alpha` form during alpha. Do not create plain `v0.3.x` or `v0.4.x` public tags. Internal development tags use the `p` prefix and must not create GitHub Releases.

Package versions in `pyproject.toml` use PEP440, for example `0.4.3a0`.

Files that often need synchronized version edits during release or documentation sync:

- `codexchange_proxy/app.py`
- `pyproject.toml`
- `tests/test_version_metadata.py`
- `tests/test_cli.py`
- `tests/test_docs_release_readiness.py`
- `tests/test_release_metadata_env_sanitization.py`

Each file has its own role. Do not force every version-related file to contain both public and internal tags.

### Version-semantic health rule

Internal `p~` versions are semantic checkpoints, not merely monotonically increasing labels. Manage them actively:

1. Continue the current `pX.YaN` line only while work remains inside the same coherent phase.
2. Start a new `pX.(Y+1)a1` line when a completed plan has closed, a new major technical phase begins, or the old line has become semantically unhealthy.
3. Do not keep stacking patches on an unhealthy phase name just because the next integer is available.
4. Record phase-boundary reasons in this handbook and `docs/development-log.md`.
5. Public `v*` Release tags remain separate and must not move unless the user explicitly requests a Release update.

## 6. Release state machine

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
11. Create or update GitHub Release and upload `bootstrap.sh` and `install.sh`.
12. Verify release assets, tags, old tags, Latest state, and absence of erroneous plain tags.
13. Validate install/upgrade on a VM or real-home path when the change affects installed user behavior.

Push over HTTPS by default. Do not rely on SSH port 22. Every network step must have a timeout.

GitHub Release notes must not repeat the release title. Public Release notes must be user-facing, feature-focused, and written from a temporary `/tmp` notes file or GitHub API body, not from a tracked repository note file.

## 7. Failure-prevention and release lessons

These rules are mandatory development controls.

### 7.1 Avoidable failure classes

1. **Script variable scope.** Shell variables such as `ts`, `out`, and `run_id` do not exist inside Python heredocs unless passed through environment variables. Use one canonical run identifier and read it from `os.environ` or command arguments.
2. **Source anchors.** Do not patch from memory. When anchors are uncertain, repeated, shifted by a half-applied patch, or embedded in generated shell templates, audit the real source first.
3. **Replacement discipline.** Prefer function-level, section-level, block-level, or AST-based whole replacement. For Python tests and functions, replace the whole `def`. For Markdown, replace whole heading sections or the whole document when doing a handbook reset. For shell templates, replace the whole generated function or heredoc body. Avoid narrow string anchors except for stable constants.
4. **Helper function semantics.** Read helper definitions before using them in tests or patch scripts. Do not assume a helper parameter accepts arbitrary text when it expects a function name or structured marker.
5. **Regex boundaries.** Regex patching is acceptable only when the boundary is stable and verified.
6. **Pre-test marker checks.** Before pytest, assert that intended markers exist and old forbidden markers are gone.
7. **Two-phase heavy changes.** For broad installer, wrapper, profile, or Release changes, first patch and test locally. Only after focused and full tests pass should a script commit, tag, push, merge, or rebuild Release assets.
8. **Acceptance criteria must match the user-visible defect.** Do not record compatibility fallback as a fix when the defect is visible UI or profile behavior.
9. **Integration surfaces are part of every task.** Every development task must explicitly consider install, upgrade, uninstall, rollback, generated wrappers, user config files, Release assets, and VM/user-path validation when changed behavior can affect them.
10. **Runtime observations outrank assumptions.** For terminal, wrapper, Codex TUI, and provider behavior, validate with isolated runtime probes before patching.
11. **Test environment contamination.** A dirty developer shell can make full tests fail for unrelated reasons. Rerun failing subsets and full tests under a sanitized environment before attributing failure to a patch.
12. **AnyCodeX future-name boundary.** CodeXchange remains the current project and public product name. AnyCodeX is a future plan name, not a current code, command, tag, branch, installer, wrapper, public path, or user-facing documentation name.
13. **Full-source-first audit rule.** For source or documentation changes, prefer complete source files and source documents. `grep`, `rg`, and narrow snippets may identify candidates, but patch design must rely on inspected full files or complete function/module/section context.
14. **Do not appease stale tests.** If a test asserts obsolete behavior or ghost documents, update the test contract. Do not preserve dead code or dead documents just to satisfy historical assertions.

### 7.2 Release-specific guardrails

- Do not hard-code runtime version paths. The runtime file is `codexchange_proxy/app.py`.
- Do not assume only one Python file contains version metadata.
- Runtime version metadata is dual-track: public `v~` for the published Release, internal `p~` for the development checkpoint.
- Release scripts must be idempotent and resume-aware.
- Git push must use HTTPS and timeout controls.
- Public release tags should be pushed late to avoid half-published states.
- `gh release view --json` must not rely on unsupported fields such as `isLatest`.
- Release notes must not duplicate the GitHub Release title.
- Documentation refactors must update the test contract.
- The developer handbook must not become a long archive.

### 7.3 Upgrade and uninstall scope rule

Any development task that can affect an installed user environment must include install, upgrade, and uninstall in the design review. At minimum, check one-line bootstrap, `scripts/install.sh`, `cox upgrade`, generated `cox` or `codex` wrappers, `~/.codex/config.toml`, local env files, manifest-backed rollback, source archive fallback, and Release assets.

## 8. Installer, wizard, and local file ownership rules

The installer must back up local files before overwriting them. Important paths:

- `~/.config/codexchange/env`
- `~/.local/bin/cox`
- `~/.local/bin/codex`
- `~/.codex/config.toml`
- dirty and untracked files inside the installed checkout

Unknown user-owned `codex` or `cox` files under `~/.local/bin` must not be silently overwritten. Known CodeXchange-managed wrappers may be backed up and refreshed.

Installer TTY menus use the arrow-key guided UI: `↑/↓` or `j/k`, Enter to select, Backspace to go back. Do not reintroduce old numeric TTY prompts. Non-TTY fallback must remain explicit and machine-readable.

Guided UI hints must be scoped to the current step. Model API details must not leak into Web search or Image generation prompts.

## 9. Provider and custom API handoff

Provider-related behavior must remain consistent across runtime, CLI, installer, README, and tests.

Key paths:

- `codexchange_proxy/app.py`
- `codexchange_proxy/cli.py`
- `scripts/install.sh`
- `README.md`
- `README.zh-CN.md`
- `TROUBLESHOOTING.md`

Custom OpenAI-compatible provider rules:

- Provider name is display-only and for user switching.
- Model name must be the exact upstream model id.
- Base URL must be the upstream OpenAI-compatible `/v1` endpoint.
- A single provider may have multiple models.
- Users must be able to add providers, add models to existing providers, and switch the active model.
- Runtime compatibility is preserved through the legacy env mirror: `COX_MODEL_PROVIDER=custom`, `COX_MODEL_BASE_URL`, `COX_MODEL`, and `COX_MODEL_API_KEY`.

Provider bridge terminology contract:

- Web search tool bridge
- Image generation tool bridge

Web search validation may perform live provider checks and can consume quota. Image generation validation is not necessarily a real generation test unless explicitly requested through:

```bash
cox doctor providers --live --allow-spend
```

Do not add a separate `cox config test-provider --kind web-search|image --provider <name>` command unless explicitly requested.

Zhipu and Z.AI image endpoints must remain separated. Provider diagnostics must not treat a generic image API key as proof that every image provider is configured. Qwen/DashScope provider diagnostics must respect regional image endpoints.

Model configuration command example that documentation and tests must preserve:

```bash
cox config set-model deepseek-v4-pro
```

Do not restore old hyphenated configuration commands.

## 10. Codex profile and wrapper contract

Codex compatibility is version-dependent:

- Codex CLI `< 0.134.0`: use legacy `[profiles.deepseek]` and `[profiles.cox]` tables in `~/.codex/config.toml`.
- Codex CLI `>= 0.134.0`: use split profile files `~/.codex/deepseek.config.toml` and `~/.codex/cox.config.toml`.

The wrapper contract:

- `REAL_CODEX` must resolve to the actual Codex binary or Node entry, not another CodeXchange wrapper.
- Paths under `/tmp/codexchange-*` must not be selected as real Codex.
- If a valid real Codex cannot be found, fail closed rather than generating a recursive wrapper.
- Managed profile repair must preserve the layout expected by the detected Codex version.
- Legacy profile status must report:
  - `profile_source=legacy_profile_table`
  - `codex_profile_layout=legacy_profile_tables`
  - `context_window.codex_profile.source=codex_profile.legacy_profile_table`

## 11. VM GitHub proxy playbook

When a VMware NAT VM cannot reliably reach GitHub, audit route, DNS, curl, git, proxy listener, and Windows host listener.

Known working pattern for the affected VM:

```text
VM -> 192.168.231.1:7896 -> Windows portproxy -> 127.0.0.1:7892 -> Jilianyun
```

GitHub-specific proxy settings are acceptable inside the VM. Do not treat jsDelivr failures as blocking when GitHub Release assets and `git ls-remote` are stable.

## 12. New conversation startup checklist

Start every new development conversation with a read-only audit before changing anything:

```bash
git branch --show-current
git rev-parse --short HEAD
git rev-parse --short origin/master
git status --short
git rev-parse --short v0.4.3-alpha^{}
git rev-parse --short p2.19a15-provider-alias-boundary^{} || true
git rev-parse --short p2.19a10-guided-installer-contextual-hints^{}
git rev-parse --short refs/tags/v0.4.0^{} || true
git rev-parse --short refs/tags/v0.3.9^{} || true
git rev-parse --short refs/tags/v0.3.5^{} || true
gh release view v0.4.3-alpha --repo Awenforever/CoDeepSeedeX --json tagName,name,isDraft,isPrerelease,targetCommitish,assets,publishedAt
gh api repos/Awenforever/CoDeepSeedeX/releases/latest --jq '{tag_name:.tag_name,name:.name,draft:.draft,prerelease:.prerelease,target_commitish:.target_commitish,assets:[.assets[].name]}'
cox --version
```

Expected current public Release baseline:

```text
worktree clean
master=origin/master=<current p2.19a25 documentation sync commit>
v0.4.3-alpha=6a96593
p2.19a23-profile-drift-failclosed-guard=6a96593
GitHub Latest Release=v0.4.3-alpha
isDraft=false
isPrerelease=false
assets=[bootstrap.sh, install.sh]
bootstrap.sh sha256=257456d2724519bf94ad09f4dce038ac23e8fd5ab9da4b117f1ae637164590a4
install.sh sha256=81b509239c10c6a911350cda51b744daedb8f0077274d09a1c94519bc4450294
public version: v0.4.3-alpha | 6a96593
internal version: p2.19a25-docs-release-state-sync | <current internal tag commit>
```

Then read `docs/developer-handbook.md`. Read `docs/development-log.md` only when historical trace-back is needed.

## 13. Install and fallback entrypoints

Latest Release bootstrap:

```bash
curl -fsSL https://github.com/Awenforever/CoDeepSeedeX/releases/latest/download/bootstrap.sh | bash
```

Resolved tag fallback:

```bash
tag="v0.4.3-alpha"
curl -fsSL https://github.com/Awenforever/CoDeepSeedeX/raw/refs/tags/${tag}/bootstrap.sh | bash
```

Pinned Release-asset bootstrap:

```bash
curl -fsSL https://github.com/Awenforever/CoDeepSeedeX/releases/download/v0.4.3-alpha/bootstrap.sh | bash -s -- --install-ref v0.4.3-alpha
```

Product uninstall remains installer-owned:

```bash
bash ~/.local/share/codexchange/scripts/install.sh --uninstall
bash ~/.local/share/codexchange/scripts/install.sh --uninstall --remove-files
```

Uninstall must not delete unrelated user files or non-CodeXchange configuration.

## 14. Long-term mainline task checklist

| ID | Mainline task | Expected indicator | Current version / anchor | Current status | Last updated | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| Release | `v0.4.3-alpha` current Latest | GitHub Latest Release exists with `isPrerelease=false`, assets exactly `bootstrap.sh` and `install.sh`, and no duplicate Release title in body. | `v0.4.3-alpha = <pending>` | Closed | 2026-06-08 | Includes the p2.19 custom provider registry, guided UI, Codex compatibility/wrapper hardening, status JSON, auxiliary-model leakage fix, profile-drift fail-closed guard, and real Codex entry validation. |
| Installer UX | Guided installer and wizard consistency | Step-local hints, arrow-key menus, Backspace navigation, concise validation summary, and no cross-step model summary leakage. | `p2.19a10-guided-installer-contextual-hints` | Closed | 2026-06-07 | VM real-home validation passed. |
| Custom providers | Multiple custom OpenAI-compatible providers and models | Users can add providers, add models, switch active provider/model, and validate against configured `/models`. | `p2.19a1` to `p2.19a6` | Closed | 2026-06-06 | Active provider/model mirrors to legacy env for runtime compatibility. |
| Codex compatibility | Version-aware profile layout and safe wrapper | Codex `<0.134` uses legacy tables; Codex `>=0.134` uses split files; `REAL_CODEX` never points to a wrapper. | `p2.19a7` to `p2.19a9` | Closed | 2026-06-07 | Real-home wrapper execution passed. |
| WeClaw | Full telemetry baseline | WeClaw can consume cox-owned status contracts for profile, model, effort, context, usage, pricing, cost, balance, Details, tokenizer, and compaction. | `v0.3.9-alpha = 82a4428` | Closed | 2026-05-24 | Requires `weclaw_dev >= v0.1.9-alpha` if used. |
| Managed tool routing | Web/image provider bridge | Native or managed routing can expose Web search tool bridge and Image generation tool bridge status and diagnostics. | `p2.14a2` to `p2.14a8` | Closed | 2026-05-26 | Real SerpAPI web E2E and Zhipu provider bridge validation were completed; Codex native image_generation was not observed. |
| Token/context | Token-first Compact/TRIM and tokenizer accounting | Provider usage remains billing-authoritative; local tokenizer accounting is display/drift support; token and char units remain separated. | `p2.10a65` to `p2.13a5` | Closed | 2026-05-24 | Do not conflate token context windows with char payload guards. |
| Process | Full-source-first patch discipline | Patch design is based on uploaded complete files or complete copied source/document context, not grep-only snippets. | Handbook rule 7.1.13 | Active rule | 2026-06-07 | Update stale tests rather than preserving ghost behavior. |

Checklist maintenance rules:

1. Update this table whenever a new plan is accepted, a task closes, or a release/handoff changes the active priority.
2. Inserted tasks must return to this checklist when they close.
3. Handoff content must include this table or an exact summary of active rows.
4. A task is not complete until its expected indicator has evidence in logs, tests, tags, Release state, or accepted downstream feedback.


### Provider alias boundary

- `qwen-us` is a current explicit regional model provider and should remain visible in README/CLI model-provider guidance.
- Public Qwen model-provider ids use hyphens (`qwen-beijing`, `qwen-singapore`, `qwen-us`); native adapter ids use underscores (`qwen_beijing`, `qwen_singapore`, `qwen_us`).
- `glm`, `qwen_us`, `qwen_us_virginia`, `dashscope_us`, and Brave web search are hidden/backward-compatible aliases unless a future validation line promotes them explicitly.
- `cox config set-api-key` remains a deprecated compatibility command; user-facing guidance should prefer `cox config set-model`.


### Legacy threshold boundary

- Managed auto-compact threshold configuration remains ratio-first: `model_auto_compact_token_limit` is generated from `model_context_window * 0.90`.
- `model_auto_compact_token_limit`, `auto_compact_token_limit`, and `auto_compact_ratio` are current generated/status fields, not legacy inputs.
- Historical `750000` and `0.75` values may remain only in history or negative guards.
- Legacy absolute-threshold env inputs are compatibility evidence and must be reported as ignored for managed profiles.
- Maintained ghost-audit rules must not classify current 90% fields as old-threshold debt.


### Wrapper path hygiene

- A generated CodeXchange Codex wrapper must never use another CodeXchange wrapper as `REAL_CODEX`.
- `cox profile refresh-wrapper` may recover from a stale manifest `REAL_CODEX` only by selecting a non-CodeXchange real Codex executable from `COX_REAL_CODEX`, `PATH`, or common npm/nvm locations.
- If no safe real Codex executable is available, wrapper refresh must fail closed.
- `/tmp/codexchange-*` test-HOME wrappers are not valid real Codex binaries for real-user wrapper manifests.


### Real-HOME profile model consistency

- The active upstream model in `COX_MODEL` is authoritative for both managed Codex profiles unless `COX_THINKING_MODEL` explicitly overrides `cox`.
- `config set-model`, `set-api-key`, custom-provider activation, and the guided wizard must not leave `deepseek` and `cox` split profiles on different upstream model names.
- Managed Codex profile provider names remain local cox providers (`cox-proxy` and `cox-proxy`); upstream provider/base URL/model are carried by the cox env contract.
- A real-HOME repair must preserve Codex 0.134+ split profile layout and must not reintroduce legacy `[profiles.deepseek*]` tables.


### Status JSON and auxiliary model leakage

- `cox status --json` is the explicit machine-readable alias for normal proxy status JSON.
- `cox status thinking --json` and `cox status --json thinking` must be accepted.
- `--weclaw-json` remains a separate WeClaw-facing contract and must not be conflated with normal proxy status JSON.
- Under `COX_FORCE_MODEL=1`, auxiliary calls such as agent-liveness judge must follow `COX_MODEL` instead of silently selecting a different provider model.
- The status surface should expose the selected auxiliary upstream model so user-path validation can catch leakage before a real model call.


### Profile drift fail-closed guard

- `COX_MODEL` remains the authoritative model source for CodeXchange-managed Codex profiles when `COX_FORCE_MODEL=1`.
- `cox start` and `cox status` run a quiet managed-profile preflight repair from the default env before continuing.
- The preflight disables post-config apply internally to avoid recursive restart/repair loops.
- If repair fails, the CLI route fails closed instead of allowing a stale split profile such as `glm-5.1` to remain active.
- The Codex wrapper launch repair remains required and complementary; status/start preflight protects user and validation paths before Codex is invoked.
