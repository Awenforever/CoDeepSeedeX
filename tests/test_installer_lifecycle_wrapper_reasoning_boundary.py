from __future__ import annotations

from pathlib import Path

from codexchange_proxy import cli


ROOT = Path(__file__).resolve().parents[1]
CANONICAL_WRAPPER = ROOT / "scripts" / "codex-wrapper.bash"
INSTALLER = ROOT / "scripts" / "install.sh"
CLI_SOURCE = ROOT / "codexchange_proxy" / "cli.py"


def test_canonical_lifecycle_wrapper_uses_reasoning_route() -> None:
    text = CANONICAL_WRAPPER.read_text(encoding="utf-8")
    lifecycle = text[
        text.index("# BEGIN COX PROFILE-AGNOSTIC RUNTIME AUTOSTART") :
        text.index("# BEGIN COX EXECUTABLE WRAPPER DISPATCHER")
    ]

    assert 'route="reasoning"' in lifecycle
    assert 'start_args=(start "$route"' in lifecycle
    assert "start_args=(start thinking)" not in lifecycle
    assert 'route="thinking"' not in lifecycle


def test_installer_and_cli_consume_the_canonical_lifecycle_wrapper() -> None:
    installer = INSTALLER.read_text(encoding="utf-8")
    cli_text = CLI_SOURCE.read_text(encoding="utf-8")
    canonical_text = CANONICAL_WRAPPER.read_text(encoding="utf-8")

    assert 'cp "$template" "$wrapper_path"' in installer
    assert "_load_canonical_codex_wrapper_template" in cli_text

    canonical_path, loaded_template, attempts = cli._load_canonical_codex_wrapper_template()
    assert canonical_path is not None, attempts
    assert canonical_path.resolve() == CANONICAL_WRAPPER.resolve()
    assert loaded_template == canonical_text


def test_post_config_apply_refresh_uses_reasoning_alias() -> None:
    text = CLI_SOURCE.read_text(encoding="utf-8")

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
