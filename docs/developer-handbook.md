# CoDeepSeedeX Developer Handbook

This is the primary developer handbook. It is written in English because it is the main startup context for future AI-assisted development conversations. The Chinese mirror is `docs/developer-handbook.zh-CN.md`.

This handbook is not a historical archive. It keeps the current operating model, project map, release rules, high-priority lessons, and a concise summary of the current major development line. Detailed long-term records belong in `docs/development-log.md`.

## 1. Documentation architecture

Active user-facing documents:

- `README.md`: English user entry.
- `README.zh-CN.md`: Chinese user entry.
- `TROUBLESHOOTING.md`: user-facing troubleshooting.

Active maintainer documents:

- `docs/developer-handbook.md`: English primary handbook and AI startup context.
- `docs/developer-handbook.zh-CN.md`: Chinese mirror for the human maintainer.
- `docs/development-log.md`: detailed long-term development log, read only when historical trace-back is needed.

Retired document families must not be reintroduced as active documents: `OPERATIONS.md`, `docs/install.*.md`, `docs/usage.*.md`, `docs/upgrade.*.md`, `docs/security.*.md`, `docs/troubleshooting.*.md`, `docs/handoff-for-developers.*.md`, `docs/custom_api_handoff.md`, and per-release note files under `docs/`.

If documentation structure changes, tests must be updated to the new contract. Do not keep ghost documents only to satisfy stale tests.

## 2. Project identity and current state

- Local project path: `~/projects/deepseek-responses-proxy`
- GitHub repository: `Awenforever/CoDeepSeedeX`
- Main branch: `master`
- Current public release: `v0.3.7-alpha`
- Public release commit: `466706f`
- Release internal tag: `p2.9a18-release-v0.3.7-alpha`
- Current documentation baseline before p2.9a21: `p2.9a20-docs-consolidation = b160525`
- Older public tags must not move:
  - `v0.3.6-alpha = 7fd8fb6`
  - `v0.3.5-alpha = 53897ad`
- Erroneous plain tag `v0.3.5` must not exist.

After p2.9a21, `master`, `origin/master`, and `p2.9a21-handbook-bilingual-restoration` should point to the same new commit.

## 3. Key file map

- `deepseek_responses_proxy/app.py`: runtime core, Responses-compatible API, DeepSeek bridge, tool bridge, provider dispatch, version metadata, debug trace.
- `deepseek_responses_proxy/cli.py`: `dsproxy` CLI, config, provider setup, doctor commands, upgrade logic.
- `scripts/install.sh`: installer, installed checkout sync, venv setup, wrappers, Codex profiles, config initialization, local file backup.
- `bootstrap.sh`: one-line bootstrap entrypoint, dependency handling, install.sh acquisition and fallback.
- `tests/`: regression tests, document contract tests, provider and installer tests.
- `README.md` / `README.zh-CN.md`: user instructions.
- `TROUBLESHOOTING.md`: user troubleshooting.
- `docs/development-log.md`: detailed chronological record.

## 4. Version and tag rules

`dsproxy --version` must expose two version sources:

```text
public version: v0.3.x-alpha | <public_release_commit>
internal version: p2.9aN-topic | <internal_commit>
```

For user installations from a public Release tag, the internal version line reports the `p~` tag that was current at the moment that Release tag was created. For a developer checkout running from `master`, the public version line remains the latest published public Release until the next Release, while the internal version line must track the latest internal `p~` tag on `master`.

Public release tags use the `v0.3.x-alpha` form during alpha. Do not create plain `v0.3.x` public tags. Internal development tags use the `p` prefix, such as `p2.9a21-handbook-bilingual-restoration`, and must not create GitHub Releases.

Package versions in `pyproject.toml` use PEP440, for example `0.3.7a0`.

Files that usually need synchronized version edits during release:

- `deepseek_responses_proxy/app.py`
- `pyproject.toml`
- `tests/test_version_metadata.py`
- `tests/test_cli.py`

Each file has its own role. Do not force every version-related file to contain both public and internal tags.

## 5. Release state machine

A release must be treated as a state machine, not as a temporary one-off script.

Required sequence:

1. Read-only audit: branch, HEAD, origin/master, worktree, existing public tags, target public tag, GitHub Release state, version string distribution, test file existence.
2. Synchronize version metadata.
3. Run static checks and focused tests.
4. Run full tests.
5. Commit release preparation.
6. Push work branch.
7. Push internal tag.
8. Fast-forward master.
9. Push master.
10. Push public release tag.
11. Create GitHub Release and upload `bootstrap.sh` and `install.sh`.
12. Verify release assets, tags, old tags, and absence of erroneous plain tags.
13. Refresh local runtime with `--install-ref master`.
14. Verify `dsproxy --version` and `codex --profile deepseek-thinking app-server --help`.

Push over HTTPS by default. Do not rely on SSH port 22. Every network step must have a timeout.

GitHub Release notes must not repeat the release title. The body should start with `Highlights:`, `Changes:`, `Fixes:`, `Install:`, or `Validation:`.

## 6. Release lessons learned

These are high-priority lessons that must remain in the handbook, not only in the long development log.

### v0.3.7-alpha release mistakes

1. Do not hard-code runtime version paths. The runtime file is `deepseek_responses_proxy/app.py`, not root-level `app.py`.
2. Do not assume only one Python file contains version metadata. Runtime code and tests can both contain version strings.
3. Version files have separate roles: runtime public/internal version, package PEP440 version, version consistency tests, and CLI output tests. Runtime version metadata is dual-track: public Release runtime is fixed at the public `v~` tag and the internal `p~` tag that existed when that Release was cut; developer checkout runtime on `master` keeps the same current public `v~` until the next Release, but its internal `p~` version must advance with the latest `master` internal tag. Therefore, after post-Release documentation or maintenance commits, the developer machine may correctly show a newer internal `p~` than users running the latest public Release.
4. Updating `pyproject.toml` requires updating package-version assertions in tests.
5. Focused test lists must filter nonexistent test files before invoking pytest.
6. Release scripts must be idempotent and resume-aware.
7. Git push must use HTTPS and timeout controls to avoid SSH 22 stalls.
8. Public release tags should be pushed late to avoid half-published states.
9. `gh release view` must not rely on fields unsupported by the installed `gh` version, such as `isLatest`.
10. Release notes must not duplicate the GitHub Release title.
11. Documentation refactors must update the test contract. Do not keep ghost documents just because stale tests read them.
12. The developer handbook must not become a long archive. Keep it as AI startup context and send detailed chronology to `docs/development-log.md`.

## 7. Installer and local file ownership rules

The installer must back up local files before overwriting them. Important paths:

- `~/.config/deepseek-responses-proxy/env`
- `~/.local/bin/dsproxy`
- `~/.local/bin/codex`
- `~/.codex/config.toml`
- dirty and untracked files inside the installed checkout

Unknown user-owned `codex` or `dsproxy` files under `~/.local/bin` must not be silently overwritten. Known CoDeepSeedeX-managed wrappers may be backed up and refreshed.

If a user-modified installed checkout blocks upgrade, back up dirty changes as a patch and untracked files as an archive, then sync to the requested release ref.

## 8. Provider and custom API handoff

Provider-related behavior must remain consistent across runtime, CLI, installer, README, and tests.

Key paths:

- `deepseek_responses_proxy/app.py`
- `deepseek_responses_proxy/cli.py`
- `scripts/install.sh`
- `README.md`
- `README.zh-CN.md`
- `TROUBLESHOOTING.md`

Web search validation may perform a live low-result query and can consume quota.

Image validation is often non-generating and does not prove real image generation works. Real image generation checks require explicit consent:

```bash
dsproxy doctor providers --live --allow-spend
```

Do not add a separate `dsproxy config test-provider --kind web-search|image --provider <name>` command unless explicitly requested.

Zhipu and Z.AI image endpoints must remain separated. Do not mix domestic ZhipuAI, international Z.AI, GLM, and CogView assumptions.

## 9. VM GitHub proxy playbook

When a VMware NAT VM cannot reliably reach GitHub, do not guess. Audit the route, DNS, curl, git, proxy listener, and Windows host listener.

Known working pattern for the affected VM:

```text
VM -> 192.168.231.1:7896 -> Windows portproxy -> 127.0.0.1:7892 -> Jilianyun
```

GitHub-specific proxy settings are acceptable inside the VM. Do not treat jsDelivr failures as blocking when GitHub Release assets and `git ls-remote` are stable.

## 10. Documentation maintenance rules

The handbook is an AI startup pack:

- Keep stable rules, current state, project map, release rules, testing rules, and high-priority lessons.
- Keep only one current major-line summary in detail.
- Move older detailed chronology to `docs/development-log.md`.
- Keep English as the primary handbook.
- Maintain the Chinese mirror for the human maintainer.
- Do not reintroduce fragmented handoff, operations, install, usage, upgrade, security, troubleshooting, or release-note documents under `docs/`.
- If a test still reads a retired path, update the test contract instead of preserving a ghost document.

## 11. Current major-line summary: p2.9 / v0.3.7-alpha

p2.9 covered:

- Provider endpoint cleanup and validation semantics.
- Zhipu/Z.AI image provider separation.
- `dsproxy doctor providers` live probe matrix.
- Installer repair for affected machines and same-version rerun.
- Installed checkout sync to selected release refs.
- Local bin ownership guards.
- VM GitHub proxy documentation.
- `v0.3.7-alpha` release.
- Release lessons written into maintainer docs.
- p2.9a20 documentation consolidation.
- p2.9a21 restoration of English-primary developer handbook and Chinese mirror.

Detailed chronology belongs in `docs/development-log.md`.

## 12. New conversation startup checklist

At the start of a new development conversation, run a read-only audit:

```bash
git branch --show-current
git rev-parse --short HEAD
git rev-parse --short origin/master
git status --short
git rev-parse --short v0.3.7-alpha^{}
git rev-parse --short p2.9a20-docs-consolidation^{}
```

Then read `docs/developer-handbook.md`. Read `docs/development-log.md` only if historical trace-back is needed.

## 13. Install and fallback entrypoints

Latest Release bootstrap:

```bash
curl -fsSL https://github.com/Awenforever/CoDeepSeedeX/releases/latest/download/bootstrap.sh | bash
```

Resolved tag fallback:

```bash
tag="v0.3.7-alpha"
curl -fsSL https://github.com/Awenforever/CoDeepSeedeX/raw/refs/tags/${tag}/bootstrap.sh | bash
```

## Provider bridge terminology contract

The provider handoff section must explicitly preserve these bridge terms because tests and future maintainers use them as stable anchors:

- Web search tool bridge
- Image generation tool bridge

The Web search tool bridge may perform live provider checks and can consume quota.

The Image generation tool bridge can perform non-generating validation by default. Real image generation must be explicitly requested through:

```bash
dsproxy doctor providers --live --allow-spend
```

## p2.9a22 runtime version metadata policy

`gh release view --json` does not support the `isLatest` field. This is a command schema limitation, not an installed GitHub CLI version issue. Release checks must use compatible fields such as `tagName`, `name`, `url`, `publishedAt`, `isDraft`, `isPrerelease`, `targetCommitish`, and `assets`. If Latest status must be checked, use a separate compatible method instead of `gh release view --json isLatest`.

Runtime version metadata follows a dual-track policy. User installations from a public Release tag report the public `v~` tag and the internal `p~` tag that existed when that Release tag was created. Developer checkout runtime on `master` keeps the latest published public `v~` until the next public Release, but its internal `p~` version must advance with the latest internal tag on `master`. Therefore, after a public Release, documentation or maintenance commits can correctly make the developer machine show a newer internal `p~` than the latest public Release used by users.

## p2.9a23 script scope safety note

When generating shell commands that embed a Python heredoc, shell variables such as `ts`, `out`, or other Bash locals are not automatically available inside Python. Either pass them explicitly through environment variables, for example `UPDATE_TS="$ts" python3 - <<'PY...'`, or generate the value inside Python, for example `datetime.datetime.now().strftime(...)`. Never reference a shell-only variable directly inside the Python heredoc. This exact mistake caused `NameError: name 'ts' is not defined` in the development-entrypoint wrapper repair script before any intended wrapper rewrite happened.

For scripts that modify real HOME paths, keep the fail-before-write pattern: complete all variable setup inside the executing language, validate preconditions, create backups, and only then write the target file.
