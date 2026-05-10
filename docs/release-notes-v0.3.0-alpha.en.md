# CoDeepSeedeX v0.3.0-alpha

Third public alpha release of CoDeepSeedeX.

**Strongly recommended upgrade** for all users, especially users running long Codex sessions through `deepseek-thinking`.

Highlights:

- Long-session context efficiency improvements for `deepseek-thinking`
- Thinking-mode tool-output trimming enabled by default
- Oversized `shell_command` and `interactive_shell` outputs compacted before re-entering model context
- Large structured tool outputs serialized compactly before trimming where possible
- Dedicated 12000-character cap for `image_payload` style tool outputs
- Runtime behavioral readiness check with `dsproxy debug behavioral --thinking`
- Real validation snapshot: `44822` characters trimmed from `shell_command` and `interactive_shell`
- Snapshot savings: about `16.6%` of latest observed context size, or `11.1%` of max observed context size
- README updated with current compaction categories and behavior
- Runtime version synced to `v0.3.0-alpha`
- Full test suite verified: 242 passed
- Upgrade dry-run verified on a clean checkout
- Post-release runtime verified: thinking proxy ready and behavioral check ready

Upgrade from older releases:

```bash
curl -fsSL https://raw.githubusercontent.com/Awenforever/CoDeepSeedeX/master/scripts/install.sh | bash
```

Upgrade from this release onward:

```bash
dsproxy upgrade
```

Preview upgrade:

```bash
dsproxy upgrade --dry-run
```

Verify:

```bash
dsproxy --version
curl -sS http://127.0.0.1:8000/healthz
curl -sS http://127.0.0.1:8001/healthz
dsproxy debug behavioral --thinking --limit 200 --timeout 5
```

Known limitations:

- This release improves tool-output trimming and long-session observability. It does not claim full semantic compaction parity with native Codex.
- The middle of very large tool outputs may be omitted. Save exact logs to files when exact reproduction is required.
- Large image-payload real-session validation remains separate.
