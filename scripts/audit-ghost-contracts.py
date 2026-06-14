#!/usr/bin/env python3
"""Read-only ghost contract audit for CodeXchange.

The audit scans tracked text files for stale release contracts, retired user
surfaces, overbroad tests, site-specific defaults, and compatibility markers.
It does not mutate the repository. Findings are intentionally conservative:
they are classified into must_fix, review, and allowed instead of being treated
as a deletion list.

Typical use:

    python scripts/audit-ghost-contracts.py --repo . --out /tmp/ghost.txt
"""

from __future__ import annotations

import argparse
import ast
import csv
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


CURRENT_PUBLIC_TAG = "v0.4.8-alpha"
CURRENT_PUBLIC_COMMIT_SHORT = "01d6cee"
CURRENT_INTERNAL_TAG = "p2.19a23-profile-drift-failclosed-guard"
CURRENT_RUNTIME_RELEASE_INTERNAL_TAG = "p2.19a10-guided-installer-contextual-hints"

TSV_FIELDS = [
    "classification",
    "severity",
    "bucket",
    "category",
    "raw_category",
    "file",
    "line",
    "allow_note",
    "label",
    "text",
]


@dataclass(frozen=True)
class PatternSpec:
    category: str
    label: str
    regex: str


PATTERNS: list[PatternSpec] = [
    PatternSpec(
        "stale_release_state",
        "Old Release/Latest state contradicting the current v0.4.8-alpha Latest ordinary Release",
        r"Current public Release kind:\s*pre-release|当前公开Release类型：pre-release|"
        r"GitHub Latest ordinary Release:\s*`v0\.4\.0-alpha`|GitHub Latest普通Release：`v0\.4\.0-alpha`|"
        r"GitHub Release flags:\s*`isDraft=false`,\s*`isPrerelease=true`|"
        r"GitHub Release标志：`isDraft=false`，`isPrerelease=true`|"
        r"currently\s+v0\.4\.3-alpha\s+pre-release|pre-release channel,\s*currently\s+v0\.4\.3-alpha|"
        r"当前.*v0\.4\.3-alpha.*pre-release通道",
    ),
    PatternSpec(
        "stale_version_commit",
        "Old placeholder or commit marker from previous Release states",
        r"\bab680ee\b|\bd674a61\b|resolved by release tag|发布后由`v0\.4\.3-alpha` tag解析",
    ),
    PatternSpec(
        "retired_doc_surface",
        "Retired documentation family or tracked release-note source",
        r"OPERATIONS\.md|docs/install\.|docs/usage\.|docs/upgrade\.|docs/security\.|"
        r"docs/troubleshooting\.|docs/handoff-for-developers|docs/custom_api_handoff|"
        r"release-notes-v|per-release note|tracked Release note",
    ),
    PatternSpec(
        "stale_test_assertion",
        "Potential test assertion of an old contract",
        r"assert .*(Current public Release kind:\s*pre-release|当前公开Release类型：pre-release|"
        r"v0\.4\.0-alpha|resolved by release tag|ab680ee|d674a61|750000|USTC)",
    ),
    PatternSpec(
        "overbroad_test_scope",
        "Potential test scanning maintainer docs/history as production surface",
        r"ROOT / \"docs\"|developer-handbook\.md|developer-handbook\.zh-CN\.md|development-log\.md|git ls-files",
    ),
    PatternSpec(
        "site_specific_default",
        "Site-specific custom provider default or example leakage",
        r"\bUSTC\b|api\.llm\.ustc\.edu\.cn|deepseek-v4-flash-ascend",
    ),
    PatternSpec(
        "old_ui_surface",
        "Old numeric prompt or non-guided wizard surface candidate",
        r"Enter a number|enter number|Choose option|Select option|read -p|PS3=|select\s+[A-Za-z_].*\bin\b",
    ),
    PatternSpec(
        "legacy_profile_contract",
        "Codex legacy/split profile marker; review scope before deleting",
        r"\[profiles\.(deepseek|cox)\]|legacy_profile_tables|legacy_profile_table|split_profile_files|profile\s*=\s*\"deepseek",
    ),
    PatternSpec(
        "recursive_wrapper_risk",
        "Codex wrapper real-binary recursion or temp-wrapper risk marker",
        r"REAL_CODEX|/tmp/codexchange-|CodeXchange codex wrapper|codex wrapper",
    ),
    PatternSpec(
        "old_effort_or_threshold",
        "Old effort or explicit legacy threshold semantics candidate",
        r"\b750000\b|\b0\.75\b|COX_AUTO_COMPACT_THRESHOLD_TOKENS|COX_MODEL_AUTO_COMPACT_TOKEN_LIMIT|COX_AUTO_COMPACT_THRESHOLD_TOKENS|COX_MODEL_AUTO_COMPACT_TOKEN_LIMIT|COX_AUTO_COMPACT_RATIO|COX_AUTO_COMPACT_RATIO",
    ),
    PatternSpec(
        "deprecated_provider_surface",
        "Provider or command surface that may be deprecated or hidden",
        r"\bBrave\b|brave_search|set-api-key|config status|\bglm\b",
    ),
    PatternSpec(
        "future_name_user_surface",
        "Future AnyCodeX name should not leak into the current user-facing product surface",
        r"AnyCodeX",
    ),
    PatternSpec(
        "forbidden_plain_release_tag",
        "Forbidden plain public release tag reference",
        r"v0\.4\.0(?!-alpha)|v0\.3\.9(?!-alpha)|v0\.3\.5(?!-alpha)",
    ),
    PatternSpec(
        "diagnostic_typo",
        "Known typo in environment or diagnostic text",
        r"DEPPSEEK",
    ),
]


def run_git(repo: Path, args: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    cp = subprocess.run(
        ["git", *args],
        cwd=str(repo),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=120,
    )
    if check and cp.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed rc={cp.returncode}: {cp.stdout}")
    return cp


def tracked_files(repo: Path) -> list[str]:
    cp = run_git(repo, ["ls-files"], check=True)
    return [line for line in cp.stdout.splitlines() if line.strip()]


def text_or_none(path: Path) -> str | None:
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if b"\x00" in data[:4096]:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("utf-8", errors="replace")


def bucket_for(rel: str) -> str:
    if rel == "scripts/audit-ghost-contracts.py":
        return "audit_tool"
    if rel.startswith("tests/"):
        return "tests"
    if rel == "docs/development-log.md":
        return "history_log"
    if rel.startswith("docs/"):
        return "maintainer_docs"
    if rel in {"README.md", "README.zh-CN.md", "TROUBLESHOOTING.md"}:
        return "user_docs"
    if rel.startswith("codexchange_proxy/"):
        return "runtime_source"
    if rel.startswith("scripts/") or rel == "bootstrap.sh":
        return "installer_scripts"
    if rel.startswith("config/") or rel.startswith("experiments/"):
        return "config_assets"
    return "other"


def is_negative_or_compat_test(line: str) -> bool:
    lower = line.lower()
    stripped = lower.strip()
    return (
        stripped.startswith("assert not ")
        or "not in" in lower
        or "forbidden =" in lower
        or "offenders == []" in lower
        or "not re.search" in lower
        or "deprecated" in lower
        or "legacy" in lower
        or "compat" in lower
        or "allowed" in lower
    )

def classify(bucket: str, raw_category: str, rel: str, line: str) -> tuple[str, str, str]:
    """Return classification, severity, allow_note.

    The audit distinguishes stale live contracts from intentional negative
    guards, compatibility tests, and audit fixtures. It must not force
    implementation or documentation to regress just because a test documents or
    forbids an old state.
    """
    lower = line.lower()

    if bucket == "audit_tool":
        return "allowed", "low", "audit tool pattern definitions intentionally contain stale-sensitive markers"

    if bucket == "history_log":
        return "allowed", "low", "history log may contain old states; only current-state headings need review"

    if bucket == "maintainer_docs":
        if raw_category in {"stale_release_state", "site_specific_default", "retired_doc_surface"}:
            return "review", "medium", "maintainer docs can record contracts, but current-state sections must be current"
        return "allowed", "low", "maintainer docs may document compatibility and history"

    if bucket == "tests":
        # Audit-tool tests deliberately seed temporary repos with stale markers
        # to verify detection. The source fixture itself is not a live product
        # contract.
        if rel == "tests/test_ghost_contract_audit_script.py":
            return "allowed", "low", "audit fixture test intentionally contains stale-sensitive sample strings"

        # Documentation-readiness tests are maintainer-doc tests by design. They
        # can read handbooks and development-log, but should not require old
        # release states as positive live contracts.
        if raw_category == "overbroad_test_scope":
            if rel in {"tests/test_docs_release_readiness.py", "tests/test_doc_command_safety.py"}:
                return "allowed", "low", "maintainer-doc test intentionally reads docs or history"
            return "review", "medium", "review scan scope; production-source scans should not include maintainer docs/history"

        if raw_category in {"stale_test_assertion", "stale_release_state"}:
            if is_negative_or_compat_test(line):
                return "allowed", "low", "negative guard against stale release state"
            return "must_fix", "high", "positive stale release assertion still requires old behavior"

        if raw_category == "site_specific_default":
            if is_negative_or_compat_test(line):
                return "allowed", "low", "negative guard against site-specific defaults"
            if "exampleprovider" in lower or "api.example" in lower or "example-chat-model" in lower:
                return "allowed", "low", "generic custom-provider fixture assertion"
            return "must_fix", "high", "positive site-specific provider assertion still requires old behavior"

        if raw_category == "retired_doc_surface":
            if is_negative_or_compat_test(line):
                return "allowed", "low", "negative guard against retired documentation"
            return "must_fix", "high", "positive assertion still expects retired documentation"

        if raw_category == "assertion_contract_review":
            if is_negative_or_compat_test(line):
                return "allowed", "low", "negative or compatibility assertion"
            if "isprerelease=false" in lower or "ordinary github latest" in lower or "pinned current latest release tag" in lower:
                return "allowed", "low", "current release contract assertion"
            if "current public release kind:" in lower and "pre-release" in lower:
                return "must_fix", "high", "positive stale release assertion"
            if "api.llm.ustc.edu.cn" in lower or "default provider: ustc" in lower:
                return "must_fix", "high", "positive site-specific provider assertion"
            if "pre-release" in lower and "result.stdout" not in lower and "upgrade" not in lower:
                return "must_fix", "high", "positive stale release assertion"
            if "set-api-key" in lower or "glm" in lower or "brave" in lower:
                return "review", "medium", "deprecated provider/command boundary belongs to p2.19a15"
            if "750000" in lower or "0.75" in lower:
                return "review", "medium", "legacy threshold compatibility belongs to p2.19a16"
            return "review", "medium", "contract-sensitive test assertion requires manual review"

        if raw_category == "deprecated_provider_surface":
            if "qwen-us" in lower:
                return "allowed", "low", "qwen-us is current public regional provider, not a legacy shortcut"
            return "review", "medium", "deprecated provider/command boundary belongs to p2.19a15"

        if raw_category == "old_effort_or_threshold":
            return "review", "medium", "legacy threshold compatibility belongs to p2.19a16"

        return "review", "medium", "test candidate; keep only if it asserts current or negative compatibility behavior"

    if bucket in {"runtime_source", "installer_scripts", "user_docs"}:
        if raw_category in {
            "stale_release_state",
            "retired_doc_surface",
            "site_specific_default",
            "old_ui_surface",
            "future_name_user_surface",
            "forbidden_plain_release_tag",
            "diagnostic_typo",
        }:
            return "must_fix", "high", "user-facing or production candidate"
        if raw_category in {"legacy_profile_contract", "recursive_wrapper_risk", "old_effort_or_threshold"}:
            return "review", "medium", "could be required compatibility or guard logic; do not delete blindly"
        return "review", "medium", "production surface candidate"

    if raw_category in {"forbidden_plain_release_tag", "diagnostic_typo"}:
        return "must_fix", "high", "global hygiene issue"

    return "review", "medium", "manual review required"

def make_finding(
    *,
    rel: str,
    line_no: int,
    bucket: str,
    raw_category: str,
    label: str,
    text: str,
) -> dict[str, object]:
    classification, severity, allow_note = classify(bucket, raw_category, rel, text)
    return {
        "classification": classification,
        "severity": severity,
        "bucket": bucket,
        "category": raw_category,
        "raw_category": raw_category,
        "file": rel,
        "line": line_no,
        "allow_note": allow_note,
        "label": label,
        "text": text[:500],
    }


def scan_text_files(repo: Path, files: Iterable[str]) -> list[dict[str, object]]:
    compiled = [(spec, re.compile(spec.regex, re.IGNORECASE)) for spec in PATTERNS]
    findings: list[dict[str, object]] = []
    for rel in files:
        path = repo / rel
        text = text_or_none(path)
        if text is None:
            continue
        bucket = bucket_for(rel)
        for line_no, line in enumerate(text.splitlines(), 1):
            for spec, rx in compiled:
                if rx.search(line):
                    findings.append(
                        make_finding(
                            rel=rel,
                            line_no=line_no,
                            bucket=bucket,
                            raw_category=spec.category,
                            label=spec.label,
                            text=line,
                        )
                    )
    return findings


def scan_test_assertions(repo: Path, files: Iterable[str]) -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    sensitive = re.compile(
        r"pre-release|isPrerelease|v0\.4\.0-alpha|resolved by release tag|"
        r"USTC|api\.llm\.ustc\.edu\.cn|deepseek-v4-flash-ascend|750000|"
        r"\[profiles\.|developer-handbook|development-log|Brave|set-api-key|DEPPSEEK",
        re.IGNORECASE,
    )
    for rel in files:
        if not rel.startswith("tests/") or not rel.endswith(".py"):
            continue
        text = text_or_none(repo / rel)
        if text is None:
            continue
        try:
            tree = ast.parse(text)
        except SyntaxError as exc:
            findings.append(
                make_finding(
                    rel=rel,
                    line_no=getattr(exc, "lineno", 1) or 1,
                    bucket="tests",
                    raw_category="test_parse_error",
                    label="Test file failed AST parse during audit",
                    text=repr(exc),
                )
            )
            continue
        lines = text.splitlines()
        for node in ast.walk(tree):
            if isinstance(node, ast.Assert):
                line = lines[node.lineno - 1] if 0 < node.lineno <= len(lines) else ""
                if sensitive.search(line):
                    findings.append(
                        make_finding(
                            rel=rel,
                            line_no=node.lineno,
                            bucket="tests",
                            raw_category="assertion_contract_review",
                            label="Assertion references a stale-sensitive contract marker",
                            text=line,
                        )
                    )
    return findings


def summarize(findings: list[dict[str, object]]) -> dict[str, object]:
    by_classification = Counter(str(f["classification"]) for f in findings)
    by_severity = Counter(str(f["severity"]) for f in findings)
    by_category = Counter(str(f["category"]) for f in findings)
    by_bucket = Counter(str(f["bucket"]) for f in findings)

    groups: dict[str, list[str]] = defaultdict(list)
    for finding in findings:
        if finding["classification"] == "must_fix":
            groups[str(finding["raw_category"])].append(str(finding["file"]))

    return {
        "total": len(findings),
        "by_classification": dict(sorted(by_classification.items())),
        "by_severity": dict(sorted(by_severity.items())),
        "by_category": dict(sorted(by_category.items())),
        "by_bucket": dict(sorted(by_bucket.items())),
        "must_fix_files_by_category": {
            k: sorted(set(v)) for k, v in sorted(groups.items())
        },
    }


def write_tsv(path: Path, findings: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=TSV_FIELDS, delimiter="\t", extrasaction="ignore")
        writer.writeheader()
        for finding in findings:
            row = {field: str(finding.get(field, "")) for field in TSV_FIELDS}
            row["text"] = row["text"].replace("\n", " ").replace("\t", " ")
            writer.writerow(row)


def write_text_report(path: Path, payload: dict[str, object], max_sample: int) -> None:
    findings = list(payload["findings"])
    summary = payload["summary"]
    current_state = payload["current_state"]

    lines: list[str] = []
    lines.append(f"stage={payload['stage']}")
    lines.append("mode=read_only_ghost_contract_audit")
    lines.append(f"generated_at={payload['generated_at']}")
    lines.append(f"repo={payload['repo']}")
    lines.append("")
    lines.append("===== CURRENT STATE =====")
    for key, value in current_state.items():
        lines.append(f"{key}={value}")
    lines.append("")
    lines.append("===== SUMMARY =====")
    lines.append(json.dumps(summary, ensure_ascii=False, indent=2))
    lines.append("")
    lines.append("===== MUST_FIX SAMPLE =====")
    must_fix = [f for f in findings if f["classification"] == "must_fix"]
    for f in must_fix[:max_sample]:
        lines.append(
            f"{f['severity']}\t{f['bucket']}\t{f['raw_category']}\t"
            f"{f['file']}:{f['line']}\t{f['text']}"
        )
    if len(must_fix) > max_sample:
        lines.append(f"... must_fix_truncated={len(must_fix) - max_sample}")
    lines.append("")
    lines.append("===== REVIEW SAMPLE =====")
    review = [f for f in findings if f["classification"] == "review"]
    for f in review[:max_sample]:
        lines.append(
            f"{f['severity']}\t{f['bucket']}\t{f['raw_category']}\t"
            f"{f['file']}:{f['line']}\t{f['text']}"
        )
    if len(review) > max_sample:
        lines.append(f"... review_truncated={len(review) - max_sample}")
    lines.append("")
    lines.append("===== CLEANUP QUEUE =====")
    lines.append("Q1: hard-stale tests and overbroad production-source scans.")
    lines.append("Q2: user-facing stale Release/channel wording in README, installer, CLI help, and wizard.")
    lines.append("Q3: site-specific custom provider examples in user-facing surfaces.")
    lines.append("Q4: provider alias and deprecated command boundary review.")
    lines.append("Q5: compatibility markers that should remain but need comments or scoped tests.")
    lines.append("")
    lines.append("run_ok=1")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def default_output_paths(out_dir: Path) -> tuple[Path, Path, Path]:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return (
        out_dir / f"audit-codexchange-ghost-contracts-{stamp}.txt",
        out_dir / f"audit-codexchange-ghost-contracts-findings-{stamp}.json",
        out_dir / f"audit-codexchange-ghost-contracts-findings-{stamp}.tsv",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only ghost contract audit for CodeXchange.")
    parser.add_argument("--repo", default=".", help="Repository root.")
    parser.add_argument("--out-dir", default="/tmp", help="Directory for generated reports.")
    parser.add_argument("--out", default=None, help="Text report path.")
    parser.add_argument("--json-out", default=None, help="JSON report path.")
    parser.add_argument("--tsv-out", default=None, help="TSV report path.")
    parser.add_argument("--max-sample", type=int, default=240, help="Maximum findings per sample section.")
    parser.add_argument("--quiet", action="store_true", help="Only print output paths and summary counts.")
    args = parser.parse_args(argv)

    repo = Path(args.repo).expanduser().resolve()
    out_dir = Path(args.out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    default_txt, default_json, default_tsv = default_output_paths(out_dir)
    text_out = Path(args.out).expanduser().resolve() if args.out else default_txt
    json_out = Path(args.json_out).expanduser().resolve() if args.json_out else default_json
    tsv_out = Path(args.tsv_out).expanduser().resolve() if args.tsv_out else default_tsv

    files = tracked_files(repo)
    text_findings = scan_text_files(repo, files)
    assertion_findings = scan_test_assertions(repo, files)
    findings = text_findings + assertion_findings

    head = run_git(repo, ["rev-parse", "--short", "HEAD"], check=False).stdout.strip()
    branch = run_git(repo, ["rev-parse", "--abbrev-ref", "HEAD"], check=False).stdout.strip()
    status = run_git(repo, ["status", "--short"], check=False).stdout
    public_tag = run_git(repo, ["rev-parse", f"{CURRENT_PUBLIC_TAG}^{{commit}}"], check=False).stdout.strip()
    current_state = {
        "branch": branch,
        "head": head,
        "status_count": len([x for x in status.splitlines() if x.strip()]),
        "current_public_tag": CURRENT_PUBLIC_TAG,
        "current_public_tag_commit": public_tag,
        "current_public_commit_short": CURRENT_PUBLIC_COMMIT_SHORT,
        "current_internal_tag": CURRENT_INTERNAL_TAG,
        "current_runtime_release_internal_tag": CURRENT_RUNTIME_RELEASE_INTERNAL_TAG,
        "tracked_files": len(files),
    }

    payload = {
        "stage": "audit-codexchange-ghost-contracts",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repo": str(repo),
        "current_state": current_state,
        "summary": summarize(findings),
        "findings": findings,
    }

    json_out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_tsv(tsv_out, findings)
    write_text_report(text_out, payload, max_sample=args.max_sample)

    summary = payload["summary"]
    if not args.quiet:
        print(f"out={text_out}")
        print(f"json_out={json_out}")
        print(f"tsv_out={tsv_out}")
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(f"out={text_out}")
        print(f"json_out={json_out}")
        print(f"tsv_out={tsv_out}")
        print(f"total={summary['total']}")
        print(f"must_fix={summary['by_classification'].get('must_fix', 0)}")
        print(f"review={summary['by_classification'].get('review', 0)}")
        print(f"allowed={summary['by_classification'].get('allowed', 0)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
