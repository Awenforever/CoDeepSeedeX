from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]

CURRENT_FILES = [
    "README.md",
    "README.zh-CN.md",
    "OPERATIONS.md",
    "TROUBLESHOOTING.md",
    "docs/install.en.md",
    "docs/install.zh-CN.md",
    "docs/usage.en.md",
    "docs/usage.zh-CN.md",
    "docs/troubleshooting.en.md",
    "docs/troubleshooting.zh-CN.md",
    "scripts/codex-wrapper.bash",
    "scripts/install-runtime-scripts.sh",
    "deepseek_responses_proxy/cli.py",
]


def _scan(pattern: str) -> list[str]:
    rx = re.compile(pattern)
    hits: list[str] = []
    for rel in CURRENT_FILES:
        text = (ROOT / rel).read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), 1):
            if rx.search(line):
                hits.append(f"{rel}:{lineno}: {line.strip()}")
    return hits


def test_current_docs_do_not_use_legacy_dash_runtime_commands() -> None:
    hits = _scan(r"\bdsproxy-(?:start|stop|status)(?:-thinking)?\b")
    assert hits == []


def test_current_docs_do_not_use_legacy_thinking_flag_for_start_stop_status() -> None:
    hits = _scan(r"\bdsproxy\s+(?:start|stop|status)\s+--thinking\b")
    assert hits == []


def test_current_upgrade_guidance_uses_bootstrap_entrypoint() -> None:
    hits = _scan(r"(?:releases/latest/download/install\.sh|raw\.githubusercontent\.com/.*/scripts/install\.sh)\s*\|\s*bash")
    assert hits == []
