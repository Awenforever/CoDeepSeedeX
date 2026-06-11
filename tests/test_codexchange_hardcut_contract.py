from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

FORBIDDEN_PRODUCT_MARKERS = {
    "CoDeepSeedeX",
    "CODEEPSEEDEX",
    "codeepseedex",
    "DeepSeek Responses Proxy",
    "deepseek-responses-proxy",
    "deepseek_responses_proxy",
    "dsproxy",
    "DSPROXY",
    "DEEPSEEK_PROXY_",
    "DEEPSEEK_API_KEY",
    "DEEPSEEK_BASE_URL",
    "DEEPSEEK_MODEL",
    "DEEPSEEK_THINKING",
    "DEEPSEEK_REASONING_EFFORT",
    "deepseek-thinking",
    "deepseek-proxy",
}

ALLOW_TEXT_FILES_SUFFIXES = {
    ".py", ".sh", ".bash", ".md", ".toml", ".json", ".ps1", ".yml", ".yaml", ".txt"
}

SKIP_PARTS = {
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".debug",
    ".tmp",
    ".generated",
}

SKIP_SUFFIXES = {
    ".pyc",
}


def _git_paths(args: list[str]) -> set[Path]:
    raw = subprocess.check_output(args, cwd=ROOT)
    result: set[Path] = set()
    for item in raw.split(b"\0"):
        if not item:
            continue
        rel = item.decode("utf-8")
        result.add(ROOT / rel)
    return result


def _source_candidate_paths() -> list[Path]:
    tracked = _git_paths(["git", "ls-files", "-z", "--", "."])
    new_unignored = _git_paths(["git", "ls-files", "--others", "--exclude-standard", "-z", "--", "."])
    return sorted(tracked | new_unignored)


def _is_scannable_source_text(path: Path) -> bool:
    rel = path.relative_to(ROOT)
    if path.name == "test_codexchange_hardcut_contract.py":
        return False
    if any(part in SKIP_PARTS for part in rel.parts):
        return False
    if any(part.endswith(".egg-info") for part in rel.parts):
        return False
    if path.suffix in SKIP_SUFFIXES:
        return False
    if path.suffix not in ALLOW_TEXT_FILES_SUFFIXES and path.name not in {"LICENSE"}:
        return False
    if not path.exists() or not path.is_file():
        return False
    try:
        data = path.read_bytes()
    except OSError:
        return False
    if b"\0" in data:
        return False
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def _tracked_text_files() -> list[Path]:
    return [path for path in _source_candidate_paths() if _is_scannable_source_text(path)]


def test_codexchange_hardcut_removes_legacy_product_markers() -> None:
    violations: list[str] = []
    for path in _tracked_text_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        for marker in sorted(FORBIDDEN_PRODUCT_MARKERS):
            if marker in text:
                violations.append(f"{path.relative_to(ROOT)} contains {marker}")
    assert not violations, "legacy product markers remain:\n" + "\n".join(violations[:80])


def test_codexchange_canonical_entrypoints_are_present() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'name = "codexchange"' in pyproject
    assert 'cox = "codexchange_proxy.cli:main"' in pyproject
    assert 'include = ["codexchange_proxy*"]' in pyproject
    assert (ROOT / "codexchange_proxy" / "app.py").exists()
    assert (ROOT / "scripts" / "cox-start").exists()
    assert (ROOT / "scripts" / "cox-status").exists()
    assert (ROOT / "scripts" / "cox-stop").exists()
