# Custom API handoff

This document is for an agent helping a user connect a custom tool server to CoDeepSeedeX.

The built-in provider menu currently supports selected web search and image generation providers. Built-in provider keys are handled by `dsproxy config set-web-search-api-key`, `dsproxy config set-image-api-key`, the installer wizard, and `dsproxy config wizard`; those paths validate keys before saving unless validation is explicitly skipped. The `Other custom server` option is intentionally a handoff path, not a generic auto-adapter. Use it when the user has an API server that is compatible with an existing provider shape or can be adapted by adding a small provider implementation.

## Scope

Supported customization targets:

- Web search tool bridge
- Image generation tool bridge

Out of scope for this handoff:

- Model API providers
- Codex model selection
- Public Release tag changes
- Installing or uninstalling into the user's real HOME without explicit approval

## First questions to ask the user

Ask for only the missing technical details:

1. Is this a web search server or an image generation server?
2. What is the base URL?
3. What authentication scheme is used?
4. What request method and path should be called?
5. What JSON request body or query parameters are required?
6. What response fields contain title, URL, snippet, image URL, base64 image data, or error messages?
7. Does the server require extra headers, region parameters, model names, or API version parameters?
8. Is the server OpenAI-compatible, SerpAPI-like, Tavily-like, Brave-like, Z.ai-like, or DashScope-like?

Do not ask for secrets in plain text logs. Tell the user to configure secrets through env files or `dsproxy config` commands. If the provider is promoted to first-class CLI or installer support, add a real validation path before saving. Do not add fake validation. Search validation may use a fixed low-result query and can consume a minimal quota. Image validation should avoid image generation where possible and should clearly document the probe type.

## Existing provider anchors

Use these anchors in the source tree:

- Runtime provider dispatch: `deepseek_responses_proxy/app.py`
- CLI configuration: `deepseek_responses_proxy/cli.py`
- Installer wizard: `scripts/install.sh`
- English docs: `README.md`
- Chinese docs: `README.zh-CN.md`
- Runtime tests: `tests/test_provider_config_status.py`
- CLI tests: `tests/test_cli.py`
- Installer UI tests: `tests/test_install_entrypoints_and_model_ui.py`

## Expected implementation shape

For a web search provider:

1. Add an API key resolver, such as `_custom_search_api_key()`.
2. Add a provider call function returning:
   - `ok`
   - `provider`
   - `query`
   - `results`
3. Normalize each result to:
   - `title`
   - `url`
   - `snippet`
   - `published_at` when available
4. Add dispatch in `_proxy_web_search`.
5. Add status reporting in `_tool_bridge_status`.
6. Add CLI and installer configuration only if the provider is intended to be first-class.

For an image generation provider:

1. Add an API key resolver if the existing image key resolver is not enough.
2. Add a provider call function returning:
   - `ok`
   - `provider`
   - `model`
   - `prompt`
   - `size`
   - `images`
3. Normalize each image to:
   - URL and/or local artifact fields
   - `mime_type`
   - minimal raw provider metadata
4. Add dispatch in `_proxy_image_generate`.
5. Add status reporting in `_tool_bridge_status`.
6. Add CLI and installer configuration only if the provider is intended to be first-class.

## Repository governance rules

Use these rules when maintaining this repository:

- Public Release tags use `v*`. During the current alpha line, use tags such as `v0.3.5-alpha`. Plain stable tags are reserved until the maintainer explicitly decides to publish a stable release.
- Internal pre-release tags use `p*`. Do not create new internal `v*` tags.
- Do not move, retag, or delete a published Release tag unless the maintainer explicitly names the exact Release and tag to rebuild.
- Prefer a new public Release tag over moving an existing public Release tag.
- Use `work/<topic>` branches for development. After a work branch is fast-forward merged into `master` and pushed, delete the merged remote `work/*` branch.
- Keep `master`, `origin/master`, public Release tags, and internal pre-release tags conceptually separate.
- Before deleting any branch or tag, audit local and remote refs and confirm the target is merged or has an equivalent replacement.
- Normal development should commit to a work branch, run focused tests, run full tests before release, then fast-forward merge into `master`.

## Safety and workflow rules for agents

Follow the project development rules:

- Start with read-only source audit when anchors are uncertain.
- Do not guess request or response schemas.
- Do not print API keys.
- Do not modify real HOME during tests unless the user explicitly asks.
- Put logs under `/tmp`.
- Keep terminal output short and write details to a txt log.
- Run at least:
  - `bash -n scripts/install.sh`
  - `bash -n bootstrap.sh`
  - `python -m py_compile deepseek_responses_proxy/app.py deepseek_responses_proxy/cli.py`
  - `git diff --check`
  - focused provider tests
- Run full tests before merging or publishing a Release.
- Do not create public Release tags unless the user explicitly asks.

## Minimal validation checklist

Before proposing a merge:

- The provider returns a stable normalized result shape.
- Missing API key paths return structured errors.
- Unsupported provider messages list accurate supported providers.
- `dsproxy config show` masks secrets.
- Installer and CLI provider names are consistent.
- Built-in provider config validates before saving, or documents why validation must be skipped.
- No new `dsproxy config test-provider` command is introduced unless the maintainer explicitly asks for it.
- README remains lightweight and does not become a provider comparison page.
