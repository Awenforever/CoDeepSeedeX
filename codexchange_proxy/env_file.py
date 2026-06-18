from __future__ import annotations

import argparse
import os
import re
import shlex
import sys
from pathlib import Path
from typing import Iterable, Mapping

_EXPORT_RE = re.compile(r"^export[ \t]+([A-Za-z_][A-Za-z0-9_]*)=(.*)$")
_RUNTIME_EXACT_NAMES = {
    "SEARCH_PROVIDER",
    "IMAGE_PROVIDER",
    "SERPAPI_API_KEY",
    "TAVILY_API_KEY",
    "EXA_API_KEY",
    "FIRECRAWL_API_KEY",
    "ZAI_API_KEY",
    "ZHIPUAI_API_KEY",
    "ZHIPU_API_KEY",
    "GLM_API_KEY",
}


class EnvFileParseError(ValueError):
    """Raised when an export assignment cannot be parsed as inert data."""

    def __init__(self, path: Path, line_number: int, reason: str):
        super().__init__(f"{path}:{line_number}: {reason}")
        self.path = path
        self.line_number = line_number
        self.reason = reason


def _decode_ansi_c_quoted(value: str) -> str:
    if not (value.startswith("$'") and value.endswith("'")):
        raise ValueError("not ANSI-C quoted")
    body = value[2:-1]
    out: list[str] = []
    index = 0
    simple = {
        "a": "\a",
        "b": "\b",
        "e": "\x1b",
        "E": "\x1b",
        "f": "\f",
        "n": "\n",
        "r": "\r",
        "t": "\t",
        "v": "\v",
        "\\": "\\",
        "'": "'",
        '"': '"',
    }
    while index < len(body):
        char = body[index]
        if char != "\\":
            out.append(char)
            index += 1
            continue
        index += 1
        if index >= len(body):
            out.append("\\")
            break
        escape = body[index]
        if escape in simple:
            out.append(simple[escape])
            index += 1
            continue
        if escape == "\n":
            index += 1
            continue
        if escape in {"x", "u", "U"}:
            width = {"x": 2, "u": 4, "U": 8}[escape]
            digits = body[index + 1 : index + 1 + width]
            if not digits or any(ch not in "0123456789abcdefABCDEF" for ch in digits):
                out.append("\\" + escape)
                index += 1
                continue
            out.append(chr(int(digits, 16)))
            index += 1 + len(digits)
            continue
        if escape in "01234567":
            end = index + 1
            while end < min(len(body), index + 3) and body[end] in "01234567":
                end += 1
            out.append(chr(int(body[index:end], 8)))
            index = end
            continue
        out.append(escape)
        index += 1
    return "".join(out)


def parse_env_value(raw_value: str) -> str:
    value = raw_value.strip()
    if value == "":
        return ""
    if value.startswith("$'"):
        return _decode_ansi_c_quoted(value)
    parts = shlex.split(value, comments=False, posix=True)
    if len(parts) != 1:
        raise ValueError("export value must be exactly one shell data token")
    return parts[0]


def read_env_exports(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        raise
    for line_number, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = _EXPORT_RE.fullmatch(line)
        if match is None:
            # Configuration files are data. Unknown non-export lines are ignored,
            # never evaluated as shell syntax.
            continue
        key, raw_value = match.groups()
        try:
            values[key] = parse_env_value(raw_value)
        except (ValueError, UnicodeError) as exc:
            raise EnvFileParseError(path, line_number, "invalid export data") from exc
    return values


def _ansi_c_quote(value: str) -> str:
    pieces: list[str] = []
    for char in value:
        code = ord(char)
        if char == "\\":
            pieces.append("\\\\")
        elif char == "'":
            pieces.append("\\'")
        elif char == "\n":
            pieces.append("\\n")
        elif char == "\r":
            pieces.append("\\r")
        elif char == "\t":
            pieces.append("\\t")
        elif code < 32 or code == 127:
            pieces.append(f"\\x{code:02x}")
        else:
            pieces.append(char)
    return "$'" + "".join(pieces) + "'"


def quote_env_value(value: object) -> str:
    text = str(value)
    if any(char in text for char in "\n\r\t") or any(ord(char) < 32 or ord(char) == 127 for char in text):
        return _ansi_c_quote(text)
    return shlex.quote(text)


def is_runtime_env_name(name: str) -> bool:
    return name.startswith("COX_") or name in _RUNTIME_EXACT_NAMES


def runtime_env_exports(path: Path) -> dict[str, str]:
    return {key: value for key, value in read_env_exports(path).items() if is_runtime_env_name(key)}


def render_env_exports(
    values: Mapping[str, str],
    *,
    ordered_keys: Iterable[str] = (),
    header: Iterable[str] = (),
) -> str:
    lines = list(header)
    emitted: set[str] = set()
    for key in ordered_keys:
        if key in values:
            lines.append(f"export {key}={quote_env_value(values[key])}")
            emitted.add(key)
    for key in sorted(values):
        if key not in emitted:
            lines.append(f"export {key}={quote_env_value(values[key])}")
    return "\n".join(lines).rstrip() + "\n"


def write_env_exports(
    path: Path,
    values: Mapping[str, str],
    *,
    ordered_keys: Iterable[str] = (),
    header: Iterable[str] = (),
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = render_env_exports(values, ordered_keys=ordered_keys, header=header)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    try:
        temporary.write_text(text, encoding="utf-8")
        temporary.chmod(0o600)
        os.replace(temporary, path)
        path.chmod(0o600)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def emit_runtime_nul(path: Path) -> None:
    output = sys.stdout.buffer
    for key, value in runtime_env_exports(path).items():
        output.write(key.encode("utf-8"))
        output.write(b"\0")
        output.write(value.encode("utf-8"))
        output.write(b"\0")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m codexchange_proxy.env_file")
    subparsers = parser.add_subparsers(dest="command", required=True)
    emit = subparsers.add_parser("emit-runtime-nul")
    emit.add_argument("path")
    set_export = subparsers.add_parser("set-export")
    set_export.add_argument("path")
    set_export.add_argument("key")
    set_export.add_argument("value")
    args = parser.parse_args(argv)
    try:
        if args.command == "emit-runtime-nul":
            emit_runtime_nul(Path(args.path).expanduser())
            return 0
        if args.command == "set-export":
            path = Path(args.path).expanduser()
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", args.key):
                print("CodeXchange: invalid env key", file=sys.stderr)
                return 70
            values = read_env_exports(path)
            values[args.key] = args.value
            write_env_exports(
                path,
                values,
                header=("# codexchange local environment", "# Generated by cox-config"),
            )
            return 0
    except EnvFileParseError as exc:
        print(f"CodeXchange: invalid env data at line {exc.line_number}", file=sys.stderr)
        return 70
    except OSError as exc:
        print(f"CodeXchange: cannot read env data: {exc}", file=sys.stderr)
        return 70
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
