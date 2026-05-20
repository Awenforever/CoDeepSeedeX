# CoDeepSeedeX v0.3.9-alpha release notes

## Highlights since v0.3.8-alpha

Requires `weclaw_dev >= v0.1.9-alpha` if WeClaw integration is used. Newer WeClaw builds can consume the latest p2.10a75-p2.10a92 status, token, Compact, TRIM, and payload-safety contracts.

### WeClaw /status telemetry and Details

- Adds current-session-scoped token and cost contracts so WeClaw does not confuse route/global totals with the active session.
- Adds explicit `tokens.auxiliary_model_calls` semantics, including `aux 0` when no auxiliary calls occurred in the current session.
- Adds session-scoped Details so prompt segmentation does not leak across sessions.
- Adds prompt reconciliation fields that compare provider prompt tokens, local message-content tokens, observable payload components, and residual provider/tokenizer differences.
- Adds a display-ready `details_origin_breakdown` so Details can show token origins directly: user, history, tool output, system, developer, compaction summary, environment, runtime injected content, other prompt, tools schema, message/protocol overhead, and provider residual.
- Explains the previously observed Details/provider prompt-token gap: the major source is tools schema tokens, with smaller message/protocol/request-option overhead and a small provider/tokenizer residual. These fields should not be folded into `other_prompt`.
- Keeps provider usage (`provider_usage`) authoritative for billing, cache hit/miss accounting, and request-level totals; local tokenizer estimates remain display and reconciliation data.
- Adds provider-authoritative DeepSeek prompt cache hit/miss accounting for session, last-turn, and auxiliary usage, including `prompt_cache_hit_tokens`, `prompt_cache_miss_tokens`, and cache hit ratio.

### Context window and auto-compact contract

- Changes the active context-window display to a token-first contract: `context_window.display_limit_tokens` is sourced from `model_context_window_tokens`, not from the compact trigger threshold.
- Managed DeepSeek V4 Codex profiles keep `model_context_window_tokens = 1000000`.
- Managed profiles derive `model_auto_compact_token_limit` from the single managed `auto_compact_ratio = 0.90`; the default `auto_compact_threshold_tokens` is therefore `900000`.
- `model_auto_compact_token_limit` and `auto_compact_threshold_tokens` are trigger thresholds, not context-window denominators.
- Char-level Compact, TRIM, and `runtime_payload_guard` fields remain available as `unit=chars` fallback/debug payload guards, but they are not the token-level context denominator and must not be merged into the token progress bar.

### Compact audit and Codex-native local prompt alignment

- Adds redacted `compaction_prompt_fingerprint` metadata for Codex-like local Compact prompts and material boundaries.
- Adds `compact_material_classifier_dry_run` so static protocol blocks, leading system/developer material, retained recent messages, and summary candidates can be audited without mutating payloads.
- Adds `retained_recent_policy` metadata, including the effective boundary and assistant tool-call/tool-result rewind behavior.
- Exposes display-safe `compact_audit` metadata through runtime status, `runtime_payload_guard`, debug budget output, CLI fallback, and the `weclaw/status` HTTP path.
- Compact audit is available even when compaction is skipped because the policy is not triggered; skipped audit remains `dry_run`, `applied=false`, `raw_prompt_exposed=false`, and `raw_material_exposed=false`.
- Adds `codex_native_source_evidence`, `compact_prompt_alignment`, and `codex_summary_prefix` for source-backed local Compact prompt alignment.
- Aligns the local Compact user message with the Codex GitHub `prompt.md` template and records the Codex `summary_prefix.md` boundary.
- Records the Codex local prompt source under the `CODEX_NATIVE_COMPACT_PROMPT` contract area while keeping raw prompt text out of status metadata.
- Documents that Codex remote `responses/compact` exists but is provider-gated; `remote_compaction_claimed_for_dsproxy_provider=false` for the third-party DeepSeek route.
- The release does not implement a local remote `responses/compact` endpoint and does not claim native remote compaction support for the DeepSeek custom-provider path.
- Raw prompt and raw material remain redacted from all normal status metadata.

### TRIM and payload safety

- Adds redacted `token_first_trim_dry_run` metadata for context trimming analysis.
- Adds `type_enum_version` and type-aware item classification for text, image payloads, tool call/result content, JSON, diff, pytest output, traceback, logs, and static system/developer/AGENTS/environment/protocol blocks.
- Adds `first_image` / first-image protection: the first observed image payload is not context-trimmed or aggressively shrunk.
- Adds `protected_static_blocks` so the current/latest system, developer, AGENTS, environment, and protocol blocks remain protected while older duplicates can be handled separately.
- Enables the first production batch of `type_aware_trim` for low-risk text-bearing payloads such as tool results, logs, pytest output, tracebacks, diffs, JSON payloads, old text, tool-call arguments, and reasoning content.
- `DEEPSEEK_PROXY_TYPE_AWARE_TRIM=0` disables production type-aware trimming while keeping dry-run metadata available.
- Adds `image_semantic_envelope` for display-safe handling of non-protected older image messages after the first image has already been preserved.
- Image envelopes expose only metadata such as message index, role, image count, media-type hints, source shape, byte estimate, and sha256.
- `raw_image_content_exposed=false`: raw image payloads, base64 strings, data URLs, raw message content, static block text, and tool arguments are not exposed through metadata.
- This release does not add OCR, external vision analysis, or fabricated image summaries.

### Runtime observability

- Adds opt-in append-only upstream payload tracing through `DEEPSEEK_PROXY_PAYLOAD_TRACE_DIR` under `/tmp`.
- Payload tracing is disabled by default and records sanitized local JSON events for diagnosis only.
- The trace does not change prompt assembly, model selection, compaction, trimming, provider calls, pricing, Release metadata, or public tag state.

### DeepSeek pricing and cost display

- Keeps DeepSeek pricing CNY-first and aligned with the Chinese official pricing page.
- Exposes effective/original pricing and discount metadata for display without requiring WeClaw to scrape pricing independently.
- Keeps provider-reported usage authoritative for billing while allowing local estimates to explain display-only token origins.
- Session cost remains based on the per-turn ledger and must not be recomputed from the currently active model price.

### Upgrade and installation behavior

- `dsproxy upgrade` now skips reinstall only when both public version and release/tag commit match.
- If the same public version points to a different commit, upgrade performs an overwrite install.
- `--force` and `--force-reinstall` explicitly force reinstallation.
- Release assets remain `bootstrap.sh` and `install.sh`.

### Model/profile and runtime contracts

- Maintains DeepSeek/Codex profile effort mapping so DeepSeek `max` maps safely to Codex profile `xhigh` where needed.
- Preserves profile-owned model, effort, pricing, context, and status contracts on the dsproxy side so WeClaw does not need to infer or patch them.

### Notes

- `provider_prompt_tokens` remains the billing/reference value from the provider.
- Details is a token-origin view for display, not a claim that every provider token maps cleanly to one natural-language category.
- `provider_residual` must not be merged into `other_prompt`; hide it when it is within the reported tolerance.
- Token-first context-window fields and char-level payload guard fields are intentionally separate.
- Raw prompt, raw material, and raw image content remain redacted from normal status surfaces.
