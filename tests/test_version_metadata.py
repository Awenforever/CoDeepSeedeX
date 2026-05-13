from __future__ import annotations

import subprocess
import tomllib
from pathlib import Path

from deepseek_responses_proxy.app import (
    PROXY_INTERNAL_VERSION,
    PROXY_PUBLIC_COMMIT,
    PROXY_PUBLIC_VERSION,
    PROXY_VERSION,
)
from deepseek_responses_proxy.cli import _format_version_metadata, _version_metadata


ROOT = Path(__file__).resolve().parents[1]


def test_public_runtime_version_matches_declared_release_tag() -> None:
    assert PROXY_PUBLIC_VERSION == "v0.3.7-alpha"
    assert PROXY_PUBLIC_COMMIT == "466706f"
    assert PROXY_VERSION == PROXY_PUBLIC_VERSION


def test_internal_runtime_version_uses_p_tag_namespace() -> None:
    assert PROXY_INTERNAL_VERSION.startswith("p")
    assert PROXY_INTERNAL_VERSION == "p2.9a22-version-metadata-policy-audit"


def test_pyproject_version_is_pep440_equivalent_to_public_release_tag() -> None:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert data["project"]["version"] == "0.3.7a0"


def test_cli_version_output_includes_public_and_internal_versions() -> None:
    result = subprocess.run(
        [".venv/bin/python", "-m", "deepseek_responses_proxy.cli", "--version"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    output = result.stdout.strip()
    assert "public version: v0.3.7-alpha |" in output
    assert "internal version: p" in output


def test_version_metadata_formatter_shape() -> None:
    text = _format_version_metadata(
        {
            "public_version": "vX",
            "public_commit": "abc1234",
            "internal_version": "pY",
            "internal_commit": "def5678",
        }
    )
    assert text.splitlines() == [
        "public version: vX | abc1234",
        "internal version: pY | def5678",
    ]


def test_version_metadata_reports_public_release_and_head_commit() -> None:
    data = _version_metadata()
    assert data["public_version"] == "v0.3.7-alpha"
    assert data["public_commit"] == "466706f"
    assert data["internal_version"].startswith("p")
    assert len(data["internal_commit"]) >= 7
