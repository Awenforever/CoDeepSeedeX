from __future__ import annotations

from deepseek_responses_proxy.terminal_tui import TerminalMenuOption, display_width, render_menu, render_panel, strip_ansi


def test_terminal_tui_display_width_counts_cjk_and_ignores_ansi() -> None:
    assert display_width("\033[31m选择语言\033[0m") == 8
    assert strip_ansi("\033[31mCoDeepSeedeX\033[0m") == "CoDeepSeedeX"


def test_terminal_tui_render_menu_stays_within_visible_width() -> None:
    rendered = render_menu(
        "Choose your language / 选择语言",
        [TerminalMenuOption("en", "English", ""), TerminalMenuOption("zh-CN", "简体中文", "")],
        selected=1,
        help_text="Use a language for installer prompts.",
        footer_label="Step 1/5",
        width=54,
    )
    visible = [display_width(line) for line in rendered.splitlines()]
    assert max(visible) <= 54
    assert "Step 1/5" in rendered
    assert "● [zh-CN] 简体中文" in rendered


def test_terminal_tui_render_panel_has_open_layout_without_right_border() -> None:
    rendered = render_panel("Setup plan", ["Only user-facing decisions are prompted."], footer_label="Step 0/5", width=50)
    assert "CoDeepSeedeX" in rendered
    assert "Setup plan" in rendered
    assert "Step 0/5" in rendered
    assert "╭" not in rendered
    assert "│" not in rendered
