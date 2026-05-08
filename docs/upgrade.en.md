# Upgrade

CoDeepSeedeX supports two compatible upgrade paths.

## Path A: dsproxy upgrade

Use this when the installed version already includes the upgrade command:

```bash
dsproxy upgrade --tag v2.6a1-docs-and-upgrade-path
```

Dry run:

```bash
dsproxy upgrade --tag v2.6a1-docs-and-upgrade-path --dry-run
```

Useful options:

```bash
dsproxy upgrade --tag v2.6a1-docs-and-upgrade-path --skip-profile
dsproxy upgrade --tag v2.6a1-docs-and-upgrade-path --no-restart
dsproxy upgrade --tag v2.6a1-docs-and-upgrade-path --allow-dirty
```

The command:

1. verifies the installation is a git checkout
2. backs up the local env file and Codex config
3. fetches tags
4. checks out the target tag
5. reinstalls the package in editable mode
6. refreshes Codex profiles unless `--skip-profile` is used
7. restarts local proxies unless `--no-restart` is used
8. verifies `/healthz` unless `--no-verify` is used

## Path B: rerun the one-line installer

Use this when upgrading from older releases such as `v0.1.0-alpha`, or when `dsproxy upgrade` is not available:

```bash
curl -fsSL https://raw.githubusercontent.com/Awenforever/CoDeepSeedeX/master/scripts/install.sh | bash
```

This is intentionally compatible with Path A. The installer refreshes the local installation and Codex profiles while preserving local env and Codex configuration by default.

Do not use uninstall `--remove-files` unless you intentionally want to delete local data.

## Verify

```bash
dsproxy --version
dsproxy doctor --thinking
curl -sS http://127.0.0.1:8000/healthz
curl -sS http://127.0.0.1:8001/healthz
```
