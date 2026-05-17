# CoDeepSeedeX详尽开发日志

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
- Decision: keep current dsproxy runtime compaction and trimming as character-based payload guards.
- Decision: do not directly switch runtime compaction to token-based triggering.
- Decision: add token shadow accounting before semantic payload compaction implementation.
- Required boundary: Codex profile context and Codex status are token-level surfaces, dsproxy runtime payload guard is char-level, provider usage remains authoritative for token/cost accounting, and local token estimates must be labelled as estimates.
- Required future work: report token-vs-char drift, warn when token risk and char risk diverge, and only then consider dual-threshold triggering.
- WeClaw implication: WeClaw display should separate token context window from char proxy payload guard and should not merge them into one unitless progress bar.
- Release state: no public Release tag is moved, no GitHub Release is created, and no Release assets are rebuilt.

## p2.10a53-tui-compact-path-evidence-sync

- Scope: docs-only evidence sync for the Codex TUI compact path after p2.10a52.
- Starting point: `master = origin/master = 2fe8c12`, internal tag `p2.10a52-semantic-payload-compaction-tui-plan = 2fe8c12`, public pre-release tag `v0.3.9-alpha = 677d923`.
- Evidence: isolated TUI run under `codex --profile deepseek` started successfully with the dsproxy-backed profile.
- Evidence: ordinary short request `reply ok exactly` returned successfully.
- Evidence: manual `/compact` displayed `Context compacted`.
- Evidence: TUI transcript markers did not contain `responses/compact` or `/responses/compact`.
- Evidence: Codex-side logs showed `codex.op="compact"`, `session_task.compact`, `model_client.stream_responses_api`, `wire_api=responses`, `http.method="POST"`, and `api.path="responses"`.
- Evidence: the dsproxy listener on port 8000 was the local uvicorn process for `deepseek_responses_proxy.app:app`; proxy access logs showed ordinary `POST /v1/responses HTTP/1.1` requests.
- Interpretation: manual `/compact` in Codex CLI `0.130.0` with `codex --profile deepseek` currently uses ordinary `/v1/responses`, not a dedicated `/responses/compact` endpoint.
- Remaining risk: auto-compact near `model_auto_compact_token_limit` remains unverified, as does long-session repeated compact behavior and usage/cost attribution for compact turns.
- Release state: no public Release tag is moved, no GitHub Release is created, and no Release assets are rebuilt.

## p2.10a52-semantic-payload-compaction-tui-plan

- Scope: record the inserted semantic payload compaction hardening plan and Codex TUI third-party profile compatibility plan after the `v0.3.9-alpha` pre-release and p2.10a51 post-release documentation sync.
- Starting point: `master = origin/master = 9337fdc`, internal tag `p2.10a51-post-v039-alpha-release-doc-sync = 9337fdc`, public pre-release tag `v0.3.9-alpha = 677d923`.
- Trigger: the maintainer identified that Codex profile context is token-based while dsproxy runtime compaction/trimming is char-based, and that native Codex `/compact` or auto-compact may still run under `codex --profile deepseek`.
- Planning result: add `P0.5 semantic payload compaction hardening` after WeClaw second-round requirements and before AnyCodeX-level architecture work, unless a high-risk TUI compaction failure forces escalation.
- Planning result: add `P0.6 Codex TUI third-party profile command compatibility` to verify `/compact`, auto-compact, `/fork`, `/resume`, `/model`, `/status`, `/diff`, `/review`, approval, sandbox, and related TUI commands under the third-party `deepseek` profile.
- Risk recorded: dsproxy character-level persistent compaction cannot be assumed to automatically replace Codex native token-level compact unless the compact request actually reaches dsproxy through a compatible path.
- Required future evidence: isolated TUI command matrix output, exact compact request path, whether `/responses/compact` is used, whether inline compact works, whether session store and provider filtering preserve `/fork` and `/resume`, and whether WeClaw display fields need token-window plus char-budget separation.
- This node updates planning documentation and runtime internal version metadata only. It does not move `v0.3.9-alpha`, create a GitHub Release, or rebuild Release assets.

## p2.10a51-post-v0.3.9-alpha-release-doc-sync

- Synchronized post-release documentation after the `v0.3.9-alpha` GitHub pre-release was created successfully.
- Verified release state before this sync: `v0.3.9-alpha = 677d923`, GitHub Release title `CoDeepSeedeX v0.3.9-alpha`, non-draft and pre-release, assets `bootstrap.sh` and `install.sh` uploaded.
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
- Added runtime WeClaw telemetry aggregation from the dsproxy usage ledger for `tokens.last_turn`, `tokens.session_total`, and `tokens.auxiliary_model_calls`.
- Added runtime WeClaw pricing and cost fields based on the existing dsproxy pricing cache and usage ledger `estimated_cost_usd` values.
- Added provider balance integration into runtime WeClaw status.
- Updated CLI `dsproxy status [thinking] --weclaw-json` to prefer the runtime `/v1/proxy/weclaw/status` endpoint when reachable.
- Added tests for HTTP full telemetry contract and CLI runtime WeClaw status preference.
- Token counts are exact provider-reported ledger totals. Cost is estimated from dsproxy pricing cache. Prompt subcategory splits remain explicitly not provider-reported without a future audited tokenizer layer.
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
- Delivered accepted CLI surfaces: `dsproxy profile status <profile> --json`, `dsproxy profile set-effort <profile> <effort> --json`, and `dsproxy status [thinking] --weclaw-json`.
- Delivered accepted HTTP surfaces: `GET /v1/proxy/weclaw/profile-status?profile=deepseek-thinking` and `GET /v1/proxy/weclaw/status?profile=deepseek-thinking`.
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
- `dsproxy config set-effort` now accepts `--json` for parser/help consistency with the always-JSON output contract.
- `dsproxy config set-effort` and `dsproxy profile set-effort` now accept `--no-refresh`, which routes through the existing post-config apply disabled mode and returns `post_config_apply.status = "skipped"`.
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
- Confirmed the naming boundary: user-facing docs, code, scripts, and tests keep the current CoDeepSeedeX name; AnyCodeX remains future-name planning text only inside developer docs.
- Identified the main DeepSeek-specific runtime seams: `DeepSeekClient`, `DEEPSEEK_*` runtime environment variables, `reasoning_content`, thinking-mode history repair, Responses-to-ChatCompletions conversion, stream event normalization, usage/cost accounting, model catalog assumptions, and WeClaw profile/status contracts.
- Defined the next implementation order as provider-capability metadata first, then upstream adapter interfaces, then reasoning/thinking strategy separation, then stream and tool-call normalization.
- No public Release tag was moved, no GitHub Release was rebuilt, and no Release assets were changed.

## p2.10a39-name-boundary-cleanup

- Cleaned remaining legacy lowercase alternate-name branch-plan wording from internal documentation so future real branches use neutral names such as `work/p2.10-generalized-provider-architecture-audit`.
- Kept AnyCodeX as a future plan name and possible future brand in developer-only planning text, while keeping code, commands, tags, branches, installers, wrappers, public paths, and user-facing documentation under the current CoDeepSeedeX name.
- Updated developer runtime internal version metadata to `p2.10a39-name-boundary-cleanup`.
- Fixed the p2.10a39 validation bug: the validation script incorrectly treated allowed internal AnyCodeX future-name planning text as forbidden, then introduced a self-conflicting lowercase legacy spelling in the development log.
- No public Release tag was moved, no GitHub Release was rebuilt, and no Release assets were changed.
## p2.10a38-version-metadata-name-boundary

- Updated runtime internal version metadata from the stale p2.10a35 tag to `p2.10a38-version-metadata-name-boundary`, while keeping public version metadata at `v0.3.8-alpha`.
- Updated version metadata tests so `dsproxy --version` must report the declared current internal tag.
- Clarified the naming boundary: CoDeepSeedeX remains the current project and public product name. AnyCodeX is a future plan name and possible future brand, not a current code, command, tag, branch, installer, wrapper, public-path, or user-facing documentation name.
- Reframed future provider work as AnyCodeX-level generalized provider architecture in internal developer documentation only.
- No public Release tag was moved, no GitHub Release was rebuilt, and no Release assets were changed.

## p2.10a37-sanitized-test-env-rule

- Added a handbook rule for sanitized test environments after p2.10a36 showed that full-suite failures can be caused by local exported model/provider/API-key variables rather than by the patch under test.
- The recurring contamination pattern includes `DEEPSEEK_PROXY_MODEL`, `DEEPSEEK_PROXY_FORCE_MODEL`, `DEEPSEEK_PROXY_IMAGE_PROVIDER`, `DEEPSEEK_PROXY_IMAGE_DOWNLOAD`, provider API keys, and web-search/image-provider variables.
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
- This prevents the title from being restored to CoDeepSeedeX after the user has already left Codex.

## p2.10a33-title-runtime-keeper

- Fixed both wrapper TTY gates so background title refresh can write `/dev/tty` even when stdout is redirected to `/dev/null`.
- Replaced the three-shot delayed title sequence with a bounded runtime keeper. The default is 60 seconds with a 1 second interval.
- Kept the wrapper foreground Codex execution model from p2.10a32 and did not change profile/model synchronization logic.

## p2.10a32-wrapper-foreground-codex

- Changed generated Codex wrappers to keep the wrapper process alive while the real Codex binary starts.
- The wrapper now prepares the matching dsproxy route, schedules the finite delayed OSC 0/2 title refresh sequence, and runs the real Codex binary as the final foreground command.
- This preserves the real Codex return status naturally while giving the delayed title refresh process a reliable execution window.

## p2.10a31-post-start-title-refresh

- Changed generated Codex wrappers to avoid setting the tab title before Codex startup.
- Kept a finite delayed OSC 0/2 refresh sequence after the matching dsproxy route is prepared, using 8s, 4s and 8s delays.
- Documented the observed failure mode where Codex overwrites a pre-start title with the working-directory title, and where undefined test helper names can print shell job `Exit 127` messages.

## p2.10a30-profile-model-sync-title-delay

- Added `dsproxy profile repair --managed-only --json` to repair managed Codex profile `model` fields according to each profile's effective upstream model.
- Kept `codex_model`, `effective_model`, and `model_conflict` as diagnostics, while making normal managed state repairable to `model_conflict=false`.
- Changed generated Codex wrappers to schedule short delayed OSC 0/2 tab-title refreshes, including a 5-second refresh, after starting the matching dsproxy route and before executing the real Codex binary.
- Preserved the non-duplicated 🐦‍🔥 emoji candidate rule.

本文件保存长期、可回溯的开发流水账。它不是新对话默认上下文。只有需要追溯具体版本、错误、测试或Release细节时才查阅。

## p2.10a29-weclaw-runtime-contract-unification

- Scope: make dsproxy the owner of Codex profile effort semantics and expose machine-readable profile/status skeletons for WeClaw.
- Root cause: `config set-effort` wrote the same canonical DeepSeek effort into `DEEPSEEK_REASONING_EFFORT` and Codex `model_reasoning_effort`, allowing `max` to enter Codex config.
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
- Saved generated validation images under `/tmp/codeepseedex-image-validation-*`.
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
- Added installer guidance explaining that the Codex wrapper enables `codex --profile deepseek` and `codex --profile deepseek-thinking` while automatically starting or refreshing the local dsproxy backend.
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

- Fixed the p2.10a18 finalization blocker where `app.py` declared the new internal version but `dsproxy --version` still reported the previous internal tag.
- Root cause: CLI version metadata was reading `proxy_app.PROXY_INTERNAL_VERSION`; the package-level `app` name can resolve to the FastAPI object rather than the `deepseek_responses_proxy.app` module.
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
- Kept the visible version line beside CoDeepSeedeX.
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
- Release validation path is `dsproxy upgrade --alpha` on a fresh VM before promoting the same GitHub Release to Latest.
- Release notes body must start from `Highlights:` and must not duplicate the GitHub Release title.
## p2.10a8-upgrade-alpha-terminal-title

- Added `dsproxy upgrade --alpha`, which resolves the newest non-draft GitHub pre-release while preserving the default `dsproxy upgrade` behavior against GitHub Latest Release.
- Added Codex wrapper terminal tab title randomization for `deepseek` and `deepseek-thinking` profiles. The format is `[emoji]CoDeepSeedeX` using the maintainer-supplied emoji candidate list.
- Documented the pre-release VM validation principle: publish a pre-release, test with `dsproxy upgrade --alpha`, then promote the same GitHub Release to Latest after validation passes.
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

- Scoped image provider diagnostics so a generic `DEEPSEEK_PROXY_IMAGE_API_KEY` no longer marks every image provider as configured.
- Kept compatibility for the currently selected `DEEPSEEK_PROXY_IMAGE_PROVIDER` while preserving provider-specific key variables for unselected providers.
- Made `set-image-api-key` and the guided wizard write provider-specific image API key variables in addition to the legacy generic variable.
- Updated README image provider examples from the old `glm` shortcut to explicit `zhipu` and `zai` examples.

## p2.9a26-provider-live-web-search-doc-sync

- Confirmed the real SerpAPI web search live probe on the developer machine.
- Command class: `dsproxy doctor providers --kind web-search --provider serpapi --live --allow-spend`.
- Result: `doctor_status=ok`, `provider_ok=True`, HTTP status 200, `validation_method=fixed_query_search`, `validation_strength=live_query_probe`, `functional_probe=True`, and `functional_validation=performed`.
- The probe did not print API key values.
- Other web search providers remain untested because their API keys are not configured.
- This validates the CoDeepSeedeX provider bridge path for SerpAPI. It does not by itself prove the full Codex TUI end-to-end tool selection path, which should be validated separately before release readiness.

## p2.9a27-zhipu-live-image-doc-sync

- Confirmed the real Zhipu image generation live probe on the developer machine.
- Command class: `dsproxy doctor providers --kind image --provider zhipu --live --allow-spend`.
- Result: `doctor_status=ok`, `provider_ok=True`, HTTP status 200, `validation_method=live_image_generation`, `validation_strength=live_generation_probe`, `functional_probe=True`, and `functional_validation=performed`.
- The probe returned image evidence: `has_image=True` and `evidence=data_url_or_base64`.
- The probe did not print API key values.
- This validates the CoDeepSeedeX provider bridge path for Zhipu image generation. It does not by itself prove the full Codex TUI end-to-end tool selection path, which should be validated separately before release readiness.

## p2.9a29-qwen-region-endpoint-probe

- Fixed Qwen/DashScope provider diagnostics so `dsproxy doctor providers --kind image --provider qwen_image --live --allow-spend` respects `DEEPSEEK_PROXY_IMAGE_BASE_URL` and `DASHSCOPE_IMAGE_ENDPOINT`.
- Fixed the Qwen non-generation image API validation path to use the same regional endpoint override.
- Root cause: runtime image generation already respected `DEEPSEEK_PROXY_IMAGE_BASE_URL`, but the CLI provider diagnostic path had a separate hardcoded Beijing endpoint.
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

- Added a CoDeepSeedeX-only post-config apply hook for successful config writes.
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

- Made `dsproxy config set-model` the primary model API setup entrypoint for provider, upstream model, and optional API key configuration.
- Kept `dsproxy config set-api-key` as a compatibility alias and added a compatibility/deprecation note in JSON output.
- Preserved the old model-only flow: `dsproxy config set-model deepseek-v4-flash`.
- Updated the guided wizard model provider catalog so supported model API providers are selectable from the wizard instead of only DeepSeek being handled as supported.
- Updated installer guidance, README, README.zh-CN, developer handbooks, and tests to prefer `set-model` for model API setup.

## p2.10a5-post-config-ux-consistency

- Synchronized the model API command summary shown by `dsproxy config wizard --non-interactive` with the full explicit provider surface.
- Replaced the remaining README and README.zh-CN Qwen Coding Plan custom-provider examples from the old `set-api-key --provider custom --model ...` form to the new `set-model <model> --provider custom --base-url ...` form.
- Added tests to prevent README custom model API examples from regressing to the old `set-api-key --provider custom` command shape.

### p2.10a25-version-install-plan-polish

- Fixed source-archive installs so wrapper-sourced version metadata can preserve the installed release commit even when the install directory is not a git checkout.
- Avoided noisy git clone fatal output when an existing install directory is non-git and non-empty by routing directly to source archive fallback.
- Quieted pip install phases with pip progress/version checks disabled and output captured in the install log.
- Clarified installer next steps for current-shell PATH refresh. p2.10a26 then pins native Codex Plan mode with `plan_mode_reasoning_effort`.

### p2.10a26-wrapper-start-plan-mode-hardening

- Made the CoDeepSeedeX Codex wrapper fail closed: it now starts the matching stable/thinking proxy route, verifies `dsproxy status`, and refuses to enter Codex if the backend remains unavailable.
- Added `plan_mode_reasoning_effort = "high"` to generated Codex profiles so native Codex Plan mode uses the DeepSeek-compatible high effort.
- Kept proxy-side compatibility normalization for legacy or Codex-originated `low` and `medium` inputs, which still map to DeepSeek `high`.
- Added explicit uninstall rollback coverage to ensure a previous Codex command backup is restored after the CoDeepSeedeX wrapper is removed.
- Rebuilt `v0.3.8-alpha` pre-release assets after merge.
