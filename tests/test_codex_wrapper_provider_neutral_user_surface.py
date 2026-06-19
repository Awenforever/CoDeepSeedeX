from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WRAPPER = (ROOT / "scripts/codex-wrapper.bash").read_text(encoding="utf-8")
HEADER = WRAPPER.split("# BEGIN COX PROFILE-AGNOSTIC RUNTIME AUTOSTART", 1)[0]


def test_codex_wrapper_behavior_header_uses_codexchange_runtime_terms() -> None:
    assert (
        "# - codex --profile cox starts the CodeXchange reasoning runtime on port 8001."
        in HEADER
    )
    assert (
        "# - codex --profile <custom-provider-id> uses its pre-generated split profile "
        "and starts the required CodeXchange runtime."
        in HEADER
    )


def test_codex_wrapper_behavior_header_no_longer_describes_primary_routes_as_proxy_branding() -> None:
    forbidden_markers = [
        "starts the thinking proxy",
        "starts the required proxy",
        "DeepSeek proxy",
        "DeepSeek thinking proxy",
        "thinking proxy on port 8001",
    ]
    for marker in forbidden_markers:
        assert marker not in HEADER


def test_legacy_deepseek_profile_deprecation_remains_fail_closed() -> None:
    assert "# - codex --profile deepseek is deprecated and fails closed." in HEADER
