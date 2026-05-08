from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_MCP_PROTOCOL_VERSION = os.environ.get(
    "DEEPSEEK_PROXY_MCP_PROTOCOL_VERSION",
    "2025-03-26",
)


@dataclass(frozen=True)
class StdioMCPServerConfig:
    name: str
    command: str
    args: list[str]
    env_vars: list[str]
    env: dict[str, str]
    startup_timeout_sec: float
    tool_timeout_sec: float


def _coerce_float(value: Any, default: float) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    if result <= 0:
        return default
    return result


def mcp_server_config_from_snapshot(server_name: str, server_snapshot: dict[str, Any]) -> StdioMCPServerConfig:
    return StdioMCPServerConfig(
        name=str(server_name),
        command=str(server_snapshot.get("command") or ""),
        args=[
            str(item)
            for item in server_snapshot.get("args", [])
            if isinstance(item, (str, int, float, bool))
        ],
        env_vars=[
            str(item)
            for item in server_snapshot.get("env_vars", [])
            if isinstance(item, (str, int, float, bool))
        ],
        env={
            str(key): str(value)
            for key, value in (server_snapshot.get("env") or {}).items()
            if isinstance(key, str)
        } if isinstance(server_snapshot.get("env"), dict) else {},
        startup_timeout_sec=_coerce_float(server_snapshot.get("startup_timeout_sec"), 20.0),
        tool_timeout_sec=_coerce_float(server_snapshot.get("tool_timeout_sec"), 120.0),
    )


def build_mcp_process_env(config: StdioMCPServerConfig) -> dict[str, str]:
    env: dict[str, str] = {}

    for key in ["PATH", "HOME", "LANG", "LC_ALL"]:
        value = os.environ.get(key)
        if value:
            env[key] = value

    for key in config.env_vars:
        value = os.environ.get(key)
        if value is not None:
            env[key] = value

    env.update(config.env)
    return env


async def _write_jsonrpc(proc: asyncio.subprocess.Process, payload: dict[str, Any]) -> None:
    if proc.stdin is None:
        raise RuntimeError("stdio MCP process has no stdin")
    line = json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"
    proc.stdin.write(line.encode("utf-8"))
    await proc.stdin.drain()


async def _read_jsonrpc_response(
    proc: asyncio.subprocess.Process,
    *,
    expected_id: int,
    timeout_sec: float,
) -> dict[str, Any]:
    if proc.stdout is None:
        raise RuntimeError("stdio MCP process has no stdout")

    while True:
        raw = await asyncio.wait_for(proc.stdout.readline(), timeout=timeout_sec)
        if not raw:
            raise RuntimeError("stdio MCP process closed stdout before response")

        try:
            message = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            continue

        if message.get("id") != expected_id:
            continue

        if "error" in message:
            raise RuntimeError(json.dumps(message["error"], ensure_ascii=False))

        if "result" not in message:
            raise RuntimeError("JSON-RPC response missing result")

        return message


async def _terminate_process(proc: asyncio.subprocess.Process) -> None:
    if proc.returncode is not None:
        return

    proc.terminate()
    try:
        await asyncio.wait_for(proc.wait(), timeout=2.0)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()


async def discover_stdio_mcp_tools(
    config: StdioMCPServerConfig,
    *,
    client_name: str = "deepseek-responses-proxy",
    client_version: str = "unknown",
    protocol_version: str = DEFAULT_MCP_PROTOCOL_VERSION,
) -> dict[str, Any]:
    if not config.command:
        return {
            "ok": False,
            "server": config.name,
            "error": "missing_mcp_command",
            "tools": [],
        }

    command_path = Path(config.command).expanduser()
    if not command_path.exists():
        return {
            "ok": False,
            "server": config.name,
            "error": "mcp_command_not_found",
            "command": str(command_path),
            "tools": [],
        }

    proc: asyncio.subprocess.Process | None = None
    try:
        proc = await asyncio.create_subprocess_exec(
            str(command_path),
            *config.args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=build_mcp_process_env(config),
        )

        initialize_id = 1
        await _write_jsonrpc(
            proc,
            {
                "jsonrpc": "2.0",
                "id": initialize_id,
                "method": "initialize",
                "params": {
                    "protocolVersion": protocol_version,
                    "capabilities": {},
                    "clientInfo": {
                        "name": client_name,
                        "version": client_version,
                    },
                },
            },
        )
        initialize_response = await _read_jsonrpc_response(
            proc,
            expected_id=initialize_id,
            timeout_sec=config.startup_timeout_sec,
        )

        await _write_jsonrpc(
            proc,
            {
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
                "params": {},
            },
        )

        tools_id = 2
        await _write_jsonrpc(
            proc,
            {
                "jsonrpc": "2.0",
                "id": tools_id,
                "method": "tools/list",
                "params": {},
            },
        )
        tools_response = await _read_jsonrpc_response(
            proc,
            expected_id=tools_id,
            timeout_sec=config.tool_timeout_sec,
        )

        tools_result = tools_response.get("result") or {}
        tools = tools_result.get("tools") or []
        if not isinstance(tools, list):
            tools = []

        normalized_tools: list[dict[str, Any]] = []
        for tool in tools:
            if not isinstance(tool, dict):
                continue
            normalized_tools.append(
                {
                    "name": str(tool.get("name") or ""),
                    "description": str(tool.get("description") or ""),
                    "inputSchema": tool.get("inputSchema") if isinstance(tool.get("inputSchema"), dict) else {},
                }
            )

        return {
            "ok": True,
            "server": config.name,
            "protocol_version": protocol_version,
            "initialize": initialize_response.get("result") or {},
            "tool_count": len(normalized_tools),
            "tools": normalized_tools,
        }
    except Exception as exc:
        return {
            "ok": False,
            "server": config.name,
            "error": "mcp_discovery_failed",
            "message": str(exc),
            "tools": [],
        }
    finally:
        if proc is not None:
            await _terminate_process(proc)
