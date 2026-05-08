# CoDeepSeedeX v0.2.0-alpha

## Summary

Internal milestone: `v2.6a2-release-upgrade-defaults`.


This release finalizes the public upgrade experience before release publication.

## Changes

- `dsproxy upgrade` no longer defaults to the current installed version.
- `dsproxy upgrade` now defaults to the latest `master` from `origin`.
- README upgrade content is placed directly after the one-line install section.
- Default upgrade commands no longer hard-code a version.
- One-line installer remains the compatible upgrade path for older releases such as `v0.1.0-alpha`.

## Upgrade

Default latest upgrade:

```bash
dsproxy upgrade
```

Preview:

```bash
dsproxy upgrade --dry-run
```

Older releases without `dsproxy upgrade`:

```bash
curl -fsSL https://raw.githubusercontent.com/Awenforever/CoDeepSeedeX/master/scripts/install.sh | bash
```
