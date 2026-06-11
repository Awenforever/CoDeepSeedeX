from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SECRET_PATTERNS = [
    ("openai_or_deepseek_key", re.compile(r"\\b(?:sk|sk-proj|ds)-[A-Za-z0-9_\\-]{20,}\\b")),
    (
        "generic_secret_assignment",
        re.compile(
            r"(?i)\\b(api[_-]?key|secret|token|password)\\b\\s*[:=]\\s*['\\\"][^'\\\"\\s]{16,}['\\\"]"
        ),
    ),
]

ALLOWED_SUBSTRINGS = [
    "COX_MODEL_API_KEY",
    "SERPAPI_API_KEY",
    "ZHIPUAI_API_KEY",
    "ZAI_API_KEY",
    "GLM_API_KEY",
    "api_key_env",
    "env_key",
    "sk-...",
    '"..."',
    "'...'",
]

SKIP_PARTS = {
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".generated",
}

TEXT_SUFFIXES = {
    ".py",
    ".sh",
    ".ps1",
    ".md",
    ".toml",
    ".json",
    ".yaml",
    ".yml",
    ".txt",
    ".bash",
}


def git_files() -> list[Path]:
    try:
        out = subprocess.check_output(["git", "ls-files"], cwd=ROOT, text=True)
    except Exception:
        return []
    return [ROOT / line for line in out.splitlines() if line.strip()]


def should_scan(path: Path) -> bool:
    rel_parts = set(path.relative_to(ROOT).parts)
    if rel_parts & SKIP_PARTS:
        return False
    return path.suffix in TEXT_SUFFIXES or path.name in {"README", "LICENSE"}


def allowed(line: str) -> bool:
    return any(token in line for token in ALLOWED_SUBSTRINGS)


def main() -> int:
    findings = []
    for path in git_files():
        if not path.exists() or not should_scan(path):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        rel = str(path.relative_to(ROOT))
        for lineno, line in enumerate(text.splitlines(), 1):
            if allowed(line):
                continue
            for name, pattern in SECRET_PATTERNS:
                if pattern.search(line):
                    findings.append(
                        {
                            "file": rel,
                            "line": lineno,
                            "pattern": name,
                            "preview": line.strip()[:160],
                        }
                    )

    print(json.dumps({"ok": not findings, "findings": findings}, ensure_ascii=False, indent=2))
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
