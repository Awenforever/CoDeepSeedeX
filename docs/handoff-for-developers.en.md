# Developer Handoff

## Current scope

deepseek-responses-proxy is a local Responses-compatible proxy for Codex.

It is not intended to be a generic model gateway. The priority is improving the codex --profile deepseek-thinking experience.

## Version line

- v2.3a1 output_text content normalization
- v2.3a2 default-open Codex tool forwarding
- v2.3a3 context trimming
- v2.3a4 persistent local compaction
- v2.3a5 runtime observability
- v2.3a6 agent loop liveness guard
- v2.3a7 tool-call protocol hardening
- v2.3a8 Codex tool protocol instruction and liveness judge
- v2.3a9 internal usage attribution
- v2.3a10 adaptive compaction budget policy
- v2.4a1 dsproxy CLI and config foundation
- v2.4a1a1 CLI start version and port guard
- v2.4a2 install scripts and Codex profile bootstrap
- v2.4a3 docs and release guide

## Invariants

- Bind to 127.0.0.1 by default
- Preserve Responses envelope compatibility
- Preserve function_call and tool_call pairing
- Never treat an old service as a ready new service
- Usage ledger should record internal upstream calls
- Codex profile installation should preserve user config where possible

## Pre-release checklist

- Confirm scripts/install.sh points to the public GitHub repository URL
- Check README links
- Test fresh clone installation
- Test WSL
- Test missing API key diagnostics
- Test Codex profile install and uninstall
- Run a secret scan

## v0.3.0-alpha long-session reliability handoff

- Runtime release line: `v0.3.0-alpha`.
- Internal milestone: `v2.7a32-real-session-validation-hardening`.
- `dsproxy debug behavioral --thinking` is the compact runtime readiness check for long Codex thinking sessions.
- `docs/real-long-session-validation.md` records the real-session validation boundary and acceptance criteria.
- `scripts/real-long-session-behavioral-smoke.sh --dry-run` validates the guarded smoke runner without invoking Codex.
- `scripts/real-long-session-behavioral-smoke.sh --allow-bypass` runs the controlled real smoke. It intentionally uses `codex exec --dangerously-bypass-approvals-and-sandbox` because Codex `workspace-write` sandbox cannot reliably reach the host WSL listener at `127.0.0.1:8001`.
- Do not interpret a sandbox-local `blocked` behavioral result as a proxy failure until localhost reachability from that execution environment is confirmed.

<!-- CODEEPSEEDEX_CURRENT_HANDOFF_BEGIN -->
## Current release handoff: v0.3.5-alpha

Current public release state:

- Public release tag: `v0.3.5-alpha`
- Release title: `CoDeepSeedeX v0.3.5-alpha`
- Release commit: `53897ad`
- Release assets: `bootstrap.sh`, `install.sh`
- Default install and upgrade target: GitHub Latest Release, not `master`
- `master` and `origin/master` are both at `53897ad`

Current internal development state:

- Current completed line: `p2.8`
- Completed internal stages:
  - `p2.8a1-api-validation`
  - `p2.8a2-doc-api-validation-sync`
  - `p2.8a3-api-validation-quality-hardening`
  - `p2.8a4-model-api-provider-catalog`
  - `p2.8a5-doc-release-readiness-sync`
- Current documentation sync: `p2.8a6-post-release-doc-handoff-sync`

Release and tag policy:

- Public Release tags use the `v0.3.x-alpha` shape during the alpha stage.
- Do not create a plain `v0.3.5` tag for this alpha release.
- Internal development tags use the `p*` shape.
- Internal `p*` tags must not create GitHub Releases.
- Do not move, delete, or recreate public Release tags unless the maintainer explicitly names the exact Release and tag operation.

v0.3.5-alpha summary:

- API key validation is integrated into manual configuration commands and the installer or bootstrap guided setup.
- No extra `dsproxy config test-provider --kind web-search|image --provider <name>` command was added.
- Web search and image provider support was expanded and hardened.
- Model provider catalog support was added.
- README and operational documentation now describe provider setup, free quota guidance, and the `Other` custom server handoff path.
- `docs/custom_api_handoff.md` is the handoff document for custom tool server configuration.

Next development guidance:

- Start any new line by auditing the current repository state, release state, tags, and dirty files.
- Use a `work/<topic>` branch.
- Commit completed changes.
- Push a work branch and its matching internal tag together only when remote publication is intended.
- Keep public Release tag work separate from normal internal development.
<!-- CODEEPSEEDEX_CURRENT_HANDOFF_END -->

<!-- CODEEPSEEDEX_HANDOFF_P2_9A4_SYNC_START -->

## p2.9a4 developer handoff sync

This section supersedes older p2.8-era handoff state when describing the current local developer checkout.

Current repository state:

- Project path: `~/projects/deepseek-responses-proxy`
- Main branch: `master`
- Remote main branch: `origin/master`
- Current `master` and `origin/master`: `b3700a3`
- Current internal development tag: `p2.9a3-version-metadata-dev-handbook`
- Current internal development tag target: `b3700a3`
- Current public Release tag: `v0.3.5-alpha`
- Current public Release tag target: `53897ad`
- Plain public tag `v0.3.5` must not exist and must not be created.
- `dsproxy --version` must print both public and internal version lines.
- Current public version line: `public version: v0.3.5-alpha | 53897ad`
- Current internal version line: `internal version: p2.9a3-version-metadata-dev-handbook | b3700a3`

### Local developer runtime rule

The developer machine must run `dsproxy` from the current checkout on `master`, not from an older installed GitHub Latest Release runtime.

The expected developer entrypoint is:

```bash
~/.local/bin/dsproxy
```

It should enter:

```bash
~/projects/deepseek-responses-proxy
```

and execute:

```bash
.venv/bin/python -m deepseek_responses_proxy.cli
```

After switching, pulling, or fast-forwarding `master`, restart both proxy services if they are running:

```bash
dsproxy stop thinking
dsproxy stop
dsproxy start
dsproxy start thinking
```

Validation commands:

```bash
dsproxy --version
curl -sS http://127.0.0.1:8000/healthz
curl -sS http://127.0.0.1:8001/healthz
```

The `/healthz` version must match the current public version. If `dsproxy --version` reports the current p2.9a3 metadata but `/healthz` still reports an old version such as `v0.3.2`, the running uvicorn proxy is stale and must be restarted.

### Debug trace recording note

When recording Codex-visible behavior, summarize the debug directory inherited by the running proxy process. A new empty debug directory can produce a misleading `debug_file_count=0` if the existing proxy process is still writing to an older `DEEPSEEK_PROXY_DEBUG_DIR`.

Always confirm:

- the uvicorn proxy process environment
- `DEEPSEEK_PROXY_DEBUG_TRACE`
- `DEEPSEEK_PROXY_DEBUG_DIR`
- `trace-*.jsonl` files
- `latest.json`

### Release and tag boundary

Internal `p*` tags may be created for development milestones, but they must not create GitHub Releases. Public Release tags continue to use the `v0.3.x-alpha` form and may only be created, deleted, rebuilt, or moved when the user explicitly requests a public Release operation.

<!-- CODEEPSEEDEX_HANDOFF_P2_9A4_SYNC_END -->

<!-- CODEEPSEEDEX_RELEASE_NOTES_NO_DUP_TITLE_RULE_START -->

### Release notes title-line rule

The GitHub Release page already has its own Release title, so the Release notes body must not repeat a title line such as:

```text
CoDeepSeedeX v0.3.5-alpha
```

Release notes should start directly with content such as Highlights, Changes, Fixes, Install, or Validation. Before publishing a Release, verify that the notes body does not contain a duplicated product-name plus version heading, otherwise the GitHub Release page will show two titles.

<!-- CODEEPSEEDEX_RELEASE_NOTES_NO_DUP_TITLE_RULE_END -->
