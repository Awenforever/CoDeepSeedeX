#!/usr/bin/env bash
# CodeXchange codex wrapper
# Auto-start CodeXchange when using CodeXchange Codex profiles.
#
# Add this function to ~/.bashrc after ~/bin is on PATH.
#
# Behavior:
# - codex --profile cox starts the thinking proxy on port 8001.
# - codex --profile <custom-provider-id> uses its pre-generated split profile and starts the required proxy.
# - codex --profile deepseek is deprecated and fails closed.

# BEGIN COX PROFILE-AGNOSTIC RUNTIME AUTOSTART
# Contract: codex --profile <name> is a one-command entrypoint for every
# CodeXchange-managed profile whose provider base_url points at a local
# Responses proxy. The wrapper resolves the profile, starts the required local
# proxy if it is absent, verifies /v1/models, then enters native Codex.
__codexchange_profile_arg() {
  local arg
  while [ "$#" -gt 0 ]; do
    arg="$1"
    case "$arg" in
      --profile|-p)
        shift || true
        [ "$#" -gt 0 ] && printf '%s\n' "$1"
        return 0
        ;;
      --profile=*)
        printf '%s\n' "${arg#--profile=}"
        return 0
        ;;
      --)
        return 0
        ;;
    esac
    shift || true
  done
}

__codexchange_toml_value() {
  local file key
  file="$1"; key="$2"
  [ -f "$file" ] || return 1
  awk -v k="$key" '
    function decode_basic_string(value, out, i, ch, escaped) {
      out=""
      escaped=0
      for (i=2; i<=length(value); i++) {
        ch=substr(value, i, 1)
        if (escaped) {
          if (ch == "\\" || ch == "\"") {
            out=out ch
          } else {
            out=out "\\" ch
          }
          escaped=0
          continue
        }
        if (ch == "\\") {
          escaped=1
          continue
        }
        if (ch == "\"") {
          return out
        }
        out=out ch
      }
      if (escaped) {
        out=out "\\"
      }
      return out
    }

    $0 ~ "^[[:space:]]*" k "[[:space:]]*=" {
      line=$0
      sub(/^[^=]*=/, "", line)
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", line)
      if (substr(line, 1, 1) == "\"") {
        line=decode_basic_string(line)
      }
      print line
      found=1
      exit
    }
    END { if (!found) exit 1 }
  ' "$file"
}

__codexchange_toml_has_key() {
  local file key
  file="$1"; key="$2"
  [ -f "$file" ] || return 1
  awk -v k="$key" '
    $0 ~ "^[[:space:]]*" k "[[:space:]]*=" { found=1; exit }
    END { if (!found) exit 1 }
  ' "$file"
}

__codexchange_profile_pricing_candidate() {
  local profile_file key present provider_id provider_owned mode provider_path
  profile_file="$1"
  __codexchange_profile_pricing_explicit=0
  __codexchange_profile_pricing_provider_id=""
  __codexchange_profile_pricing_mode=""
  __codexchange_profile_pricing_provider_path=""

  present=0
  for key in \
    pricing_provider_id \
    pricing_provider_owned \
    pricing_mode \
    pricing_provider_path; do
    if __codexchange_toml_has_key "$profile_file" "$key"; then
      present=$((present + 1))
    fi
  done

  [ "$present" -eq 0 ] && return 0
  if [ "$present" -ne 4 ]; then
    echo "CodeXchange: profile pricing fields are incomplete; require pricing_provider_id, pricing_provider_owned, pricing_mode, and pricing_provider_path." >&2
    return 70
  fi

  provider_id="$(__codexchange_toml_value "$profile_file" pricing_provider_id 2>/dev/null || true)"
  provider_owned="$(__codexchange_toml_value "$profile_file" pricing_provider_owned 2>/dev/null || true)"
  mode="$(__codexchange_toml_value "$profile_file" pricing_mode 2>/dev/null || true)"
  provider_path="$(__codexchange_toml_value "$profile_file" pricing_provider_path 2>/dev/null || true)"

  provider_id="$(printf '%s' "$provider_id" | tr '[:upper:]' '[:lower:]' | tr '-' '_')"
  mode="$(printf '%s' "$mode" | tr '[:upper:]' '[:lower:]' | tr '-' '_')"
  provider_owned="$(printf '%s' "$provider_owned" | tr '[:upper:]' '[:lower:]')"

  if [ "$provider_owned" != "true" ]; then
    echo "CodeXchange: pricing_provider_owned must be true for explicit profile pricing." >&2
    return 70
  fi
  if [ -z "$provider_id" ]; then
    echo "CodeXchange: pricing_provider_id is required for explicit profile pricing." >&2
    return 70
  fi
  if [ "$mode" != "provider_owned" ]; then
    echo "CodeXchange: pricing_mode must be provider_owned for explicit profile pricing." >&2
    return 70
  fi
  if [ -z "$provider_path" ]; then
    echo "CodeXchange: pricing_provider_path is required for explicit profile pricing." >&2
    return 70
  fi

  case "$provider_path" in
    ~/*) provider_path="$HOME/${provider_path#~/}" ;;
  esac
  case "$provider_path" in
    /*) ;;
    *)
      echo "CodeXchange: pricing_provider_path must be absolute after home expansion." >&2
      return 70
      ;;
  esac
  if [ ! -f "$provider_path" ]; then
    echo "CodeXchange: explicit profile pricing file does not exist: $provider_path" >&2
    return 70
  fi

  __codexchange_profile_pricing_explicit=1
  __codexchange_profile_pricing_provider_id="$provider_id"
  __codexchange_profile_pricing_mode="provider_owned"
  __codexchange_profile_pricing_provider_path="$provider_path"
  return 0
}

__codexchange_provider_base_url() {
  local provider file
  provider="$1"; shift || true
  [ -n "$provider" ] || return 1
  for file in "$@"; do
    [ -f "$file" ] || continue
    awk -v provider="$provider" '
      function trim(s) { gsub(/^[[:space:]]+|[[:space:]]+$/, "", s); return s }
      /^\[model_providers\./ {
        section=$0
        sub(/^\[model_providers\./, "", section)
        sub(/\]$/, "", section)
        gsub(/^"|"$/, "", section)
        in_section=(section == provider)
        next
      }
      /^\[/ { in_section=0 }
      in_section && /^[[:space:]]*base_url[[:space:]]*=/ {
        line=$0
        sub(/^[^=]*=/, "", line)
        line=trim(line)
        if (line ~ /^"/) { sub(/^"/, "", line); sub(/".*$/, "", line) }
        print line
        exit
      }
    ' "$file"
  done | head -n 1
}

__codexchange_local_proxy_port_from_base_url() {
  local base_url
  base_url="$1"
  case "$base_url" in
    http://127.0.0.1:*|http://localhost:*|http://[::1]:*)
      printf '%s\n' "$base_url" | sed -E 's#^http://(\[::1\]|127\.0\.0\.1|localhost):([0-9]+).*#\2#'
      ;;
    *) return 1 ;;
  esac
}

__codexchange_port_open() {
  local port
  port="$1"
  python3 - "$port" <<'PY_COX_PORT_OPEN' >/dev/null 2>&1
import socket, sys
port = int(sys.argv[1])
try:
    with socket.create_connection(("127.0.0.1", port), timeout=0.35):
        pass
except OSError:
    raise SystemExit(1)
PY_COX_PORT_OPEN
}

__codexchange_proxy_models_ok() {
  local port
  port="$1"
  if command -v curl >/dev/null 2>&1; then
    curl -fsS -m 3 "http://127.0.0.1:${port}/v1/models" >/dev/null 2>&1
    return $?
  fi
  python3 - "$port" <<'PY_COX_MODELS_OK' >/dev/null 2>&1
import sys, urllib.request
port = int(sys.argv[1])
with urllib.request.urlopen(f"http://127.0.0.1:{port}/v1/models", timeout=3) as r:
    if r.status != 200:
        raise SystemExit(1)
PY_COX_MODELS_OK
}

__codexchange_proxy_runtime_identity_matches() {
  local port expected_provider_id expected_mode expected_provider_path payload python_bin
  port="$1"
  expected_provider_id="$2"
  expected_mode="$3"
  expected_provider_path="$4"
  python_bin="$(command -v python3 || true)"
  [ -n "$python_bin" ] || return 1

  if command -v curl >/dev/null 2>&1; then
    payload="$(curl -fsS -m 3 "http://127.0.0.1:${port}/v1/proxy/status" 2>/dev/null)" || return 1
    "$python_bin" -c '
import json
import sys

expected_provider_id, expected_mode, expected_path = sys.argv[1:4]
try:
    payload = json.load(sys.stdin)
except Exception:
    raise SystemExit(1)
identity = payload.get("runtime_identity") if isinstance(payload, dict) else None
if not isinstance(identity, dict):
    raise SystemExit(1)
normalize = lambda value: str(value or "").strip().lower().replace("-", "_")
actual = (
    str(identity.get("contract") or ""),
    normalize(identity.get("pricing_provider_id")),
    identity.get("pricing_activate") is True,
    normalize(identity.get("pricing_mode")),
    str(identity.get("pricing_provider_path") or ""),
)
expected = (
    "provider_pricing_runtime_identity_v1",
    normalize(expected_provider_id),
    True,
    normalize(expected_mode),
    expected_path,
)
raise SystemExit(0 if actual == expected else 1)
' "$expected_provider_id" "$expected_mode" "$expected_provider_path" <<<"$payload"
    return $?
  fi

  "$python_bin" - "$port" "$expected_provider_id" "$expected_mode" "$expected_provider_path" <<'PY_COX_RUNTIME_IDENTITY'
import json
import sys
import urllib.request

port, expected_provider_id, expected_mode, expected_path = sys.argv[1:5]
try:
    with urllib.request.urlopen(
        f"http://127.0.0.1:{int(port)}/v1/proxy/status",
        timeout=3,
    ) as response:
        if response.status != 200:
            raise SystemExit(1)
        payload = json.load(response)
except Exception:
    raise SystemExit(1)
identity = payload.get("runtime_identity") if isinstance(payload, dict) else None
if not isinstance(identity, dict):
    raise SystemExit(1)
normalize = lambda value: str(value or "").strip().lower().replace("-", "_")
actual = (
    str(identity.get("contract") or ""),
    normalize(identity.get("pricing_provider_id")),
    identity.get("pricing_activate") is True,
    normalize(identity.get("pricing_mode")),
    str(identity.get("pricing_provider_path") or ""),
)
expected = (
    "provider_pricing_runtime_identity_v1",
    normalize(expected_provider_id),
    True,
    normalize(expected_mode),
    expected_path,
)
raise SystemExit(0 if actual == expected else 1)
PY_COX_RUNTIME_IDENTITY
}


__codexchange_source_env_file() {
  local env_file
  env_file="${COX_ENV_FILE:-$HOME/.config/codexchange/env}"
  [ -f "$env_file" ] || return 0
  set -a
  # shellcheck disable=SC1090
  . "$env_file"
  set +a
}

__codexchange_start_local_proxy() (
  local port profile model provider pricing_provider_id pricing_mode pricing_provider_path
  local install_dir python_bin log_dir log_file state_dir pid_file safe_profile route i
  local start_args=()
  port="$1"; profile="$2"; model="$3"; provider="$4"
  pricing_provider_id="${5:-}"
  pricing_mode="${6:-}"
  pricing_provider_path="${7:-}"

  # Load configured proxy secrets and defaults only inside this isolated
  # startup subprocess. Profile-specific runtime identity below overrides any
  # stale active-profile values from the shared environment file.
  __codexchange_source_env_file
  export NO_PROXY="${NO_PROXY:-127.0.0.1,localhost,::1}"
  export no_proxy="${no_proxy:-$NO_PROXY}"
  export COX_PORT="$port"
  if [ -n "$model" ]; then
    export COX_MODEL="$model"
  else
    unset COX_MODEL
  fi
  export COX_FORCE_MODEL="${COX_FORCE_MODEL:-1}"
  export COX_TOOL_MAX_ROUNDS="${COX_TOOL_MAX_ROUNDS:-6}"
  export COX_COMPACT_POLICY="${COX_COMPACT_POLICY:-adaptive}"
  export COX_AGENT_LIVENESS_GUARD="${COX_AGENT_LIVENESS_GUARD:-1}"
  export COX_AGENT_LIVENESS_JUDGE_ENABLED="${COX_AGENT_LIVENESS_JUDGE_ENABLED:-1}"
  export COX_AGENT_LIVENESS_JUDGE_MODEL="${COX_AGENT_LIVENESS_JUDGE_MODEL:-v4-flash-no-thinking}"
  export COX_CODEX_TOOL_PROTOCOL_INSTRUCTION="${COX_CODEX_TOOL_PROTOCOL_INSTRUCTION:-1}"
  export COX_TOOL_BRIDGE="${COX_TOOL_BRIDGE:-1}"

  route="standard"
  unset COX_REASONING COX_TOOL_OUTPUT_TRIM_MODE COX_TOOL_OUTPUT_IMAGE_PAYLOAD_MAX_ITEM_CHARS
  case "$profile:$provider:$port" in
    *thinking*|*:cox*:*|*:*:8001)
      route="reasoning"
      export COX_REASONING=enabled
      export COX_TOOL_OUTPUT_TRIM_MODE=enabled
      export COX_TOOL_OUTPUT_IMAGE_PAYLOAD_MAX_ITEM_CHARS=12000
      ;;
  esac

  if [ -n "$provider" ] && [ "${provider%deepseek*}" = "$provider" ]; then
    export COX_MODEL_PROVIDER=custom
    case "$provider" in
      *-proxy) export COX_CUSTOM_PROVIDER_NAME="${provider%-proxy}" ;;
      *) export COX_CUSTOM_PROVIDER_NAME="$provider" ;;
    esac
  else
    export COX_MODEL_PROVIDER=deepseek
    unset COX_CUSTOM_PROVIDER_NAME
  fi

  install_dir="${COX_INSTALL_DIR:-$HOME/.local/share/codexchange}"
  python_bin="${install_dir}/.venv/bin/python"
  if [ ! -x "$python_bin" ]; then
    if [ -x "$PWD/.venv/bin/python" ] && [ -d "$PWD/codexchange_proxy" ]; then
      python_bin="$PWD/.venv/bin/python"; install_dir="$PWD"
    else
      python_bin="$(command -v python3 || true)"
    fi
  fi
  if [ -z "$python_bin" ]; then
    echo "CodeXchange: cannot start local proxy; python3 not found" >&2
    return 70
  fi
  export PYTHONPATH="${install_dir}${PYTHONPATH:+:$PYTHONPATH}"
  log_dir="${COX_LOG_DIR:-$HOME/.cache/codexchange}"
  state_dir="${COX_STATE_DIR:-$HOME/.local/state/codexchange}"
  mkdir -p "$log_dir" "$state_dir"
  safe_profile="$(printf '%s' "${profile:-default}" | tr -c 'A-Za-z0-9._-' '_')"
  log_file="${log_dir}/codex-profile-${safe_profile}-proxy-${port}.log"
  pid_file="${state_dir}/profile-${safe_profile}-proxy-${port}.pid"
  start_args=(start "$route" --port "$port" --state-dir "$state_dir" --pid-file "$pid_file" --log-file "$log_file" --owner-profile "${profile:-default}")
  if [ -n "$pricing_provider_id" ]; then
    start_args+=(
      --pricing-provider-id "$pricing_provider_id"
      --pricing-mode "$pricing_mode"
      --pricing-provider-path "$pricing_provider_path"
    )
  fi
  if ! (
    cd "$install_dir" 2>/dev/null || cd "$PWD"
    "$python_bin" -m codexchange_proxy.cli "${start_args[@]}"
  ) >>"$log_file" 2>&1; then
    echo "CodeXchange: lifecycle-aware proxy start failed for profile '${profile}' on 127.0.0.1:${port}" >&2
    echo "CodeXchange: inspect log: ${log_file}" >&2
    echo "CodeXchange: recovery command: cox stop --port ${port}" >&2
    return 70
  fi
  echo "CodeXchange: lifecycle-aware local Responses proxy is available for profile '${profile}' on 127.0.0.1:${port}" >&2
  echo "CodeXchange: proxy log: ${log_file}" >&2
  i=0
  while [ "$i" -lt 8 ]; do
    if __codexchange_proxy_models_ok "$port"; then
      if [ -z "$pricing_provider_id" ] || __codexchange_proxy_runtime_identity_matches \
        "$port" \
        "$pricing_provider_id" \
        "$pricing_mode" \
        "$pricing_provider_path"; then
        return 0
      fi
    fi
    i=$((i + 1)); sleep 0.25
  done
  echo "CodeXchange: local proxy failed readiness check for profile '${profile}' on 127.0.0.1:${port}" >&2
  echo "CodeXchange: inspect log: ${log_file}" >&2
  echo "CodeXchange: recovery command: cox stop --port ${port}" >&2
  return 70
)

__codexchange_profile_runtime_autostart() (
  local profile codex_dir profile_file config_file model provider base_url port
  profile="$(__codexchange_profile_arg "$@")"
  [ -n "$profile" ] || return 0
  if [ "$profile" = "deepseek" ]; then
    printf 'CodeXchange error: profile "deepseek" is deprecated. Use: codex --profile cox\n' >&2
    return 2
  fi
  codex_dir="${CODEX_HOME:-$HOME/.codex}"
  config_file="${CODEX_CONFIG_FILE:-$codex_dir/config.toml}"
  profile_file="$codex_dir/${profile}.config.toml"
  if [ ! -f "$profile_file" ]; then
    printf 'CodeXchange error: unknown Codex profile "%s". No split profile file was found.\n' "$profile" >&2
    printf 'Add/sync it first: cox provider install-profile --name %s --profile-name %s\n' "$profile" "$profile" >&2
    return 2
  fi
  model="$(__codexchange_toml_value "$profile_file" model 2>/dev/null || true)"
  provider="$(__codexchange_toml_value "$profile_file" model_provider 2>/dev/null || true)"
  [ -n "$provider" ] || return 0
  __codexchange_profile_pricing_candidate "$profile_file" || return $?
  base_url="$(__codexchange_provider_base_url "$provider" "$profile_file" "$config_file" 2>/dev/null || true)"
  [ -n "$base_url" ] || return 0
  port="$(__codexchange_local_proxy_port_from_base_url "$base_url" 2>/dev/null || true)"
  [ -n "$port" ] || return 0
  export NO_PROXY="127.0.0.1,localhost,${NO_PROXY:-}"
  export no_proxy="127.0.0.1,localhost,${no_proxy:-}"
  if __codexchange_proxy_models_ok "$port"; then
    if [ "${__codexchange_profile_pricing_explicit:-0}" -ne 1 ]; then
      return 0
    fi
    if __codexchange_proxy_runtime_identity_matches \
      "$port" \
      "${__codexchange_profile_pricing_provider_id:-}" \
      "${__codexchange_profile_pricing_mode:-}" \
      "${__codexchange_profile_pricing_provider_path:-}"; then
      return 0
    fi
    echo "CodeXchange: healthy local proxy runtime pricing identity does not match explicit profile '${profile}'." >&2
    echo "CodeXchange: stop the proxy on 127.0.0.1:${port} and retry so the requested pricing runtime can start." >&2
    echo "CodeXchange: recovery command: cox stop --port ${port}" >&2
    echo "CodeXchange: refusing to enter Codex to avoid silently using the wrong pricing source." >&2
    return 70
  fi
  if __codexchange_port_open "$port"; then
    echo "CodeXchange: 127.0.0.1:${port} is open but /v1/models is not healthy for profile '${profile}'." >&2
    echo "CodeXchange: refusing to enter Codex to avoid stream disconnected failures." >&2
    return 70
  fi
  __codexchange_start_local_proxy \
    "$port" \
    "$profile" \
    "$model" \
    "$provider" \
    "${__codexchange_profile_pricing_provider_id:-}" \
    "${__codexchange_profile_pricing_mode:-}" \
    "${__codexchange_profile_pricing_provider_path:-}"
)

# BEGIN COX UNIFIED INVOCATION-MODE DISPATCH
codex() {
  __codexchange_profile_runtime_autostart "$@" || return $?
  local __codexchange_real_codex
  __codexchange_real_codex="$(__codexchange_resolve_real_codex || true)"
  if [ -n "$__codexchange_real_codex" ]; then
    command "$__codexchange_real_codex" "$@"
    return $?
  fi
  __codexchange_run_npm_codex_fallback "$@"
}
# END COX UNIFIED INVOCATION-MODE DISPATCH

# BEGIN COX EXECUTABLE WRAPPER DISPATCHER
# When this file is sourced, it only defines the codex() shell function.
# When this file is installed as ~/.local/bin/codex and executed directly,
# it must dispatch to the real native Codex binary after running the same
# profile-agnostic local proxy readiness checks.
__codexchange_emit_executable_if_not_self() {
  local candidate self resolved
  candidate="$1"
  [ -n "$candidate" ] || return 1
  [ -x "$candidate" ] || return 1
  self="$(readlink -f "${BASH_SOURCE[0]:-$0}" 2>/dev/null || printf '%s' "${BASH_SOURCE[0]:-$0}")"
  resolved="$(readlink -f "$candidate" 2>/dev/null || printf '%s' "$candidate")"
  [ "$resolved" = "$self" ] && return 1
  case "$resolved" in
    "$HOME/.local/bin/codex") return 1 ;;
  esac
  if [ -r "$resolved" ] \
    && grep -q "# CodeXchange codex wrapper" "$resolved" 2>/dev/null; then
    return 1
  fi
  printf '%s\n' "$resolved"
  return 0
}

__codexchange_emit_npm_codex_bin() {
  local root pkg bin candidate
  for root in \
    "$(npm root -g 2>/dev/null || true)" \
    "$HOME/.npm-global/lib/node_modules" \
    "$HOME/.local/share/npm/lib/node_modules" \
    "$HOME/.nvm/current/lib/node_modules" \
    "/usr/local/lib/node_modules" \
    "/opt/homebrew/lib/node_modules" \
    "/usr/lib/node_modules"; do
    [ -n "$root" ] || continue
    for pkg in "$root/@openai/codex" "$root/codex"; do
      [ -f "$pkg/package.json" ] || continue
      bin="$(node - "$pkg/package.json" <<'PY_COX_NPM_BIN' 2>/dev/null || true
import json, sys
p = sys.argv[1]
try:
    data = json.load(open(p, encoding="utf-8"))
except Exception:
    raise SystemExit(1)
b = data.get("bin")
if isinstance(b, dict):
    b = b.get("codex") or next(iter(b.values()), "")
elif not isinstance(b, str):
    b = ""
if b:
    print(b)
PY_COX_NPM_BIN
)"
      [ -n "$bin" ] || continue
      candidate="$pkg/$bin"
      __codexchange_emit_executable_if_not_self "$candidate" && return 0
    done
  done
  return 1
}

__codexchange_manifest_real_codex() {
  local manifest python_bin candidate
  manifest="${COX_INSTALL_MANIFEST:-$HOME/.config/codexchange/install-manifest.env}"
  [ -r "$manifest" ] || return 1

  python_bin="${COX_INSTALL_DIR:-$HOME/.local/share/codexchange}/.venv/bin/python"
  if [ ! -x "$python_bin" ]; then
    python_bin="$(command -v python3 || command -v python || true)"
  fi
  [ -n "$python_bin" ] || return 1

  candidate="$($python_bin - "$manifest" <<'PY_COX_MANIFEST_REAL_CODEX'
import shlex
import sys
from pathlib import Path

path = Path(sys.argv[1])
try:
    lines = path.read_text(encoding="utf-8").splitlines()
except OSError:
    raise SystemExit(1)

for raw_line in lines:
    line = raw_line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, raw_value = line.split("=", 1)
    if key.strip() != "REAL_CODEX":
        continue
    try:
        parts = shlex.split(raw_value, comments=False, posix=True)
    except ValueError:
        raise SystemExit(1)
    if len(parts) != 1 or not parts[0]:
        raise SystemExit(1)
    print(parts[0])
    raise SystemExit(0)
raise SystemExit(1)
PY_COX_MANIFEST_REAL_CODEX
  )" || return 1
  [ -n "$candidate" ] || return 1
  printf '%s\n' "$candidate"
}

__codexchange_resolve_real_codex() {
  if [ -n "${COX_REAL_CODEX:-}" ]; then
    __codexchange_emit_executable_if_not_self "${COX_REAL_CODEX}" && return 0
    echo "CodeXchange: COX_REAL_CODEX is set but not executable or points to wrapper: ${COX_REAL_CODEX}" >&2
  fi

  local candidate
  candidate="$(__codexchange_manifest_real_codex || true)"
  if [ -n "$candidate" ]; then
    __codexchange_emit_executable_if_not_self "$candidate" && return 0
  fi

  while IFS= read -r candidate; do
    __codexchange_emit_executable_if_not_self "$candidate" && return 0
  done < <(type -P -a codex 2>/dev/null | awk '!seen[$0]++')

  for candidate in \
    "$HOME/.local/bin/codex.real" \
    "$HOME/.local/bin/codex-native" \
    "$HOME/.npm-global/bin/codex" \
    "$HOME/.local/share/npm/bin/codex" \
    "$HOME/.nvm/current/bin/codex" \
    "/usr/local/bin/codex" \
    "/opt/homebrew/bin/codex" \
    "/usr/bin/codex"; do
    __codexchange_emit_executable_if_not_self "$candidate" && return 0
  done

  __codexchange_emit_npm_codex_bin && return 0
  return 1
}

__codexchange_run_npm_codex_fallback() {
  if command -v npm >/dev/null 2>&1 \
    && npm exec --offline --package @openai/codex -- codex --version >/dev/null 2>&1; then
    command npm exec --offline --package @openai/codex -- codex "$@"
    return $?
  fi
  if command -v npx >/dev/null 2>&1; then
    echo "CodeXchange: native Codex binary not found; falling back to npx @openai/codex" >&2
    command npx --yes @openai/codex "$@"
    return $?
  fi
  echo "CodeXchange: cannot find native Codex binary." >&2
  echo "CodeXchange: set COX_REAL_CODEX=/path/to/native/codex, or install @openai/codex globally." >&2
  return 127
}

__codexchange_exec_npm_codex_fallback() {
  if command -v npm >/dev/null 2>&1; then
    npm exec --offline --package @openai/codex -- codex --version >/dev/null 2>&1 \
      && exec npm exec --offline --package @openai/codex -- codex "$@"
  fi
  if command -v npx >/dev/null 2>&1; then
    echo "CodeXchange: native Codex binary not found; falling back to npx @openai/codex" >&2
    exec npx --yes @openai/codex "$@"
  fi
  echo "CodeXchange: cannot find native Codex binary." >&2
  echo "CodeXchange: set COX_REAL_CODEX=/path/to/native/codex, or install @openai/codex globally." >&2
  return 127
}

__codexchange_executable_wrapper_main() {
  __codexchange_profile_runtime_autostart "$@" || exit $?
  local __codexchange_real_codex
  __codexchange_real_codex="$(__codexchange_resolve_real_codex || true)"
  if [ -n "$__codexchange_real_codex" ]; then
    exec "$__codexchange_real_codex" "$@"
  fi
  __codexchange_exec_npm_codex_fallback "$@"
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
  __codexchange_executable_wrapper_main "$@"
fi
# END COX EXECUTABLE WRAPPER DISPATCHER
