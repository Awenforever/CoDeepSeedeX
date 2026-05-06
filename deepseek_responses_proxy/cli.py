from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .app import PROXY_VERSION


APP_NAME = "deepseek-responses-proxy"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_STABLE_PORT = 8000
DEFAULT_THINKING_PORT = 8001


def _xdg_config_home() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")).expanduser()


def _xdg_state_home() -> Path:
    return Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state")).expanduser()


def _default_config_dir() -> Path:
    return _xdg_config_home() / APP_NAME


def _default_state_dir() -> Path:
    return _xdg_state_home() / APP_NAME


def default_config_path() -> Path:
    return Path(os.environ.get("DEEPSEEK_PROXY_CONFIG", _default_config_dir() / "config.toml")).expanduser()


def _default_log_path(*, thinking: bool) -> Path:
    return _default_state_dir() / ("proxy-thinking.log" if thinking else "proxy.log")


def _port_for(thinking: bool, explicit_port: int | None = None) -> int:
    if explicit_port is not None:
        return int(explicit_port)
    env_name = "DEEPSEEK_PROXY_THINKING_PORT" if thinking else "DEEPSEEK_PROXY_PORT"
    env_value = os.environ.get(env_name)
    if env_value:
        return int(env_value)
    return DEFAULT_THINKING_PORT if thinking else DEFAULT_STABLE_PORT


def _base_url(*, thinking: bool, port: int | None = None) -> str:
    return f"http://{DEFAULT_HOST}:{_port_for(thinking, port)}"


def _http_json(url: str, *, timeout: float = 3.0) -> tuple[int | None, dict[str, Any] | None, str | None]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            try:
                return response.status, json.loads(raw), None
            except json.JSONDecodeError:
                return response.status, None, raw[:2000]
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(raw), None
        except json.JSONDecodeError:
            return exc.code, None, raw[:2000]
    except Exception as exc:
        return None, None, f"{type(exc).__name__}: {exc}"


def _tcp_port_open(host: str, port: int, *, timeout: float = 0.25) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _healthz_for_port(port: int, *, timeout: float = 1.0) -> tuple[int | None, dict[str, Any] | None, str | None]:
    return _http_json(f"http://{DEFAULT_HOST}:{port}/healthz", timeout=timeout)


def _version_from_healthz(data: dict[str, Any] | None) -> str | None:
    if not isinstance(data, dict):
        return None
    value = data.get("version")
    return str(value) if value is not None else None


def _write_default_config(path: Path, *, force: bool = False) -> bool:
    if path.exists() and not force:
        return False

    path.parent.mkdir(parents=True, exist_ok=True)
    state_dir = _default_state_dir()
    content = (
        f"# {APP_NAME} local configuration\n"
        "# Environment variables override these defaults where supported.\n\n"
        "[server]\n"
        f'host = "{DEFAULT_HOST}"\n'
        f"stable_port = {DEFAULT_STABLE_PORT}\n"
        f"thinking_port = {DEFAULT_THINKING_PORT}\n\n"
        "[deepseek]\n"
        'model = "deepseek-v4-pro"\n'
        "force_model = true\n"
        'base_url = "https://api.deepseek.com"\n'
        'api_key_env = "DEEPSEEK_API_KEY"\n\n'
        "[paths]\n"
        f'state_dir = "{state_dir}"\n\n'
        "[tool_bridge]\n"
        "enabled = true\n"
        "max_rounds = 6\n\n"
        "[agent_liveness]\n"
        "enabled = true\n"
        "max_retries = 2\n"
        "judge_enabled = true\n"
        'judge_model = "v4-flash-no-thinking"\n\n'
        "[context]\n"
        'compaction_policy = "adaptive"\n'
        "max_context_chars = 1500000\n"
        "min_target_chars = 350000\n"
        "max_target_chars = 750000\n"
        "min_new_chars = 250000\n"
        "min_turns = 4\n"
    )
    path.write_text(content, encoding="utf-8")
    return True


def default_codex_config_path() -> Path:
    return Path(os.environ.get("CODEX_CONFIG_FILE", Path.home() / ".codex" / "config.toml")).expanduser()


def _toml_quote(value: str) -> str:
    escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _toml_table_range(text: str, header: str) -> tuple[int, int] | None:
    lines = text.splitlines(keepends=True)
    offset = 0
    start = None
    for line in lines:
        if line.strip() == header:
            start = offset
            break
        offset += len(line)
    if start is None:
        return None

    end = len(text)
    offset = 0
    found = False
    for line in lines:
        line_start = offset
        offset += len(line)
        stripped = line.strip()
        if line_start <= start:
            if line_start == start:
                found = True
            continue
        if found and stripped.startswith("[") and stripped.endswith("]"):
            end = line_start
            break

    return start, end


def _remove_toml_table(text: str, header: str) -> tuple[str, bool]:
    table_range = _toml_table_range(text, header)
    if table_range is None:
        return text, False
    start, end = table_range
    new_text = text[:start].rstrip() + "\n\n" + text[end:].lstrip()
    return new_text, True


def _upsert_toml_table(text: str, header: str, block: str) -> tuple[str, bool]:
    removed_text, existed = _remove_toml_table(text, header)
    cleaned = removed_text.rstrip()
    if cleaned:
        return cleaned + "\n\n" + block.rstrip() + "\n", existed
    return block.rstrip() + "\n", existed


def _codex_profile_blocks(
    *,
    profile_name: str,
    provider_name: str,
    base_url: str,
    model: str,
    reasoning_effort: str,
    context_window: int,
    auto_compact_token_limit: int,
    tool_output_token_limit: int,
    model_catalog_json: str | None,
) -> tuple[str, str, str, str]:
    provider_header = f"[model_providers.{provider_name}]"
    profile_header = f"[profiles.{profile_name}]"

    provider_lines = [
        provider_header,
        'name = "DeepSeek Thinking Responses Proxy"' if "thinking" in profile_name else 'name = "DeepSeek Responses Proxy"',
        f"base_url = {_toml_quote(base_url)}",
        'env_key = "DEEPSEEK_API_KEY"',
        'wire_api = "responses"',
    ]

    profile_lines = [
        profile_header,
        f"model = {_toml_quote(model)}",
        f"model_provider = {_toml_quote(provider_name)}",
        f"model_context_window = {int(context_window)}",
        f"model_auto_compact_token_limit = {int(auto_compact_token_limit)}",
        f"tool_output_token_limit = {int(tool_output_token_limit)}",
        'model_reasoning_summary = "none"',
        "model_supports_reasoning_summaries = false",
        f"model_reasoning_effort = {_toml_quote(reasoning_effort)}",
    ]
    if model_catalog_json:
        profile_lines.append(f"model_catalog_json = {_toml_quote(model_catalog_json)}")

    return provider_header, "\n".join(provider_lines), profile_header, "\n".join(profile_lines)


def _install_codex_profile(args: argparse.Namespace) -> int:
    config_path = Path(args.path).expanduser() if args.path else default_codex_config_path()
    profile_name = args.name
    provider_name = args.provider_name or f"{profile_name}-proxy"

    provider_header, provider_block, profile_header, profile_block = _codex_profile_blocks(
        profile_name=profile_name,
        provider_name=provider_name,
        base_url=args.base_url,
        model=args.model,
        reasoning_effort=args.reasoning_effort,
        context_window=args.context_window,
        auto_compact_token_limit=args.auto_compact_token_limit,
        tool_output_token_limit=args.tool_output_token_limit,
        model_catalog_json=args.model_catalog_json,
    )

    original = config_path.read_text(encoding="utf-8") if config_path.exists() else ""
    text, provider_existed = _upsert_toml_table(original, provider_header, provider_block)
    text, profile_existed = _upsert_toml_table(text, profile_header, profile_block)

    result = {
        "path": str(config_path),
        "profile": profile_name,
        "provider": provider_name,
        "base_url": args.base_url,
        "model": args.model,
        "provider_existed": provider_existed,
        "profile_existed": profile_existed,
        "dry_run": bool(args.dry_run),
    }

    if args.dry_run:
        result["config_preview"] = text
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    config_path.parent.mkdir(parents=True, exist_ok=True)
    if config_path.exists() and not args.no_backup:
        backup = config_path.with_suffix(config_path.suffix + ".bak")
        backup.write_text(original, encoding="utf-8")
        result["backup"] = str(backup)

    config_path.write_text(text, encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _uninstall_codex_profile(args: argparse.Namespace) -> int:
    config_path = Path(args.path).expanduser() if args.path else default_codex_config_path()
    profile_name = args.name
    provider_name = args.provider_name or f"{profile_name}-proxy"
    provider_header = f"[model_providers.{provider_name}]"
    profile_header = f"[profiles.{profile_name}]"

    original = config_path.read_text(encoding="utf-8") if config_path.exists() else ""
    text, profile_removed = _remove_toml_table(original, profile_header)
    text, provider_removed = _remove_toml_table(text, provider_header)

    result = {
        "path": str(config_path),
        "profile": profile_name,
        "provider": provider_name,
        "profile_removed": profile_removed,
        "provider_removed": provider_removed,
        "dry_run": bool(args.dry_run),
    }

    if args.dry_run:
        result["config_preview"] = text
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if config_path.exists() and not args.no_backup:
        backup = config_path.with_suffix(config_path.suffix + ".bak")
        backup.write_text(original, encoding="utf-8")
        result["backup"] = str(backup)

    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(text, encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _read_pid(pid_path: Path) -> int | None:
    try:
        text = pid_path.read_text(encoding="utf-8").strip()
        return int(text) if text else None
    except Exception:
        return None


def _pid_alive(pid: int | None) -> bool:
    if pid is None:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _start_proxy(args: argparse.Namespace) -> int:
    thinking = bool(args.thinking)
    port = _port_for(thinking, args.port)
    state_dir = Path(args.state_dir).expanduser() if args.state_dir else _default_state_dir()
    state_dir.mkdir(parents=True, exist_ok=True)

    pid_path = Path(args.pid_file).expanduser() if args.pid_file else state_dir / ("proxy-thinking.pid" if thinking else "proxy.pid")
    log_path = Path(args.log_file).expanduser() if args.log_file else state_dir / ("proxy-thinking.log" if thinking else "proxy.log")
    db_path = Path(args.db_path).expanduser() if args.db_path else state_dir / ("responses-thinking.sqlite3" if thinking else "responses.sqlite3")

    existing_pid = _read_pid(pid_path)
    if _pid_alive(existing_pid):
        status, data, error = _healthz_for_port(port, timeout=1.0)
        running_version = _version_from_healthz(data)
        if status == 200 and running_version == PROXY_VERSION:
            print(f"already_running pid={existing_pid} port={port} version={running_version} pid_file={pid_path}")
            return 0
        print(
            json.dumps(
                {
                    "error": "pid_file_points_to_different_or_unhealthy_service",
                    "pid": existing_pid,
                    "port": port,
                    "expected_version": PROXY_VERSION,
                    "running_version": running_version,
                    "http_status": status,
                    "healthz_error": error,
                    "pid_file": str(pid_path),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1

    status, data, error = _healthz_for_port(port, timeout=1.0)
    running_version = _version_from_healthz(data)
    if status == 200:
        if running_version == PROXY_VERSION:
            print(f"already_running port={port} version={running_version}")
            return 0
        print(
            json.dumps(
                {
                    "error": "port_in_use_by_different_proxy_version",
                    "port": port,
                    "expected_version": PROXY_VERSION,
                    "running_version": running_version,
                    "hint": "Stop the old proxy process or choose another port.",
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1

    if _tcp_port_open(DEFAULT_HOST, port):
        print(
            json.dumps(
                {
                    "error": "port_in_use_by_unrecognized_service",
                    "port": port,
                    "expected_version": PROXY_VERSION,
                    "healthz_status": status,
                    "healthz_error": error,
                    "hint": "Stop the process that owns this port or choose another port.",
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1

    env = os.environ.copy()
    env.setdefault("NO_PROXY", "127.0.0.1,localhost,::1")
    env.setdefault("no_proxy", env["NO_PROXY"])
    env["DEEPSEEK_PROXY_DB_PATH"] = str(db_path)
    env["DEEPSEEK_PROXY_MODEL"] = env.get("DEEPSEEK_PROXY_MODEL", "deepseek-v4-pro")
    env["DEEPSEEK_PROXY_FORCE_MODEL"] = env.get("DEEPSEEK_PROXY_FORCE_MODEL", "1")
    env["DEEPSEEK_PROXY_TOOL_MAX_ROUNDS"] = env.get("DEEPSEEK_PROXY_TOOL_MAX_ROUNDS", "6")
    env["DEEPSEEK_PROXY_COMPACT_POLICY"] = env.get("DEEPSEEK_PROXY_COMPACT_POLICY", "adaptive")
    env["DEEPSEEK_PROXY_AGENT_LIVENESS_GUARD"] = env.get("DEEPSEEK_PROXY_AGENT_LIVENESS_GUARD", "1")
    env["DEEPSEEK_PROXY_AGENT_LIVENESS_JUDGE_ENABLED"] = env.get("DEEPSEEK_PROXY_AGENT_LIVENESS_JUDGE_ENABLED", "1")
    env["DEEPSEEK_PROXY_AGENT_LIVENESS_JUDGE_MODEL"] = env.get("DEEPSEEK_PROXY_AGENT_LIVENESS_JUDGE_MODEL", "v4-flash-no-thinking")
    env["DEEPSEEK_PROXY_CODEX_TOOL_PROTOCOL_INSTRUCTION"] = env.get("DEEPSEEK_PROXY_CODEX_TOOL_PROTOCOL_INSTRUCTION", "1")
    if thinking:
        env["DEEPSEEK_THINKING"] = "enabled"

    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "deepseek_responses_proxy.app:app",
        "--host",
        DEFAULT_HOST,
        "--port",
        str(port),
    ]

    log_handle = log_path.open("ab")
    process = subprocess.Popen(
        cmd,
        cwd=str(Path.cwd()),
        env=env,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    pid_path.write_text(str(process.pid), encoding="utf-8")

    print(f"started pid={process.pid} port={port}")
    print(f"log={log_path}")
    print(f"pid_file={pid_path}")
    print(f"db={db_path}")

    for _ in range(20):
        if process.poll() is not None:
            print(
                json.dumps(
                    {
                        "error": "process_exited_before_ready",
                        "exit_code": process.returncode,
                        "port": port,
                        "log": str(log_path),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 1

        status, data, _error = _healthz_for_port(port, timeout=1.0)
        running_version = _version_from_healthz(data)
        if status == 200 and running_version == PROXY_VERSION:
            print(f"ready version={running_version}")
            return 0
        if status == 200 and running_version and running_version != PROXY_VERSION:
            print(
                json.dumps(
                    {
                        "error": "ready_version_mismatch",
                        "port": port,
                        "expected_version": PROXY_VERSION,
                        "running_version": running_version,
                        "log": str(log_path),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 1
        time.sleep(0.25)

    print(
        json.dumps(
            {
                "error": "started_but_not_ready",
                "port": port,
                "expected_version": PROXY_VERSION,
                "log": str(log_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 1


def _stop_proxy(args: argparse.Namespace) -> int:
    thinking = bool(args.thinking)
    state_dir = Path(args.state_dir).expanduser() if args.state_dir else _default_state_dir()
    pid_path = Path(args.pid_file).expanduser() if args.pid_file else state_dir / ("proxy-thinking.pid" if thinking else "proxy.pid")

    pid = _read_pid(pid_path)
    if not pid:
        print(f"not_running pid_file={pid_path}")
        return 0

    if _pid_alive(pid):
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
        for _ in range(20):
            if not _pid_alive(pid):
                break
            time.sleep(0.1)

    if _pid_alive(pid):
        print(f"warning=still_running pid={pid}")

    try:
        pid_path.unlink()
    except FileNotFoundError:
        pass

    print(f"stopped pid={pid}")
    return 0


def _status(args: argparse.Namespace) -> int:
    thinking = bool(args.thinking)
    port = _port_for(thinking, args.port)
    url = f"{_base_url(thinking=thinking, port=port)}/v1/proxy/status"
    status, data, error = _http_json(url, timeout=args.timeout)

    if data is not None:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0 if status == 200 else 1

    print(json.dumps({"status": "error", "url": url, "http_status": status, "error": error}, ensure_ascii=False, indent=2))
    return 1


def _usage(args: argparse.Namespace) -> int:
    thinking = bool(args.thinking)
    port = _port_for(thinking, args.port)
    path = "/v1/proxy/usage/summary" if args.summary else "/v1/proxy/usage"
    params: list[str] = []
    if args.limit is not None and not args.summary:
        params.append(f"limit={int(args.limit)}")
    if args.purpose:
        params.append(f"purpose={args.purpose}")
    if args.model:
        params.append(f"model={args.model}")
    if args.thinking_filter is not None:
        params.append(f"thinking={str(args.thinking_filter).lower()}")

    query = ("?" + "&".join(params)) if params else ""
    status, data, error = _http_json(f"{_base_url(thinking=thinking, port=port)}{path}{query}", timeout=args.timeout)

    if data is not None:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0 if status == 200 else 1

    print(json.dumps({"status": "error", "http_status": status, "error": error}, ensure_ascii=False, indent=2))
    return 1


def _doctor(args: argparse.Namespace) -> int:
    thinking = bool(args.thinking)
    port = _port_for(thinking, args.port)
    config_path = default_config_path()
    state_dir = _default_state_dir()

    checks: dict[str, Any] = {
        "proxy_version": PROXY_VERSION,
        "python": sys.version.split()[0],
        "executable": sys.executable,
        "config_path": str(config_path),
        "config_exists": config_path.exists(),
        "state_dir": str(state_dir),
        "deepseek_api_key_configured": bool(os.environ.get("DEEPSEEK_API_KEY")),
        "target": "thinking" if thinking else "stable",
        "port": port,
    }

    health_status, health_data, health_error = _http_json(f"{_base_url(thinking=thinking, port=port)}/healthz", timeout=args.timeout)
    status_code, status_data, status_error = _http_json(f"{_base_url(thinking=thinking, port=port)}/v1/proxy/status", timeout=args.timeout)

    health_version = health_data.get("version") if isinstance(health_data, dict) else None
    proxy_version = status_data.get("version") if isinstance(status_data, dict) else None

    checks["healthz"] = {
        "ok": health_status == 200,
        "http_status": health_status,
        "version": health_version,
        "version_match": health_version == PROXY_VERSION,
        "error": health_error,
    }
    checks["proxy_status"] = {
        "ok": status_code == 200,
        "http_status": status_code,
        "version": proxy_version,
        "version_match": proxy_version == PROXY_VERSION,
        "store": status_data.get("store") if isinstance(status_data, dict) else None,
        "error": status_error,
    }

    ok = bool(
        checks["healthz"]["ok"]
        and checks["proxy_status"]["ok"]
        and checks["healthz"]["version_match"]
        and checks["proxy_status"]["version_match"]
    )
    checks["ok"] = ok
    print(json.dumps(checks, ensure_ascii=False, indent=2))
    return 0 if ok or args.allow_down else 1


def _logs(args: argparse.Namespace) -> int:
    thinking = bool(args.thinking)
    log_path = Path(args.log_file).expanduser() if args.log_file else _default_log_path(thinking=thinking)
    if not log_path.exists():
        print(f"log_missing path={log_path}")
        return 1

    lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    for line in lines[-int(args.lines) :]:
        print(line)
    return 0


def _config(args: argparse.Namespace) -> int:
    path = Path(args.path).expanduser() if args.path else default_config_path()

    if args.config_command == "path":
        print(path)
        return 0

    if args.config_command == "init":
        changed = _write_default_config(path, force=args.force)
        print(json.dumps({"path": str(path), "created_or_overwritten": changed}, ensure_ascii=False, indent=2))
        return 0

    raise SystemExit("unknown config command")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dsproxy", description="DeepSeek Responses Proxy command line tools")
    parser.add_argument("--version", action="store_true", help="print proxy version and exit")

    sub = parser.add_subparsers(dest="command")

    start = sub.add_parser("start", help="start the local proxy")
    start.add_argument("--thinking", action="store_true", help="start thinking proxy on port 8001")
    start.add_argument("--port", type=int)
    start.add_argument("--state-dir")
    start.add_argument("--pid-file")
    start.add_argument("--log-file")
    start.add_argument("--db-path")
    start.set_defaults(func=_start_proxy)

    stop = sub.add_parser("stop", help="stop the local proxy")
    stop.add_argument("--thinking", action="store_true")
    stop.add_argument("--state-dir")
    stop.add_argument("--pid-file")
    stop.set_defaults(func=_stop_proxy)

    status = sub.add_parser("status", help="print /v1/proxy/status")
    status.add_argument("--thinking", action="store_true")
    status.add_argument("--port", type=int)
    status.add_argument("--timeout", type=float, default=3.0)
    status.set_defaults(func=_status)

    doctor = sub.add_parser("doctor", help="diagnose local proxy setup")
    doctor.add_argument("--thinking", action="store_true")
    doctor.add_argument("--port", type=int)
    doctor.add_argument("--timeout", type=float, default=3.0)
    doctor.add_argument("--allow-down", action="store_true", help="exit 0 even when proxy is not running")
    doctor.set_defaults(func=_doctor)

    logs = sub.add_parser("logs", help="print recent proxy logs")
    logs.add_argument("--thinking", action="store_true")
    logs.add_argument("--log-file")
    logs.add_argument("--lines", type=int, default=120)
    logs.set_defaults(func=_logs)

    usage = sub.add_parser("usage", help="print usage ledger")
    usage.add_argument("--thinking", action="store_true")
    usage.add_argument("--port", type=int)
    usage.add_argument("--timeout", type=float, default=3.0)
    usage.add_argument("--summary", action="store_true")
    usage.add_argument("--limit", type=int, default=20)
    usage.add_argument("--purpose")
    usage.add_argument("--model")
    usage.add_argument("--thinking-filter", choices=["true", "false"])
    usage.set_defaults(func=_usage)

    config = sub.add_parser("config", help="manage local config")
    config_sub = config.add_subparsers(dest="config_command", required=True)

    config_path = config_sub.add_parser("path", help="print config path")
    config_path.add_argument("--path")
    config_path.set_defaults(func=_config)

    config_init = config_sub.add_parser("init", help="write default config")
    config_init.add_argument("--path")
    config_init.add_argument("--force", action="store_true")
    config_init.set_defaults(func=_config)

    install_profile = sub.add_parser("install-codex-profile", help="install a Codex config profile")
    install_profile.add_argument("--name", default="deepseek-thinking")
    install_profile.add_argument("--path")
    install_profile.add_argument("--provider-name")
    install_profile.add_argument("--base-url", default="http://127.0.0.1:8001/v1")
    install_profile.add_argument("--model", default="deepseek-v4-pro")
    install_profile.add_argument("--reasoning-effort", default="xhigh")
    install_profile.add_argument("--context-window", type=int, default=1_000_000)
    install_profile.add_argument("--auto-compact-token-limit", type=int, default=750_000)
    install_profile.add_argument("--tool-output-token-limit", type=int, default=12_000)
    install_profile.add_argument("--model-catalog-json")
    install_profile.add_argument("--dry-run", action="store_true")
    install_profile.add_argument("--no-backup", action="store_true")
    install_profile.set_defaults(func=_install_codex_profile)

    uninstall_profile = sub.add_parser("uninstall-codex-profile", help="remove a Codex config profile")
    uninstall_profile.add_argument("--name", default="deepseek-thinking")
    uninstall_profile.add_argument("--path")
    uninstall_profile.add_argument("--provider-name")
    uninstall_profile.add_argument("--dry-run", action="store_true")
    uninstall_profile.add_argument("--no-backup", action="store_true")
    uninstall_profile.set_defaults(func=_uninstall_codex_profile)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.version:
        print(PROXY_VERSION)
        return 0

    if getattr(args, "thinking_filter", None) is not None:
        args.thinking_filter = args.thinking_filter == "true"

    if not hasattr(args, "func"):
        parser.print_help()
        return 0

    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
