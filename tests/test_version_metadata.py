import tomllib
from pathlib import Path

from deepseek_responses_proxy.app import PROXY_VERSION


ROOT = Path(__file__).resolve().parents[1]


def test_runtime_version_matches_release_tag() -> None:
    assert PROXY_VERSION == "v0.3.1"


def test_pyproject_version_matches_runtime_version() -> None:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert data["project"]["version"] == "0.3.1"
    assert PROXY_VERSION == f"v{data['project']['version']}"
