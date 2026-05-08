# v2.6a1-docs-and-upgrade-path

## Summary

This release adds two compatible upgrade paths and synchronizes documentation for the v2.6a Codex-default MCP policy.

## Upgrade paths

- `dsproxy upgrade` for newer git checkout installations
- one-line installer rerun for older releases such as `v0.1.0-alpha`

## Changes

- Added `dsproxy upgrade`
- Added English and Chinese upgrade docs
- Updated README upgrade sections
- Documented v2.6a+ MCP behavior:
  - default policy is `codex`
  - default backend is `stdio`
  - proxy-side MCP allowlists are not required by default
  - write-capable MCP tools are not rejected by default
- Clarified that only stdio MCP transport is currently supported

## Compatibility

Older releases that do not include `dsproxy upgrade` should rerun the one-line installer from the target release.
