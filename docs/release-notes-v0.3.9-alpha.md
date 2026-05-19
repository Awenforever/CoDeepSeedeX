# CoDeepSeedeX v0.3.9-alpha release notes

## Highlights since v0.3.8-alpha

Requires `weclaw_dev >= v0.1.9-alpha` if WeClaw integration is used. Newer WeClaw builds can additionally consume the latest p2.10a75–p2.10a79 status contracts.

### WeClaw /status telemetry

- Adds current-session-scoped token and cost contracts so WeClaw does not confuse route/global totals with the active session.
- Adds explicit `tokens.auxiliary_model_calls` semantics, including `aux 0` when no auxiliary calls occurred in the current session.
- Adds session-scoped Details so prompt segmentation does not leak across sessions.
- Adds prompt reconciliation fields that compare provider prompt tokens, local message-content tokens, observable payload components, and residual provider/tokenizer differences.
- Adds a display-ready `details_origin_breakdown` so Details can show token origins directly: user, history, tool output, system, developer, compaction summary, environment, runtime injected content, other prompt, tool schema, message/protocol overhead, and provider residual.
- Explains the previously observed Details/provider prompt-token gap: the major source is tool/function schema tokens, with smaller message/protocol/request-option overhead and a small provider/tokenizer residual. These fields should not be folded into `other_prompt`.
- Compact and Trim status now expose retention-oriented progress separately from capacity/trigger progress.

### DeepSeek pricing and cost display

- Keeps DeepSeek pricing CNY-first and aligned with the Chinese official pricing page.
- Exposes effective/original pricing and discount metadata for display without requiring WeClaw to scrape pricing independently.
- Keeps provider-reported usage authoritative for billing while allowing local estimates to explain display-only token origins.

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
