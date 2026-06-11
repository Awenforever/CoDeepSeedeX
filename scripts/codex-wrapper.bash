#!/usr/bin/env bash
# Auto-start CodeXchange when using CodeXchange Codex profiles.
#
# Add this function to ~/.bashrc after ~/bin is on PATH.
#
# Behavior:
# - codex --profile cox starts the thinking proxy on port 8001.
# - codex --profile <custom-provider-id> activates that configured provider and starts the thinking proxy.
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
      --profile)
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
    $0 ~ "^[[:space:]]*" k "[[:space:]]*=" {
      line=$0
      sub(/^[^=]*=/, "", line)
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", line)
      if (line ~ /^"/) { sub(/^"/, "", line); sub(/".*$/, "", line) }
      print line
      found=1
      exit
    }
    END { if (!found) exit 1 }
  ' "$file"
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

__codexchange_source_env_file() {
  local env_file
  env_file="${COX_ENV_FILE:-$HOME/.config/codexchange/env}"
  [ -f "$env_file" ] || return 0
  set -a
  # shellcheck disable=SC1090
  . "$env_file"
  set +a
}

__codexchange_start_local_proxy() {
  local port profile model provider install_dir python_bin log_dir log_file i
  port="$1"; profile="$2"; model="$3"; provider="$4"
  __codexchange_source_env_file
  export NO_PROXY="${NO_PROXY:-127.0.0.1,localhost,::1}"
  export no_proxy="${no_proxy:-$NO_PROXY}"
  export COX_PORT="$port"
  [ -n "$model" ] && export COX_MODEL="$model" && export COX_MODEL="$model"
  export COX_FORCE_MODEL="${COX_FORCE_MODEL:-1}"
  export COX_TOOL_MAX_ROUNDS="${COX_TOOL_MAX_ROUNDS:-6}"
  export COX_COMPACT_POLICY="${COX_COMPACT_POLICY:-adaptive}"
  export COX_AGENT_LIVENESS_GUARD="${COX_AGENT_LIVENESS_GUARD:-1}"
  export COX_AGENT_LIVENESS_JUDGE_ENABLED="${COX_AGENT_LIVENESS_JUDGE_ENABLED:-1}"
  export COX_AGENT_LIVENESS_JUDGE_MODEL="${COX_AGENT_LIVENESS_JUDGE_MODEL:-v4-flash-no-thinking}"
  export COX_CODEX_TOOL_PROTOCOL_INSTRUCTION="${COX_CODEX_TOOL_PROTOCOL_INSTRUCTION:-1}"
  export COX_TOOL_BRIDGE="${COX_TOOL_BRIDGE:-1}"
  case "$profile:$provider:$port" in
    *thinking*|*:cox*:*|*:*:8001)
      export COX_REASONING=enabled
      export COX_TOOL_OUTPUT_TRIM_MODE="${COX_TOOL_OUTPUT_TRIM_MODE:-enabled}"
      export COX_TOOL_OUTPUT_IMAGE_PAYLOAD_MAX_ITEM_CHARS="${COX_TOOL_OUTPUT_IMAGE_PAYLOAD_MAX_ITEM_CHARS:-12000}"
      ;;
  esac
  if [ -n "$provider" ] && [ "${provider%deepseek*}" = "$provider" ]; then
    export COX_MODEL_PROVIDER="${COX_MODEL_PROVIDER:-custom}"
    case "$provider" in *-proxy) export COX_CUSTOM_PROVIDER_NAME="${COX_CUSTOM_PROVIDER_NAME:-${provider%-proxy}}" ;; esac
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
  mkdir -p "$log_dir"
  log_file="${log_dir}/codex-profile-${profile:-default}-proxy-${port}.log"
  (
    cd "$install_dir" 2>/dev/null || cd "$PWD"
    exec "$python_bin" -m uvicorn codexchange_proxy.app:app --host 127.0.0.1 --port "$port"
  ) >>"$log_file" 2>&1 &
  echo "CodeXchange: starting local Responses proxy for profile '${profile}' on 127.0.0.1:${port}" >&2
  echo "CodeXchange: proxy log: ${log_file}" >&2
  i=0
  while [ "$i" -lt 40 ]; do
    if __codexchange_proxy_models_ok "$port"; then return 0; fi
    i=$((i + 1)); sleep 0.25
  done
  echo "CodeXchange: local proxy failed readiness check for profile '${profile}' on 127.0.0.1:${port}" >&2
  echo "CodeXchange: inspect log: ${log_file}" >&2
  return 70
}

__codexchange_profile_runtime_autostart() {
  local profile codex_dir profile_file config_file model provider base_url port
  profile="$(__codexchange_profile_arg "$@")"
  [ -n "$profile" ] || return 0
  codex_dir="${CODEX_HOME:-$HOME/.codex}"
  config_file="${CODEX_CONFIG_FILE:-$codex_dir/config.toml}"
  profile_file="$codex_dir/${profile}.config.toml"
  [ -f "$profile_file" ] || return 0
  model="$(__codexchange_toml_value "$profile_file" model 2>/dev/null || true)"
  provider="$(__codexchange_toml_value "$profile_file" model_provider 2>/dev/null || true)"
  [ -n "$provider" ] || return 0
  base_url="$(__codexchange_provider_base_url "$provider" "$profile_file" "$config_file" 2>/dev/null || true)"
  [ -n "$base_url" ] || return 0
  port="$(__codexchange_local_proxy_port_from_base_url "$base_url" 2>/dev/null || true)"
  [ -n "$port" ] || return 0
  if __codexchange_proxy_models_ok "$port"; then return 0; fi
  if __codexchange_port_open "$port"; then
    echo "CodeXchange: 127.0.0.1:${port} is open but /v1/models is not healthy for profile '${profile}'." >&2
    echo "CodeXchange: refusing to enter Codex to avoid stream disconnected failures." >&2
    return 70
  fi
  __codexchange_start_local_proxy "$port" "$profile" "$model" "$provider"
}
# END COX PROFILE-AGNOSTIC RUNTIME AUTOSTART

codex() {
  __codexchange_profile_runtime_autostart "$@" || return $?
  local selected_profile=""
  local arg
  local next_is_profile=0

  for arg in "$@"; do
    if [ "$next_is_profile" = "1" ]; then
      selected_profile="$arg"
      next_is_profile=0
      continue
    fi

    case "$arg" in
      --profile|-p)
        next_is_profile=1
        ;;
      --profile=*)
        selected_profile="${arg#--profile=}"
        ;;
    esac
  done

  export NO_PROXY="127.0.0.1,localhost,${NO_PROXY:-}"
  export no_proxy="127.0.0.1,localhost,${no_proxy:-}"

  case "$selected_profile" in
    deepseek)
      printf 'CodeXchange error: profile "deepseek" is deprecated. Use: codex --profile cox\n' >&2
      return 2
      ;;
    cox)
      source "$HOME/.config/codexchange/env"
      cox start thinking
      COX_MODEL_API_KEY="$COX_MODEL_API_KEY" command codex "$@"
      ;;
    "")
      command codex "$@"
      ;;
    *)
      source "$HOME/.config/codexchange/env"
      if cox config custom-provider use --name "$selected_profile" --no-profile-sync >/dev/null 2>&1; then
        if ! cox provider install-profile --name "$selected_profile" --profile-name "$selected_profile" >/dev/null 2>&1; then
          printf 'CodeXchange error: failed to sync custom provider profile "%s".\n' "$selected_profile" >&2
          return 2
        fi
        cox start thinking
        COX_MODEL_API_KEY="$COX_MODEL_API_KEY" command codex "$@"
      elif [ -f "$HOME/.codex/${selected_profile}.config.toml" ]; then
        command codex "$@"
      else
        printf 'CodeXchange error: unknown Codex profile "%s". No custom provider or split profile file was found.\n' "$selected_profile" >&2
        printf 'Add/sync it first: cox provider install-profile --name %s --profile-name %s\n' "$selected_profile" "$selected_profile" >&2
        return 2
      fi
      ;;
  esac
}

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

__codexchange_resolve_real_codex() {
  if [ -n "${COX_REAL_CODEX:-}" ]; then
    __codexchange_emit_executable_if_not_self "${COX_REAL_CODEX}" && return 0
    echo "CodeXchange: COX_REAL_CODEX is set but not executable or points to wrapper: ${COX_REAL_CODEX}" >&2
  fi

  local candidate
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
