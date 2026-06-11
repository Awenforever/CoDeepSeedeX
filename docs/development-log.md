## p3.0a1-full-test-fix1-codexchange-cox-reasoning-route

- Fixed the p3.0a1 full-test regression by mapping the canonical `cox` profile to the reasoning usage-ledger route.
- Updated remaining CLI version and Chinese README provider-surface assertions after the CodeXchange hard cut.
- Existing pushed p3.0a1 tag is not moved; this fix uses a separate internal full-test fix tag.

## p3.0a1-codexchange-hardcut-generalized-router

- Started the CodeXchange / CoX hard-cut line.
- Renamed the product surface to CodeXchange, the CLI to `cox`, and the Python package to `codexchange_proxy`.
- Moved the product-level configuration namespace to `COX_`.
- Added a hard-cut guard test so retired product markers cannot silently re-enter tracked source.
- Kept DeepSeek as a model provider name while removing it as the product boundary.

## p2.22a1-custom-provider-capability-metadata

Date: 2026-06-10

Scope:

- Added custom-provider capability-aware reasoning-effort handling so custom OpenAI-compatible providers no longer default to Codex-visible `xhigh` unless max reasoning support is explicitly declared.
- Added custom-provider Codex model catalog generation for provider-backed profiles so `model_catalog_json` is present and custom models such as `deepseek-v4-flash-ascend` can be reported with token context metadata.
- Made provider-backed profile status infer thinking route state from the configured local provider base URL instead of only from profile names.
- Hardened local proxy startup against stale pid files that point to live processes not listening on the requested route port.
- Hardened wrapper behavior so unknown `codex --profile <name>` no longer silently falls through to the OpenAI default profile unless a real split profile file exists.

Validation:

- Pending in this run.

Release boundary:

- Internal development node only. Public Release `v0.4.3-alpha` remains pinned at `f8a6635`; no public Release or asset update.

## p2.21a6-docs-public-tag-state-sync

Date: 2026-06-09

Scope:

- Corrected the developer-handbook public tag state line after `v0.4.3-alpha` was refreshed to commit `f8a6635`.
- Advanced the source metadata checkpoint from `p2.21a5-docs-release-state-sync` to `p2.21a6-docs-public-tag-state-sync`.
- Preserved the public Release boundary: no Release refresh, no asset upload, no runtime logic change, and no model/provider call.
- Kept `p2.21a4-codex-wrapper-nonfatal-split-profile` as the latest runtime checkpoint included in the current public Release.

Validation target:

- Documentation release-readiness tests
- Version metadata tests
- Release metadata environment sanitization tests
- Full test suite

## p2.21a5-docs-release-state-sync

Date: 2026-06-09

Scope:

- Synchronized developer-handbook current Release state after `v0.4.3-alpha` was refreshed to the `p2.21a4` public build.
- Updated the recorded `install.sh` Release asset digest to `99a6abfd555646789e0a10ee28760f22d6fa150bdf946e020d9a1eb43594f070`.
- Marked `p2.21a4-codex-wrapper-nonfatal-split-profile` as the latest runtime checkpoint included in the public Release.
- Kept the public Release tag pinned to `v0.4.3-alpha` and did not refresh Release assets in this documentation-only checkpoint.
- Preserved the boundary that this checkpoint changes documentation, metadata, and tests only; no runtime logic and no model/provider calls.

Validation target:

- Release-state documentation tests
- Version metadata tests
- Release metadata environment sanitization tests
- Full test suite

## p2.21a4-codex-wrapper-nonfatal-split-profile

Date: 2026-06-09

Scope:

- Fixed the p2.21a3 real-HOME VM follow-up where installation reached the refreshed `v0.4.3-alpha` build and selected `/usr/bin/python3.11`, but the optional Codex wrapper step returned rc=1 when no real Codex launcher existed behind the existing managed wrapper.
- The Codex wrapper step now skips nonfatally when no real Codex launcher is available, while preserving a clear diagnostic and the boundary that CodeXchange does not install or patch Node.js or Codex.
- The installer now forces the primary managed `cox` profile installation to the Codex 0.134+ split profile-file layout instead of relying on auto layout when Codex cannot be probed.
- The installer removes the deprecated managed `deepseek` profile after installing the primary `cox` profile so stale legacy `[profiles.deepseek]` tables do not survive normal upgrade.
- The CLI upgrade path also forces managed profile refreshes to `split_profile_files`.

Validation target:

- Static regression tests for optional Codex wrapper nonfatal behavior when real Codex is absent
- Static regression tests for installer split-profile layout and deprecated `deepseek` cleanup
- Shell syntax and Python bytecode checks
- Focused installer/wrapper/profile/provider/version/docs tests
- Full test suite
- Release refresh to `v0.4.3-alpha`
- Real-HOME VM upgrade validation

## p2.21a3-installer-python-selection-order

Date: 2026-06-09

Scope:

- Fixed the p2.21a2 installer ordering regression where `PYTHON_BIN` intentionally starts empty until compatible interpreter selection, but the guided setup flow could read existing env values before that selection occurred.
- The VM symptom was `install.sh: line 2913: : command not found` before the requirements check; the failing path was `env_file_value`, which executed an empty `PYTHON_BIN`.
- The installer now selects a compatible Python before env-backed guided setup helpers run, and `ensure_codexchange_python_bin` is idempotent so the later requirements check can safely call it again.
- This preserves the p2.21a2 boundary: CodeXchange selects from existing compatible interpreters, but does not install, patch, or replace Python.

Validation target:

- Static regression tests for Python-selection order before `choose_installer_language` and `env_file_value`
- Installer/wrapper/guided UI focused tests
- Shell syntax and Python bytecode checks
- Full test suite
- Release refresh to `v0.4.3-alpha`
- Real-HOME VM upgrade validation on a non-fresh machine with stale default `/usr/bin/python3` and available `python3.11`

## p2.21a2-installer-python-selection

Date: 2026-06-09

Scope:

- Fixed the real-HOME upgrade blocker where the installer could select a stale generic `python3` interpreter and abort before refreshing an existing installation.
- The installer now resolves a compatible Python interpreter before the requirements check, trying versioned Python commands (`python3.13`, `python3.12`, `python3.11`), the existing managed virtual environment, then generic `python3`/`python`.
- Explicit `--python-bin` / `COX_PYTHON_BIN` remains authoritative; if that explicit interpreter is incompatible, the installer fails with a clear diagnostic instead of silently changing the user's explicit choice.
- When the existing managed virtual environment is the only compatible interpreter, the installer reuses it instead of trying to recreate the same venv with itself.
- CodeXchange still does not install, patch, or replace Python.
- This node is source-only; public `v0.4.3-alpha` must be refreshed after validation.

Validation target:

- Installer Python-selection static contract tests
- install/wrapper/guided UI focused tests
- provider/config focused tests
- shell syntax and Python bytecode checks
- full test suite
- real-HOME VM upgrade validation after Release refresh

## p2.21a1-install-entry-guided-ui-hardening

Date: 2026-06-08

Scope:

- Hardened installed-user Codex entry behavior on the CodeXchange side.
- The installer now persists `~/.local/bin` discovery more broadly and performs post-install entrypoint diagnostics for `cox` and `codex` wrapper precedence.
- Generated Codex wrappers now preflight Node-backed Codex launchers and report a clear CodeXchange diagnostic when Node.js is missing; CodeXchange still does not install or patch Node automatically.
- `cox config wizard` now uses cbreak menu input so terminal output keeps normal line rendering, matching the installer guided UI more closely.
- The config wizard custom-provider path now collects a provider name/profile id, writes the custom provider registry, and syncs a provider-backed Codex profile for `codex --profile <provider-id>`.

Validation target:

- install/wrapper/guided UI focused tests
- provider/config focused tests
- shell syntax and Python bytecode checks
- full test suite
- no public Release/tag movement

Public release:

- No public tag or GitHub Release movement in this source node.

## p2.20a3-dev-handbook-subprocess-shell-builtins

Date: 2026-06-08

Scope:

- Documented the Python subprocess shell-builtin rule in the English and Chinese developer handbooks.
- Captured the release-script lesson that `command -v gh` must be invoked through `bash -lc` when called from Python subprocess, or replaced by a direct executable probe such as `shutil.which("gh")`.
- Added a documentation regression test to prevent the rule from being dropped.
- Synchronized developer-handbook current Release state to refreshed `v0.4.3-alpha` at `b11a1c4`.
- Corrected current-state checkpoint taxonomy so ghost-audit/profile-drift closure remains `p2.19a23`, while Release runtime/provider coverage remains `p2.20a2`.

Validation:

- docs focused tests
- version metadata tests
- shell syntax and Python bytecode checks
- full test suite

Public release:

- No public tag or GitHub Release movement in this docs-only node.

## p2.20a2-provider-profile-primary-only-and-real-entry

Date: 2026-06-08

Scope:

- Make `cox` the only primary managed Codex profile.
- Stop custom provider activation from synchronizing deprecated `deepseek` or managed DeepSeek profiles.
- Keep provider-backed custom profiles independent: `codex --profile <provider-id>` activates that provider and starts the thinking proxy.
- Make wrapper entry fail closed for deprecated `codex --profile deepseek`.
- Remove stable-profile installation from installer and upgrade profile refresh paths.
- Keep Codex TUI `/model` integration unclaimed until real Codex behavior proves profile-level model catalog injection.

Validation target:

- provider/profile isolated CRUD and profile generation
- wrapper/source markers for deprecated `deepseek`
- focused provider/profile tests
- full test suite
- no public Release/tag movement

## p2.20a1-provider-profile-abstraction

Date: 2026-06-08

Scope:

- Start the provider/profile abstraction line.
- Add top-level `cox provider` alias for named custom OpenAI-compatible providers.
- Add provider CRUD and model management actions for custom providers.
- Generate provider-backed Codex split profiles so users can run `codex --profile <provider-id>`.
- Keep custom provider validation on the OpenAI-compatible `/models` path, not the DeepSeek account balance endpoint.
- Keep Codex TUI `/model` integration explicitly unclaimed until real Codex behavior proves it reads profile-level model catalogs.
- Keep ordinary `deepseek` profile as legacy compatibility in this foundation node; `cox` remains the preferred primary DeepSeek entry.

Validation target:

- focused provider/profile tests
- full test suite
- no public Release/tag movement

## p2.19a25-docs-release-state-sync — Documentation sync after v0.4.3-alpha refresh

Date: 2026-06-08

Scope:

- Synchronize the English and Chinese developer handbooks after refreshing the public `v0.4.3-alpha` Latest Release to `p2.19a23-profile-drift-failclosed-guard`.
- Record the current public Release baseline: `v0.4.3-alpha = 6a96593`, GitHub Release non-draft and non-prerelease, Latest API returning `v0.4.3-alpha`, and Release assets exactly `bootstrap.sh` and `install.sh`.
- Record refreshed asset digests: `bootstrap.sh` sha256 `257456d2724519bf94ad09f4dce038ac23e8fd5ab9da4b117f1ae637164590a4` and `install.sh` sha256 `81b509239c10c6a911350cda51b744daedb8f0077274d09a1c94519bc4450294`.
- Record that `p2.19a24` was a real Codex entry validation node, not a source commit node.
- Keep public GitHub Release notes on the GitHub Release page only; do not add tracked per-release note files under `docs/`.
- Advance runtime internal version metadata to `p2.19a25-docs-release-state-sync` while keeping public version `v0.4.3-alpha`.

Validation target:

- `git diff --check`
- `bash -n bootstrap.sh scripts/install.sh`
- Python compile for touched files and focused tests
- full test suite
- post-merge verification that `v0.4.3-alpha` remains at `6a96593` until a future explicit Release-update task.

Release boundary:

- This documentation node does not move `v0.4.3-alpha`, does not rebuild Release assets, and does not edit the GitHub Release body.

## v0.4.3-alpha Latest refresh to p2.19a23

Date: 2026-06-08

Scope:

- Move the public `v0.4.3-alpha` Release/tag from `01d6cee` to `6a96593` after p2.19a23 closure and p2.19a24 real Codex entry validation.
- Preserve GitHub Release title `CodeXchange v0.4.3-alpha`.
- Keep GitHub Release as non-draft and non-prerelease, making it the current Latest ordinary Release.
- Re-upload Release assets `bootstrap.sh` and `install.sh`.
- Write public Release notes from a temporary `/tmp` file only; no tracked per-release note file is added under `docs/`.

Final state:

- `master = origin/master = 6a96593` at the time of Release refresh.
- Public tag `v0.4.3-alpha = 6a96593`.
- Internal checkpoint included in the Release: `p2.19a23-profile-drift-failclosed-guard = 6a96593`.
- GitHub Release `CodeXchange v0.4.3-alpha`: `isDraft=false`, `isPrerelease=false`.
- GitHub Latest API returns `v0.4.3-alpha`.
- Release assets are exactly `bootstrap.sh` and `install.sh`.
- Asset digests:
  - `bootstrap.sh` sha256 `257456d2724519bf94ad09f4dce038ac23e8fd5ab9da4b117f1ae637164590a4`
  - `install.sh` sha256 `81b509239c10c6a911350cda51b744daedb8f0077274d09a1c94519bc4450294`

Release-note coverage:

- Custom provider profile/model consistency for managed Codex profiles.
- `cox status --json` normal status output and separate `--weclaw-json` contract.
- Auxiliary agent-liveness model selection under forced/custom model configuration.
- Runtime-entry managed profile drift guard with fail-closed behavior.
- Wrapper path hygiene and `/tmp` wrapper-chain prevention.
- Provider alias and legacy threshold boundaries.
- Managed tool routing diagnostics.

Validation evidence before Release:

- p2.19a23 full test suite passed.
- p2.19a24 real Codex entry validation passed after deliberately drifting both split profiles to `glm-5.1`; the entry path repaired profiles and used `deepseek-v4-flash-ascend` without 403/access-denied, default-model leakage, or `/tmp` wrapper-chain residue.

## p2.19a23-profile-drift-failclosed-guard — Runtime-entry managed profile drift guard

Date: 2026-06-08

Scope:

- Close the real-HOME profile drift gap observed after p2.19a22.
- Add a CLI-route preflight guard that repairs CodeXchange-managed split Codex profile models from the default cox env before `cox start` and `cox status` continue.
- The guard uses `profile repair --managed-only` semantics internally, disables post-config apply during the guard to avoid recursion, and fails closed if the repair itself fails.
- This makes the runtime/status entry path self-healing for stale split profiles such as `glm-5.1` while the env forces `deepseek-v4-flash-ascend`.
- Existing Codex wrapper launch repair remains in place; this node extends the protection to cox CLI startup/status paths.
- No model-provider call is required for validation.
- Do not move `v0.4.3-alpha` and do not rebuild Release assets.

Validation target:

- `git diff --check`
- `bash -n bootstrap.sh scripts/install.sh`
- Python compile for touched files
- maintained ghost audit smoke with `must_fix=0`
- focused p2.19a23 tests
- full test suite
- real-HOME validation: deliberately drift both split profiles to `glm-5.1`, then prove `status thinking --json` and `start thinking` repair them back to the env-selected model.

## p2.19a21-status-json-and-upstream-model-leakage — Status JSON and auxiliary model leakage boundary

Date: 2026-06-07

Scope:

- Add `cox status --json` as an explicit machine-readable alias for normal status output.
- Preserve existing `cox status thinking` JSON behavior.
- Keep `--weclaw-json` as the WeClaw-specific status contract.
- Fix auxiliary agent-liveness judge upstream model selection under forced/custom model configuration.
- When `COX_FORCE_MODEL=1` and `COX_MODEL` is set, liveness judge upstream calls now follow the forced upstream model instead of silently normalizing the default no-thinking alias to a different provider model.
- This closes the real-HOME leakage where the runtime status showed an agent-liveness judge upstream model that could request an inaccessible default model even though the main profile used the env-selected custom model.
- No model-provider call is needed for validation; local status endpoints and CLI status are sufficient.
- Do not move `v0.4.3-alpha` and do not rebuild Release assets.

Validation target:

- `git diff --check`
- `bash -n bootstrap.sh scripts/install.sh`
- `python -m py_compile` for touched Python files
- maintained ghost audit smoke with `must_fix=0`
- focused CLI status/liveness/docs/version tests
- full test suite
- real-HOME local status validation: `cox status thinking --json` returns JSON and agent-liveness `upstream_model` matches the forced env-selected model.

## p2.19a19-real-home-profile-model-consistency — Real-HOME split-profile model consistency

Date: 2026-06-07

Scope:

- Fix managed Codex split-profile model synchronization after model API configuration changes.
- `cox config set-model` and the deprecated compatibility alias `cox config set-api-key` now sync the selected upstream model to all managed Codex profiles by default (`deepseek` and `cox`), unless the user explicitly passes `--profile`.
- Custom-provider activation and guided wizard configuration sync managed Codex profile models when operating on the default real-user env file.
- `profile repair` now honors an explicit `COX_THINKING_MODEL` / `COX_REASONING_MODEL` override for `cox`; otherwise both managed profiles use `COX_MODEL`.
- Keep provider blocks as local cox providers (`cox-proxy` and `cox-proxy`); the upstream provider/base URL/model remain cox env concerns.
- Repair the observed real-HOME drift where env selected `custom/deepseek-v4-flash-ascend` while `~/.codex/cox.config.toml` still contained `glm-5.1`.
- Do not move `v0.4.3-alpha` and do not rebuild Release assets.

Validation target:

- `git diff --check`
- `bash -n bootstrap.sh scripts/install.sh`
- `python -m py_compile` for touched Python files
- maintained ghost audit smoke with `must_fix=0`
- focused config/profile/docs/version tests
- full test suite
- real-HOME profile repair and consistency check: both split profiles match the env-selected model unless an explicit thinking model is configured

## p2.19a17-wrapper-path-hygiene — Codex wrapper path hygiene

Date: 2026-06-07

Scope:

- Harden managed Codex wrapper refresh when the install manifest contains a stale or unsafe `REAL_CODEX`.
- Keep the existing fail-closed guard for wrapper-to-wrapper recursion.
- Add safe recovery: if manifest `REAL_CODEX` points to a CodeXchange wrapper, to the wrapper itself, or to a stale `/tmp/codexchange-*` wrapper, `cox profile refresh-wrapper` now searches `COX_REAL_CODEX`, current `PATH`, and common npm/nvm Codex locations for a non-CodeXchange real Codex executable.
- If no safe real Codex executable exists, refresh still fails closed with `real_codex_points_to_codexchange_wrapper`.
- Preserve the real-user invariant: generated wrappers must not use another CodeXchange wrapper as `REAL_CODEX`, and must not use a prior test-HOME `/tmp/codexchange-*` wrapper as `REAL_CODEX`.
- Do not clean `/tmp` as a substitute for fixing source behavior.
- Do not move `v0.4.3-alpha` and do not rebuild Release assets.

Validation target:

- `git diff --check`
- `bash -n bootstrap.sh scripts/install.sh`
- `python -m py_compile` for touched Python files
- maintained ghost audit smoke with `must_fix=0`
- focused wrapper/profile/docs/version tests
- full test suite

## p2.19a16-legacy-threshold-boundary — Legacy threshold audit boundary

Date: 2026-06-07

Scope:

- Clarify the managed auto-compact threshold boundary after the p2.19a16 audit.
- Keep the runtime and profile contract unchanged: managed profiles derive `model_auto_compact_token_limit` from `model_context_window * 0.90`; for the 1M-token DeepSeek profile this remains `900000`.
- Keep `model_auto_compact_token_limit`, `auto_compact_token_limit`, and `auto_compact_ratio` as current generated/telemetry fields, not legacy input contracts.
- Keep stale absolute threshold and ratio inputs as ignored/compatibility evidence only:
  - historical `750000` and `0.75` remain history or negative-guard material.
  - `COX_AUTO_COMPACT_THRESHOLD_TOKENS` and `COX_MODEL_AUTO_COMPACT_TOKEN_LIMIT` remain legacy absolute-threshold inputs and are reported as ignored by managed runtime code.
  - `COX_AUTO_COMPACT_RATIO` and `COX_AUTO_COMPACT_RATIO` remain ignored legacy ratio overrides for managed profiles.
- Narrow the maintained ghost-audit threshold pattern so it no longer classifies current 90% fields as old-threshold review debt.
- Do not move `v0.4.3-alpha` and do not rebuild Release assets.

Validation target:

- `git diff --check`
- `bash -n bootstrap.sh scripts/install.sh`
- `python -m py_compile` for touched Python files
- maintained ghost audit smoke with `must_fix=0`
- focused ghost-audit/docs/version/threshold tests
- full test suite

## p2.19a15-provider-alias-boundary — Provider alias public/compatibility boundary

Date: 2026-06-07

Scope:

- Classify provider and command alias surfaces instead of deleting compatibility paths blindly.
- Keep `qwen-us` as a current explicit regional model provider; it is not a legacy shortcut.
- Keep `glm`, `qwen_us`, `qwen_us_virginia`, `dashscope_us`, and Brave runtime paths as hidden/backward-compatible aliases where existing configurations may still depend on them.
- Remove or de-emphasize deprecated aliases from user-facing supported-provider summaries:
  - unsupported image provider messages no longer list `glm` as a current public provider.
  - unsupported web search provider messages no longer list Brave as a current public provider.
  - `cox config status` supported image provider catalog no longer promotes `glm` or `dashscope` shortcuts.
- Keep `cox config set-api-key` as a compatibility command, but mark it as deprecated and point users to `cox config set-model`.
- Refine ghost audit rules so `qwen-us` is treated as current public regional provider, while `glm`, Brave, and `set-api-key` remain review-only alias-boundary markers.
- Do not move `v0.4.3-alpha` and do not rebuild Release assets.

Validation target:

- `git diff --check`
- `bash -n bootstrap.sh scripts/install.sh`
- `python -m py_compile` for touched Python files
- maintained ghost audit smoke with `must_fix=0`
- focused provider alias/readme/CLI/status/version tests
- full test suite

## p2.19a14-test-contract-pruning — Stale test contract pruning

Date: 2026-06-07

Scope:

- Refine the maintained ghost audit tool so tests are not blindly classified as `must_fix` merely because they contain current-contract, negative-guard, compatibility, or audit-fixture strings.
- Keep true positive stale assertions as `must_fix`, but classify deprecated provider aliases and legacy threshold assertions as `review` for p2.19a15/p2.19a16.
- Split stale Release strings in negative guards and audit fixtures so repository self-audits do not treat those tests as live stale contracts.
- Keep developer handbooks and development-log tests intentional; avoid treating maintainer docs as production runtime surfaces.
- Narrow Release asset entrypoint tests to user-facing install/usage documents rather than maintainer handoff documents.
- Do not move `v0.4.3-alpha` and do not rebuild Release assets.

Validation target:

- `git diff --check`
- `bash -n bootstrap.sh scripts/install.sh`
- `python -m py_compile` for touched Python files
- maintained ghost audit smoke with `must_fix=0`
- focused test-contract/audit/docs/version tests
- full test suite

## p2.19a13-user-facing-release-state-cleanup — User-facing ghost surface cleanup

Date: 2026-06-07

Scope:

- Clean user-facing README wording so the current `v0.4.3-alpha` Latest ordinary Release is no longer described as the current pre-release channel.
- Keep `cox upgrade --alpha` documented only as a future/non-draft GitHub pre-release channel.
- Simplify the WeClaw integration requirement to the current public Release instead of listing older public Release tags in the user README.
- Replace site-specific custom provider examples in installer and CLI help with generic placeholders: `ExampleProvider`, `https://api.example.com/v1`, and `your-model-id`.
- Update custom-provider tests so they validate generic OpenAI-compatible provider behavior without making USTC a public contract.
- Fix the visible `DEPPSEEK_PROXY...` diagnostic typo to `DEEPSEEK_PROXY...`.
- Refine the ghost audit tool so its own pattern definitions do not count as user-facing must-fix findings and so current guided UI step labels are not misclassified as old numeric UI prompts.
- Do not move `v0.4.3-alpha` and do not rebuild Release assets.

Validation target:

- `git diff --check`
- `bash -n scripts/install.sh`
- `python -m py_compile` for touched Python files
- focused README/installer/CLI/custom-provider/audit/docs/version tests
- full test suite

## p2.19a12-ghost-audit-tool-fixup — Maintained ghost contract audit tool

Date: 2026-06-07

Scope:

- Add a maintained read-only ghost contract audit tool at `scripts/audit-ghost-contracts.py`.
- Fix the ad-hoc p2.19a12 audit failure class where AST assertion findings lacked `raw_category` and caused TSV/report generation to fail with `KeyError('raw_category')`.
- Classify findings into `must_fix`, `review`, and `allowed` so broad scans do not become blind deletion lists.
- Keep compatibility markers such as Codex legacy profile layout, wrapper recursion guards, and managed 90% auto-compact threshold as review candidates rather than automatic deletion targets.
- Add regression tests for the audit script schema, output files, and current-repository read-only execution.
- Do not move `v0.4.3-alpha` and do not rebuild Release assets.

Validation target:

- `python -m py_compile scripts/audit-ghost-contracts.py`
- focused audit-tool tests
- docs/version metadata tests
- full test suite

## p2.19a11-docs-release-handoff-sync — Documentation release handoff sync

Date: 2026-06-07

Scope:

- Documentation-only closeout after the `v0.4.3-alpha` Release refresh to `01d6cee`.
- Rewrite `docs/developer-handbook.md` and `docs/developer-handbook.zh-CN.md` into current handoff manuals rather than long historical archives.
- Remove stale current-state claims that still described `v0.4.3-alpha` as a pre-release or described `v0.4.0-alpha` as Latest.
- Record the current trusted state: `master=origin/master=01d6cee`, `v0.4.3-alpha=01d6cee`, GitHub Release non-draft and non-prerelease, Latest API returns `v0.4.3-alpha`.
- Record Release asset digests: `bootstrap.sh` sha256 `257456d2724519bf94ad09f4dce038ac23e8fd5ab9da4b117f1ae637164590a4`; `install.sh` sha256 `3403a77bf8935c5f8514cf44656308e52696e2026931133e83858b9f975502f9`.
- Keep detailed historical chronology in this `docs/development-log.md` file.
- Do not refresh Release assets in this documentation node.

Validation target:

- `git diff --check`
- `python -m py_compile codexchange_proxy/app.py`
- focused documentation/version tests
- full tests

## v0.4.3-alpha Release refresh to p2.19a10

Date: 2026-06-07

Scope:

- Move the public `v0.4.3-alpha` Release/tag to `01d6cee` after p2.19a10 VM real-home validation.
- Preserve GitHub Release title `CodeXchange v0.4.3-alpha`.
- Keep GitHub Release as non-draft and non-prerelease, making it the current Latest ordinary Release.
- Re-upload Release assets `bootstrap.sh` and `install.sh`.
- Write public Release notes from a temporary `/tmp` file only; no tracked per-release note file is added under `docs/`.

Final state:

- `master = origin/master = 01d6cee`.
- Public tag `v0.4.3-alpha = 01d6cee`.
- Internal checkpoint included in the Release: `p2.19a10-guided-installer-contextual-hints = 01d6cee`.
- GitHub Release `CodeXchange v0.4.3-alpha`: `isDraft=false`, `isPrerelease=false`.
- GitHub Latest API returns `v0.4.3-alpha`.
- Release assets are exactly `bootstrap.sh` and `install.sh`.
- Asset digests:
  - `bootstrap.sh` sha256 `257456d2724519bf94ad09f4dce038ac23e8fd5ab9da4b117f1ae637164590a4`
  - `install.sh` sha256 `3403a77bf8935c5f8514cf44656308e52696e2026931133e83858b9f975502f9`

Release-note coverage:

- Guided installer contextual hints.
- Custom OpenAI-compatible provider registry, multiple providers, multiple models, and active-model switching.
- Custom provider validation using configured OpenAI-compatible `/models` endpoint.
- Model input/API-key pollution guards.
- Codex version-aware legacy/split profile layout.
- Codex wrapper real-binary resolution and recursive-wrapper prevention.
- Legacy profile status/context-window source consistency.
- API-key redaction and backup behavior.
- VM real-home validation and local full-suite validation.

Validation evidence before Release:

- Local full test suite passed: `629 passed, 1 skipped`.
- VM real-home validation passed for custom provider configuration, Codex wrapper execution, legacy Codex profile layout, context-window profile-source consistency, guided-hint contamination checks, and absence of `/tmp/codexchange-*` in the installed wrapper.


## p2.19a10-guided-installer-contextual-hints — Guided installer contextual hints

Date: 2026-06-07

Scope:

- Keep public `v0.4.3-alpha` unrefreshed until final validation and release refresh.
- Fix guided installer hint leakage where a custom model provider summary could appear on Web search or Image generation prompts.
- Give Model API, Web search API, and Image generation API yes/no prompts explicit step-local hints.
- Preserve p2.19a7/p2.19a8/p2.19a9 runtime and wrapper contracts.

## p2.19a9-context-window-profile-source-consistency — Context-window profile source consistency

Date: 2026-06-06

Scope:

- Keep public `v0.4.3-alpha` unrefreshed until final VM validation and release refresh.
- Align `context_window.codex_profile.source` with the profile source used by `cox profile status`.
- When `profile_source=legacy_profile_table`, report `context_window.codex_profile.source=codex_profile.legacy_profile_table` instead of the stale `codex_split_profile_file` label.
- Preserve the p2.19a8 real Codex binary wrapper fix and p2.19a7 legacy layout status contract.

## p2.19a8-codex-wrapper-real-binary-resolution — Codex wrapper real binary resolution

Date: 2026-06-06

Scope:

- Keep public `v0.4.3-alpha` unrefreshed until VM wrapper validation passes.
- Fix installer real Codex resolution so CodeXchange never writes a wrapper whose `REAL_CODEX` points to another CodeXchange wrapper.
- Skip managed wrappers, temporary `/tmp/codexchange-*` wrappers, and the destination wrapper path while resolving the real Codex command.
- Fail closed for invalid `COX_REAL_CODEX` and stale refresh-wrapper manifests that point to a managed wrapper.

## p2.19a7-codex-wrapper-env-and-status-layout — Codex wrapper environment and status layout

Date: 2026-06-06

Scope:

- Keep public `v0.4.3-alpha` unrefreshed until VM wrapper validation passes.
- Prevent the Codex wrapper launch-time repair step from converting Codex `<0.134` legacy profile tables into split profile files before invoking real Codex.
- Ensure status/profile/runtime contracts report `legacy_profile_tables` when values are loaded from `[profiles.*]` legacy tables.
- For legacy profile tables, report `codex_profile_config` as the main `config.toml`, not the non-existent split profile file.

## p2.19a6-installer-ux-and-codex-detection-finalize — installer UX and Codex detection finalize

Date: 2026-06-06

Scope:

- Keep the public `v0.4.3-alpha` release rolled back until VM user-path validation passes.
- Finalize the custom provider empty-state menu so unavailable existing-provider actions are not shown before a provider exists.
- Render saved custom provider selection through the guided arrow-key UI instead of exact-name text entry.
- Replace completion-page `Next commands` wording with `Start using CodeXchange` and `Optional verification`.
- Remove the old post-install command dump from the default guided install path.
- Make unknown Codex CLI version resolve to legacy main-config profile tables instead of split profile files.
- Preserve explicit `--profile-layout split_profile_files` and the Codex `>= 0.134.0` split-profile path.
- Do not refresh Release assets in this patch step.

## p2.19a5-codex-version-layout-compat — Codex version-aware profile layout compatibility

Date: 2026-06-06

Scope:

- Keep the public `v0.4.3-alpha` release rolled back until VM user-path validation passes.
- Make managed Codex profile installation version-aware.
- Codex CLI `>= 0.134.0` keeps the split profile file layout.
- Codex CLI `< 0.134.0` uses legacy named profile tables for the managed deepseek and cox profiles in the main `config.toml` so older Codex can resolve profiles.
- Expose `codex_cli_version`, `codex_profile_layout`, and `layout_reason` in install-codex-profile JSON output.
- Preserve p2.19 custom provider registry and guided UI work.
- Do not refresh Release assets in this patch step.

## p2.19a4-custom-provider-backstep-chain — custom provider Backspace chain

Date: 2026-06-06

Scope:

- Keep the public `v0.4.3-alpha` release rolled back until VM user-path validation passes.
- Fix the custom provider setup Backspace chain so each field returns to the immediate previous step.
- New custom provider path now follows: API key → Model name → Base URL → Provider name → Custom provider setup → provider family.
- Existing-provider paths now return from provider-name selection to the custom provider setup menu, not directly to provider family.
- Preserve p2.19a1 registry support, p2.19a2 guided custom provider UI, and p2.19a3 generic provider-name default.
- Do not refresh Release assets in this patch step.

## p2.19a3-generic-custom-provider-default — generic custom provider default

Date: 2026-06-06

Scope:

- Keep the public `v0.4.3-alpha` release rolled back until VM user-path validation passes.
- Remove the site-specific `USTC` default from the installer Provider name page.
- Keep Provider name display-only and let an empty entry fall back internally to the generic `Custom Provider` label.
- Preserve p2.19a1 registry support and p2.19a2 guided custom provider UI.
- Do not refresh Release assets in this patch step.

## p2.19a2-custom-provider-guided-ui — custom provider guided UI

Date: 2026-06-06

Scope:

- Keep the public `v0.4.3-alpha` release rolled back until VM user-path validation passes.
- Connect installer custom provider setup to the p2.19a1 registry foundation.
- Fix Provider name Backspace routing so it returns to provider-family selection rather than looping on itself.
- Add installer custom-provider modes: use existing, add new, add model to existing, and switch active model.
- Keep the active custom provider/model mirrored to the legacy env contract.
- Do not refresh Release assets in this patch step.

## p2.19a1-custom-provider-registry-foundation — custom provider registry foundation

Date: 2026-06-06

Scope:

- Keep the public `v0.4.3-alpha` release rolled back until VM user-path validation passes.
- Add a minimal custom OpenAI-compatible provider registry at `model-providers.json` while preserving the legacy env mirror.
- Let users assign a display-only custom provider name, store multiple custom providers, store multiple models per provider, and switch active provider/model.
- Keep runtime compatibility by mirroring the active provider/model/key to `COX_MODEL_PROVIDER=custom`, `COX_MODEL_BASE_URL`, `COX_MODEL`, and `COX_MODEL_API_KEY`.
- Add CLI entry points for `cox config custom-provider list|add|use|add-model`.
- Keep API-key output redacted and registry files written with user-only permissions.
- Do not refresh Release assets in this patch step.

## p2.18a9-concise-model-api-validation-hold — concise model API panels and validation hold

Date: 2026-06-05

Scope:

- Keep the public `v0.4.3-alpha` release rolled back until VM user-path validation passes.
- Make Step 2 model API input panels concise: Base URL, Model name, and API key no longer duplicate the panel heading.
- Add an immediate model API validation result page after API-key validation before advancing to web search configuration.
- The validation page shows provider/base URL/model/API-key state/status/method/URL/detail without exposing API-key material.
- Preserve p2.18a8 stepwise Backspace semantics and final completion page summary.
- Do not refresh Release assets in this patch step.

## p2.18a8-stepwise-backspace-validation-summary — stepwise Backspace and validation summary

Date: 2026-06-05

Scope:

- Keep the public `v0.4.3-alpha` release rolled back until VM user-path validation passes.
- Replace Step 2 post-fill review as the primary path with a stepwise model API flow: provider → base URL → model → API key.
- Text and secret inputs treat Backspace on an empty input as previous-step navigation while still allowing normal character deletion.
- Custom provider fields can move backward from API key to model, model to base URL, and base URL to provider selection.
- Store a redacted model API validation summary and show provider/base URL/model/status/method/URL on the final completion page.
- Reduce early post-language log flashing by keeping install log paths for the completion page instead of printing them immediately after Step 1.
- Preserve p2.18a4 stable splash entry, p2.18a5 model input guard, p2.18a6 completion hold, and p2.18a7 review helpers as non-primary helpers.
- Do not refresh Release assets in this patch step.

## p2.18a7-model-api-review-back — model API review/back step

Date: 2026-06-05

Scope:

- Keep the public `v0.4.3-alpha` release rolled back until VM user-path validation passes.
- Add an installer Step 2 model API review page after provider/base URL/model/API key collection.
- The review page hides API key material and supports Continue, Edit base URL, Edit model name, Edit API key, Back to provider selection, and Skip model API.
- Preserve p2.18a4 stable splash entry, p2.18a5 model input guard, and p2.18a6 completion hold.
- Non-interactive installs remain non-blocking and keep the existing field guard.
- Do not refresh Release assets in this patch step.

## p2.18a6-install-completion-hold — install completion hold

Date: 2026-06-05

Scope:

- Keep the public `v0.4.3-alpha` release rolled back until VM user-path validation passes.
- Add a stable installer completion page after configuration/profile repair output so users can see the final result before the terminal returns.
- The completion page summarizes public/internal version, install directory, config directory, Codex directory, and next commands.
- Interactive TTY installs wait for Enter; non-interactive installs do not block.
- Preserve p2.18a4 stable splash entry and p2.18a5 model input guard.
- Do not refresh Release assets in this patch step.

## p2.18a5-model-input-guard — model input guard

Date: 2026-06-05

Scope:

- Keep the public `v0.4.3-alpha` release rolled back until VM user-path validation passes.
- Add a final model-name guard for installer and `cox config wizard`: URL/path/control-character values, whitespace, and API-key-like values such as `sk-*` or `Bearer ...` are rejected as model ids.
- Preserve the p2.18a4 stable splash entry and p2.18a3 custom base URL normalization.
- Do not refresh Release assets in this patch step.

## p2.18a4-stable-splash-entry — stable splash entry

Date: 2026-06-05

Scope:

- Keep the public `v0.4.3-alpha` release rolled back until VM user-path validation passes.
- Add an explicit stable installer splash entry: users see the CodeXchange logo, Welcome panel, and setup summary first, then press Enter to start Step 1 language selection.
- Keep non-interactive installs non-blocking.
- Do not refresh Release assets in this patch step.

## p2.18a3-stable-guided-ui-input-contract — stable guided UI input contract

Date: 2026-06-05

Scope:

- Keep the public `v0.4.3-alpha` release rolled back until VM user-path validation passes.
- Replace the risky `p2.18a2` full-screen input clearing behavior with stable panel rendering.
- Preserve a visible brand/setup plan before Step 1 language selection.
- Sanitize TTY input, handle Backspace/DEL control characters, normalize custom OpenAI-compatible base URLs, and reject URL/path-like model names.
- Apply the same input contract to installer and `cox config wizard`.
- Keep `cox upgrade` TTY panels but avoid refreshing the public release in this patch step.

## p2.18a2-end-to-end-guided-ui — end-to-end guided UI

Date: 2026-06-05

Scope:

- Keep public version `v0.4.3-alpha` while making the interactive user path consistent across install, upgrade, and `cox config wizard`.
- Treat language selection as Step 1/5 in the guided installer instead of a pre-flow prompt.
- Replace bare custom-provider text prompts with the same open terminal panel style used by arrow menus.
- Add TTY upgrade panels for plan, progress, blocked-state, fallback bootstrap, and completion while keeping non-TTY / JSON output machine-readable.
- Preserve non-interactive behavior and the existing custom provider / split-profile contracts.

## p2.18a1-unified-guided-ui-upgrade-fallback — unified guided UI and upgrade fallback

Date: 2026-06-04

Scope:

- Keep `v0.4.3-alpha` as the public Latest line while hardening the user upgrade path.
- Add a latest-release resolution fallback so `cox upgrade` can continue with the current public release tag when the GitHub Latest Release API is rate-limited.
- Let git-backed installs fall back to the release bootstrap installer if `git fetch` fails, preserving the same safe backup/install path used by non-git installs.
- Keep installer and `cox config wizard` guided surfaces aligned with the arrow-key open terminal UI contract.

Validation focus:

- `cox upgrade --tag v0.4.3-alpha` remains the reliable legacy path for already-installed old runtimes whose own code cannot be patched retroactively.
- Future `cox upgrade` from this checkpoint should report structured fallback metadata instead of stopping at `latest_release_resolution_failed` when GitHub API resolution fails.

## p2.17a9-upgrade-ignore-managed-resources-dirty — v0.4.3-alpha public release

Date: 2026-06-03

Scope:

- Publish `v0.4.3-alpha` as the current public Latest release with user-facing release notes.
- Include the custom provider capability profile work and custom reasoning-only output mapping in the public release line.
- Keep README changes minimal and focused on user-visible custom provider, reasoning output, and image payload behavior.

Release boundary:

- Public tag: `v0.4.3-alpha`.
- Internal checkpoint: `p2.17a9-upgrade-ignore-managed-resources-dirty`.
- Release assets: `bootstrap.sh` and `install.sh`.

## p2.17a7 Custom reasoning output diagnostics

Date: 2026-05-30

Scope:

- Handle OpenAI-compatible custom providers that return `reasoning_content` without ordinary assistant `content` in a Chat Completions response.
- Map reasoning-only assistant text into a valid Responses `output_text` instead of returning a completed empty-output contract error.
- Preserve the strict empty-output guard when neither assistant content, reasoning content, nor tool calls are available.
- Improve diagnostics for invalid output contract failures so custom provider errors include provider, base URL host, chat compatibility mode, and capability profile metadata instead of misleading DeepSeek-only wording.

Release boundary:

- Internal runtime node only. Public Release assets are not updated in this step.


## p2.17a6 Provider capability profiles

Date: 2026-05-29

Scope:

- Add a provider capability profile layer for chat/completions payload adaptation.
- Keep custom/OpenAI-compatible providers on a conservative common-parameter allowlist by default.
- Support explicit `COX_CHAT_ALLOW_PARAMS`, `COX_CHAT_DROP_PARAMS`, and `COX_CHAT_EXTRA_PARAMS_JSON` overrides for provider-specific custom extensions.
- Keep DeepSeek official extensions enabled for the official provider, while letting custom providers opt in explicitly.
- Enrich upstream error diagnostics with provider, base URL host, compatibility mode, capability profile, and unsupported parameter extraction.

Release boundary:

- Internal development node only. No public Release or asset update.


## p2.17a5 Custom provider chat compatibility

Date: 2026-05-29

Scope:

- Added provider-aware chat payload compatibility for custom OpenAI-compatible providers.
- Custom providers now strip DeepSeek-only chat extensions such as `user_id`, `thinking`, and `reasoning_effort` by default before `/chat/completions` calls.
- DeepSeek official keeps stable `user_id` and DeepSeek-specific fields for cache/accounting compatibility.
- Upstream error details now report the configured provider and base URL host so custom-provider failures are not mislabeled as DeepSeek official failures.
- Operators can opt into DeepSeek extension passthrough for compatible custom endpoints with `COX_CHAT_SUPPORTS_DEEPSEEK_EXTENSIONS=1` or `COX_CHAT_COMPAT_MODE=deepseek`.

Release boundary:

- Internal development node only. Public Release remains `v0.4.3-alpha` until a release update is explicitly requested.

## p2.17a3 Restore p2.16a7 terminal UI

## p2.17a4 Release v0.4.3-alpha

Date: 2026-05-29

Scope:

- Publish `v0.4.3-alpha` as the current public Release from the restored stable open terminal UI line.
- Keep the user-facing Release notes focused on upgrade impact rather than internal checkpoint names.
- Include image payload preservation and installer/wizard usability improvements since `v0.4.1-alpha`.

Release boundary:

- Public tag: `v0.4.3-alpha`.
- Internal checkpoint: `p2.17a4-release-v042-alpha`.
- GitHub Release should be non-draft, non-prerelease, and Latest after promotion.


Date: 2026-05-29

Scope:

- Reverted the p2.17 Python TUI foundation and layout redesign after visual review showed the Python TUI prototype did not meet the expected terminal UI quality bar.
- Restored the p2.16a7 stable open-layout terminal UI as the active guided configuration surface.
- Kept the restoration as a normal forward commit instead of rewriting public or shared history.
- This node does not update the public Release.


## p2.16a7 Terminal UI stable open layout

Date: 2026-05-29

Scope:

- Replace fragile closed-box shell/Python menu rendering with an open-layout terminal panel that avoids right-border alignment errors and stale border remnants.
- Keep the modern visual hierarchy from the p2.16 UI line while removing the right frame edge until a proper Python TUI renderer can own Unicode/ANSI-aware layout.
- Preserve Step x/5 labels, language-first flow, auto port handling, and Backspace previous-step semantics from p2.16a6.

Release boundary:

- Internal development node only. Public Release remains `v0.4.3-alpha` until a later explicit release update.


## p2.16a6 Terminal UI flow language and automatic ports

Date: 2026-05-29

Scope:

- Add the installer language choice as the first user-facing decision, with English and Simplified Chinese options.
- Align the setup plan with the five guided user decisions: language, model API, web search API, image generation API, and Codex wrapper.
- Remove manual cox port prompts from the guided path; installer selects available non-thinking and thinking ports automatically.
- Make installer Backspace handling safe under `set -e` so the previous-step sentinel is consumed by the step loop instead of ending installation.
- Keep the boxed UI compact and avoid inner separator clutter.

Release boundary:

- Internal development node only. It does not move `v0.4.3-alpha` and does not update public Release assets.


## p2.16a5 Terminal UI frame and Backspace correctness

Date: 2026-05-29

Scope:

- Fixed terminal frame width calculation so top/body/footer borders use the same display width.
- Removed inner menu separator lines from boxed interactive menus in favor of whitespace sections.
- Changed Backspace from a skip/default shortcut into an explicit previous-step sentinel in installer menus.
- Added a guided installer step loop for model, web, image, and wrapper configuration.

Release boundary:

- Internal development node only. Public Release assets were not updated.

## p2.16a4 Terminal UI frame and step polish

Date: 2026-05-28

Scope:

- Fixed the terminal menu frame redraw model so interactive installer selections redraw the whole panel instead of leaving stale right-border fragments.
- Replaced the placeholder `Step interactive` footer with explicit step labels such as `Step 2/5`, `Step 3/5`, `Step 4/5`, and `Step 5/5`.
- Narrowed interactive panels to a calmer 72-88 column range and applied the same footer convention to `cox config wizard`.

Release boundary:

- Internal development only. No public Release tag or GitHub Release asset is moved.

## p2.16a3 Terminal UI layout redesign

Date: 2026-05-28

Scope:

- Reworked the installer and `cox config wizard` terminal panels from compact box-only output into a more spacious framed layout.
- Separated the main question, hint/details, option list, and keybinding footer so long guidance does not visually crowd the selection rows.
- Kept non-interactive and dry-run output machine-readable; this node only changes interactive TTY presentation.
- Public `v0.4.3-alpha` is not moved in this internal UI iteration.

## p2.16a2 Terminal UI polish

Date: 2026-05-28

Scope:

- Replace the p2.16a1 box-only terminal UI with a shared framed renderer that wraps long text and keeps menu content inside the panel.
- Improve installer arrow menus and `cox config wizard` with a consistent title, hint, options, and Step footer layout.
- Keep non-interactive and JSON/dry-run paths machine-readable; this node does not update the public Release.

## p2.16a1 Image payload preservation and terminal UI foundation

Date: 2026-05-28

Scope:

- Treat image payloads as opaque, lossless request payloads. They are excluded from tool-output trimming, artifact-ref replacement, semantic-envelope replacement, token-first compaction, and char fallback trimming.
- Add reporting semantics for `image_payload_preserved_verbatim_no_compact_no_trim` so downstream status/debug surfaces can distinguish preservation from a missing trim opportunity.
- Start a boxed terminal UI foundation for installer and `cox config wizard`, preserving arrow-key navigation while improving structure and visual hierarchy.

Release boundary:

- Internal development node only. It does not move `v0.4.3-alpha` and does not update GitHub Release assets.

## p2.15a6-installer-env-file-precedence installer env-file precedence for non-interactive upgrades

Date: 2026-05-28

Scope:

- Fixed the installer non-interactive upgrade path so an existing env file remains the source of truth for model provider, base URL, upstream model, web-search provider/key, and image provider/key.
- Prevented ambient shell variables from another HOME/session from overriding the target install HOME env file during Release/VM validation and real user upgrades.
- This closes the v0.4.3-alpha VM validation gap where a legacy custom provider env was overwritten back to DeepSeek official defaults.

Release boundary:

- The existing `v0.4.3-alpha` pre-release is updated to this internal checkpoint for VM validation.
- GitHub Latest remains `v0.4.0-alpha` until VM validation passes and promotion is explicitly requested.


## p2.15a5 Installer preserves existing model-provider env

Date: 2026-05-28

Scope:

- Fix the `v0.4.3-alpha` VM validation failure where non-interactive install rewrote an existing env file without loading its configured model provider before choosing defaults.
- Preserve existing `COX_MODEL_PROVIDER`, `COX_MODEL_BASE_URL`, and `COX_MODEL` values during non-interactive install/upgrade.
- Use the resolved non-DeepSeek/custom model when generating managed Codex split profile files, so upgraded Codex 0.134+ users keep their configured upstream model.

Release boundary:

- This node updates the existing `v0.4.3-alpha` pre-release candidate only after tests pass. VM legacy-config validation remains required before any Latest promotion.

## p2.15a4 v0.4.3-alpha pre-release

Date: 2026-05-28

Scope:

- Publish the p2.15 Codex 0.134+ split-profile fix line as `v0.4.3-alpha`.
- Keep `v0.4.0-alpha` as the GitHub Latest ordinary Release; `v0.4.3-alpha` is a non-draft pre-release.
- Release coverage: split Codex profile files for Codex 0.134+, legacy profile-table migration/removal, custom provider default API validation, and wizard/installer provider UX alignment.
- Validate the old-user path with an isolated HOME containing legacy `[profiles.*]` config before install/repair.

Release boundary:

- Do not move `v0.4.0-alpha`.
- Do not create tracked release-note files under `docs/`.
- Upload only `bootstrap.sh` and `install.sh` as Release assets.

## p2.15a3 Postmerge checklist closure

Date: 2026-05-28

Scope:

- Close remaining p2.15 post-merge checklist gates after p2.15a2.
- Advance runtime internal metadata to `p2.15a3-postmerge-checklist-closure` while keeping public `v0.4.0-alpha` unchanged.
- Remove the unused wizard catalog helper from the CLI source surface.
- Update the split-profile context source label from the legacy `codex_config.profiles.<profile>` wording to `codex_split_profile_file`.
- Isolate custom-provider and wizard non-interactive regression tests from developer-machine `DEEPSEEK_*` environment variables.

Validation target:

- `python -m py_compile` for app/CLI/focused tests.
- `bash -n bootstrap.sh`, `bash -n scripts/install.sh`, and `bash -n scripts/cox-config`.
- `git diff --check`.
- Focused CLI/docs/version/provider tests.
- Full tests.

Release boundary:

- This internal node does not move `v0.4.0-alpha`, rebuild Release assets, or update GitHub Release notes.


## p2.15a1 Codex 0.134 profile, custom provider, and wizard UX contract

Date: 2026-05-28

Scope:

- Adapt managed Codex profiles to the Codex 0.134+ split profile file layout.
- Keep provider blocks in the main Codex config and write profile bodies to `deepseek.config.toml` and `cox.config.toml`.
- Treat legacy embedded profile tables and top-level deepseek profile selectors as migration input only.
- Make `cox config test-api-key` read the configured model provider/base URL/model from env by default, so custom providers validate against their configured `/models` endpoint instead of DeepSeek official `/user/balance`.
- Align `cox config wizard` with the installer arrow-key menu contract.

Release boundary:

- Internal patch node only unless the maintainer explicitly starts a `v0.4.0-alpha` Release update.
- Public tag `v0.4.0-alpha` remains pinned before a separate Release task.

## p2.14a10 Release metadata environment sanitization

Date: 2026-05-27

Scope:

- Fix stale release metadata env pollution found during `v0.4.0-alpha` VM validation.
- Runtime commit metadata now ignores `COX_PUBLIC_COMMIT` and `COX_INTERNAL_COMMIT` when the env file also exposes a mismatched `COX_INTERNAL_VERSION`.
- `scripts/install.sh` now writes the current internal version parsed from installed source instead of the old hard-coded `p2.10a26-wrapper-start-plan-mode-hardening` value.
- `bootstrap.sh` and `cox upgrade` non-git fallback scrub stale release metadata env keys before invoking the installer.
- Added regression tests for stale env metadata, non-git upgrade env scrubbing, and installer release metadata output.

Reason:

- VM validation showed `cox --version` returning `v0.4.0-alpha | 72e0f77` although remote `v0.4.0-alpha^{}` and `p2.14a9-upgrade-alpha-non-git-fallback^{}` both pointed to `e5111c5`.
- Narrow audit showed `72e0f77` came from `/home/wjh/.config/codexchange/env`, not from the Release tag or installed source.

Release boundary:

- This is an internal patch node until the existing `v0.4.0-alpha` pre-release is updated again.
- Do not mark `v0.4.0-alpha` as Latest until VM install and forced non-git `upgrade --alpha` both report the updated peeled commit.

## p2.14a9 Upgrade alpha non-git fallback

Date: 2026-05-26

Scope:

- Fix future `cox upgrade --alpha` behavior for source-archive/non-git installs.
- Replace the old `not_a_git_checkout` terminal error with a release-bootstrap fallback.
- The fallback downloads target-ref `bootstrap.sh` and runs it with `--install-ref <target-ref>` plus `--non-interactive --install-dir <repo_hint>`.
- `--dry-run` now reports the non-git bootstrap plan without downloading or executing it.
- `--skip-profile` maps to installer `--no-codex-profile`.
- `--no-restart` is recorded as informational because the installer fallback does not start proxy processes.
- Same-public-version non-git upgrades skip unless `--force` is used.
- This node does not move `v0.3.9-alpha` or `v0.4.0-alpha` and does not update GitHub Release assets.

Reason:

- VM validation showed explicit `--install-ref v0.4.0-alpha` succeeds, but `v0.3.9-alpha` source-archive installs return `not_a_git_checkout` for `cox upgrade --alpha`.
- Because `v0.3.9-alpha` must not move, old clients still need the explicit installer path. p2.14a9 prevents the same failure for future installed versions once this fix is published in a later public alpha.

Validation target:

- py_compile for app/CLI/tests
- `bash -n bootstrap.sh`
- `bash -n scripts/install.sh`
- `git diff --check`
- focused upgrade tests including non-git dry-run and bootstrap execution fallback
- focused version/docs tests
- full tests

Release boundary:

- Internal-only patch node unless a separate Release decision updates `v0.4.0-alpha` or publishes a later alpha.
- `v0.3.9-alpha` remains pinned at `82a4428`.

## p2.14a8 v0.4.0-alpha Release

Date: 2026-05-26

Scope:

- Publish the p2.14 managed native tool routing line as `v0.4.0-alpha`.
- Keep `v0.3.9-alpha` pinned at `82a4428`; do not move the previous public Release tag.
- Update runtime public version metadata to `v0.4.0-alpha` and internal metadata to `p2.14a8-v040-alpha-release`.
- Update README explicit pre-release install examples to `v0.4.0-alpha`.
- Update developer handbooks with the new pre-release state.
- Write GitHub Release notes from a temporary file only; do not add tracked per-release note files under `docs/`.

p2.14 release coverage:

- Managed native tool routing core maps native `web_search` and `image_generation` to `codexchange_web_search` and `codexchange_generate_image` when policy allows managed routing.
- Runtime diagnostics expose last route decisions, last execution evidence, tool calls, tool results, request-scoped no-native-tool/no-tool-call diagnostics, and WeClaw-facing status.
- `cox config show`, `cox config set-tool-routing`, and `cox doctor tool-routing` expose routing configuration and non-spending diagnostics.
- Real Codex `--search` E2E passed through real SerpAPI.
- Real Zhipu image-generation E2E passed through the cox provider bridge using an ASGI/mock DeepSeek client.
- Current Codex CLI did not expose native `image_generation` to cox; image provider E2E validates the provider bridge rather than Codex native image entry.
- Future real-provider E2E scripts must not log signed image URLs, temporary provider URLs, or query-string tokens.

Validation target:

- `python -m py_compile codexchange_proxy/app.py codexchange_proxy/cli.py tests/test_version_metadata.py tests/test_docs_release_readiness.py`
- `bash -n bootstrap.sh`
- `bash -n scripts/install.sh`
- `git diff --check`
- focused version/docs/CLI/managed-routing/provider tests
- full tests
- GitHub Release verification for `v0.4.0-alpha` as non-draft pre-release with assets `bootstrap.sh` and `install.sh`

Release boundary:

- `v0.4.0-alpha` is a new public pre-release.
- `v0.3.9-alpha` remains at `82a4428` and remains the previous Latest ordinary Release unless GitHub Latest state is explicitly changed later.

## p2.14a6 Routing policy CLI and doctor diagnostics

Date: 2026-05-26

Scope:

- Expose managed native tool routing configuration in `cox config show`.
- Add `cox config set-tool-routing <web-search|image-generation> <auto|managed-only|native-only|disabled>`.
- Add `cox doctor tool-routing` for non-spending diagnostics over provider configuration, routing policy, last route decision, last execution, and no-native-tool/no-tool-call status.
- Keep live provider probes behind `cox doctor providers --live --allow-spend`.
- Do not move public `v0.3.9-alpha` and do not rebuild Release assets.

Validation:

- `python -m py_compile codexchange_proxy/app.py codexchange_proxy/cli.py tests/test_cli.py tests/test_version_metadata.py tests/test_docs_release_readiness.py`
- `bash -n bootstrap.sh`
- `bash -n scripts/install.sh`
- `git diff --check`
- focused CLI/provider/managed-routing/version/docs tests
- full tests

## p2.14a5 No-tool-call diagnostics

Date: 2026-05-25

Scope:

- Add no-native-tool/no-tool-call diagnostics for managed tool routing without claiming execution.
- Explain the real Codex image-generation observation where Codex did not send a native `image_generation` Responses tool to cox.
- Expose request-scoped diagnostics through `tool_bridge.managed_tool_routing`, per-tool status, and WeClaw-facing tools status.
- Emit `managed_tool_routing_no_native_tool_observed` when the latest request lacks one or more managed native tool capabilities.
- Keep diagnostics redacted and avoid raw prompt/query/provider payload exposure.

Validation:

- `git diff --check`
- `bash -n bootstrap.sh`
- `bash -n scripts/install.sh`
- `python -m py_compile codexchange_proxy/app.py`
- focused managed-tool-routing/tool-bridge/proxy/provider/version/docs tests
- full tests

Release boundary:

- Public `v0.3.9-alpha` remains at `82a4428`.
- No GitHub Release update is performed.
- No Release assets are rebuilt.

## p2.14a3 Managed tool routing runtime diagnostics

Date: 2026-05-25

Scope:

- Harden managed tool routing diagnostics without moving the public `v0.3.9-alpha` Release.
- Record actual managed tool execution evidence in `managed_tool_routing_report.tool_calls`, `tool_results`, and `execution`.
- Expose per-tool `last_execution` and aggregate `managed_tool_routing.last_execution` through tool-bridge status and WeClaw-facing tools status.
- Keep execution diagnostics redacted: argument keys and result keys are exposed, but raw query/prompt/result payloads are not surfaced in status.
- Emit `managed_tool_routing_execution` and `managed_tool_routing_after_tool_bridge` debug trace events.

Validation:

- `git diff --check`
- `bash -n bootstrap.sh`
- `bash -n scripts/install.sh`
- `python -m py_compile codexchange_proxy/app.py`
- focused managed-tool-routing/tool-bridge/proxy/status/version/docs tests
- full tests

Release boundary:

- Public `v0.3.9-alpha` remains at `82a4428`.
- No GitHub Release update is performed.
- No Release assets are rebuilt.

## p2.14a2 Managed tool routing core

Date: 2026-05-25

Scope:

- Start the p2.14 managed tool routing line without moving the public `v0.3.9-alpha` Release.
- Add a cox-owned managed tool routing core for native Responses web/image tools on DeepSeek/Codex third-party profiles.
- Add policy normalization for `auto`, `managed_only`, `native_only`, and `disabled`.
- Map native `web_search` to `codexchange_web_search` and native `image_generation` to `codexchange_generate_image` when the policy is `auto` or `managed_only`.
- Keep legacy `proxy_web_search` and `proxy_image_generate` execution aliases working for compatibility.
- Add managed routing instruction injection, route decision reporting, debug trace event emission, and tool-bridge status registry fields.
- Expose routing status through normal status and WeClaw-facing status while keeping provider cost attribution out of scope for this core node.

Validation:

- `git diff --check`
- `bash -n bootstrap.sh`
- `bash -n scripts/install.sh`
- `python -m py_compile codexchange_proxy/app.py`
- focused managed-tool-routing/tool-bridge/provider/version tests
- full tests

Release boundary:

- Public `v0.3.9-alpha` remains at `82a4428`.
- No GitHub Release update is performed.
- No Release assets are rebuilt.

## p2.13a6 Documentation current-state sync

Date: 2026-05-24

Scope:

- Synchronize `docs/developer-handbook.md` and `docs/developer-handbook.zh-CN.md` from the stale `d674a61` / `p2.12a13-remove-tracked-release-notes` startup baseline to the current `82a4428` / `p2.13a5-token-first-trim-profile-scoped-report` public Latest baseline.
- Update current-state markers, startup checklist markers, long-term task checklist anchors, and p2.13 Compact/TRIM current-rule notes.
- Record that repository-tracked per-release note files remain retired; public GitHub Release text stays on the GitHub Release page and may only be generated from temporary files.
- Advance developer internal runtime metadata to `p2.13a6-docs-current-state-sync` while keeping public `v0.3.9-alpha` Release metadata at the `82a4428` public Release baseline.

Validation:

- `git diff --check`
- `bash -n bootstrap.sh`
- `bash -n scripts/install.sh`
- `python -m py_compile codexchange_proxy/app.py`
- focused documentation/version tests
- full tests

Release boundary:

- Public `v0.3.9-alpha` remains at `82a4428`.
- No GitHub Release update is performed.
- No Release assets are rebuilt.
- `the retired v0.3.9-alpha per-release note source under docs` must not be recreated.

## v0.3.9-alpha Latest update to p2.13a5

Date: 2026-05-24

Scope:

- Move the public `v0.3.9-alpha` Latest Release from the previous peeled commit `d674a61` to `82a4428` after p2.13a5 validation.
- Keep the GitHub Release title `CodeXchange v0.3.9-alpha` and state as non-draft, non-prerelease, Latest ordinary Release.
- Re-upload the public Release assets `bootstrap.sh` and `install.sh`.
- Write Release text through a temporary `/tmp` notes file instead of creating any tracked repository Release-note source.

Final state:

- `master = origin/master = 82a4428`.
- `p2.13a5-token-first-trim-profile-scoped-report = 82a4428`.
- Public `v0.3.9-alpha` peeled commit is `82a4428`.
- GitHub Latest Release is `v0.3.9-alpha`, `isDraft=false`, `isPrerelease=false`.
- Release assets are exactly `bootstrap.sh` and `install.sh`.
- Expected public Release install version is `public version: v0.3.9-alpha | 82a4428` and `internal version: p2.13a5-token-first-trim-profile-scoped-report | 82a4428`.

Boundary:

- Do not recreate `the retired v0.3.9-alpha per-release note source under docs`.
- Do not add repository README links to a tracked Release-note file.
- Future Release updates require an explicit Release-update task.

## p2.13a5 Token-first TRIM profile-scoped report

Date: 2026-05-24

Scope:

- Fix WeClaw-facing token-first TRIM status so a stale in-memory report from another profile cannot mask a matching persisted report for the requested profile/session.
- Add a profile-scoped `not_triggered` TRIM fallback for current sessions that have displayable token context but no matching live TRIM report.
- Keep cross-profile TRIM reports unavailable; profile mismatch remains diagnostic only and must not be displayed as current-profile TRIM.
- The fallback reports `source=profile_scoped_current_session_token_status_fallback` and `precision=current_session_context_window_estimate_not_live_request_payload`, so it is not confused with a live payload report.

## p2.13a4 Pricing discount valid-until test isolation

Date: 2026-05-24

Scope:

- Close the pre-existing full-test failure in `tests/test_weclaw_pricing_discount_contract.py`.
- Confirm the bundled `config/pricing.json` snapshot already carries `deepseek-v4-pro` discount metadata, including `valid_until=2026-05-31T23:59:00+08:00`.
- Make the WeClaw pricing discount contract test explicitly pin `COX_PRICING_PATH` to the bundled project snapshot so user pricing cache files cannot mask bundled snapshot metadata during tests.
- Keep runtime pricing source precedence unchanged: real status still uses configured/cache/project pricing source order.

## p2.13a3 Managed auto-compact ratio repair

Date: 2026-05-24

Scope:

- Lock managed CodeXchange auto-compact ratio to `0.90` for runtime status, profile status, install-codex-profile defaults, and managed profile repair.
- Treat `COX_AUTO_COMPACT_RATIO` and `COX_AUTO_COMPACT_RATIO` as ignored legacy low-trigger experiment residue unless an explicit CLI `--auto-compact-ratio` argument is used for a deliberate one-shot repair.
- Repair real managed Codex profiles so `model_context_window=1000000` derives `model_auto_compact_token_limit=900000`.
- Keep public `v0.3.9-alpha` unchanged.

## p2.13a2 Codex native Compact observability and Responses output contract

Date: 2026-05-23

Scope:

- Treat CodeXchange runtime Compact as a fallback-only path after Codex native compact summaries are present.
- Detect Codex native compact summaries by the audited Codex summary prefix and protect them from cox LLM re-compaction.
- Expose `codex_native_compact` in WeClaw-facing runtime status as an observed/inferred cox payload contract, not as Codex internal session truth.
- Keep remote `responses/compact` unsupported for the managed DeepSeek third-party provider unless future request evidence proves Codex is incorrectly calling it.
- Reject `/v1/responses` completed envelopes that would otherwise return `output=[]` and `output_text=""` while upstream reports completion tokens.

Validation note:

- Full-test pricing discount validity failure is pre-existing on clean `origin/master` and remains tracked separately.

## p2.13a1 Handbook current-state cleanup and Codex native Compact/Fork audit prep

Date: 2026-05-23

Scope:

- Correct the handbook current-state drift after p2.12a13 so the startup baseline no longer points to the historical p2.10a80/p2.10a81 `80bb0ea` Release-note-source state.
- Reaffirm that `the retired v0.3.9-alpha per-release note file under docs` must not be restored and README files must not link to a repository-tracked Release-note file.
- Prepare a source-audit bundle for Codex native Compact/Fork behavior, including local CodeXchange source grep evidence and upstream OpenAI Codex source snapshots when network access is available.

Boundary:

- Documentation and audit-prep only.
- No runtime behavior change.
- No public `v0.3.9-alpha` tag movement.
- No GitHub Release update.
- No Release asset rebuild.
- Any decision to disable, merge, or further expose native Codex Compact requires a follow-up implementation node based on the audit report.

# p2.12a8-runtime-payload-report-persistence

Date: 2026-05-22

Scope:

- Added SQLite persistence for token-first runtime Compact/Trim reports so WeClaw status can recover runtime payload guard observations after proxy restarts.
- Restored runtime payload guard from the latest matching profile/session persisted report when process-local `last_context_compaction_report` or `last_context_trimming_report` is unavailable.
- Kept external `--weclaw-json` token-only by reusing the token-only public runtime sanitizer; debug report files remain diagnostic fallback artifacts rather than authoritative runtime state.
- Added focused regression coverage for SQLite persistence and WeClaw status recovery from persisted runtime reports.

Boundary:

- Public `v0.3.9-alpha` was not moved.
- This node does not change the user-facing auto-compact ratio or context denominator.

## p2.10a64 Pre-release upgrade and uninstall documentation closure

## p2.12a7-token-only-status-surface

- Tightened the external WeClaw/status surface to token-only semantics.
- Broadened the public runtime/status sanitizer so old non-token diagnostic fields and heuristic strings remain internal-only.
- Sanitized the top-level `_runtime_weclaw_status` return value so persisted legacy reports cannot leak non-token diagnostics back into the public JSON contract.
- Public Release `v0.3.9-alpha` was not moved in this internal node.


- Closed the post-P0 audit gap for uninstall documentation.
- Pre-release upgrade was already covered by `cox upgrade --alpha`, explicit `--tag`, and `--dry-run`.
- Product-level uninstall remains installer-owned and is documented as `bash ~/.local/share/codexchange/scripts/install.sh --uninstall`.
- Full removal is documented as `bash ~/.local/share/codexchange/scripts/install.sh --uninstall --remove-files`.
- README.md and README.zh-CN.md now document uninstall scope, including managed Codex profiles, the CodeXchange codex wrapper, the cox wrapper, optional install directory/env/manifest removal, and the boundary against deleting unrelated user files.
- Added a README regression test for uninstall documentation.
- Public `v0.3.9-alpha` remains at `ac63043`; this node does not update Release assets or Release notes.


## p2.10a63 P0 release-state documentation sync

- Synchronized repository docs after updating public pre-release `v0.3.9-alpha` to `p2.10a62-weclaw-runtime-payload-guard`.
- Current trusted state: `master = origin/master = ac63043`, `p2.10a62-weclaw-runtime-payload-guard = ac63043`, and `v0.3.9-alpha` peeled commit `ac63043`.
- `v0.3.8-alpha` remains `dfdc629`; forbidden plain tags `v0.3.9` and `v0.3.5` remain absent.
- GitHub Release `CodeXchange v0.3.9-alpha` is non-draft, pre-release, and includes `bootstrap.sh` and `install.sh` assets.
- P0 is closed from the CodeXchange implementation and pre-release delivery side; the mainline is now waiting for WeClaw-side validation.
- If WeClaw reports new issues, treat them as the next explicit requirement round rather than reopening this P0 scope by default.


## p2.10a62 WeClaw runtime payload guard

- Added `runtime_payload_guard` to WeClaw-facing status.
- Compact progress uses the latest in-memory context compaction report `after_chars` as exact `runtime_context_builder` chars.
- Trim progress uses the latest in-memory DeepSeek payload trimming report `after_chars` as exact `live_request_payload` chars.
- The contract exposes denominators, usage ratios, remaining chars, status, source, precision, observed timestamp, and unavailable actions.
- Public `v0.3.9-alpha` is not moved in this internal node.


## p2.10a61 README structure cleanup

- Rewrote `README.md` and `README.zh-CN.md` as concise user-facing entry points.
- Removed long historical change tables, developer-only context, Brave setup references, and Markdown heading pollution caused by shell comments.
- Kept install, verification, model provider setup, optional tool providers, pricing cache, upgrade, WeClaw compatibility, security boundaries, and documentation entry points.
- Synchronized developer-handbook current state after `p2.10a60`; public pre-release `v0.3.9-alpha` remains at `4a96283` and was not moved.


## p2.10a60 WeClaw status context and pricing contract

- Updated runtime WeClaw status to expose a usable context numerator from the latest primary upstream provider `prompt_tokens` when available, with explicit estimated precision and source labels.
- Added context limit explanations for display limit, full model context window, auto-compact token limit, and model-catalog context values.
- Added pricing source trust, official reference URL, official-cache availability, and cost pricing-source metadata so WeClaw can distinguish bundled fallback estimates from official refreshed pricing.
- Kept the boundary that session totals are cumulative spend and must not be used as current context-window occupancy.


# CodeXchange详尽开发日志

## p2.10a60-weclaw-status-context-pricing-contract

- Scope: token attribution boundary contract for WeClaw third-round status display.
- Starting point: `master = origin/master = d5bdd0b`, internal tag `p2.10a58-weclaw-round3-pricing-refresh = d5bdd0b`, public pre-release tag `v0.3.9-alpha = 677d923`.
- Audit conclusion: cox usage ledger records provider aggregate usage fields and cox purpose/call-index/model attribution, but it does not store prompt subcategory token splits.
- Audit conclusion: no audited tokenizer or local token estimator was present. `tiktoken` and `token_estimate` were not found in the p2.10a59 audit.
- Contract: `tokens.taxonomy.version` is now `3`.
- Contract: `tokens.attribution.provider_usage_totals` is exact provider-reported aggregate usage.
- Contract: `tokens.attribution.purpose_attribution` is exact cox model-call purpose attribution.
- Contract: `tokens.attribution.prompt_subcategory_split` and `tokens.prompt_subcategory_split` are explicitly unavailable with reason/action/missing fields.
- Boundary: this node does not estimate user/tool/environment/history tokens and does not derive context-window used tokens from session totals.
- Release state: no public Release tag is moved, no GitHub Release is created, and no Release assets are rebuilt.

## p2.10a58-weclaw-round3-pricing-refresh

- Scope: guarded pricing refresh for WeClaw third-round status/cost display.
- Starting point: `master = origin/master = 861f260`, internal tag `p2.10a57-weclaw-round3-contract-foundation = 861f260`, public pre-release tag `v0.3.9-alpha = 677d923`.
- Audit conclusion: the current V4 pricing source is the human HTML page `https://api-docs.deepseek.com/quick_start/pricing`; `pricing-details-usd` and `pricing-details-cny` still describe legacy `deepseek-chat`/`deepseek-reasoner` pricing and must not be treated as V4 sources.
- Implementation: `cox pricing refresh --json` fetches and validates official pricing HTML without writing cache by default.
- Implementation: `cox pricing refresh --json --write-cache` writes validated pricing atomically to the user pricing cache or explicit `--cache-path`.
- Contract: refresh failures preserve existing cache and return structured reason/error/source metadata.
- Contract: `pricing show --json` reports metadata from official-docs cache files, including `source_url`, `source_kind`, `fetched_at`, `expires_at`, `ttl_seconds`, and `is_stale`.
- Boundary: this node does not claim a stable official pricing API and does not modify project `config/pricing.json` by default.
- Release state: no public Release tag is moved, no GitHub Release is created, and no Release assets are rebuilt.

## p2.10a57-weclaw-round3-contract-foundation

- Scope: low-risk WeClaw third-round contract foundation after p2.10a56 read-only audit.
- Starting point: `master = origin/master = 7f88f27`, internal tag `p2.10a55-weclaw-runtime-status-contract = 7f88f27`, public pre-release tag `v0.3.9-alpha = 677d923`.
- Contract: add top-level `diagnostics` with `degraded_fields`, `warnings`, and `actions` for profile and runtime WeClaw status.
- Contract: keep `context_window.used_tokens` unavailable while adding `used_tokens_action` and `used_tokens_precision=unavailable`.
- Contract: bind `context_window.model_catalog` to a readable managed Codex `model_catalog_json` entry when available, otherwise return stable reason/action fields.
- Contract: add stable pricing fields `source_url`, `ttl_seconds`, and refresh action metadata.
- CLI: add `cox pricing show --json` and structured `cox pricing refresh --json` not-implemented output without live network or cache writes.
- Contract: mirror runtime semantic compaction status to top-level `semantic_compaction` and add rollout `action` and `missing_events`.
- Boundary: this node does not implement context used-token estimation, prompt subcategory attribution, official live pricing refresh, or semantic payload compaction enablement.
- Release state: no public Release tag is moved, no GitHub Release is created, and no Release assets are rebuilt.

## p2.10a55-weclaw-runtime-status-contract

- Scope: runtime and contract fix for WeClaw second-round full telemetry integration gaps.
- Starting point: `master = origin/master = f43a4c0`, internal tag `p2.10a54-token-shadow-accounting-plan = f43a4c0`, public pre-release tag `v0.3.9-alpha = 677d923`.
- Root cause: runtime `GET /v1/proxy/weclaw/status` used `create_app()` closure parameters for `store` and `deepseek_client`; default runtime creation leaves those closure values as `None`, while the real objects live in `app.state.store` and `app.state.deepseek_client`.
- Fix: bind runtime WeClaw status aggregation to `app.state.store` and `app.state.deepseek_client`.
- Contract: add explicit context `used_tokens` display semantics without inferring context usage from session totals.
- Contract: add actionable balance unavailable fields and balance display fields when available.
- Contract: add cost availability reason fields and pricing timestamp fields.
- Contract: add model conflict `display_hint`, `diagnostic_hint`, and `user_visible=false`.
- Tests: cover app.state store/client binding, actionable balance degradation, context used-token fields, model-conflict diagnostic fields, CLI fallback fields, and effort max to Codex xhigh safety.
- Recovery note: the first focused test run used the unsanitized developer shell and image-provider tests picked up local image-model/provider overrides. The final validation must use a sanitized environment before commit.
- Release state: no public Release tag is moved, no GitHub Release is created, and no Release assets are rebuilt.

## p2.10a54-token-shadow-accounting-plan

- Scope: docs-only plan for token shadow accounting and token-vs-char drift observability before semantic payload compaction implementation.
- Starting point: `master = origin/master = 2781892`, internal tag `p2.10a53-tui-compact-path-evidence-sync = 2781892`, public pre-release tag `v0.3.9-alpha = 677d923`.
- Decision: keep current cox runtime compaction and trimming as character-based payload guards.
- Decision: do not directly switch runtime compaction to token-based triggering.
- Decision: add token shadow accounting before semantic payload compaction implementation.
- Required boundary: Codex profile context and Codex status are token-level surfaces, cox runtime payload guard is char-level, provider usage remains authoritative for token/cost accounting, and local token estimates must be labelled as estimates.
- Required future work: report token-vs-char drift, warn when token risk and char risk diverge, and only then consider dual-threshold triggering.
- WeClaw implication: WeClaw display should separate token context window from char proxy payload guard and should not merge them into one unitless progress bar.
- Release state: no public Release tag is moved, no GitHub Release is created, and no Release assets are rebuilt.

## p2.10a53-tui-compact-path-evidence-sync

- Scope: docs-only evidence sync for the Codex TUI compact path after p2.10a52.
- Starting point: `master = origin/master = 2fe8c12`, internal tag `p2.10a52-semantic-payload-compaction-tui-plan = 2fe8c12`, public pre-release tag `v0.3.9-alpha = 677d923`.
- Evidence: isolated TUI run under `codex --profile deepseek` started successfully with the cox-backed profile.
- Evidence: ordinary short request `reply ok exactly` returned successfully.
- Evidence: manual `/compact` displayed `Context compacted`.
- Evidence: TUI transcript markers did not contain `responses/compact` or `/responses/compact`.
- Evidence: Codex-side logs showed `codex.op="compact"`, `session_task.compact`, `model_client.stream_responses_api`, `wire_api=responses`, `http.method="POST"`, and `api.path="responses"`.
- Evidence: the cox listener on port 8000 was the local uvicorn process for `codexchange_proxy.app:app`; proxy access logs showed ordinary `POST /v1/responses HTTP/1.1` requests.
- Interpretation: manual `/compact` in Codex CLI `0.130.0` with `codex --profile deepseek` currently uses ordinary `/v1/responses`, not a dedicated `/responses/compact` endpoint.
- Remaining risk: auto-compact near `model_auto_compact_token_limit` remains unverified, as does long-session repeated compact behavior and usage/cost attribution for compact turns.
- Release state: no public Release tag is moved, no GitHub Release is created, and no Release assets are rebuilt.

## p2.10a52-semantic-payload-compaction-tui-plan

- Scope: record the inserted semantic payload compaction hardening plan and Codex TUI third-party profile compatibility plan after the `v0.3.9-alpha` pre-release and p2.10a51 post-release documentation sync.
- Starting point: `master = origin/master = 9337fdc`, internal tag `p2.10a51-post-v039-alpha-release-doc-sync = 9337fdc`, public pre-release tag `v0.3.9-alpha = 677d923`.
- Trigger: the maintainer identified that Codex profile context is token-based while cox runtime compaction/trimming is char-based, and that native Codex `/compact` or auto-compact may still run under `codex --profile deepseek`.
- Planning result: add `P0.5 semantic payload compaction hardening` after WeClaw second-round requirements and before AnyCodeX-level architecture work, unless a high-risk TUI compaction failure forces escalation.
- Planning result: add `P0.6 Codex TUI third-party profile command compatibility` to verify `/compact`, auto-compact, `/fork`, `/resume`, `/model`, `/status`, `/diff`, `/review`, approval, sandbox, and related TUI commands under the third-party `deepseek` profile.
- Risk recorded: cox character-level persistent compaction cannot be assumed to automatically replace Codex native token-level compact unless the compact request actually reaches cox through a compatible path.
- Required future evidence: isolated TUI command matrix output, exact compact request path, whether `/responses/compact` is used, whether inline compact works, whether session store and provider filtering preserve `/fork` and `/resume`, and whether WeClaw display fields need token-window plus char-budget separation.
- This node updates planning documentation and runtime internal version metadata only. It does not move `v0.3.9-alpha`, create a GitHub Release, or rebuild Release assets.

## p2.10a51-post-v0.3.9-alpha-release-doc-sync

- Synchronized post-release documentation after the `v0.3.9-alpha` GitHub pre-release was created successfully.
- Verified release state before this sync: `v0.3.9-alpha = 677d923`, GitHub Release title `CodeXchange v0.3.9-alpha`, non-draft and pre-release, assets `bootstrap.sh` and `install.sh` uploaded.
- Confirmed `v0.3.8-alpha = dfdc629` remained unmoved and plain `v0.3.9` did not exist.
- Updated developer handbooks from release-readiness wording to published pre-release wording.
- Updated the long-term mainline checklist so the `v0.3.9-alpha` public pre-release task is marked completed.
- Updated README behavior wording from future publication to currently installable pre-release.
- Updated runtime internal version metadata to `p2.10a51-post-v039-alpha-release-doc-sync`.
- No public tag was moved, no new GitHub Release was created, and no Release assets were rebuilt in this documentation sync node.

## p2.10a50-v039-alpha-release-readiness-sync

- Prepared the repository for the `v0.3.9-alpha` public pre-release.
- Confirmed pre-patch baseline: `master = origin/master = e8ca586`, internal tag `p2.10a49-final-handoff-sync = e8ca586`, and public Release tag `v0.3.8-alpha = dfdc629`.
- Confirmed `v0.3.9-alpha`, plain `v0.3.9`, and erroneous plain `v0.3.5` did not exist before this readiness node.
- Updated the English and Chinese developer handbooks with a durable long-term mainline task checklist.
- Added the full-source-first audit rule: source and documentation changes must be designed from uploaded complete files or complete copied source/document files, not from grep/rg snippets.
- Updated README and README.zh-CN behavior-change tables for the upcoming `v0.3.9-alpha` release line.
- Added the WeClaw integration requirement: `weclaw_dev >= v0.1.9-alpha` when WeClaw integration is used.
- Prepared release notes for `v0.3.9-alpha` without a duplicate release-title line and without developer-only details.
- Updated runtime public version metadata to `v0.3.9-alpha` and package version to `0.3.9a0`.
- This node does not create the GitHub Release or push the public `v0.3.9-alpha` tag. The public pre-release must be created in a separate explicit release step.

## p2.10a49-final-handoff-sync

- Finalized the handoff state after p2.10a48.
- Current pre-sync baseline: `master = origin/master = 2e0edd0`, internal tag `p2.10a48-weclaw-full-telemetry-contract = 2e0edd0`, and public Release tag `v0.3.8-alpha = dfdc629`.
- Recorded that the WeClaw side accepted the p2.10a48 reporting baseline and started initial integration.
- Recorded that WeClaw second-round requirements will be proposed after their audit and should continue in a new development conversation.
- Updated the English and Chinese developer handbooks so current state, current major-line summary, and task bus no longer describe p2.10a46 structured degraded fields as the active P0 state.
- Updated developer runtime internal version metadata to `p2.10a49-final-handoff-sync`.
- No public Release tag was moved, no GitHub Release was rebuilt, and no Release assets were changed.

## p2.10a48-weclaw-full-telemetry-contract

- Reopened P0 after the p2.10a46/p2.10a47 basic contract and documentation sync because the original WeClaw requirements were not fully closed by structured degraded fields.
- Added runtime WeClaw telemetry aggregation from the cox usage ledger for `tokens.last_turn`, `tokens.session_total`, and `tokens.auxiliary_model_calls`.
- Added runtime WeClaw pricing and cost fields based on the existing cox pricing cache and usage ledger `estimated_cost_usd` values.
- Added provider balance integration into runtime WeClaw status.
- Updated CLI `cox status [thinking] --weclaw-json` to prefer the runtime `/v1/proxy/weclaw/status` endpoint when reachable.
- Added tests for HTTP full telemetry contract and CLI runtime WeClaw status preference.
- Token counts are exact provider-reported ledger totals. Cost is estimated from cox pricing cache. Prompt subcategory splits remain explicitly not provider-reported without a future audited tokenizer layer.
- No public Release tag was moved, no GitHub Release was rebuilt, and no Release assets were changed.

## p2.10a47-doc-weclaw-contract-sync

- Synchronized the English and Chinese developer handbooks after the p2.10a46 WeClaw contract acceptance checkpoint.
- Updated current-state sections to point to the p2.10a46 verified baseline: `master = origin/master = 3e6b922`, internal tag `p2.10a46-weclaw-usage-test-env-isolation = 3e6b922`, and public Release tag `v0.3.8-alpha = dfdc629`.
- Updated the task bus so P0 is recorded as accepted with structured degraded fields, while P1 remains the future AnyCodeX-level generalized provider architecture direction.
- Recorded the p2.10a46 delivery surfaces, ready fields, degraded fields, and sanitized test-environment lesson.
- Updated developer runtime internal version metadata to `p2.10a47-doc-weclaw-contract-sync`.
- No public Release tag was moved, no GitHub Release was rebuilt, and no Release assets were changed.

## p2.10a46-weclaw-usage-test-env-isolation

- Completed the P0 WeClaw contract acceptance checkpoint.
- Final merged state: `master = origin/master = 3e6b922`, internal tag `p2.10a46-weclaw-usage-test-env-isolation = 3e6b922`, public Release tag `v0.3.8-alpha = dfdc629`.
- Delivered accepted CLI surfaces: `cox profile status <profile> --json`, `cox profile set-effort <profile> <effort> --json`, and `cox status [thinking] --weclaw-json`.
- Delivered accepted HTTP surfaces: `GET /v1/proxy/weclaw/profile-status?profile=cox` and `GET /v1/proxy/weclaw/status?profile=cox`.
- Ready fields include effective model, Codex model, model conflict, force-model status, user-facing effort, DeepSeek effort, Codex effort, token-level context-window declarations, and char-level runtime compaction/trimming data.
- Structured degraded fields remain for turn/session token attribution, auxiliary model calls, pricing, cost, and balance-in-status. They must remain explicit `available=false` or `missing=[...]` values until exact sources are audited.
- Fixed the usage ledger test isolation gap by clearing model override environment variables before asserting request-model attribution.
- Sanitized full tests passed with `435 passed`; focused WeClaw acceptance passed with all acceptance flags true.
- No public Release tag was moved, no GitHub Release was rebuilt, and no Release assets were changed.

## p2.10a45-handbook-section-structure-cleanup

- Cleaned handbook section structure after p2.10a44.
- Moved the English `Provider bridge terminology contract` into numbered section 8 as `### 8.1 Provider bridge terminology contract`.
- Added the English `### 8.2 Model configuration command contract` to mirror the Chinese command contract.
- Moved the Chinese `模型配置命令契约` into numbered section 8 as `### 8.2 模型配置命令契约`.
- Added the Chinese `### 8.1 工具桥接术语契约` so the English and Chinese handbooks remain structurally aligned.
- Added a documentation structure discipline rule: stable handbook rules must live under numbered chapters or versioned history sections; do not leave unnumbered standalone islands.
- No user-facing README/TROUBLESHOOTING content was changed.
- No public Release tag was moved, no GitHub Release was rebuilt, and no Release assets were changed.

## p2.10a44-doc-marker-discipline-cleanup

- Removed marker-only compatibility text that had been added to the p2.10a43 internal handbook sections.
- Reframed the p2.10a43 handbook content as normal command-contract documentation instead of validation-marker accommodation.
- Added an internal patch-discipline rule: verification markers must be derived from real source, tests, and document text, and documentation must not be polluted to satisfy a validation string.
- Updated developer runtime internal version metadata to `p2.10a44-doc-marker-discipline-cleanup`.
- No user-facing README/TROUBLESHOOTING content was changed.
- No public Release tag was moved, no GitHub Release was rebuilt, and no Release assets were changed.

## p2.10a43-effort-json-refresh-control

- Added explicit refresh control for WeClaw/CI-safe effort configuration.
- `cox config set-effort` now accepts `--json` for parser/help consistency with the always-JSON output contract.
- `cox config set-effort` and `cox profile set-effort` now accept `--no-refresh`, which routes through the existing post-config apply disabled mode and returns `post_config_apply.status = "skipped"`.
- Preserved effort semantics: DeepSeek/env effort may be `max`, Codex `model_reasoning_effort` stores `xhigh`, compatibility inputs `low`, `medium`, `minimal`, and `none` normalize to DeepSeek `high`, and `plan_mode_reasoning_effort` stays `high`.
- Added isolated tests to ensure `--no-refresh` does not check or restart live proxy ports.
- No public Release tag was moved, no GitHub Release was rebuilt, and no Release assets were changed.

## p2.10a41-task-bus-weclaw-acceptance-audit

- Added a long-term task bus to the internal developer handbooks to prevent future mainline drift across inserted tasks and new conversations.
- Set P0 as WeClaw contract acceptance and gap closure. The generalized provider architecture remains a P1 follow-up and must not displace the P0 acceptance task.
- Recorded the drift cause: p2.10a40 continued into architecture planning after inserted documentation/version/naming tasks, instead of returning to the original WeClaw interface acceptance checklist.
- Added a read-only acceptance audit plan for profile/effort interfaces, WeClaw status JSON, HTTP endpoint discovery, pricing/cost/token/compaction gaps, and isolated HOME effort behavior.
- No public Release tag was moved, no GitHub Release was rebuilt, and no Release assets were changed.

## p2.10a40-generalized-provider-architecture-audit-report

- Converted the read-only generalized provider architecture audit into an internal planning node.
- Confirmed the current baseline before the planning patch: `master = origin/master = p2.10a39 = e0b16fd`, public Release tag `v0.3.8-alpha = dfdc629`, and a clean worktree.
- Confirmed the naming boundary: user-facing docs, code, scripts, and tests keep the current CodeXchange name; AnyCodeX remains future-name planning text only inside developer docs.
- Identified the main DeepSeek-specific runtime seams: `DeepSeekClient`, `DEEPSEEK_*` runtime environment variables, `reasoning_content`, thinking-mode history repair, Responses-to-ChatCompletions conversion, stream event normalization, usage/cost accounting, model catalog assumptions, and WeClaw profile/status contracts.
- Defined the next implementation order as provider-capability metadata first, then upstream adapter interfaces, then reasoning/thinking strategy separation, then stream and tool-call normalization.
- No public Release tag was moved, no GitHub Release was rebuilt, and no Release assets were changed.

## p2.10a39-name-boundary-cleanup

- Cleaned remaining legacy lowercase alternate-name branch-plan wording from internal documentation so future real branches use neutral names such as `work/p2.10-generalized-provider-architecture-audit`.
- Kept AnyCodeX as a future plan name and possible future brand in developer-only planning text, while keeping code, commands, tags, branches, installers, wrappers, public paths, and user-facing documentation under the current CodeXchange name.
- Updated developer runtime internal version metadata to `p2.10a39-name-boundary-cleanup`.
- Fixed the p2.10a39 validation bug: the validation script incorrectly treated allowed internal AnyCodeX future-name planning text as forbidden, then introduced a self-conflicting lowercase legacy spelling in the development log.
- No public Release tag was moved, no GitHub Release was rebuilt, and no Release assets were changed.
## p2.10a38-version-metadata-name-boundary

- Updated runtime internal version metadata from the stale p2.10a35 tag to `p2.10a38-version-metadata-name-boundary`, while keeping public version metadata at `v0.3.8-alpha`.
- Updated version metadata tests so `cox --version` must report the declared current internal tag.
- Clarified the naming boundary: CodeXchange remains the current project and public product name. AnyCodeX is a future plan name and possible future brand, not a current code, command, tag, branch, installer, wrapper, public-path, or user-facing documentation name.
- Reframed future provider work as AnyCodeX-level generalized provider architecture in internal developer documentation only.
- No public Release tag was moved, no GitHub Release was rebuilt, and no Release assets were changed.

## p2.10a37-sanitized-test-env-rule

- Added a handbook rule for sanitized test environments after p2.10a36 showed that full-suite failures can be caused by local exported model/provider/API-key variables rather than by the patch under test.
- The recurring contamination pattern includes `COX_MODEL`, `COX_FORCE_MODEL`, `COX_IMAGE_PROVIDER`, `COX_IMAGE_DOWNLOAD`, provider API keys, and web-search/image-provider variables.
- Future development scripts should record relevant environment overrides and rerun failing subsets plus full tests under a sanitized environment before attributing failures to the patch.
- No public Release tag was moved, no GitHub Release was rebuilt, and no Release assets were changed.

## p2.10a36-release-state-doc-sync

- Synchronized documentation with the verified GitHub Release state: `v0.3.8-alpha` is the current non-draft, non-prerelease GitHub Release at `dfdc629`, while `master = origin/master = 659854a`.
- Updated README and README.zh-CN behavior-change migration notes that still told users to install the pre-release or wait for Latest promotion.
- Updated both developer handbooks so the current public line is described as a public alpha Release rather than a GitHub pre-release, while preserving the historical pre-release validation policy for future Release candidates.
- No public Release tag was moved, no GitHub Release was rebuilt, and no Release assets were changed.

## p2.10a35-docs-handoff-and-replacement-discipline

- Updated the current-state blocks in both developer handbooks after p2.10a34. The current internal line is `p2.10a35-docs-handoff-and-replacement-discipline`, while `v0.3.8-alpha` remains at `dfdc629`.
- Condensed p2.10a30 through p2.10a34 wrapper title experiments into the current effective p2.10a34 design: route preparation, bounded runtime keeper, foreground real Codex execution, PID cleanup, and preservation of the real Codex return status.
- Recorded the replacement-discipline rule after repeated stale-anchor failures: prefer function-level, block-level, section-level, or AST-level whole replacement instead of fragile narrow string anchors.
- Confirmed tab color was abandoned for this line. Windows Terminal `--tabColor` is not a verified current-tab wrapper control path.
- No public Release tag was moved and no Release assets were rebuilt.

## p2.10a34-title-keeper-cleanup

- Bound the finite tab-title keeper lifecycle to the real Codex command lifecycle.
- The generated wrapper now records the keeper PID, stops and waits for it after Codex returns, and preserves the original Codex return status through a wrapper function.
- This prevents the title from being restored to CodeXchange after the user has already left Codex.

## p2.10a33-title-runtime-keeper

- Fixed both wrapper TTY gates so background title refresh can write `/dev/tty` even when stdout is redirected to `/dev/null`.
- Replaced the three-shot delayed title sequence with a bounded runtime keeper. The default is 60 seconds with a 1 second interval.
- Kept the wrapper foreground Codex execution model from p2.10a32 and did not change profile/model synchronization logic.

## p2.10a32-wrapper-foreground-codex

- Changed generated Codex wrappers to keep the wrapper process alive while the real Codex binary starts.
- The wrapper now prepares the matching cox route, schedules the finite delayed OSC 0/2 title refresh sequence, and runs the real Codex binary as the final foreground command.
- This preserves the real Codex return status naturally while giving the delayed title refresh process a reliable execution window.

## p2.10a31-post-start-title-refresh

- Changed generated Codex wrappers to avoid setting the tab title before Codex startup.
- Kept a finite delayed OSC 0/2 refresh sequence after the matching cox route is prepared, using 8s, 4s and 8s delays.
- Documented the observed failure mode where Codex overwrites a pre-start title with the working-directory title, and where undefined test helper names can print shell job `Exit 127` messages.

## p2.10a30-profile-model-sync-title-delay

- Added `cox profile repair --managed-only --json` to repair managed Codex profile `model` fields according to each profile's effective upstream model.
- Kept `codex_model`, `effective_model`, and `model_conflict` as diagnostics, while making normal managed state repairable to `model_conflict=false`.
- Changed generated Codex wrappers to schedule short delayed OSC 0/2 tab-title refreshes, including a 5-second refresh, after starting the matching cox route and before executing the real Codex binary.
- Preserved the non-duplicated 🐦‍🔥 emoji candidate rule.

本文件保存长期、可回溯的开发流水账。它不是新对话默认上下文。只有需要追溯具体版本、错误、测试或Release细节时才查阅。

## p2.10a29-weclaw-runtime-contract-unification

- Scope: make cox the owner of Codex profile effort semantics and expose machine-readable profile/status skeletons for WeClaw.
- Root cause: `config set-effort` wrote the same canonical DeepSeek effort into `COX_REASONING_EFFORT` and Codex `model_reasoning_effort`, allowing `max` to enter Codex config.
- Contract: DeepSeek/env effort may be `max`, but Codex profile effort must be `xhigh`; `xhigh` input normalizes to DeepSeek `max`.
- Added structured profile status and WeClaw status JSON skeletons while marking unaudited token, pricing, cost, balance, auxiliary-call, and compaction fields unavailable instead of letting WeClaw guess.
- Install/upgrade/uninstall review: installer env effort now uses DeepSeek semantic `max`; install profile generation still writes Codex-compatible `xhigh`; no Release assets or public tags are moved in this internal patch phase.


## p2.10a27-doc-structure-process-rules

- Scope: structured documentation cleanup after p2.10a26 VM validation.
- Starting point: `master = origin/master = 54d81ab`, public pre-release `v0.3.8-alpha = 54d81ab`, internal tag `p2.10a26-wrapper-start-plan-mode-hardening = 54d81ab`.
- Changes: updated current state in both developer handbooks, replaced stale p2.9/v0.3.7 current-state blocks with p2.10/v0.3.8-alpha, added the eight failure-prevention classes, and clarified that install, upgrade, uninstall, rollback, wrappers, user config, Release assets, and VM/user-path validation are part of every affected task.
- Documentation structure rule: README stays user-facing, TROUBLESHOOTING stays operator recovery guidance, developer-handbook stays the AI startup context, and development-log stays chronological.
- Public Release note: this p2.10a27 task does not move or rebuild `v0.3.8-alpha`.

## p2.10a24-installer-ui-live-image-validation

- Removed the visible bootstrap `log:` line above the installer banner.
- Passed the bootstrap log path into `install.sh` and showed both bootstrap and install logs under `Install logs`.
- Changed guided image API validation from a non-generating probe to live image generation.
- Added a dim warning under the image provider family menu explaining that validation generates one safe test image and may consume provider credits.
- Saved generated validation images under `/tmp/codexchange-image-validation-*`.
- Rebuilt `v0.3.8-alpha` pre-release assets after merge.
## p2.10a23-installer-image-validation-tag-fetch

- Added the missing `test_image_api_key()` shell function used by the guided image generation API configuration flow.
- Added installer test coverage that verifies project-like shell calls are defined before use.
- Changed installer tag refresh commands to `git fetch --tags --force origin` to support repeatedly rebuilt pre-release tags such as `v0.3.8-alpha`.
- Rebuilt `v0.3.8-alpha` pre-release assets after merge.
## p2.10a22-port-label-effort-surface

- Renamed the guided installer prompt from `Stable proxy port` to `Non-Thinking proxy port`.
- Removed the duplicate standalone Codex wrapper help line so prompt-specific help is only rendered by the menu detail mechanism.
- Changed the CLI upgrade profile reinstall path from `medium` to `high` for the non-thinking DeepSeek Codex profile.
- Kept compatibility normalization: old `low` and `medium` inputs normalize to DeepSeek `high`, while `xhigh` and `max` normalize to DeepSeek `max`.
- Rebuilt `v0.3.8-alpha` pre-release assets after merge.
## p2.10a21-installer-wrapper-help-placement

- Moved the Codex wrapper explanatory line from above the wrapper question into the menu renderer.
- The explanation now appears under `Install codex wrapper...` and before the global arrow-key hint.
- Rebuilt `v0.3.8-alpha` pre-release assets after merge.
## p2.10a20-installer-secret-prompt-wrapper-help

- Dimmed secret prompt helper text.
- Changed empty secret input with an existing model API key to keep the existing key without reporting it as newly entered characters.
- Added installer guidance explaining that the Codex wrapper enables `codex --profile deepseek` and `codex --profile cox` while automatically starting or refreshing the local cox backend.
- Rebuilt `v0.3.8-alpha` pre-release assets after merge.
## p2.10a19-installer-menu-column-alignment

- Aligned installer selected-row and unselected-row option value columns.
- Changed the unselected menu prefix from three spaces to two spaces so `▶ ` and blank rows occupy the same marker width.
- Rebuilt `v0.3.8-alpha` pre-release assets after merge.
## p2.10a18-installer-minimal-arrow-ui

- Removed the duplicate old `read_menu_choice_from_tty()` definition that overrode the p2.10a17 renderer.
- Removed numeric/text fallback from TTY menus.
- Kept only ↑/↓ or j/k movement, Enter selection, and Backspace back/skip behavior.
- Dimmed menu helper text and input default hints.
- Colored the installer logo version.
- Hid duplicate bootstrap Python and installer-ready messages from the visible UI.
- Rebuilt `v0.3.8-alpha` pre-release assets after merge.

### CLI version metadata source guard

- Fixed the p2.10a18 finalization blocker where `app.py` declared the new internal version but `cox --version` still reported the previous internal tag.
- Root cause: CLI version metadata was reading `proxy_app.PROXY_INTERNAL_VERSION`; the package-level `app` name can resolve to the FastAPI object rather than the `codexchange_proxy.app` module.
- Added a test requiring CLI output to include the declared `PROXY_INTERNAL_VERSION`.

### Declared internal version precedence

- Finalized the p2.10a18 CLI version source fix by making the declared `PROXY_INTERNAL_VERSION` win over any existing `p*` tag on the current HEAD.
- This prevents a pre-tag finalization build from reporting the previous internal tag before the new p-tag is created.

## p2.10a17-installer-menu-render-layout-polish

- Reworked installer arrow-menu row rendering to truncate to terminal width and avoid wrapped-line residue.
- Added full-row reverse-video highlighting for selected rows.
- Made listed numeric values return immediately, including `0` skip/back choices.
- Displayed the arrow-menu help hint only once per installer run.
- Added blank separators between guided configuration sections.
- Rebuilt `v0.3.8-alpha` pre-release assets after merge.
## p2.10a16-installer-logo-heredoc-runtime-fix

- Fixed installer logo runtime rendering by using quoted heredocs for ASCII art.
- Kept the visible version line beside CodeXchange.
- Added a runtime logo smoke test so `bash -n` cannot miss heredoc command-substitution failures.
- Rebuilt `v0.3.8-alpha` pre-release assets after merge.
## p2.10a15-installer-provider-flow-source-fallback

- Added installer logo install-ref display.
- Removed Supported labels from Yes/No menus.
- Changed model and image provider setup to use provider-family menus followed by endpoint/region submenus.
- Restored unsupported provider visibility for Mimo and Baichuan without prompting for unusable keys.
- Added key-entry character-count feedback and three-empty-submission skip behavior.
- Added tagged source archive fallback when git clone/fetch fails during VM installation.
## p2.10a14-install-log-source-polish-fix

- Fixed installer source logging to use `INSTALL_LOG` instead of undefined `LOG_FILE`.
- Added installer test coverage to prevent `LOG_FILE` references.
- Rebuilt `v0.3.8-alpha` pre-release assets after merge.
- Purged jsDelivr tag cache best-effort for `v0.3.8-alpha/bootstrap.sh`.
## p2.10a13-installer-tty-menu-ui-polish

- Removed verbose source URL display from interactive bootstrap/install screens.
- Kept source information in logs.
- Routed installer arrow menus through `/dev/tty` so they still work when stdout is captured.
- Rebuilt `v0.3.8-alpha` pre-release assets after merge.
## p2.10a12-bootstrap-install-ref-source-banner

- Fixed bootstrap `--install-ref` handling so pre-release fresh VM installs download the matching release asset `install.sh` first instead of GitHub Latest.
- Added bootstrap/installer source display under the banner.
- Added dry-run coverage for `bootstrap.sh --install-ref v0.3.8-alpha`.
- Rebuilt `v0.3.8-alpha` pre-release assets after merge.
## p2.10a11-model-provider-experimental-labels

- Reclassified non-DeepSeek model providers from Supported to Experimental in installer/configuration UX.
- Kept DeepSeek as the only Supported model provider.
- Documented that API connectivity is not equivalent to full Codex workflow support.
- No public Release tag was moved.
## p2.10a10-installer-arrow-provider-ui

- Added arrow-key installer provider selection with numeric/text fallback.
- Kept model, web search, and image generation provider menus explicit.
- Updated image-provider user hints to prefer explicit Qwen / DashScope region provider names.
- Documented that regional Qwen providers must not collapse into a single generic entry.
- No public Release tag was moved.
## p2.10a9-release-v0.3.8-alpha

- Prepared and published `v0.3.8-alpha` as a GitHub pre-release, not Latest.
- Updated runtime public version metadata to `v0.3.8-alpha`.
- Updated package PEP440 version to `0.3.8a0`.
- Release validation path is `cox upgrade --alpha` on a fresh VM before promoting the same GitHub Release to Latest.
- Release notes body must start from `Highlights:` and must not duplicate the GitHub Release title.
## p2.10a8-upgrade-alpha-terminal-title

- Added `cox upgrade --alpha`, which resolves the newest non-draft GitHub pre-release while preserving the default `cox upgrade` behavior against GitHub Latest Release.
- Added Codex wrapper terminal tab title randomization for `deepseek` and `cox` profiles. The format is `[emoji]CodeXchange` using the maintainer-supplied emoji candidate list.
- Documented the pre-release VM validation principle: publish a pre-release, test with `cox upgrade --alpha`, then promote the same GitHub Release to Latest after validation passes.
- No public Release tag was moved or recreated.
## p2.10a7-doc-sync

- Synchronized README, README.zh-CN, developer handbook, Chinese handbook, and this development log after the p2.10a6 installer model provider surface repair.
- Developer runtime internal version now advances to `p2.10a7-doc-sync`, while the public runtime version remains `v0.3.7-alpha | 466706f` until the next public Release.
- No public Release tag was moved or recreated.

## p2.10a6-installer-model-provider-surface

- Repaired `scripts/install.sh` so guided installer model API setup no longer presents ambiguous public choices such as `GLM / Z.AI`, generic `Qwen / DashScope`, Mimo, or Baichuan.
- The installer now mirrors the public model API provider surface:
  - `zhipu`
  - `zhipu-coding`
  - `zai`
  - `zai-coding`
  - `qwen-beijing`
  - `qwen-singapore`
  - `qwen-us`
  - `custom`
- Kept legacy `glm`, `qwen`, `dashscope`, and related aliases only as backward-compatible selection inputs, mapping them to explicit canonical providers.
- Added `tests/test_installer_model_provider_surface.py` and updated installer UI tests to prevent reverting to generic provider labels.
- Validation passed before merge: `git diff --check`, `bash -n bootstrap.sh`, `bash -n scripts/install.sh`, focused tests, broader tests, and full suite `379 passed`.

## 记录格式规范

每条记录使用统一模板：

```text
## <date> <tag-or-branch> <short-title>

- 范围：
- 起点：
- 变更：
- 测试：
- 结果：
- 风险：
- 后续：
```

规则：

- 记录客观事实，不写泛泛总结。
- 必须写commit、tag、branch、测试结果和是否推送。
- 失败也记录，说明阻断点和恢复方式。
- 不记录API key值。
- 长日志路径写`/tmp/*.txt`，不要把完整日志粘进开发手册。
- 公开Release tag和内部tag必须分开记录。
- Release notes正文不得重复GitHub Release标题。

## 2026-05-13 p2.9a18 / v0.3.7-alpha 发布

- 范围：发布`v0.3.7-alpha`。
- 起点：`p2.9a17-vm-github-proxy-handbook = e5f79c2`。
- 变更：安装器受影响机器修复、installed checkout同步、local bin ownership guard、provider验证语义、VM代理经验、Release文档修正。
- 测试：focused tests通过，full tests为`359 passed in 18.98s`。
- 结果：`v0.3.7-alpha = 466706f`，`p2.9a18-release-v0.3.7-alpha = 466706f`，GitHubRelease已创建，资产`bootstrap.sh`和`install.sh`可访问。
- 风险：发布过程中曾出现半发布状态，公开tag先推送成功，但work分支、internal tag、master和GitHubRelease未全部完成。
- 恢复：改用HTTPS补齐push、master、Release和本机运行时刷新。
- 后续：必须将Release流程做成幂等状态机。

## 2026-05-13 p2.9a19 Release错题和handoff同步

- 范围：将`v0.3.7-alpha`发布经验写入开发手册和handoff。
- 起点：`master = origin/master = 466706f`。
- 变更：更新`OPERATIONS.md`、`docs/custom_api_handoff.md`、`docs/developer-handbook.zh-CN.md`、`docs/handoff-for-developers.en.md`、`docs/handoff-for-developers.zh-CN.md`。
- 测试：静态检查通过。
- 结果：`master = origin/master = 5013413`，`p2.9a19-release-lessons-handoff = 5013413`。
- 风险：文档继续分散，维护成本高。
- 后续：p2.9a20执行文档收敛。

## 2026-05-13 p2.9a20 文档重构

- 范围：重构文档体系。
- 起点：`master = origin/master = 5013413`。
- 目标：README面向用户，TROUBLESHOOTING面向用户排障，developer-handbook作为新对话启动包，development-log作为长期详尽日志。
- 关键决策：不再保留幽灵文档和幽灵测试。删除旧文档路径时必须同步测试契约。
- 当前过程：先尝试保留stub过测，后修正为测试契约跟随新文档结构。
- 风险：测试中仍可能存在旧文档路径硬编码，需要逐项替换。
- 后续：完成p2.9a20提交、内部tag、push和fast-forward master。

## 2026-05-13 p2.9a21 Bilingual developer handbook restoration

- Scope: restore the missing maintainer knowledge after p2.9a20 and introduce an English-primary developer handbook.
- Starting point: `master = origin/master = b160525`, `p2.9a20-docs-consolidation = b160525`.
- Change: add `docs/developer-handbook.md` as the primary AI startup context, keep `docs/developer-handbook.zh-CN.md` as the Chinese mirror, preserve detailed history in this log.
- Reason: p2.9a20 consolidated documentation correctly but compressed the developer handbook too aggressively and left only the Chinese handbook.
- Test contract: active documents now include both English and Chinese developer handbooks.
- Expected result: `master`, `origin/master`, and `p2.9a21-handbook-bilingual-restoration` point to the same new commit.

## p2.9a22-version-metadata-policy-audit

- Clarified runtime version metadata as a dual-track policy.
- User installations from a public Release tag report the public `v~` tag and the internal `p~` tag that existed when the Release tag was cut.
- Developer checkout runtime on `master` keeps the current public `v~` until the next Release, but its internal `p~` must advance with the latest `master` internal tag.
- Corrected the GitHub CLI rule: `gh release view --json` does not support `isLatest`; this is a command schema limitation, not an installed-version issue.
- Updated current developer runtime metadata to `p2.9a22-version-metadata-policy-audit` while keeping public Release `v0.3.7-alpha` and public commit `466706f`.

## p2.9a23-script-scope-safety-note

- Recorded a script-scope safety rule after the development-entrypoint wrapper repair script failed with `NameError: name 'ts' is not defined`.
- Shell variables are not available inside Python heredocs unless explicitly passed through environment variables.
- Future generated commands must either pass shell values into Python through environment variables or generate those values inside Python.
- For real-HOME modifications, scripts must validate variables and preconditions before writing target files.

## p2.9a24-script-helper-signature-safety

- Recorded a second generated-command safety rule after a read-only mainline resume audit failed with `TypeError: run() got an unexpected keyword argument 'env'`.
- Helper function signatures in generated Python scripts must cover all later keyword arguments such as `env`, `timeout`, `check`, and `allow_fail`.
- Future commands should be statically checked for helper definition/call-site consistency before being given to the user.

## p2.9a25-provider-key-scope-doc-sync

- Scoped image provider diagnostics so a generic `COX_IMAGE_API_KEY` no longer marks every image provider as configured.
- Kept compatibility for the currently selected `COX_IMAGE_PROVIDER` while preserving provider-specific key variables for unselected providers.
- Made `set-image-api-key` and the guided wizard write provider-specific image API key variables in addition to the legacy generic variable.
- Updated README image provider examples from the old `glm` shortcut to explicit `zhipu` and `zai` examples.

## p2.9a26-provider-live-web-search-doc-sync

- Confirmed the real SerpAPI web search live probe on the developer machine.
- Command class: `cox doctor providers --kind web-search --provider serpapi --live --allow-spend`.
- Result: `doctor_status=ok`, `provider_ok=True`, HTTP status 200, `validation_method=fixed_query_search`, `validation_strength=live_query_probe`, `functional_probe=True`, and `functional_validation=performed`.
- The probe did not print API key values.
- Other web search providers remain untested because their API keys are not configured.
- This validates the CodeXchange provider bridge path for SerpAPI. It does not by itself prove the full Codex TUI end-to-end tool selection path, which should be validated separately before release readiness.

## p2.9a27-zhipu-live-image-doc-sync

- Confirmed the real Zhipu image generation live probe on the developer machine.
- Command class: `cox doctor providers --kind image --provider zhipu --live --allow-spend`.
- Result: `doctor_status=ok`, `provider_ok=True`, HTTP status 200, `validation_method=live_image_generation`, `validation_strength=live_generation_probe`, `functional_probe=True`, and `functional_validation=performed`.
- The probe returned image evidence: `has_image=True` and `evidence=data_url_or_base64`.
- The probe did not print API key values.
- This validates the CodeXchange provider bridge path for Zhipu image generation. It does not by itself prove the full Codex TUI end-to-end tool selection path, which should be validated separately before release readiness.

## p2.9a29-qwen-region-endpoint-probe

- Fixed Qwen/DashScope provider diagnostics so `cox doctor providers --kind image --provider qwen_image --live --allow-spend` respects `COX_IMAGE_BASE_URL` and `DASHSCOPE_IMAGE_ENDPOINT`.
- Fixed the Qwen non-generation image API validation path to use the same regional endpoint override.
- Root cause: runtime image generation already respected `COX_IMAGE_BASE_URL`, but the CLI provider diagnostic path had a separate hardcoded Beijing endpoint.
- This prevents Singapore, US Virginia, and Germany Frankfurt DashScope keys from being incorrectly tested against the Beijing endpoint.

## p2.9a30-qwen-region-live-matrix-doc-sync

- Recorded the Qwen/DashScope image regional live-probe matrix after p2.9a29 fixed regional endpoint overrides in CLI provider diagnostics.
- Beijing live probe passed: `qwen-image-2.0-pro`, endpoint `https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation`, HTTP 200, `has_image=True`, evidence `output_choice_image`.
- Singapore live probe passed: `qwen-image-2.0-pro`, endpoint `https://dashscope-intl.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation`, HTTP 200, `has_image=True`, evidence `output_choice_image`.
- US Virginia endpoint override worked: endpoint `https://dashscope-us.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation`, but `qwen-image-2.0-pro` and `qwen-image-2.0-pro-2026-03-03` returned `Model not exist`.
- Germany Frankfurt workspace endpoint override worked: endpoint `{workspace}.eu-central-1.maas.aliyuncs.com`, but `qwen-image-2.0-pro` returned `Model not exist`.
- Conclusion: keep `qwen_image` validated for Beijing and Singapore. Treat US Virginia and Germany as model-availability failures for the tested Qwen Image models, not as endpoint override failures.
- Future work: if US/Germany Alibaba image generation is required, introduce or test a separate Wan image/text-to-image provider mode.

## p2.9a34-brave-provider-surface-removal

- Removed Brave Search from public/guided web search provider surfaces because Brave does not provide a free API key path before subscription.
- Updated README and README.zh-CN command examples to list SerpAPI, Tavily, Exa, and Firecrawl only.
- Removed Brave from CLI configuration choices, provider configuration status, and the `doctor providers` default web-search matrix.
- Kept low-level runtime compatibility separate from the public provider catalog to avoid unnecessarily breaking existing manual Brave configurations.

## p2.9a37-web-search-live-matrix-doc-sync

- Recorded current web search provider live-probe status after the Brave provider surface removal.
- Tavily live probe passed: endpoint `https://api.tavily.com/search`, HTTP 200, `validation_strength=live_query_probe`, `functional_validation=performed`.
- Exa live probe passed: endpoint `https://api.exa.ai/search`, HTTP 200, `validation_strength=live_query_probe`, `functional_validation=performed`.
- Firecrawl live probe passed: endpoint `https://api.firecrawl.dev/v2/search`, HTTP 200, `validation_strength=live_query_probe`, `functional_validation=performed`.
- SerpAPI remains the configured existing primary web search path.
- Brave Search remains removed from public/guided configuration because API key creation requires a paid subscription before testing.
- Current public/guided web search provider list: SerpAPI, Tavily, Exa, Firecrawl.

## p2.9a38-image-provider-live-matrix-doc-sync

- Recorded current image provider live-probe status after the Qwen regional matrix, Stability AI probe, and fal.ai probe.
- Qwen Image Beijing passed: `qwen-image-2.0-pro`, HTTP 200, image evidence present.
- Qwen Image Singapore passed: `qwen-image-2.0-pro`, HTTP 200, image evidence present.
- Qwen Image US Virginia endpoint override worked, but `qwen-image-2.0-pro` and `qwen-image-2.0-pro-2026-03-03` returned `Model not exist`.
- Qwen Image Germany Frankfurt workspace endpoint override worked, but `qwen-image-2.0-pro` returned `Model not exist`.
- Stability AI reached the official endpoint but was blocked at the Cloudflare layer with Error 1010 `browser_signature_banned`; do not bypass or retry aggressively.
- fal.ai reached the provider/account layer but live generation failed because the account balance was exhausted.
- Current interpretation: Qwen Image is validated for Beijing and Singapore; US/Germany are model-availability failures for the tested Qwen Image models; Stability is a sanctioned-access/WAF issue; fal.ai needs balance top-up before retesting.

## p2.9a39-model-api-live-matrix-doc-sync

- Recorded current model API live verification matrix.
- DeepSeek remains the existing primary path and release baseline.
- Kimi / Moonshot endpoint was reachable at `https://api.moonshot.ai/v1/models`, but the provided key returned HTTP 401 `Invalid Authentication`; mark as endpoint reachable but not verified, not as unsupported.
- GLM / Zhipu / Z.AI `/models` validation passed across the tested key-source by endpoint matrix:
  - Domestic BigModel general: `https://open.bigmodel.cn/api/paas/v4`.
  - Domestic BigModel Coding Plan: `https://open.bigmodel.cn/api/coding/paas/v4`.
  - Z.AI general: `https://api.z.ai/api/paas/v4`.
  - Z.AI Coding Plan: `https://api.z.ai/api/coding/paas/v4`.
  - Both the domestic BigModel key and the Z.AI key passed against all four endpoints.
- Qwen / DashScope pay-as-you-go `/models` validation passed:
  - Beijing: `https://dashscope.aliyuncs.com/compatible-mode/v1`, `qwen-plus`.
  - Singapore: `https://dashscope-intl.aliyuncs.com/compatible-mode/v1`, `qwen-plus`.
  - US Virginia: `https://dashscope-us.aliyuncs.com/compatible-mode/v1`, `qwen-plus-us`.
- Qwen Coding Plan and Token Plan were not script-tested because official usage constraints distinguish them from ordinary automation-style probes; they require guided config and tool-path validation.
- Custom provider is validated as a mechanism because the GLM/Zhipu/Z.AI and Qwen matrices used `--provider custom` with explicit base URLs and models.
- Future README, wizard, and config guidance must distinguish verified, endpoint reachable but auth failed, implemented but not yet verified, not script-tested, and abandoned states. Do not mark untested providers as unsupported.
- After matrix testing, prepare a separate architecture audit branch for a potential AnyCodeX-level generalized provider-architecture refactor. The audit should identify DeepSeek-specific logic such as `reasoning_content`, reasoning/thinking event handling, model catalog assumptions, and which proxy layers can be generalized across providers.

## p2.9a40-config-guide-provider-surface-repair

- Repaired the public configuration surface after p2.9a40 audit.
- Removed the remaining Brave Search README quick-reference row and removed Brave from the installer validation surface.
- Replaced ambiguous model API guide commands with explicit site and plan provider names:
  - `zhipu`, `zhipu-coding`, `zai`, `zai-coding`.
  - `qwen-beijing`, `qwen-singapore`, `qwen-us`.
- Kept legacy `glm` and `qwen` only as internal canonicalization/backward-config helpers, while tests prevent these shortcuts from being used as public CLI choices or recommended README commands.
- Added test coverage so README examples parse through the CLI and continue to distinguish provider states rather than reverting to a binary supported/unsupported label.

## p2.9a41-post-p2.9a40-handoff-sync

- Synced developer handbooks and the development log after the p2.9a40 provider-surface repair.
- Current post-p2.9a40 state:
  - `master=origin/master=cd8e4d9`.
  - Internal tag `p2.9a40-config-guide-provider-surface-repair=cd8e4d9`.
  - Public release tag `v0.3.7-alpha=466706f`, unchanged.
  - Plain public tag `v0.3.5` remains absent.
  - p2.9a40 passed full tests with `363 passed`.
- Provider-surface result:
  - Brave Search removed from public and guided web search configuration.
  - Model API public guidance now uses explicit Zhipu/Z.AI/Qwen site and plan providers rather than ambiguous `glm` and `qwen` shortcuts.
- Next planned line:
  - `work/p2.10-generalized-provider-architecture-audit`.
  - Start with read-only architecture evidence collection.
  - Assess DeepSeek-specific logic and the feasibility of an AnyCodeX-style provider abstraction.
  - Keep the broader third-party tool replacement objective separate from a single SerpAPI-style bridge.

## p2.10a2-config-refresh-and-effort-ux

- Added a CodeXchange-only post-config apply hook for successful config writes.
- API key, model, and effort config updates refresh already-running local stable/thinking proxy processes instead of requiring users to infer whether a restart is needed.
- The hook reports `all updates applied` when the local apply path completes.
- WeClaw stop/start/resume automation remains out of scope for this repository line.
- User-facing effort guidance no longer recommends `medium`; compatibility inputs `low` and `medium` are stored as `high` for the DeepSeek proxy path.
- README and README.zh-CN now include a compact behavior-change table for milestone CLI/workflow changes.

## p2.10a3-provider-validation-region-status

- Updated non-generation image validation so HTTP 200 provider error bodies are accepted as probe evidence when no authentication error is detected.
- Added explicit Qwen Image region choices for Beijing, Singapore, US Virginia, and Germany Frankfurt.
- Beijing and Singapore remain selectable for Qwen Image. US Virginia and Germany Frankfurt are listed but return a model-unavailable status for qwen-image-2.0-pro.
- Updated README behavior-change tables and developer handbook rules for provider validation classification and Qwen Image regional status.

## p2.10a4-config-menu-model-provider-ux

- Made `cox config set-model` the primary model API setup entrypoint for provider, upstream model, and optional API key configuration.
- Kept `cox config set-api-key` as a compatibility alias and added a compatibility/deprecation note in JSON output.
- Preserved the old model-only flow: `cox config set-model deepseek-v4-flash`.
- Updated the guided wizard model provider catalog so supported model API providers are selectable from the wizard instead of only DeepSeek being handled as supported.
- Updated installer guidance, README, README.zh-CN, developer handbooks, and tests to prefer `set-model` for model API setup.

## p2.10a5-post-config-ux-consistency

- Synchronized the model API command summary shown by `cox config wizard --non-interactive` with the full explicit provider surface.
- Replaced the remaining README and README.zh-CN Qwen Coding Plan custom-provider examples from the old `set-api-key --provider custom --model ...` form to the new `set-model <model> --provider custom --base-url ...` form.
- Added tests to prevent README custom model API examples from regressing to the old `set-api-key --provider custom` command shape.

### p2.10a25-version-install-plan-polish

- Fixed source-archive installs so wrapper-sourced version metadata can preserve the installed release commit even when the install directory is not a git checkout.
- Avoided noisy git clone fatal output when an existing install directory is non-git and non-empty by routing directly to source archive fallback.
- Quieted pip install phases with pip progress/version checks disabled and output captured in the install log.
- Clarified installer next steps for current-shell PATH refresh. p2.10a26 then pins native Codex Plan mode with `plan_mode_reasoning_effort`.

### p2.10a26-wrapper-start-plan-mode-hardening

- Made the CodeXchange Codex wrapper fail closed: it now starts the matching stable/thinking proxy route, verifies `cox status`, and refuses to enter Codex if the backend remains unavailable.
- Added `plan_mode_reasoning_effort = "high"` to generated Codex profiles so native Codex Plan mode uses the DeepSeek-compatible high effort.
- Kept proxy-side compatibility normalization for legacy or Codex-originated `low` and `medium` inputs, which still map to DeepSeek `high`.
- Added explicit uninstall rollback coverage to ensure a previous Codex command backup is restored after the CodeXchange wrapper is removed.
- Rebuilt `v0.3.8-alpha` pre-release assets after merge.


## p2.10a65-profile-tokenizer-accounting

Added profile-aware DeepSeek tokenizer accounting for WeClaw-facing status. The node bundles the official DeepSeek V3 tokenizer JSON resource, adds the `tokenizers` runtime dependency, records local prompt subcategory estimates under `tokens.profile_tokenizer` and `tokens.prompt_subcategory_split`, and keeps provider `usage` as the authoritative billing source. Codex TUI tokenizer behavior remains separate because the current `codex --profile deepseek debug models` evidence did not expose DeepSeek catalog entries.


## p2.10a66-tokenizer-resource-installer-sync

Moved DeepSeek tokenizer resource delivery out of the repository and into installer/user-machine synchronization through `cox tokenizer sync deepseek --json`. The runtime now uses managed tokenizer resources from the install/user resource directory or explicit env overrides, while provider usage remains billing-authoritative and local profile tokenizer counts remain estimates.


## p2.10a67-status-tokenizer-contract-consistency

Fixed the WeClaw status tokenizer contract so tokenizer resource availability is separated from observed prompt subcategory availability. `tokens.profile_tokenizer.available` can now be true before the route observes a prompt, while `tokens.prompt_subcategory_split.available=false` reports `profile_tokenizer_available_but_no_observed_prompt` with empty categories.


## p2.10a68-prompt-segment-ledger-audit

Added sanitized latest prompt segmentation for WeClaw Details and refined profile-tokenizer prompt categories. The `user` bucket is now the latest ordinary user segment, `user_history` stores earlier ordinary user-role segments, Codex tool transcripts are classified as `tool_output`, and AGENTS/memory/environment user-role blocks are classified as `environment`.


## p2.10a69-pricing-currency-turn-ledger

Added structured Pricing/Cost currency metadata for WeClaw, CNY display conversion based on cox-owned FX metadata, per-turn pricing context columns in the usage ledger, cash cost semantics, reasoning-cost unavailable semantics, and a more robust DeepSeek official pricing HTML parser.


## p2.10a70-pricing-cny-primary-source

Changed DeepSeek pricing priority so the Chinese official CNY pricing page is the default source for V4 Flash/Pro. The English USD pricing page remains available as fallback/i18n. Bundled pricing now uses CNY prices from https://api-docs.deepseek.com/zh-cn/quick_start/pricing/; FX metadata from p2.10a69 remains but is not the default path when CNY pricing is available.


## p2.10a71-docs-prerelease-notes

Prepared the cumulative `v0.3.9-alpha` Release note update. The note preserves the existing v0.3.9-alpha feature body and adds user-facing functional changes from the tokenizer/Details/Pricing-Cost closeout line: profile tokenizer sync/status, prompt segmentation, CNY-first Pricing/Cost, cash estimate, per-turn cost ledger semantics, and explicit reasoning-cost unavailable semantics. Development-only details are intentionally excluded from the Release note.

## p2.10a72 Handbook Latest-state sync

Date: 2026-05-18

Purpose:

- Synchronize the English and Chinese developer handbooks after the `v0.3.9-alpha` Latest Release closeout and VM validation.
- Correct stale current-state references to earlier pre-release commits such as `ac63043` and `677d923`.
- Record the trusted current state: `master = origin/master = 6ea67b2`, `v0.3.9-alpha = 6ea67b2`, `p2.10a71-docs-prerelease-notes = 6ea67b2`, GitHub Latest Release `v0.3.9-alpha`, `isPrerelease=false`, assets `bootstrap.sh` and `install.sh`.
- Preserve the rule that `v0.3.9` and `v0.3.5` must not exist.

Scope:

- Documentation-only.
- No public Release tag movement.
- No GitHub Release rebuild.
- No Release asset upload.


## p2.10a73 WeClaw status primary-scope contract

Date: 2026-05-19

Scope:

- Add `usage_events.session_id` and current-session filtering.
- Split latest primary, latest any model call, and latest auxiliary call in the WeClaw token contract.
- Keep `context_window.used_tokens` pinned to latest primary prompt tokens.
- Add explicit Compact/Trim progress numerator, denominator, ratio, and basis fields.
- Defer DeepSeek pricing discount parser changes to a later node.


## p2.10a74 DeepSeek pricing discount contract

Date: 2026-05-19

Scope:

- Make DeepSeek pricing CNY-first and discount-aware.
- Prefer the Chinese official pricing page for refresh.
- Expose `deepseek-v4-pro` effective prices, original prices, discount label/rate, and validity window.
- Keep pricing and cost semantics separated: historical turn costs remain ledger-based and must not be recomputed from the current price table.
- Public Release tag `v0.3.9-alpha` is not moved by this internal node.


## p2.10a75 upgrade, current-session cost, prompt segmentation, and retention progress

Date: 2026-05-19

Scope:

- Add same-public-version upgrade skip/reinstall semantics with remote tag commit comparison and `--force`.
- Expose current-session cost as a nested `cost.session` contract.
- Prevent session-scoped prompt segmentation from reusing a route-latest prompt report from another session.
- Make Compact/Trim `progress_*` fields represent information retention and move trigger/capacity semantics to `capacity_progress_*`.
- Public Release tag `v0.3.9-alpha` is not moved by this internal node.


## p2.10a76 Tokens aux and Details coverage contract

Date: 2026-05-19

Scope:

- Add explicit zero current-session `tokens.auxiliary_model_calls` object when no auxiliary model calls occurred.
- Add prompt Details coverage and delta metadata so WeClaw does not infer missing provider prompt-token overhead.
- Upgrade token taxonomy to version 8.
- Public Release tag `v0.3.9-alpha` is not moved by this internal node.


## p2.10a77 Prompt reconciliation contract

Date: 2026-05-19

Scope:

- Add `tokens.prompt_reconciliation` for Details/provider prompt-token reconciliation.
- Distinguish displayed category sum, local full observed prompt tokens, and provider prompt tokens.
- Add sanitized segment audit summary and unclassified segment accounting.
- Mark unexplained provider/local deltas as accounting-suspect rather than hiding them behind `partial`.
- Upgrade token taxonomy to version 9.
- Public Release tag `v0.3.9-alpha` is not moved by this internal node.


## p2.10a78 Prompt delta root-cause accounting

Date: 2026-05-19

Scope:

- Pass full DeepSeek chat payload into profile-tokenizer accounting.
- Add `observable_payload.components` for message content, messages JSON, tools schema, tool choice, response format, request options, and full payload JSON.
- Recompute `local_full_observed_prompt_tokens` from message content plus prompt-bearing observable API fields.
- Classify provider/Details delta as explained by observable payload components, partially explained, or remaining provider/template/tokenizer overhead.
- Upgrade token taxonomy to version 10.
- Public Release tag `v0.3.9-alpha` is not moved by this internal node.


## p2.10a79 Details origin breakdown

Date: 2026-05-19

Scope:

- Add display-ready `prompt_reconciliation.details_origin_breakdown`.
- Remove the need for WeClaw to show a `classified~x/y` subtotal.
- Expose user/history/tool/system/environment/tools schema/message protocol/provider residual origins as separate display components.
- Classify the observed provider/Details delta as tools schema plus message protocol overhead when residual is within tolerance.
- Upgrade token taxonomy to version 11.
- Public Release tag `v0.3.9-alpha` is not moved by this internal node.


## p2.10a80 Docs and latest release handoff

Date: 2026-05-19

Scope:

- Update cumulative public release notes for `v0.3.9-alpha`.
- Document p2.10a75–p2.10a79 WeClaw-facing contracts in public and developer documentation.
- Move `v0.3.9-alpha` Latest Release to the current master after validation.
- Keep forbidden plain tags `v0.3.9` and `v0.3.5` absent.

Final state:

- `master = origin/master = 80bb0ea`
- `p2.10a80-docs-release-latest = 80bb0ea`
- `v0.3.9-alpha = 80bb0ea`
- GitHub Release `CodeXchange v0.3.9-alpha` is non-draft, non-prerelease, and Latest.
- Release assets are `bootstrap.sh` and `install.sh`.
- Full tests passed before the Release update.

## p2.10a81 Handbook current-state sync

Date: 2026-05-19

Scope:

- Restore the tracked cumulative release-note source if it was accidentally deleted locally.
- Synchronize English and Chinese handbook current-state blocks from the stale `6ea67b2` / `p2.10a71-docs-prerelease-notes` state to the p2.10a80 public Release baseline `80bb0ea`.
- Clarify that the removed repository-tracked Release-note file is the active cumulative Release-note source for the current public Release, while legacy fragmented release-note documents remain retired.
- Advance developer internal runtime metadata to `p2.10a81-handbook-current-state-sync`.

Release boundary:

- Public tag `v0.3.9-alpha` remains at `80bb0ea`.
- No GitHub Release is created or updated.
- No Release assets are rebuilt.
- Forbidden plain tags `v0.3.9` and `v0.3.5` must remain absent.


## p2.10a82 Append-only upstream payload trace

Date: 2026-05-20

Scope:

- Add opt-in append-only upstream payload tracing through `COX_PAYLOAD_TRACE_DIR`.
- Record one local JSON event per `DeepSeekClient.chat_completions()` call before the upstream POST.
- Include sanitized raw payload, summary, request purpose metadata, duplicate-content hashes, role character totals, tools schema size, and context trimming report.
- Restrict trace output to `/tmp` and keep the feature disabled by default.

Boundary:

- No prompt assembly behavior changes.
- No payload reduction, semantic compaction, prompt caching, pricing, Release asset, or public tag changes.
- Public `v0.3.9-alpha` remains at `80bb0ea`.


## p2.10a83 DeepSeek cache accounting contract

Adds provider-authoritative DeepSeek prompt cache hit/miss accounting to the usage ledger, WeClaw status, and cost contract. Session, last-turn, and auxiliary cache sections expose request-level `prompt_cache_hit_tokens`, `prompt_cache_miss_tokens`, and cache hit ratio. Cost remains per-turn ledger based and uses hit/miss input prices rather than treating all prompt tokens as cache miss or cache hit. DeepSeek ChatCompletions payloads now set a stable hashed `user_id` by default and canonicalize tools schema ordering to protect DeepSeek context-cache reuse. Segment-level origin splits remain local estimates; provider cache hit/miss is request-level authoritative.

## p2.10a84 Token-first Compact/Trim context contract

Date: 2026-05-20

Scope:

- Make the active context-window display token-first.
- Managed Codex profile generation now derives `model_auto_compact_token_limit` from the single managed `auto_compact_ratio = 0.90`.
- Default DeepSeek V4 managed profile context remains `model_context_window = 1000000`, so the derived auto-compact threshold is `900000`.
- `context_window.display_limit_tokens` and `effective_safe_window_tokens` now report the full `model_context_window_tokens`.
- `auto_compact_threshold_tokens` exposes the separate trigger threshold.
- Char-level `runtime_payload_guard`, Compact, Trim, and context-trimming fields remain `unit=chars` fallback/debug payload guards and are not token denominators.

Boundary:

- No semantic payload compaction enablement.
- No token-based runtime trimming enablement.
- No public `v0.3.9-alpha` tag movement.
- No GitHub Release update or Release asset rebuild.

## p2.10a85 Compact prompt fingerprint and material classifier dry-run

Date: 2026-05-20

Scope:

- Added redacted SHA-256 compact prompt fingerprints for Codex-like persistent compaction.
- Added COMPACT material classifier dry-run metadata for compaction material, retained recent verbatim messages, and leading protected messages.
- Added retained recent policy metadata showing the requested keep-recent count, nominal boundary, effective boundary, and tool-result-boundary rewind.
- Exposed the new metadata through compaction reports and runtime payload guard last-report snapshots.
- Added focused regression tests for fingerprint stability, content redaction, dry-run-only classifier semantics, retained tool-call/tool-result boundary preservation, and runtime status exposure.

Boundary:

- No semantic payload compaction enablement.
- No token-based runtime trimming enablement.
- No public `v0.3.9-alpha` tag movement.
- No GitHub Release update or Release asset rebuild.

## p2.10a86 Compact runtime/status contract

Date: 2026-05-20

Scope:

- Added a stable redacted `compact_audit` contract for Compact metadata.
- Runtime WeClaw status now exposes `runtime_payload_guard.compaction.compact_audit` and mirrors it under `compaction.compact_audit`.
- CLI legacy fallback can expose the same audit metadata from `/v1/proxy/status.context.compaction.last_report` when the direct WeClaw runtime endpoint is unavailable.
- Debug budget reports expose Compact audit metadata for local validation.
- Added focused tests for runtime status serialization, WeClaw status, CLI fallback, and debug budget propagation.

Boundary:

- No semantic payload compaction enablement.
- No token-based runtime trimming enablement.
- No public `v0.3.9-alpha` tag movement.
- No GitHub Release update or Release asset rebuild.

## p2.10a87 Compact audit dry-run on skipped compaction

Date: 2026-05-20

Scope:

- Closed the runtime gap where `compact_audit` fields existed but remained unavailable after normal non-triggering requests.
- Attached redacted dry-run Compact audit metadata to skipped compaction reports when the policy is not triggered or there are too few messages.
- Preserved disabled-compaction semantics: disabled compaction still reports disabled/unavailable and does not fabricate audit metadata.
- Added focused regression coverage for non-triggered compaction reports, redaction, classifier dry-run metadata, retained-recent policy metadata, and existing runtime/WeClaw status propagation.

Boundary:

- No model call is made for skipped-compaction audit metadata.
- No payload mutation.
- No semantic payload compaction enablement.
- No token-based runtime trimming enablement.
- No public `v0.3.9-alpha` tag movement.
- No GitHub Release update or Release asset rebuild.

## p2.10a88 HTTP WeClaw Compact audit E2E regression

Date: 2026-05-20

Scope:

- Added a no-network ASGI end-to-end regression for Compact audit after skipped compaction.
- The test executes `POST /v1/responses`, then checks `GET /v1/proxy/weclaw/status?profile=cox&include_balance=false` on the same app instance.
- The test asserts both top-level `compaction.compact_audit` and nested `context_window.runtime.payload_guard.compaction.compact_audit`.
- The test confirms dry-run classifier semantics, retained-recent metadata, 64-character SHA-256 fingerprint presence, and no raw prompt/material exposure.

Boundary:

- No production behavior change beyond internal version metadata.
- No model/network calls in the new regression.
- No semantic payload compaction enablement.
- No token-based runtime trimming enablement.
- No public `v0.3.9-alpha` tag movement.
- No GitHub Release update or Release asset rebuild.

## p2.10a89 TRIM type enum, first-image protection, and token dry-run

Date: 2026-05-20

Scope:

- Returned to the original TRIM checklist after the Compact audit observability nodes.
- Added redacted `token_first_trim_dry_run` metadata to context trimming reports.
- Added context trim type enum metadata for text, image payload, tool call/result, JSON, diff, pytest, traceback, log, static system/developer/AGENTS/environment/protocol, and unknown-style categories.
- Added first-image protection so the first observed image payload is not context-trimmed or aggressively shrunk.
- Added current/latest static block protection metadata and guard behavior for system/developer/AGENTS/environment/protocol blocks.
- Exposed TRIM dry-run metadata through runtime payload guard report snapshots.
- Added regression coverage for first-image protection, static block protection, redaction, and runtime status propagation.

Boundary:

- Production context trimming remains char-level in this node.
- Token-based runtime trimming is dry-run only.
- No semantic payload compaction enablement.
- No public `v0.3.9-alpha` tag movement.
- No GitHub Release update or Release asset rebuild.

## p2.10a90 Type-aware TRIM enablement

Date: 2026-05-20

Scope:

- Enabled the first production batch of type-aware context TRIM using the p2.10a89 dry-run classifier and protection metadata.
- Added type-specific limits for tool outputs, logs, pytest output, tracebacks, diffs, JSON payloads, old text, tool-call arguments, and reasoning content.
- Preserved first-image and current/latest static block protections across normal TRIM, prefix compaction, and aggressive shrinking.
- Added `type_aware_trim` status/report metadata with redacted applied-by-type summaries and no raw content exposure.
- Added regression coverage for type-aware trimming, opt-out behavior, redaction, and status propagation.

Boundary:

- This node does not enable semantic payload compaction.
- This node does not implement image semantic envelopes.
- Public `v0.3.9-alpha` remains unmoved.

## p2.10a91 Image semantic envelope

Date: 2026-05-20

Scope:

- Added display-safe `image_semantic_envelope` metadata for context TRIM.
- Preserved the first observed image payload verbatim while allowing non-protected image messages to be replaced with semantic envelope text.
- Exposed envelope metadata through trim reports, runtime payload guard snapshots, and WeClaw status paths.
- Added regression coverage for first-image preservation, non-first image replacement, opt-out behavior, and raw image redaction.

Boundary:

- This node does not implement OCR, image captioning, or external vision analysis.
- This node does not update the public `v0.3.9-alpha` release.

## p2.10a92 Codex native Compact source alignment

Date: 2026-05-21

Scope:

- Replaced the failed installed-package-only Compact conclusion with GitHub source-backed evidence.
- Included the exact Codex `prompt.md` text in cox's local Compact user message.
- Recorded `prompt.md` sha256 `ab0c334d4faca17e3afbb9b16967c1b2fdcc7242a9a0880af57949fa236d6d07`.
- Recorded `summary_prefix.md` sha256 `e9b088e794a6bb9082ac053fcc760bd818d7e720ee4bcdc72c6e480de7b7cb0e`.
- Exposed `codex_native_source_evidence`, `compact_prompt_alignment`, and `codex_summary_prefix` through Compact metadata, compact audit, runtime payload guard, and WeClaw status paths.
- Preserved the boundary that Codex remote `responses/compact` is provider-gated and is not claimed for the third-party DeepSeek route.

Boundary:

- This node does not implement the remote `responses/compact` endpoint locally.
- This node does not claim DeepSeek route native remote compaction support.
- Public `v0.3.9-alpha` remains unmoved.

## p2.10a94 Plan closure contract

Date: 2026-05-21

Scope:

- Close low-risk plan-audit gaps before any public `v0.3.9-alpha` Release update.
- Add explicit retained-recent Compact booleans for latest incoming user, recent user/assistant turns, and active tool-chain preservation.
- Add semantic payload compaction token estimate fields and plan-level type aliases such as `pytest_success`, `pytest_failure`, `git_diff`, and `api_response_json`.
- Add explicit image-envelope `semantic_summary_unavailable` metadata so metadata-only image envelopes cannot be mistaken for OCR, captioning, or vision summaries.
- Superseded by p2.10a95: production Compact/TRIM now use token-first runtime thresholds; char-level controls are emergency safety fallback.

Boundary:

- No public `v0.3.9-alpha` tag movement.
- No GitHub Release update.
- No Release asset rebuild.

## p2.10a95 token-first runtime closure

Date: 2026-05-21

Scope:

- Close the remaining C1/D1 plan blockers by making production COMPACT and production TRIM token-first at runtime.
- COMPACT now estimates context tokens for the assembled request payload and triggers on `auto_compact_threshold_tokens` / `model_auto_compact_token_limit`.
- TRIM now uses the active profile auto-compact token limit as the production token target unless `COX_TRIM_MAX_CONTEXT_TOKENS` explicitly overrides it.
- Char-level limits remain only as emergency safety fallback after token-first runtime processing.
- Runtime reports expose `estimated_context_tokens`, `tokens_to_auto_compact`, `token_first_runtime_trim`, token removal fields, and char fallback scope.

Boundary:

- No public `v0.3.9-alpha` tag movement.
- No GitHub Release update.
- No Release asset rebuild.

## p2.10a96 release notes final sync

Date: 2026-05-21

Scope:

- Refresh the removed repository-tracked Release-note file after p2.10a94 and p2.10a95.
- Include token-first production Compact/TRIM runtime closure, semantic payload token estimates, image summary-unavailable metadata, retained-recent booleans, and release boundary notes.
- Update runtime internal version metadata for the final public `v0.3.9-alpha` candidate.

Boundary:

- No public `v0.3.9-alpha` tag movement.
- No GitHub Release update.
- No Release asset upload.


## p2.10a97 WeClaw contract stabilization

Date: 2026-05-21

Scope:

- Stabilize cox-owned WeClaw status contracts after `v0.3.9-alpha=282e059`.
- Add explicit auto-compact policy diagnostics when an active profile still exposes a legacy/custom threshold such as 750k/0.75 instead of the managed 0.90 ratio.
- Add a stable token-first Compact contract with trigger, target availability, before/after token estimates, retention ratio, source, reason, and observed timestamp.
- Guard token-first TRIM status against stale runtime reports from a different route/profile.
- Mark Details origin breakdown unavailable when local origin components are missing so provider residual is not displayed as a fabricated origin split.
- Expose top-level pricing refresh/stale metadata for WeClaw display.

Boundary:

- No public `v0.3.9-alpha` tag movement.
- No GitHub Release update.
- No Release asset rebuild.


## p2.10a98 WeClaw resume Details and Pricing lifecycle

Date: 2026-05-21

Scope:

- Persist profile tokenizer reports so `cox status thinking --weclaw-json --session-id <session>` can restore Details origin breakdown after resume or process restart.
- Mark restored Details origin data with `restored_from_persistence=true` and `source=sqlite_profile_tokenizer_report_store`.
- Make Pricing lifecycle explicit: bundled official snapshots are active fallback data and should be shown as refresh-recommended, not refresh-required. Only stale official cache is refresh-required.
- Harden the DeepSeek official pricing HTML parser against capability rows such as `输出长度 / 最大 384K`.
- Add short display fields for auto-compact policy diagnostics: `display_label` and `short_action`.

Boundary:

- No public `v0.3.9-alpha` tag movement.
- No GitHub Release update.
- No Release asset rebuild.


## p2.10a99 Plan full closure

Date: 2026-05-22

Scope:

- Enforce the strict Plan rule that managed CodeXchange profiles use `auto_compact_ratio=0.90` as the only auto-compact threshold source.
- Runtime status, CLI profile status, Compact, and Trim now derive `model_auto_compact_token_limit` from `model_context_window_tokens * 0.90`.
- Legacy absolute values such as `750000` are ignored as current runtime thresholds and are surfaced only as generated-profile drift requiring repair.
- `cox profile repair --managed-only --json` now repairs `model_auto_compact_token_limit` to the ratio-derived value.
- Current user Codex profiles were backed up and repaired so `deepseek` and `cox` use `900000` for a `1000000` token window.
- TRIM dry-run now uses the explicit active profile when deriving the token-first runtime target.
- Tests were updated so `750000` is only a legacy input/negative marker, never a live runtime threshold.

Strict rule: no Plan item is considered complete unless tests and runtime gates pass with exact values.


## p2.10a100 Token-first field contract

Date: 2026-05-22

Scope:

- Close Plan items B1, B2, C1, and D1 using strict binary acceptance.
- Add exact Plan field names for COMPACT:
  - `estimated_tokens_before_compact`
  - `estimated_tokens_after_compact`
  - `estimated_tokens_removed_by_compact`
- Add exact Plan field names for TRIM:
  - `estimated_tokens_before_trim`
  - `estimated_tokens_after_trim`
  - `estimated_tokens_removed_by_trim`
- Mark Compact/Trim token reports with `primary_control_unit=tokens`.
- Mark char fields with `char_control_scope=fallback_debug_safety_only`.
- Preserve the p2.10a99 rule that managed Compact/Trim thresholds derive from `model_context_window_tokens * 0.90`.

Boundary:

- Does not close C2/C4/D2/D3/D4/D5/E/F/G.
- Does not update public `v0.3.9-alpha`.


## p2.10a101 Token-first unavailable field contract

Date: 2026-05-22

Scope:

- Close the p2.10a100 strict runtime gate failure.
- Ensure `runtime_payload_guard.compaction.token_first` exposes Plan field names even when no live runtime compaction report has been observed:
  - `estimated_tokens_before_compact`
  - `estimated_tokens_after_compact`
  - `estimated_tokens_removed_by_compact`
- Unavailable token-first sections now return `None` for unavailable before/after estimates and `0` for removed tokens.
- This node does not close later Plan items C2/C4/D2/D3/D4/D5/E/F/G.


## p2.10a108 Semantic payload compaction tests

Date: 2026-05-22

Scope:

- Close Plan item E under strict binary acceptance.
- Source/runtime gates for semantic payload compaction were already present:
  - target limited to old flattened tool transcripts and low-risk repeated logs,
  - token gain fields,
  - type details,
  - risk levels,
  - observe/dry-run/canary/validation staging,
  - separation from main conversation COMPACT.
- Added explicit tests for:
  - semantic payload compaction dry-run,
  - token gain fields,
  - risk/type fields,
  - canary gating,
  - staged enablement markers.
- Does not close F or G.


## p2.10a110 Final tests and docs contract

Date: 2026-05-22

Scope:

- Close Plan item G under strict binary acceptance.
- Confirm tests cover the completed A/B/C/D/E/F rules.
- Keep `750000` only as historical, legacy, or negative-test input; it is not a live runtime threshold.
- Record the managed context contract:
  - `model_context_window_tokens = 1000000`
  - `auto_compact_ratio = 0.90`
  - `model_auto_compact_token_limit = 900000`
  - `auto_compact_threshold_tokens = 900000`
- Validate full tests under sanitized environment. The p2.10a110 read-only audit showed raw-environment failures from local environment leakage:
  - `COX_MODEL` affected model-default assertions.
  - image-provider environment affected provider mock tests.
  Sanitized full tests are the authoritative CI-style gate for this node.
- Public `v0.3.9-alpha` is not moved by this internal node.


## p2.10a111 Pricing daily refresh contract

Date: 2026-05-22

Scope:

- Add cox-owned daily pricing refresh contract.
- Status / WeClaw JSON now evaluates pricing freshness by local calendar day.
- When the bundled official snapshot or official cache is older than the current local day, cox attempts an official-docs refresh and writes the managed cache.
- If the official source is unavailable, the previous cache or bundled snapshot is preserved, but the status contract exposes `requires_refresh`, `reason`, and `action` instead of silently treating the old date as current.
- External pricing configs remain user-managed and are not auto-refreshed.
- Tests cover cross-day refresh, same-day no-refresh, and failure-preserves-old-prices behavior.

## p2.10a112 Pricing owned refresh contract

Date: 2026-05-22

Scope:

- Complete pricing ownership correction.
- `COX_PRICING_PATH` is cox-managed, not user-managed.
- Daily official pricing refresh after local midnight applies to configured pricing paths as well as the default managed cache.
- A configured pricing path becomes the refresh target when present; otherwise the managed cache path is used.
- Failed refresh preserves the previous pricing file or bundled snapshot and exposes `requires_refresh`, `reason`, and `action`.

Boundary:

- This node does not declare semantic payload compaction production-ready.
- The prior attempt to equate "default enabled" with production readiness is explicitly rejected.
- Semantic payload compaction remains a follow-up hardening line requiring staged correctness work, runtime observability, safety gates, and real-session validation.


## p2.10a115 Semantic payload runtime snapshot

Date: 2026-05-22

Scope:

- Close the first p2.10a114 runtime audit gap for semantic payload compaction observability.
- Real request handling already called semantic audit, policy dry-run, and payload compaction logic, but normal status visibility depended on debug trace events.
- Runtime now keeps an in-memory semantic payload compaction event snapshot for the latest request.
- `/v1/proxy/status` and `/v1/proxy/weclaw/status` can read semantic audit, policy dry-run, and payload compaction events from that runtime snapshot even when debug trace is disabled.
- Debug trace remains an optional long-session observability path; it is no longer the only runtime source for the latest semantic event triplet.
- This node does not mark semantic payload compaction production-ready and does not move public `v0.3.9-alpha`.

Boundary:

- Default semantic payload mode remains dry-run.
- Enabled mode still requires the canary guard and local invariant checks.
- This node does not update the GitHub Release or Release assets.

## p2.11a1 Semantic payload safety core

Date: 2026-05-22

Scope:

- Start the p2.11 line instead of continuing to stack p2.10a116+ after the p2.10 A-G plan had closed.
- Document the version-semantic health rule in both developer handbooks.
- Harden semantic payload safety core so enabled mutation is explicitly limited to old flattened tool transcripts classified as low-risk pytest-success output.
- Preserve system/developer messages before flattened transcript classification.
- Preserve recent flattened transcripts, medium/high-risk transcripts, diff/patch/traceback/json/search/shell logs, and unknown transcripts.
- Add safety_core_version, safety_core metadata, semantic type counts, risk counts, policy decisions, skip reasons, and source metadata to semantic payload reports.
- Keep canary-gated enabled mode and fallback-to-original behavior.

Release boundary:

- Public `v0.3.9-alpha` is not moved in this node.

## p2.11a2 Semantic payload enabled runtime status

Date: 2026-05-22

Scope:

- Separate dry-run readiness from enabled-mode runtime health for semantic payload compaction.
- Add `runtime_state`, `enabled_monitoring_healthy`, latest payload mode/effective mode/reason/error/canary status to rollout assessment.
- Preserve `safe_to_enable_payload_compaction` as a dry-run-only readiness signal.
- Avoid WeClaw degraded diagnostics when enabled mode is healthy and actively monitored.
- Keep explicit blockers for missing events, non-enabled runtime payload events, canary rejection, and fallback/error.

Release boundary:

- Public `v0.3.9-alpha` is not moved in this node.

## p2.11a3 Semantic payload real route

Date: 2026-05-22

Scope:

- Add a route-level `/v1/responses` regression for enabled semantic payload compaction.
- Verify thinking-mode flattened tool transcript payloads are compacted before the upstream DeepSeek request.
- Verify the upstream request contains the semantic compacted envelope and no original large pytest body.
- Verify `/v1/proxy/status` reads the runtime snapshot and reports enabled monitoring with savings and safety metadata.
- Keep public `v0.3.9-alpha` unchanged.

## p2.11a4 Semantic payload WeClaw contract

Date: 2026-05-22

Scope:

- Add `semantic_compaction.display` as the stable WeClaw-facing semantic payload display contract.
- Expose mode/status/runtime_state, applied/skipped counts, token/char savings, type counts/actions, risk counts, skip reasons, last event metadata, blockers, and warnings.
- Preserve redaction and keep raw payload details out of WeClaw display fields.
- Keep healthy enabled monitoring out of degraded diagnostics.
- Keep public `v0.3.9-alpha` unchanged.

## p2.11a5 Semantic payload production validation

Date: 2026-05-22

Scope:

- Add a real HTTP E2E validation for semantic payload compaction across `/v1/responses` and `/v1/proxy/weclaw/status`.
- Verify upstream payload mutation, removal of the original large low-risk pytest body, and preservation of display-safe summary evidence.
- Verify WeClaw can consume `semantic_compaction.display` from both the top-level status payload and `context_window.runtime.semantic_compaction`.
- Verify token/char savings, type/risk/action counts, last-event metadata, blockers, warnings, redaction, and healthy enabled monitoring.
- Update Release notes for the p2.11 semantic payload production validation line.

Release boundary:

- Public `v0.3.9-alpha` is not moved in this node.

## p2.12a2 Codex profile forward-compatible repair

Date: 2026-05-22

Scope:

- Regenerate managed Codex provider/profile blocks during `cox profile repair --managed-only --json`.
- Clear stale `glm-5.1` model drift in `cox` by rewriting the Codex-visible profile model to the cox effective upstream model.
- Refresh the managed Codex wrapper so it repairs and verifies managed profiles before launching Codex.
- Fail closed if a managed profile still has a model conflict after repair.
- Keep token-only Compact/Trim runtime migration for the next node.

## p2.12a6-token-accounting-source

- Retired char counts from the visible runtime Compact/Trim control plane.
- Runtime payload guard and WeClaw status now expose `unit=tokens`, `current_tokens`, token trigger/remaining/progress fields, and move char counters to `legacy_char_debug`.
- Character counters are diagnostic only and must not drive Compact/Trim triggering, capacity progress, or WeClaw display.

## p2.12a10 Docs and v0.3.9-alpha Release closeout

Date: 2026-05-23

Scope:

- Update the cumulative the removed repository-tracked Release-note file source after the p2.12 stabilization line.
- Ensure the Release Note covers every functional change since the previous published `v0.3.9-alpha` commit: p2.12a2 through p2.12a9.
- Preserve older cumulative v0.3.9-alpha content rather than replacing it with a short delta.
- Keep the WeClaw requirement `weclaw_dev >= v0.1.9-alpha`.
- Prepare the GitHub Release update and asset refresh for `bootstrap.sh` and `install.sh`.

Functional coverage added for the new public Release body:

- Codex profile forward-compatible repair.
- Token-first Compact/Trim runtime.
- Ratio-only auto-compact policy.
- Token Compact status semantics.
- Token accounting source fixes.
- Token-only status surface.
- Runtime payload report persistence.
- Semantic low-risk pytest classifier/candidate fix and real-route validation.

Release boundary:

- Public tag `v0.3.9-alpha` is moved only after this documentation and validation step passes.
- Forbidden plain tags `v0.3.9` and `v0.3.5` must remain absent.

## p2.12a11 Doc duplicate tag block cleanup

Date: 2026-05-23

Scope:

- Clean up the duplicate stale public-tag block in `docs/developer-handbook.zh-CN.md`.
- Remove the old `v0.3.9-alpha = ab680ee` line from the Chinese current-state block.
- Preserve the corrected `v0.3.9-alpha = d674a61` block.
- Update docs readiness tests to assert that the Chinese current-state block no longer contains `ab680ee`.
- This node does not move public `v0.3.9-alpha` and does not update GitHub Release assets.

## p2.12a12 Clean v0.3.9-alpha Release highlights

Date: 2026-05-23

Scope:

- Replace the overly fragmented `v0.3.9-alpha` Release body with one clean Highlights list.
- Describe the user-visible diff from `v0.3.8-alpha` to `v0.3.9-alpha`.
- Remove redundant body title, internal workflow headings, validation section, old cumulative block headings, internal p-node references, and repeated implementation-log fragments.
- Keep the WeClaw minimum version requirement.
- Keep Release assets as `bootstrap.sh` and `install.sh`.
- Update GitHub Release and move public `v0.3.9-alpha` after tests pass.

## p2.12a13 Remove tracked Release-note document

Date: 2026-05-23

Scope:

- Remove the repository-tracked Release-note file.
- Remove README and README.zh-CN links to that file.
- Keep the public GitHub Release body as the Release-note source.
- Keep long-lived documentation limited to developer handbooks and development logs.
- Move public `v0.3.9-alpha` after tests pass so the latest public source no longer contains the extra tracked Release-note file.

## p2.22a2-test-isolation-and-validation

- Fixed the p2.22a1 validation gap: the earlier node correctly implemented custom-provider capability downgrading and model catalog generation, but its test run inherited the developer shell's active provider/model environment.
- Added test-suite environment isolation for CodeXchange/DeepSeek/Codex provider variables at import time and per test so local configured shells cannot mutate default model, upstream provider, semantic compaction mode, trace directory, or pricing assertions.
- Fixed the stale-pid self-heal unit test double to expose the minimal `subprocess.Popen.poll()` surface required by `cox start` readiness handling.
- Validation target: rerun static checks, focused tests, and the full pytest suite from a configured local environment before accepting the repair node.

### p2.22a3-model-catalog-visibility-schema

- Fixed Codex 0.138 model catalog schema compatibility for generated custom-provider catalogs.
- Replaced invalid `visibility = visible` / `"visibility": "visible"` output with Codex-compatible `visibility = list` / `"visibility": "list"`.
- Added regression coverage so managed model catalog fixtures and generator source do not reintroduce the invalid visibility enum.

### p2.22a4-model-catalog-slug-schema

- Fixed Codex 0.138 model catalog schema compatibility for generated custom-provider catalogs requiring `slug`.
- Custom-provider catalog entries now include `slug` plus common aliases (`id`, `model`, `name`) and display fields.
- Repaired local `~/.codex/model-catalogs/codexchange-custom-providers.json` without calling the upstream model API.

### p2.22a5-model-catalog-reasoning-presets-schema

- Fixed Codex 0.138 model catalog schema compatibility for reasoning preset fields.
- Removed guessed string-array `supported_reasoning_levels` entries from generated and managed custom-provider model catalogs.
- Repaired local `~/.codex/model-catalogs/codexchange-custom-providers.json` without calling upstream model APIs.

### p2.22a6-model-catalog-reasoning-preset-objects

- Fixed Codex 0.138 model catalog schema compatibility for `supported_reasoning_levels`.
- Generated and managed custom-provider catalogs now emit ReasoningEffortPreset objects with `effort` and `description`.
- Repaired local `~/.codex/model-catalogs/codexchange-custom-providers.json` without calling upstream model APIs.

### p2.22a7-model-catalog-full-codex-schema

- Fixed Codex 0.138 model catalog schema compatibility by emitting the complete required model entry shape.
- Added `shell_type`, `minimal_client_version`, `supported_in_api`, `base_instructions`, and `model_messages` to generated custom-provider catalogs.
- Repaired local `~/.codex/model-catalogs/codexchange-custom-providers.json` without calling upstream model APIs.

### p2.22a8-model-catalog-final-required-fields

- Fixed Codex 0.138 model catalog schema compatibility by adding final required tail fields.
- Added `experimental_supported_tools`, `available_in_plans`, `supports_search_tool`, `additional_speed_tiers`, and `supports_reasoning_summaries` to generated custom-provider catalogs.
- Repaired local `~/.codex/model-catalogs/codexchange-custom-providers.json` without calling upstream model APIs.

### p2.22a9-profile-agnostic-codex-runtime-autostart

- Established a profile-agnostic Codex runtime autostart contract: `codex --profile <name>` now checks any managed local Responses proxy route before entering native Codex.
- The wrapper parses split profile files, resolves the configured `model_provider` base URL, starts the matching local proxy port when absent, and verifies `/v1/models` before launching Codex.
- The behavior is not USTC-specific; it applies to managed DeepSeek, thinking, and custom-provider profiles whose Codex provider base URL points at `127.0.0.1` or `localhost`.
- Fail-closed behavior now happens before Codex TUI entry when the local proxy port is occupied but unhealthy or when proxy startup/readiness fails.
- Do not move `v0.4.3-alpha` and do not rebuild Release assets.

### p2.22a10-codex-executable-wrapper-dispatcher

- Fixed the installed `~/.local/bin/codex` command form by making `scripts/codex-wrapper.bash` dual-use: sourceable shell-function wrapper and executable command dispatcher.
- The executable dispatcher runs profile-agnostic proxy autostart/readiness first, resolves the native Codex binary while skipping itself, then `exec`s the native binary with original arguments.
- This closes the regression where `codex --profile <name>` returned immediately after a function-style wrapper was copied into `~/.local/bin/codex`.
- Do not move `v0.4.3-alpha` and do not rebuild Release assets.

### p2.22a11-native-codex-resolver

- Hardened the executable Codex wrapper native-binary resolver.
- The dispatcher now scans PATH entries while skipping itself, common native binary aliases, npm global package bins, and then falls back to offline `npm exec --package @openai/codex` or `npx @openai/codex`.
- This fixes the case where `~/.local/bin/codex` shadows the native Codex binary and the previous resolver could not find a second `codex` executable.
- Do not move `v0.4.3-alpha` and do not rebuild Release assets.

### p2.22a12-codex-wrapper-bash-shebang

- Added an explicit Bash shebang to the installed Codex wrapper source.
- This fixes the executable-wrapper path where `~/.local/bin/codex` could be interpreted by `sh` and fail on Bash-only syntax such as process substitution.
- The wrapper remains dual-use: sourceable for shell function mode and directly executable for `codex --profile <name>` command mode.
- Do not move `v0.4.3-alpha` and do not rebuild Release assets.

### p2.22a13-install-wrapper-propagation

- Closed install/upgrade propagation for the verified Codex wrapper.
- `scripts/install.sh` now refreshes a managed `~/.local/bin/codex` from the canonical `scripts/codex-wrapper.bash` template after installer wrapper writes have completed.
- `codexchange_proxy/cli.py` records the canonical wrapper template and target paths for refresh-wrapper/install propagation audits.
- The verified wrapper contract remains dual-use: sourceable function mode and executable dispatcher mode with profile-agnostic local proxy readiness.
- Do not move `v0.4.3-alpha` and do not rebuild Release assets.

### p2.22a16-release-v043-alpha-update-to-p222-closeout

- Updated public release `v0.4.3-alpha` from `f8a6635` to the p2.22 closeout release line.
- Included the p2.22a8-p2.22a13 chain: Codex 0.138 model catalog compatibility, profile-agnostic runtime autostart, executable wrapper dispatcher, native Codex resolver hardening, Bash shebang, and installer propagation of the canonical wrapper.
- Local lifecycle closeout audit passed with no issues; VM validation for `24d542f` passed with `run_ok=1`, `issues=[]`, and isolated wrapper/profile dispatch checks passing.
- The tracked handbooks record the release commit as tag-managed because a commit cannot stably embed its own final hash before tagging.
- Release assets remain exactly `bootstrap.sh` and `install.sh`.
  - `bootstrap.sh` sha256 `257456d2724519bf94ad09f4dce038ac23e8fd5ab9da4b117f1ae637164590a4`
  - `install.sh` sha256 `3456aac1f06a45e78c60feb32c12765fb3f8bd38bdb36dd4dead10f3e91de596`
- `v0.4.3-alpha` remains the public release line; no new public version number was introduced.
