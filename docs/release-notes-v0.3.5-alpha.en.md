# CoDeepSeedeX v0.3.5-alpha

## Summary

CoDeepSeedeX v0.3.5-alpha completes the p2.8 provider-configuration line and publishes the tested alpha release at commit `53897ad`.

## Changes

- Integrated API key validation into manual provider configuration commands.
- Integrated API key validation into installer and bootstrap guided setup flows.
- Kept provider validation inside existing setup paths instead of adding a separate `dsproxy config test-provider --kind web-search|image --provider <name>` command.
- Expanded and hardened web search and image generation provider support.
- Added model provider catalog support.
- Updated README and operational guidance for provider setup, quota and application-page hints, and the `Other` custom server path.
- Added `docs/custom_api_handoff.md` as the agent-facing checklist for custom tool server configuration.

## Release state

- Public Release tag: `v0.3.5-alpha`
- Release title: `CoDeepSeedeX v0.3.5-alpha`
- Release commit: `53897ad`
- Release assets: `bootstrap.sh`, `install.sh`
- Default install and upgrade target: GitHub Latest Release

## Compatibility

The alpha-stage public tag remains `v0.3.5-alpha`. Do not use a plain `v0.3.5` tag for this release.
