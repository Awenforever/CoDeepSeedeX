## p2.10a64 Pre-release upgrade and uninstall documentation closure

- Closed the post-P0 audit gap for uninstall documentation.
- Pre-release upgrade was already covered by `dsproxy upgrade --alpha`, explicit `--tag`, and `--dry-run`.
- Product-level uninstall remains installer-owned and is documented as `bash ~/.local/share/deepseek-responses-proxy/scripts/install.sh --uninstall`.
- Full removal is documented as `bash ~/.local/share/deepseek-responses-proxy/scripts/install.sh --uninstall --remove-files`.
- README.md and README.zh-CN.md now document uninstall scope, including managed Codex profiles, the CoDeepSeedeX codex wrapper, the dsproxy wrapper, optional install directory/env/manifest removal, and the boundary against deleting unrelated user files.
- Added a README regression test for uninstall documentation.
- Public `v0.3.9-alpha` remains at `ac63043`; this node does not update Release assets or Release notes.


## p2.10a63 P0 release-state documentation sync

- Synchronized repository docs after updating public pre-release `v0.3.9-alpha` to `p2.10a62-weclaw-runtime-payload-guard`.
- Current trusted state: `master = origin/master = ac63043`, `p2.10a62-weclaw-runtime-payload-guard = ac63043`, and `v0.3.9-alpha` peeled commit `ac63043`.
- `v0.3.8-alpha` remains `dfdc629`; forbidden plain tags `v0.3.9` and `v0.3.5` remain absent.
- GitHub Release `CoDeepSeedeX v0.3.9-alpha` is non-draft, pre-release, and includes `bootstrap.sh` and `install.sh` assets.
- P0 is closed from the CoDeepSeedeX implementation and pre-release delivery side; the mainline is now waiting for WeClaw-side validation.
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


# CoDeepSeedeX详尽开发日志

## p2.10a60-weclaw-status-context-pricing-contract

- Scope: token attribution boundary contract for WeClaw third-round status display.
- Starting point: `master = origin/master = d5bdd0b`, internal tag `p2.10a58-weclaw-round3-pricing-refresh = d5bdd0b`, public pre-release tag `v0.3.9-alpha = 677d923`.
- Audit conclusion: dsproxy usage ledger records provider aggregate usage fields and dsproxy purpose/call-index/model attribution, but it does not store prompt subcategory token splits.
- Audit conclusion: no audited tokenizer or local token estimator was present. `tiktoken` and `token_estimate` were not found in the p2.10a59 audit.
- Contract: `tokens.taxonomy.version` is now `3`.
- Contract: `tokens.attribution.provider_usage_totals` is exact provider-reported aggregate usage.
- Contract: `tokens.attribution.purpose_attribution` is exact dsproxy model-call purpose attribution.
- Contract: `tokens.attribution.prompt_subcategory_split` and `tokens.prompt_subcategory_split` are explicitly unavailable with reason/action/missing fields.
- Boundary: this node does not estimate user/tool/environment/history tokens and does not derive context-window used tokens from session totals.
- Release state: no public Release tag is moved, no GitHub Release is created, and no Release assets are rebuilt.

## p2.10a58-weclaw-round3-pricing-refresh

- Scope: guarded pricing refresh for WeClaw third-round status/cost display.
- Starting point: `master = origin/master = 861f260`, internal tag `p2.10a57-weclaw-round3-contract-foundation = 861f260`, public pre-release tag `v0.3.9-alpha = 677d923`.
- Audit conclusion: the current V4 pricing source is the human HTML page `https://api-docs.deepseek.com/quick_start/pricing`; `pricing-details-usd` and `pricing-details-cny` still describe legacy `deepseek-chat`/`deepseek-reasoner` pricing and must not be treated as V4 sources.
- Implementation: `dsproxy pricing refresh --json` fetches and validates official pricing HTML without writing cache by default.
- Implementation: `dsproxy pricing refresh --json --write-cache` writes validated pricing atomically to the user pricing cache or explicit `--cache-path`.
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
- CLI: add `dsproxy pricing show --json` and structured `dsproxy pricing refresh --json` not-implemented output without live network or cache writes.
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


## p2.10a65-profile-tokenizer-accounting

Added profile-aware DeepSeek tokenizer accounting for WeClaw-facing status. The node bundles the official DeepSeek V3 tokenizer JSON resource, adds the `tokenizers` runtime dependency, records local prompt subcategory estimates under `tokens.profile_tokenizer` and `tokens.prompt_subcategory_split`, and keeps provider `usage` as the authoritative billing source. Codex TUI tokenizer behavior remains separate because the current `codex --profile deepseek debug models` evidence did not expose DeepSeek catalog entries.


## p2.10a66-tokenizer-resource-installer-sync

Moved DeepSeek tokenizer resource delivery out of the repository and into installer/user-machine synchronization through `dsproxy tokenizer sync deepseek --json`. The runtime now uses managed tokenizer resources from the install/user resource directory or explicit env overrides, while provider usage remains billing-authoritative and local profile tokenizer counts remain estimates.


## p2.10a67-status-tokenizer-contract-consistency

Fixed the WeClaw status tokenizer contract so tokenizer resource availability is separated from observed prompt subcategory availability. `tokens.profile_tokenizer.available` can now be true before the route observes a prompt, while `tokens.prompt_subcategory_split.available=false` reports `profile_tokenizer_available_but_no_observed_prompt` with empty categories.


## p2.10a68-prompt-segment-ledger-audit

Added sanitized latest prompt segmentation for WeClaw Details and refined profile-tokenizer prompt categories. The `user` bucket is now the latest ordinary user segment, `user_history` stores earlier ordinary user-role segments, Codex tool transcripts are classified as `tool_output`, and AGENTS/memory/environment user-role blocks are classified as `environment`.


## p2.10a69-pricing-currency-turn-ledger

Added structured Pricing/Cost currency metadata for WeClaw, CNY display conversion based on dsproxy-owned FX metadata, per-turn pricing context columns in the usage ledger, cash cost semantics, reasoning-cost unavailable semantics, and a more robust DeepSeek official pricing HTML parser.


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
- GitHub Release `CoDeepSeedeX v0.3.9-alpha` is non-draft, non-prerelease, and Latest.
- Release assets are `bootstrap.sh` and `install.sh`.
- Full tests passed before the Release update.

## p2.10a81 Handbook current-state sync

Date: 2026-05-19

Scope:

- Restore the tracked cumulative release-note source if it was accidentally deleted locally.
- Synchronize English and Chinese handbook current-state blocks from the stale `6ea67b2` / `p2.10a71-docs-prerelease-notes` state to the p2.10a80 public Release baseline `80bb0ea`.
- Clarify that `docs/release-notes-v0.3.9-alpha.md` is the active cumulative Release-note source for the current public Release, while legacy fragmented release-note documents remain retired.
- Advance developer internal runtime metadata to `p2.10a81-handbook-current-state-sync`.

Release boundary:

- Public tag `v0.3.9-alpha` remains at `80bb0ea`.
- No GitHub Release is created or updated.
- No Release assets are rebuilt.
- Forbidden plain tags `v0.3.9` and `v0.3.5` must remain absent.


## p2.10a82 Append-only upstream payload trace

Date: 2026-05-20

Scope:

- Add opt-in append-only upstream payload tracing through `DEEPSEEK_PROXY_PAYLOAD_TRACE_DIR`.
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
- The test executes `POST /v1/responses`, then checks `GET /v1/proxy/weclaw/status?profile=deepseek-thinking&include_balance=false` on the same app instance.
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
- Included the exact Codex `prompt.md` text in dsproxy's local Compact user message.
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
- TRIM now uses the active profile auto-compact token limit as the production token target unless `DEEPSEEK_PROXY_TRIM_MAX_CONTEXT_TOKENS` explicitly overrides it.
- Char-level limits remain only as emergency safety fallback after token-first runtime processing.
- Runtime reports expose `estimated_context_tokens`, `tokens_to_auto_compact`, `token_first_runtime_trim`, token removal fields, and char fallback scope.

Boundary:

- No public `v0.3.9-alpha` tag movement.
- No GitHub Release update.
- No Release asset rebuild.

## p2.10a96 release notes final sync

Date: 2026-05-21

Scope:

- Refresh `docs/release-notes-v0.3.9-alpha.md` after p2.10a94 and p2.10a95.
- Include token-first production Compact/TRIM runtime closure, semantic payload token estimates, image summary-unavailable metadata, retained-recent booleans, and release boundary notes.
- Update runtime internal version metadata for the final public `v0.3.9-alpha` candidate.

Boundary:

- No public `v0.3.9-alpha` tag movement.
- No GitHub Release update.
- No Release asset upload.


## p2.10a97 WeClaw contract stabilization

Date: 2026-05-21

Scope:

- Stabilize dsproxy-owned WeClaw status contracts after `v0.3.9-alpha=282e059`.
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

- Persist profile tokenizer reports so `dsproxy status thinking --weclaw-json --session-id <session>` can restore Details origin breakdown after resume or process restart.
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

- Enforce the strict Plan rule that managed CoDeepSeedeX profiles use `auto_compact_ratio=0.90` as the only auto-compact threshold source.
- Runtime status, CLI profile status, Compact, and Trim now derive `model_auto_compact_token_limit` from `model_context_window_tokens * 0.90`.
- Legacy absolute values such as `750000` are ignored as current runtime thresholds and are surfaced only as generated-profile drift requiring repair.
- `dsproxy profile repair --managed-only --json` now repairs `model_auto_compact_token_limit` to the ratio-derived value.
- Current user Codex profiles were backed up and repaired so `deepseek` and `deepseek-thinking` use `900000` for a `1000000` token window.
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
  - `DEEPSEEK_PROXY_MODEL` affected model-default assertions.
  - image-provider environment affected provider mock tests.
  Sanitized full tests are the authoritative CI-style gate for this node.
- Public `v0.3.9-alpha` is not moved by this internal node.


## p2.10a111 Pricing daily refresh contract

Date: 2026-05-22

Scope:

- Add dsproxy-owned daily pricing refresh contract.
- Status / WeClaw JSON now evaluates pricing freshness by local calendar day.
- When the bundled official snapshot or official cache is older than the current local day, dsproxy attempts an official-docs refresh and writes the managed cache.
- If the official source is unavailable, the previous cache or bundled snapshot is preserved, but the status contract exposes `requires_refresh`, `reason`, and `action` instead of silently treating the old date as current.
- External pricing configs remain user-managed and are not auto-refreshed.
- Tests cover cross-day refresh, same-day no-refresh, and failure-preserves-old-prices behavior.

## p2.10a112 Pricing owned refresh contract

Date: 2026-05-22

Scope:

- Complete pricing ownership correction.
- `DEEPSEEK_PROXY_PRICING_PATH` is dsproxy-managed, not user-managed.
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

- Regenerate managed Codex provider/profile blocks during `dsproxy profile repair --managed-only --json`.
- Clear stale `glm-5.1` model drift in `deepseek-thinking` by rewriting the Codex-visible profile model to the dsproxy effective upstream model.
- Refresh the managed Codex wrapper so it repairs and verifies managed profiles before launching Codex.
- Fail closed if a managed profile still has a model conflict after repair.
- Keep token-only Compact/Trim runtime migration for the next node.

## p2.12a5-token-compact-status-semantics

- Retired char counts from the visible runtime Compact/Trim control plane.
- Runtime payload guard and WeClaw status now expose `unit=tokens`, `current_tokens`, token trigger/remaining/progress fields, and move char counters to `legacy_char_debug`.
- Character counters are diagnostic only and must not drive Compact/Trim triggering, capacity progress, or WeClaw display.
