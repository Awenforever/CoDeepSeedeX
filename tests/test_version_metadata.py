from __future__ import annotations

import subprocess
import sys
import tomllib
from pathlib import Path

from codexchange_proxy.app import (
    PROXY_INTERNAL_COMMIT,
    PROXY_INTERNAL_VERSION,
    PROXY_PUBLIC_COMMIT,
    PROXY_PUBLIC_VERSION,
    PROXY_VERSION,
)
from codexchange_proxy.cli import _format_version_metadata, _version_metadata


ROOT = Path(__file__).resolve().parents[1]


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _expected_public_commit() -> str:
    for ref in [f"{PROXY_PUBLIC_VERSION}^{{}}", "HEAD"]:
        result = subprocess.run(
            ["git", "rev-parse", "--short", ref],
            cwd=PROJECT_ROOT,
            text=True,
            capture_output=True,
            timeout=5,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    return PROXY_PUBLIC_COMMIT

def test_public_runtime_version_matches_declared_release_tag() -> None:
    assert PROXY_PUBLIC_VERSION == "v0.4.14-alpha"
    assert PROXY_PUBLIC_COMMIT == _expected_public_commit()


def test_internal_runtime_version_metadata_is_not_unknown() -> None:
    assert PROXY_INTERNAL_VERSION == "p3.0a1-codexchange-hardcut-generalized-router"
    assert PROXY_INTERNAL_COMMIT != "unknown"
    assert PROXY_VERSION == PROXY_PUBLIC_VERSION


def test_internal_runtime_version_uses_p_tag_namespace() -> None:
    assert PROXY_INTERNAL_VERSION.startswith("p")
    assert PROXY_INTERNAL_VERSION == "p3.0a1-codexchange-hardcut-generalized-router"


def test_pyproject_version_is_pep440_equivalent_to_public_release_tag() -> None:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert data["project"]["version"] == "0.4.14a0"


def test_cli_version_output_includes_public_and_internal_versions() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "codexchange_proxy.cli", "--version"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    output = result.stdout.strip()
    assert "public version: v0.4.14-alpha |" in output
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
    assert data["public_version"] == "v0.4.14-alpha"
    assert data["public_commit"] == _expected_public_commit()
    assert data["internal_version"].startswith("p")
    assert len(data["internal_commit"]) >= 7


def test_cli_version_output_uses_declared_internal_version() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "codexchange_proxy.cli", "--version"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    assert f"internal version: {PROXY_INTERNAL_VERSION} |" in result.stdout

def test_public_version_matches_packaged_installer_fallback_tag() -> None:
    import pathlib
    import re

    root = pathlib.Path(__file__).resolve().parents[1]
    text = (root / "scripts" / "install.sh").read_text(encoding="utf-8")
    match = re.search(
        r'COX_PUBLIC_RELEASE_TAG="\$\{COX_LATEST_RELEASE_FALLBACK_TAG:-(v[0-9]+\.[0-9]+\.[0-9]+-alpha)\}"',
        text,
    )
    assert match, "installer fallback public tag must be explicit"
    assert PROXY_PUBLIC_VERSION == match.group(1)
