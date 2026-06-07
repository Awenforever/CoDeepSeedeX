from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "audit-ghost-contracts.py"


def _run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=True,
    )


def _make_temp_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _run(["git", "init"], repo)
    _run(["git", "config", "user.email", "test@example.invalid"], repo)
    _run(["git", "config", "user.name", "Test"], repo)

    (repo / "README.md").write_text(
        "Current public Release kind: " "pre-release\n"
        "Default provider: " "U" "STC\n",
        encoding="utf-8",
    )
    (repo / "docs").mkdir()
    (repo / "docs" / ("development-" "log.md")).write_text(
        "Historical note: Current public Release kind: " "pre-release\n",
        encoding="utf-8",
    )
    (repo / "tests").mkdir()
    (repo / "tests" / "test_old_contract.py").write_text(
        "def test_old():\n"
        "    text = 'Current public Release kind: ' + 'pre-release'\n"
        "    assert 'pre-release' in text\n",
        encoding="utf-8",
    )
    _run(["git", "add", "README.md", "docs/" + "development-" + "log.md", "tests/test_old_contract.py"], repo)
    _run(["git", "commit", "-m", "seed"], repo)
    return repo


def test_ghost_contract_audit_outputs_schema_and_classifications(tmp_path: Path) -> None:
    repo = _make_temp_repo(tmp_path)
    out = tmp_path / "audit.txt"
    json_out = tmp_path / "audit.json"
    tsv_out = tmp_path / "audit.tsv"

    cp = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--repo",
            str(repo),
            "--out",
            str(out),
            "--json-out",
            str(json_out),
            "--tsv-out",
            str(tsv_out),
            "--quiet",
        ],
        cwd=str(ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=True,
    )

    assert "must_fix=" in cp.stdout
    assert out.exists()
    assert json_out.exists()
    assert tsv_out.exists()

    payload = json.loads(json_out.read_text(encoding="utf-8"))
    findings = payload["findings"]
    assert findings
    assert all("raw_category" in finding for finding in findings)
    assert all("classification" in finding for finding in findings)

    assert any(
        f["file"] == "README.md"
        and f["raw_category"] == "stale_release_state"
        and f["classification"] == "must_fix"
        for f in findings
    )
    assert any(
        f["file"] == "docs/" + "development-" + "log.md"
        and f["classification"] == "allowed"
        for f in findings
    )
    assert any(
        f["file"] == "tests/test_old_contract.py"
        and f["raw_category"] in {"stale_test_assertion", "assertion_contract_review"}
        and f["classification"] == "must_fix"
        for f in findings
    )

    header = tsv_out.read_text(encoding="utf-8").splitlines()[0]
    assert "raw_category" in header
    assert "classification" in header


def test_ghost_contract_audit_runs_on_current_repository(tmp_path: Path) -> None:
    out = tmp_path / "current.txt"
    json_out = tmp_path / "current.json"
    tsv_out = tmp_path / "current.tsv"

    subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--repo",
            str(ROOT),
            "--out",
            str(out),
            "--json-out",
            str(json_out),
            "--tsv-out",
            str(tsv_out),
            "--quiet",
            "--max-sample",
            "20",
        ],
        cwd=str(ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=True,
    )

    payload = json.loads(json_out.read_text(encoding="utf-8"))
    assert payload["stage"] == "audit-codeepseedex-ghost-contracts"
    assert payload["current_state"]["tracked_files"] > 0
    assert all("raw_category" in finding for finding in payload["findings"])
    assert all(finding["classification"] in {"must_fix", "review", "allowed"} for finding in payload["findings"])
