# Release Checklist

This checklist is for preparing the first public technical preview release.

Target release label:

    v0.1.0-alpha

## Required checks

- Confirm git status is clean
- Confirm full pytest passes
- Confirm dsproxy --version prints the intended version
- Confirm dsproxy doctor --thinking reports version_match=true
- Confirm dsproxy install-codex-profile works on a temporary config file
- Confirm dsproxy uninstall-codex-profile removes only its own profile and provider
- Confirm scripts/install.sh passes bash -n
- Confirm scripts/secret-scan.py reports no findings
- Confirm README.md and README.zh-CN.md do not mention private paths as installation defaults
- Replace the placeholder repository URL in scripts/install.sh before public one-line install
- Test fresh clone installation in a clean directory
- Test WSL installation
- Test missing DEEPSEEK_API_KEY diagnostics
- Confirm the proxy binds only to 127.0.0.1
- Confirm no secrets are committed

## Release notes

See:

    docs/release-notes-v0.1.0-alpha.en.md
    docs/release-notes-v0.1.0-alpha.zh-CN.md
