from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import signal
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import urllib.parse
import zipfile
from pathlib import Path
from typing import Any

from .app import DEFAULT_MODEL, PROXY_INTERNAL_COMMIT, PROXY_INTERNAL_VERSION, PROXY_PUBLIC_COMMIT, PROXY_PUBLIC_VERSION, PROXY_VERSION, _refresh_deepseek_pricing_from_official_docs, _weclaw_context_used_tokens_unavailable_contract, _weclaw_diagnostics_contract, _weclaw_model_catalog_contract, _weclaw_pricing_contract, _profile_tokenizer_contract


APP_NAME = "deepseek-responses-proxy"

DEFAULT_CONTEXT_WINDOW_TOKENS = 1_000_000
DEFAULT_AUTO_COMPACT_RATIO = 0.90
MANAGED_AUTO_COMPACT_RATIO = DEFAULT_AUTO_COMPACT_RATIO
AUTO_COMPACT_RATIO_TOLERANCE = 0.000001
AUTO_COMPACT_RATIO_ENV_NAMES = ("DEEPSEEK_PROXY_AUTO_COMPACT_RATIO", "CODEEPSEEDEX_AUTO_COMPACT_RATIO")



def _normalize_auto_compact_ratio(value: object, default: float = DEFAULT_AUTO_COMPACT_RATIO) -> float:
    try:
        ratio = float(value)
    except (TypeError, ValueError):
        return default
    if not 0 < ratio < 1:
        return default
    return ratio



def _auto_compact_ratio_from_env_values(
    env_values: dict[str, str] | None = None,
    *,
    explicit: object | None = None,
) -> float:
    """Return the managed ratio for profile generation/repair.

    Managed CoDeepSeedeX profiles use 0.90 unless the caller passes an
    explicit --auto-compact-ratio argument for a deliberate one-shot repair.
    Environment variables are ignored here so stale low-trigger experiments do
    not silently redefine the managed profile contract.
    """
    if explicit is not None:
        return _normalize_auto_compact_ratio(explicit)
    return DEFAULT_AUTO_COMPACT_RATIO

def _derive_auto_compact_token_limit(
    context_window: int,
    ratio: float = DEFAULT_AUTO_COMPACT_RATIO,
) -> int:
    try:
        context_tokens = int(context_window)
    except (TypeError, ValueError):
        context_tokens = 0
    if context_tokens <= 0:
        return 0
    safe_ratio = _normalize_auto_compact_ratio(ratio)
    return max(1, int(context_tokens * safe_ratio))





def _auto_compact_policy_contract(
    *,
    model_context_window: int,
    auto_compact_token_limit: int,
    expected_ratio: float | None = None,
) -> dict[str, object]:
    expected_ratio = _normalize_auto_compact_ratio(
        expected_ratio if expected_ratio is not None else _auto_compact_ratio_from_env_values()
    )
    expected_percent = int(round(expected_ratio * 100))
    expected_threshold = int(model_context_window * expected_ratio) if model_context_window > 0 else None
    observed_ratio = (
        round(auto_compact_token_limit / model_context_window, 6)
        if model_context_window > 0 and auto_compact_token_limit > 0
        else None
    )
    observed_percent = int(round(float(observed_ratio) * 100)) if observed_ratio is not None else None
    compliant = bool(expected_threshold is not None and auto_compact_token_limit == expected_threshold)
    if observed_ratio is not None:
        compliant = compliant or abs(float(observed_ratio) - expected_ratio) <= AUTO_COMPACT_RATIO_TOLERANCE
    if model_context_window <= 0 or auto_compact_token_limit <= 0:
        status = "unavailable"
        reason = "model_context_window_or_auto_compact_threshold_missing"
        action = "repair or reinstall the managed Codex profile so both model_context_window and the ratio-derived model_auto_compact_token_limit are present"
        needs_migration = True
        display_label = "auto-compact unavailable"
        short_action = "repair profile"
    elif compliant:
        status = "managed_expected_ratio"
        reason = None
        action = None
        needs_migration = False
        display_label = f"managed {expected_percent}%"
        short_action = "ok"
    else:
        status = "legacy_or_custom_profile_needs_migration"
        reason = "observed_auto_compact_ratio_differs_from_managed_ratio"
        action = f"run dsproxy profile repair --managed-only --json or reinstall the managed Codex profile to derive model_auto_compact_token_limit from auto_compact_ratio={expected_ratio:.6g}"
        needs_migration = True
        display_label = (
            f"legacy {observed_percent}%→{expected_percent}%"
            if observed_percent is not None
            else f"legacy profile→{expected_percent}%"
        )
        short_action = "repair profile"
    return {
        "available": model_context_window > 0 and auto_compact_token_limit > 0,
        "unit": "tokens",
        "managed_expected_auto_compact_ratio": expected_ratio,
        "managed_expected_auto_compact_threshold_tokens": expected_threshold,
        "observed_auto_compact_ratio": observed_ratio,
        "observed_auto_compact_threshold_tokens": auto_compact_token_limit or None,
        "compliant_with_managed_ratio": compliant,
        "needs_migration": needs_migration,
        "status": status,
        "reason": reason,
        "action": action,
        "display_label": display_label,
        "short_action": short_action,
        "source": "codex_profile.model_context_window_and_ratio_derived_model_auto_compact_token_limit",
    }

def _repo_root_for_version_metadata() -> Path:
    return Path(__file__).resolve().parents[1]


def _git_version_value(args: list[str], *, fallback: str) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=_repo_root_for_version_metadata(),
            text=True,
            capture_output=True,
            timeout=2.0,
        )
    except Exception:
        return fallback
    value = result.stdout.strip()
    if result.returncode != 0 or not value:
        return fallback
    return value.splitlines()[0].strip() or fallback


def _git_internal_tag_for_head(*, fallback: str) -> str:
    try:
        result = subprocess.run(
            ["git", "tag", "--points-at", "HEAD", "--list", "p*"],
            cwd=_repo_root_for_version_metadata(),
            text=True,
            capture_output=True,
            timeout=2.0,
        )
    except Exception:
        return fallback
    if result.returncode != 0:
        return fallback
    tags = sorted(line.strip() for line in result.stdout.splitlines() if line.strip().startswith("p"))
    return tags[-1] if tags else fallback


def _git_commit_for_ref(ref: str) -> str:
    """Return a short commit for a local git ref, such as a public release tag."""
    if not ref:
        return ""
    try:
        import subprocess
        from pathlib import Path

        root = Path(__file__).resolve().parents[1]
        proc = subprocess.run(
            ["git", "rev-parse", "--short", f"{ref}^{{commit}}"],
            cwd=str(root),
            text=True,
            capture_output=True,
            timeout=2,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout.strip()
    except Exception:
        return ""
    return ""


def _runtime_git_head() -> str:
    """Return the current checkout HEAD when running from a git tree."""
    try:
        import subprocess
        from pathlib import Path

        root = Path(__file__).resolve().parents[1]
        proc = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(root),
            text=True,
            capture_output=True,
            timeout=2,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout.strip()
    except Exception:
        return ""
    return ""


def _version_metadata() -> dict[str, str]:
    import importlib

    proxy_app = importlib.import_module("deepseek_responses_proxy.app")

    public_version = str(
        getattr(proxy_app, "PROXY_PUBLIC_VERSION", getattr(proxy_app, "PROXY_VERSION", "unknown"))
    ).strip()
    runtime_head = _runtime_git_head()

    public_commit = (
        _git_commit_for_ref(public_version)
        or str(getattr(proxy_app, "PROXY_PUBLIC_COMMIT", "")).strip()
        or runtime_head
        or "unknown"
    )

    declared_internal_version = str(PROXY_INTERNAL_VERSION).strip()
    internal_version = declared_internal_version or "unknown"
    internal_commit = (
        runtime_head
        or str(getattr(proxy_app, "PROXY_INTERNAL_COMMIT", "")).strip()
        or "unknown"
    )

    return {
        "public_version": public_version or "unknown",
        "public_commit": public_commit,
        "internal_version": internal_version or "unknown",
        "internal_commit": internal_commit,
    }


def _format_version_metadata(metadata: dict[str, str] | None = None) -> str:
    data = metadata or _version_metadata()
    return "\n".join(
        [
            f"public version: {data['public_version']} | {data['public_commit']}",
            f"internal version: {data['internal_version']} | {data['internal_commit']}",
        ]
    )

DEFAULT_HOST = "127.0.0.1"
DEFAULT_STABLE_PORT = 8000
DEFAULT_THINKING_PORT = 8001


MODEL_API_PROVIDER_ALIASES = {
    "deepseek": "deepseek",
    "kimi": "kimi",
    "moonshot": "kimi",

    # Backward-compatible aliases. The public guide should prefer explicit
    # site and plan names below instead of the ambiguous glm/qwen shortcuts.
    "glm": "zai",
    "qwen": "qwen_singapore",
    "dashscope": "qwen_singapore",

    "zai": "zai",
    "z_ai": "zai",
    "z.ai": "zai",
    "zai_general": "zai",
    "zai_coding": "zai_coding",
    "z.ai_coding": "zai_coding",

    "zhipu": "zhipu",
    "zhipuai": "zhipu",
    "bigmodel": "zhipu",
    "zhipu_domestic": "zhipu",
    "bigmodel_domestic": "zhipu",
    "zhipu_coding": "zhipu_coding",
    "bigmodel_coding": "zhipu_coding",

    "qwen_beijing": "qwen_beijing",
    "qwen_cn": "qwen_beijing",
    "dashscope_beijing": "qwen_beijing",
    "qwen_singapore": "qwen_singapore",
    "qwen_intl": "qwen_singapore",
    "dashscope_singapore": "qwen_singapore",
    "qwen_us": "qwen_us",
    "qwen_us_virginia": "qwen_us",
    "dashscope_us": "qwen_us",

    "custom": "custom",
    "other": "custom",
    "openai_compatible": "custom",
    "openai-compatible": "custom",
}

MODEL_API_PROVIDERS = {
    "deepseek": {
        "display_name": "DeepSeek",
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-v4-pro",
        "validation_path": "/user/balance",
    },
    "kimi": {
        "display_name": "Kimi / Moonshot",
        "base_url": "https://api.moonshot.ai/v1",
        "model": "kimi-latest",
        "validation_path": "/models",
    },
    "zhipu": {
        "display_name": "Zhipu / BigModel domestic general",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "model": "glm-5.1",
        "validation_path": "/models",
    },
    "zhipu_coding": {
        "display_name": "Zhipu / BigModel domestic Coding Plan",
        "base_url": "https://open.bigmodel.cn/api/coding/paas/v4",
        "model": "glm-5.1",
        "validation_path": "/models",
    },
    "zai": {
        "display_name": "Z.AI international general",
        "base_url": "https://api.z.ai/api/paas/v4",
        "model": "glm-5.1",
        "validation_path": "/models",
    },
    "zai_coding": {
        "display_name": "Z.AI international Coding Plan",
        "base_url": "https://api.z.ai/api/coding/paas/v4",
        "model": "glm-4.7",
        "validation_path": "/models",
    },
    "qwen_beijing": {
        "display_name": "Qwen / DashScope Beijing pay-as-you-go",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-plus",
        "validation_path": "/models",
    },
    "qwen_singapore": {
        "display_name": "Qwen / DashScope Singapore pay-as-you-go",
        "base_url": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-plus",
        "validation_path": "/models",
    },
    "qwen_us": {
        "display_name": "Qwen / DashScope US Virginia pay-as-you-go",
        "base_url": "https://dashscope-us.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-plus-us",
        "validation_path": "/models",
    },
}


def _canonical_model_api_provider(provider: str | None) -> str:
    selected = str(provider or "deepseek").strip().lower().replace(" ", "_").replace("-", "_")
    return MODEL_API_PROVIDER_ALIASES.get(selected, selected)


def _model_api_provider_config(provider: str | None) -> dict[str, str]:
    canonical = _canonical_model_api_provider(provider)
    if canonical == "custom":
        return {
            "display_name": "Other OpenAI-compatible server",
            "base_url": "",
            "model": "",
            "validation_path": "/models",
        }
    if canonical not in MODEL_API_PROVIDERS:
        raise ValueError(f"unsupported_model_api_provider:{canonical}")
    return dict(MODEL_API_PROVIDERS[canonical])


def _supported_model_api_providers() -> list[str]:
    return ["deepseek", "kimi", "zhipu", "zhipu-coding", "zai", "zai-coding", "qwen-beijing", "qwen-singapore", "qwen-us", "custom"]


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


def default_env_file_path() -> Path:
    return Path(os.environ.get("DEEPSEEK_PROXY_ENV_FILE", _default_config_dir() / "env")).expanduser()


def _shell_quote(value: str) -> str:
    return shlex.quote(str(value))


def _read_env_exports(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line.startswith("export "):
            continue
        body = line[len("export ") :]
        if "=" not in body:
            continue
        key, value = body.split("=", 1)
        key = key.strip()
        value = value.strip()
        try:
            parsed = shlex.split(value)
            values[key] = parsed[0] if parsed else ''
        except ValueError:
            values[key] = value.strip("'\"")
    return values


def _write_env_exports(path: Path, values: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered_keys = [
        "DEEPSEEK_API_KEY",
        "DEEPSEEK_BASE_URL",
        "DEEPSEEK_PROXY_MODEL_PROVIDER",
        "DEEPSEEK_PROXY_PORT",
        "DEEPSEEK_PROXY_THINKING_PORT",
        "DEEPSEEK_PROXY_MODEL",
        "DEEPSEEK_REASONING_EFFORT",
        "DEEPSEEK_PROXY_FORCE_MODEL",
        "DEEPSEEK_PROXY_TOOL_MAX_ROUNDS",
        "DEEPSEEK_PROXY_COMPACT_POLICY",
        "DEEPSEEK_PROXY_AGENT_LIVENESS_GUARD",
        "DEEPSEEK_PROXY_AGENT_LIVENESS_JUDGE_ENABLED",
        "DEEPSEEK_PROXY_AGENT_LIVENESS_JUDGE_MODEL",
        "DEEPSEEK_PROXY_CODEX_TOOL_PROTOCOL_INSTRUCTION",
        "DEEPSEEK_PROXY_WEB_SEARCH_PROVIDER",
        "DEEPSEEK_PROXY_WEB_SEARCH_ROUTING",
        "DEEPSEEK_PROXY_IMAGE_PROVIDER",
        "DEEPSEEK_PROXY_IMAGE_GENERATION_ROUTING",
    ]
    lines = ["# deepseek-responses-proxy local environment", "# Generated by dsproxy"]
    for key in ordered_keys:
        if key in values:
            lines.append(f"export {key}={_shell_quote(values[key])}")
    for key in sorted(values):
        if key not in ordered_keys:
            lines.append(f"export {key}={_shell_quote(values[key])}")
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass

def _default_log_path(*, thinking: bool) -> Path:
    return _default_state_dir() / ("proxy-thinking.log" if thinking else "proxy.log")


def _port_for(thinking: bool, explicit_port: int | None = None) -> int:
    if explicit_port is not None:
        return int(explicit_port)
    env_name = "DEEPSEEK_PROXY_THINKING_PORT" if thinking else "DEEPSEEK_PROXY_PORT"
    env_value = os.environ.get(env_name)
    if not env_value:
        env_value = _read_env_exports(default_env_file_path()).get(env_name)
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
        "[model_api]\n"
        'provider = "deepseek"\n'
        'base_url = "https://api.deepseek.com"\n'
        'model = "deepseek-v4-pro"\n\n'
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
        "max_target_chars = 900000\n"
        "min_new_chars = 250000\n"
        "min_turns = 4\n"
    )
    path.write_text(content, encoding="utf-8")
    return True


def default_codex_config_path() -> Path:
    return Path(os.environ.get("CODEX_CONFIG_FILE", Path.home() / ".codex" / "config.toml")).expanduser()


def codex_profile_config_path(profile_name: str, codex_config: Path | None = None) -> Path:
    """Return the Codex 0.134+ split profile file path.

    Codex 0.134+ loads the main ~/.codex/config.toml first, then overlays
    ~/.codex/<profile>.config.toml for --profile <profile>. CoDeepSeedeX keeps
    provider blocks in the main config and writes managed profile bodies to
    these split profile files.
    """
    main_path = (codex_config or default_codex_config_path()).expanduser()
    return main_path.parent / f"{profile_name}.config.toml"


def codex_profile_layout_contract(layout: str = "split_profile_files", codex_cli_version: str | None = None) -> dict[str, object]:
    if layout == "legacy_profile_tables":
        payload: dict[str, object] = {
            "name": "legacy_profile_tables",
            "codex_cli_max_version_exclusive": "0.134.0",
            "main_config_contains": ["model_providers", "profiles"],
            "profile_config_contains": [],
            "legacy_profile_tables_allowed": True,
            "legacy_profile_selector_allowed": False,
        }
    else:
        payload = {
            "name": "split_profile_files",
            "codex_cli_min_version": "0.134.0",
            "main_config_contains": ["model_providers"],
            "profile_config_contains": ["profile_body"],
            "legacy_profile_tables_allowed": False,
            "legacy_profile_selector_allowed": False,
        }
    if codex_cli_version:
        payload["codex_cli_version"] = codex_cli_version
    return payload


def _parse_codex_cli_version_text(text: str) -> tuple[int, int, int] | None:
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", text or "")
    if not match:
        return None
    return tuple(int(part) for part in match.groups())


def _detect_codex_cli_version_text() -> str:
    override = os.environ.get("CODEEPSEEDEX_CODEX_CLI_VERSION", "").strip()
    if override:
        return override
    try:
        cp = subprocess.run(
            ["codex", "--version"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=10,
        )
    except Exception:
        return ""
    return (cp.stdout or "").strip()


def _resolve_codex_profile_layout(requested: str | None = None) -> dict[str, object]:
    requested = (requested or os.environ.get("CODEEPSEEDEX_CODEX_PROFILE_LAYOUT") or "auto").strip()
    codex_cli_version_text = _detect_codex_cli_version_text()
    parsed = _parse_codex_cli_version_text(codex_cli_version_text)
    if requested in {"split", "split_profile_files"}:
        return {
            "name": "split_profile_files",
            "requested": requested,
            "codex_cli_version": codex_cli_version_text,
            "reason": "explicit_split_profile_files",
        }
    if requested in {"legacy", "legacy_profile_tables"}:
        return {
            "name": "legacy_profile_tables",
            "requested": requested,
            "codex_cli_version": codex_cli_version_text,
            "reason": "explicit_legacy_profile_tables",
        }
    if parsed is not None and parsed < (0, 134, 0):
        return {
            "name": "legacy_profile_tables",
            "requested": requested,
            "codex_cli_version": codex_cli_version_text,
            "reason": "codex_cli_lt_0_134",
        }
    if parsed is not None:
        return {
            "name": "split_profile_files",
            "requested": requested,
            "codex_cli_version": codex_cli_version_text,
            "reason": "codex_cli_gte_0_134_or_unknown",
        }
    return {
        "name": "legacy_profile_tables",
        "requested": requested,
        "codex_cli_version": codex_cli_version_text,
        "reason": "codex_cli_unknown_default_legacy",
    }

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


def _parse_simple_toml_key_values_from_text(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    current_section: str | None = None
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if re.match(r"^\[[^\]]+\]\s*$", stripped):
            current_section = stripped
            continue
        if current_section is not None or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip()
        if value.startswith('"') and value.endswith('"'):
            value = value[1:-1].replace('\\"', '"').replace("\\\\", "\\")
        else:
            value = value.split("#", 1)[0].strip()
        values[key] = value
    return values


def _render_simple_toml_key_values(values: dict[str, object]) -> str:
    order = [
        "model",
        "model_provider",
        "model_context_window",
        "model_auto_compact_token_limit",
        "tool_output_token_limit",
        "model_reasoning_summary",
        "model_supports_reasoning_summaries",
        "model_reasoning_effort",
        "plan_mode_reasoning_effort",
        "model_catalog_json",
    ]
    lines: list[str] = []
    emitted: set[str] = set()
    for key in order + sorted(k for k in values if k not in order):
        if key in emitted or key not in values:
            continue
        value = values.get(key)
        if value is None:
            continue
        emitted.add(key)
        if isinstance(value, bool):
            rendered = "true" if value else "false"
        elif isinstance(value, int):
            rendered = str(value)
        else:
            text = str(value)
            if text.lower() in {"true", "false"} and key == "model_supports_reasoning_summaries":
                rendered = text.lower()
            elif re.fullmatch(r"-?\d+", text) and key in {"model_context_window", "model_auto_compact_token_limit", "tool_output_token_limit"}:
                rendered = text
            else:
                rendered = _toml_quote(text)
        lines.append(f"{key} = {rendered}")
    return "\n".join(lines).rstrip() + "\n"


def _remove_top_level_codex_profile_selector(text: str) -> tuple[str, bool]:
    changed = False
    current_section: str | None = None
    out: list[str] = []
    for raw_line in text.splitlines(keepends=True):
        stripped = raw_line.strip()
        if re.match(r"^\[[^\]]+\]\s*$", stripped):
            current_section = stripped
            out.append(raw_line)
            continue
        if current_section is None and re.match(r'^profile\s*=\s*"(deepseek|deepseek-thinking)"\s*(#.*)?$', stripped):
            changed = True
            continue
        out.append(raw_line)
    return "".join(out), changed


def _cleanup_main_codex_config_for_profile(text: str, profile_name: str) -> tuple[str, dict[str, bool]]:
    cleaned, legacy_table_removed = _remove_toml_table(text, f"[profiles.{profile_name}]")
    cleaned, legacy_selector_removed = _remove_top_level_codex_profile_selector(cleaned)
    return cleaned, {
        "legacy_profile_table_removed": legacy_table_removed,
        "legacy_profile_selector_removed": legacy_selector_removed,
    }


def _legacy_profile_values_from_main_config(config_path: Path, profile_name: str) -> dict[str, str]:
    sections = _parse_simple_toml_sections(config_path)
    return dict(sections.get(f"profiles.{profile_name}", {}))


def _read_codex_profile_values(config_path: Path, profile_name: str) -> tuple[dict[str, str], str, Path]:
    profile_path = codex_profile_config_path(profile_name, config_path)
    if profile_path.exists():
        return _parse_simple_toml_key_values_from_text(
            profile_path.read_text(encoding="utf-8", errors="replace")
        ), "split_profile_file", profile_path
    legacy = _legacy_profile_values_from_main_config(config_path, profile_name)
    if legacy:
        return legacy, "legacy_profile_table", profile_path
    return {}, "missing", profile_path


def _write_codex_profile_values(config_path: Path, profile_name: str, values: dict[str, object]) -> Path:
    profile_path = codex_profile_config_path(profile_name, config_path)
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_text(_render_simple_toml_key_values(values), encoding="utf-8")
    return profile_path


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
    # Codex 0.134+ profile bodies are written to ~/.codex/<profile>.config.toml
    # and must not include a [profiles.<name>] table header.
    profile_header = ""

    provider_defaults = _managed_profile_provider_defaults(profile_name) or {}
    provider_label = provider_defaults.get("provider_label") or (
        "DeepSeek Thinking Responses Proxy" if "thinking" in profile_name else "DeepSeek Responses Proxy"
    )
    provider_lines = [
        provider_header,
        f"name = {_toml_quote(provider_label)}",
        f"base_url = {_toml_quote(base_url)}",
        'env_key = "DEEPSEEK_API_KEY"',
        'wire_api = "responses"',
    ]

    profile_values: dict[str, object] = {
        "model": model,
        "model_provider": provider_name,
        "model_context_window": int(context_window),
        "model_auto_compact_token_limit": int(auto_compact_token_limit),
        "tool_output_token_limit": int(tool_output_token_limit),
        "model_reasoning_summary": "none",
        "model_supports_reasoning_summaries": False,
        "model_reasoning_effort": reasoning_effort,
        "plan_mode_reasoning_effort": "high",
    }
    if model_catalog_json:
        profile_values["model_catalog_json"] = model_catalog_json

    return provider_header, "\n".join(provider_lines), profile_header, _render_simple_toml_key_values(profile_values)


def _install_codex_profile(args: argparse.Namespace) -> int:
    config_path = Path(args.path).expanduser() if args.path else default_codex_config_path()
    profile_name = args.name
    profile_path = codex_profile_config_path(profile_name, config_path)
    layout_info = _resolve_codex_profile_layout(getattr(args, "profile_layout", "auto"))
    layout_name = str(layout_info["name"])
    provider_name = args.provider_name or f"{profile_name}-proxy"
    auto_compact_ratio = _auto_compact_ratio_from_env_values(explicit=getattr(args, "auto_compact_ratio", None))
    derived_auto_compact_token_limit = _derive_auto_compact_token_limit(args.context_window, auto_compact_ratio)
    legacy_auto_compact_token_limit = getattr(args, "auto_compact_token_limit", None)

    provider_header, provider_block, _profile_header, profile_block = _codex_profile_blocks(
        profile_name=profile_name,
        provider_name=provider_name,
        base_url=args.base_url,
        model=args.model,
        reasoning_effort=args.reasoning_effort,
        context_window=args.context_window,
        auto_compact_token_limit=derived_auto_compact_token_limit,
        tool_output_token_limit=args.tool_output_token_limit,
        model_catalog_json=args.model_catalog_json,
    )

    original = config_path.read_text(encoding="utf-8") if config_path.exists() else ""
    text, provider_existed = _upsert_toml_table(original, provider_header, provider_block)
    if layout_name == "legacy_profile_tables":
        text, legacy_selector_removed = _remove_top_level_codex_profile_selector(text)
        profile_header = f"[profiles.{profile_name}]"
        text, legacy_profile_existed = _remove_toml_table(text, profile_header)
        legacy_profile_block = profile_header + "\n" + profile_block.strip() + "\n"
        text = text.rstrip() + "\n\n" + legacy_profile_block
        cleanup = {
            "legacy_profile_table_removed": False,
            "legacy_profile_selector_removed": legacy_selector_removed,
        }
        profile_existed = legacy_profile_existed or profile_path.exists()
    else:
        text, cleanup = _cleanup_main_codex_config_for_profile(text, profile_name)
        profile_existed = profile_path.exists() or cleanup["legacy_profile_table_removed"]

    result = {
        "path": str(config_path),
        "codex_profile_layout": layout_name,
        "layout_contract": codex_profile_layout_contract(layout_name, str(layout_info.get("codex_cli_version") or "")),
        "codex_cli_version": layout_info.get("codex_cli_version"),
        "layout_reason": layout_info.get("reason"),
        "main_config": str(config_path),
        "profile_config": str(config_path if layout_name == "legacy_profile_tables" else profile_path),
        "split_profile_config": str(profile_path),
        "profile": profile_name,
        "provider": provider_name,
        "base_url": args.base_url,
        "model": args.model,
        "provider_existed": provider_existed,
        "profile_existed": profile_existed,
        "legacy_profile_table_removed": cleanup["legacy_profile_table_removed"],
        "legacy_profile_selector_removed": cleanup["legacy_profile_selector_removed"],
        "dry_run": bool(args.dry_run),
        "context_window_tokens": int(args.context_window),
        "auto_compact_ratio": auto_compact_ratio,
        "auto_compact_token_limit": derived_auto_compact_token_limit,
        "auto_compact_token_limit_source": "derived_from_context_window_tokens_and_auto_compact_ratio",
    }
    if legacy_auto_compact_token_limit is not None:
        result["ignored_legacy_auto_compact_token_limit"] = int(legacy_auto_compact_token_limit)
        result["ignored_legacy_auto_compact_token_limit_reason"] = "managed profiles derive the threshold from auto_compact_ratio"

    if args.dry_run:
        result["config_preview"] = text
        result["profile_config_preview"] = profile_block
        if layout_name == "legacy_profile_tables":
            result["legacy_config_preview"] = text
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    config_path.parent.mkdir(parents=True, exist_ok=True)
    if (config_path.exists() or profile_path.exists()) and not args.no_backup:
        backup = config_path.with_suffix(config_path.suffix + ".bak")
        backup.write_text(original, encoding="utf-8")
        result["backup"] = str(backup)
        if profile_path.exists():
            profile_backup = profile_path.with_suffix(profile_path.suffix + ".bak")
            profile_backup.write_text(profile_path.read_text(encoding="utf-8"), encoding="utf-8")
            result["profile_backup"] = str(profile_backup)

    config_path.write_text(text, encoding="utf-8")
    if layout_name == "legacy_profile_tables":
        if profile_path.exists():
            profile_path.unlink()
    else:
        profile_path.parent.mkdir(parents=True, exist_ok=True)
        profile_path.write_text(profile_block, encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0

def _canonical_cli_reasoning_effort(value: object) -> str | None:
    normalized = str(value or "").strip().lower()
    if not normalized:
        return None
    if normalized in {"none", "minimal", "low", "medium", "high"}:
        return "high"
    if normalized in {"xhigh", "max"}:
        return "max"
    return None


CODEX_MODEL_REASONING_EFFORT_ALLOWED = {"none", "minimal", "low", "medium", "high", "xhigh"}
CODEEPSEEDEX_LEGACY_CODEX_PROFILES = ("deepseek",)
CODEEPSEEDEX_MANAGED_CODEX_PROFILES = ("deepseek-thinking",)
CODEEPSEEDEX_PRIMARY_CODEX_PROFILE = "deepseek-thinking"
CODEEPSEEDEX_PROFILE_CONTRACT_VERSION = 2


def _managed_profile_provider_defaults(profile_name: str) -> dict[str, str] | None:
    if profile_name == "deepseek":
        return {
            "provider_name": "deepseek-proxy",
            "provider_label": "DeepSeek Responses Proxy",
            "base_url": "http://127.0.0.1:8000/v1",
        }
    if profile_name == "deepseek-thinking":
        return {
            "provider_name": "deepseek-thinking-proxy",
            "provider_label": "DeepSeek Thinking Responses Proxy",
            "base_url": "http://127.0.0.1:8001/v1",
        }
    return None


def _codex_model_reasoning_effort_for_deepseek(deepseek_effort: str) -> str:
    if deepseek_effort == "max":
        return "xhigh"
    return "high"


def _custom_provider_capabilities(entry: dict[str, Any] | None) -> dict[str, Any]:
    capabilities = entry.get("capabilities") if isinstance(entry, dict) else None
    if not isinstance(capabilities, dict):
        capabilities = {}
    reasoning = capabilities.get("reasoning_effort")
    if isinstance(reasoning, str):
        reasoning_values = [reasoning]
    elif isinstance(reasoning, list):
        reasoning_values = [str(item).strip().lower() for item in reasoning if str(item).strip()]
    else:
        reasoning_values = []
    return {
        **capabilities,
        "reasoning_effort": reasoning_values or ["high"],
        "reasoning_effort_max": bool(capabilities.get("reasoning_effort_max")) or "max" in reasoning_values or "xhigh" in reasoning_values,
    }


def _custom_provider_supports_reasoning_effort_max(entry: dict[str, Any] | None) -> bool:
    return bool(_custom_provider_capabilities(entry).get("reasoning_effort_max"))


def _custom_provider_effective_reasoning_effort(
    entry: dict[str, Any] | None,
    env_values: dict[str, str] | None,
    *,
    requested: str | None = None,
) -> tuple[str, dict[str, Any]]:
    env_values = env_values or {}
    requested_raw = requested or env_values.get("DEEPSEEK_REASONING_EFFORT") or "high"
    requested_effort = _canonical_cli_reasoning_effort(requested_raw) or "high"
    supports_max = _custom_provider_supports_reasoning_effort_max(entry)
    if requested_effort == "max" and not supports_max:
        return "high", {
            "requested_deepseek_reasoning_effort": "max",
            "effective_deepseek_reasoning_effort": "high",
            "codex_model_reasoning_effort": "high",
            "reasoning_effort_max_supported": False,
            "capability_downgraded": True,
            "reason": "custom_provider_reasoning_effort_max_not_declared",
            "action": "Declare provider capabilities.reasoning_effort_max=true only after validating that the upstream endpoint supports max reasoning effort.",
        }
    return requested_effort, {
        "requested_deepseek_reasoning_effort": requested_effort,
        "effective_deepseek_reasoning_effort": requested_effort,
        "codex_model_reasoning_effort": "xhigh" if requested_effort == "max" else "high",
        "reasoning_effort_max_supported": supports_max,
        "capability_downgraded": False,
        "reason": None,
        "action": None,
    }


def _codex_model_reasoning_effort_for_custom_provider(deepseek_effort: str, entry: dict[str, Any] | None) -> str:
    if deepseek_effort == "max" and _custom_provider_supports_reasoning_effort_max(entry):
        return "xhigh"
    return "high"


def _reasoning_effort_contract(value: object) -> dict[str, object] | None:
    requested = str(value or "").strip().lower()
    deepseek_effort = _canonical_cli_reasoning_effort(requested)
    if deepseek_effort is None:
        return None
    codex_effort = _codex_model_reasoning_effort_for_deepseek(deepseek_effort)
    return {
        "requested_effort": str(value),
        "user_facing": "max" if deepseek_effort == "max" else "high",
        "deepseek_reasoning_effort": deepseek_effort,
        "codex_model_reasoning_effort": codex_effort,
        "normalized": requested != deepseek_effort or codex_effort != deepseek_effort,
        "compatibility_note": (
            "low/medium/minimal are accepted compatibility inputs and normalize to DeepSeek high; "
            "xhigh is accepted as Codex-compatible input and normalizes to DeepSeek max while Codex profile stores xhigh."
        ),
    }


def _managed_profile_targets(profile_value: object) -> list[str]:
    raw = str(profile_value or "").strip()
    if raw in {"", "__managed__", "managed", "all", "all-managed"}:
        return list(CODEEPSEEDEX_MANAGED_CODEX_PROFILES)
    return [raw]



def _patch_codex_profile_value(config_path: Path, profile_name: str, key: str, value: str) -> bool:
    values, source, profile_path = _read_codex_profile_values(config_path, profile_name)
    changed = values.get(key) != str(value)
    values[key] = str(value)
    _write_codex_profile_values(config_path, profile_name, values)

    original = config_path.read_text(encoding="utf-8") if config_path.exists() else ""
    cleaned, cleanup = _cleanup_main_codex_config_for_profile(original, profile_name)
    if cleanup["legacy_profile_table_removed"] or cleanup["legacy_profile_selector_removed"]:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(cleaned, encoding="utf-8")
        changed = True
    return changed or source != "split_profile_file"




def _sync_managed_codex_profile_models_from_env(
    *,
    env_file: Path,
    codex_path: Path,
    profile_value: object = "__managed__",
) -> dict[str, object]:
    env_values = _read_env_exports(env_file)
    target_profiles = _managed_profile_targets(profile_value)
    profile_results: list[dict[str, object]] = []
    updated_profiles: list[str] = []

    for profile_name in target_profiles:
        model_value, model_source = _managed_profile_env_model_for_profile(profile_name, env_values)
        if not model_value:
            profile_results.append({
                "profile": profile_name,
                "status": "skipped",
                "reason": "env_model_missing",
                "model_source": model_source,
                "profile_config": str(codex_profile_config_path(profile_name, codex_path)),
            })
            continue
        patched = _patch_codex_profile_value(codex_path, profile_name, "model", model_value)
        if patched:
            updated_profiles.append(profile_name)
        profile_results.append({
            "profile": profile_name,
            "status": "ok",
            "model": model_value,
            "model_source": model_source,
            "profile_config": str(codex_profile_config_path(profile_name, codex_path)),
            "model_patched": patched,
        })

    return {
        "status": "ok" if any(item.get("status") == "ok" for item in profile_results) else "skipped",
        "env_file": str(env_file),
        "codex_config": str(codex_path),
        "codex_profile": str(profile_value or "__managed__"),
        "target_profiles": target_profiles,
        "updated_profiles": updated_profiles,
        "codex_profiles": target_profiles,
        "codex_profile_results": profile_results,
        "codex_profile_patched": bool(updated_profiles),
        "codex_profile_config": str(codex_profile_config_path(target_profiles[0], codex_path)) if target_profiles else None,
        "codex_profile_configs": [str(codex_profile_config_path(name, codex_path)) for name in target_profiles],
    }

def _parse_simple_toml_sections_from_text(text: str) -> dict[str, dict[str, str]]:
    sections: dict[str, dict[str, str]] = {}
    current: str | None = None
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = re.match(r"^\[([^\]]+)\]\s*$", stripped)
        if match:
            current = match.group(1).strip()
            sections.setdefault(current, {})
            continue
        if current and "=" in stripped:
            key, value = stripped.split("=", 1)
            key = key.strip()
            value = value.strip()
            if value.startswith('"') and value.endswith('"'):
                value = value[1:-1].replace('\\"', '"').replace("\\\\", "\\")
            else:
                value = value.split("#", 1)[0].strip()
            sections[current][key] = value
    return sections


def _parse_simple_toml_sections(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    return _parse_simple_toml_sections_from_text(
        path.read_text(encoding="utf-8", errors="replace")
    )



def _codex_config_health(config_path: Path) -> dict[str, object]:
    sections = _parse_simple_toml_sections(config_path)
    invalid_fields: list[dict[str, object]] = []
    warnings: list[str] = []
    legacy_profile_tables = sorted(
        section.removeprefix("profiles.")
        for section in sections
        if section.startswith("profiles.")
    )
    legacy_profile_selectors: list[str] = []

    if config_path.exists():
        current_section: str | None = None
        for raw_line in config_path.read_text(encoding="utf-8", errors="replace").splitlines():
            stripped = raw_line.strip()
            if re.match(r"^\[[^\]]+\]\s*$", stripped):
                current_section = stripped
                continue
            if current_section is None:
                match = re.match(r'^profile\s*=\s*"([^"]+)"', stripped)
                if match and match.group(1) in CODEEPSEEDEX_MANAGED_CODEX_PROFILES:
                    legacy_profile_selectors.append(match.group(1))
    else:
        warnings.append("codex_config_missing")

    for profile_name in CODEEPSEEDEX_MANAGED_CODEX_PROFILES:
        values, source, profile_path = _read_codex_profile_values(config_path, profile_name)
        effort = values.get("model_reasoning_effort")
        if effort is not None and effort not in CODEX_MODEL_REASONING_EFFORT_ALLOWED:
            invalid_fields.append({
                "profile": profile_name,
                "field": "model_reasoning_effort",
                "value": effort,
                "source": source,
                "profile_config": str(config_path if source == "legacy_profile_table" else profile_path),
                "allowed": sorted(CODEX_MODEL_REASONING_EFFORT_ALLOWED),
                "suggested_repair_command": f"dsproxy profile set-effort {profile_name} max --json",
            })
    if legacy_profile_tables:
        warnings.append("legacy_profile_tables_present")
    if legacy_profile_selectors:
        warnings.append("legacy_profile_selector_present")

    layout = "legacy_profile_tables" if legacy_profile_tables else "split_profile_files"
    return {
        "codex_config": str(config_path),
        "codex_profile_layout": layout,
        "layout_contract": codex_profile_layout_contract(layout),
        "codex_config_exists": config_path.exists(),
        "codex_config_loadable": not invalid_fields and not legacy_profile_selectors,
        "legacy_profile_tables_present": bool(legacy_profile_tables),
        "legacy_profile_tables": legacy_profile_tables,
        "legacy_profile_selectors_present": bool(legacy_profile_selectors),
        "legacy_profile_selectors": legacy_profile_selectors,
        "invalid_profile_fields": invalid_fields,
        "warnings": warnings,
    }

def _env_value_truthy(value: object) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "enabled"}


def _int_or_zero(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _managed_profile_env_model_for_profile(profile_name: str | None, env_values: dict[str, str]) -> tuple[str | None, str]:
    env_model = env_values.get("DEEPSEEK_PROXY_MODEL") or env_values.get("DEEPSEEK_MODEL")
    if profile_name == "deepseek-thinking":
        thinking_model = env_values.get("DEEPSEEK_PROXY_THINKING_MODEL") or env_values.get("DEEPSEEK_THINKING_MODEL")
        if thinking_model:
            return thinking_model, "dsproxy_env.DEEPSEEK_PROXY_THINKING_MODEL"
    if env_model:
        return env_model, "dsproxy_env.DEEPSEEK_PROXY_MODEL"
    return None, "unknown"


def _profile_model_contract(profile_section: dict[str, str], env_values: dict[str, str], *, profile_name: str | None = None) -> dict[str, object]:
    codex_model = profile_section.get("model")
    env_model, env_model_source = _managed_profile_env_model_for_profile(profile_name, env_values)
    force_model_enabled = _env_value_truthy(
        env_values.get("DEEPSEEK_PROXY_FORCE_MODEL", os.environ.get("DEEPSEEK_PROXY_FORCE_MODEL"))
    )

    if force_model_enabled and env_model:
        effective_model = env_model
        source = f"{env_model_source}_forced"
    elif codex_model:
        effective_model = codex_model
        source = "codex_profile.model"
    elif env_model:
        effective_model = env_model
        source = env_model_source
    else:
        effective_model = "unknown"
        source = "unknown"

    upstream_model = effective_model if effective_model != "unknown" else env_model
    model_conflict = bool(codex_model and effective_model and codex_model != effective_model)
    diagnostic_hint = (
        "Codex profile model differs from forced upstream model; dsproxy effective_model is authoritative."
        if model_conflict
        else None
    )

    return {
        "provider": env_values.get("DEEPSEEK_PROXY_MODEL_PROVIDER") or "deepseek",
        "model": effective_model,
        "display_model": effective_model,
        "weclaw_display_model": effective_model,
        "requested_model": codex_model,
        "codex_model": codex_model,
        "upstream_model": upstream_model,
        "effective_model": effective_model,
        "force_model_enabled": force_model_enabled,
        "model_conflict": model_conflict,
        "display_hint": None,
        "diagnostic_hint": diagnostic_hint,
        "user_visible": False,
        "source": source,
        "notes": (
            [
                "Codex profile model differs from the effective upstream model. Managed CoDeepSeedeX profile repair must rewrite the Codex-visible model before launch."
            ]
            if model_conflict
            else []
        ),
        "profile_contract_version": CODEEPSEEDEX_PROFILE_CONTRACT_VERSION,
        "managed_profile_contract": {
            "available": True,
            "status": "conflict" if model_conflict else "ok",
            "fail_closed_recommended": bool(model_conflict),
            "repair_command": "dsproxy profile repair --managed-only --json" if model_conflict else None,
            "reason": "codex_profile_model_differs_from_effective_upstream_model" if model_conflict else None,
            "future_compatibility_policy": "repair managed profile before launching Codex; fail closed if conflict remains after repair",
        },
    }



def _profile_context_contract(profile_section: dict[str, str], *, effective_model: str | None = None, env_values: dict[str, str] | None = None) -> dict[str, object]:
    model_context_window = _int_or_zero(profile_section.get("model_context_window")) or DEFAULT_CONTEXT_WINDOW_TOKENS
    legacy_auto_compact_token_limit = _int_or_zero(profile_section.get("model_auto_compact_token_limit"))
    managed_auto_compact_ratio = _auto_compact_ratio_from_env_values(env_values)
    auto_compact_token_limit = _derive_auto_compact_token_limit(model_context_window, managed_auto_compact_ratio)
    display_limit_tokens = model_context_window or auto_compact_token_limit or 0
    auto_compact_ratio = round(auto_compact_token_limit / model_context_window, 6) if model_context_window > 0 and auto_compact_token_limit > 0 else None
    model_catalog = _weclaw_model_catalog_contract(profile_section, effective_model)
    auto_compact_policy = _auto_compact_policy_contract(
        model_context_window=model_context_window,
        auto_compact_token_limit=auto_compact_token_limit,
        expected_ratio=managed_auto_compact_ratio,
    )
    conflicts: list[dict[str, object]] = []
    catalog_context = model_catalog.get("context_window_tokens") if isinstance(model_catalog, dict) else None
    if (
        isinstance(catalog_context, int)
        and catalog_context > 0
        and model_context_window > 0
        and catalog_context != model_context_window
    ):
        conflicts.append(
            {
                "field": "model_context_window_tokens",
                "codex_profile_value": model_context_window,
                "model_catalog_value": catalog_context,
                "resolution": "codex_profile_model_context_window_remains_display_source",
                "user_visible": False,
            }
        )
    if legacy_auto_compact_token_limit and legacy_auto_compact_token_limit != auto_compact_token_limit:
        conflicts.append(
            {
                "field": "model_auto_compact_token_limit",
                "codex_profile_value": legacy_auto_compact_token_limit,
                "derived_managed_value": auto_compact_token_limit,
                "expected_auto_compact_ratio": managed_auto_compact_ratio,
                "resolution": "managed_runtime_uses_ratio_derived_threshold_and_profile_repair_rewrites_generated_value",
                "action": "run dsproxy profile repair --managed-only --json",
                "user_visible": True,
            }
        )

    display_source = "codex_profile.model_context_window" if model_context_window > 0 else "managed_auto_compact_ratio"
    return {
        "display_limit_tokens": display_limit_tokens,
        "model_context_window_tokens": model_context_window,
        "auto_compact_token_limit": auto_compact_token_limit,
        "auto_compact_threshold_tokens": auto_compact_token_limit,
        "model_auto_compact_token_limit": auto_compact_token_limit,
        "auto_compact_ratio": auto_compact_ratio,
        "auto_compact_policy": auto_compact_policy,
        "legacy_absolute_limit_ignored": (
            {
                "ignored_value": legacy_auto_compact_token_limit,
                "derived_value": auto_compact_token_limit,
                "reason": "managed_profiles_derive_auto_compact_threshold_from_ratio_only",
                "action": "run dsproxy profile repair --managed-only --json",
            }
            if legacy_auto_compact_token_limit and legacy_auto_compact_token_limit != auto_compact_token_limit
            else None
        ),
        "effective_safe_window_tokens": display_limit_tokens,
        **_weclaw_context_used_tokens_unavailable_contract(),
        "source": display_source,
        "is_estimated": False,
        "codex_profile": {
            "model_context_window_tokens": model_context_window,
            "auto_compact_token_limit": auto_compact_token_limit,
            "auto_compact_threshold_tokens": auto_compact_token_limit,
            "model_auto_compact_token_limit": auto_compact_token_limit,
            "auto_compact_ratio": auto_compact_ratio,
            "auto_compact_policy": auto_compact_policy,
            "unit": "tokens",
            "source": "codex_split_profile_file",
        },
        "model_catalog": model_catalog,
        "runtime": {
            "available": False,
            "unit": "tokens",
            "source": "not_queried",
        },
        "effective_display": {
            "limit_tokens": display_limit_tokens,
            "source": display_source,
            "is_estimated": False,
        },
        "conflicts": conflicts,
        "notes": [
            "Codex profile values are token-level declarations.",
            "The displayed context denominator is model_context_window_tokens, while model_auto_compact_token_limit is the ratio-derived auto-compact trigger threshold.",
            "Managed CoDeepSeedeX profiles use auto_compact_ratio as the only configuration source for auto-compact threshold.",
            "Runtime Compact and Trim status must remain token-only in external status contracts.",
        ],
    }

def _merge_runtime_context_contract(context_window: dict[str, object], runtime_status: dict[str, object] | None) -> dict[str, object]:
    merged = dict(context_window)
    if not isinstance(runtime_status, dict):
        merged["runtime"] = {
            "available": False,
            "unit": "tokens",
            "source": "http_status_unavailable",
        }
        return merged

    runtime_context = runtime_status.get("context")
    semantic_compaction = runtime_status.get("semantic_compaction")
    if not isinstance(runtime_context, dict):
        runtime_context = {}

    merged["runtime"] = {
        "available": bool(runtime_context),
        "unit": "tokens",
        "source": "dsproxy_runtime./v1/proxy/status.context",
        "context": runtime_context,
        "semantic_compaction": semantic_compaction if isinstance(semantic_compaction, dict) else None,
    }
    merged["runtime_compaction"] = runtime_context.get("compaction") if isinstance(runtime_context, dict) else None
    merged["runtime_trimming"] = runtime_context.get("trimming") if isinstance(runtime_context, dict) else None
    return merged


def _manifest_path_from_args(args: argparse.Namespace) -> Path:
    explicit = getattr(args, "manifest", None)
    if explicit:
        return Path(explicit).expanduser()
    return default_env_file_path().parent / "install-manifest.env"


def _read_manifest_exports(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        key = key.strip()
        raw_value = raw_value.strip()
        try:
            parsed = shlex.split(raw_value)
            value = parsed[0] if parsed else ""
        except ValueError:
            value = raw_value.strip('"').strip("'")
        values[key] = value
    return values


def _shell_quote(value: object) -> str:
    return shlex.quote(str(value or ""))



def _is_codeepseedex_codex_wrapper_path(path: str | Path) -> bool:
    candidate = Path(path).expanduser()
    try:
        resolved = candidate.resolve(strict=False)
    except Exception:
        resolved = candidate
    resolved_text = str(resolved)
    if resolved_text.startswith("/tmp/codeepseedex-") and resolved.name == "codex":
        return True
    if not candidate.exists() or not candidate.is_file():
        return False
    try:
        text = candidate.read_text(encoding="utf-8", errors="replace")[:20000]
    except Exception:
        return False
    return any(
        marker in text
        for marker in (
            "CoDeepSeedeX codex wrapper",
            "CODEEPSEEDEX_DSPROXY",
            "start_dsproxy_profile",
            "deepseek-responses-proxy",
        )
    )


def _is_tmp_codeepseedex_codex_path(path: Path) -> bool:
    try:
        resolved = path.expanduser().resolve(strict=False)
    except Exception:
        resolved = path.expanduser()
    resolved_text = str(resolved)
    return resolved.name == "codex" and (
        resolved_text.startswith("/tmp/codeepseedex-")
        or "/tmp/codeepseedex-" in resolved_text
    )


def _is_safe_real_codex_executable(candidate: Path, wrapper_path: Path) -> tuple[bool, str, Path]:
    candidate = candidate.expanduser()
    try:
        candidate_resolved = candidate.resolve(strict=False)
    except Exception:
        candidate_resolved = candidate
    try:
        wrapper_resolved = wrapper_path.expanduser().resolve(strict=False)
    except Exception:
        wrapper_resolved = wrapper_path.expanduser()

    if not candidate.exists() or not candidate.is_file():
        return False, "real_codex_missing", candidate_resolved
    if candidate_resolved == wrapper_resolved:
        return False, "real_codex_points_to_wrapper_itself", candidate_resolved
    if _is_tmp_codeepseedex_codex_path(candidate_resolved):
        return False, "real_codex_points_to_tmp_codeepseedex_wrapper", candidate_resolved
    if _is_codeepseedex_codex_wrapper_path(candidate_resolved):
        return False, "real_codex_points_to_codeepseedex_wrapper", candidate_resolved
    if not os.access(candidate_resolved, os.X_OK):
        return False, "real_codex_not_executable", candidate_resolved

    try:
        cp = subprocess.run(
            [str(candidate_resolved), "--version"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=5,
        )
        version_text = (cp.stdout or "").strip()
    except Exception:
        version_text = ""

    if version_text and ("codex-cli" in version_text or "OpenAI Codex" in version_text):
        return True, "ok", candidate_resolved
    if candidate_resolved.name == "codex":
        return True, "ok_name_only", candidate_resolved
    return False, "real_codex_version_unrecognized", candidate_resolved


def _iter_real_codex_candidate_paths(preferred: str, wrapper_path: Path) -> list[tuple[str, Path]]:
    candidates: list[tuple[str, Path]] = []
    seen: set[str] = set()

    def add(source: str, value: str | Path | None) -> None:
        if not value:
            return
        candidate = Path(value).expanduser()
        try:
            key = str(candidate.resolve(strict=False))
        except Exception:
            key = str(candidate)
        if key in seen:
            return
        seen.add(key)
        candidates.append((source, candidate))

    add("manifest", preferred)
    add("env_CODEEPSEEDEX_REAL_CODEX", os.environ.get("CODEEPSEEDEX_REAL_CODEX"))

    for item in os.environ.get("PATH", "").split(os.pathsep):
        if item:
            add("PATH", Path(item) / "codex")

    home = Path.home()
    add("home_npm_global", home / ".npm-global" / "bin" / "codex")
    add("home_local_share_npm", home / ".local" / "share" / "npm" / "bin" / "codex")
    add("home_node_modules", home / ".node_modules" / "bin" / "codex")

    nvm_root = home / ".nvm" / "versions" / "node"
    if nvm_root.exists():
        for candidate in sorted(nvm_root.glob("*/bin/codex"), reverse=True):
            add("home_nvm", candidate)

    add("usr_local_bin", Path("/usr/local/bin/codex"))
    add("usr_bin", Path("/usr/bin/codex"))
    return candidates


def _find_safe_real_codex_executable(preferred: str, wrapper_path: Path) -> tuple[Path | None, dict[str, object]]:
    attempts: list[dict[str, object]] = []
    for source, candidate in _iter_real_codex_candidate_paths(preferred, wrapper_path):
        ok, reason, resolved = _is_safe_real_codex_executable(candidate, wrapper_path)
        attempts.append({
            "source": source,
            "candidate": str(candidate),
            "resolved": str(resolved),
            "ok": ok,
            "reason": reason,
        })
        if ok:
            return resolved, {
                "source": source,
                "attempts": attempts,
                "recovered": source != "manifest" or str(resolved) != str(Path(preferred).expanduser()),
            }
    return None, {"source": None, "attempts": attempts, "recovered": False}

def _write_managed_codex_wrapper_from_manifest(args: argparse.Namespace) -> dict[str, object]:
    manifest_path = _manifest_path_from_args(args)
    values = _read_manifest_exports(manifest_path)
    wrapper_path = Path(values.get("CODEX_WRAPPER_PATH") or (Path.home() / ".local" / "bin" / "codex")).expanduser()
    backup_path = values.get("CODEX_WRAPPER_BACKUP", "")
    real_codex = values.get("REAL_CODEX", "")
    env_file = values.get("ENV_FILE") or str(default_env_file_path())
    install_dir = values.get("INSTALL_DIR") or str(Path.home() / ".local" / "share" / "deepseek-responses-proxy")
    bin_dir = values.get("BIN_DIR") or str(wrapper_path.parent)

    result: dict[str, object] = {
        "status": "ok",
        "manifest": str(manifest_path),
        "wrapper_path": str(wrapper_path),
        "real_codex": real_codex,
        "env_file": env_file,
        "install_dir": install_dir,
        "bin_dir": bin_dir,
        "refreshed": False,
        "backup": None,
    }

    if not real_codex:
        result.update({"status": "error", "error": "manifest_missing_REAL_CODEX"})
        return result

    real_resolved, resolution = _find_safe_real_codex_executable(real_codex, wrapper_path)
    result["real_codex_resolution"] = resolution
    result["real_codex_recovered"] = bool(resolution.get("recovered"))

    if real_resolved is None:
        manifest_attempt = next(
            (
                item for item in resolution.get("attempts", [])
                if isinstance(item, dict) and item.get("source") == "manifest"
            ),
            {},
        )
        error = str(manifest_attempt.get("reason") or "real_codex_missing")
        if error in {"real_codex_points_to_wrapper_itself", "real_codex_points_to_tmp_codeepseedex_wrapper"}:
            error = "real_codex_points_to_codeepseedex_wrapper"
        result.update({
            "status": "error",
            "error": error,
            "hint": "Refusing to refresh a wrapper without a safe real Codex binary. Install Codex CLI, clean PATH, or set CODEEPSEEDEX_REAL_CODEX to the real Codex binary.",
        })
        return result

    existing = wrapper_path.read_text(encoding="utf-8", errors="replace") if wrapper_path.exists() else ""
    is_managed = "CoDeepSeedeX codex wrapper" in existing
    if wrapper_path.exists() and not is_managed and not bool(getattr(args, "force", False)):
        result.update({
            "status": "error",
            "error": "unknown_existing_codex_wrapper",
            "hint": "Refusing to overwrite a non-CoDeepSeedeX codex command without --force.",
        })
        return result

    if wrapper_path.exists() and not is_managed:
        backup = wrapper_path.with_name(wrapper_path.name + f".codeepseedex.bak.{int(time.time())}")
        shutil.move(str(wrapper_path), str(backup))
        backup_path = str(backup)
        result["backup"] = backup_path

    title_emojis = '"✨" "💞" "🐦‍🔥" "🔥" "❄️" "💫" "🌈" "⚡" "🌀" "🚀" "🍁" "🍒" "🧬" "🪄" "💎" "🦞" "🐋" "😻"'
    wrapper_template = r"""#!/usr/bin/env bash
# CoDeepSeedeX codex wrapper
set -euo pipefail

REAL_CODEX=__REAL_CODEX__
DSPROXY="${CODEEPSEEDEX_DSPROXY:-__BIN_DIR__/dsproxy}"
if [ ! -x "$DSPROXY" ] && [ -x "__INSTALL_DIR__/.venv/bin/dsproxy" ]; then
  DSPROXY="__INSTALL_DIR__/.venv/bin/dsproxy"
fi
ENV_FILE="${DEEPSEEK_PROXY_ENV_FILE:-__ENV_FILE__}"

if [ -f "$ENV_FILE" ]; then
  source "$ENV_FILE"
fi

profile=""
prev=""
for arg in "$@"; do
  if [ "$prev" = "--profile" ] || [ "$prev" = "-p" ]; then
    profile="$arg"
    break
  fi
  case "$arg" in
    --profile=*) profile="${arg#--profile=}"; break ;;
    -p*) profile="${arg#-p}"; break ;;
  esac
  prev="$arg"
done

set_codeepseedex_terminal_title() {
  if [ ! -w /dev/tty ] && [ ! -t 1 ]; then
    return 0
  fi
  case "${TERM:-}" in
    ""|dumb)
      return 0
      ;;
  esac

  local title="${CODEEPSEEDEX_TERMINAL_TITLE:-}"
  if [ -z "$title" ]; then
    local emojis=(__TITLE_EMOJIS__)
    local idx=$((RANDOM % ${#emojis[@]}))
    title="${emojis[$idx]}CoDeepSeedeX"
    CODEEPSEEDEX_TERMINAL_TITLE="$title"
  fi

  if [ -w /dev/tty ]; then
    printf '\033]0;%s\007\033]2;%s\007' "$title" "$title" > /dev/tty 2>/dev/null || true
  else
    printf '\033]0;%s\007\033]2;%s\007' "$title" "$title" 2>/dev/null || true
  fi
}

CODEEPSEEDEX_TITLE_KEEPER_PID=""

schedule_codeepseedex_terminal_title_refresh() {
  if [ ! -w /dev/tty ] && [ ! -t 1 ]; then
    return 0
  fi
  case "${TERM:-}" in
    ""|dumb)
      return 0
      ;;
  esac

  (
    i=1
    max_seconds="${CODEEPSEEDEX_TITLE_KEEPER_SECONDS:-60}"
    interval_seconds="${CODEEPSEEDEX_TITLE_KEEPER_INTERVAL_SECONDS:-1}"
    while [ "$i" -le "$max_seconds" ]; do
      sleep "$interval_seconds"
      set_codeepseedex_terminal_title
      i=$((i + interval_seconds))
    done
  ) >/dev/null 2>&1 &
  CODEEPSEEDEX_TITLE_KEEPER_PID="$!"
}

stop_codeepseedex_terminal_title_keeper() {
  if [ -n "${CODEEPSEEDEX_TITLE_KEEPER_PID:-}" ]; then
    kill "$CODEEPSEEDEX_TITLE_KEEPER_PID" >/dev/null 2>&1 || true
    wait "$CODEEPSEEDEX_TITLE_KEEPER_PID" >/dev/null 2>&1 || true
    CODEEPSEEDEX_TITLE_KEEPER_PID=""
  fi
}

codex_runtime_preflight() {
  if [ ! -x "$REAL_CODEX" ]; then
    printf 'CoDeepSeedeX error: real Codex command is not executable: %s\n' "$REAL_CODEX" >&2
    return 127
  fi

  if ! command -v node >/dev/null 2>&1; then
    if head -n 1 "$REAL_CODEX" 2>/dev/null | grep -Eq '(^#!.*node|/env[[:space:]]+node)' || grep -qE 'node|@openai/codex|codex-cli' "$REAL_CODEX" 2>/dev/null; then
      printf 'CoDeepSeedeX error: Codex CLI was found at %s, but Node.js is not on PATH.\n' "$REAL_CODEX" >&2
      printf 'Install Node.js/Codex CLI first, then rerun the CoDeepSeedeX installer or: %s profile refresh-wrapper\n' "$DSPROXY" >&2
      printf 'Boundary: CoDeepSeedeX detects this dependency but does not install or patch Node automatically.\n' >&2
      return 127
    fi
  fi
}

codex_requires_legacy_profile_tables() {
  local version_text=""
  version_text="$("$REAL_CODEX" --version 2>/dev/null || true)"
  case "$version_text" in
    *" 0.130."*|*" 0.131."*|*" 0.132."*|*" 0.133."*|*"v0.130."*|*"v0.131."*|*"v0.132."*|*"v0.133."*)
      return 0
      ;;
  esac
  return 1
}

repair_codeepseedex_legacy_managed_profiles() {
  local thinking_port="${DEEPSEEK_PROXY_THINKING_PORT:-8001}"
  local model="${DEEPSEEK_PROXY_THINKING_MODEL:-${DEEPSEEK_PROXY_MODEL:-deepseek-v4-pro}}"
  local catalog_args=()
  local catalog=""

  catalog="${DEEPSEEK_PROXY_MODEL_CATALOG_JSON:-}"
  if [ -z "$catalog" ]; then
    catalog="__INSTALL_DIR__/experiments/model-catalog/deepseek-proxy-models.json"
  fi
  if [ -n "$catalog" ] && [ -f "$catalog" ]; then
    catalog_args=(--model-catalog-json "$catalog")
  fi

  "$DSPROXY" install-codex-profile \
    --name deepseek-thinking \
    --provider-name deepseek-thinking-proxy \
    --base-url "http://127.0.0.1:${thinking_port}/v1" \
    --model "$model" \
    --reasoning-effort xhigh \
    --profile-layout legacy_profile_tables \
    --no-backup \
    "${catalog_args[@]}" >/dev/null
}

repair_codeepseedex_managed_profile_contract() {
  local profile_name="$1"
  local status_json=""

  case "$profile_name" in
    deepseek-thinking)
      ;;
    deepseek)
      printf 'CoDeepSeedeX error: profile "deepseek" is deprecated. Use: codex --profile deepseek-thinking\n' >&2
      return 2
      ;;
    *)
      return 0
      ;;
  esac

  if [ "${CODEEPSEEDEX_PROFILE_REPAIR_ON_LAUNCH:-1}" = "0" ]; then
    return 0
  fi

  if [ ! -x "$DSPROXY" ]; then
    printf 'CoDeepSeedeX error: dsproxy command is not executable: %s\n' "$DSPROXY" >&2
    return 1
  fi

  if codex_requires_legacy_profile_tables; then
    if status_json="$("$DSPROXY" profile status "$profile_name" --json 2>/dev/null)"; then
      if printf '%s' "$status_json" | grep -q '"profile_source"[[:space:]]*:[[:space:]]*"legacy_profile_table"' \
        && ! printf '%s' "$status_json" | grep -q '"model_conflict"[[:space:]]*:[[:space:]]*true'; then
        return 0
      fi
    fi

    if ! repair_codeepseedex_legacy_managed_profiles; then
      printf 'CoDeepSeedeX error: failed to repair legacy managed Codex profile before launch.\n' >&2
      printf 'Run for details: %s install-codex-profile --profile-layout legacy_profile_tables --name %s\n' "$DSPROXY" "$profile_name" >&2
      return 1
    fi
  else
    if ! "$DSPROXY" profile repair --managed-only --json >/dev/null 2>&1; then
      printf 'CoDeepSeedeX error: failed to repair managed Codex profile before launch.\n' >&2
      printf 'Run for details: %s profile repair --managed-only --json\n' "$DSPROXY" >&2
      return 1
    fi
  fi

  if ! status_json="$("$DSPROXY" profile status "$profile_name" --json 2>/dev/null)"; then
    printf 'CoDeepSeedeX error: failed to verify managed Codex profile %s after repair.\n' "$profile_name" >&2
    return 1
  fi

  if printf '%s' "$status_json" | grep -q '"model_conflict"[[:space:]]*:[[:space:]]*true'; then
    if [ "${CODEEPSEEDEX_ALLOW_PROFILE_MODEL_CONFLICT:-0}" = "1" ]; then
      printf 'CoDeepSeedeX warning: managed Codex profile %s still has a model conflict; continuing because CODEEPSEEDEX_ALLOW_PROFILE_MODEL_CONFLICT=1.\n' "$profile_name" >&2
      return 0
    fi
    printf 'CoDeepSeedeX error: managed Codex profile %s still has a model conflict after repair.\n' "$profile_name" >&2
    printf 'Refusing to launch Codex with a stale or incompatible profile. Run: %s profile status %s --json\n' "$DSPROXY" "$profile_name" >&2
    return 1
  fi
}

activate_codeepseedex_custom_provider_profile() {
  local profile_name="$1"
  if [ -z "$profile_name" ] || [ ! -x "$DSPROXY" ]; then
    return 1
  fi
  if ! "$DSPROXY" config custom-provider use --name "$profile_name" --no-profile-sync >/dev/null 2>&1; then
    return 1
  fi
  "$DSPROXY" provider install-profile --name "$profile_name" --profile-name "$profile_name" >/dev/null 2>&1
}

start_dsproxy_profile() {
  local profile_name="$1"
  local start_args=()
  local status_args=()

  if [ ! -x "$DSPROXY" ]; then
    printf 'CoDeepSeedeX error: dsproxy command is not executable: %s\n' "$DSPROXY" >&2
    return 1
  fi

  case "$profile_name" in
    deepseek-thinking)
      start_args=(start thinking)
      status_args=(status thinking)
      ;;
    *)
      return 0
      ;;
  esac

  if ! "$DSPROXY" "${start_args[@]}" >/dev/null 2>&1; then
    if ! "$DSPROXY" "${status_args[@]}" >/dev/null 2>&1; then
      printf 'CoDeepSeedeX error: failed to start dsproxy for profile %s.\n' "$profile_name" >&2
      printf 'Run for details: %s %s\n' "$DSPROXY" "${start_args[*]}" >&2
      return 1
    fi
    return 0
  fi

  if ! "$DSPROXY" "${status_args[@]}" >/dev/null 2>&1; then
    printf 'CoDeepSeedeX error: dsproxy started but status check failed for profile %s.\n' "$profile_name" >&2
    printf 'Run for details: %s %s\n' "$DSPROXY" "${status_args[*]}" >&2
    return 1
  fi
}

run_codeepseedex_codex() {
  case "$profile" in
    deepseek)
      printf 'CoDeepSeedeX error: profile "deepseek" is deprecated. Use: codex --profile deepseek-thinking\n' >&2
      return 2
      ;;
    deepseek-thinking)
      repair_codeepseedex_managed_profile_contract "$profile"
      start_dsproxy_profile "$profile"
      schedule_codeepseedex_terminal_title_refresh
      ;;
    "")
      ;;
    *)
      if activate_codeepseedex_custom_provider_profile "$profile"; then
        start_dsproxy_profile "deepseek-thinking"
        schedule_codeepseedex_terminal_title_refresh
      elif [ -f "$HOME/.codex/${profile}.config.toml" ]; then
        :
      else
        printf 'CoDeepSeedeX error: unknown Codex profile "%s". No custom provider or split profile file was found.\n' "$profile" >&2
        printf 'Add/sync it first: %s provider install-profile --name %s --profile-name %s\n' "$DSPROXY" "$profile" "$profile" >&2
        return 2
      fi
      ;;
  esac

  if ! codex_runtime_preflight; then
    local preflight_rc=$?
    stop_codeepseedex_terminal_title_keeper
    return "$preflight_rc"
  fi

  set +e
  "$REAL_CODEX" "$@"
  local codex_rc=$?
  set -e
  stop_codeepseedex_terminal_title_keeper
  return "$codex_rc"
}

trap 'stop_codeepseedex_terminal_title_keeper' INT TERM HUP
run_codeepseedex_codex "$@"
"""
    wrapper = (
        wrapper_template
        .replace("__REAL_CODEX__", _shell_quote(str(real_resolved)))
        .replace("__BIN_DIR__", bin_dir)
        .replace("__INSTALL_DIR__", install_dir)
        .replace("__ENV_FILE__", env_file)
        .replace("__TITLE_EMOJIS__", title_emojis)
    )

    wrapper_path.parent.mkdir(parents=True, exist_ok=True)
    if bool(getattr(args, "dry_run", False)):
        result["refreshed"] = True
        result["dry_run"] = True
        result["contains_terminal_title"] = "set_codeepseedex_terminal_title" in wrapper
        result["emoji_firebird_count"] = wrapper.count("🐦‍🔥")
        return result

    wrapper_path.write_text(wrapper, encoding="utf-8")
    wrapper_path.chmod(0o755)

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_text = "\n".join([
        f"CODEX_WRAPPER_PATH={_shell_quote(str(wrapper_path))}",
        f"CODEX_WRAPPER_BACKUP={_shell_quote(backup_path)}",
        f"REAL_CODEX={_shell_quote(str(real_resolved))}",
        f"ENV_FILE={_shell_quote(env_file)}",
        f"INSTALL_DIR={_shell_quote(install_dir)}",
        f"BIN_DIR={_shell_quote(bin_dir)}",
        "",
    ])
    manifest_path.write_text(manifest_text, encoding="utf-8")
    try:
        manifest_path.chmod(0o600)
    except OSError:
        pass

    result["refreshed"] = True
    result["dry_run"] = False
    result["real_codex"] = str(real_resolved)
    result["contains_terminal_title"] = "set_codeepseedex_terminal_title" in wrapper
    result["emoji_firebird_count"] = wrapper.count("🐦‍🔥")
    return result

def _refresh_codex_wrapper(args: argparse.Namespace) -> int:
    result = _write_managed_codex_wrapper_from_manifest(args)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("status") == "ok" else 1



def _codex_reasoning_effort_for_deepseek(deepseek_effort: str | None, *, profile_name: str = "deepseek-thinking") -> str:
    """Map dsproxy/DeepSeek user-facing reasoning effort to Codex profile effort.

    CoDeepSeedeX exposes `high` and `max` to users. Codex profile files do not
    accept `max`; the compatible high-reasoning value is `xhigh`.
    """
    canonical = _canonical_cli_reasoning_effort(deepseek_effort or "high") or "high"
    if canonical == "max":
        return "xhigh"
    return "high"

def _profile_status_payload(profile_name: str, *, env_file: Path | None = None, codex_config: Path | None = None) -> dict[str, object]:
    env_path = env_file or default_env_file_path()
    codex_path = codex_config or default_codex_config_path()
    env_values = _read_env_exports(env_path)
    sections = _parse_simple_toml_sections(codex_path)
    profile_section, profile_source, profile_path = _read_codex_profile_values(codex_path, profile_name)
    profile_layout = "legacy_profile_tables" if profile_source == "legacy_profile_table" else "split_profile_files"
    profile_config_path = codex_path if profile_source == "legacy_profile_table" else profile_path
    provider_name = profile_section.get("model_provider") or f"{profile_name}-proxy"
    provider_section = sections.get(f"model_providers.{provider_name}", {})

    custom_provider_entry = _custom_provider_entry_for_profile(
        profile_name,
        env_file=env_path,
        env_values=env_values,
        provider_name=provider_name,
    )
    env_effort_raw = env_values.get("DEEPSEEK_REASONING_EFFORT")
    requested_deepseek_effort = _canonical_cli_reasoning_effort(env_effort_raw or profile_section.get("model_reasoning_effort") or "high") or "high"
    if custom_provider_entry is not None:
        deepseek_effort, effort_capability = _custom_provider_effective_reasoning_effort(
            custom_provider_entry,
            env_values,
            requested=requested_deepseek_effort,
        )
        expected_codex_effort = _codex_model_reasoning_effort_for_custom_provider(deepseek_effort, custom_provider_entry)
    else:
        deepseek_effort = requested_deepseek_effort
        effort_capability = {
            "requested_deepseek_reasoning_effort": requested_deepseek_effort,
            "effective_deepseek_reasoning_effort": deepseek_effort,
            "codex_model_reasoning_effort": _codex_model_reasoning_effort_for_deepseek(deepseek_effort),
            "reasoning_effort_max_supported": deepseek_effort == "max",
            "capability_downgraded": False,
            "reason": None,
            "action": None,
        }
        expected_codex_effort = _codex_model_reasoning_effort_for_deepseek(deepseek_effort)
    codex_effort = profile_section.get("model_reasoning_effort")
    health = _codex_config_health(codex_path)
    profile_invalid = [
        item for item in health["invalid_profile_fields"]
        if isinstance(item, dict) and item.get("profile") == profile_name
    ]

    model_contract = _profile_model_contract(profile_section, env_values, profile_name=profile_name)
    model_contract["model_provider"] = provider_name
    model_contract["base_url"] = provider_section.get("base_url")
    context_contract = _profile_context_contract(
        profile_section,
        effective_model=str(model_contract.get("effective_model") or model_contract.get("upstream_model") or model_contract.get("codex_model") or ""),
        env_values=env_values,
    )
    codex_profile_contract = context_contract.get("codex_profile")
    if isinstance(codex_profile_contract, dict):
        codex_profile_contract["profile_source"] = profile_source
        codex_profile_contract["codex_profile_layout"] = profile_layout
        codex_profile_contract["codex_profile_config"] = str(profile_config_path)
        if profile_source == "legacy_profile_table":
            codex_profile_contract["source"] = "codex_profile.legacy_profile_table"

    warnings = list(health["warnings"])
    if bool(model_contract.get("model_conflict")):
        warnings.append("codex_profile_model_differs_from_effective_upstream_model")

    payload = {
        "status": "ok" if not profile_invalid and health["codex_config_loadable"] else "error",
        "profile": profile_name,
        "profile_source": profile_source,
        "codex_profile_layout": profile_layout,
        "main_config": str(codex_path),
        "codex_config": str(codex_path),
        "codex_main_config": str(codex_path),
        "codex_profile_config": str(profile_config_path),
        "env_file": str(env_path),
        "model": model_contract,
        "effort": {
            "user_facing": "max" if deepseek_effort == "max" else "high",
            "requested_deepseek_reasoning_effort": requested_deepseek_effort,
            "deepseek_reasoning_effort": deepseek_effort,
            "codex_model_reasoning_effort": codex_effort,
            "expected_codex_model_reasoning_effort": expected_codex_effort,
            "source": "dsproxy_env_profile_and_provider_capability",
            "codex_profile_valid": codex_effort in CODEX_MODEL_REASONING_EFFORT_ALLOWED if codex_effort else False,
            "normalized": codex_effort == expected_codex_effort,
            "capability": effort_capability,
        },
        "thinking": _profile_thinking_status(profile_name, provider_section, env_values),
        "context_window": context_contract,
        "health": {
            "codex_config_loadable": bool(health["codex_config_loadable"]),
            "invalid_profile_fields": profile_invalid,
            "warnings": warnings,
            "legacy_profile_tables_present": health.get("legacy_profile_tables_present"),
            "legacy_profile_tables": health.get("legacy_profile_tables"),
            "legacy_profile_selectors_present": health.get("legacy_profile_selectors_present"),
        },
    }
    payload["diagnostics"] = _weclaw_diagnostics_contract(payload)
    return payload

def _post_config_apply_for_args(args: argparse.Namespace) -> dict[str, object]:
    if not bool(getattr(args, "no_refresh", False)):
        return _post_config_apply()

    env_names = ("DEEPSEEK_PROXY_POST_CONFIG_APPLY", "CODEEPSEEDEX_POST_CONFIG_APPLY")
    previous = {name: os.environ.get(name) for name in env_names}
    try:
        for name in env_names:
            os.environ[name] = "disabled"
        return _post_config_apply()
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def _set_effort_contract(args: argparse.Namespace, env_file: Path, *, explicit_profiles: list[str] | None = None) -> int:
    contract = _reasoning_effort_contract(args.effort)
    allowed = {"low", "medium", "high", "xhigh", "max", "minimal", "none"}
    if contract is None:
        print(json.dumps({"status": "error", "error": "invalid_effort", "allowed": sorted(allowed)}, ensure_ascii=False, indent=2))
        return 2

    deepseek_effort = str(contract["deepseek_reasoning_effort"])
    codex_effort = str(contract["codex_model_reasoning_effort"])

    values = _read_env_exports(env_file)
    values["DEEPSEEK_REASONING_EFFORT"] = deepseek_effort
    _write_env_exports(env_file, values)

    codex_path = Path(args.codex_config).expanduser() if getattr(args, "codex_config", None) else default_codex_config_path()
    target_profiles = explicit_profiles or _managed_profile_targets(getattr(args, "profile", "__managed__"))

    profile_results: list[dict[str, object]] = []
    updated_profiles: list[str] = []
    for profile_name in target_profiles:
        model_patched = _patch_codex_profile_value(codex_path, profile_name, "model_reasoning_effort", codex_effort)
        plan_patched = _patch_codex_profile_value(codex_path, profile_name, "plan_mode_reasoning_effort", "high")
        if model_patched or plan_patched:
            updated_profiles.append(profile_name)
        profile_results.append({
            "profile": profile_name,
            "model_reasoning_effort": codex_effort,
            "model_reasoning_effort_patched": model_patched,
            "plan_mode_reasoning_effort": "high",
            "plan_mode_reasoning_effort_patched": plan_patched,
        })

    health = _codex_config_health(codex_path)
    output = {
        "status": "ok" if health["codex_config_loadable"] else "error",
        "env_file": str(env_file),
        "requested_effort": args.effort,
        "effort": deepseek_effort,
        "user_facing": contract["user_facing"],
        "deepseek_reasoning_effort": deepseek_effort,
        "codex_model_reasoning_effort": codex_effort,
        "codex_plan_mode_reasoning_effort": "high",
        "normalized": contract["normalized"],
        "compatibility_note": contract["compatibility_note"],
        "codex_config": str(codex_path),
        "codex_profile": getattr(args, "profile", "__managed__"),
        "target_profiles": target_profiles,
        "updated_profiles": updated_profiles,
        "codex_profile_patched": bool(updated_profiles),
        "codex_plan_mode_profile_patched": any(bool(item["plan_mode_reasoning_effort_patched"]) for item in profile_results),
        "profile_results": profile_results,
        "codex_config_loadable": health["codex_config_loadable"],
        "invalid_profile_fields": health["invalid_profile_fields"],
        "post_config_apply": _post_config_apply_for_args(args),
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0





def _repair_profile_models(args: argparse.Namespace, env_file: Path) -> int:
    codex_path = Path(args.codex_config).expanduser() if getattr(args, "codex_config", None) else default_codex_config_path()
    target_profiles = _managed_profile_targets("__managed__" if bool(getattr(args, "managed_only", False)) else getattr(args, "profile", "__managed__"))
    dry_run = bool(getattr(args, "dry_run", False))
    env_values = _read_env_exports(env_file)
    managed_auto_compact_ratio = _auto_compact_ratio_from_env_values(
        env_values,
        explicit=getattr(args, "auto_compact_ratio", None),
    )

    original_text = codex_path.read_text(encoding="utf-8") if codex_path.exists() else ""
    working_text = original_text
    profile_results: list[dict[str, object]] = []
    updated_profiles: list[str] = []
    skipped_profiles: list[str] = []
    post_validation_errors: list[dict[str, object]] = []
    profile_writes: dict[str, str] = {}

    for profile_name in target_profiles:
        provider_defaults = _managed_profile_provider_defaults(profile_name)
        before_sections = _parse_simple_toml_sections_from_text(working_text)
        before_profile_section, before_profile_source, profile_path = _read_codex_profile_values(codex_path, profile_name)
        if profile_name in profile_writes:
            before_profile_section = _parse_simple_toml_key_values_from_text(profile_writes[profile_name])
            before_profile_source = "split_profile_file_pending_write"
        before_provider_name = before_profile_section.get("model_provider") or (provider_defaults or {}).get("provider_name") or f"{profile_name}-proxy"
        before_provider_section = before_sections.get(f"model_providers.{before_provider_name}", {})

        before_payload = _profile_status_payload(profile_name, env_file=env_file, codex_config=codex_path)
        if profile_name in profile_writes:
            tmp_profile_section = before_profile_section
            model_info = _profile_model_contract(tmp_profile_section, env_values, profile_name=profile_name)
            model_info["model_provider"] = before_provider_name
        else:
            model_info = before_payload.get("model", {}) if isinstance(before_payload, dict) else {}
        effective_model = str(model_info.get("effective_model") or "").strip()
        codex_model = str(model_info.get("codex_model") or "").strip()

        effort_info = before_payload.get("effort", {}) if isinstance(before_payload, dict) else {}
        expected_effort = str(effort_info.get("expected_codex_model_reasoning_effort") or "").strip() or "high"

        if not effective_model or effective_model == "unknown":
            env_model = env_values.get("DEEPSEEK_PROXY_MODEL") or env_values.get("DEEPSEEK_MODEL")
            if env_model:
                effective_model = env_model
            else:
                skipped_profiles.append(profile_name)
                profile_results.append({
                    "profile": profile_name,
                    "status": "skipped",
                    "reason": "effective_model_unknown",
                    "codex_model_before": codex_model or None,
                    "effective_model": effective_model or None,
                    "profile_contract_version": CODEEPSEEDEX_PROFILE_CONTRACT_VERSION,
                    "codex_profile_layout": "split_profile_files",
                    "profile_config": str(profile_path),
                })
                continue

        model_context_window = _int_or_zero(before_profile_section.get("model_context_window")) or DEFAULT_CONTEXT_WINDOW_TOKENS
        expected_auto_compact_token_limit = _derive_auto_compact_token_limit(
            model_context_window,
            managed_auto_compact_ratio,
        )
        current_auto_compact_token_limit = _int_or_zero(before_profile_section.get("model_auto_compact_token_limit"))
        tool_output_token_limit = _int_or_zero(before_profile_section.get("tool_output_token_limit")) or 12_000
        model_catalog_json = before_profile_section.get("model_catalog_json")

        provider_name = (provider_defaults or {}).get("provider_name") or before_provider_name
        base_url = (provider_defaults or {}).get("base_url") or before_provider_section.get("base_url") or ""
        _provider_header, provider_block, _profile_header, profile_block = _codex_profile_blocks(
            profile_name=profile_name,
            provider_name=provider_name,
            base_url=base_url,
            model=effective_model,
            reasoning_effort=expected_effort,
            context_window=model_context_window,
            auto_compact_token_limit=expected_auto_compact_token_limit,
            tool_output_token_limit=tool_output_token_limit,
            model_catalog_json=model_catalog_json,
        )
        provider_header = f"[model_providers.{provider_name}]"
        candidate_text, provider_existed = _upsert_toml_table(working_text, provider_header, provider_block)
        candidate_text, cleanup = _cleanup_main_codex_config_for_profile(candidate_text, profile_name)
        changed_main = candidate_text != working_text
        working_text = candidate_text

        before_profile_text = profile_path.read_text(encoding="utf-8") if profile_path.exists() else ""
        changed_profile = before_profile_text != profile_block
        profile_writes[profile_name] = profile_block

        after_profile_section = _parse_simple_toml_key_values_from_text(profile_block)
        after_sections = _parse_simple_toml_sections_from_text(working_text)
        after_provider_section = after_sections.get(f"model_providers.{provider_name}", {})
        provider_needs_patch = (
            before_provider_name != provider_name
            or before_provider_section.get("base_url") != base_url
            or before_provider_section.get("wire_api") != "responses"
            or before_provider_section.get("env_key") != "DEEPSEEK_API_KEY"
        )
        model_needs_patch = codex_model != effective_model
        effort_needs_patch = before_profile_section.get("model_reasoning_effort") != expected_effort
        plan_needs_patch = before_profile_section.get("plan_mode_reasoning_effort") != "high"
        auto_compact_needs_patch = current_auto_compact_token_limit != expected_auto_compact_token_limit
        changed = changed_main or changed_profile

        if changed:
            updated_profiles.append(profile_name)

        profile_results.append({
            "profile": profile_name,
            "status": "ok",
            "profile_contract_version": CODEEPSEEDEX_PROFILE_CONTRACT_VERSION,
            "codex_profile_layout": "split_profile_files",
            "profile_source_before": before_profile_source,
            "profile_config": str(profile_path),
            "managed_profile": bool(provider_defaults),
            "provider": provider_name,
            "provider_before": before_provider_name,
            "provider_existed": provider_existed,
            "profile_existed": profile_path.exists() or cleanup["legacy_profile_table_removed"],
            "legacy_profile_table_removed": cleanup["legacy_profile_table_removed"],
            "legacy_profile_selector_removed": cleanup["legacy_profile_selector_removed"],
            "provider_needs_patch": provider_needs_patch,
            "provider_patched": bool(changed_main and provider_needs_patch and not dry_run),
            "provider_base_url": base_url,
            "provider_base_url_after": after_provider_section.get("base_url"),
            "wire_api_after": after_provider_section.get("wire_api"),
            "env_key_after": after_provider_section.get("env_key"),
            "codex_model_before": codex_model or None,
            "effective_model": effective_model,
            "codex_model_after": after_profile_section.get("model"),
            "model_needs_patch": model_needs_patch,
            "model_patched": bool(changed_profile and model_needs_patch and not dry_run),
            "model_reasoning_effort": expected_effort,
            "model_reasoning_effort_after": after_profile_section.get("model_reasoning_effort"),
            "model_reasoning_effort_needs_patch": effort_needs_patch,
            "model_reasoning_effort_patched": bool(changed_profile and effort_needs_patch and not dry_run),
            "plan_mode_reasoning_effort": "high",
            "plan_mode_reasoning_effort_after": after_profile_section.get("plan_mode_reasoning_effort"),
            "plan_mode_reasoning_effort_needs_patch": plan_needs_patch,
            "plan_mode_reasoning_effort_patched": bool(changed_profile and plan_needs_patch and not dry_run),
            "model_context_window_tokens": model_context_window,
            "auto_compact_ratio": managed_auto_compact_ratio,
            "current_model_auto_compact_token_limit": current_auto_compact_token_limit,
            "expected_model_auto_compact_token_limit": expected_auto_compact_token_limit,
            "model_auto_compact_token_limit_needs_patch": auto_compact_needs_patch,
            "model_auto_compact_token_limit_patched": bool(changed_profile and auto_compact_needs_patch and not dry_run),
            "future_compatibility_policy": "regenerate split managed profile/provider from dsproxy contract and fail closed if the Codex-visible model still differs",
        })

    if not dry_run:
        if working_text != original_text:
            codex_path.parent.mkdir(parents=True, exist_ok=True)
            codex_path.write_text(working_text, encoding="utf-8")
        for profile_name, profile_text in profile_writes.items():
            profile_path = codex_profile_config_path(profile_name, codex_path)
            profile_path.parent.mkdir(parents=True, exist_ok=True)
            profile_path.write_text(profile_text, encoding="utf-8")

    if not dry_run:
        for profile_name in target_profiles:
            if profile_name not in CODEEPSEEDEX_MANAGED_CODEX_PROFILES:
                continue
            post_payload = _profile_status_payload(profile_name, env_file=env_file, codex_config=codex_path)
            model_info = post_payload.get("model", {}) if isinstance(post_payload, dict) else {}
            if bool(model_info.get("model_conflict")):
                post_validation_errors.append({
                    "profile": profile_name,
                    "reason": "managed_profile_model_conflict_after_repair",
                    "codex_model": model_info.get("codex_model"),
                    "effective_model": model_info.get("effective_model"),
                    "action": "inspect Codex split profile files before launching Codex",
                })

    health = _codex_config_health(codex_path)
    output = {
        "status": "error" if post_validation_errors or not health["codex_config_loadable"] else "ok",
        "operation": "profile_repair",
        "profile_contract_version": CODEEPSEEDEX_PROFILE_CONTRACT_VERSION,
        "codex_profile_layout": "split_profile_files",
        "layout_contract": codex_profile_layout_contract(),
        "managed_auto_compact_ratio": managed_auto_compact_ratio,
        "auto_compact_ratio_source": (
            "arg.auto_compact_ratio"
            if getattr(args, "auto_compact_ratio", None) is not None
            else "env_file_or_default"
        ),
        "env_file": str(env_file),
        "codex_config": str(codex_path),
        "codex_main_config": str(codex_path),
        "managed_only": bool(getattr(args, "managed_only", False)),
        "target_profiles": target_profiles,
        "updated_profiles": updated_profiles,
        "skipped_profiles": skipped_profiles,
        "profile_results": profile_results,
        "post_validation_errors": post_validation_errors,
        "codex_config_loadable": health["codex_config_loadable"],
        "invalid_profile_fields": health["invalid_profile_fields"],
        "legacy_profile_tables_present": health.get("legacy_profile_tables_present"),
        "dry_run": dry_run,
        "config_preview": working_text if dry_run else None,
        "profile_config_previews": profile_writes if dry_run else None,
        "post_config_apply": None if dry_run else _post_config_apply(),
        "future_compatibility_policy": "Managed CoDeepSeedeX profiles are regenerated as Codex 0.134+ split profile files before Codex launch; launch must fail closed if profile model conflict remains.",
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if output["status"] == "ok" else 1




def _repair_default_managed_codex_profiles_for_cli_route(*, reason: str) -> dict[str, object]:
    """Repair managed split profile models before runtime/status entry paths.

    This is intentionally quiet because `start` and `status` have their own
    output contracts. It prevents stale Codex-visible split profiles from
    surviving after the env has moved to a forced custom upstream model.
    """
    if str(os.environ.get("CODEEPSEEDEX_PROFILE_SYNC_ON_CLI_ROUTE", "1")).strip().lower() in {"0", "false", "no", "off", "disabled", "never"}:
        return {
            "status": "skipped",
            "reason": "profile_sync_on_cli_route_disabled",
            "operation": "managed_profile_route_preflight",
        }
    if os.environ.get("PYTEST_CURRENT_TEST") and os.environ.get("CODEEPSEEDEX_TEST_ALLOW_PROFILE_SYNC") != "1":
        return {
            "status": "skipped",
            "reason": "pytest_guard_without_explicit_allow",
            "operation": "managed_profile_route_preflight",
        }

    env_file = default_env_file_path()
    codex_path = default_codex_config_path()
    if not env_file.exists():
        return {
            "status": "skipped",
            "reason": "default_env_file_missing",
            "env_file": str(env_file),
            "codex_config": str(codex_path),
            "operation": "managed_profile_route_preflight",
        }

    args = argparse.Namespace(
        codex_config=str(codex_path),
        managed_only=True,
        profile="__managed__",
        dry_run=False,
        auto_compact_ratio=None,
    )
    previous_post_apply = {
        "DEEPSEEK_PROXY_POST_CONFIG_APPLY": os.environ.get("DEEPSEEK_PROXY_POST_CONFIG_APPLY"),
        "CODEEPSEEDEX_POST_CONFIG_APPLY": os.environ.get("CODEEPSEEDEX_POST_CONFIG_APPLY"),
    }
    old_stdout = sys.stdout
    buffer = io.StringIO()
    try:
        os.environ["CODEEPSEEDEX_POST_CONFIG_APPLY"] = "disabled"
        os.environ["DEEPSEEK_PROXY_POST_CONFIG_APPLY"] = "disabled"
        sys.stdout = buffer
        rc = _repair_profile_models(args, env_file)
    finally:
        sys.stdout = old_stdout
        for key, value in previous_post_apply.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    raw = buffer.getvalue()
    try:
        payload = json.loads(raw[raw.find("{"):]) if "{" in raw else {}
    except Exception as exc:
        payload = {"parse_error": f"{type(exc).__name__}: {exc}", "raw": raw[:2000]}

    status = "ok" if rc == 0 and payload.get("status") == "ok" else "error"
    return {
        "status": status,
        "operation": "managed_profile_route_preflight",
        "reason": reason,
        "returncode": rc,
        "env_file": str(env_file),
        "codex_config": str(codex_path),
        "repair": payload,
    }


def _managed_profile_route_preflight_or_error(*, reason: str) -> dict[str, object] | None:
    result = _repair_default_managed_codex_profiles_for_cli_route(reason=reason)
    if result.get("status") == "error":
        return {
            "status": "error",
            "error": "managed_profile_route_preflight_failed",
            "message": "CoDeepSeedeX refused to continue with stale or unrepaired managed Codex profiles.",
            "profile_preflight": result,
            "action": "Run: dsproxy profile repair --managed-only --json",
        }
    return None


def _profile(args: argparse.Namespace) -> int:
    env_file = Path(args.env_file).expanduser() if getattr(args, "env_file", None) else default_env_file_path()
    if args.profile_command == "status":
        codex_path = Path(args.codex_config).expanduser() if getattr(args, "codex_config", None) else default_codex_config_path()
        payload = _profile_status_payload(args.profile, env_file=env_file, codex_config=codex_path)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if payload.get("status") == "ok" else 1
    if args.profile_command == "set-effort":
        return _set_effort_contract(args, env_file, explicit_profiles=[args.profile])
    if args.profile_command == "repair":
        return _repair_profile_models(args, env_file)
    if args.profile_command == "refresh-wrapper":
        return _refresh_codex_wrapper(args)
    print(json.dumps({"status": "error", "error": "unknown_profile_command"}, ensure_ascii=False, indent=2))
    return 2


def _cli_compaction_audit_metadata_from_runtime_status(runtime_status: dict[str, object] | None) -> dict[str, object]:
    if not isinstance(runtime_status, dict):
        return {
            "available": False,
            "unit": "tokens",
            "source": "legacy_runtime_status_unavailable",
            "reason": "legacy_runtime_status_unavailable",
            "missing": [
                "compaction_prompt_fingerprint",
                "compact_material_classifier_dry_run",
                "retained_recent_policy",
            ],
            "raw_content_exposed": False,
            "redacted": True,
        }

    runtime_context = runtime_status.get("context")
    compaction = runtime_context.get("compaction") if isinstance(runtime_context, dict) else None
    last_report = compaction.get("last_report") if isinstance(compaction, dict) else None
    if not isinstance(last_report, dict):
        return {
            "available": False,
            "unit": "tokens",
            "source": "legacy_runtime_status.context.compaction.last_report",
            "reason": "context_compaction_last_report_unavailable",
            "missing": [
                "compaction_prompt_fingerprint",
                "compact_material_classifier_dry_run",
                "retained_recent_policy",
            ],
            "raw_content_exposed": False,
            "redacted": True,
        }

    material = last_report.get("material") if isinstance(last_report.get("material"), dict) else {}
    fingerprint = last_report.get("compaction_prompt_fingerprint")
    if not isinstance(fingerprint, dict):
        fingerprint = material.get("compaction_prompt_fingerprint") if isinstance(material, dict) else None
    classifier = last_report.get("compact_material_classifier_dry_run")
    if not isinstance(classifier, dict):
        classifier = material.get("compact_material_classifier_dry_run") if isinstance(material, dict) else None
    retained_policy = last_report.get("retained_recent_policy")
    if not isinstance(retained_policy, dict):
        retained_policy = material.get("retained_recent_policy") if isinstance(material, dict) else None

    missing: list[str] = []
    if not isinstance(fingerprint, dict):
        missing.append("compaction_prompt_fingerprint")
        fingerprint = None
    if not isinstance(classifier, dict):
        missing.append("compact_material_classifier_dry_run")
        classifier = None
    if not isinstance(retained_policy, dict):
        missing.append("retained_recent_policy")
        retained_policy = None

    available = not missing
    return {
        "available": available,
        "unit": "tokens",
        "source": "legacy_runtime_status.context.compaction.last_report.compact_audit_metadata",
        "raw_content_exposed": False,
        "redacted": True,
        "fingerprint": fingerprint,
        "classifier_dry_run": classifier,
        "retained_recent_policy": retained_policy,
        "missing": missing,
        "reason": None if available else "compact_audit_metadata_incomplete",
    }

def _weclaw_status_payload(args: argparse.Namespace) -> dict[str, object]:
    profile_name = "deepseek-thinking" if bool(getattr(args, "thinking", False)) else "deepseek"
    env_file = Path(getattr(args, "env_file", "")).expanduser() if getattr(args, "env_file", None) else default_env_file_path()
    profile_status = _profile_status_payload(profile_name, env_file=env_file, codex_config=default_codex_config_path())

    runtime_error: dict[str, object] | None = None
    try:
        thinking = bool(getattr(args, "thinking", False))
        port = _port_for(thinking, getattr(args, "port", None))
        timeout = float(getattr(args, "timeout", 2.0) or 2.0)
        base_url = _base_url(thinking=thinking, port=port)
        query = {"profile": profile_name, "include_balance": "true"}
        if getattr(args, "session_id", None):
            query["session_id"] = str(args.session_id)
        weclaw_url = f"{base_url}/v1/proxy/weclaw/status?{urllib.parse.urlencode(query)}"
        http_status, data, error = _http_json(weclaw_url, timeout=timeout)
        if isinstance(data, dict) and data.get("status") in {"ok", "error"}:
            data = dict(data)
            data["runtime_status"] = {
                "available": True,
                "source": weclaw_url,
                "error": None,
            }
            if "diagnostics" not in data:
                data["diagnostics"] = _weclaw_diagnostics_contract(data)
            return data
        runtime_error = {"http_status": http_status, "error": error, "source": weclaw_url}
    except Exception as exc:
        runtime_error = {"error": f"{type(exc).__name__}: {exc}"}

    legacy_runtime_status: dict[str, object] | None = None
    try:
        thinking = bool(getattr(args, "thinking", False))
        port = _port_for(thinking, getattr(args, "port", None))
        timeout = float(getattr(args, "timeout", 2.0) or 2.0)
        legacy_url = f"{_base_url(thinking=thinking, port=port)}/v1/proxy/status"
        http_status, data, error = _http_json(legacy_url, timeout=timeout)
        if isinstance(data, dict):
            legacy_runtime_status = data
        else:
            runtime_error = runtime_error or {"http_status": http_status, "error": error, "source": legacy_url}
    except Exception as exc:
        runtime_error = runtime_error or {"error": f"{type(exc).__name__}: {exc}"}

    context_window = _merge_runtime_context_contract(
        dict(profile_status.get("context_window", {})),
        legacy_runtime_status,
    )

    compaction_available = bool(legacy_runtime_status and isinstance(legacy_runtime_status.get("context"), dict))
    runtime_context = legacy_runtime_status.get("context") if isinstance(legacy_runtime_status, dict) else None
    semantic_compaction = None
    if isinstance(legacy_runtime_status, dict) and isinstance(legacy_runtime_status.get("semantic_compaction"), dict):
        semantic_compaction = legacy_runtime_status.get("semantic_compaction")

    compact_audit = _cli_compaction_audit_metadata_from_runtime_status(legacy_runtime_status)

    fallback_pricing = {
        "available": False,
        "provider": "deepseek",
        "model": str(dict(profile_status.get("model", {})).get("effective_model") or DEFAULT_MODEL),
        "currency": "USD",
        "unit": "per_1m_tokens",
        "source": "runtime_required",
        "source_path": None,
        "source_url": None,
        "source_kind": "runtime_required",
        "fallback_used": None,
        "is_stale": None,
        "fetched_at": None,
        "expires_at": None,
        "ttl_seconds": None,
        "prices": None,
        "all_models": [],
        "missing": ["running_dsproxy_weclaw_status_endpoint"],
        "refresh": {
            "available": False,
            "reason": "running_dsproxy_weclaw_status_endpoint_unavailable",
            "action": "start the selected dsproxy route and re-run dsproxy status --weclaw-json",
            "source_kind": "runtime_required",
            "requires_live_network": None,
            "writes_cache": False,
        },
    }

    payload = {
        "status": profile_status.get("status", "ok"),
        "version": {
            "public_version": globals().get("PROXY_PUBLIC_VERSION", "unknown"),
            "internal_version": globals().get("PROXY_INTERNAL_VERSION", "unknown"),
        },
        "profile": profile_name,
        "session": {
            "id": None,
            "started_at": None,
            "source": "not_available_from_dsproxy_cli_status_yet",
            "available": False,
        },
        "model": {
            **dict(profile_status.get("model", {})),
            "thinking_enabled": bool(profile_status.get("thinking", {}).get("enabled")) if isinstance(profile_status.get("thinking"), dict) else profile_name.endswith("thinking"),
        },
        "effort": profile_status.get("effort", {}),
        "context_window": context_window,
        "runtime_status": {
            "available": legacy_runtime_status is not None,
            "source": "http://127.0.0.1:<route>/v1/proxy/weclaw/status",
            "error": runtime_error,
        },
        "tokens": {
            "taxonomy": {
                "version": 2,
                "unit": "tokens",
                "source": "dsproxy_runtime_required",
                "categories": [
                    "input",
                    "cached_input",
                    "output",
                    "reasoning",
                    "primary_model_call",
                    "auxiliary_model_call",
                    "tool_bridge",
                    "liveness_judge",
                    "liveness_retry",
                    "compaction",
                    "semantic_audit",
                    "other",
                ],
                "precision": {
                    "provider_usage_totals": "runtime_required",
                    "purpose_attribution": "runtime_required",
                    "prompt_subcategory_split": "not_reported_by_provider_without_tokenizer",
                },
            },
            "last_turn": {
                "available": False,
                "unit": "tokens",
                "is_estimated": False,
                "missing": ["running_dsproxy_weclaw_status_endpoint"],
                "reason": "running_dsproxy_weclaw_status_endpoint_unavailable",
                "action": "start the selected dsproxy route and re-run dsproxy status --weclaw-json",
                "source": "not_available_without_runtime_usage_snapshot",
            },
            "session_total": {
                "available": False,
                "unit": "tokens",
                "is_estimated": False,
                "missing": ["running_dsproxy_weclaw_status_endpoint"],
                "reason": "running_dsproxy_weclaw_status_endpoint_unavailable",
                "action": "start the selected dsproxy route and re-run dsproxy status --weclaw-json",
            },
            "auxiliary_model_calls": {
                "available": False,
                "unit": "tokens",
                "included_in_session_total": None,
                "missing": ["running_dsproxy_weclaw_status_endpoint"],
                "reason": "running_dsproxy_weclaw_status_endpoint_unavailable",
                "action": "start the selected dsproxy route and re-run dsproxy status --weclaw-json",
            },
        },
        "pricing": fallback_pricing,
        "cost": {
            "available": False,
            "is_estimated": False,
            "usage_available": False,
            "pricing_available": False,
            "pricing_stale": False,
            "reason": "running_dsproxy_weclaw_status_endpoint_unavailable",
            "missing": ["running_dsproxy_weclaw_status_endpoint"],
            "balance": {
                "available": False,
                "reason": "running_dsproxy_weclaw_status_endpoint_unavailable",
                "action": "start the selected dsproxy route and re-run dsproxy status --weclaw-json",
            },
        },
        "balance": {
            "available": False,
            "status": "not_configured",
            "provider": "deepseek",
            "reason": "running_dsproxy_weclaw_status_endpoint_unavailable",
            "action": "start the selected dsproxy route and re-run dsproxy status --weclaw-json",
            "updated_at": None,
            "currency": None,
            "amount": None,
            "display": None,
        },
        "runtime_payload_guard": {
            "available": False,
            "unit": "tokens",
            "current_tokens": None,
            "current_tokens_available": False,
            "current_tokens_source": "runtime_weclaw_status_endpoint_unavailable",
            "current_tokens_precision": "unavailable",
            "current_tokens_observed_at": None,
            "reason": "running_dsproxy_weclaw_status_endpoint_unavailable",
            "action": "start the selected dsproxy route and re-run dsproxy status --weclaw-json",
            "compaction": {
                "available": False,
                "status": "unavailable",
                "reason": "running_dsproxy_weclaw_status_endpoint_unavailable",
                "compact_audit": compact_audit,
            },
            "trimming": {
                "available": False,
                "status": "unavailable",
                "reason": "running_dsproxy_weclaw_status_endpoint_unavailable",
            },
        },
        "compaction": {
            "available": compaction_available,
            "is_estimated": False,
            "source": "dsproxy_runtime./v1/proxy/status.context",
            "unit": "tokens",
            "runtime_context": runtime_context if isinstance(runtime_context, dict) else None,
            "compact_audit": compact_audit,
            "semantic_compaction": semantic_compaction,
            "missing": [] if compaction_available else ["context_compaction_report_binding"],
        },
        "semantic_compaction": semantic_compaction,
        "health": profile_status.get("health", {}),
    }
    payload["diagnostics"] = _weclaw_diagnostics_contract(payload)
    return payload



def _uninstall_codex_profile(args: argparse.Namespace) -> int:
    config_path = Path(args.path).expanduser() if args.path else default_codex_config_path()
    profile_name = args.name
    provider_name = args.provider_name or f"{profile_name}-proxy"
    profile_path = codex_profile_config_path(profile_name, config_path)
    provider_header = f"[model_providers.{provider_name}]"

    original = config_path.read_text(encoding="utf-8") if config_path.exists() else ""
    text, cleanup = _cleanup_main_codex_config_for_profile(original, profile_name)
    text, provider_removed = _remove_toml_table(text, provider_header)
    profile_file_removed = profile_path.exists()

    result = {
        "path": str(config_path),
        "codex_profile_layout": "split_profile_files",
        "main_config": str(config_path),
        "profile_config": str(profile_path),
        "profile": profile_name,
        "provider": provider_name,
        "profile_removed": bool(cleanup["legacy_profile_table_removed"] or profile_file_removed),
        "profile_file_removed": profile_file_removed,
        "legacy_profile_table_removed": cleanup["legacy_profile_table_removed"],
        "legacy_profile_selector_removed": cleanup["legacy_profile_selector_removed"],
        "provider_removed": provider_removed,
        "dry_run": bool(args.dry_run),
    }

    if args.dry_run:
        result["config_preview"] = text
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if (config_path.exists() or profile_path.exists()) and not args.no_backup:
        backup = config_path.with_suffix(config_path.suffix + ".bak")
        backup.write_text(original, encoding="utf-8")
        result["backup"] = str(backup)
        if profile_path.exists():
            profile_backup = profile_path.with_suffix(profile_path.suffix + ".bak")
            profile_backup.write_text(profile_path.read_text(encoding="utf-8"), encoding="utf-8")
            result["profile_backup"] = str(profile_backup)

    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(text, encoding="utf-8")
    if profile_path.exists():
        profile_path.unlink()
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


def _move_stale_pid_file(pid_path: Path, *, pid: int | None, port: int, reason: str) -> dict[str, object]:
    stale_path = pid_path.with_name(f"{pid_path.name}.stale-{int(time.time())}")
    try:
        pid_path.replace(stale_path)
        moved = True
        error = None
    except Exception as exc:
        moved = False
        stale_path = pid_path
        error = f"{type(exc).__name__}: {exc}"
    return {
        "pid": pid,
        "port": port,
        "pid_file": str(pid_path),
        "stale_pid_file": str(stale_path),
        "stale_pid_moved": moved,
        "reason": reason,
        "error": error,
    }


def _start_proxy(args: argparse.Namespace) -> int:
    thinking = bool(args.thinking)
    port = _port_for(thinking, args.port)
    state_dir = Path(args.state_dir).expanduser() if args.state_dir else _default_state_dir()
    state_dir.mkdir(parents=True, exist_ok=True)
    _maybe_print_startup_release_update_notice()

    profile_preflight_error = _managed_profile_route_preflight_or_error(reason="dsproxy_start_preflight")
    if profile_preflight_error is not None:
        print(json.dumps(profile_preflight_error, ensure_ascii=False, indent=2))
        return 1

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
        listen_pids = _listen_pids_for_local_port(port)
        if existing_pid not in listen_pids:
            moved = _move_stale_pid_file(
                pid_path,
                pid=existing_pid,
                port=port,
                reason="pid_file_alive_but_not_listening_on_target_port",
            )
            print(json.dumps({"status": "recovered_stale_pid_file", **moved}, ensure_ascii=False))
        else:
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
                        "listen_pids": listen_pids,
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
    for key, value in _read_env_exports(default_env_file_path()).items():
        env.setdefault(key, value)
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
        env["DEEPSEEK_PROXY_TOOL_OUTPUT_TRIM_MODE"] = env.get(
            "DEEPSEEK_PROXY_TOOL_OUTPUT_TRIM_MODE",
            "enabled",
        )
        env["DEEPSEEK_PROXY_TOOL_OUTPUT_IMAGE_PAYLOAD_MAX_ITEM_CHARS"] = env.get(
            "DEEPSEEK_PROXY_TOOL_OUTPUT_IMAGE_PAYLOAD_MAX_ITEM_CHARS",
            "12000",
        )

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



def _pid_alive(pid: int | None) -> bool:
    if pid is None:
        return False
    try:
        os.kill(pid, 0)
        return True
    except (OSError, TypeError):
        return False


def _cmdline_for_pid(pid: int) -> str:
    proc_cmdline = Path(f"/proc/{pid}/cmdline")
    try:
        if proc_cmdline.exists():
            raw = proc_cmdline.read_bytes()
            return raw.replace(b"\x00", b" ").decode("utf-8", errors="replace").strip()
    except OSError:
        pass

    try:
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "args="],
            text=True,
            capture_output=True,
            timeout=2,
            check=False,
        )
        return result.stdout.strip()
    except Exception:
        return ""


def _pid_looks_like_proxy(pid: int) -> bool:
    cmdline = _cmdline_for_pid(pid)
    markers = [
        "deepseek_responses_proxy.app:app",
        "deepseek_responses_proxy",
        "deepseek-responses-proxy",
    ]
    return any(marker in cmdline for marker in markers)


def _listen_pids_for_local_port(port: int) -> list[int]:
    try:
        result = subprocess.run(
            ["ss", "-ltnp"],
            text=True,
            capture_output=True,
            timeout=2,
            check=False,
        )
    except Exception:
        return []

    pids: set[int] = set()
    for line in result.stdout.splitlines():
        if f":{port}" not in line:
            continue
        if "127.0.0.1:" not in line and "[::1]:" not in line and "localhost:" not in line:
            continue
        for match in re.finditer(r"pid=(\d+)", line):
            try:
                pids.add(int(match.group(1)))
            except ValueError:
                pass
    return sorted(pids)


def _port_status_looks_like_proxy(port: int) -> bool:
    status, data, _error = _http_json(f"http://{DEFAULT_HOST}:{port}/v1/proxy/status", timeout=1.0)
    if status != 200 or not isinstance(data, dict):
        status, data, _error = _healthz_for_port(port, timeout=1.0)
        if status != 200 or not isinstance(data, dict):
            return False

    version = data.get("version")
    if not isinstance(version, str) or not version.startswith("v"):
        return False

    proxy_markers = {
        "model_default",
        "thinking",
        "thinking_enabled",
        "tool_bridge",
        "store",
        "deepseek_base_url",
        "agent_liveness",
        "context",
    }
    if any(key in data for key in proxy_markers):
        return True

    return data.get("status") == "ok"


def _terminate_pid(pid: int, *, label: str) -> bool:
    if not _pid_alive(pid):
        return False

    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return False

    for _ in range(30):
        if not _pid_alive(pid):
            print(f"stopped pid={pid} {label}".rstrip())
            return True
        time.sleep(0.1)

    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        pass

    for _ in range(10):
        if not _pid_alive(pid):
            print(f"killed pid={pid} {label}".rstrip())
            return True
        time.sleep(0.1)

    return False


def _default_stop_port(args: argparse.Namespace) -> int:
    if getattr(args, "port", None):
        return int(args.port)

    thinking = bool(getattr(args, "thinking", False))
    env_name = "DEEPSEEK_PROXY_THINKING_PORT" if thinking else "DEEPSEEK_PROXY_PORT"
    env_value = os.environ.get(env_name)

    if not env_value:
        try:
            env_value = _read_env_exports(default_env_file_path()).get(env_name)
        except Exception:
            env_value = None

    if env_value:
        try:
            return int(env_value)
        except ValueError:
            pass

    return 8001 if thinking else 8000


def _stop_by_port_discovery(port: int) -> bool:
    if not _port_status_looks_like_proxy(port):
        return False

    pids = _listen_pids_for_local_port(port)
    if not pids:
        print(f"proxy_running_but_pid_not_found port={port}")
        return False

    stopped_any = False
    refused: list[int] = []
    for pid in pids:
        if _pid_looks_like_proxy(pid):
            stopped_any = _terminate_pid(pid, label=f"port={port} source=port_discovery") or stopped_any
        else:
            refused.append(pid)

    if refused:
        refused_text = ",".join(str(pid) for pid in refused)
        print(f"refused_to_kill_non_proxy_service port={port} pids={refused_text}")

    return stopped_any

def _stop_proxy(args: argparse.Namespace) -> int:
    thinking = bool(args.thinking)
    state_dir = Path(args.state_dir).expanduser() if args.state_dir else _default_state_dir()
    pid_path = Path(args.pid_file).expanduser() if args.pid_file else state_dir / ("proxy-thinking.pid" if thinking else "proxy.pid")
    port = _default_stop_port(args)

    stopped_any = False
    explicit_port = getattr(args, "port", None) is not None

    # If the user explicitly gives --port, respect the port first. Do not kill a
    # stale/default pid-file process that may belong to another instance.
    if explicit_port:
        stopped_any = _stop_by_port_discovery(port)
        if not stopped_any:
            print(f"not_running port={port}")
        return 0

    if pid_path.exists():
        try:
            pid = int(pid_path.read_text(encoding="utf-8").strip())
        except Exception:
            pid = None

        if pid is not None and _pid_alive(pid):
            if _pid_looks_like_proxy(pid):
                stopped_any = _terminate_pid(pid, label=f"pid_file={pid_path}") or stopped_any
            else:
                print(f"refused_to_kill_non_proxy_pid_file pid={pid} pid_file={pid_path}")
        else:
            print(f"stale_pid_file pid_file={pid_path}")

        try:
            pid_path.unlink()
        except OSError:
            pass

    # Fallback: if no valid pid file existed, or if the port still responds as
    # CoDeepSeedeX, discover the listener by port and stop it safely.
    if _port_status_looks_like_proxy(port):
        stopped_any = _stop_by_port_discovery(port) or stopped_any

    if not stopped_any:
        print(f"not_running pid_file={pid_path} port={port}")

    return 0

def _status(args: argparse.Namespace) -> int:
    profile_preflight_error = _managed_profile_route_preflight_or_error(reason="dsproxy_status_preflight")
    if profile_preflight_error is not None:
        print(json.dumps(profile_preflight_error, ensure_ascii=False, indent=2))
        return 1

    if getattr(args, "weclaw_json", False):
        print(json.dumps(_weclaw_status_payload(args), ensure_ascii=False, indent=2))
        return 0

    thinking = bool(args.thinking)
    port = _port_for(thinking, args.port)
    url = f"{_base_url(thinking=thinking, port=port)}/v1/proxy/status"
    status, data, error = _http_json(url, timeout=args.timeout)

    if data is not None:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0 if status == 200 else 1

    print(json.dumps({"status": "error", "url": url, "http_status": status, "error": error}, ensure_ascii=False, indent=2))
    return 1




def _cli_pricing_contract(model: str | None = None) -> dict[str, object]:
    return dict(_weclaw_pricing_contract(model))


DEEPSEEK_TOKENIZER_KIND = "deepseek_official_current"
DEEPSEEK_TOKENIZER_SOURCE_URL = "https://cdn.deepseek.com/api-docs/deepseek_v3_tokenizer.zip"
DEEPSEEK_TOKENIZER_ZIP_SHA256 = "c954ca6f6e54281d72d3c27e2430cea7663f81292b39982e2f97890c66c302de"
DEEPSEEK_TOKENIZER_ZIP_ENTRIES = {
    "tokenizer_json": "deepseek_v3_tokenizer/tokenizer.json",
    "tokenizer_config_json": "deepseek_v3_tokenizer/tokenizer_config.json",
}


def _tokenizer_resource_root(value: str | None = None) -> Path:
    if value:
        return Path(value).expanduser()
    env_value = os.environ.get("DEEPSEEK_PROXY_TOKENIZER_RESOURCE_DIR", "").strip()
    if env_value:
        return Path(env_value).expanduser()
    install_dir = os.environ.get("DEEPSEEK_PROXY_INSTALL_DIR", "").strip()
    if install_dir:
        return Path(install_dir).expanduser() / "resources" / "tokenizers"
    return Path.home() / ".local" / "share" / APP_NAME / "resources" / "tokenizers"


def _tokenizer_provider_kind(provider: str | None) -> str | None:
    provider_key = str(provider or "deepseek").strip().lower()
    if provider_key in {"deepseek", "deepseek-v3", "deepseek-v4"}:
        return DEEPSEEK_TOKENIZER_KIND
    return None


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_path(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _read_tokenizer_source_bytes(source_url: str, *, timeout: float) -> bytes:
    parsed = urllib.parse.urlparse(source_url)
    if parsed.scheme in {"", "file"}:
        path = Path(urllib.request.url2pathname(parsed.path) if parsed.scheme == "file" else source_url).expanduser()
        return path.read_bytes()

    with urllib.request.urlopen(source_url, timeout=timeout) as response:
        return response.read()


def _tokenizer_resource_status(provider: str = "deepseek", *, resource_root: str | None = None) -> dict[str, Any]:
    kind = _tokenizer_provider_kind(provider)
    root = _tokenizer_resource_root(resource_root)
    if kind is None:
        return {
            "status": "unsupported",
            "provider": provider,
            "available": False,
            "reason": "unsupported_tokenizer_provider",
            "supported_providers": ["deepseek"],
        }

    resource_dir = root / kind
    tokenizer_json = resource_dir / "tokenizer.json"
    tokenizer_config = resource_dir / "tokenizer_config.json"
    manifest_path = resource_dir / "manifest.json"
    manifest: dict[str, Any] | None = None
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception as exc:
            manifest = {"parse_error": f"{type(exc).__name__}: {exc}"}

    contract = _profile_tokenizer_contract("deepseek-v4-flash", "deepseek")
    return {
        "status": "ok",
        "provider": provider,
        "tokenizer_kind": kind,
        "available": tokenizer_json.is_file(),
        "resource_root": str(root),
        "resource_dir": str(resource_dir),
        "tokenizer_json": {
            "path": str(tokenizer_json),
            "exists": tokenizer_json.is_file(),
            "sha256": _sha256_path(tokenizer_json) if tokenizer_json.is_file() else None,
            "bytes": tokenizer_json.stat().st_size if tokenizer_json.is_file() else None,
        },
        "tokenizer_config_json": {
            "path": str(tokenizer_config),
            "exists": tokenizer_config.is_file(),
            "sha256": _sha256_path(tokenizer_config) if tokenizer_config.is_file() else None,
            "bytes": tokenizer_config.stat().st_size if tokenizer_config.is_file() else None,
        },
        "manifest": manifest,
        "runtime_contract": contract,
    }


def _sync_deepseek_tokenizer_resource(
    *,
    source_url: str = DEEPSEEK_TOKENIZER_SOURCE_URL,
    expected_sha256: str = DEEPSEEK_TOKENIZER_ZIP_SHA256,
    resource_root: str | None = None,
    timeout: float = 60.0,
    force: bool = False,
) -> dict[str, Any]:
    root = _tokenizer_resource_root(resource_root)
    kind = DEEPSEEK_TOKENIZER_KIND
    resource_dir = root / kind
    tokenizer_json = resource_dir / "tokenizer.json"
    tokenizer_config = resource_dir / "tokenizer_config.json"
    manifest_path = resource_dir / "manifest.json"

    if tokenizer_json.is_file() and tokenizer_config.is_file() and not force:
        return {
            "status": "ok",
            "provider": "deepseek",
            "tokenizer_kind": kind,
            "changed": False,
            "reason": "already_synced",
            "resource_dir": str(resource_dir),
            "tokenizer_json": str(tokenizer_json),
            "manifest": json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else None,
        }

    data = _read_tokenizer_source_bytes(source_url, timeout=timeout)
    actual_sha256 = _sha256_bytes(data)
    if expected_sha256 and actual_sha256.lower() != expected_sha256.lower():
        return {
            "status": "error",
            "provider": "deepseek",
            "tokenizer_kind": kind,
            "changed": False,
            "reason": "tokenizer_zip_sha256_mismatch",
            "source_url": source_url,
            "expected_sha256": expected_sha256,
            "actual_sha256": actual_sha256,
            "old_resource_preserved": resource_dir.exists(),
        }

    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        missing = [entry for entry in DEEPSEEK_TOKENIZER_ZIP_ENTRIES.values() if entry not in archive.namelist()]
        if missing:
            return {
                "status": "error",
                "provider": "deepseek",
                "tokenizer_kind": kind,
                "changed": False,
                "reason": "tokenizer_zip_missing_expected_entries",
                "source_url": source_url,
                "missing": missing,
                "old_resource_preserved": resource_dir.exists(),
            }

        root.mkdir(parents=True, exist_ok=True)
        tmp_dir = Path(tempfile.mkdtemp(prefix=f".{kind}.", dir=str(root)))
        try:
            (tmp_dir / "tokenizer.json").write_bytes(archive.read(DEEPSEEK_TOKENIZER_ZIP_ENTRIES["tokenizer_json"]))
            (tmp_dir / "tokenizer_config.json").write_bytes(archive.read(DEEPSEEK_TOKENIZER_ZIP_ENTRIES["tokenizer_config_json"]))
            manifest = {
                "provider": "deepseek",
                "tokenizer_kind": kind,
                "source_url": source_url,
                "source_zip_sha256": actual_sha256,
                "source_zip_entries": DEEPSEEK_TOKENIZER_ZIP_ENTRIES,
                "upstream_archive_name": "deepseek_v3_tokenizer.zip",
                "upstream_archive_internal_dir": "deepseek_v3_tokenizer",
                "naming_note": "DeepSeek currently publishes this official tokenizer archive from its token usage documentation; the archive name remains deepseek_v3_tokenizer even when used for current DeepSeek profile local estimates.",
                "fetched_at": int(time.time()),
                "tokenizer_json_sha256": _sha256_path(tmp_dir / "tokenizer.json"),
                "tokenizer_config_json_sha256": _sha256_path(tmp_dir / "tokenizer_config.json"),
            }
            (tmp_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

            backup_dir = None
            if resource_dir.exists():
                backup_dir = root / f".{kind}.old.{os.getpid()}"
                if backup_dir.exists():
                    shutil.rmtree(backup_dir)
                resource_dir.replace(backup_dir)
            tmp_dir.replace(resource_dir)
            if backup_dir is not None and backup_dir.exists():
                shutil.rmtree(backup_dir)

            return {
                "status": "ok",
                "provider": "deepseek",
                "tokenizer_kind": kind,
                "changed": True,
                "resource_dir": str(resource_dir),
                "tokenizer_json": str(resource_dir / "tokenizer.json"),
                "tokenizer_config_json": str(resource_dir / "tokenizer_config.json"),
                "manifest": manifest,
            }
        except Exception:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            raise


def _tokenizer(args: argparse.Namespace) -> int:
    command = getattr(args, "tokenizer_command", None)
    provider = getattr(args, "provider", "deepseek")
    if command == "status":
        payload = _tokenizer_resource_status(provider, resource_root=getattr(args, "resource_dir", None))
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if payload.get("status") == "ok" else 1

    if command == "sync":
        if provider != "deepseek":
            print(json.dumps({
                "status": "error",
                "error": "unsupported_tokenizer_provider",
                "provider": provider,
                "supported_providers": ["deepseek"],
            }, ensure_ascii=False, indent=2))
            return 2
        payload = _sync_deepseek_tokenizer_resource(
            source_url=getattr(args, "source_url", None) or DEEPSEEK_TOKENIZER_SOURCE_URL,
            expected_sha256=getattr(args, "expected_sha256", None) or DEEPSEEK_TOKENIZER_ZIP_SHA256,
            resource_root=getattr(args, "resource_dir", None),
            timeout=float(getattr(args, "timeout", 60.0) or 60.0),
            force=bool(getattr(args, "force", False)),
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if payload.get("status") == "ok" else 1

    print(json.dumps({"status": "error", "error": "unknown_tokenizer_command"}, ensure_ascii=False, indent=2))
    return 2



def _pricing(args: argparse.Namespace) -> int:
    model = getattr(args, "model", None)
    command = getattr(args, "pricing_command", "show")
    if command == "show":
        pricing = _cli_pricing_contract(model)
        payload = {
            "status": "ok",
            "pricing": pricing,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    if command == "refresh":
        payload = _refresh_deepseek_pricing_from_official_docs(
            model=model,
            source_url=getattr(args, "source_url", None) or "https://api-docs.deepseek.com/zh-cn/quick_start/pricing/",
            write_cache=bool(getattr(args, "write_cache", False)),
            cache_path=getattr(args, "cache_path", None),
            timeout=float(getattr(args, "timeout", 20.0) or 20.0),
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if payload.get("status") == "ok" else 1

    print(json.dumps({"status": "error", "error": "unknown_pricing_command"}, ensure_ascii=False, indent=2))
    return 2


def _post_config_run_self(argv: list[str], *, timeout: float = 20.0) -> dict[str, object]:
    command = [sys.executable, "-m", "deepseek_responses_proxy.cli", *argv]
    try:
        proc = subprocess.run(
            command,
            cwd=str(Path.cwd()),
            text=True,
            capture_output=True,
            timeout=timeout,
        )
        return {
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "argv": ["dsproxy", *argv],
            "stdout_tail": proc.stdout[-1200:],
            "stderr_tail": proc.stderr[-1200:],
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "returncode": "timeout",
            "argv": ["dsproxy", *argv],
            "stdout_tail": str(exc.stdout or "")[-1200:],
            "stderr_tail": str(exc.stderr or "")[-1200:],
        }
    except Exception as exc:
        return {
            "ok": False,
            "returncode": "error",
            "argv": ["dsproxy", *argv],
            "error": f"{type(exc).__name__}: {exc}",
        }


def _post_config_apply() -> dict[str, object]:
    mode = (
        os.environ.get("DEEPSEEK_PROXY_POST_CONFIG_APPLY")
        or os.environ.get("CODEEPSEEDEX_POST_CONFIG_APPLY")
        or "auto"
    ).strip().lower()
    result: dict[str, object] = {
        "status": "ok",
        "mode": mode,
        "message": "all updates applied",
        "stable_proxy": {},
        "thinking_proxy": {},
    }
    if mode in {"0", "false", "no", "off", "disabled", "never"}:
        result["status"] = "skipped"
        result["message"] = "post-config apply disabled"
        return result

    overall_ok = True
    for target_name, thinking in [("stable_proxy", False), ("thinking_proxy", True)]:
        port = _port_for(thinking, None)
        target: dict[str, object] = {
            "port": port,
            "was_running": False,
            "action": "not_running",
            "ok": True,
        }
        if _port_status_looks_like_proxy(port):
            target["was_running"] = True
            stop_argv = ["stop", "thinking"] if thinking else ["stop"]
            start_argv = ["start", "thinking"] if thinking else ["start"]
            stop_step = _post_config_run_self(stop_argv)
            start_step = _post_config_run_self(start_argv) if bool(stop_step.get("ok")) else {
                "ok": False,
                "argv": ["dsproxy", *start_argv],
                "skipped": "stop_failed",
            }
            target.update(
                {
                    "action": "refreshed",
                    "stop": stop_step,
                    "start": start_step,
                    "ok": bool(stop_step.get("ok")) and bool(start_step.get("ok")),
                }
            )
        result[target_name] = target
        overall_ok = overall_ok and bool(target.get("ok"))

    if not overall_ok:
        result["status"] = "partial"
        result["message"] = "configuration saved, but one or more running proxies could not be refreshed"
    return result



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



_PROVIDER_PROBE_PROMPT = "A small red cube on a white background, minimal style."

_WEB_SEARCH_PROVIDER_ENV_KEYS = {
    "serpapi": ["SERPAPI_API_KEY", "DEEPSEEK_PROXY_SERPAPI_API_KEY"],
    "tavily": ["TAVILY_API_KEY", "DEEPSEEK_PROXY_TAVILY_API_KEY"],
    "exa": ["EXA_API_KEY", "DEEPSEEK_PROXY_EXA_API_KEY"],
    "firecrawl": ["FIRECRAWL_API_KEY", "DEEPSEEK_PROXY_FIRECRAWL_API_KEY"],
}

_IMAGE_PROVIDER_ALIASES = {
    "zhipu": "zhipu",
    "zhipuai": "zhipu",
    "bigmodel": "zhipu",
    "zai": "zai",
    "z.ai": "zai",
    "glm": "zai",
    "qwen": "qwen_image",
    "qwen_image": "qwen_image",
    "qwen-image": "qwen_image",
    "dashscope": "qwen_image",
    "aliyun": "qwen_image",
    "qwen_image_beijing": "qwen_image_beijing",
    "qwen-image-beijing": "qwen_image_beijing",
    "qwen_beijing": "qwen_image_beijing",
    "dashscope_beijing": "qwen_image_beijing",
    "qwen_image_singapore": "qwen_image_singapore",
    "qwen-image-singapore": "qwen_image_singapore",
    "qwen_singapore": "qwen_image_singapore",
    "dashscope_singapore": "qwen_image_singapore",
    "qwen_image_us": "qwen_image_us",
    "qwen-image-us": "qwen_image_us",
    "qwen_us": "qwen_image_us",
    "qwen_us_virginia": "qwen_image_us",
    "dashscope_us": "qwen_image_us",
    "qwen_image_germany": "qwen_image_germany",
    "qwen-image-germany": "qwen_image_germany",
    "qwen_germany": "qwen_image_germany",
    "qwen_frankfurt": "qwen_image_germany",
    "dashscope_germany": "qwen_image_germany",
    "stability": "stability",
    "stability_ai": "stability",
    "stable_image": "stability",
    "fal": "fal",
    "fal_ai": "fal",
    "fal.ai": "fal",
}

_IMAGE_PROVIDER_ENV_KEYS: dict[str, list[str]] = {
    "zhipu": ["ZHIPUAI_API_KEY", "ZHIPU_API_KEY"],
    "zai": ["ZAI_API_KEY", "GLM_API_KEY"],
    "qwen_image": ["DASHSCOPE_API_KEY", "ALIBABA_DASHSCOPE_API_KEY", "DEEPSEEK_PROXY_DASHSCOPE_API_KEY"],
    "qwen_image_beijing": ["DASHSCOPE_API_KEY", "ALIBABA_DASHSCOPE_API_KEY", "DEEPSEEK_PROXY_DASHSCOPE_API_KEY"],
    "qwen_image_singapore": ["DASHSCOPE_API_KEY", "ALIBABA_DASHSCOPE_API_KEY", "DEEPSEEK_PROXY_DASHSCOPE_API_KEY"],
    "qwen_image_us": ["DASHSCOPE_API_KEY", "ALIBABA_DASHSCOPE_API_KEY", "DEEPSEEK_PROXY_DASHSCOPE_API_KEY"],
    "qwen_image_germany": ["DASHSCOPE_API_KEY", "ALIBABA_DASHSCOPE_API_KEY", "DEEPSEEK_PROXY_DASHSCOPE_API_KEY"],
    "stability": ["STABILITY_API_KEY", "DEEPSEEK_PROXY_STABILITY_API_KEY"],
    "fal": ["FAL_KEY", "FAL_API_KEY", "DEEPSEEK_PROXY_FAL_API_KEY"],
}


def _image_provider_primary_env_key(provider: str | None) -> str:
    canonical = _canonical_probe_image_provider(str(provider or ""))
    mapping = {
        "zhipu": "ZHIPUAI_API_KEY",
        "zai": "ZAI_API_KEY",
        "qwen_image": "DASHSCOPE_API_KEY",
        "qwen_image_beijing": "DASHSCOPE_API_KEY",
        "qwen_image_singapore": "DASHSCOPE_API_KEY",
        "qwen_image_us": "DASHSCOPE_API_KEY",
        "qwen_image_germany": "DASHSCOPE_API_KEY",
        "stability": "STABILITY_API_KEY",
        "fal": "FAL_KEY",
    }
    return mapping.get(canonical, "DEEPSEEK_PROXY_IMAGE_API_KEY")


def _image_provider_probe_keys(canonical: str, env_values: dict[str, str]) -> list[str]:
    selected = _canonical_probe_image_provider(env_values.get("DEEPSEEK_PROXY_IMAGE_PROVIDER", "")) or "zhipu"
    keys = list(_IMAGE_PROVIDER_ENV_KEYS.get(canonical) or [])
    if selected == canonical and "DEEPSEEK_PROXY_IMAGE_API_KEY" not in keys:
        keys = ["DEEPSEEK_PROXY_IMAGE_API_KEY", *keys]
    return keys


def _provider_probe_env_values(env_file: Path | None) -> tuple[Path, dict[str, str]]:
    path = env_file or default_env_file_path()
    return path, _read_env_exports(path)


def _provider_probe_secret(keys: list[str], env_values: dict[str, str], env_file: Path) -> tuple[str, str | None, str | None]:
    for key in keys:
        value = os.environ.get(key, "")
        if value:
            return value, f"environment:{key}", key
    for key in keys:
        value = env_values.get(key, "")
        if value:
            return value, f"env_file:{key}", key
    return "", None, None


def _canonical_probe_image_provider(provider: str) -> str:
    selected = str(provider or "").strip().lower()
    return _IMAGE_PROVIDER_ALIASES.get(selected, selected)



_QWEN_IMAGE_REGION_STATUS = {
    "qwen_image": {
        "region": "Beijing",
        "endpoint": "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation",
        "model_available": True,
        "status": "supported",
    },
    "qwen_image_beijing": {
        "region": "Beijing",
        "endpoint": "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation",
        "model_available": True,
        "status": "supported",
    },
    "qwen_image_singapore": {
        "region": "Singapore",
        "endpoint": "https://dashscope-intl.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation",
        "model_available": True,
        "status": "supported",
    },
    "qwen_image_us": {
        "region": "US Virginia",
        "endpoint": "https://dashscope-us.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation",
        "model_available": False,
        "status": "qwen_image_model_unavailable",
    },
    "qwen_image_germany": {
        "region": "Germany Frankfurt",
        "endpoint": "https://dashscope.eu-central-1.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation",
        "model_available": False,
        "status": "qwen_image_model_unavailable",
    },
}


def _is_qwen_image_provider(provider: str | None) -> bool:
    return _canonical_probe_image_provider(str(provider or "")) in _QWEN_IMAGE_REGION_STATUS


def _qwen_image_region_status(provider: str | None) -> dict[str, Any]:
    canonical = _canonical_probe_image_provider(str(provider or ""))
    return dict(_QWEN_IMAGE_REGION_STATUS.get(canonical) or _QWEN_IMAGE_REGION_STATUS["qwen_image"])


def _qwen_image_region_unavailable_result(provider: str | None) -> dict[str, Any]:
    canonical = _canonical_probe_image_provider(str(provider or ""))
    info = _qwen_image_region_status(canonical)
    return {
        "ok": False,
        "status": "region_model_unavailable",
        "kind": "image_generation",
        "provider": canonical,
        "region": info.get("region"),
        "endpoint": info.get("endpoint"),
        "error": "qwen_image_region_model_unavailable",
        "message": f"Qwen Image is currently not available for {info.get('region')}. Choose qwen_image_beijing or qwen_image_singapore, or set a verified custom DashScope image endpoint.",
        "validation_method": "region_capability_check",
        "may_consume_quota": False,
        "validation_strength": "static_region_capability",
        "functional_probe": False,
        "functional_validation": "not_performed",
    }



def _provider_probe_web_targets(kind: str, provider: str) -> list[tuple[str, str]]:
    selected_kind = str(kind or "all").strip().lower()
    selected_provider = str(provider or "all").strip().lower()
    targets: list[tuple[str, str]] = []
    if selected_kind in {"all", "web-search", "web_search", "web"}:
        web_providers = list(_WEB_SEARCH_PROVIDER_ENV_KEYS)
        if selected_provider not in {"all", "*"}:
            web_providers = [selected_provider]
        for item in web_providers:
            targets.append(("web_search", item))
    if selected_kind in {"all", "image", "image-generation", "image_generation"}:
        image_providers = ["zhipu", "zai", "qwen_image", "qwen_image_beijing", "qwen_image_singapore", "qwen_image_us", "qwen_image_germany", "stability", "fal"]
        if selected_provider not in {"all", "*"}:
            image_providers = [_canonical_probe_image_provider(selected_provider)]
        for item in image_providers:
            targets.append(("image_generation", item))
    return targets


def _provider_probe_image_payload(provider: str, prompt: str) -> tuple[str, bytes, dict[str, str]]:
    if provider == "zhipu":
        endpoint = "https://open.bigmodel.cn/api/paas/v4/images/generations"
        payload = {"model": "cogView-4-250304", "prompt": prompt, "size": "1024x1024"}
        return endpoint, json.dumps(payload).encode("utf-8"), {"Content-Type": "application/json"}
    if provider == "zai":
        endpoint = "https://api.z.ai/api/paas/v4/images/generations"
        payload = {"model": "cogView-4-250304", "prompt": prompt, "size": "1024x1024"}
        return endpoint, json.dumps(payload).encode("utf-8"), {"Content-Type": "application/json"}
    if _is_qwen_image_provider(provider):
        info = _qwen_image_region_status(provider)
        endpoint = (
            os.environ.get("DEEPSEEK_PROXY_IMAGE_BASE_URL")
            or os.environ.get("DASHSCOPE_IMAGE_ENDPOINT")
            or str(info.get("endpoint") or "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation")
        )
        model = (
            os.environ.get("DEEPSEEK_PROXY_IMAGE_MODEL")
            or os.environ.get("DASHSCOPE_IMAGE_MODEL")
            or "qwen-image-2.0-pro"
        )
        payload = {
            "model": model,
            "input": {"messages": [{"role": "user", "content": [{"text": prompt}]}]},
            "parameters": {"size": "1024*1024", "n": 1},
        }
        return endpoint, json.dumps(payload).encode("utf-8"), {"Content-Type": "application/json"}
    if provider == "stability":
        endpoint = "https://api.stability.ai/v2beta/stable-image/generate/core"
        boundary = "----CoDeepSeedeXProviderProbeBoundary"
        parts = []
        for name, value in [("prompt", prompt), ("output_format", "png")]:
            parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n")
        parts.append(f"--{boundary}--\r\n")
        return endpoint, "".join(parts).encode("utf-8"), {"Content-Type": f"multipart/form-data; boundary={boundary}", "Accept": "application/json"}
    if provider == "fal":
        endpoint = "https://fal.run/fal-ai/flux/schnell"
        payload = {"prompt": prompt, "num_images": 1}
        return endpoint, json.dumps(payload).encode("utf-8"), {"Content-Type": "application/json"}
    raise ValueError(f"unsupported_image_provider:{provider}")

def _provider_probe_image_evidence(provider: str, data: Any, raw: bytes, content_type: str) -> dict[str, Any]:
    content_type_l = str(content_type or "").lower()
    if raw and ("image/" in content_type_l or "application/octet-stream" in content_type_l):
        return {"has_image": True, "evidence": "binary_image_response", "content_type": content_type}
    if not isinstance(data, dict):
        return {"has_image": False, "evidence": "unparseable_response", "content_type": content_type}

    if provider in {"zhipu", "zai"}:
        items = data.get("data") or []
        for item in items:
            if isinstance(item, dict) and (item.get("url") or item.get("b64_json")):
                return {"has_image": True, "evidence": "data_url_or_base64", "content_type": content_type}
    if _is_qwen_image_provider(provider):
        output = data.get("output") if isinstance(data.get("output"), dict) else {}
        for item in output.get("results") or []:
            if isinstance(item, dict) and (item.get("url") or item.get("image")):
                return {"has_image": True, "evidence": "output_results_image", "content_type": content_type}
        for choice in output.get("choices") or []:
            message = choice.get("message") if isinstance(choice, dict) else {}
            for item in (message or {}).get("content") or []:
                if isinstance(item, dict) and (item.get("image") or item.get("url")):
                    return {"has_image": True, "evidence": "output_choice_image", "content_type": content_type}
    if provider == "stability":
        if data.get("image"):
            return {"has_image": True, "evidence": "json_image_base64", "content_type": content_type}
        for item in data.get("artifacts") or data.get("images") or []:
            if isinstance(item, dict) and (item.get("base64") or item.get("url") or item.get("image_url")):
                return {"has_image": True, "evidence": "json_artifact_image", "content_type": content_type}
    if provider == "fal":
        items = data.get("images") or (data.get("data") or {}).get("images") or []
        for item in items:
            if isinstance(item, dict) and (item.get("url") or item.get("image_url")):
                return {"has_image": True, "evidence": "images_url", "content_type": content_type}

    return {"has_image": False, "evidence": "no_image_field", "content_type": content_type}

def _live_image_generation_probe(provider: str, api_key: str, *, timeout: float, prompt: str) -> dict[str, Any]:
    canonical = _canonical_probe_image_provider(provider)
    if canonical not in _IMAGE_PROVIDER_ENV_KEYS:
        return {
            "ok": False,
            "status": "error",
            "kind": "image_generation",
            "provider": canonical,
            "error": "unsupported_image_provider",
            "supported_providers": list(_IMAGE_PROVIDER_ENV_KEYS),
        }
    if not api_key:
        return {
            "ok": False,
            "status": "error",
            "kind": "image_generation",
            "provider": canonical,
            "error": "missing_api_key",
        }
    if _is_qwen_image_provider(canonical) and not bool(_qwen_image_region_status(canonical).get("model_available")):
        return _qwen_image_region_unavailable_result(canonical)

    try:
        endpoint, body, extra_headers = _provider_probe_image_payload(canonical, prompt)
    except ValueError:
        return {
            "ok": False,
            "status": "error",
            "kind": "image_generation",
            "provider": canonical,
            "error": "unsupported_image_provider",
            "supported_providers": list(_IMAGE_PROVIDER_ENV_KEYS),
        }

    headers = {
        **extra_headers,
        "Authorization": f"Key {api_key}" if canonical == "fal" else f"Bearer {api_key}",
        "Accept": extra_headers.get("Accept", "application/json"),
    }
    request = urllib.request.Request(endpoint, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            content_type = response.headers.get("content-type", "")
            try:
                data = json.loads(raw.decode("utf-8", errors="replace")) if raw else {}
            except json.JSONDecodeError:
                data = None
            evidence = _provider_probe_image_evidence(canonical, data, raw, content_type)
            ok = 200 <= int(response.status) < 300 and bool(evidence.get("has_image"))
            return {
                "ok": ok,
                "status": "ok" if ok else "error",
                "kind": "image_generation",
                "provider": canonical,
                "endpoint": endpoint,
                "http_status": int(response.status),
                "validation_method": "live_image_generation",
                "validation_strength": "live_generation_probe",
                "functional_probe": True,
                "functional_validation": "performed",
                "may_consume_quota": True,
                "prompt": prompt,
                **evidence,
            }
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        return {
            "ok": False,
            "status": "error",
            "kind": "image_generation",
            "provider": canonical,
            "endpoint": endpoint,
            "error": "http_error",
            "http_status": int(exc.code),
            "body_preview": raw[:1000],
            "validation_method": "live_image_generation",
            "validation_strength": "live_generation_probe",
            "functional_probe": True,
            "functional_validation": "performed",
            "may_consume_quota": True,
            "prompt": prompt,
        }
    except Exception as exc:
        return {
            "ok": False,
            "status": "error",
            "kind": "image_generation",
            "provider": canonical,
            "endpoint": endpoint,
            "error": type(exc).__name__,
            "message": str(exc)[:500],
            "validation_method": "live_image_generation",
            "validation_strength": "live_generation_probe",
            "functional_probe": True,
            "functional_validation": "performed",
            "may_consume_quota": True,
            "prompt": prompt,
        }




_TOOL_ROUTING_POLICY_VALUES = ("auto", "managed_only", "native_only", "disabled")
_TOOL_ROUTING_KIND_ALIASES = {
    "web": "web_search",
    "web_search": "web_search",
    "web-search": "web_search",
    "image": "image_generation",
    "image_generation": "image_generation",
    "image-generation": "image_generation",
}
_TOOL_ROUTING_POLICY_ALIASES = {
    "auto": "auto",
    "managed": "managed_only",
    "managed_only": "managed_only",
    "managed-only": "managed_only",
    "managed_tool": "managed_only",
    "native": "native_only",
    "native_only": "native_only",
    "native-only": "native_only",
    "disabled": "disabled",
    "off": "disabled",
    "none": "disabled",
}


def _canonical_tool_routing_kind(value: object) -> str | None:
    return _TOOL_ROUTING_KIND_ALIASES.get(str(value or "").strip().lower().replace(" ", "_"))


def _canonical_tool_routing_policy(value: object) -> str | None:
    return _TOOL_ROUTING_POLICY_ALIASES.get(str(value or "").strip().lower().replace(" ", "_"))


def _tool_routing_env_key(kind: str) -> str:
    if kind == "web_search":
        return "DEEPSEEK_PROXY_WEB_SEARCH_ROUTING"
    if kind == "image_generation":
        return "DEEPSEEK_PROXY_IMAGE_GENERATION_ROUTING"
    raise ValueError(f"unsupported_tool_routing_kind:{kind}")


def _tool_routing_policy_from_env_values(kind: str, env_values: dict[str, str]) -> tuple[str, str | None]:
    if kind == "web_search":
        names = [
            "DEEPSEEK_PROXY_WEB_SEARCH_ROUTING",
            "DEEPSEEK_PROXY_WEB_SEARCH_ROUTING_POLICY",
            "CODEEPSEEDEX_WEB_SEARCH_ROUTING",
        ]
    elif kind == "image_generation":
        names = [
            "DEEPSEEK_PROXY_IMAGE_GENERATION_ROUTING",
            "DEEPSEEK_PROXY_IMAGE_ROUTING",
            "DEEPSEEK_PROXY_IMAGE_GENERATION_ROUTING_POLICY",
            "CODEEPSEEDEX_IMAGE_GENERATION_ROUTING",
        ]
    else:
        return "auto", None
    for name in names:
        raw = env_values.get(name) or os.environ.get(name)
        policy = _canonical_tool_routing_policy(raw)
        if policy is not None:
            return policy, name
    return "auto", None


def _tool_routing_provider_config_status(kind: str, env_values: dict[str, str], env_file: Path) -> dict[str, object]:
    if kind == "web_search":
        provider = str(env_values.get("DEEPSEEK_PROXY_WEB_SEARCH_PROVIDER") or os.environ.get("DEEPSEEK_PROXY_WEB_SEARCH_PROVIDER") or "serpapi").strip().lower()
        keys = _WEB_SEARCH_PROVIDER_ENV_KEYS.get(provider) or []
        api_key, source, env_key = _provider_probe_secret(keys, env_values, env_file)
        policy, policy_source = _tool_routing_policy_from_env_values(kind, env_values)
        return {
            "kind": kind,
            "provider": provider,
            "configured": bool(api_key),
            "api_key_source": source,
            "api_key_env_key": env_key,
            "api_key_value_logged": False,
            "routing_policy": policy,
            "routing_policy_source": policy_source or "default:auto",
            "routing_env_key": _tool_routing_env_key(kind),
            "managed_function_name": "codeepseedex_web_search",
            "action": None if api_key else "run dsproxy config set-web-search-api-key --provider serpapi|tavily|exa|firecrawl",
        }
    if kind == "image_generation":
        provider = _canonical_probe_image_provider(str(env_values.get("DEEPSEEK_PROXY_IMAGE_PROVIDER") or os.environ.get("DEEPSEEK_PROXY_IMAGE_PROVIDER") or "zhipu"))
        keys = _image_provider_probe_keys(provider, env_values)
        api_key, source, env_key = _provider_probe_secret(keys, env_values, env_file)
        policy, policy_source = _tool_routing_policy_from_env_values(kind, env_values)
        return {
            "kind": kind,
            "provider": provider,
            "configured": bool(api_key),
            "api_key_source": source,
            "api_key_env_key": env_key,
            "api_key_value_logged": False,
            "routing_policy": policy,
            "routing_policy_source": policy_source or "default:auto",
            "routing_env_key": _tool_routing_env_key(kind),
            "managed_function_name": "codeepseedex_generate_image",
            "action": None if api_key else "run dsproxy config set-image-api-key --provider zhipu|qwen_image|stability|fal",
        }
    raise ValueError(f"unsupported_tool_routing_kind:{kind}")


def _tool_routing_config_status(env_file: Path | None = None, env_values: dict[str, str] | None = None) -> dict[str, object]:
    env_path = env_file or default_env_file_path()
    values = env_values if env_values is not None else _read_env_exports(env_path)
    return {
        "enabled": _env_value_truthy(values.get("DEEPSEEK_PROXY_TOOL_BRIDGE", os.environ.get("DEEPSEEK_PROXY_TOOL_BRIDGE", "1"))),
        "policies": list(_TOOL_ROUTING_POLICY_VALUES),
        "web_search": _tool_routing_provider_config_status("web_search", values, env_path),
        "image_generation": _tool_routing_provider_config_status("image_generation", values, env_path),
    }


def _set_tool_routing_policy(args: argparse.Namespace, env_file: Path) -> int:
    kind = _canonical_tool_routing_kind(getattr(args, "tool", None))
    policy = _canonical_tool_routing_policy(getattr(args, "policy", None))
    if kind is None or policy is None:
        print(json.dumps({
            "status": "error",
            "error": "invalid_tool_routing_policy",
            "tool": getattr(args, "tool", None),
            "policy": getattr(args, "policy", None),
            "supported_tools": ["web-search", "image-generation"],
            "supported_policies": list(_TOOL_ROUTING_POLICY_VALUES),
        }, ensure_ascii=False, indent=2))
        return 2
    values = _read_env_exports(env_file)
    values["DEEPSEEK_PROXY_TOOL_BRIDGE"] = "1"
    env_key = _tool_routing_env_key(kind)
    values[env_key] = policy
    _write_env_exports(env_file, values)
    status = _tool_routing_config_status(env_file, values)
    output = {
        "status": "ok",
        "env_file": str(env_file),
        "tool": kind,
        "routing_policy": policy,
        "routing_env_key": env_key,
        "tool_routing": status,
        "post_config_apply": _post_config_apply_for_args(args),
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0

def _doctor_provider_probe_result(
    kind: str,
    provider: str,
    *,
    env_values: dict[str, str],
    env_file: Path,
    live: bool,
    allow_spend: bool,
    timeout: float,
    prompt: str,
) -> dict[str, Any]:
    if kind == "web_search":
        keys = _WEB_SEARCH_PROVIDER_ENV_KEYS.get(provider)
        if not keys:
            return {
                "ok": False,
                "kind": kind,
                "provider": provider,
                "configured": False,
                "error": "unsupported_web_search_provider",
                "supported_providers": list(_WEB_SEARCH_PROVIDER_ENV_KEYS),
            }
        api_key, source, env_key = _provider_probe_secret(keys, env_values, env_file)
        result: dict[str, Any] = {
            "kind": kind,
            "provider": provider,
            "configured": bool(api_key),
            "api_key_source": source,
            "api_key_env_key": env_key,
            "api_key_value_logged": False,
            "live_requested": bool(live),
        }
        if not live:
            result["ok"] = bool(api_key)
            result["status"] = "configured" if api_key else "missing_api_key"
            return result
        if not allow_spend:
            result.update({
                "ok": False,
                "status": "error",
                "error": "allow_spend_required",
                "message": "Live web search probes may consume provider search quota. Re-run with --allow-spend.",
            })
            return result
        if not api_key:
            result.update({"ok": False, "status": "error", "error": "missing_api_key"})
            return result
        probe = _validate_web_search_api_key(provider, api_key, timeout=timeout)
        result.update({
            "ok": bool(probe.get("ok")),
            "status": "ok" if probe.get("ok") else "error",
            "probe": probe,
        })
        return result

    if kind == "image_generation":
        canonical = _canonical_probe_image_provider(provider)
        keys = _image_provider_probe_keys(canonical, env_values)
        if not keys:
            return {
                "ok": False,
                "kind": kind,
                "provider": canonical,
                "configured": False,
                "error": "unsupported_image_provider",
                "supported_providers": list(_IMAGE_PROVIDER_ENV_KEYS),
            }
        api_key, source, env_key = _provider_probe_secret(keys, env_values, env_file)
        result = {
            "kind": kind,
            "provider": canonical,
            "configured": bool(api_key),
            "api_key_source": source,
            "api_key_env_key": env_key,
            "api_key_value_logged": False,
            "live_requested": bool(live),
        }
        if not live:
            result["ok"] = bool(api_key)
            result["status"] = "configured" if api_key else "missing_api_key"
            return result
        if not allow_spend:
            result.update({
                "ok": False,
                "status": "error",
                "error": "allow_spend_required",
                "message": "Live image generation probes create a real image and may consume provider credits. Re-run with --allow-spend.",
            })
            return result
        if not api_key:
            result.update({"ok": False, "status": "error", "error": "missing_api_key"})
            return result
        probe = _live_image_generation_probe(canonical, api_key, timeout=timeout, prompt=prompt)
        result.update({
            "ok": bool(probe.get("ok")),
            "status": "ok" if probe.get("ok") else "error",
            "probe": probe,
        })
        return result

    return {"ok": False, "kind": kind, "provider": provider, "error": "unsupported_provider_kind"}


def _doctor_providers(args: argparse.Namespace) -> int:
    env_file = Path(args.env_file).expanduser() if getattr(args, "env_file", None) else default_env_file_path()
    env_file, env_values = _provider_probe_env_values(env_file)
    kind = str(getattr(args, "kind", "all") or "all").strip().lower()
    provider = str(getattr(args, "provider", "all") or "all").strip().lower()
    live = bool(getattr(args, "live", False))
    allow_spend = bool(getattr(args, "allow_spend", False))
    timeout = float(getattr(args, "timeout", 10.0))
    prompt = str(getattr(args, "prompt", "") or _PROVIDER_PROBE_PROMPT).strip() or _PROVIDER_PROBE_PROMPT

    targets = _provider_probe_web_targets(kind, provider)
    if not targets:
        output = {
            "status": "error",
            "error": "no_provider_targets",
            "kind": kind,
            "provider": provider,
            "supported_kinds": ["all", "web-search", "image"],
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 1

    results = [
        _doctor_provider_probe_result(
            item_kind,
            item_provider,
            env_values=env_values,
            env_file=env_file,
            live=live,
            allow_spend=allow_spend,
            timeout=timeout,
            prompt=prompt,
        )
        for item_kind, item_provider in targets
    ]
    output = {
        "status": "ok" if all(bool(item.get("ok")) for item in results) else "partial",
        "command": "doctor providers",
        "env_file": str(env_file),
        "kind": kind,
        "provider": provider,
        "live": live,
        "allow_spend": allow_spend,
        "api_key_values_logged": False,
        "results": results,
    }
    if live:
        output["warning"] = "Live provider probes can consume external provider quota or image credits."
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if (not live or all(bool(item.get("ok")) for item in results)) else 1





def _doctor_tool_routing_summary(args: argparse.Namespace) -> dict[str, object]:
    thinking = bool(getattr(args, "thinking", False))
    port = _port_for(thinking, getattr(args, "port", None))
    timeout = float(getattr(args, "timeout", 3.0) or 3.0)
    env_file = Path(getattr(args, "env_file", "")).expanduser() if getattr(args, "env_file", None) else default_env_file_path()
    env_values = _read_env_exports(env_file)
    config_status = _tool_routing_config_status(env_file, env_values)
    url = f"{_base_url(thinking=thinking, port=port)}/v1/proxy/tool-bridge/status"
    http_status, data, error = _http_json(url, timeout=timeout)
    runtime_available = http_status == 200 and isinstance(data, dict)
    tool_bridge = data.get("tool_bridge") if isinstance(data, dict) else None
    if not isinstance(tool_bridge, dict):
        tool_bridge = {}
    managed_runtime = tool_bridge.get("managed_tool_routing") if isinstance(tool_bridge.get("managed_tool_routing"), dict) else {}

    tools: dict[str, object] = {}
    for kind in ["web_search", "image_generation"]:
        configured = config_status.get(kind) if isinstance(config_status.get(kind), dict) else {}
        runtime_item = tool_bridge.get(kind) if isinstance(tool_bridge.get(kind), dict) else {}
        tools[kind] = {
            "provider": runtime_item.get("provider", configured.get("provider")),
            "configured": runtime_item.get("configured", configured.get("configured")),
            "routing_policy": runtime_item.get("routing_policy", configured.get("routing_policy")),
            "managed_function_name": runtime_item.get("managed_function_name", configured.get("managed_function_name")),
            "last_route_decision": runtime_item.get("last_route_decision"),
            "last_execution": runtime_item.get("last_execution"),
            "native_tool_observed": runtime_item.get("native_tool_observed"),
            "no_native_tool_observed": runtime_item.get("no_native_tool_observed"),
            "diagnostic": runtime_item.get("diagnostic"),
            "config": configured,
        }

    aggregate_execution = managed_runtime.get("last_execution") if isinstance(managed_runtime, dict) else None
    end_to_end_status = "tested" if isinstance(aggregate_execution, dict) and aggregate_execution.get("attempted") else "not_tested"
    return {
        "status": "ok" if runtime_available else "runtime_unavailable",
        "command": "doctor tool-routing",
        "target": "thinking" if thinking else "stable",
        "port": port,
        "env_file": str(env_file),
        "runtime": {
            "available": runtime_available,
            "url": url,
            "http_status": http_status,
            "error": error,
        },
        "native_tool_routing": {
            "available": bool(runtime_available and managed_runtime.get("enabled") is True),
            "enabled": managed_runtime.get("enabled") if managed_runtime else config_status.get("enabled"),
            "instruction_enabled": managed_runtime.get("instruction_enabled") if managed_runtime else None,
            "end_to_end_managed_route": end_to_end_status,
            "last_execution": aggregate_execution,
            "no_native_tools_observed": managed_runtime.get("no_native_tools_observed") if managed_runtime else [],
            "no_tool_call_diagnostics": managed_runtime.get("no_tool_call_diagnostics") if managed_runtime else [],
        },
        "tools": tools,
        "config": config_status,
        "api_key_values_logged": False,
        "live_probe_performed": False,
        "live_probe_warning": "No live provider request is performed by doctor tool-routing. Use doctor providers --live --allow-spend for quota-consuming checks.",
    }


def _doctor_tool_routing(args: argparse.Namespace) -> int:
    payload = _doctor_tool_routing_summary(args)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0

def _doctor(args: argparse.Namespace) -> int:
    if getattr(args, "doctor_command", None) == "providers":
        return _doctor_providers(args)
    if getattr(args, "doctor_command", None) == "tool-routing":
        return _doctor_tool_routing(args)

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
    checks["tool_routing"] = _doctor_tool_routing_summary(args)

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



def _mask_api_key(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "***"
    return value[:4] + "..." + value[-4:]


def _load_deepseek_api_key(*, env_file: Path | None = None) -> tuple[str, str | None]:
    env_value = os.environ.get("DEEPSEEK_API_KEY", "")
    if env_value:
        return env_value, "environment"
    path = env_file or default_env_file_path()
    values = _read_env_exports(path)
    file_value = values.get("DEEPSEEK_API_KEY", "")
    if file_value:
        return file_value, str(path)
    return "", str(path)



def _model_api_validation_url(base_url: str, path: str) -> str:
    return base_url.rstrip("/") + "/" + path.lstrip("/")


def _validate_model_api_key(
    provider: str,
    api_key: str,
    *,
    base_url: str | None = None,
    timeout: float,
) -> dict[str, Any]:
    canonical = _canonical_model_api_provider(provider)
    if not api_key:
        return {
            "ok": False,
            "status": "error",
            "kind": "model_api",
            "provider": canonical,
            "error": "missing_model_api_key",
            "message": "Model API key is required.",
        }
    try:
        config = _model_api_provider_config(canonical)
    except ValueError:
        return {
            "ok": False,
            "status": "error",
            "kind": "model_api",
            "provider": canonical,
            "error": "unsupported_model_api_provider",
            "supported_providers": _supported_model_api_providers(),
        }
    resolved_base_url = (base_url or config.get("base_url") or "").strip().rstrip("/")
    if not resolved_base_url:
        return {
            "ok": False,
            "status": "error",
            "kind": "model_api",
            "provider": canonical,
            "error": "missing_model_base_url",
            "message": "Custom model API providers require --base-url.",
        }
    validation_url = _model_api_validation_url(resolved_base_url, config.get("validation_path", "/models"))
    request = urllib.request.Request(
        validation_url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            ok = 200 <= int(response.status) < 300
            return {
                "ok": ok,
                "status": "ok" if ok else "error",
                "kind": "model_api",
                "provider": canonical,
                "base_url": resolved_base_url,
                "url": validation_url,
                "http_status": int(response.status),
                "body_preview": raw[:500] if raw else "",
            }
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        return {
            "ok": False,
            "status": "error",
            "kind": "model_api",
            "provider": canonical,
            "base_url": resolved_base_url,
            "url": validation_url,
            "error": "http_error",
            "http_status": exc.code,
            "body_preview": raw[:1000],
        }
    except Exception as exc:
        return {
            "ok": False,
            "status": "error",
            "kind": "model_api",
            "provider": canonical,
            "base_url": resolved_base_url,
            "url": validation_url,
            "error": type(exc).__name__,
            "message": str(exc),
        }

def _check_deepseek_api_key(api_key: str, *, url: str, timeout: float) -> dict[str, Any]:
    if not api_key:
        return {
            "ok": False,
            "status": "error",
            "error": "missing_deepseek_api_key",
            "message": "DEEPSEEK_API_KEY is empty.",
        }

    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            try:
                data = json.loads(raw.decode("utf-8"))
            except Exception:
                data = {"raw_preview": raw[:500].decode("utf-8", errors="replace")}
            return {
                "ok": 200 <= int(response.status) < 300,
                "status": "ok" if 200 <= int(response.status) < 300 else "error",
                "http_status": int(response.status),
                "url": url,
                "balance": data,
            }
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:500]
        return {
            "ok": False,
            "status": "error",
            "http_status": int(exc.code),
            "url": url,
            "error": "http_error",
            "body_preview": body,
        }
    except Exception as exc:
        return {
            "ok": False,
            "status": "error",
            "url": url,
            "error": type(exc).__name__,
            "message": str(exc)[:500],
        }


def _provider_auth_error_detected(data: Any) -> str | None:
    if not isinstance(data, dict):
        return None

    values: list[str] = []

    def collect(value: Any) -> None:
        if isinstance(value, str) and value.strip():
            values.append(value.strip())
        elif isinstance(value, (int, float)):
            values.append(str(value))
        elif isinstance(value, dict):
            for nested in ("error", "error_message", "message", "msg", "detail", "code", "status_code"):
                collect(value.get(nested))
        elif isinstance(value, list):
            for item in value[:5]:
                collect(item)

    for key in ("error", "error_message", "message", "msg", "detail", "code", "status_code"):
        collect(data.get(key))

    auth_tokens = (
        "unauthorized",
        "forbidden",
        "api key",
        "api-key",
        "apikey",
        "access key",
        "access token",
        "token",
        "authentication",
        "authorization",
        "auth",
        "invalid api key",
        "invalid apikey",
        "invalid token",
        "invalid authentication",
        "invalid authorization",
    )
    auth_codes = {"1002", "401", "403"}

    for value in values:
        lowered = value.lower()
        if lowered in auth_codes or any(token in lowered for token in auth_tokens):
            return value[:300]
    return None


def _provider_error_body_detected(data: Any) -> str | None:
    if not isinstance(data, dict):
        return None

    def first_value(value: Any) -> str | None:
        if isinstance(value, str) and value.strip():
            return value.strip()[:300]
        if isinstance(value, (int, float)):
            return str(value)[:300]
        if isinstance(value, dict):
            for nested in ("error", "error_message", "message", "msg", "detail", "code", "status_code"):
                nested_value = first_value(value.get(nested))
                if nested_value:
                    return nested_value
        if isinstance(value, list):
            for item in value[:5]:
                item_value = first_value(item)
                if item_value:
                    return item_value
        return None

    for key in ("error", "error_message", "message", "msg", "detail"):
        value = first_value(data.get(key))
        if value:
            return value

    status = str(data.get("status") or "").strip().lower()
    if status in {"error", "failed", "failure"}:
        return status
    return None


def _validation_http_json(
    *,
    provider: str,
    kind: str,
    method: str,
    url: str,
    endpoint: str,
    headers: dict[str, str] | None = None,
    payload: dict[str, Any] | None = None,
    timeout: float = 10.0,
    ok_statuses: tuple[int, ...] = (200,),
    allow_provider_error_body: bool = False,
    validation_method: str = "http_probe",
    may_consume_quota: bool = False,
    require_provider_error_body: bool = False,
    validation_strength: str = "http_status",
    functional_probe: bool = False,
    warning: str | None = None,
) -> dict[str, Any]:
    encoded_payload: bytes | None = None
    request_headers = dict(headers or {})
    if payload is not None:
        encoded_payload = json.dumps(payload).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/json")
    request_headers.setdefault("Accept", "application/json")

    def make_result(http_status: int, raw: bytes) -> dict[str, Any]:
        try:
            data = json.loads(raw.decode("utf-8"))
        except Exception:
            data = {"raw_preview": raw[:500].decode("utf-8", errors="replace")}
        auth_error = _provider_auth_error_detected(data)
        provider_error = _provider_error_body_detected(data)
        provider_error_acceptance = bool(
            provider_error
            and allow_provider_error_body
            and not auth_error
            and (int(http_status) in ok_statuses or 200 <= int(http_status) < 300)
        )
        ok = int(http_status) in ok_statuses or provider_error_acceptance
        if auth_error:
            ok = False
        elif ok and require_provider_error_body and not provider_error:
            ok = False
        elif ok and provider_error and not allow_provider_error_body:
            ok = False
        result = {
            "ok": ok,
            "status": "ok" if ok else "error",
            "kind": kind,
            "provider": provider,
            "validation_method": validation_method,
            "http_status": int(http_status),
            "endpoint": endpoint,
            "may_consume_quota": bool(may_consume_quota),
            "require_provider_error_body": bool(require_provider_error_body),
            "provider_error_accepted": bool(provider_error_acceptance),
            "validation_strength": validation_strength,
            "functional_probe": bool(functional_probe),
            "functional_validation": "performed" if functional_probe else "not_performed",
        }
        if warning:
            result["warning"] = warning
        if auth_error:
            result["error"] = "auth_error_response"
            result["message"] = auth_error
        elif require_provider_error_body and (int(http_status) in ok_statuses or 200 <= int(http_status) < 300) and not provider_error:
            result["error"] = "missing_provider_error_body"
            result["message"] = "Expected a provider validation error body for non-generation probe."
        elif provider_error and not allow_provider_error_body:
            result["error"] = "provider_error_response"
            result["message"] = provider_error
        else:
            result["response_keys"] = sorted(data.keys())[:12] if isinstance(data, dict) else []
        return result

    request = urllib.request.Request(url, data=encoded_payload, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return make_result(int(response.status), response.read())
    except urllib.error.HTTPError as exc:
        body = exc.read()
        result = make_result(int(exc.code), body)
        if not result.get("ok"):
            result.setdefault("error", "http_error")
            result.setdefault("body_preview", body[:500].decode("utf-8", errors="replace"))
        return result
    except Exception as exc:
        return {
            "ok": False,
            "status": "error",
            "kind": kind,
            "provider": provider,
            "validation_method": validation_method,
            "endpoint": endpoint,
            "error": type(exc).__name__,
            "message": str(exc)[:500],
            "may_consume_quota": bool(may_consume_quota),
            "validation_strength": validation_strength,
            "functional_probe": bool(functional_probe),
            "functional_validation": "performed" if functional_probe else "not_performed",
            **({"warning": warning} if warning else {}),
        }
def _validate_web_search_api_key(provider: str, api_key: str, *, timeout: float = 10.0) -> dict[str, Any]:
    selected = provider.strip().lower()
    if not api_key:
        return {
            "ok": False,
            "status": "error",
            "kind": "web_search",
            "provider": selected,
            "error": "missing_api_key",
        }

    query = "test"
    web_search_validation_warning = "This performs a live low-result search request and may consume provider search quota."
    if selected == "serpapi":
        params = urllib.parse.urlencode({"engine": "google", "q": query, "api_key": api_key, "num": "1"})
        return _validation_http_json(
            provider="serpapi",
            kind="web_search",
            method="GET",
            url=f"https://serpapi.com/search.json?{params}",
            endpoint="https://serpapi.com/search.json",
            timeout=timeout,
            validation_method="fixed_query_search",
            may_consume_quota=True,
            validation_strength="live_query_probe",
            functional_probe=True,
            warning=web_search_validation_warning,
        )
    if selected == "tavily":
        return _validation_http_json(
            provider="tavily",
            kind="web_search",
            method="POST",
            url="https://api.tavily.com/search",
            endpoint="https://api.tavily.com/search",
            headers={"Authorization": f"Bearer {api_key}"},
            payload={"query": query, "max_results": 1, "search_depth": "basic", "include_answer": False},
            timeout=timeout,
            validation_method="fixed_query_search",
            may_consume_quota=True,
            validation_strength="live_query_probe",
            functional_probe=True,
            warning=web_search_validation_warning,
        )
    if selected == "exa":
        return _validation_http_json(
            provider="exa",
            kind="web_search",
            method="POST",
            url="https://api.exa.ai/search",
            endpoint="https://api.exa.ai/search",
            headers={"Authorization": f"Bearer {api_key}"},
            payload={"query": query, "numResults": 1},
            timeout=timeout,
            validation_method="fixed_query_search",
            may_consume_quota=True,
            validation_strength="live_query_probe",
            functional_probe=True,
            warning=web_search_validation_warning,
        )
    if selected == "firecrawl":
        return _validation_http_json(
            provider="firecrawl",
            kind="web_search",
            method="POST",
            url="https://api.firecrawl.dev/v2/search",
            endpoint="https://api.firecrawl.dev/v2/search",
            headers={"Authorization": f"Bearer {api_key}"},
            payload={"query": query, "limit": 1},
            timeout=timeout,
            validation_method="fixed_query_search",
            may_consume_quota=True,
            validation_strength="live_query_probe",
            functional_probe=True,
            warning=web_search_validation_warning,
        )
    return {
        "ok": False,
        "status": "error",
        "kind": "web_search",
        "provider": selected,
        "error": "unsupported_web_search_provider",
        "supported_providers": ["serpapi", "tavily", "exa", "firecrawl"],
    }


_NON_GENERATION_IMAGE_PROBE_WARNING = (
    "This non-generating authentication probe checks whether the provider accepts the key and endpoint, "
    "but it does not prove that real image generation can produce an image."
)
_IMAGE_METADATA_PROBE_WARNING = (
    "This non-generating provider metadata or account probe checks the key without creating an image, "
    "but it does not prove that real image generation can produce an image."
)


def _validate_image_api_key(provider: str, api_key: str, *, timeout: float = 10.0) -> dict[str, Any]:
    selected = _canonical_probe_image_provider(provider)
    if not api_key:
        return {
            "ok": False,
            "status": "error",
            "kind": "image_generation",
            "provider": selected,
            "error": "missing_api_key",
        }

    if selected in {"glm", "zai"}:
        return _validation_http_json(
            provider=selected,
            kind="image_generation",
            method="POST",
            url="https://api.z.ai/api/paas/v4/images/generations",
            endpoint="https://api.z.ai/api/paas/v4/images/generations",
            headers={"Authorization": f"Bearer {api_key}"},
            payload={},
            timeout=timeout,
            ok_statuses=(400, 422),
            allow_provider_error_body=True,
            require_provider_error_body=True,
            validation_method="non_generation_auth_probe",
            may_consume_quota=False,
            validation_strength="auth_probe",
            functional_probe=False,
            warning=_NON_GENERATION_IMAGE_PROBE_WARNING,
        )
    if selected in {"zhipu", "zhipuai", "bigmodel"}:
        return _validation_http_json(
            provider=selected,
            kind="image_generation",
            method="POST",
            url="https://open.bigmodel.cn/api/paas/v4/images/generations",
            endpoint="https://open.bigmodel.cn/api/paas/v4/images/generations",
            headers={"Authorization": f"Bearer {api_key}"},
            payload={},
            timeout=timeout,
            ok_statuses=(400, 422),
            allow_provider_error_body=True,
            require_provider_error_body=True,
            validation_method="non_generation_auth_probe",
            may_consume_quota=False,
            validation_strength="auth_probe",
            functional_probe=False,
            warning=_NON_GENERATION_IMAGE_PROBE_WARNING,
        )
    if _is_qwen_image_provider(selected):
        info = _qwen_image_region_status(selected)
        if not bool(info.get("model_available")):
            return _qwen_image_region_unavailable_result(selected)
        endpoint = (
            os.environ.get("DEEPSEEK_PROXY_IMAGE_BASE_URL")
            or os.environ.get("DASHSCOPE_IMAGE_ENDPOINT")
            or str(info.get("endpoint") or "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation")
        )
        return _validation_http_json(
            provider=selected,
            kind="image_generation",
            method="POST",
            url=endpoint,
            endpoint=endpoint,
            headers={"Authorization": f"Bearer {api_key}"},
            payload={},
            timeout=timeout,
            ok_statuses=(400, 422),
            allow_provider_error_body=True,
            require_provider_error_body=True,
            validation_method="non_generation_auth_probe",
            may_consume_quota=False,
            validation_strength="auth_probe",
            functional_probe=False,
            warning=_NON_GENERATION_IMAGE_PROBE_WARNING,
        )
    if selected in {"stability", "stability_ai", "stable_image"}:
        return _validation_http_json(
            provider="stability",
            kind="image_generation",
            method="GET",
            url="https://api.stability.ai/v1/user/balance",
            endpoint="https://api.stability.ai/v1/user/balance",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
            validation_method="account_balance_probe",
            may_consume_quota=False,
            validation_strength="account_probe",
            functional_probe=False,
            warning=_IMAGE_METADATA_PROBE_WARNING,
        )
    if selected in {"fal", "fal_ai", "fal.ai"}:
        params = urllib.parse.urlencode({"endpoint_id": "fal-ai/flux/schnell", "limit": "1"})
        return _validation_http_json(
            provider="fal",
            kind="image_generation",
            method="GET",
            url=f"https://api.fal.ai/v1/models?{params}",
            endpoint="https://api.fal.ai/v1/models",
            headers={"Authorization": f"Key {api_key}"},
            timeout=timeout,
            validation_method="model_metadata_probe",
            may_consume_quota=False,
            validation_strength="metadata_probe",
            functional_probe=False,
            warning=_IMAGE_METADATA_PROBE_WARNING,
        )
    return {
        "ok": False,
        "status": "error",
        "kind": "image_generation",
        "provider": selected,
        "error": "unsupported_image_provider",
        "supported_providers": ["zai", "zhipu", "zhipuai", "bigmodel", "qwen_image", "qwen_image_beijing", "qwen_image_singapore", "qwen_image_us", "qwen_image_germany", "stability", "fal"],
    }
def _skipped_validation(kind: str, provider: str) -> dict[str, Any]:
    return {
        "ok": None,
        "status": "skipped",
        "kind": kind,
        "provider": provider,
        "skipped": True,
        "message": "Validation was skipped by user request.",
        "validation_strength": "skipped",
        "functional_probe": False,
        "functional_validation": "not_performed",
    }


def _image_generation_base_url_for_provider(provider: str | None) -> str:
    selected = str(provider or "").strip().lower()
    if selected in {"zhipu", "zhipuai", "bigmodel"}:
        return "https://open.bigmodel.cn/api/paas/v4/images/generations"
    if selected in {"glm", "zai", "z.ai"}:
        return "https://api.z.ai/api/paas/v4/images/generations"
    if _is_qwen_image_provider(selected):
        info = _qwen_image_region_status(selected)
        return str(info.get("endpoint") or "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation")
    return ""

def _mask_env_secret(key: str, value: str) -> str:
    upper = key.upper()
    if any(token in upper for token in ("API_KEY", "TOKEN", "SECRET", "PASSWORD")) or upper in {"FAL_KEY"}:
        return "***" if value else value
    return value


def _release_tag_matches_runtime(tag: str, runtime_version: str = PROXY_VERSION) -> bool:
    normalized_tag = str(tag or "").strip()
    normalized_runtime = str(runtime_version or "").strip()
    if not normalized_tag or not normalized_runtime:
        return True
    return normalized_tag == normalized_runtime or normalized_tag.startswith(normalized_runtime + "-")


def _startup_release_check_mode() -> str:
    value = (
        os.environ.get("DEEPSEEK_PROXY_RELEASE_CHECK")
        or os.environ.get("CODEEPSEEDEX_RELEASE_CHECK")
        or "auto"
    )
    return str(value).strip().lower()


def _startup_release_check_enabled() -> bool:
    mode = _startup_release_check_mode()
    if mode in {"0", "false", "no", "off", "disabled", "never"}:
        return False
    if mode in {"1", "true", "yes", "on", "enabled", "always"}:
        return True
    return bool(getattr(sys.stderr, "isatty", lambda: False)())


def _maybe_print_startup_release_update_notice() -> None:
    if not _startup_release_check_enabled():
        return
    try:
        latest_tag, release = _resolve_latest_release_tag(timeout=float(os.environ.get("DEEPSEEK_PROXY_RELEASE_CHECK_TIMEOUT", "1.5")))
    except Exception:
        return
    if _release_tag_matches_runtime(latest_tag):
        return
    release_url = release.get("html_url") if isinstance(release, dict) else None
    print(
        f"[CoDeepSeedeX] update available: current runtime {PROXY_VERSION}, latest Release {latest_tag}. Run: dsproxy upgrade",
        file=sys.stderr,
    )
    if release_url:
        print(f"[CoDeepSeedeX] release notes: {release_url}", file=sys.stderr)


def _model_api_config_status(env_file: Path | None = None, values: dict[str, str] | None = None) -> dict[str, Any]:
    path = env_file or default_env_file_path()
    env_values = values if values is not None else _read_env_exports(path)
    provider = _canonical_model_api_provider(env_values.get("DEEPSEEK_PROXY_MODEL_PROVIDER") or "deepseek")
    try:
        provider_config = _model_api_provider_config(provider)
    except ValueError:
        provider_config = {"base_url": "", "model": "", "validation_path": "/models", "display_name": provider}
    base_url = str(env_values.get("DEEPSEEK_BASE_URL") or provider_config.get("base_url") or "").strip().rstrip("/")
    model = str(env_values.get("DEEPSEEK_PROXY_MODEL") or provider_config.get("model") or "").strip()
    api_key = env_values.get("DEEPSEEK_API_KEY") or os.environ.get("DEEPSEEK_API_KEY", "")
    validation_path = str(provider_config.get("validation_path") or "/models")
    validation_url = (
        str(getattr(argparse.Namespace(), "x", "") or "")
        or (_model_api_validation_url(base_url, validation_path) if base_url else "")
    )
    return {
        "provider": provider,
        "base_url": base_url,
        "model": model,
        "configured": bool(api_key and base_url and (model or provider != "custom")),
        "api_key_source": "env_file" if env_values.get("DEEPSEEK_API_KEY") else ("environment" if os.environ.get("DEEPSEEK_API_KEY") else None),
        "api_key_preview": _mask_api_key(api_key),
        "validation_command": "dsproxy config test-api-key",
        "validation_url": validation_url,
        "validation_method": "deepseek_balance" if provider == "deepseek" else "openai_compatible_models",
        "may_consume_quota": False,
    }



def _model_provider_registry_path(env_file: Path | None = None) -> Path:
    env_values = _read_env_exports(env_file or default_env_file_path())
    configured = env_values.get("DEEPSEEK_PROXY_MODEL_PROVIDER_REGISTRY") or os.environ.get("DEEPSEEK_PROXY_MODEL_PROVIDER_REGISTRY")
    if configured:
        return Path(configured).expanduser()
    base = (env_file or default_env_file_path()).expanduser().parent
    return base / "model-providers.json"


def _custom_provider_registry_slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", (value or "").strip().lower()).strip("-._")
    return slug or "custom-provider"


def _read_custom_provider_registry(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": 1, "active_provider": None, "providers": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8") or "{}")
    except Exception:
        data = {}
    if not isinstance(data, dict):
        data = {}
    providers = data.get("providers")
    if not isinstance(providers, dict):
        providers = {}
    data["providers"] = providers
    data.setdefault("version", 1)
    data.setdefault("active_provider", None)
    return data


def _write_custom_provider_registry(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def _redact_custom_provider_registry(data: dict[str, Any]) -> dict[str, Any]:
    redacted = {
        "version": data.get("version", 1),
        "active_provider": data.get("active_provider"),
        "providers": {},
    }
    for provider_id, entry in (data.get("providers") or {}).items():
        if not isinstance(entry, dict):
            continue
        item = dict(entry)
        api_key = str(item.pop("api_key", "") or "")
        item["api_key_configured"] = bool(api_key)
        item["api_key_preview"] = _mask_api_key(api_key)
        redacted["providers"][provider_id] = item
    return redacted


def _upsert_custom_provider_registry_entry(
    path: Path,
    *,
    display_name: str,
    base_url: str,
    model: str,
    api_key: str = "",
    make_active: bool = True,
) -> dict[str, Any]:
    display_name = (display_name or "Custom Provider").strip() or "Custom Provider"
    base_url = _normalize_openai_base_url_value(base_url or "")
    model = _clean_wizard_input_value(model or "")
    provider_id = _custom_provider_registry_slug(display_name)
    data = _read_custom_provider_registry(path)
    providers = data.setdefault("providers", {})
    entry = providers.get(provider_id)
    if not isinstance(entry, dict):
        entry = {}
    models = entry.get("models")
    if not isinstance(models, list):
        models = []
    if model and model not in models:
        models.append(model)
    capabilities = entry.get("capabilities")
    if not isinstance(capabilities, dict):
        capabilities = {}
    capabilities.setdefault("reasoning_effort", ["high"])
    capabilities.setdefault("reasoning_effort_max", False)
    entry.update({
        "id": provider_id,
        "type": "custom_openai_compatible",
        "display_name": display_name,
        "base_url": base_url,
        "active_model": model,
        "models": models,
        "capabilities": capabilities,
    })
    if api_key:
        entry["api_key"] = api_key
    providers[provider_id] = entry
    data["version"] = 1
    if make_active:
        data["active_provider"] = provider_id
    _write_custom_provider_registry(path, data)
    return data


def _custom_provider_registry_status(env_file: Path, values: dict[str, str]) -> dict[str, Any]:
    path = _model_provider_registry_path(env_file)
    data = _read_custom_provider_registry(path)
    return {
        "path": str(path),
        "exists": path.exists(),
        "active_provider": data.get("active_provider"),
        "registry": _redact_custom_provider_registry(data),
    }



def _custom_provider_codex_profile_name(provider_id: str, explicit: str | None = None) -> str:
    return _custom_provider_registry_slug(explicit or provider_id)


def _custom_provider_model_catalog_path(codex_config: Path | str | None = None) -> Path:
    codex_path = Path(codex_config).expanduser() if codex_config else default_codex_config_path()
    return codex_path.parent / "model-catalogs" / "codeepseedex-custom-providers.json"


def _write_custom_provider_model_catalog(
    codex_config: Path | str | None,
    *,
    provider_id: str,
    entry: dict[str, Any],
    model: str,
    context_window: int,
) -> Path:
    catalog_path = _custom_provider_model_catalog_path(codex_config)
    catalog_path.parent.mkdir(parents=True, exist_ok=True)
    if catalog_path.exists():
        try:
            data = json.loads(catalog_path.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    else:
        data = {}
    if not isinstance(data, dict):
        data = {}
    models = data.get("models")
    if not isinstance(models, list):
        models = []
    model_key = str(model or "").strip()
    models = [
        item for item in models
        if not (isinstance(item, dict) and str(item.get("id") or item.get("model") or item.get("name") or "").strip() == model_key)
    ]
    capabilities = _custom_provider_capabilities(entry)
    models.append({
        "id": model_key,
        "model": model_key,
        "name": model_key,
        "provider_id": provider_id,
        "provider_type": "custom_openai_compatible",
        "context_window_tokens": int(context_window),
        "max_context_window_tokens": int(context_window),
        "supports_reasoning_effort_max": bool(capabilities.get("reasoning_effort_max")),
        "visibility": "visible",
    })
    data.update({
        "version": 1,
        "source": "codeepseedex_custom_provider_registry",
        "models": models,
    })
    catalog_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return catalog_path


def _custom_provider_entry_for_profile(
    profile_name: str,
    *,
    env_file: Path | None = None,
    env_values: dict[str, str] | None = None,
    provider_name: str | None = None,
) -> dict[str, Any] | None:
    env_path = env_file or default_env_file_path()
    try:
        registry = _read_custom_provider_registry(_model_provider_registry_path(env_path))
    except Exception:
        return None
    providers = registry.get("providers")
    if not isinstance(providers, dict):
        return None
    candidates = [
        _custom_provider_registry_slug(profile_name),
        _custom_provider_registry_slug((provider_name or "").removesuffix("-proxy")),
        _custom_provider_registry_slug(str((env_values or {}).get("DEEPSEEK_PROXY_CUSTOM_PROVIDER_NAME") or "")),
        str(registry.get("active_provider") or "").strip(),
    ]
    for candidate in candidates:
        if candidate and isinstance(providers.get(candidate), dict):
            return providers[candidate]
    return None


def _profile_thinking_status(
    profile_name: str,
    provider_section: dict[str, str],
    env_values: dict[str, str],
) -> dict[str, object]:
    base_url = str(provider_section.get("base_url") or "")
    thinking_port = str(env_values.get("DEEPSEEK_PROXY_THINKING_PORT") or DEFAULT_THINKING_PORT).strip()
    if thinking_port and re.search(rf":{re.escape(thinking_port)}(?:/|$)", base_url):
        return {"enabled": True, "source": "provider_base_url"}
    if profile_name.endswith("thinking"):
        return {"enabled": True, "source": "profile_name"}
    return {"enabled": False, "source": "profile_name_and_provider_base_url"}


def _sync_custom_provider_codex_profile_from_entry(
    env_file: Path,
    *,
    entry: dict[str, Any],
    selected_model: str,
    profile_name: str | None = None,
    codex_config: Path | str | None = None,
) -> dict[str, Any]:
    provider_id = _custom_provider_registry_slug(str(entry.get("id") or entry.get("display_name") or "custom-provider"))
    codex_profile = _custom_provider_codex_profile_name(provider_id, profile_name)
    model = _clean_wizard_input_value(selected_model or str(entry.get("active_model") or ""))
    if not model:
        return {"status": "error", "error": "custom_provider_model_missing", "provider_id": provider_id, "profile": codex_profile}
    env_values = _read_env_exports(env_file)
    codex_path = Path(codex_config).expanduser() if codex_config else default_codex_config_path()
    thinking_port = str(env_values.get("DEEPSEEK_PROXY_THINKING_PORT") or os.environ.get("DEEPSEEK_PROXY_THINKING_PORT") or DEFAULT_THINKING_PORT).strip() or str(DEFAULT_THINKING_PORT)
    local_base_url = f"http://127.0.0.1:{thinking_port}/v1"
    provider_name = f"{codex_profile}-proxy"
    context_window = DEFAULT_CONTEXT_WINDOW_TOKENS
    auto_compact_ratio = _auto_compact_ratio_from_env_values(env_values)
    auto_compact_token_limit = _derive_auto_compact_token_limit(context_window, auto_compact_ratio)
    deepseek_effort, effort_capability = _custom_provider_effective_reasoning_effort(entry, env_values)
    codex_effort = _codex_model_reasoning_effort_for_custom_provider(deepseek_effort, entry)
    catalog_path = _write_custom_provider_model_catalog(
        codex_path,
        provider_id=provider_id,
        entry=entry,
        model=model,
        context_window=context_window,
    )
    profile_path = codex_profile_config_path(codex_profile, codex_path)
    provider_header, provider_block, _profile_header, profile_block = _codex_profile_blocks(
        profile_name=codex_profile,
        provider_name=provider_name,
        base_url=local_base_url,
        model=model,
        reasoning_effort=codex_effort,
        context_window=context_window,
        auto_compact_token_limit=auto_compact_token_limit,
        tool_output_token_limit=12_000,
        model_catalog_json=str(catalog_path),
    )
    original = codex_path.read_text(encoding="utf-8") if codex_path.exists() else ""
    updated, provider_existed = _upsert_toml_table(original, provider_header, provider_block)
    updated, cleanup = _cleanup_main_codex_config_for_profile(updated, codex_profile)
    before_profile = profile_path.read_text(encoding="utf-8") if profile_path.exists() else ""
    codex_path.parent.mkdir(parents=True, exist_ok=True)
    codex_path.write_text(updated, encoding="utf-8")
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_text(profile_block, encoding="utf-8")
    return {
        "status": "ok",
        "provider_id": provider_id,
        "provider_name": entry.get("display_name") or provider_id,
        "profile": codex_profile,
        "provider": provider_name,
        "codex_config": str(codex_path),
        "codex_profile_config": str(profile_path),
        "base_url": local_base_url,
        "model": model,
        "provider_existed": provider_existed,
        "profile_existed": bool(before_profile),
        "main_config_changed": updated != original,
        "profile_config_changed": before_profile != profile_block,
        "legacy_profile_table_removed": cleanup["legacy_profile_table_removed"],
        "legacy_profile_selector_removed": cleanup["legacy_profile_selector_removed"],
        "codex_command": f"codex --profile {codex_profile}",
        "model_catalog_json": str(catalog_path),
        "deepseek_reasoning_effort": deepseek_effort,
        "codex_model_reasoning_effort": codex_effort,
        "reasoning_effort_capability": effort_capability,
    }


def _remove_custom_provider_codex_profile(
    *,
    provider_id: str,
    profile_name: str | None = None,
    codex_config: Path | str | None = None,
) -> dict[str, Any]:
    codex_profile = _custom_provider_codex_profile_name(provider_id, profile_name)
    codex_path = Path(codex_config).expanduser() if codex_config else default_codex_config_path()
    provider_name = f"{codex_profile}-proxy"
    profile_path = codex_profile_config_path(codex_profile, codex_path)
    original = codex_path.read_text(encoding="utf-8") if codex_path.exists() else ""
    updated, cleanup = _cleanup_main_codex_config_for_profile(original, codex_profile)
    updated, provider_removed = _remove_toml_table(updated, f"[model_providers.{provider_name}]")
    profile_removed = profile_path.exists()
    if codex_path.exists() or updated.strip():
        codex_path.parent.mkdir(parents=True, exist_ok=True)
        codex_path.write_text(updated, encoding="utf-8")
    if profile_path.exists():
        profile_path.unlink()
    return {
        "status": "ok",
        "profile": codex_profile,
        "provider": provider_name,
        "codex_config": str(codex_path),
        "codex_profile_config": str(profile_path),
        "profile_removed": bool(profile_removed or cleanup["legacy_profile_table_removed"]),
        "profile_file_removed": profile_removed,
        "provider_removed": provider_removed,
        "legacy_profile_table_removed": cleanup["legacy_profile_table_removed"],
        "legacy_profile_selector_removed": cleanup["legacy_profile_selector_removed"],
    }

def _apply_custom_provider_registry_entry(
    env_file: Path,
    *,
    provider_name: str,
    model: str | None = None,
    profile_name: str | None = None,
    codex_config: Path | str | None = None,
    sync_profile: bool = True,
) -> dict[str, Any]:
    path = _model_provider_registry_path(env_file)
    data = _read_custom_provider_registry(path)
    provider_id = _custom_provider_registry_slug(provider_name)
    entry = (data.get("providers") or {}).get(provider_id)
    if not isinstance(entry, dict):
        raise ValueError(f"custom_provider_not_found:{provider_name}")
    selected_model = _clean_wizard_input_value(model or entry.get("active_model") or "")
    if not selected_model:
        raise ValueError(f"custom_provider_model_missing:{provider_name}")
    models = entry.setdefault("models", [])
    if selected_model not in models:
        models.append(selected_model)
    entry["active_model"] = selected_model
    data["active_provider"] = provider_id
    _write_custom_provider_registry(path, data)

    values = _read_env_exports(env_file)
    values["DEEPSEEK_PROXY_MODEL_PROVIDER"] = "custom"
    values["DEEPSEEK_PROXY_CUSTOM_PROVIDER_NAME"] = str(entry.get("display_name") or provider_name)
    values["DEEPSEEK_BASE_URL"] = str(entry.get("base_url") or "")
    values["DEEPSEEK_PROXY_MODEL"] = selected_model
    values["DEEPSEEK_PROXY_MODEL_PROVIDER_REGISTRY"] = str(path)
    if entry.get("api_key"):
        values["DEEPSEEK_API_KEY"] = str(entry.get("api_key") or "")
    values["DEEPSEEK_PROXY_FORCE_MODEL"] = values.get("DEEPSEEK_PROXY_FORCE_MODEL", "1")
    custom_effort, effort_capability = _custom_provider_effective_reasoning_effort(entry, values)
    values["DEEPSEEK_REASONING_EFFORT"] = custom_effort
    _write_env_exports(env_file, values)

    output = {
        "status": "ok",
        "env_file": str(env_file),
        "registry_path": str(path),
        "provider_id": provider_id,
        "provider_name": entry.get("display_name") or provider_name,
        "provider_type": "custom_openai_compatible",
        "base_url": entry.get("base_url"),
        "active_model": selected_model,
        "models": models,
        "api_key_configured": bool(entry.get("api_key")),
        "api_key_preview": _mask_api_key(str(entry.get("api_key") or "")),
        "deepseek_reasoning_effort": custom_effort,
        "reasoning_effort_capability": effort_capability,
    }
    should_sync_profile = bool(sync_profile) and (
        codex_config is not None or env_file.expanduser() == default_env_file_path()
    )
    if should_sync_profile:
        output["provider_codex_profile_sync"] = _sync_custom_provider_codex_profile_from_entry(
            env_file,
            entry=entry,
            selected_model=selected_model,
            profile_name=profile_name,
            codex_config=codex_config,
        )
        output["codex_profile_sync"] = output["provider_codex_profile_sync"]
        output["managed_codex_profile_sync"] = {
            "status": "skipped",
            "reason": "custom_provider_profiles_are_provider_backed",
            "target_profiles": [],
            "deprecated_legacy_profiles": list(CODEEPSEEDEX_LEGACY_CODEX_PROFILES),
        }
    else:
        output["codex_profile_sync"] = {
            "status": "skipped",
            "reason": "non_default_env_file_without_codex_config" if codex_config is None else "profile_sync_disabled",
            "env_file": str(env_file),
        }
        output["managed_codex_profile_sync"] = {
            "status": "skipped",
            "reason": "profile_sync_disabled",
            "target_profiles": [],
            "deprecated_legacy_profiles": list(CODEEPSEEDEX_LEGACY_CODEX_PROFILES),
        }
    return output


def _custom_provider_config_command(args: argparse.Namespace, env_file: Path) -> int:
    path = _model_provider_registry_path(env_file)
    action = getattr(args, "custom_provider_action", "list")
    name = (getattr(args, "name", "") or "").strip()
    provider_id = _custom_provider_registry_slug(name)
    data = _read_custom_provider_registry(path)
    providers = data.setdefault("providers", {})
    entry = providers.get(provider_id) if name else None

    if action == "list":
        print(json.dumps({
            "status": "ok",
            "registry_path": str(path),
            "built_in_model_api_providers": [
                {
                    "id": provider,
                    "display_name": _model_api_provider_config(provider).get("display_name"),
                    "default_model": _model_api_provider_config(provider).get("model"),
                    "base_url": _model_api_provider_config(provider).get("base_url"),
                }
                for provider in _supported_model_api_providers()
                if provider != "custom"
            ],
            "custom_provider_registry": _redact_custom_provider_registry(data),
            "preferred_profile_note": "Custom providers can be launched with codex --profile <provider-id> after use/add --use or install-profile.",
        }, ensure_ascii=False, indent=2))
        return 0

    if action in {"show", "models", "list-models"}:
        if not name:
            print(json.dumps({"status": "error", "error": "missing_provider_name", "required": ["--name"]}, ensure_ascii=False, indent=2))
            return 1
        if not isinstance(entry, dict):
            print(json.dumps({"status": "error", "error": "custom_provider_not_found", "provider_name": name}, ensure_ascii=False, indent=2))
            return 1
        redacted = _redact_custom_provider_registry({"version": 1, "active_provider": data.get("active_provider"), "providers": {provider_id: entry}})
        print(json.dumps({
            "status": "ok",
            "registry_path": str(path),
            "provider_id": provider_id,
            "provider": redacted["providers"].get(provider_id),
            "models": entry.get("models", []),
            "active_model": entry.get("active_model"),
            "codex_profile": _custom_provider_codex_profile_name(provider_id, getattr(args, "profile_name", None)),
            "codex_command": f"codex --profile {_custom_provider_codex_profile_name(provider_id, getattr(args, 'profile_name', None))}",
        }, ensure_ascii=False, indent=2))
        return 0

    if action in {"add", "update"}:
        if action == "add":
            display_name = name
            base_url = _normalize_openai_base_url_value(getattr(args, "base_url", "") or "")
            model = _clean_wizard_input_value(getattr(args, "model", "") or "")
            if not display_name or not base_url or not model:
                print(json.dumps({"status": "error", "error": "missing_custom_provider_details", "required": ["--name", "--base-url", "--model"]}, ensure_ascii=False, indent=2))
                return 1
        else:
            if not name or not isinstance(entry, dict):
                print(json.dumps({"status": "error", "error": "custom_provider_not_found", "provider_name": name}, ensure_ascii=False, indent=2))
                return 1
            display_name = (getattr(args, "display_name", None) or entry.get("display_name") or name).strip()
            base_url = _normalize_openai_base_url_value(getattr(args, "base_url", "") or entry.get("base_url") or "")
            model = _clean_wizard_input_value(getattr(args, "model", "") or entry.get("active_model") or "")
        if not _is_valid_model_name_value(model):
            print(json.dumps({"status": "error", "error": "invalid_model_name", "message": "Model name is sent upstream and must be an exact model id, not a URL/path/API key.", "model": model}, ensure_ascii=False, indent=2))
            return 1
        api_key = (getattr(args, "value", "") or "").strip()
        if not api_key and action == "update" and isinstance(entry, dict):
            api_key = str(entry.get("api_key") or "")
        if api_key and not getattr(args, "skip_validation", False):
            validation_result = _validate_model_api_key("custom", api_key, base_url=base_url, timeout=float(getattr(args, "validation_timeout", 10.0)))
            if not validation_result.get("ok"):
                validation_result.update({"status": "error", "provider_name": display_name, "base_url": base_url, "model": model})
                print(json.dumps(validation_result, ensure_ascii=False, indent=2))
                return 1
        else:
            validation_result = _skipped_validation("model_api", "custom")
        data = _upsert_custom_provider_registry_entry(path, display_name=display_name, base_url=base_url, model=model, api_key=api_key, make_active=bool(getattr(args, "use", False)))
        output = {"status": "ok", "action": action, "registry_path": str(path), "provider_id": _custom_provider_registry_slug(display_name), "provider_name": display_name, "provider_type": "custom_openai_compatible", "base_url": base_url, "active_model": model, "validation": validation_result, "api_key_configured": bool(api_key), "api_key_preview": _mask_api_key(api_key), "custom_provider_registry": _redact_custom_provider_registry(data)}
        if getattr(args, "use", False):
            output["activated"] = _apply_custom_provider_registry_entry(env_file, provider_name=display_name, model=model, profile_name=getattr(args, "profile_name", None), codex_config=getattr(args, "codex_config", None), sync_profile=not bool(getattr(args, "no_profile_sync", False)))
        elif getattr(args, "install_profile", False):
            entry_after = (data.get("providers") or {}).get(_custom_provider_registry_slug(display_name), {})
            output["provider_codex_profile_sync"] = _sync_custom_provider_codex_profile_from_entry(env_file, entry=entry_after, selected_model=model, profile_name=getattr(args, "profile_name", None), codex_config=getattr(args, "codex_config", None))
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0

    if action == "add-model":
        model = _clean_wizard_input_value(getattr(args, "model", "") or "")
        if not name or not model:
            print(json.dumps({"status": "error", "error": "missing_name_or_model"}, ensure_ascii=False, indent=2))
            return 1
        if not _is_valid_model_name_value(model):
            print(json.dumps({"status": "error", "error": "invalid_model_name", "model": model}, ensure_ascii=False, indent=2))
            return 1
        if not isinstance(entry, dict):
            print(json.dumps({"status": "error", "error": "custom_provider_not_found", "provider_name": name}, ensure_ascii=False, indent=2))
            return 1
        models = entry.setdefault("models", [])
        if model not in models:
            models.append(model)
        if getattr(args, "use", False):
            entry["active_model"] = model
        _write_custom_provider_registry(path, data)
        output = {"status": "ok", "registry_path": str(path), "provider_id": provider_id, "provider_name": entry.get("display_name") or name, "models": models, "active_model": entry.get("active_model")}
        if getattr(args, "use", False):
            output["activated"] = _apply_custom_provider_registry_entry(env_file, provider_name=name, model=model, profile_name=getattr(args, "profile_name", None), codex_config=getattr(args, "codex_config", None), sync_profile=not bool(getattr(args, "no_profile_sync", False)))
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0

    if action == "remove-model":
        model = _clean_wizard_input_value(getattr(args, "model", "") or "")
        if not name or not model:
            print(json.dumps({"status": "error", "error": "missing_name_or_model"}, ensure_ascii=False, indent=2))
            return 1
        if not isinstance(entry, dict):
            print(json.dumps({"status": "error", "error": "custom_provider_not_found", "provider_name": name}, ensure_ascii=False, indent=2))
            return 1
        models = [m for m in entry.get("models", []) if m != model]
        if len(models) == len(entry.get("models", [])):
            print(json.dumps({"status": "error", "error": "model_not_found", "provider_name": name, "model": model}, ensure_ascii=False, indent=2))
            return 1
        if not models:
            print(json.dumps({"status": "error", "error": "cannot_remove_last_model_use_remove_provider", "provider_name": name, "model": model}, ensure_ascii=False, indent=2))
            return 1
        entry["models"] = models
        if entry.get("active_model") == model:
            entry["active_model"] = models[0]
        _write_custom_provider_registry(path, data)
        print(json.dumps({"status": "ok", "registry_path": str(path), "provider_id": provider_id, "provider_name": entry.get("display_name") or name, "removed_model": model, "models": models, "active_model": entry.get("active_model")}, ensure_ascii=False, indent=2))
        return 0

    if action == "use":
        try:
            output = _apply_custom_provider_registry_entry(env_file, provider_name=name, model=getattr(args, "model", None), profile_name=getattr(args, "profile_name", None), codex_config=getattr(args, "codex_config", None), sync_profile=not bool(getattr(args, "no_profile_sync", False)))
        except ValueError as exc:
            print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False, indent=2))
            return 1
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0

    if action == "install-profile":
        if not name or not isinstance(entry, dict):
            print(json.dumps({"status": "error", "error": "custom_provider_not_found", "provider_name": name}, ensure_ascii=False, indent=2))
            return 1
        selected_model = _clean_wizard_input_value(getattr(args, "model", "") or entry.get("active_model") or "")
        output = _sync_custom_provider_codex_profile_from_entry(env_file, entry=entry, selected_model=selected_model, profile_name=getattr(args, "profile_name", None), codex_config=getattr(args, "codex_config", None))
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0 if output.get("status") == "ok" else 1

    if action == "validate":
        if not name or not isinstance(entry, dict):
            print(json.dumps({"status": "error", "error": "custom_provider_not_found", "provider_name": name}, ensure_ascii=False, indent=2))
            return 1
        api_key = str(entry.get("api_key") or "")
        if not api_key:
            print(json.dumps({"ok": False, "status": "error", "error": "missing_model_api_key", "provider_id": provider_id, "provider_name": entry.get("display_name") or name}, ensure_ascii=False, indent=2))
            return 1
        result = _validate_model_api_key("custom", api_key, base_url=str(entry.get("base_url") or ""), timeout=float(getattr(args, "validation_timeout", 10.0)))
        result.update({"provider_id": provider_id, "provider_name": entry.get("display_name") or name, "model": entry.get("active_model")})
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("ok") else 1

    if action == "remove":
        if not name or not isinstance(entry, dict):
            print(json.dumps({"status": "error", "error": "custom_provider_not_found", "provider_name": name}, ensure_ascii=False, indent=2))
            return 1
        removed = dict(entry)
        providers.pop(provider_id, None)
        if data.get("active_provider") == provider_id:
            data["active_provider"] = None
        _write_custom_provider_registry(path, data)
        profile_remove = None
        if not bool(getattr(args, "no_profile_sync", False)):
            profile_remove = _remove_custom_provider_codex_profile(provider_id=provider_id, profile_name=getattr(args, "profile_name", None), codex_config=getattr(args, "codex_config", None))
        print(json.dumps({"status": "ok", "registry_path": str(path), "provider_id": provider_id, "provider_name": removed.get("display_name") or name, "removed": True, "active_provider": data.get("active_provider"), "profile_remove": profile_remove}, ensure_ascii=False, indent=2))
        return 0

    print(json.dumps({"status": "error", "error": "unsupported_custom_provider_action", "action": action}, ensure_ascii=False, indent=2))
    return 1



def _provider(args: argparse.Namespace) -> int:
    env_file = Path(args.env_file).expanduser() if getattr(args, "env_file", None) else default_env_file_path()
    setattr(args, "custom_provider_action", getattr(args, "provider_action", "list"))
    return _custom_provider_config_command(args, env_file)

def _api_configuration_status(env_file: Path | None = None) -> dict[str, Any]:
    path = env_file or default_env_file_path()
    values = _read_env_exports(path)
    web_search_keys = [
        "SERPAPI_API_KEY",
        "DEEPSEEK_PROXY_SERPAPI_API_KEY",
        "TAVILY_API_KEY",
        "DEEPSEEK_PROXY_TAVILY_API_KEY",
        "DEEPSEEK_PROXY_BRAVE_SEARCH_API_KEY",
        "EXA_API_KEY",
        "DEEPSEEK_PROXY_EXA_API_KEY",
        "FIRECRAWL_API_KEY",
        "DEEPSEEK_PROXY_FIRECRAWL_API_KEY",
    ]
    image_keys = [
        "DEEPSEEK_PROXY_IMAGE_API_KEY",
        "ZAI_API_KEY",
        "ZHIPUAI_API_KEY",
        "ZHIPU_API_KEY",
        "GLM_API_KEY",
        "DEEPSEEK_PROXY_DASHSCOPE_API_KEY",
        "DASHSCOPE_API_KEY",
        "ALIBABA_DASHSCOPE_API_KEY",
        "STABILITY_API_KEY",
        "DEEPSEEK_PROXY_STABILITY_API_KEY",
        "FAL_KEY",
        "FAL_API_KEY",
        "DEEPSEEK_PROXY_FAL_API_KEY",
    ]
    model_api = _model_api_config_status(path, values)
    missing = {
        "model_api": not bool(model_api.get("configured")),
        "web_search_api": not any(bool(values.get(key)) for key in web_search_keys),
        "image_generation_api": not any(bool(values.get(key)) for key in image_keys),
    }
    return {
        "env_file": str(path),
        "missing": missing,
        "all_configured": not any(missing.values()),
        "model_api": model_api,
        "commands": {
            "guided": "dsproxy config wizard",
            "model_api": "dsproxy config set-model --provider deepseek|kimi|zhipu|zhipu-coding|zai|zai-coding|qwen-beijing|qwen-singapore|qwen-us|custom",
            "web_search_api": "dsproxy config set-web-search-api-key --provider serpapi|tavily|exa|firecrawl",
            "image_generation_api": "dsproxy config set-image-api-key --provider zhipu|zai|qwen_image|stability|fal",
        },
        "supported": {
            "model_api": _supported_model_api_providers(),
            "web_search_api": ["serpapi", "tavily", "exa", "firecrawl"],
            "image_generation_api": ["zhipu", "bigmodel", "zai", "qwen_image", "stability", "fal"],
        },
        "unsupported_catalog": {
            "model_api": ["mimo", "baichuan"],
            "web_search_api": ["bing", "google_pse"],
            "image_generation_api": ["kolors", "hunyuan", "volcengine_ark"],
        },
    }


def _clean_wizard_input_value(value: str) -> str:
    buf: list[str] = []
    for ch in value or "":
        code = ord(ch)
        if ch in ("\b", "\x7f"):
            if buf:
                buf.pop()
            continue
        if code < 32 and ch != "\t":
            continue
        if code == 127:
            if buf:
                buf.pop()
            continue
        buf.append(ch)
    return "".join(buf).strip()


def _normalize_openai_base_url_value(value: str) -> str:
    url = re.sub(r"[\x00-\x1f\x7f]", "", value or "").strip().rstrip("/")
    for suffix in ("/chat/completions", "/responses", "/models"):
        if url.endswith(suffix):
            url = url[: -len(suffix)]
            break
    return url.rstrip("/")


def _is_probable_api_key_value(value: str) -> bool:
    value = (value or "").strip()
    lower = value.lower()
    if not value:
        return False
    if lower.startswith(("sk-", "sk_", "bearer ", "api-key", "apikey", "x-api-key")):
        return True
    if re.fullmatch(r"[A-Za-z0-9_.=-]{32,}", value):
        model_words = (
            "deepseek",
            "gpt",
            "glm",
            "qwen",
            "kimi",
            "moonshot",
            "zhipu",
            "doubao",
            "baichuan",
            "mimo",
            "flash",
            "pro",
            "chat",
            "model",
            "reasoner",
            "coder",
            "vision",
            "image",
            "embedding",
        )
        return not any(word in lower for word in model_words)
    return False


def _is_valid_model_name_value(value: str) -> bool:
    if not value:
        return False
    value = _clean_wizard_input_value(value)
    if value.startswith(("http://", "https://")):
        return False
    if "/" in value:
        return False
    if "\x7f" in value or "\b" in value:
        return False
    if any(ch.isspace() for ch in value):
        return False
    if _is_probable_api_key_value(value):
        return False
    return True

def _wizard_read_line(
    prompt: str,
    default: str = "",
    *,
    non_interactive: bool = False,
    title: str | None = None,
    footer: str | None = None,
    detail: str | None = None,
) -> str:
    if non_interactive or not sys.stdin.isatty():
        return default
    _wizard_render_input_panel(
        title or prompt,
        prompt,
        default=default,
        detail=detail,
        footer=footer or _wizard_step_label_for_prompt(prompt),
        secret=False,
    )
    print(f"\n  {prompt}", file=sys.stderr)
    if default:
        print("  \033[2m[Enter keeps default]\033[0m", file=sys.stderr)
    print("  > ", end="", file=sys.stderr, flush=True)
    value = sys.stdin.readline()
    print("", file=sys.stderr)
    return _clean_wizard_input_value(value) or default

def _wizard_read_secret(
    prompt: str,
    default: str = "",
    *,
    non_interactive: bool = False,
    title: str | None = None,
    footer: str | None = None,
    detail: str | None = None,
) -> str:
    if non_interactive or not sys.stdin.isatty():
        return default
    import termios

    _wizard_render_input_panel(
        title or prompt,
        prompt,
        default=default,
        detail=detail,
        footer=footer or _wizard_step_label_for_prompt(prompt),
        secret=True,
    )
    print(f"\n  {prompt}", file=sys.stderr)
    if default:
        print("  \033[2mhidden · Enter keeps existing\033[0m", file=sys.stderr)
    else:
        print("  \033[2mhidden\033[0m", file=sys.stderr)
    print("  > ", end="", file=sys.stderr, flush=True)
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        new_settings = termios.tcgetattr(fd)
        new_settings[3] = new_settings[3] & ~termios.ECHO
        termios.tcsetattr(fd, termios.TCSADRAIN, new_settings)
        value = sys.stdin.readline()
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        print("\n", file=sys.stderr)
    return _clean_wizard_input_value(value) or default

def _wizard_terminal_width() -> int:
    return min(86, max(64, shutil.get_terminal_size((86, 24)).columns))


def _wizard_wrap_lines(text: str, width: int) -> list[str]:
    import textwrap

    value = str(text or "")
    if not value:
        return [""]
    return textwrap.wrap(value, width=max(24, width), replace_whitespace=False, drop_whitespace=True) or [""]


def _wizard_print_box_line(text: str = "", *, width: int | None = None, style: str = "") -> None:
    width = width or _wizard_terminal_width()
    inner = max(40, width - 4)
    for line in _wizard_wrap_lines(text, inner):
        if len(line) > inner:
            line = line[: max(1, inner - 1)] + "…"
        if style:
            print(f"  {style}{line}\033[0m\033[K", file=sys.stderr)
        else:
            print(f"  {line}\033[K", file=sys.stderr)


def _wizard_print_box_top(title: str = "CoDeepSeedeX", *, width: int | None = None) -> None:
    width = width or _wizard_terminal_width()
    label = str(title or "CoDeepSeedeX")
    max_label = max(8, width - 8)
    if len(label) > max_label:
        label = label[: max(1, max_label - 1)] + "…"
    fill = "─" * max(4, width - len(label) - 4)
    print(f"\n\033[38;5;33m─ {label} {fill}\033[0m\033[K", file=sys.stderr)


def _wizard_print_box_separator(*, width: int | None = None) -> None:
    print("", file=sys.stderr)


def _wizard_print_step_footer(label: str = "Step 2/5", *, width: int | None = None) -> None:
    width = width or _wizard_terminal_width()
    text = str(label or "Step 2/5")
    prefix = f"─ {text} "
    fill = "─" * max(4, width - len(prefix))
    print(f"\033[38;5;33m{prefix}{fill}\033[0m\033[K", file=sys.stderr)

def _wizard_render_panel(title: str, lines: list[str], *, footer: str = "Step 2/5") -> None:
    width = _wizard_terminal_width()
    _wizard_print_box_top("CoDeepSeedeX", width=width)
    _wizard_print_box_line("", width=width)
    _wizard_print_box_line(title, width=width, style="\033[1;38;5;75m")
    body = list(lines or [])
    if body:
        _wizard_print_box_line("", width=width)
    for line in body:
        style = "\033[2m" if str(line).startswith("Hint:") else ""
        _wizard_print_box_line(line, width=width, style=style)
    _wizard_print_box_line("", width=width)
    _wizard_print_step_footer(footer, width=width)


def _wizard_render_input_panel(
    title: str,
    prompt: str,
    *,
    default: str = "",
    detail: str | None = None,
    footer: str = "Step 2/5",
    secret: bool = False,
) -> None:
    # Stable input panel: do not clear the whole terminal here.
    lines: list[str] = [prompt]
    if default:
        lines.append("Default: existing hidden value" if secret else f"Default: {default}")
    if detail:
        lines.append(f"Hint: {detail}")
    lines.append("Input is hidden. Press Enter to keep the existing value when one is available." if secret else "Press Enter to keep the default value.")
    _wizard_render_panel(title, lines, footer=footer)

def _wizard_step_label_for_prompt(prompt: str) -> str:
    value = str(prompt or "")
    if "image" in value.lower() or "qwen image" in value.lower():
        return "Step 4/5"
    if "web search" in value.lower():
        return "Step 3/5"
    if "model" in value.lower() or "zhipu" in value.lower() or "z.ai" in value.lower() or "dashscope" in value.lower():
        return "Step 2/5"
    return "Step 2/5"



def _wizard_render_menu(prompt: str, options: list[tuple[str, str, str]], selected: int, *, help_text: str | None = None) -> None:
    width = _wizard_terminal_width()
    inner = max(40, width - 4)

    def fit(value: str) -> str:
        value = str(value)
        if len(value) > inner:
            value = value[: max(1, inner - 1)] + "…"
        return value.ljust(inner)

    _wizard_print_box_top("CoDeepSeedeX", width=width)
    _wizard_print_box_line("", width=width)
    _wizard_print_box_line(prompt, width=width, style="\033[1;38;5;75m")
    _wizard_print_box_line("", width=width)
    if help_text:
        _wizard_print_box_line("Hint", width=width, style="\033[2m")
        _wizard_print_box_line(help_text, width=width, style="\033[2m")
        _wizard_print_box_line("", width=width)
    _wizard_print_box_line("", width=width)
    for idx, (value, label, status) in enumerate(options):
        marker = "●" if idx == selected else "○"
        suffix = f"  [{status}]" if status else ""
        row = fit(f"{marker} [{value}] {label}{suffix}")
        if idx == selected:
            _wizard_print_box_line(row, width=width, style="\033[1;38;5;75m")
        elif status.lower() == "supported":
            _wizard_print_box_line(row, width=width, style="\033[38;5;114m")
        elif status.lower() in {"experimental", "validated"}:
            _wizard_print_box_line(row, width=width, style="\033[38;5;177m")
        elif status.lower() in {"custom", "model availability varies"}:
            _wizard_print_box_line(row, width=width, style="\033[38;5;215m")
        elif status.lower() == "unsupported":
            _wizard_print_box_line(row, width=width, style="\033[2m")
        else:
            _wizard_print_box_line(row, width=width)
    _wizard_print_box_line("", width=width)
    _wizard_print_box_line("Use ↑/↓ or j/k to move, Enter to select, Backspace to previous step.", width=width, style="\033[2m")
    _wizard_print_step_footer(_wizard_step_label_for_prompt(prompt), width=width)


def _wizard_read_menu_choice(prompt: str, options: list[tuple[str, str, str]], default: str, *, help_text: str | None = None, non_interactive: bool = False) -> str:
    if non_interactive or not sys.stdin.isatty():
        return default
    try:
        import termios
        import tty
    except Exception:
        return default

    selected = 0
    for idx, (value, _label, _status) in enumerate(options):
        if value == default:
            selected = idx
            break

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        # Use cbreak instead of raw mode so terminal output keeps normal CR/LF rendering.
        tty.setcbreak(fd)
        while True:
            print("\033[?25l\033[H\033[J\033[3J", end="", file=sys.stderr)
            _wizard_render_menu(prompt, options, selected, help_text=help_text)
            ch = sys.stdin.read(1)
            if ch == "\x1b":
                seq = sys.stdin.read(2)
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
                return options[selected][0]
            if ch in {"\x7f", "\b"}:
                return "__CODEEPSEEDEX_BACK__"
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        print("\033[?25h", file=sys.stderr)

def _wizard_yes_no_choice(prompt: str, default: str = "N", *, non_interactive: bool = False) -> str:
    default_value = "Y" if str(default).strip().lower().startswith("y") else "N"
    return _wizard_read_menu_choice(
        prompt,
        [("Y", "Yes", ""), ("N", "No", "")],
        default_value,
        non_interactive=non_interactive,
    )


def _wizard_yes_no(prompt: str, default: str = "N", *, non_interactive: bool = False) -> bool:
    return _wizard_yes_no_choice(prompt, default, non_interactive=non_interactive) == "Y"


def _wizard_model_provider_choice(*, non_interactive: bool = False) -> str:
    family = _wizard_read_menu_choice(
        "Select model provider family",
        [
            ("deepseek", "DeepSeek", "Supported"),
            ("kimi", "Kimi / Moonshot", "Experimental"),
            ("zhipu", "ZhipuAI / BigModel", "Experimental"),
            ("zai", "Z.AI", "Experimental"),
            ("qwen", "Qwen / DashScope", "Experimental"),
            ("custom", "Other OpenAI-compatible server", "Custom"),
            ("mimo", "Mimo", "Unsupported"),
            ("baichuan", "Baichuan", "Unsupported"),
            ("0", "Skip", ""),
        ],
        "deepseek",
        non_interactive=non_interactive,
    )
    if family == "zhipu":
        return _wizard_read_menu_choice(
            "Select ZhipuAI / BigModel endpoint",
            [("zhipu", "Token API", "Experimental"), ("zhipu-coding", "Coding Plan", "Experimental"), ("0", "Back", "")],
            "zhipu",
            non_interactive=non_interactive,
        )
    if family == "zai":
        return _wizard_read_menu_choice(
            "Select Z.AI endpoint",
            [("zai", "Token API", "Experimental"), ("zai-coding", "Coding Plan", "Experimental"), ("0", "Back", "")],
            "zai",
            non_interactive=non_interactive,
        )
    if family == "qwen":
        return _wizard_read_menu_choice(
            "Select Qwen / DashScope endpoint",
            [("qwen-beijing", "Beijing", "Experimental"), ("qwen-singapore", "Singapore", "Experimental"), ("qwen-us", "US Virginia", "Experimental"), ("0", "Back", "")],
            "qwen-beijing",
            non_interactive=non_interactive,
        )
    return family


def _wizard_web_provider_choice(*, non_interactive: bool = False) -> str:
    return _wizard_read_menu_choice(
        "Select web search provider",
        [
            ("serpapi", "SerpAPI", "Experimental"),
            ("tavily", "Tavily", "Experimental"),
            ("exa", "Exa", "Experimental"),
            ("firecrawl", "Firecrawl", "Experimental"),
            ("0", "Skip", ""),
        ],
        "serpapi",
        non_interactive=non_interactive,
    )


def _wizard_image_provider_choice(*, non_interactive: bool = False) -> str:
    family = _wizard_read_menu_choice(
        "Choose image generation provider family",
        [
            ("zhipu", "ZhipuAI / BigModel", "Experimental"),
            ("zai", "Z.AI", "Experimental"),
            ("qwen", "Qwen Image / DashScope", "Experimental"),
            ("stability", "Stability AI", "Experimental"),
            ("fal", "fal.ai", "Experimental"),
            ("0", "Skip", ""),
        ],
        "zhipu",
        non_interactive=non_interactive,
    )
    if family == "qwen":
        return _wizard_read_menu_choice(
            "Select Qwen Image / DashScope region",
            [
                ("qwen_image_beijing", "Beijing", "Validated"),
                ("qwen_image_singapore", "Singapore", "Validated"),
                ("qwen_image_us", "US Virginia", "Model availability varies"),
                ("qwen_image_germany", "Germany Frankfurt", "Model availability varies"),
                ("0", "Back", ""),
            ],
            "qwen_image_beijing",
            non_interactive=non_interactive,
        )
    return family


def _run_guided_config(env_file: Path, *, non_interactive: bool = False, emit_json: bool = True) -> dict[str, Any]:
    values = _read_env_exports(env_file)
    before = _api_configuration_status(env_file)
    configured: list[str] = []
    skipped: list[str] = []
    unsupported: list[str] = []
    validation_results: list[dict[str, Any]] = []

    if non_interactive or not sys.stdin.isatty():
        result = {
            "status": "ok",
            "mode": "config_wizard",
            "interactive": False,
            "env_file": str(env_file),
            "configuration_status": before,
            "configured": configured,
            "skipped": ["interactive_prompt_unavailable"],
            "unsupported": unsupported,
            "validation_results": validation_results,
            "ui_contract": {
                "mode": "installer_matching_arrow_menu",
                "keybindings": "Use ↑/↓ or j/k to move, Enter to select, Backspace to go back.",
                "tty_numeric_fallback": False,
            },
        }
        if emit_json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        return result

    _wizard_render_panel(
        "Guided API configuration",
        [
            "You can skip any item and configure it later.",
            "Secrets are hidden. Saved values are kept when you press Enter.",
            "Use Backspace from a menu to return to the previous guided step.",
        ],
        footer="Step 0/5",
    )

    wizard_step = 2
    while wizard_step <= 4:
        if wizard_step == 2:
            choice = _wizard_yes_no_choice("Configure model API now?", "Y", non_interactive=non_interactive)
            if choice == "__CODEEPSEEDEX_BACK__":
                wizard_step = 2
                continue
            if choice == "Y":
                provider = _wizard_model_provider_choice(non_interactive=non_interactive)
                if provider == "__CODEEPSEEDEX_BACK__":
                    wizard_step = 2
                    continue
                if provider in {"0", "mimo", "baichuan"}:
                    skipped.append("model_api" if provider == "0" else f"model_api:{provider}_unsupported")
                    if provider in {"mimo", "baichuan"}:
                        unsupported.append(f"model_api:{provider}")
                        print("Selected model provider is currently unsupported. Configure it as custom only if it is OpenAI-compatible.", file=sys.stderr)
                else:
                    provider_config = _model_api_provider_config(provider)
                    base_url = str(provider_config.get("base_url") or "").strip()
                    model = str(provider_config.get("model") or "").strip()
                    custom_provider_name = ""
                    if provider == "custom":
                        custom_provider_name = _clean_wizard_input_value(_wizard_read_line(
                            "Custom provider name / Codex profile id",
                            values.get("DEEPSEEK_PROXY_CUSTOM_PROVIDER_NAME", "") or "custom-provider",
                            non_interactive=non_interactive,
                            title="Custom OpenAI-compatible model API",
                            footer="Step 2/5",
                            detail="Used locally for dsproxy provider switching and codex --profile <provider-id>; it is not sent upstream.",
                        )) or "custom-provider"
                        base_url = _normalize_openai_base_url_value(_wizard_read_line(
                            "OpenAI-compatible base URL",
                            values.get("DEEPSEEK_BASE_URL", ""),
                            non_interactive=non_interactive,
                            title="Custom OpenAI-compatible model API",
                            footer="Step 2/5",
                            detail="Enter the upstream endpoint. /chat/completions will be normalized to the base /v1 URL.",
                        ))
                        while True:
                            model = _clean_wizard_input_value(_wizard_read_line(
                                "Upstream model name",
                                values.get("DEEPSEEK_PROXY_MODEL", ""),
                                non_interactive=non_interactive,
                                title="Custom OpenAI-compatible model API",
                                footer="Step 2/5",
                                detail=f"Provider: {custom_provider_name}. Endpoint: {base_url or '<empty>'}. Enter only the exact upstream model id.",
                            ))
                            if not model or _is_valid_model_name_value(model):
                                break
                            if non_interactive:
                                raise SystemExit("Custom provider model must be a model id, not a URL, path, whitespace-containing value, or API key. Example: your-model-id")
                            print("Invalid upstream model name: enter only the model id, not a URL, path, whitespace-containing value, or API key.", file=sys.stderr)
                        if not base_url or not model:
                            skipped.append("model_api:custom_missing_details")
                            print("Custom model API skipped because base URL or model name is empty.", file=sys.stderr)
                            provider = ""
                    if provider:
                        key = _wizard_read_secret(
                            f"{provider_config['display_name']} API key",
                            values.get("DEEPSEEK_API_KEY", ""),
                            non_interactive=non_interactive,
                            title="Model API key",
                            footer="Step 2/5",
                            detail=f"Provider: {provider} · Model: {model or '<unset>'}",
                        )
                        if key:
                            if provider == "deepseek":
                                validation = _check_deepseek_api_key(key, url="https://api.deepseek.com/user/balance", timeout=10.0)
                                validation["kind"] = "model_api"
                                validation["provider"] = "deepseek"
                            else:
                                validation = _validate_model_api_key(provider, key, base_url=base_url, timeout=10.0)
                            validation_results.append(validation)
                            if validation.get("ok"):
                                if provider == "custom":
                                    registry_path = _model_provider_registry_path(env_file)
                                    registry_data = _upsert_custom_provider_registry_entry(
                                        registry_path,
                                        display_name=custom_provider_name,
                                        base_url=base_url,
                                        model=model,
                                        api_key=key,
                                        make_active=True,
                                    )
                                    provider_id = _custom_provider_registry_slug(custom_provider_name)
                                    entry = (registry_data.get("providers") or {}).get(provider_id, {})
                                    profile_sync = _sync_custom_provider_codex_profile_from_entry(
                                        env_file,
                                        entry=entry,
                                        selected_model=model,
                                    ) if isinstance(entry, dict) else {"status": "error", "error": "custom_provider_registry_entry_missing"}
                                    validation["custom_provider"] = {
                                        "provider_name": custom_provider_name,
                                        "provider_id": provider_id,
                                        "registry_path": str(registry_path),
                                        "codex_profile_sync": profile_sync,
                                        "codex_command": profile_sync.get("codex_command") if isinstance(profile_sync, dict) else None,
                                    }
                                    values["DEEPSEEK_PROXY_CUSTOM_PROVIDER_NAME"] = custom_provider_name
                                    values["DEEPSEEK_PROXY_MODEL_PROVIDER_REGISTRY"] = str(registry_path)
                                values["DEEPSEEK_API_KEY"] = key
                                values["DEEPSEEK_BASE_URL"] = base_url
                                values["DEEPSEEK_PROXY_MODEL_PROVIDER"] = provider
                                values["DEEPSEEK_PROXY_MODEL"] = model
                                values["DEEPSEEK_PROXY_FORCE_MODEL"] = values.get("DEEPSEEK_PROXY_FORCE_MODEL", "1")
                                configured.append(f"model_api:{provider}")
                                print(f"Model API key validated for provider: {provider}.", file=sys.stderr)
                            else:
                                skipped.append(f"model_api:{provider}_validation_failed")
                                print(f"Model API key validation failed for provider {provider}. It was not saved.", file=sys.stderr)
                        else:
                            skipped.append("model_api")
            else:
                skipped.append("model_api")
            wizard_step = 3
            continue

        if wizard_step == 3:
            choice = _wizard_yes_no_choice("Configure web search API now?", "N", non_interactive=non_interactive)
            if choice == "__CODEEPSEEDEX_BACK__":
                wizard_step = 2
                continue
            if choice == "Y":
                provider = _wizard_web_provider_choice(non_interactive=non_interactive)
                if provider == "__CODEEPSEEDEX_BACK__":
                    wizard_step = 3
                    continue
                web_provider_map = {
                    "serpapi": ("serpapi", "SerpAPI API key", "SERPAPI_API_KEY"),
                    "tavily": ("tavily", "Tavily API key", "TAVILY_API_KEY"),
                    "exa": ("exa", "Exa API key", "EXA_API_KEY"),
                    "firecrawl": ("firecrawl", "Firecrawl API key", "FIRECRAWL_API_KEY"),
                }
                if provider in web_provider_map:
                    provider, prompt, env_key = web_provider_map[provider]
                    key = _wizard_read_secret(
                        prompt,
                        values.get(env_key, ""),
                        non_interactive=non_interactive,
                        title="Web search API key",
                        footer="Step 3/5",
                        detail=f"Provider: {provider}",
                    )
                    if key:
                        validation = _validate_web_search_api_key(provider, key, timeout=10.0)
                        validation_results.append(validation)
                        if validation.get("ok"):
                            values["DEEPSEEK_PROXY_TOOL_BRIDGE"] = "1"
                            values["DEEPSEEK_PROXY_WEB_SEARCH_PROVIDER"] = provider
                            values["DEEPSEEK_PROXY_WEB_SEARCH_MAX_RESULTS"] = values.get("DEEPSEEK_PROXY_WEB_SEARCH_MAX_RESULTS", "6")
                            values["DEEPSEEK_PROXY_WEB_SEARCH_TIMEOUT_SECONDS"] = values.get("DEEPSEEK_PROXY_WEB_SEARCH_TIMEOUT_SECONDS", "12.5")
                            values[env_key] = key
                            configured.append(f"web_search_api:{provider}")
                            print(f"Web search API key validated for provider: {provider}.", file=sys.stderr)
                        else:
                            skipped.append(f"web_search_api:{provider}_validation_failed")
                            print(f"Web search API key validation failed for provider {provider}. It was not saved.", file=sys.stderr)
                    else:
                        skipped.append("web_search_api")
                else:
                    skipped.append("web_search_api")
            else:
                skipped.append("web_search_api")
            wizard_step = 4
            continue

        if wizard_step == 4:
            choice = _wizard_yes_no_choice("Configure image generation API now?", "N", non_interactive=non_interactive)
            if choice == "__CODEEPSEEDEX_BACK__":
                wizard_step = 3
                continue
            if choice == "Y":
                provider = _wizard_image_provider_choice(non_interactive=non_interactive)
                if provider == "__CODEEPSEEDEX_BACK__":
                    wizard_step = 4
                    continue
                image_provider_map = {
                    "zhipu": ("zhipu", "ZhipuAI / BigModel image API key", "ZHIPUAI_API_KEY"),
                    "zai": ("zai", "Z.AI image API key", "ZAI_API_KEY"),
                    "qwen_image_beijing": ("qwen_image_beijing", "DashScope Qwen Image API key", "DASHSCOPE_API_KEY"),
                    "qwen_image_singapore": ("qwen_image_singapore", "DashScope Qwen Image API key", "DASHSCOPE_API_KEY"),
                    "qwen_image_us": ("qwen_image_us", "DashScope Qwen Image API key", "DASHSCOPE_API_KEY"),
                    "qwen_image_germany": ("qwen_image_germany", "DashScope Qwen Image API key", "DASHSCOPE_API_KEY"),
                    "stability": ("stability", "Stability AI API key", "STABILITY_API_KEY"),
                    "fal": ("fal", "fal.ai API key", "FAL_KEY"),
                }
                if provider in image_provider_map:
                    provider, prompt, env_key = image_provider_map[provider]
                    saved_default = values.get(env_key, "") or values.get("DEEPSEEK_PROXY_IMAGE_API_KEY", "")
                    key = _wizard_read_secret(
                        prompt,
                        saved_default,
                        non_interactive=non_interactive,
                        title="Image generation API key",
                        footer="Step 4/5",
                        detail=f"Provider: {provider}. Live validation may consume provider credits.",
                    )
                    if key:
                        validation = _validate_image_api_key(provider, key, timeout=10.0)
                        validation_results.append(validation)
                        if validation.get("ok"):
                            canonical = _canonical_image_generation_provider(provider)
                            values["DEEPSEEK_PROXY_TOOL_BRIDGE"] = "1"
                            values["DEEPSEEK_PROXY_IMAGE_PROVIDER"] = canonical
                            values["DEEPSEEK_PROXY_IMAGE_API_KEY"] = key
                            values[env_key] = key
                            base_url = _image_generation_base_url_for_provider(canonical)
                            if base_url:
                                values["DEEPSEEK_PROXY_IMAGE_BASE_URL"] = base_url
                            configured.append(f"image_generation_api:{canonical}")
                            print(f"Image generation API key validated for provider: {canonical}.", file=sys.stderr)
                        else:
                            skipped.append(f"image_generation_api:{provider}_validation_failed")
                            print(f"Image generation API key validation failed for provider {provider}. It was not saved.", file=sys.stderr)
                    else:
                        skipped.append("image_generation_api")
                else:
                    skipped.append("image_generation_api")
            else:
                skipped.append("image_generation_api")
            wizard_step = 5
            continue
    if configured:
        _write_env_exports(env_file, values)

    after = _api_configuration_status(env_file)
    result = {
        "status": "ok",
        "mode": "config_wizard",
        "interactive": True,
        "ui_contract": {
            "mode": "installer_matching_arrow_menu",
            "keybindings": "Use ↑/↓ or j/k to move, Enter to select, Backspace to go back.",
            "tty_numeric_fallback": False,
        },
        "env_file": str(env_file),
        "configuration_status_before": before,
        "configuration_status": after,
        "configured": configured,
        "skipped": skipped,
        "unsupported": unsupported,
        "validation_results": validation_results,
    }
    if emit_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return result

def _configure_model_api_command(args: argparse.Namespace, env_file: Path, *, legacy_command: bool) -> int:
    provider_arg = getattr(args, "provider", None)
    provider = _canonical_model_api_provider(provider_arg or "deepseek")
    try:
        provider_config = _model_api_provider_config(provider)
    except ValueError:
        print(json.dumps({
            "status": "error",
            "error": "unsupported_model_api_provider",
            "provider": provider,
            "supported_providers": _supported_model_api_providers(),
        }, ensure_ascii=False, indent=2))
        return 1

    model_value = str(getattr(args, "model", "") or "").strip()
    base_url_value = str(getattr(args, "base_url", "") or provider_config.get("base_url") or "").strip().rstrip("/")
    api_key_value = str(getattr(args, "value", "") or "")
    provider_was_explicit = provider_arg is not None and str(provider_arg).strip() != ""
    api_setup_requested = bool(
        legacy_command
        or provider_was_explicit
        or api_key_value
        or str(getattr(args, "base_url", "") or "").strip()
    )

    if not api_setup_requested:
        allowed = {"deepseek-v4-pro", "deepseek-v4-flash"}
        if not model_value:
            print(json.dumps({
                "status": "error",
                "error": "missing_model",
                "message": "Provide a model name, or use --provider with --value to configure the model API provider and API key.",
                "preferred_command": "dsproxy config set-model <model> --provider <provider>",
            }, ensure_ascii=False, indent=2))
            return 2
        if model_value not in allowed:
            print(json.dumps({
                "status": "error",
                "error": "invalid_model",
                "allowed": sorted(allowed),
                "message": "Use --provider when setting a non-DeepSeek model or configuring a model API provider.",
                "preferred_command": "dsproxy config set-model <model> --provider <provider>",
            }, ensure_ascii=False, indent=2))
            return 2
        values = _read_env_exports(env_file)
        values["DEEPSEEK_PROXY_MODEL"] = model_value
        values.setdefault("DEEPSEEK_PROXY_FORCE_MODEL", "1")
        _write_env_exports(env_file, values)

        codex_path = Path(args.codex_config).expanduser() if getattr(args, "codex_config", None) else default_codex_config_path()
        profile_sync = _sync_managed_codex_profile_models_from_env(
            env_file=env_file,
            codex_path=codex_path,
            profile_value=getattr(args, "profile", "__managed__"),
        )

        output = {
            "status": "ok",
            "env_file": str(env_file),
            "model": model_value,
            "post_config_apply": _post_config_apply(),
        }
        output.update(profile_sync)
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0

    resolved_model = model_value or str(provider_config.get("model") or "").strip()
    if provider == "custom" and (not base_url_value or not resolved_model):
        print(json.dumps({
            "status": "error",
            "error": "missing_custom_model_api_details",
            "message": "Custom model API providers require --base-url and a model name.",
            "env_file": str(env_file),
            "preferred_command": "dsproxy config set-model <model> --provider custom --base-url <url>",
        }, ensure_ascii=False, indent=2))
        return 1

    if not api_key_value:
        import getpass
        api_key_value = getpass.getpass(f"{provider_config['display_name']} API key: ").strip()

    if not api_key_value:
        print(json.dumps({
            "status": "error",
            "error": "missing_model_api_key",
            "provider": provider,
            "env_file": str(env_file),
            "preferred_command": f"dsproxy config set-model {resolved_model or '<model>'} --provider {provider}",
        }, ensure_ascii=False, indent=2))
        return 1

    if not getattr(args, "skip_validation", False):
        if provider == "deepseek":
            validation_result = _check_deepseek_api_key(
                api_key_value,
                url=getattr(args, "validation_url", "https://api.deepseek.com/user/balance"),
                timeout=float(getattr(args, "validation_timeout", 10.0)),
            )
            validation_result["kind"] = "model_api"
            validation_result["provider"] = "deepseek"
        else:
            validation_result = _validate_model_api_key(
                provider,
                api_key_value,
                base_url=base_url_value,
                timeout=float(getattr(args, "validation_timeout", 10.0)),
            )
        if not validation_result.get("ok"):
            validation_result.update({
                "env_file": str(env_file),
                "model_api_key_configured": False,
                "model_provider": provider,
                "base_url": base_url_value,
                "model": resolved_model,
                "preferred_command": f"dsproxy config set-model {resolved_model or '<model>'} --provider {provider}",
            })
            if provider == "deepseek":
                validation_result["deepseek_api_key_configured"] = False
                validation_result["deepseek_api_key_preview"] = _mask_api_key(api_key_value)
            print(json.dumps(validation_result, ensure_ascii=False, indent=2))
            return 1
    else:
        validation_result = _skipped_validation("model_api", provider)

    values = _read_env_exports(env_file)
    values["DEEPSEEK_API_KEY"] = api_key_value
    values["DEEPSEEK_BASE_URL"] = base_url_value
    values["DEEPSEEK_PROXY_MODEL_PROVIDER"] = provider
    values["DEEPSEEK_PROXY_MODEL"] = resolved_model
    values["DEEPSEEK_PROXY_FORCE_MODEL"] = values.get("DEEPSEEK_PROXY_FORCE_MODEL", "1")
    _write_env_exports(env_file, values)

    codex_path = Path(args.codex_config).expanduser() if getattr(args, "codex_config", None) else default_codex_config_path()
    profile_sync = _sync_managed_codex_profile_models_from_env(
        env_file=env_file,
        codex_path=codex_path,
        profile_value=getattr(args, "profile", "__managed__"),
    )

    output = {
        "status": "ok",
        "env_file": str(env_file),
        "model_api_key_configured": True,
        "model_provider": provider,
        "model_api_key_preview": _mask_api_key(api_key_value),
        "base_url": base_url_value,
        "model": resolved_model,
        "validation": validation_result,
        "preferred_command": f"dsproxy config set-model {resolved_model} --provider {provider}",
        "post_config_apply": _post_config_apply(),
    }
    output.update(profile_sync)
    if legacy_command:
        output["deprecated_command"] = "set-api-key"
        output["compatibility_note"] = "dsproxy config set-api-key remains supported as a compatibility alias; prefer dsproxy config set-model for model provider, model, and API key setup."
    if provider == "deepseek":
        output["deepseek_api_key_configured"] = True
        output["deepseek_api_key_preview"] = _mask_api_key(api_key_value)
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


def _config_wizard(args: argparse.Namespace) -> int:
    env_file = Path(args.env_file).expanduser() if getattr(args, "env_file", None) else default_env_file_path()
    result = _run_guided_config(env_file, non_interactive=bool(getattr(args, "non_interactive", False)), emit_json=False)
    if result.get("configured"):
        if env_file.expanduser() == default_env_file_path():
            result["codex_profile_sync"] = _sync_managed_codex_profile_models_from_env(
                env_file=env_file,
                codex_path=default_codex_config_path(),
                profile_value="__managed__",
            )
        else:
            result["codex_profile_sync"] = {
                "status": "skipped",
                "reason": "non_default_env_file",
                "env_file": str(env_file),
            }
        result["post_config_apply"] = _post_config_apply()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _config(args: argparse.Namespace) -> int:
    if args.config_command == "wizard":
        return _config_wizard(args)
    path = Path(args.path).expanduser() if getattr(args, "path", None) else default_config_path()
    env_file = Path(args.env_file).expanduser() if getattr(args, "env_file", None) else default_env_file_path()

    if args.config_command == "path":
        print(path)
        return 0

    if args.config_command == "init":
        changed = _write_default_config(path, force=args.force)
        print(json.dumps({"path": str(path), "created_or_overwritten": changed}, ensure_ascii=False, indent=2))
        return 0

    if args.config_command == "show":
        values = _read_env_exports(env_file)
        safe_values = {
            key: _mask_env_secret(key, value)
            for key, value in values.items()
        }
        print(json.dumps({
            "env_file": str(env_file),
            "values": safe_values,
            "model_api": _model_api_config_status(env_file, values),
            "custom_provider_registry": _custom_provider_registry_status(env_file, values),
            "tool_routing": _tool_routing_config_status(env_file, values),
        }, ensure_ascii=False, indent=2))
        return 0

    if args.config_command == "set-tool-routing":
        return _set_tool_routing_policy(args, env_file)

    if args.config_command == "set-api-key":
        return _configure_model_api_command(args, env_file, legacy_command=True)

    if args.config_command == "test-api-key":
        env_values = _read_env_exports(env_file)
        provider_arg = getattr(args, "provider", None)
        provider_arg = None if provider_arg is None or str(provider_arg).strip() == "" else str(provider_arg).strip()
        provider = _canonical_model_api_provider(provider_arg or env_values.get("DEEPSEEK_PROXY_MODEL_PROVIDER") or "deepseek")
        api_key, source = _load_deepseek_api_key(env_file=env_file)
        try:
            provider_config = _model_api_provider_config(provider)
        except ValueError:
            print(json.dumps({
                "status": "error",
                "error": "unsupported_model_api_provider",
                "provider": provider,
                "supported_providers": _supported_model_api_providers(),
            }, ensure_ascii=False, indent=2))
            return 1
        base_url = str(getattr(args, "base_url", "") or env_values.get("DEEPSEEK_BASE_URL") or provider_config.get("base_url", "") or "").strip().rstrip("/")
        model = str(env_values.get("DEEPSEEK_PROXY_MODEL") or provider_config.get("model", "") or "").strip()
        if provider == "custom" and (not base_url or not model):
            result = {
                "ok": False,
                "status": "error",
                "kind": "model_api",
                "provider": provider,
                "error": "missing_custom_model_api_details",
                "message": "Custom model API validation requires DEEPSEEK_BASE_URL and DEEPSEEK_PROXY_MODEL, or --base-url plus a configured model.",
                "base_url": base_url,
                "model": model,
            }
        elif provider == "deepseek":
            result = _check_deepseek_api_key(
                api_key,
                url=args.url,
                timeout=float(args.timeout),
            )
            result["kind"] = "model_api"
            result["provider"] = "deepseek"
            if not base_url:
                base_url = "https://api.deepseek.com"
            if not model:
                model = "deepseek-v4-pro"
        else:
            result = _validate_model_api_key(provider, api_key, base_url=base_url, timeout=float(args.timeout))
        validation_url = result.get("url") or (args.url if provider == "deepseek" else (_model_api_validation_url(base_url, provider_config.get("validation_path", "/models")) if base_url else ""))
        result["env_file"] = str(env_file)
        result["api_key_source"] = source
        result["model_api_key_configured"] = bool(api_key)
        result["model_api_key_preview"] = _mask_api_key(api_key)
        result["model_provider"] = provider
        result["base_url"] = base_url
        result["model"] = model
        result["validation_url"] = validation_url
        result["validation_method"] = "deepseek_balance" if provider == "deepseek" else "openai_compatible_models"
        result["may_consume_quota"] = False
        if provider == "deepseek":
            result["deepseek_api_key_configured"] = bool(api_key)
            result["deepseek_api_key_preview"] = _mask_api_key(api_key)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("ok") else 1



    if args.config_command == "set-web-search-api-key":
        provider = str(getattr(args, "provider", "serpapi") or "serpapi").strip().lower()
        provider_aliases = {
            "serpapi": ("serpapi", "SERPAPI_API_KEY", "SerpAPI API key"),
            "tavily": ("tavily", "TAVILY_API_KEY", "Tavily API key"),
            "exa": ("exa", "EXA_API_KEY", "Exa API key"),
            "firecrawl": ("firecrawl", "FIRECRAWL_API_KEY", "Firecrawl API key"),
        }
        if provider not in provider_aliases:
            print(json.dumps({
                "status": "error",
                "error": "unsupported_web_search_provider",
                "supported_providers": ["serpapi", "tavily", "exa", "firecrawl"],
            }, ensure_ascii=False, indent=2))
            return 1
        canonical_provider, env_key, prompt = provider_aliases[provider]
        api_key = str(getattr(args, "value", "") or "")
        if not api_key:
            import getpass

            api_key = getpass.getpass(f"{prompt}: ").strip()
        if not api_key:
            print(json.dumps({
                "status": "error",
                "error": f"missing_{canonical_provider}_api_key",
                "env_file": str(env_file),
            }, ensure_ascii=False, indent=2))
            return 1

        if getattr(args, "skip_validation", False):
            validation = _skipped_validation("web_search", canonical_provider)
        else:
            validation = _validate_web_search_api_key(canonical_provider, api_key, timeout=float(args.validation_timeout))
            if not validation.get("ok"):
                validation.update({
                    "env_file": str(env_file),
                    "web_search_provider": canonical_provider,
                    "web_search_api_key_configured": False,
                    "web_search_api_key_preview": _mask_api_key(api_key),
                    "error": validation.get("error") or "validation_failed",
                })
                print(json.dumps(validation, ensure_ascii=False, indent=2))
                return 1

        values = _read_env_exports(env_file)
        values["DEEPSEEK_PROXY_TOOL_BRIDGE"] = "1"
        values["DEEPSEEK_PROXY_WEB_SEARCH_PROVIDER"] = canonical_provider
        values["DEEPSEEK_PROXY_WEB_SEARCH_MAX_RESULTS"] = values.get("DEEPSEEK_PROXY_WEB_SEARCH_MAX_RESULTS", "6")
        values["DEEPSEEK_PROXY_WEB_SEARCH_TIMEOUT_SECONDS"] = values.get("DEEPSEEK_PROXY_WEB_SEARCH_TIMEOUT_SECONDS", "12.5")
        values[env_key] = api_key
        _write_env_exports(env_file, values)
        output = {
            "status": "ok",
            "env_file": str(env_file),
            "web_search_provider": canonical_provider,
            "web_search_api_key_configured": True,
            "web_search_api_key_preview": _mask_api_key(api_key),
            "validation": validation,
        }
        if canonical_provider == "serpapi":
            output["serpapi_api_key_configured"] = True
            output["serpapi_api_key_preview"] = _mask_api_key(api_key)
        output["post_config_apply"] = _post_config_apply()
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0

    if args.config_command == "set-image-api-key":
        provider = str(getattr(args, "provider", "zhipu") or "zhipu").strip().lower()
        provider_aliases = {
            "glm": ("glm", "cogView-4-250304", "GLM image API key"),
            "zai": ("zai", "cogView-4-250304", "Z.AI image API key"),
            "z.ai": ("zai", "cogView-4-250304", "Z.AI image API key"),
            "zhipu": ("zhipu", "cogView-4-250304", "ZhipuAI image API key"),
            "zhipuai": ("zhipuai", "cogView-4-250304", "ZhipuAI image API key"),
            "bigmodel": ("bigmodel", "cogView-4-250304", "BigModel image API key"),
            "qwen": ("qwen_image", "qwen-image-2.0-pro", "DashScope API key"),
            "qwen_image": ("qwen_image", "qwen-image-2.0-pro", "DashScope API key"),
            "qwen-image": ("qwen_image", "qwen-image-2.0-pro", "DashScope API key"),
            "dashscope": ("qwen_image", "qwen-image-2.0-pro", "DashScope API key"),
            "aliyun": ("qwen_image", "qwen-image-2.0-pro", "DashScope API key"),
            "qwen_image_beijing": ("qwen_image_beijing", "qwen-image-2.0-pro", "DashScope Beijing API key"),
            "qwen-image-beijing": ("qwen_image_beijing", "qwen-image-2.0-pro", "DashScope Beijing API key"),
            "qwen_image_singapore": ("qwen_image_singapore", "qwen-image-2.0-pro", "DashScope Singapore API key"),
            "qwen-image-singapore": ("qwen_image_singapore", "qwen-image-2.0-pro", "DashScope Singapore API key"),
            "qwen_image_us": ("qwen_image_us", "qwen-image-2.0-pro", "DashScope US Virginia API key"),
            "qwen-image-us": ("qwen_image_us", "qwen-image-2.0-pro", "DashScope US Virginia API key"),
            "qwen_image_germany": ("qwen_image_germany", "qwen-image-2.0-pro", "DashScope Germany Frankfurt API key"),
            "qwen-image-germany": ("qwen_image_germany", "qwen-image-2.0-pro", "DashScope Germany Frankfurt API key"),
            "stability": ("stability", "stable-image-core", "Stability AI API key"),
            "stability_ai": ("stability", "stable-image-core", "Stability AI API key"),
            "stable_image": ("stability", "stable-image-core", "Stability AI API key"),
            "fal": ("fal", "fal-ai/flux/schnell", "fal.ai API key"),
            "fal_ai": ("fal", "fal-ai/flux/schnell", "fal.ai API key"),
            "fal.ai": ("fal", "fal-ai/flux/schnell", "fal.ai API key"),
        }
        if provider not in provider_aliases:
            print(json.dumps({
                "status": "error",
                "error": "unsupported_image_provider",
                "supported_providers": ["zai", "zhipu", "zhipuai", "bigmodel", "qwen_image", "qwen_image_beijing", "qwen_image_singapore", "qwen_image_us", "qwen_image_germany", "stability", "fal"],
            }, ensure_ascii=False, indent=2))
            return 1
        canonical_provider, default_model, prompt = provider_aliases[provider]
        api_key = str(getattr(args, "value", "") or "")
        if not api_key:
            import getpass

            api_key = getpass.getpass(f"{prompt}: ").strip()
        if not api_key:
            print(json.dumps({
                "status": "error",
                "error": f"missing_{canonical_provider}_image_api_key",
                "env_file": str(env_file),
            }, ensure_ascii=False, indent=2))
            return 1

        if getattr(args, "skip_validation", False):
            validation = _skipped_validation("image_generation", canonical_provider)
        else:
            validation = _validate_image_api_key(canonical_provider, api_key, timeout=float(args.validation_timeout))
            if not validation.get("ok"):
                validation.update({
                    "env_file": str(env_file),
                    "image_provider": canonical_provider,
                    "image_api_key_configured": False,
                    "image_api_key_preview": _mask_api_key(api_key),
                    "error": validation.get("error") or "validation_failed",
                })
                print(json.dumps(validation, ensure_ascii=False, indent=2))
                return 1

        values = _read_env_exports(env_file)
        values["DEEPSEEK_PROXY_TOOL_BRIDGE"] = "1"
        values["DEEPSEEK_PROXY_IMAGE_PROVIDER"] = canonical_provider
        values["DEEPSEEK_PROXY_IMAGE_MODEL"] = values.get("DEEPSEEK_PROXY_IMAGE_MODEL", default_model)
        values["DEEPSEEK_PROXY_IMAGE_SIZE"] = values.get("DEEPSEEK_PROXY_IMAGE_SIZE", "1024x1024")
        values["DEEPSEEK_PROXY_IMAGE_N"] = values.get("DEEPSEEK_PROXY_IMAGE_N", "1")
        values["DEEPSEEK_PROXY_IMAGE_DOWNLOAD"] = values.get("DEEPSEEK_PROXY_IMAGE_DOWNLOAD", "1")
        base_url = _image_generation_base_url_for_provider(canonical_provider)
        if base_url:
            values["DEEPSEEK_PROXY_IMAGE_BASE_URL"] = base_url
        else:
            values.pop("DEEPSEEK_PROXY_IMAGE_BASE_URL", None)
        provider_env_key = _image_provider_primary_env_key(canonical_provider)
        values[provider_env_key] = api_key
        values["DEEPSEEK_PROXY_IMAGE_API_KEY"] = api_key
        _write_env_exports(env_file, values)
        output = {
            "status": "ok",
            "env_file": str(env_file),
            "image_provider": canonical_provider,
            "image_model": values["DEEPSEEK_PROXY_IMAGE_MODEL"],
            "image_api_key_configured": True,
            "image_api_key_preview": _mask_api_key(api_key),
            "validation": validation,
        }
        if canonical_provider == "glm":
            output["glm_image_api_key_configured"] = True
        output["post_config_apply"] = _post_config_apply()
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0

    if args.config_command == "set-model":
        return _configure_model_api_command(args, env_file, legacy_command=False)

    if args.config_command == "custom-provider":
        return _custom_provider_config_command(args, env_file)

    if args.config_command == "set-effort":
        return _set_effort_contract(args, env_file)

    raise SystemExit("unknown config command")




def _git_root_for(path: Path) -> Path | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--show-toplevel"],
            text=True,
            capture_output=True,
            timeout=5,
            check=False,
        )
    except Exception:
        return None

    if result.returncode != 0:
        return None

    root = result.stdout.strip()
    return Path(root).expanduser() if root else None


def _git_status_porcelain(repo_root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "status", "--porcelain"],
            text=True,
            capture_output=True,
            timeout=5,
            check=False,
        )
    except Exception as exc:
        return f"<status failed: {type(exc).__name__}: {exc}>"

    if result.returncode != 0:
        return result.stderr.strip() or result.stdout.strip()

    return result.stdout.strip()


def _is_upgrade_managed_resource_dirty_line(line: str) -> bool:
    stripped = str(line or "").rstrip("\n")
    if not stripped.startswith("?? "):
        return False
    path = stripped[3:].strip().strip('"')
    return path in {"resources", "resources/"} or path.startswith("resources/")


def _filter_upgrade_dirty_worktree_status(status: str) -> tuple[str, str]:
    kept: list[str] = []
    ignored: list[str] = []
    for line in str(status or "").splitlines():
        if not line.strip():
            continue
        if _is_upgrade_managed_resource_dirty_line(line):
            ignored.append(line)
        else:
            kept.append(line)
    return "\n".join(kept).strip(), "\n".join(ignored).strip()


def _git_commit_for_ref_in_repo(repo_root: Path, ref: str) -> str:
    if not ref:
        return ""
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "--short", f"{ref}^{{commit}}"],
            text=True,
            capture_output=True,
            timeout=5,
            check=False,
        )
    except Exception:
        return ""
    value = result.stdout.strip()
    if result.returncode != 0 or not value:
        return ""
    return value.splitlines()[0].strip() or ""


def _git_remote_tag_commit_in_repo(repo_root: Path, tag: str, remote: str = "origin") -> str:
    if not tag:
        return ""
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "ls-remote", "--tags", remote, tag],
            text=True,
            capture_output=True,
            timeout=15,
            check=False,
        )
    except Exception:
        return ""
    if result.returncode != 0:
        return ""
    direct = ""
    peeled = ""
    for line in result.stdout.splitlines():
        parts = line.strip().split()
        if len(parts) < 2:
            continue
        commit, ref = parts[0].strip(), parts[1].strip()
        if ref.endswith(f"refs/tags/{tag}^{{}}"):
            peeled = commit[:7]
        elif ref.endswith(f"refs/tags/{tag}"):
            direct = commit[:7]
    return peeled or direct





def _upgrade_tty_enabled() -> bool:
    return bool(sys.stdin.isatty() and sys.stderr.isatty() and os.environ.get("DEEPSEEK_PROXY_UPGRADE_JSON_ONLY") != "1")


def _upgrade_render_tty_panel(title: str, lines: list[str], *, footer: str = "Upgrade") -> None:
    if not _upgrade_tty_enabled():
        return
    print("\033[?25h\033[H\033[J\033[3J", end="", file=sys.stderr)
    _wizard_render_panel(title, lines, footer=footer)


def _upgrade_bootstrap_urls_for_ref(target_ref: str, *, target_source: str | None = None) -> list[str]:
    ref = str(target_ref or "").strip()
    urls: list[str] = []
    if target_source == "latest_release":
        urls.append("https://github.com/Awenforever/CoDeepSeedeX/releases/latest/download/bootstrap.sh")
    if ref:
        quoted_ref = urllib.parse.quote(ref, safe="")
        urls.extend([
            f"https://github.com/Awenforever/CoDeepSeedeX/releases/download/{quoted_ref}/bootstrap.sh",
            f"https://raw.githubusercontent.com/Awenforever/CoDeepSeedeX/{urllib.parse.quote(ref, safe='/._-')}/bootstrap.sh",
            f"https://github.com/Awenforever/CoDeepSeedeX/raw/refs/tags/{quoted_ref}/bootstrap.sh",
        ])
    deduped: list[str] = []
    for url in urls:
        if url not in deduped:
            deduped.append(url)
    return deduped


def _upgrade_bootstrap_command_for_non_git(
    target_ref: str,
    bootstrap_path: Path,
    repo_hint: Path,
    *,
    skip_profile: bool = False,
) -> list[str]:
    cmd = [
        "bash",
        str(bootstrap_path),
        "--install-ref",
        target_ref,
        "--",
        "--non-interactive",
        "--install-dir",
        str(repo_hint),
    ]
    if skip_profile:
        cmd.append("--no-codex-profile")
    return cmd


def _download_upgrade_bootstrap(
    result: dict[str, Any],
    *,
    target_ref: str,
    target_source: str,
    bootstrap_path: Path,
    dry_run: bool,
) -> bool:
    urls = _upgrade_bootstrap_urls_for_ref(target_ref, target_source=target_source)
    result["one_line_upgrade"] = f"curl -fsSL https://github.com/Awenforever/CoDeepSeedeX/releases/download/{target_ref}/bootstrap.sh | bash -s -- --install-ref {target_ref}"
    result["bootstrap_urls"] = urls
    step: dict[str, Any] = {
        "label": "download_release_bootstrap",
        "urls": urls,
        "target": str(bootstrap_path),
        "dry_run": dry_run,
    }
    result.setdefault("steps", []).append(step)
    if dry_run:
        step["skipped"] = True
        return True

    last_error = None
    for url in urls:
        try:
            request = urllib.request.Request(
                url,
                headers={
                    "User-Agent": f"CoDeepSeedeX/{PROXY_VERSION}",
                    "Accept": "application/octet-stream,*/*",
                },
            )
            with urllib.request.urlopen(request, timeout=120) as response:
                raw = response.read()
            if not raw.startswith(b"#!/") and b"bash" not in raw[:200]:
                raise RuntimeError("downloaded bootstrap asset does not look like a shell script")
            bootstrap_path.write_bytes(raw)
            bootstrap_path.chmod(0o755)
            step["selected_url"] = url
            step["bytes"] = len(raw)
            return True
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            step.setdefault("attempts", []).append({"url": url, "error": last_error})
    step["error"] = last_error
    return False


def _upgrade_non_git_install(
    result: dict[str, Any],
    *,
    target_ref: str,
    target_source: str,
    repo_hint: Path,
    args: argparse.Namespace,
    dry_run: bool,
    upgrade_path: str = "non_git_release_bootstrap",
    non_git_install: bool = True,
    hint: str | None = None,
) -> int:
    result.update({
        "status": "ok",
        "upgrade_path": upgrade_path,
        "non_git_install": non_git_install,
        "repo_root": None if non_git_install else str(repo_hint),
        "hint": hint or "This install is not a git checkout, so dsproxy upgrade will rerun the release bootstrap installer with an explicit install ref.",
        "fallback": "If the automatic release-bootstrap upgrade fails, rerun the one-line installer shown in one_line_upgrade.",
    })
    same_public_version = _release_tag_matches_runtime(target_ref, str(result.get("current_public_version") or ""))
    result["same_public_version"] = same_public_version
    if same_public_version and not bool(result.get("force_reinstall")):
        result.update({
            "status": "already_up_to_date",
            "skipped": True,
            "skip_reason": "same_public_version_non_git_install",
            "message": f"Already on {result.get('current_public_version')}; pass --force to rerun the release bootstrap installer.",
        })
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    with tempfile.TemporaryDirectory(prefix="codeepseedex-upgrade-bootstrap-") as tmp:
        bootstrap_path = Path(tmp) / "bootstrap.sh"
        if not _download_upgrade_bootstrap(
            result,
            target_ref=target_ref,
            target_source=target_source,
            bootstrap_path=bootstrap_path,
            dry_run=dry_run,
        ):
            result.update({"status": "error", "error": "bootstrap_download_failed"})
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 1

        cmd = _upgrade_bootstrap_command_for_non_git(
            target_ref,
            bootstrap_path,
            repo_hint,
            skip_profile=bool(args.skip_profile),
        )
        step: dict[str, Any] = {
            "label": "run_release_bootstrap_installer",
            "cmd": cmd,
            "cwd": str(Path.home()),
            "dry_run": dry_run,
        }
        if bool(args.no_restart):
            step["no_restart_note"] = "The installer fallback does not start proxy processes; no restart is performed by this non-git path."
        if bool(args.no_backup):
            step["no_backup_note"] = "The installer fallback may still create its own safety backups for replaced install directories."
        result.setdefault("steps", []).append(step)

        if dry_run:
            step["skipped"] = True
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0

        _upgrade_render_tty_panel(
            "Upgrade fallback",
            [
                "This install will use the release bootstrap installer.",
                f"Target: {target_ref}",
                f"Install dir: {repo_hint}",
            ],
            footer="Upgrade",
        )

        env = os.environ.copy()
        for metadata_key in (
            "DEEPSEEK_PROXY_PUBLIC_COMMIT",
            "DEEPSEEK_PROXY_INTERNAL_COMMIT",
            "DEEPSEEK_PROXY_INTERNAL_VERSION",
        ):
            env.pop(metadata_key, None)
        env["DEEPSEEK_PROXY_INSTALL_REF"] = target_ref
        env["DEEPSEEK_PROXY_INSTALL_DIR"] = str(repo_hint)
        step["metadata_env_sanitized"] = True
        try:
            completed = subprocess.run(
                cmd,
                cwd=str(Path.home()),
                env=env,
                text=True,
                capture_output=True,
                timeout=900,
                check=False,
            )
        except Exception as exc:
            step["returncode"] = None
            step["error"] = f"{type(exc).__name__}: {exc}"
            result.update({"status": "error", "error": "bootstrap_installer_failed"})
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 1

        step["returncode"] = completed.returncode
        step["stdout"] = completed.stdout[-4000:]
        step["stderr"] = completed.stderr[-4000:]
        if completed.returncode != 0:
            result.update({"status": "error", "error": "bootstrap_installer_failed"})
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 1

    result["configuration_guidance"] = _api_configuration_status(default_env_file_path())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _upgrade_commit_matches(current_commit: str | None, target_commit: str | None) -> bool:
    current = str(current_commit or "").strip()
    target = str(target_commit or "").strip()
    if not current or not target or current == "unknown":
        return False
    return current == target or current.startswith(target) or target.startswith(current)


def _should_skip_same_public_version_upgrade(
    *,
    current_public_version: str | None,
    current_public_commit: str | None,
    target_ref: str | None,
    target_commit: str | None,
    force: bool = False,
) -> bool:
    if force:
        return False
    if not _release_tag_matches_runtime(str(target_ref or ""), str(current_public_version or "")):
        return False
    target = str(target_commit or "").strip()
    if not target:
        return True
    return _upgrade_commit_matches(current_public_commit, target)

def _backup_upgrade_file(path: Path, backup_dir: Path, result: dict[str, Any]) -> None:
    if not path.exists():
        return

    backup_dir.mkdir(parents=True, exist_ok=True)
    target = backup_dir / path.name
    if target.exists():
        target = backup_dir / f"{path.name}.{int(time.time())}"
    shutil.copy2(path, target)
    result.setdefault("backups", []).append({"source": str(path), "backup": str(target)})


def _upgrade_run_step(
    result: dict[str, Any],
    *,
    label: str,
    argv: list[str],
    cwd: Path,
    dry_run: bool,
    allow_failure: bool = False,
) -> bool:
    step: dict[str, Any] = {
        "label": label,
        "cmd": argv,
        "cwd": str(cwd),
        "dry_run": dry_run,
    }
    result.setdefault("steps", []).append(step)

    if dry_run:
        step["skipped"] = True
        return True

    _upgrade_render_tty_panel(
        "Upgrade running",
        [
            f"Step: {label}",
            f"Target: {result.get('target_ref') or '<unknown>'}",
            f"Repository: {result.get('repo_root') or cwd}",
        ],
        footer="Upgrade",
    )

    try:
        completed = subprocess.run(
            argv,
            cwd=str(cwd),
            text=True,
            capture_output=True,
            timeout=300,
            check=False,
        )
    except Exception as exc:
        step["returncode"] = None
        step["error"] = f"{type(exc).__name__}: {exc}"
        return bool(allow_failure)

    step["returncode"] = completed.returncode
    step["stdout"] = completed.stdout[-2000:]
    step["stderr"] = completed.stderr[-2000:]

    if completed.returncode != 0 and not allow_failure:
        return False

    return True



LATEST_RELEASE_API_URL = "https://api.github.com/repos/Awenforever/CoDeepSeedeX/releases/latest"
ALPHA_RELEASES_API_URL = "https://api.github.com/repos/Awenforever/CoDeepSeedeX/releases?per_page=50"


def _default_latest_release_fallback_tag() -> str:
    configured = str(os.environ.get("DEEPSEEK_PROXY_LATEST_RELEASE_FALLBACK_TAG") or "").strip()
    if configured:
        return configured
    current = str(PROXY_PUBLIC_VERSION or "").strip()
    if re.match(r"^v\d+\.\d+\.\d+(?:[-+][A-Za-z0-9_.-]+)?$", current):
        return current
    return ""


def _latest_release_resolution_fallback(
    *,
    release_url: str,
    exc: BaseException,
) -> tuple[str, dict[str, Any]] | None:
    fallback_tag = _default_latest_release_fallback_tag()
    if not fallback_tag:
        return None
    return fallback_tag, {
        "api_url": release_url,
        "tag_name": fallback_tag,
        "name": f"CoDeepSeedeX {fallback_tag}",
        "html_url": f"https://github.com/Awenforever/CoDeepSeedeX/releases/tag/{fallback_tag}",
        "prerelease": False,
        "draft": False,
        "resolution_fallback": True,
        "fallback_reason": "latest_release_resolution_failed",
        "resolution_error": f"{type(exc).__name__}: {exc}",
        "fallback_source": "DEEPSEEK_PROXY_LATEST_RELEASE_FALLBACK_TAG_or_runtime_public_version",
    }


def _resolve_latest_release_tag(api_url: str | None = None, *, timeout: float | None = None) -> tuple[str, dict[str, Any]]:
    url = api_url or os.environ.get("DEEPSEEK_PROXY_LATEST_RELEASE_API_URL") or LATEST_RELEASE_API_URL
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"CoDeepSeedeX/{PROXY_VERSION}",
        },
    )
    with urllib.request.urlopen(request, timeout=15 if timeout is None else timeout) as response:
        raw = response.read().decode("utf-8")
    data = json.loads(raw)
    tag = data.get("tag_name") or data.get("tagName")
    if not isinstance(tag, str) or not tag.strip():
        raise RuntimeError("latest release response did not contain tag_name")
    return tag.strip(), {
        "api_url": url,
        "tag_name": tag.strip(),
        "name": data.get("name"),
        "html_url": data.get("html_url"),
        "prerelease": data.get("prerelease"),
        "draft": data.get("draft"),
    }

def _resolve_latest_prerelease_tag(api_url: str | None = None, *, timeout: float | None = None) -> tuple[str, dict[str, Any]]:
    url = api_url or os.environ.get("DEEPSEEK_PROXY_ALPHA_RELEASES_API_URL") or ALPHA_RELEASES_API_URL
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"CoDeepSeedeX/{PROXY_VERSION}",
        },
    )
    with urllib.request.urlopen(request, timeout=15 if timeout is None else timeout) as response:
        raw = response.read().decode("utf-8")
    data = json.loads(raw)
    if not isinstance(data, list):
        raise RuntimeError("GitHub releases response was not a list")
    for release in data:
        if not isinstance(release, dict):
            continue
        if bool(release.get("draft")):
            continue
        if not bool(release.get("prerelease") or release.get("isPrerelease")):
            continue
        tag = release.get("tag_name") or release.get("tagName")
        if isinstance(tag, str) and tag.strip():
            return tag.strip(), {
                "api_url": url,
                "tag_name": tag.strip(),
                "name": release.get("name"),
                "html_url": release.get("html_url") or release.get("url"),
                "prerelease": release.get("prerelease", release.get("isPrerelease")),
                "draft": release.get("draft"),
            }
    raise RuntimeError("GitHub releases response did not contain a non-draft pre-release tag")



def _upgrade(args: argparse.Namespace) -> int:
    repo_hint = Path(args.repo).expanduser() if args.repo else Path(__file__).resolve().parents[1]
    requested_ref = args.tag
    alpha_channel = bool(getattr(args, "alpha", False))
    dry_run = bool(args.dry_run)
    force_reinstall = bool(getattr(args, "force", False) or getattr(args, "force_reinstall", False))

    latest_release: dict[str, Any] | None = None
    if requested_ref and alpha_channel:
        print(json.dumps({
            "status": "error",
            "operation": "upgrade",
            "current_runtime_version": PROXY_VERSION,
            "error": "conflicting_upgrade_target",
            "message": "Use either --tag for an explicit ref or --alpha for the latest GitHub pre-release, not both.",
            "mode": "dsproxy_upgrade",
            "dry_run": dry_run,
        }, ensure_ascii=False, indent=2))
        return 2

    if requested_ref:
        target_ref = requested_ref
        target_source = "explicit_ref"
    else:
        try:
            if alpha_channel:
                target_ref, latest_release = _resolve_latest_prerelease_tag(getattr(args, "alpha_release_url", None))
                target_source = "latest_prerelease"
            else:
                target_ref, latest_release = _resolve_latest_release_tag(args.latest_release_url)
                target_source = "latest_release"
        except Exception as exc:
            if alpha_channel:
                release_url = getattr(args, "alpha_release_url", None) or os.environ.get("DEEPSEEK_PROXY_ALPHA_RELEASES_API_URL") or ALPHA_RELEASES_API_URL
                error_code = "latest_prerelease_resolution_failed"
                hint = "Alpha upgrades follow the newest non-draft GitHub pre-release. Pass --tag <tag-or-branch> to select an explicit ref, or publish a pre-release first."
                url_key = "alpha_release_url"
                result = {
                    "status": "error",
                    "operation": "upgrade",
                    "current_runtime_version": PROXY_VERSION,
                    "error": error_code,
                    "detail": f"{type(exc).__name__}: {exc}",
                    url_key: release_url,
                    "repo_hint": str(repo_hint),
                    "dry_run": dry_run,
                    "mode": "dsproxy_upgrade",
                    "hint": hint,
                }
                print(json.dumps(result, ensure_ascii=False, indent=2))
                return 1

            release_url = args.latest_release_url or os.environ.get("DEEPSEEK_PROXY_LATEST_RELEASE_API_URL") or LATEST_RELEASE_API_URL
            fallback = _latest_release_resolution_fallback(release_url=release_url, exc=exc)
            if fallback is None:
                result = {
                    "status": "error",
                    "operation": "upgrade",
                    "current_runtime_version": PROXY_VERSION,
                    "error": "latest_release_resolution_failed",
                    "detail": f"{type(exc).__name__}: {exc}",
                    "latest_release_url": release_url,
                    "repo_hint": str(repo_hint),
                    "dry_run": dry_run,
                    "mode": "dsproxy_upgrade",
                    "hint": "Default upgrades follow the GitHub Latest Release. Pass --tag <tag-or-branch> to select an explicit ref, or rerun the latest Release bootstrap installer.",
                }
                print(json.dumps(result, ensure_ascii=False, indent=2))
                return 1
            target_ref, latest_release = fallback
            target_source = "latest_release_resolution_fallback"

    release_channel = "explicit" if target_source == "explicit_ref" else ("alpha" if target_source == "latest_prerelease" else "latest")
    version_metadata = _version_metadata()
    result: dict[str, Any] = {
        "status": "ok",
        "operation": "upgrade",
        "current_runtime_version": PROXY_VERSION,
        "current_public_version": version_metadata.get("public_version"),
        "current_public_commit": version_metadata.get("public_commit"),
        "current_internal_version": version_metadata.get("internal_version"),
        "current_internal_commit": version_metadata.get("internal_commit"),
        "target_ref": target_ref,
        "target_source": target_source,
        "target_commit": None,
        "release_channel": release_channel,
        "latest_release": latest_release,
        "repo_hint": str(repo_hint),
        "dry_run": dry_run,
        "force_reinstall": force_reinstall,
        "mode": "dsproxy_upgrade",
        "fallback": "If this install is not a git checkout, rerun the one-line installer from the GitHub Latest Release.",
        "skip_profile": bool(args.skip_profile),
        "no_restart": bool(args.no_restart),
    }

    _upgrade_render_tty_panel(
        "Upgrade plan",
        [
            f"Current: {version_metadata.get('public_version') or PROXY_VERSION} | {version_metadata.get('public_commit') or 'unknown'}",
            f"Target: {target_ref}",
            f"Mode: {target_source}",
            f"Repository hint: {repo_hint}",
        ],
        footer="Upgrade",
    )

    repo_root = _git_root_for(repo_hint)
    if repo_root is None:
        return _upgrade_non_git_install(
            result,
            target_ref=target_ref,
            target_source=target_source,
            repo_hint=repo_hint,
            args=args,
            dry_run=dry_run,
        )

    result["repo_root"] = str(repo_root)

    dirty_raw = _git_status_porcelain(repo_root)
    dirty, ignored_managed_resources = _filter_upgrade_dirty_worktree_status(dirty_raw)
    result["git_dirty"] = bool(dirty)
    if ignored_managed_resources:
        result["git_dirty_ignored_managed_resources"] = ignored_managed_resources
        result["git_dirty_raw"] = dirty_raw
    if dirty and not args.allow_dirty:
        result.update({"status": "error", "error": "dirty_worktree", "git_status": dirty, "hint": "Commit, stash, or pass --allow-dirty if you understand the risk."})
        _upgrade_render_tty_panel(
            "Upgrade blocked",
            [
                "The installed checkout has local changes that are not managed resources.",
                "Commit, stash, or pass --allow-dirty if you understand the risk.",
                dirty,
            ],
            footer="Upgrade",
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1

    commands: list[tuple[str, list[str], bool]] = [
        ("git_fetch_tags", ["git", "-C", str(repo_root), "fetch", "--tags", "origin"], False),
    ]

    target_commit = ""
    remote_tag_commit = ""
    if not dry_run:
        remote_tag_commit = _git_remote_tag_commit_in_repo(repo_root, target_ref)
        target_commit = remote_tag_commit
        for label, argv, allow_failure in commands:
            ok = _upgrade_run_step(result, label=label, argv=argv, cwd=repo_root, dry_run=False, allow_failure=allow_failure)
            if not ok:
                result["git_upgrade_fallback_reason"] = label
                result["git_upgrade_fallback"] = "release_bootstrap_installer"
                return _upgrade_non_git_install(
                    result,
                    target_ref=target_ref,
                    target_source=target_source,
                    repo_hint=repo_root,
                    args=args,
                    dry_run=dry_run,
                    upgrade_path="git_fetch_failed_release_bootstrap",
                    non_git_install=False,
                    hint="Git fetch failed for this installed checkout, so dsproxy upgrade is falling back to the release bootstrap installer with an explicit install ref.",
                )
        if not target_commit:
            target_commit = _git_commit_for_ref_in_repo(repo_root, target_ref)
        result["target_commit"] = target_commit or None
        result["target_commit_source"] = "remote_tag" if remote_tag_commit else ("local_ref_after_fetch" if target_commit else None)
        result["same_public_version"] = _release_tag_matches_runtime(target_ref, str(version_metadata.get("public_version") or ""))
        result["public_commit_matches_target"] = _upgrade_commit_matches(version_metadata.get("public_commit"), target_commit)

        if _should_skip_same_public_version_upgrade(
            current_public_version=version_metadata.get("public_version"),
            current_public_commit=version_metadata.get("public_commit"),
            target_ref=target_ref,
            target_commit=target_commit,
            force=force_reinstall,
        ):
            result.update({
                "status": "already_up_to_date",
                "skipped": True,
                "skip_reason": "same_public_version_and_commit",
                "message": f"Already up to date ({version_metadata.get('public_version')} | {version_metadata.get('public_commit')})",
            })
            _upgrade_render_tty_panel(
                "Already up to date",
                [
                    str(result.get("message") or "Already up to date."),
                    f"Target: {target_ref}",
                ],
                footer="Upgrade",
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0

        if result["same_public_version"] and target_commit and not result["public_commit_matches_target"]:
            result["same_version_reinstall_reason"] = "release_tag_commit_changed"

        if remote_tag_commit:
            commands = [("git_fetch_target_tag_force", ["git", "-C", str(repo_root), "fetch", "--force", "origin", f"refs/tags/{target_ref}:refs/tags/{target_ref}"], False)]
        else:
            commands = []
    else:
        result["target_commit"] = None
        result["target_commit_source"] = None

    if not args.no_backup:
        safe_target_ref = re.sub(r"[^A-Za-z0-9_.-]+", "_", target_ref)
        backup_root = Path(args.backup_dir).expanduser() if args.backup_dir else _default_config_dir() / "upgrade-backups" / f"{safe_target_ref}-{int(time.time())}"
        _backup_upgrade_file(default_env_file_path(), backup_root, result)
        _backup_upgrade_file(default_codex_config_path(), backup_root, result)

    if dry_run:
        commands = [("git_fetch_tags", ["git", "-C", str(repo_root), "fetch", "--tags", "origin"], False)]

    if requested_ref:
        commands.append(("git_checkout_target", ["git", "-C", str(repo_root), "checkout", target_ref], False))
    else:
        checkout_label = "git_checkout_latest_prerelease" if alpha_channel else "git_checkout_latest_release"
        commands.append((checkout_label, ["git", "-C", str(repo_root), "checkout", target_ref], False))

    commands.append(("pip_install_editable", [sys.executable, "-m", "pip", "install", "-e", str(repo_root)], False))

    if not args.skip_profile:
        commands.extend([
            (
                "install_codex_profile_thinking",
                [
                    sys.executable,
                    "-m",
                    "deepseek_responses_proxy.cli",
                    "install-codex-profile",
                    "--name",
                    "deepseek-thinking",
                    "--provider-name",
                    "deepseek-thinking-proxy",
                    "--base-url",
                    "http://127.0.0.1:8001/v1",
                    "--model",
                    "deepseek-v4-pro",
                    "--reasoning-effort",
                    "xhigh",
                    "--profile-layout",
                    "split_profile_files",
                ],
                False,
            ),
        ])

    if not args.no_restart:
        commands.extend([
            ("stop_stable_proxy", [sys.executable, "-m", "deepseek_responses_proxy.cli", "stop"], True),
            ("stop_thinking_proxy", [sys.executable, "-m", "deepseek_responses_proxy.cli", "stop", "--thinking"], True),
            ("start_thinking_proxy", [sys.executable, "-m", "deepseek_responses_proxy.cli", "start", "--thinking"], False),
        ])

    for label, argv, allow_failure in commands:
        ok = _upgrade_run_step(result, label=label, argv=argv, cwd=repo_root, dry_run=dry_run, allow_failure=allow_failure)
        if not ok:
            result.update({"status": "error", "error": "upgrade_step_failed", "failed_step": label})
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 1

    if not dry_run and not args.no_restart and not args.no_verify:
        stable_status, stable_data, stable_error = _healthz_for_port(DEFAULT_STABLE_PORT, timeout=3.0)
        thinking_status, thinking_data, thinking_error = _healthz_for_port(DEFAULT_THINKING_PORT, timeout=3.0)
        result["runtime_verify"] = {
            "stable": {"http_status": stable_status, "data": stable_data, "error": stable_error},
            "thinking": {"http_status": thinking_status, "data": thinking_data, "error": thinking_error},
        }

    result["configuration_guidance"] = _api_configuration_status(default_env_file_path())
    missing_api = any(result["configuration_guidance"].get("missing", {}).values())
    if not dry_run and missing_api and not getattr(args, "skip_config_wizard", False) and sys.stdin.isatty():
        result["configuration_wizard"] = _run_guided_config(default_env_file_path(), emit_json=False)
        result["configuration_guidance"] = _api_configuration_status(default_env_file_path())

    _upgrade_render_tty_panel(
        "Upgrade complete",
        [
            f"Status: {result.get('status')}",
            f"Target: {target_ref}",
            "Run dsproxy --version and dsproxy config show to inspect the active runtime.",
        ],
        footer="Upgrade",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0



def _proxy_port_from_args(args: argparse.Namespace) -> int:
    if getattr(args, "port", None) is not None:
        return int(args.port)
    if getattr(args, "thinking", False):
        return 8001
    return 8000


def _proxy_base_url_from_args(args: argparse.Namespace) -> str:
    return f"http://127.0.0.1:{_proxy_port_from_args(args)}"


def _debug_fetch_json(url: str, timeout: float) -> dict[str, object]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                data = {"raw": raw}
            return {
                "ok": True,
                "status": getattr(response, "status", None),
                "url": url,
                "json": data,
            }
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = raw
        return {
            "ok": False,
            "status": exc.code,
            "url": url,
            "error": data,
        }
    except Exception as exc:
        return {
            "ok": False,
            "status": None,
            "url": url,
            "error": f"{type(exc).__name__}: {exc}",
        }


def _debug_budget_from_events(events: list[object]) -> dict[str, object]:
    budget_events = [
        event
        for event in events
        if isinstance(event, dict) and event.get("event") == "context_budget_breakdown"
    ]
    upstream_finished = [
        event
        for event in events
        if isinstance(event, dict) and event.get("event") == "upstream_call_finished"
    ]
    latest_budget = budget_events[-1] if budget_events else None
    latest_primary_usage = None
    for event in reversed(upstream_finished):
        if isinstance(event, dict) and event.get("purpose") == "primary":
            latest_primary_usage = event
            break

    tool_output_events = [
        event
        for event in events
        if isinstance(event, dict) and event.get("event") == "tool_output_budget_breakdown"
    ]
    latest_tool_output_budget = tool_output_events[-1] if tool_output_events else None
    tool_output_budget_truncated = bool(
        isinstance(latest_tool_output_budget, dict)
        and latest_tool_output_budget.get("truncated_event")
    )

    semantic_event_names = {
        "semantic_audit": "flattened_tool_transcript_semantic_audit",
        "semantic_policy_dry_run": "flattened_tool_transcript_semantic_policy_dry_run",
        "semantic_payload_compaction": "flattened_tool_transcript_semantic_payload_compaction_applied",
    }
    semantic_compaction: dict[str, object] = {}
    for label, event_name in semantic_event_names.items():
        matching = [
            event
            for event in events
            if isinstance(event, dict) and event.get("event") == event_name
        ]
        latest_event = matching[-1] if matching else None
        semantic_compaction[label] = {
            "found": latest_event is not None,
            "event": latest_event,
        }

    return {
        "found": latest_budget is not None,
        "event": latest_budget,
        "tool_output_budget": latest_tool_output_budget,
        "tool_output_budget_truncated": tool_output_budget_truncated,
        "tool_output_budget_error": "tool_output_budget_event_truncated" if tool_output_budget_truncated else None,
        "semantic_compaction": semantic_compaction,
        "primary_usage": latest_primary_usage,
    }


def _debug_semantic_compaction_summary(
    *,
    status_body: object,
    latest_body: object,
) -> dict[str, object]:
    status_semantic = None
    if isinstance(status_body, dict):
        status_semantic = status_body.get("semantic_compaction")

    events = latest_body.get("events", []) if isinstance(latest_body, dict) else []
    if not isinstance(events, list):
        events = []

    budget = _debug_budget_from_events(events)
    return {
        "status_semantic_compaction": status_semantic,
        "trace_semantic_compaction": budget.get("semantic_compaction"),
        "primary_usage": budget.get("primary_usage"),
    }


def _debug_behavioral_check_from_long_session(long_session: object) -> dict[str, object]:
    if not isinstance(long_session, dict):
        return {
            "status": "blocked",
            "assertions": {
                "has_long_session_report": False,
                "has_context_budget": False,
                "has_primary_usage": False,
                "has_tool_output_trim_events": False,
                "has_tool_output_trim_applied": False,
                "has_development_continuity_categories": False,
                "recommendation_is_monitor": False,
                "trace_current": False,
            },
            "metrics": {},
            "blockers": ["long_session_report_missing"],
            "recommendation": "inspect_debug_long_session_endpoint",
        }

    context_budget = long_session.get("context_budget") or {}
    primary_usage = long_session.get("primary_usage") or {}
    tool_output_trim = long_session.get("tool_output_trim") or {}
    runtime_payload = long_session.get("runtime_payload") or {}
    by_category = tool_output_trim.get("by_category") or {}

    if not isinstance(context_budget, dict):
        context_budget = {}
    if not isinstance(primary_usage, dict):
        primary_usage = {}
    if not isinstance(tool_output_trim, dict):
        tool_output_trim = {}
    if not isinstance(runtime_payload, dict):
        runtime_payload = {}
    if not isinstance(by_category, dict):
        by_category = {}

    def _positive_number(value: object) -> bool:
        return isinstance(value, (int, float)) and value > 0

    def _category_trimmed(category: str) -> bool:
        value = by_category.get(category)
        return isinstance(value, dict) and _positive_number(value.get("trimmed_item_count"))

    monitor_state = str(long_session.get("monitor_state") or "")
    trace_stale = bool(long_session.get("trace_stale"))
    current_runtime_payload_seen = bool(long_session.get("current_runtime_payload_seen"))
    trace_current = monitor_state not in {"trace_disabled", "trace_stale"} and not trace_stale

    has_long_session_report = (
        long_session.get("status") == "ok"
        and long_session.get("kind") == "runtime_long_session_observability"
    )
    has_context_budget = (
        _positive_number(context_budget.get("latest_chars"))
        or _positive_number(context_budget.get("max_chars"))
        or _positive_number(context_budget.get("event_count"))
    )
    has_primary_usage = (
        _positive_number(primary_usage.get("latest_prompt_tokens"))
        or _positive_number(primary_usage.get("max_prompt_tokens"))
        or _positive_number(primary_usage.get("event_count"))
    )
    has_tool_output_trim_events = _positive_number(tool_output_trim.get("event_count"))
    has_tool_output_trim_applied = (
        _positive_number(tool_output_trim.get("applied_count"))
        and _positive_number(tool_output_trim.get("chars_removed"))
    )
    has_development_continuity_categories = any(
        _category_trimmed(category)
        for category in ("shell_command", "interactive_shell", "image_payload")
    )
    recommendation_is_monitor = long_session.get("recommendation") == "monitor_limited_enabled_session"

    assertions = {
        "has_long_session_report": has_long_session_report,
        "has_context_budget": has_context_budget,
        "has_primary_usage": has_primary_usage,
        "has_tool_output_trim_events": has_tool_output_trim_events,
        "has_tool_output_trim_applied": has_tool_output_trim_applied,
        "has_development_continuity_categories": has_development_continuity_categories,
        "recommendation_is_monitor": recommendation_is_monitor,
        "trace_current": trace_current,
    }

    blockers = [name for name, ok in assertions.items() if not ok]
    if not has_long_session_report:
        status = "blocked"
        recommendation = "inspect_debug_long_session_endpoint"
    elif not trace_current:
        status = "monitor_stale"
        recommendation = "inspect_current_runtime_payload_or_enable_debug_trace"
    elif not has_context_budget or not has_primary_usage:
        status = "collect_more_trace_data"
        recommendation = "collect_more_trace_data"
    elif has_tool_output_trim_applied and has_development_continuity_categories:
        status = "ready"
        recommendation = "ready_for_real_long_session_behavioral_test"
    else:
        status = "monitor"
        recommendation = "continue_runtime_observation"

    marker_summary = runtime_payload.get("tool_output_trim_marker_summary") or {}
    if not isinstance(marker_summary, dict):
        marker_summary = {}

    metrics = {
        "trace_event_count": long_session.get("trace_event_count"),
        "response_count": long_session.get("response_count"),
        "context_latest_chars": context_budget.get("latest_chars"),
        "context_max_chars": context_budget.get("max_chars"),
        "latest_prompt_tokens": primary_usage.get("latest_prompt_tokens"),
        "max_prompt_tokens": primary_usage.get("max_prompt_tokens"),
        "tool_output_trim_event_count": tool_output_trim.get("event_count"),
        "tool_output_trim_applied_count": tool_output_trim.get("applied_count"),
        "tool_output_trim_chars_removed": tool_output_trim.get("chars_removed"),
        "image_payload_trim_count": tool_output_trim.get("image_payload_trim_count"),
        "trimmed_categories": sorted(
            category
            for category, summary in by_category.items()
            if isinstance(summary, dict) and _positive_number(summary.get("trimmed_item_count"))
        ),
        "long_session_recommendation": long_session.get("recommendation"),
        "monitor_state": monitor_state or None,
        "trace_stale": trace_stale,
        "current_runtime_payload_seen": current_runtime_payload_seen,
        "last_responses_payload_mtime": long_session.get("last_responses_payload_mtime"),
        "last_responses_payload_size": long_session.get("last_responses_payload_size"),
        "last_deepseek_payload_mtime": long_session.get("last_deepseek_payload_mtime"),
        "last_deepseek_payload_size": long_session.get("last_deepseek_payload_size"),
        "runtime_payload_trim_marker_count": marker_summary.get("marker_count"),
        "runtime_payload_image_payload_trim_count": marker_summary.get("image_payload_trim_count"),
    }

    return {
        "status": status,
        "assertions": assertions,
        "metrics": metrics,
        "blockers": blockers,
        "recommendation": recommendation,
    }


def _debug(args: argparse.Namespace) -> int:
    base_url = _proxy_base_url_from_args(args)
    command = getattr(args, "debug_command", "")

    if command == "behavioral":
        limit = max(1, min(int(getattr(args, "limit", 200)), 1000))
        timeout = float(getattr(args, "timeout", 3.0))
        path = f"/v1/proxy/debug/long-session?{urllib.parse.urlencode({'limit': limit, 'mode': 'aggregate'})}"
        result = _debug_fetch_json(base_url + path, timeout)
        long_session = result.get("json") if result.get("ok") else None
        output = {
            "status": "ok" if result.get("ok") else "error",
            "proxy_url": base_url,
            "debug_command": command,
            "result": {
                "ok": result.get("ok"),
                "status": result.get("status"),
                "url": result.get("url"),
            },
            "behavioral": _debug_behavioral_check_from_long_session(long_session),
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0 if result.get("ok") else 1

    if command == "long-session":
        limit = max(1, min(int(getattr(args, "limit", 200)), 1000))
        timeout = float(getattr(args, "timeout", 3.0))
        mode = str(getattr(args, "mode", "aggregate") or "aggregate")
        path = f"/v1/proxy/debug/long-session?{urllib.parse.urlencode({'limit': limit, 'mode': mode})}"
        result = _debug_fetch_json(base_url + path, timeout)
        output = {
            "status": "ok" if result.get("ok") else "error",
            "proxy_url": base_url,
            "debug_command": command,
            "result": result,
        }
        if result.get("ok"):
            output["long_session"] = result.get("json")
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0 if result.get("ok") else 1

    if command == "semantic":
        limit = max(1, min(int(getattr(args, "limit", 200)), 1000))
        timeout = float(getattr(args, "timeout", 3.0))
        if bool(getattr(args, "self_test", False)):
            selftest_result = _debug_fetch_json(base_url + "/v1/proxy/debug/semantic-selftest", timeout)
            ok = bool(selftest_result.get("ok"))
            output = {
                "status": "ok" if ok else "error",
                "proxy_url": base_url,
                "debug_command": command,
                "self_test": True,
                "result": selftest_result,
            }
            if ok:
                output["semantic_selftest"] = selftest_result.get("json")
            print(json.dumps(output, ensure_ascii=False, indent=2))
            return 0 if ok else 1

        status_result = _debug_fetch_json(base_url + "/v1/proxy/status", timeout)
        if bool(getattr(args, "canary_check", False)):
            canary_result = _debug_fetch_json(base_url + "/v1/proxy/debug/semantic-canary-check", timeout)
            ok = bool(canary_result.get("ok"))
            output = {
                "status": "ok" if ok else "error",
                "proxy_url": base_url,
                "debug_command": command,
                "canary_check": True,
                "result": canary_result,
            }
            if ok:
                output["semantic_canary_check"] = canary_result.get("json")
            print(json.dumps(output, ensure_ascii=False, indent=2))
            return 0 if ok else 1

        latest_path = f"/v1/proxy/debug/latest?{urllib.parse.urlencode({'limit': limit})}"
        latest_result = _debug_fetch_json(base_url + latest_path, timeout)
        ok = bool(status_result.get("ok") and latest_result.get("ok"))
        output = {
            "status": "ok" if ok else "error",
            "proxy_url": base_url,
            "debug_command": command,
            "status_result": status_result,
            "latest_result": latest_result,
        }
        if ok:
            output["semantic"] = _debug_semantic_compaction_summary(
                status_body=status_result.get("json"),
                latest_body=latest_result.get("json"),
            )
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0 if ok else 1

    if command == "status":
        path = "/v1/proxy/debug/status"
    elif command in {"latest", "budget"}:
        limit = max(1, min(int(getattr(args, "limit", 200)), 1000))
        path = f"/v1/proxy/debug/latest?{urllib.parse.urlencode({'limit': limit})}"
    else:
        print(json.dumps({
            "status": "error",
            "error": "unknown_debug_command",
            "command": command,
        }, ensure_ascii=False, indent=2))
        return 1

    result = _debug_fetch_json(base_url + path, float(getattr(args, "timeout", 3.0)))
    output = {
        "status": "ok" if result.get("ok") else "error",
        "proxy_url": base_url,
        "debug_command": command,
        "result": result,
    }

    if command == "budget" and result.get("ok"):
        body = result.get("json")
        events = body.get("events", []) if isinstance(body, dict) else []
        output["budget"] = _debug_budget_from_events(events)

    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


def _balance(args: argparse.Namespace) -> int:
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        env_values = _read_env_exports(Path(args.env_file).expanduser() if args.env_file else default_env_file_path())
        api_key = env_values.get("DEEPSEEK_API_KEY", "")

    if not api_key:
        print(json.dumps({
            "status": "error",
            "error": "missing_deepseek_api_key",
            "hint": "Set DEEPSEEK_API_KEY or write the local env file.",
        }, ensure_ascii=False, indent=2))
        return 1

    request = urllib.request.Request(
        args.url,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="GET",
    )

    try:
        with urllib.request.urlopen(request, timeout=args.timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            data = json.loads(raw)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        print(json.dumps({"status": "error", "http_status": exc.code, "body": raw[:2000]}, ensure_ascii=False, indent=2))
        return 1
    except Exception as exc:
        print(json.dumps({"status": "error", "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False, indent=2))
        return 1

    print(json.dumps({"status": "ok", "url": args.url, "balance": data}, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dsproxy", description="DeepSeek Responses Proxy command line tools")
    parser.add_argument("--version", action="store_true", help="print proxy version and exit")
    parser.add_argument("-H", "--help-all", action="help", help="show this help message and exit")

    sub = parser.add_subparsers(dest="command")

    start = sub.add_parser("start", help="start the local proxy")
    start.add_argument("target", nargs="?", choices=["thinking"], help="optional target: thinking")
    start.add_argument("--thinking", action="store_true", help="start thinking proxy on port 8001")
    start.add_argument("--port", type=int)
    start.add_argument("--state-dir")
    start.add_argument("--pid-file")
    start.add_argument("--log-file")
    start.add_argument("--db-path")
    start.set_defaults(func=_start_proxy)

    stop = sub.add_parser("stop", help="stop the local proxy")
    stop.add_argument("target", nargs="?", choices=["thinking"], help="optional target: thinking")
    stop.add_argument("--thinking", action="store_true")
    stop.add_argument("--state-dir")
    stop.add_argument("--pid-file")
    stop.add_argument("--port", type=int, help="accepted for consistency with start/status; stop uses the recorded pid file")
    stop.set_defaults(func=_stop_proxy)

    status = sub.add_parser("status", help="print /v1/proxy/status")
    status.add_argument("target", nargs="?", choices=["thinking"], help="optional target: thinking")
    status.add_argument("--thinking", action="store_true")
    status.add_argument("--port", type=int)
    status.add_argument("--timeout", type=float, default=3.0)
    status.add_argument("--json", action="store_true", help="print machine-readable proxy status JSON; alias for default status output")
    status.add_argument("--weclaw-json", action="store_true", help="print WeClaw integration status JSON")
    status.add_argument("--session-id", help="active Codex/ACP session id for current-session usage scope")
    status.set_defaults(func=_status)

    doctor = sub.add_parser("doctor", help="diagnose local proxy setup")
    doctor.add_argument("--thinking", action="store_true")
    doctor.add_argument("--port", type=int)
    doctor.add_argument("--timeout", type=float, default=3.0)
    doctor.add_argument("--allow-down", action="store_true", help="exit 0 even when proxy is not running")
    doctor_sub = doctor.add_subparsers(dest="doctor_command")
    doctor_providers = doctor_sub.add_parser("providers", help="check or live-probe web search and image providers")
    doctor_providers.add_argument("--env-file")
    doctor_providers.add_argument("--kind", choices=["all", "web-search", "image"], default="all")
    doctor_providers.add_argument("--provider", default="all")
    doctor_providers.add_argument("--live", action="store_true", help="run real provider requests")
    doctor_providers.add_argument("--allow-spend", action="store_true", help="allow live probes that may consume quota or credits")
    doctor_providers.add_argument("--timeout", type=float, default=10.0)
    doctor_providers.add_argument("--prompt", default=_PROVIDER_PROBE_PROMPT, help="prompt for live image generation probes")
    doctor_tool_routing = doctor_sub.add_parser("tool-routing", help="summarize managed native tool routing status without live provider calls")
    doctor_tool_routing.add_argument("--env-file")
    doctor_tool_routing.add_argument("--thinking", action="store_true", default=argparse.SUPPRESS)
    doctor_tool_routing.add_argument("--port", type=int, default=argparse.SUPPRESS)
    doctor_tool_routing.add_argument("--timeout", type=float, default=argparse.SUPPRESS)
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

    pricing = sub.add_parser("pricing", help="inspect or refresh dsproxy pricing cache")
    pricing_sub = pricing.add_subparsers(dest="pricing_command", required=True)

    pricing_show = pricing_sub.add_parser("show", help="show current pricing cache")
    pricing_show.add_argument("--json", action="store_true", help="accepted for explicit machine-readable output")
    pricing_show.add_argument("--model", default=None)
    pricing_show.set_defaults(func=_pricing)

    pricing_refresh = pricing_sub.add_parser("refresh", help="fetch and validate official DeepSeek pricing HTML")
    pricing_refresh.add_argument("--json", action="store_true", help="accepted for explicit machine-readable output")
    pricing_refresh.add_argument("--model", default=None)
    pricing_refresh.add_argument("--write-cache", action="store_true", help="atomically write validated pricing to the user cache")
    pricing_refresh.add_argument("--cache-path", default=None, help="optional explicit cache path for --write-cache")
    pricing_refresh.add_argument("--source-url", default="https://api-docs.deepseek.com/zh-cn/quick_start/pricing/")
    pricing_refresh.add_argument("--timeout", type=float, default=20.0)
    pricing_refresh.set_defaults(func=_pricing)

    tokenizer = sub.add_parser("tokenizer", help="manage profile tokenizer resources")
    tokenizer_sub = tokenizer.add_subparsers(dest="tokenizer_command", required=True)

    tokenizer_status = tokenizer_sub.add_parser("status", help="show local profile tokenizer resource status")
    tokenizer_status.add_argument("provider", nargs="?", default="deepseek", choices=["deepseek"])
    tokenizer_status.add_argument("--json", action="store_true", help="accepted for explicit machine-readable output")
    tokenizer_status.add_argument("--resource-dir", help="tokenizer resource root; defaults to env/install/user resource dir")
    tokenizer_status.set_defaults(func=_tokenizer)

    tokenizer_sync = tokenizer_sub.add_parser("sync", help="download and verify official profile tokenizer resources")
    tokenizer_sync.add_argument("provider", nargs="?", default="deepseek", choices=["deepseek"])
    tokenizer_sync.add_argument("--json", action="store_true", help="accepted for explicit machine-readable output")
    tokenizer_sync.add_argument("--resource-dir", help="tokenizer resource root; defaults to env/install/user resource dir")
    tokenizer_sync.add_argument("--source-url", default=DEEPSEEK_TOKENIZER_SOURCE_URL)
    tokenizer_sync.add_argument("--expected-sha256", default=DEEPSEEK_TOKENIZER_ZIP_SHA256)
    tokenizer_sync.add_argument("--timeout", type=float, default=60.0)
    tokenizer_sync.add_argument("--force", action="store_true", help="replace an existing synced tokenizer resource")
    tokenizer_sync.set_defaults(func=_tokenizer)

    config = sub.add_parser("config", help="manage local config")
    config_sub = config.add_subparsers(dest="config_command", required=True)

    config_path = config_sub.add_parser("path", help="print config path")
    config_path.add_argument("--path")
    config_path.set_defaults(func=_config)

    config_init = config_sub.add_parser("init", help="write default config")
    config_init.add_argument("--path")
    config_init.add_argument("--force", action="store_true")
    config_init.set_defaults(func=_config)

    config_show = config_sub.add_parser("show", help="show local env configuration")
    config_show.add_argument("--env-file")
    config_show.set_defaults(func=_config)

    config_wizard = config_sub.add_parser("wizard", help="guided API configuration wizard")
    config_wizard.add_argument("--env-file")
    config_wizard.add_argument("--non-interactive", action="store_true", help="report missing API configuration without prompting")
    config_wizard.set_defaults(func=_config)

    config_set_tool_routing = config_sub.add_parser("set-tool-routing", help="set managed native tool routing policy")
    config_set_tool_routing.add_argument("tool", choices=["web", "web-search", "web_search", "image", "image-generation", "image_generation"])
    config_set_tool_routing.add_argument("policy", choices=["auto", "managed-only", "managed_only", "native-only", "native_only", "disabled"])
    config_set_tool_routing.add_argument("--env-file")
    config_set_tool_routing.add_argument("--no-refresh", action="store_true", help="save configuration without refreshing running proxy processes")
    config_set_tool_routing.set_defaults(func=_config)

    config_set_api_key = config_sub.add_parser(
        "set-api-key",
        help="deprecated compatibility alias for model API key setup; prefer set-model",
        description="deprecated compatibility alias for model API key setup; prefer set-model (dsproxy config set-model).",
    )
    config_set_api_key.add_argument("--env-file")
    config_set_api_key.add_argument("--provider", default="deepseek", choices=_supported_model_api_providers())
    config_set_api_key.add_argument("--base-url", help="OpenAI-compatible base URL; required for --provider custom")
    config_set_api_key.add_argument("--model", help="upstream model name; required for --provider custom")
    config_set_api_key.add_argument("--value", help="API key value; omit to enter hidden input")
    config_set_api_key.add_argument("--skip-validation", action="store_true", help="store without validating the API key")
    config_set_api_key.add_argument("--validation-url", default="https://api.deepseek.com/user/balance")
    config_set_api_key.add_argument("--validation-timeout", type=float, default=10.0)
    config_set_api_key.set_defaults(func=_config)

    config_test_api_key = config_sub.add_parser("test-api-key", help="validate model API key")
    config_test_api_key.add_argument("--env-file")
    config_test_api_key.add_argument("--provider", default=None, choices=_supported_model_api_providers(), help="model API provider; defaults to DEEPSEEK_PROXY_MODEL_PROVIDER from env")
    config_test_api_key.add_argument("--base-url", help="OpenAI-compatible base URL for --provider custom or provider override")
    config_test_api_key.add_argument("--url", default="https://api.deepseek.com/user/balance")
    config_test_api_key.add_argument("--timeout", type=float, default=10.0)
    config_test_api_key.set_defaults(func=_config)


    config_set_web_search_api_key = config_sub.add_parser("set-web-search-api-key", help="store web search API key")
    config_set_web_search_api_key.add_argument("--env-file")
    config_set_web_search_api_key.add_argument("--provider", default="serpapi", choices=["serpapi", "tavily", "exa", "firecrawl"])
    config_set_web_search_api_key.add_argument("--value", help="API key value; omit to enter hidden input")
    config_set_web_search_api_key.add_argument("--skip-validation", action="store_true", help="store without validating the API key")
    config_set_web_search_api_key.add_argument("--validation-timeout", type=float, default=10.0)
    config_set_web_search_api_key.set_defaults(func=_config)

    config_set_image_api_key = config_sub.add_parser("set-image-api-key", help="store image generation API key")
    config_set_image_api_key.add_argument("--env-file")
    config_set_image_api_key.add_argument("--provider", default="zhipu", choices=["zhipu", "zhipuai", "bigmodel", "zai", "z.ai", "glm", "qwen", "qwen_image", "qwen-image", "dashscope", "aliyun", "qwen_image_beijing", "qwen-image-beijing", "qwen_image_singapore", "qwen-image-singapore", "qwen_image_us", "qwen-image-us", "qwen_image_germany", "qwen-image-germany", "stability", "stability_ai", "stable_image", "fal", "fal_ai", "fal.ai"], metavar="PROVIDER", help="image provider; current public providers: zhipu, zai, qwen_image, qwen_image_beijing, qwen_image_singapore, qwen_image_us, qwen_image_germany, stability, fal; legacy aliases remain accepted for compatibility")
    config_set_image_api_key.add_argument("--value", help="API key value; omit to enter hidden input")
    config_set_image_api_key.add_argument("--skip-validation", action="store_true", help="store without validating the API key")
    config_set_image_api_key.add_argument("--validation-timeout", type=float, default=10.0)
    config_set_image_api_key.set_defaults(func=_config)

    config_set_model = config_sub.add_parser("set-model", help="set model provider, upstream model, and optional model API key")
    config_set_model.add_argument("model", nargs="?", help="upstream model name; optional when --provider has a default")
    config_set_model.add_argument("--env-file")
    config_set_model.add_argument("--provider", choices=_supported_model_api_providers(), help="model API provider")
    config_set_model.add_argument("--base-url", help="OpenAI-compatible base URL; required for --provider custom")
    config_set_model.add_argument("--value", help="API key value; omit to enter hidden input when configuring provider credentials")
    config_set_model.add_argument("--skip-validation", action="store_true", help="store without validating the API key")
    config_set_model.add_argument("--validation-url", default="https://api.deepseek.com/user/balance")
    config_set_model.add_argument("--validation-timeout", type=float, default=10.0)
    config_set_model.add_argument("--codex-config")
    config_set_model.add_argument("--profile", default="__managed__", help="Codex profile name, or managed/all to update deepseek-thinking")
    config_set_model.set_defaults(func=_config)

    config_custom_provider = config_sub.add_parser("custom-provider", help="manage named custom OpenAI-compatible providers")
    config_custom_provider.add_argument("custom_provider_action", choices=["list", "show", "add", "update", "remove", "use", "validate", "models", "list-models", "add-model", "remove-model", "install-profile"])
    config_custom_provider.add_argument("--env-file")
    config_custom_provider.add_argument("--name", help="display-only custom provider name, e.g. ExampleProvider")
    config_custom_provider.add_argument("--base-url", help="OpenAI-compatible base URL")
    config_custom_provider.add_argument("--model", help="model id for this provider")
    config_custom_provider.add_argument("--value", help="API key value; omit or pass --skip-validation to avoid live validation")
    config_custom_provider.add_argument("--skip-validation", action="store_true", help="store without validating the API key")
    config_custom_provider.add_argument("--validation-timeout", type=float, default=10.0)
    config_custom_provider.add_argument("--use", action="store_true", help="make provider/model active after add or add-model")
    config_custom_provider.add_argument("--display-name", help="new display name for update")
    config_custom_provider.add_argument("--profile-name", help="Codex profile name to generate; defaults to the provider id")
    config_custom_provider.add_argument("--codex-config", help="Codex main config path for profile generation/removal")
    config_custom_provider.add_argument("--install-profile", action="store_true", help="generate codex --profile <provider> without activating it")
    config_custom_provider.add_argument("--no-profile-sync", action="store_true", help="do not write/remove Codex profile files")
    config_custom_provider.set_defaults(func=_config)

    config_set_effort = config_sub.add_parser("set-effort", help="set Codex reasoning effort; low/medium are stored as high and Plan mode is pinned to high for DeepSeek compatibility")
    config_set_effort.add_argument("effort")
    config_set_effort.add_argument("--json", action="store_true", help="accepted for explicit machine-readable output")
    config_set_effort.add_argument("--env-file")
    config_set_effort.add_argument("--codex-config")
    config_set_effort.add_argument("--profile", default="__managed__", help="Codex profile name, or managed/all to update deepseek-thinking")
    config_set_effort.add_argument("--no-refresh", action="store_true", help="save configuration without refreshing running proxy processes")
    config_set_effort.set_defaults(func=_config)

    provider = sub.add_parser("provider", help="manage named custom model API providers and their Codex profiles")
    provider.add_argument("provider_action", choices=["list", "show", "add", "update", "remove", "use", "validate", "models", "list-models", "add-model", "remove-model", "install-profile"])
    provider.add_argument("--env-file")
    provider.add_argument("--name", help="provider name or provider id")
    provider.add_argument("--display-name", help="new display name for update")
    provider.add_argument("--base-url", help="OpenAI-compatible base URL")
    provider.add_argument("--model", help="model id for this provider")
    provider.add_argument("--value", help="API key value; omit or pass --skip-validation to avoid live validation")
    provider.add_argument("--skip-validation", action="store_true", help="store without validating the API key")
    provider.add_argument("--validation-timeout", type=float, default=10.0)
    provider.add_argument("--use", action="store_true", help="make provider/model active after add or add-model")
    provider.add_argument("--profile-name", help="Codex profile name to generate; defaults to the provider id")
    provider.add_argument("--codex-config", help="Codex main config path for profile generation/removal")
    provider.add_argument("--install-profile", action="store_true", help="generate codex --profile <provider> without activating it")
    provider.add_argument("--no-profile-sync", action="store_true", help="do not write/remove Codex profile files")
    provider.set_defaults(func=_provider)

    profile = sub.add_parser("profile", help="inspect and manage CoDeepSeedeX-owned Codex profiles")
    profile_sub = profile.add_subparsers(dest="profile_command", required=True)

    profile_status = profile_sub.add_parser("status", help="print machine-readable Codex profile status")
    profile_status.add_argument("profile", nargs="?", default="deepseek-thinking")
    profile_status.add_argument("--json", action="store_true", help="accepted for explicit machine-readable output")
    profile_status.add_argument("--env-file")
    profile_status.add_argument("--codex-config")
    profile_status.set_defaults(func=_profile)

    profile_set_effort = profile_sub.add_parser("set-effort", help="set one managed Codex profile effort through the dsproxy contract")
    profile_set_effort.add_argument("profile")
    profile_set_effort.add_argument("effort")
    profile_set_effort.add_argument("--json", action="store_true", help="accepted for explicit machine-readable output")
    profile_set_effort.add_argument("--env-file")
    profile_set_effort.add_argument("--codex-config")
    profile_set_effort.add_argument("--no-refresh", action="store_true", help="save configuration without refreshing running proxy processes")
    profile_set_effort.set_defaults(func=_profile)

    profile_repair = profile_sub.add_parser("repair", help="repair managed Codex profile model and effort fields")
    profile_repair.add_argument("--managed-only", action="store_true", help="repair CoDeepSeedeX-managed profiles only")
    profile_repair.add_argument("--profile", default="__managed__", help="profile to repair when --managed-only is not used")
    profile_repair.add_argument("--env-file")
    profile_repair.add_argument("--codex-config")
    profile_repair.add_argument("--json", action="store_true", help="accepted for explicit machine-readable output")
    profile_repair.add_argument("--dry-run", action="store_true")
    profile_repair.add_argument("--auto-compact-ratio", type=float, default=None, help="derive managed profile model_auto_compact_token_limit from this ratio; do not pass absolute token thresholds")
    profile_repair.set_defaults(func=_profile)

    profile_refresh_wrapper = profile_sub.add_parser("refresh-wrapper", help="refresh the managed Codex wrapper from the install manifest")
    profile_refresh_wrapper.add_argument("--manifest", help="install manifest path; defaults to ~/.config/deepseek-responses-proxy/install-manifest.env")
    profile_refresh_wrapper.add_argument("--json", action="store_true", help="accepted for explicit machine-readable output")
    profile_refresh_wrapper.add_argument("--dry-run", action="store_true")
    profile_refresh_wrapper.add_argument("--force", action="store_true", help="allow backup and replacement of an unknown existing codex command")
    profile_refresh_wrapper.set_defaults(func=_profile)

    debug = sub.add_parser("debug", help="inspect proxy debug trace state")
    debug_sub = debug.add_subparsers(dest="debug_command", required=True)

    debug_status = debug_sub.add_parser("status", help="show debug trace status")
    debug_status.add_argument("--thinking", action="store_true")
    debug_status.add_argument("--port", type=int)
    debug_status.add_argument("--timeout", type=float, default=3.0)
    debug_status.set_defaults(func=_debug)

    debug_latest = debug_sub.add_parser("latest", help="show latest debug trace events")
    debug_latest.add_argument("--thinking", action="store_true")
    debug_latest.add_argument("--port", type=int)
    debug_latest.add_argument("--timeout", type=float, default=3.0)
    debug_latest.add_argument("--limit", type=int, default=200)
    debug_latest.set_defaults(func=_debug)

    debug_budget = debug_sub.add_parser("budget", help="show latest context budget breakdown")
    debug_budget.add_argument("--thinking", action="store_true")
    debug_budget.add_argument("--port", type=int)
    debug_budget.add_argument("--timeout", type=float, default=3.0)
    debug_budget.add_argument("--limit", type=int, default=200)
    debug_budget.set_defaults(func=_debug)

    debug_behavioral = debug_sub.add_parser("behavioral", help="summarize runtime behavioral readiness from long-session traces")
    debug_behavioral.add_argument("--thinking", action="store_true")
    debug_behavioral.add_argument("--port", type=int)
    debug_behavioral.add_argument("--timeout", type=float, default=3.0)
    debug_behavioral.add_argument("--limit", type=int, default=200)
    debug_behavioral.set_defaults(func=_debug)

    debug_long_session = debug_sub.add_parser("long-session", help="summarize recent long-session debug trace trends")
    debug_long_session.add_argument("--thinking", action="store_true")
    debug_long_session.add_argument("--port", type=int)
    debug_long_session.add_argument("--timeout", type=float, default=3.0)
    debug_long_session.add_argument("--limit", type=int, default=200)
    debug_long_session.add_argument("--mode", choices=["aggregate", "latest"], default="aggregate")
    debug_long_session.set_defaults(func=_debug)

    debug_semantic = debug_sub.add_parser("semantic", help="show semantic compaction rollout status")
    debug_semantic.add_argument("--thinking", action="store_true")
    debug_semantic.add_argument("--port", type=int)
    debug_semantic.add_argument("--timeout", type=float, default=3.0)
    debug_semantic.add_argument("--limit", type=int, default=200)
    debug_semantic.add_argument("--self-test", action="store_true", help="run local semantic compaction self-test")
    debug_semantic.add_argument("--canary-check", action="store_true", help="check whether semantic payload compaction canary rollout is ready")
    debug_semantic.set_defaults(func=_debug)

    balance = sub.add_parser("balance", help="query DeepSeek API account balance")
    balance.add_argument("--env-file")
    balance.add_argument("--url", default="https://api.deepseek.com/user/balance")
    balance.add_argument("--timeout", type=float, default=10.0)
    balance.set_defaults(func=_balance)

    upgrade = sub.add_parser("upgrade", help="upgrade a git checkout or source-archive installation")
    upgrade.add_argument("--tag", help="target git tag or ref; defaults to the GitHub Latest Release tag")
    upgrade.add_argument("--alpha", action="store_true", help="upgrade to the newest non-draft GitHub pre-release instead of the Latest Release")
    upgrade.add_argument("--latest-release-url", help="GitHub latest Release API URL; defaults to the CoDeepSeedeX releases/latest endpoint")
    upgrade.add_argument("--alpha-release-url", help="GitHub releases API URL used by --alpha; defaults to the CoDeepSeedeX releases list endpoint")
    upgrade.add_argument("--repo", help="installation repository path, defaults to the current package checkout")
    upgrade.add_argument("--dry-run", action="store_true", help="print the upgrade plan without changing files")
    upgrade.add_argument("--force", "--force-reinstall", dest="force", action="store_true", help="reinstall even when the target public version and commit already match")
    upgrade.add_argument("--allow-dirty", action="store_true", help="allow upgrade with a dirty git worktree")
    upgrade.add_argument("--no-backup", action="store_true", help="do not back up local env and Codex config files")
    upgrade.add_argument("--backup-dir", help="directory for env/Codex config backups")
    upgrade.add_argument("--skip-profile", action="store_true", help="do not refresh Codex profiles")
    upgrade.add_argument("--no-restart", action="store_true", help="do not restart local proxy processes")
    upgrade.add_argument("--no-verify", action="store_true", help="skip post-upgrade health checks")
    upgrade.add_argument("--skip-config-wizard", action="store_true", help="do not open the guided API configuration wizard after upgrade")
    upgrade.set_defaults(func=_upgrade)

    install_profile = sub.add_parser("install-codex-profile", help="install a Codex config profile")
    install_profile.add_argument("--name", default="deepseek-thinking")
    install_profile.add_argument("--path")
    install_profile.add_argument("--provider-name")
    install_profile.add_argument("--base-url", default="http://127.0.0.1:8001/v1")
    install_profile.add_argument("--model", default="deepseek-v4-pro")
    install_profile.add_argument("--reasoning-effort", default="xhigh")
    install_profile.add_argument("--context-window", type=int, default=DEFAULT_CONTEXT_WINDOW_TOKENS)
    install_profile.add_argument("--auto-compact-ratio", type=float, default=DEFAULT_AUTO_COMPACT_RATIO, help="derive model_auto_compact_token_limit from context window; managed default is 0.90")
    install_profile.add_argument("--auto-compact-token-limit", type=int, default=None, help=argparse.SUPPRESS)
    install_profile.add_argument("--tool-output-token-limit", type=int, default=12_000)
    install_profile.add_argument("--model-catalog-json")
    install_profile.add_argument("--dry-run", action="store_true")
    install_profile.add_argument("--no-backup", action="store_true")
    install_profile.add_argument("--profile-layout", choices=["auto", "split_profile_files", "legacy_profile_tables", "split", "legacy"], default="auto", help="Codex profile layout; auto uses legacy tables for Codex < 0.134 and split profile files for newer Codex")
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
    if getattr(args, "target", None) == "thinking":
        setattr(args, "thinking", True)

    if args.version:
        print(_format_version_metadata())
        return 0

    if getattr(args, "thinking_filter", None) is not None:
        args.thinking_filter = args.thinking_filter == "true"

    if not hasattr(args, "func"):
        parser.print_help()
        return 0

    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
