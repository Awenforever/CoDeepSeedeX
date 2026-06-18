from __future__ import annotations

import argparse
import contextlib
import fcntl
import os
import re
import shlex
import stat
import sys
import tempfile
from pathlib import Path
from typing import Iterable, Iterator, Mapping, Sequence

_EXPORT_RE = re.compile(r"^export[ \t]+([A-Za-z_][A-Za-z0-9_]*)=(.*)$")
_ENV_KEY_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
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


class EnvFileStorageError(OSError):
    """Raised when an env or lock path violates the private regular-file contract."""


class EnvExportSnapshot(dict[str, str]):
    """Mutable export snapshot that remembers its original values for safe rebasing."""

    def __init__(self, values: Mapping[str, str] = ()) -> None:
        super().__init__(values)
        self.original = dict(values)


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


def _parse_env_text(path: Path, text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
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


def _require_private_regular_stat(path: Path, metadata: os.stat_result, *, kind: str) -> None:
    if not stat.S_ISREG(metadata.st_mode):
        raise EnvFileStorageError(f"{kind} must be a regular file: {path}")
    if metadata.st_nlink != 1:
        raise EnvFileStorageError(f"{kind} must have exactly one hard link: {path}")


def _secure_read_text(path: Path) -> str | None:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise EnvFileStorageError(f"cannot safely open env file: {path}") from exc
    try:
        metadata = os.fstat(fd)
        _require_private_regular_stat(path, metadata, kind="env file")
        with os.fdopen(fd, "r", encoding="utf-8", closefd=False) as stream:
            return stream.read()
    finally:
        os.close(fd)


def _read_env_exports_unlocked(path: Path) -> dict[str, str]:
    text = _secure_read_text(path)
    if text is None:
        return {}
    return _parse_env_text(path, text)


def read_env_exports(path: Path) -> EnvExportSnapshot:
    return EnvExportSnapshot(_read_env_exports_unlocked(path))


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


def _lock_path(path: Path) -> Path:
    return path.with_name(f".{path.name}.lock")


@contextlib.contextmanager
def _exclusive_env_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = _lock_path(path)
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(lock_path, flags, 0o600)
    except OSError as exc:
        raise EnvFileStorageError(f"cannot safely open env lock: {lock_path}") from exc
    try:
        metadata = os.fstat(fd)
        _require_private_regular_stat(lock_path, metadata, kind="env lock")
        os.fchmod(fd, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX)
        metadata = os.fstat(fd)
        _require_private_regular_stat(lock_path, metadata, kind="env lock")
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def _validate_existing_target(path: Path) -> None:
    try:
        metadata = os.lstat(path)
    except FileNotFoundError:
        return
    if stat.S_ISLNK(metadata.st_mode):
        raise EnvFileStorageError(f"env file must not be a symbolic link: {path}")
    _require_private_regular_stat(path, metadata, kind="env file")


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0)
    fd = os.open(path, flags)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _atomic_write_text_unlocked(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _validate_existing_target(path)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.tmp-", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8", closefd=True) as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        fd = -1
        _validate_existing_target(path)
        os.replace(temporary, path)
        os.chmod(path, 0o600, follow_symlinks=False)
        final_metadata = os.lstat(path)
        _require_private_regular_stat(path, final_metadata, kind="env file")
        _fsync_directory(path.parent)
    finally:
        if fd >= 0:
            os.close(fd)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _write_values_unlocked(
    path: Path,
    values: Mapping[str, str],
    *,
    ordered_keys: Iterable[str],
    header: Iterable[str],
) -> None:
    text = render_env_exports(values, ordered_keys=ordered_keys, header=header)
    _atomic_write_text_unlocked(path, text)


def update_env_exports(
    path: Path,
    updates: Mapping[str, str],
    *,
    remove_keys: Iterable[str] = (),
    ordered_keys: Iterable[str] = (),
    header: Iterable[str] = (),
    ensure_only: bool = False,
) -> EnvExportSnapshot:
    with _exclusive_env_lock(path):
        current = _read_env_exports_unlocked(path)
        changed = False
        for key, value in updates.items():
            if not _ENV_KEY_RE.fullmatch(key):
                raise EnvFileStorageError("invalid env key")
            if ensure_only and key in current:
                continue
            text_value = str(value)
            if current.get(key) != text_value:
                current[key] = text_value
                changed = True
        for key in remove_keys:
            if key in current:
                del current[key]
                changed = True
        if changed or not path.exists():
            _write_values_unlocked(path, current, ordered_keys=ordered_keys, header=header)
        else:
            _validate_existing_target(path)
            flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
            fd = os.open(path, flags)
            try:
                metadata = os.fstat(fd)
                _require_private_regular_stat(path, metadata, kind="env file")
                os.fchmod(fd, 0o600)
                os.fsync(fd)
            finally:
                os.close(fd)
        return EnvExportSnapshot(current)


def write_env_exports(
    path: Path,
    values: Mapping[str, str],
    *,
    ordered_keys: Iterable[str] = (),
    header: Iterable[str] = (),
) -> None:
    if isinstance(values, EnvExportSnapshot):
        original = values.original
        updates = {
            key: value
            for key, value in values.items()
            if key not in original or original[key] != value
        }
        remove_keys = [key for key in original if key not in values]
        update_env_exports(
            path,
            updates,
            remove_keys=remove_keys,
            ordered_keys=ordered_keys,
            header=header,
        )
        return
    normalized = {str(key): str(value) for key, value in values.items()}
    for key in normalized:
        if not _ENV_KEY_RE.fullmatch(key):
            raise EnvFileStorageError("invalid env key")
    with _exclusive_env_lock(path):
        _write_values_unlocked(path, normalized, ordered_keys=ordered_keys, header=header)


def emit_runtime_nul(path: Path) -> None:
    output = sys.stdout.buffer
    for key, value in runtime_env_exports(path).items():
        output.write(key.encode("utf-8"))
        output.write(b"\0")
        output.write(value.encode("utf-8"))
        output.write(b"\0")


def _read_nul_pairs(data: bytes) -> tuple[dict[str, str], list[str]]:
    fields = data.split(b"\0")
    if fields and fields[-1] == b"":
        fields.pop()
    if len(fields) % 2:
        raise EnvFileStorageError("truncated NUL env data")
    values: dict[str, str] = {}
    order: list[str] = []
    for index in range(0, len(fields), 2):
        try:
            key = fields[index].decode("utf-8")
            value = fields[index + 1].decode("utf-8")
        except UnicodeDecodeError as exc:
            raise EnvFileStorageError("invalid UTF-8 env data") from exc
        if not _ENV_KEY_RE.fullmatch(key):
            raise EnvFileStorageError("invalid env key")
        if key in values:
            raise EnvFileStorageError("duplicate env key")
        values[key] = value
        order.append(key)
    return values, order


def _add_nul_command(subparsers: argparse._SubParsersAction[argparse.ArgumentParser], name: str) -> None:
    command = subparsers.add_parser(name)
    command.add_argument("path")
    command.add_argument("--header", action="append", default=[])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m codexchange_proxy.env_file")
    subparsers = parser.add_subparsers(dest="command", required=True)
    emit = subparsers.add_parser("emit-runtime-nul")
    emit.add_argument("path")
    set_export = subparsers.add_parser("set-export")
    set_export.add_argument("path")
    set_export.add_argument("key")
    set_export.add_argument("value")
    _add_nul_command(subparsers, "replace-exports-nul")
    _add_nul_command(subparsers, "ensure-exports-nul")
    args = parser.parse_args(argv)
    try:
        path = Path(args.path).expanduser()
        if args.command == "emit-runtime-nul":
            emit_runtime_nul(path)
            return 0
        if args.command == "set-export":
            if not _ENV_KEY_RE.fullmatch(args.key):
                print("CodeXchange: invalid env key", file=sys.stderr)
                return 70
            update_env_exports(
                path,
                {args.key: args.value},
                header=("# codexchange local environment", "# Generated by cox-config"),
            )
            return 0
        if args.command in {"replace-exports-nul", "ensure-exports-nul"}:
            values, order = _read_nul_pairs(sys.stdin.buffer.read())
            if args.command == "replace-exports-nul":
                write_env_exports(path, values, ordered_keys=order, header=args.header)
            else:
                update_env_exports(
                    path,
                    values,
                    ordered_keys=order,
                    header=args.header,
                    ensure_only=True,
                )
            return 0
    except EnvFileParseError as exc:
        print(f"CodeXchange: invalid env data at line {exc.line_number}", file=sys.stderr)
        return 70
    except (EnvFileStorageError, OSError) as exc:
        print(f"CodeXchange: cannot safely access env data: {exc}", file=sys.stderr)
        return 70
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
