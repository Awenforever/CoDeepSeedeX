# Auto-start DeepSeek Responses Proxy when using CoDeepSeedeX Codex profiles.
#
# Add this function to ~/.bashrc after ~/bin is on PATH.
#
# Behavior:
# - codex --profile deepseek-thinking starts the thinking proxy on port 8001.
# - codex --profile <custom-provider-id> activates that configured provider and starts the thinking proxy.
# - codex --profile deepseek is deprecated and fails closed.

# BEGIN CODEEPSEEDEX PROFILE-AGNOSTIC RUNTIME AUTOSTART
# Contract: codex --profile <name> is a one-command entrypoint for every
# CoDeepSeedeX-managed profile whose provider base_url points at a local
# Responses proxy. The wrapper resolves the profile, starts the required local
# proxy if it is absent, verifies /v1/models, then enters native Codex.
__codeepseedex_profile_arg() {
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

__codeepseedex_toml_value() {
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

__codeepseedex_provider_base_url() {
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

__codeepseedex_local_proxy_port_from_base_url() {
  local base_url
  base_url="$1"
  case "$base_url" in
    http://127.0.0.1:*|http://localhost:*|http://[::1]:*)
      printf '%s\n' "$base_url" | sed -E 's#^http://(\[::1\]|127\.0\.0\.1|localhost):([0-9]+).*#\2#'
      ;;
    *) return 1 ;;
  esac
}

__codeepseedex_port_open() {
  local port
  port="$1"
  python3 - "$port" <<'PY_CODEEPSEEDEX_PORT_OPEN' >/dev/null 2>&1
import socket, sys
port = int(sys.argv[1])
try:
    with socket.create_connection(("127.0.0.1", port), timeout=0.35):
        pass
except OSError:
    raise SystemExit(1)
PY_CODEEPSEEDEX_PORT_OPEN
}

__codeepseedex_proxy_models_ok() {
  local port
  port="$1"
  if command -v curl >/dev/null 2>&1; then
    curl -fsS -m 3 "http://127.0.0.1:${port}/v1/models" >/dev/null 2>&1
    return $?
  fi
  python3 - "$port" <<'PY_CODEEPSEEDEX_MODELS_OK' >/dev/null 2>&1
import sys, urllib.request
port = int(sys.argv[1])
with urllib.request.urlopen(f"http://127.0.0.1:{port}/v1/models", timeout=3) as r:
    if r.status != 200:
        raise SystemExit(1)
PY_CODEEPSEEDEX_MODELS_OK
}

__codeepseedex_source_env_file() {
  local env_file
  env_file="${DEEPSEEK_PROXY_ENV_FILE:-$HOME/.config/deepseek-responses-proxy/env}"
  [ -f "$env_file" ] || return 0
  set -a
  # shellcheck disable=SC1090
  . "$env_file"
  set +a
}

__codeepseedex_start_local_proxy() {
  local port profile model provider install_dir python_bin log_dir log_file i
  port="$1"; profile="$2"; model="$3"; provider="$4"
  __codeepseedex_source_env_file
  export NO_PROXY="${NO_PROXY:-127.0.0.1,localhost,::1}"
  export no_proxy="${no_proxy:-$NO_PROXY}"
  export DEEPSEEK_PROXY_PORT="$port"
  [ -n "$model" ] && export DEEPSEEK_PROXY_MODEL="$model" && export DEEPSEEK_MODEL="$model"
  export DEEPSEEK_PROXY_FORCE_MODEL="${DEEPSEEK_PROXY_FORCE_MODEL:-1}"
  export DEEPSEEK_PROXY_TOOL_MAX_ROUNDS="${DEEPSEEK_PROXY_TOOL_MAX_ROUNDS:-6}"
  export DEEPSEEK_PROXY_COMPACT_POLICY="${DEEPSEEK_PROXY_COMPACT_POLICY:-adaptive}"
  export DEEPSEEK_PROXY_AGENT_LIVENESS_GUARD="${DEEPSEEK_PROXY_AGENT_LIVENESS_GUARD:-1}"
  export DEEPSEEK_PROXY_AGENT_LIVENESS_JUDGE_ENABLED="${DEEPSEEK_PROXY_AGENT_LIVENESS_JUDGE_ENABLED:-1}"
  export DEEPSEEK_PROXY_AGENT_LIVENESS_JUDGE_MODEL="${DEEPSEEK_PROXY_AGENT_LIVENESS_JUDGE_MODEL:-v4-flash-no-thinking}"
  export DEEPSEEK_PROXY_CODEX_TOOL_PROTOCOL_INSTRUCTION="${DEEPSEEK_PROXY_CODEX_TOOL_PROTOCOL_INSTRUCTION:-1}"
  export DEEPSEEK_PROXY_TOOL_BRIDGE="${DEEPSEEK_PROXY_TOOL_BRIDGE:-1}"
  case "$profile:$provider:$port" in
    *thinking*|*:deepseek-thinking*:*|*:*:8001)
      export DEEPSEEK_THINKING=enabled
      export DEEPSEEK_PROXY_TOOL_OUTPUT_TRIM_MODE="${DEEPSEEK_PROXY_TOOL_OUTPUT_TRIM_MODE:-enabled}"
      export DEEPSEEK_PROXY_TOOL_OUTPUT_IMAGE_PAYLOAD_MAX_ITEM_CHARS="${DEEPSEEK_PROXY_TOOL_OUTPUT_IMAGE_PAYLOAD_MAX_ITEM_CHARS:-12000}"
      ;;
  esac
  if [ -n "$provider" ] && [ "${provider%deepseek*}" = "$provider" ]; then
    export DEEPSEEK_PROXY_MODEL_PROVIDER="${DEEPSEEK_PROXY_MODEL_PROVIDER:-custom}"
    case "$provider" in *-proxy) export DEEPSEEK_PROXY_CUSTOM_PROVIDER_NAME="${DEEPSEEK_PROXY_CUSTOM_PROVIDER_NAME:-${provider%-proxy}}" ;; esac
  fi
  install_dir="${DEEPSEEK_PROXY_INSTALL_DIR:-$HOME/.local/share/deepseek-responses-proxy}"
  python_bin="${install_dir}/.venv/bin/python"
  if [ ! -x "$python_bin" ]; then
    if [ -x "$PWD/.venv/bin/python" ] && [ -d "$PWD/deepseek_responses_proxy" ]; then
      python_bin="$PWD/.venv/bin/python"; install_dir="$PWD"
    else
      python_bin="$(command -v python3 || true)"
    fi
  fi
  if [ -z "$python_bin" ]; then
    echo "CoDeepSeedeX: cannot start local proxy; python3 not found" >&2
    return 70
  fi
  export PYTHONPATH="${install_dir}${PYTHONPATH:+:$PYTHONPATH}"
  log_dir="${DEEPSEEK_PROXY_LOG_DIR:-$HOME/.cache/deepseek-responses-proxy}"
  mkdir -p "$log_dir"
  log_file="${log_dir}/codex-profile-${profile:-default}-proxy-${port}.log"
  (
    cd "$install_dir" 2>/dev/null || cd "$PWD"
    exec "$python_bin" -m uvicorn deepseek_responses_proxy.app:app --host 127.0.0.1 --port "$port"
  ) >>"$log_file" 2>&1 &
  echo "CoDeepSeedeX: starting local Responses proxy for profile '${profile}' on 127.0.0.1:${port}" >&2
  echo "CoDeepSeedeX: proxy log: ${log_file}" >&2
  i=0
  while [ "$i" -lt 40 ]; do
    if __codeepseedex_proxy_models_ok "$port"; then return 0; fi
    i=$((i + 1)); sleep 0.25
  done
  echo "CoDeepSeedeX: local proxy failed readiness check for profile '${profile}' on 127.0.0.1:${port}" >&2
  echo "CoDeepSeedeX: inspect log: ${log_file}" >&2
  return 70
}

__codeepseedex_profile_runtime_autostart() {
  local profile codex_dir profile_file config_file model provider base_url port
  profile="$(__codeepseedex_profile_arg "$@")"
  [ -n "$profile" ] || return 0
  codex_dir="${CODEX_HOME:-$HOME/.codex}"
  config_file="${CODEX_CONFIG_FILE:-$codex_dir/config.toml}"
  profile_file="$codex_dir/${profile}.config.toml"
  [ -f "$profile_file" ] || return 0
  model="$(__codeepseedex_toml_value "$profile_file" model 2>/dev/null || true)"
  provider="$(__codeepseedex_toml_value "$profile_file" model_provider 2>/dev/null || true)"
  [ -n "$provider" ] || return 0
  base_url="$(__codeepseedex_provider_base_url "$provider" "$profile_file" "$config_file" 2>/dev/null || true)"
  [ -n "$base_url" ] || return 0
  port="$(__codeepseedex_local_proxy_port_from_base_url "$base_url" 2>/dev/null || true)"
  [ -n "$port" ] || return 0
  if __codeepseedex_proxy_models_ok "$port"; then return 0; fi
  if __codeepseedex_port_open "$port"; then
    echo "CoDeepSeedeX: 127.0.0.1:${port} is open but /v1/models is not healthy for profile '${profile}'." >&2
    echo "CoDeepSeedeX: refusing to enter Codex to avoid stream disconnected failures." >&2
    return 70
  fi
  __codeepseedex_start_local_proxy "$port" "$profile" "$model" "$provider"
}
# END CODEEPSEEDEX PROFILE-AGNOSTIC RUNTIME AUTOSTART

codex() {
  __codeepseedex_profile_runtime_autostart "$@" || return $?
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
      printf 'CoDeepSeedeX error: profile "deepseek" is deprecated. Use: codex --profile deepseek-thinking\n' >&2
      return 2
      ;;
    deepseek-thinking)
      source "$HOME/.config/deepseek-responses-proxy/env"
      dsproxy start thinking
      DEEPSEEK_API_KEY="$DEEPSEEK_API_KEY" command codex "$@"
      ;;
    "")
      command codex "$@"
      ;;
    *)
      source "$HOME/.config/deepseek-responses-proxy/env"
      if dsproxy config custom-provider use --name "$selected_profile" --no-profile-sync >/dev/null 2>&1; then
        if ! dsproxy provider install-profile --name "$selected_profile" --profile-name "$selected_profile" >/dev/null 2>&1; then
          printf 'CoDeepSeedeX error: failed to sync custom provider profile "%s".\n' "$selected_profile" >&2
          return 2
        fi
        dsproxy start thinking
        DEEPSEEK_API_KEY="$DEEPSEEK_API_KEY" command codex "$@"
      elif [ -f "$HOME/.codex/${selected_profile}.config.toml" ]; then
        command codex "$@"
      else
        printf 'CoDeepSeedeX error: unknown Codex profile "%s". No custom provider or split profile file was found.\n' "$selected_profile" >&2
        printf 'Add/sync it first: dsproxy provider install-profile --name %s --profile-name %s\n' "$selected_profile" "$selected_profile" >&2
        return 2
      fi
      ;;
  esac
}

# BEGIN CODEEPSEEDEX EXECUTABLE WRAPPER DISPATCHER
# When this file is sourced, it only defines the codex() shell function.
# When this file is installed as ~/.local/bin/codex and executed directly,
# it must dispatch to the real native Codex binary after running the same
# profile-agnostic local proxy readiness checks.
__codeepseedex_emit_executable_if_not_self() {
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

__codeepseedex_emit_npm_codex_bin() {
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
      bin="$(node - "$pkg/package.json" <<'PY_CODEEPSEEDEX_NPM_BIN' 2>/dev/null || true
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
PY_CODEEPSEEDEX_NPM_BIN
)"
      [ -n "$bin" ] || continue
      candidate="$pkg/$bin"
      __codeepseedex_emit_executable_if_not_self "$candidate" && return 0
    done
  done
  return 1
}

__codeepseedex_resolve_real_codex() {
  if [ -n "${CODEEPSEEDEX_REAL_CODEX:-}" ]; then
    __codeepseedex_emit_executable_if_not_self "${CODEEPSEEDEX_REAL_CODEX}" && return 0
    echo "CoDeepSeedeX: CODEEPSEEDEX_REAL_CODEX is set but not executable or points to wrapper: ${CODEEPSEEDEX_REAL_CODEX}" >&2
  fi

  local candidate
  while IFS= read -r candidate; do
    __codeepseedex_emit_executable_if_not_self "$candidate" && return 0
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
    __codeepseedex_emit_executable_if_not_self "$candidate" && return 0
  done

  __codeepseedex_emit_npm_codex_bin && return 0
  return 1
}

__codeepseedex_exec_npm_codex_fallback() {
  if command -v npm >/dev/null 2>&1; then
    npm exec --offline --package @openai/codex -- codex --version >/dev/null 2>&1 \
      && exec npm exec --offline --package @openai/codex -- codex "$@"
  fi
  if command -v npx >/dev/null 2>&1; then
    echo "CoDeepSeedeX: native Codex binary not found; falling back to npx @openai/codex" >&2
    exec npx --yes @openai/codex "$@"
  fi
  echo "CoDeepSeedeX: cannot find native Codex binary." >&2
  echo "CoDeepSeedeX: set CODEEPSEEDEX_REAL_CODEX=/path/to/native/codex, or install @openai/codex globally." >&2
  return 127
}

__codeepseedex_executable_wrapper_main() {
  __codeepseedex_profile_runtime_autostart "$@" || exit $?
  local __codeepseedex_real_codex
  __codeepseedex_real_codex="$(__codeepseedex_resolve_real_codex || true)"
  if [ -n "$__codeepseedex_real_codex" ]; then
    exec "$__codeepseedex_real_codex" "$@"
  fi
  __codeepseedex_exec_npm_codex_fallback "$@"
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
  __codeepseedex_executable_wrapper_main "$@"
fi
# END CODEEPSEEDEX EXECUTABLE WRAPPER DISPATCHER
