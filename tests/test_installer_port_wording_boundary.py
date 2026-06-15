from __future__ import annotations

from pathlib import Path


def test_installer_visible_port_wording_is_route_neutral() -> None:
    text = Path("scripts/install.sh").read_text(encoding="utf-8")

    assert "Proxy ports selected automatically: standard=$STABLE_PORT, reasoning=$THINKING_PORT" in text
    assert "Proxy ports selected automatically: non-thinking=$STABLE_PORT, thinking=$THINKING_PORT" not in text

    # Compatibility names remain implementation/config details until the runtime route is renamed.
    assert "DEFAULT_THINKING_PORT" in text
    assert "COX_THINKING_PORT" in text
    assert 'choose_available_port "$DEFAULT_THINKING_PORT" "$STABLE_PORT"' in text


def test_lifecycle_help_boundary_test_does_not_reintroduce_old_help_literals() -> None:
    text = Path("tests/test_lifecycle_help_wording_boundary.py").read_text(encoding="utf-8")

    assert ("optional target: " + "thinking") not in text
    assert ("start " + "thinking proxy on port 8001") not in text
    assert '"optional target: " + "thinking"' in text
    assert '"start " + "thinking proxy on port 8001"' in text
