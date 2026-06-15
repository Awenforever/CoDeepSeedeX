from __future__ import annotations

from pathlib import Path

from codexchange_proxy import cli


def test_installer_generated_lifecycle_wrapper_uses_reasoning_alias() -> None:
    text = Path("scripts/install.sh").read_text(encoding="utf-8")

    assert "start_args=(start reasoning)" in text
    assert "status_args=(status reasoning)" in text
    legacy_start_args = "start_args=(start " + "thinking)"
    assert legacy_start_args not in text
    legacy_status_args = "status_args=(status " + "thinking)"
    assert legacy_status_args not in text


def test_cli_generated_lifecycle_wrapper_uses_reasoning_alias() -> None:
    text = Path("codexchange_proxy/cli.py").read_text(encoding="utf-8")

    assert "start_args=(start reasoning)" in text
    assert "status_args=(status reasoning)" in text
    legacy_start_args = "start_args=(start " + "thinking)"
    assert legacy_start_args not in text
    legacy_status_args = "status_args=(status " + "thinking)"
    assert legacy_status_args not in text


def test_post_config_apply_refresh_uses_reasoning_alias() -> None:
    text = Path("codexchange_proxy/cli.py").read_text(encoding="utf-8")

    assert 'stop_argv = ["stop", "reasoning"] if thinking else ["stop"]' in text
    assert 'start_argv = ["start", "reasoning"] if thinking else ["start"]' in text
    legacy_stop_argv = 'stop_argv = ["stop", "' + 'thinking"] if thinking else ["stop"]'
    assert legacy_stop_argv not in text
    legacy_start_argv = 'start_argv = ["start", "' + 'thinking"] if thinking else ["start"]'
    assert legacy_start_argv not in text


def test_legacy_lifecycle_aliases_remain_accepted() -> None:
    assert cli._normalize_route_target_to_reasoning("reasoning") is True
    assert cli._normalize_route_target_to_reasoning("thinking") is True
    assert cli._normalize_route_target_to_reasoning("standard") is False
    assert cli._normalize_route_target_to_reasoning("stable") is False
    assert cli._normalize_route_target_to_reasoning("non-thinking") is False
    assert cli._normalize_route_target_to_reasoning("non_thinking") is False
