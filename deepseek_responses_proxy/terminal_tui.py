from __future__ import annotations

import os
import re
import shutil
import sys
import termios
import tty
import unicodedata
from dataclasses import dataclass
from typing import TextIO

ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
BACK_EVENT = "__CODEEPSEEDEX_BACK__"
BLUE = "\033[38;5;33m"
BRIGHT_BLUE = "\033[1;38;5;75m"
DIM = "\033[2m"
RESET = "\033[0m"
CLEAR_LINE = "\033[K"


@dataclass(frozen=True)
class TerminalMenuOption:
    value: str
    label: str
    status: str = ""


def strip_ansi(value: str) -> str:
    return ANSI_RE.sub("", str(value or ""))


def cell_width_char(ch: str) -> int:
    if not ch:
        return 0
    if unicodedata.combining(ch):
        return 0
    category = unicodedata.category(ch)
    if category in {"Cc", "Cf"}:
        return 0
    if unicodedata.east_asian_width(ch) in {"F", "W"}:
        return 2
    return 1


def display_width(value: str) -> int:
    return sum(cell_width_char(ch) for ch in strip_ansi(value))


def terminal_width(default: int = 74, minimum: int = 58, maximum: int = 78) -> int:
    cols = shutil.get_terminal_size((default, 24)).columns
    try:
        cols = int(os.environ.get("COLUMNS") or cols)
    except Exception:
        cols = default
    usable = max(40, cols - 2)
    return max(minimum, min(maximum, usable))


def truncate_display(value: str, width: int) -> str:
    text = str(value or "")
    if display_width(text) <= width:
        return text
    out: list[str] = []
    used = 0
    marker = "…"
    marker_width = display_width(marker)
    for ch in strip_ansi(text):
        w = cell_width_char(ch)
        if used + w + marker_width > width:
            break
        out.append(ch)
        used += w
    return "".join(out) + marker


def pad_display(value: str, width: int) -> str:
    text = truncate_display(str(value or ""), width)
    return text + " " * max(0, width - display_width(text))


def _slice_display(value: str, width: int) -> tuple[str, str]:
    out: list[str] = []
    used = 0
    text = str(value or "")
    idx = 0
    for idx, ch in enumerate(text):
        w = cell_width_char(ch)
        if used + w > width:
            return "".join(out), text[idx:]
        out.append(ch)
        used += w
    return "".join(out), ""


def wrap_display_text(value: str, width: int) -> list[str]:
    text = str(value or "").strip()
    if not text:
        return [""]
    paragraphs = text.splitlines() or [text]
    lines: list[str] = []
    for paragraph in paragraphs:
        words = paragraph.split(" ")
        current = ""
        for word in words:
            if not word:
                continue
            candidate = word if not current else current + " " + word
            if display_width(candidate) <= width:
                current = candidate
                continue
            if current:
                lines.append(current)
                current = ""
            while display_width(word) > width:
                piece, rest = _slice_display(word, width)
                if not piece:
                    break
                lines.append(piece)
                word = rest
            current = word
        if current:
            lines.append(current)
    return lines or [""]


def _styled(text: str, style: str = "") -> str:
    return f"{style}{text}{RESET}" if style else text


def line(value: str = "", *, width: int | None = None, style: str = "", indent: int = 2) -> str:
    width = width or terminal_width()
    body_width = max(24, width - indent)
    prefix = " " * indent
    rendered: list[str] = []
    for part in wrap_display_text(value, body_width):
        rendered.append(f"{prefix}{_styled(part, style)}{CLEAR_LINE}")
    return "\n".join(rendered)


def blank(*, width: int | None = None) -> str:
    return f"{CLEAR_LINE}"


def header(title: str = "CoDeepSeedeX", *, width: int | None = None) -> str:
    width = width or terminal_width()
    label = truncate_display(title, max(12, width - 4))
    fill = "─" * max(4, width - display_width(label) - 2)
    return f"\n{BLUE}{label} {fill}{RESET}{CLEAR_LINE}"


def footer(label: str = "Step 1/1", *, width: int | None = None) -> str:
    width = width or terminal_width()
    text = truncate_display(label, max(12, width - 3))
    fill = "─" * max(4, width - display_width(text) - 2)
    return f"{BLUE}{text} {fill}{RESET}{CLEAR_LINE}"


def style_for_status(status: str, *, selected: bool = False) -> str:
    status_lower = str(status or "").strip().lower()
    if selected:
        return BRIGHT_BLUE
    if status_lower == "supported":
        return "\033[38;5;114m"
    if status_lower in {"experimental", "validated"}:
        return "\033[38;5;177m"
    if status_lower in {"custom", "model availability varies"}:
        return "\033[38;5;215m"
    if status_lower == "unsupported":
        return DIM
    return ""


def render_panel(title: str, body: list[str] | tuple[str, ...] | None = None, *, footer_label: str = "Step 1/1", width: int | None = None) -> str:
    width = width or terminal_width()
    parts: list[str] = [header("CoDeepSeedeX", width=width), blank(width=width), line(title, width=width, style=BRIGHT_BLUE)]
    body = list(body or [])
    if body:
        parts.append(blank(width=width))
        for item in body:
            value = str(item or "")
            style = DIM if value.strip().lower().startswith("hint") else ""
            parts.append(line(value, width=width, style=style))
    parts.append(blank(width=width))
    parts.append(footer(footer_label, width=width))
    return "\n".join(parts)


def render_menu(title: str, options: list[TerminalMenuOption], selected: int = 0, *, help_text: str | None = None, footer_label: str = "Step 1/1", width: int | None = None) -> str:
    width = width or terminal_width()
    parts: list[str] = [header("CoDeepSeedeX", width=width), blank(width=width), line(title, width=width, style=BRIGHT_BLUE), blank(width=width)]
    if help_text:
        for item in wrap_display_text(help_text, max(24, width - 4))[:3]:
            parts.append(line(item, width=width, style=DIM))
        parts.append(blank(width=width))
    for idx, option in enumerate(options):
        marker = "●" if idx == selected else "○"
        suffix = f"  [{option.status}]" if option.status else ""
        row = f"{marker} [{option.value}] {option.label}{suffix}"
        parts.append(line(row, width=width, style=style_for_status(option.status, selected=idx == selected), indent=2))
    parts.append(blank(width=width))
    parts.append(line("↑/↓ or j/k move · Enter select · Backspace previous step", width=width, style=DIM))
    parts.append(footer(footer_label, width=width))
    return "\n".join(parts)


def clear_frame(stream: TextIO) -> None:
    print("\033[?25l\033[2J\033[3J\033[H", end="", file=stream, flush=True)


def select_menu(title: str, options: list[TerminalMenuOption], default: str, *, help_text: str | None = None, footer_label: str = "Step 1/1", input_stream: TextIO | None = None, output_stream: TextIO | None = None, non_interactive: bool = False) -> str:
    input_stream = input_stream or sys.stdin
    output_stream = output_stream or sys.stderr
    if non_interactive or not getattr(input_stream, "isatty", lambda: False)():
        return default
    selected = 0
    for idx, option in enumerate(options):
        if option.value == default:
            selected = idx
            break
    fd = input_stream.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        while True:
            clear_frame(output_stream)
            print(render_menu(title, options, selected, help_text=help_text, footer_label=footer_label), file=output_stream, flush=True)
            ch = input_stream.read(1)
            if ch == "\x1b":
                seq = input_stream.read(2)
                if seq == "[A":
                    selected = (selected - 1) % len(options)
                elif seq == "[B":
                    selected = (selected + 1) % len(options)
                continue
            if ch in {"j", "J"}:
                selected = (selected + 1) % len(options)
                continue
            if ch in {"k", "K"}:
                selected = (selected - 1) % len(options)
                continue
            if ch in {"\r", "\n"}:
                return options[selected].value
            if ch in {"\x7f", "\b"}:
                return BACK_EVENT
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        print("\033[?25h", file=output_stream, flush=True)
