#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="${DEEPSEEK_PROXY_INSTALL_DIR:-$HOME/.local/share/deepseek-responses-proxy}"
REPO_URL="${DEEPSEEK_PROXY_REPO_URL:-https://github.com/Awenforever/CoDeepSeedeX.git}"
BIN_DIR="${DEEPSEEK_PROXY_BIN_DIR:-$HOME/.local/bin}"
CONFIG_DIR="${DEEPSEEK_PROXY_CONFIG_DIR:-$HOME/.config/deepseek-responses-proxy}"
ENV_FILE="${DEEPSEEK_PROXY_ENV_FILE:-$CONFIG_DIR/env}"
MANIFEST_FILE="${DEEPSEEK_PROXY_MANIFEST_FILE:-$CONFIG_DIR/install-manifest.env}"
INSTALL_LOG="${DEEPSEEK_PROXY_INSTALL_LOG:-/tmp/codeepseedex-install-$(date +%Y%m%d_%H%M%S).log}"

DRY_RUN=0
NON_INTERACTIVE=0
INSTALL_CODEX_PROFILE=1
INSTALL_CODEX_WRAPPER=1
UNINSTALL=0
REMOVE_FILES=0

logo() {
  cat <<'LOGO'
   ____      ____                 ____              _      __  __
  / ___|___ |  _ \  ___  ___ _ __/ ___|  ___  ___  __| | ___ \ \/ /
 | |   / _ \| | | |/ _ \/ _ \ '_ \___ \ / _ \/ _ \/ _` |/ _ \ \  /
 | |__| (_) | |_| |  __/  __/ |_) |__) |  __/  __/ (_| |  __/ /  \
  \____\___/|____/ \___|\___| .__/____/ \___|\___|\__,_|\___|/_/\_\
                             |_|

  CoDeepSeedeX
  Codex × DeepSeek local Responses proxy
LOGO
}

usage() {
  cat <<'USAGE'
Usage: scripts/install.sh [options]

Options:
  --dry-run              Print actions without applying changes
  --non-interactive      Do not prompt; use environment/default values
  --install-dir DIR      Installation directory
  --repo-url URL         Git repository URL
  --bin-dir DIR          Directory for dsproxy and optional codex wrapper
  --config-dir DIR       Config directory
  --env-file FILE        Env file path
  --no-codex-profile     Skip Codex profile installation
  --no-codex-wrapper     Skip safe codex wrapper installation
  --uninstall            Remove profiles and wrappers installed by CoDeepSeedeX
  --remove-files         With --uninstall, also remove install dir and env files
  -h, -H, --help         Show help

The API key is entered with hidden input and written to a chmod 600 env file.
This is not cryptographic encryption.
USAGE
}

step() {
  printf '\n\033[1;36m%s\033[0m\n' "$1"
}

ok() {
  printf '  \033[1;32m✓\033[0m %s\n' "$1"
}

warn() {
  printf '  \033[1;33m!\033[0m %s\n' "$1"
}

divider() {
  printf '\n\033[1;36m%s\033[0m\n' '────────────────────────────────────────────────────────────'
}

section_title() {
  printf '\n\033[1;36m%s\033[0m\n' "$1"
}

sub_title() {
  printf '\n\033[1;35m%s\033[0m\n' "$1"
}

run_quiet() {
  local label="$1"
  shift
  printf '  ... %s\n' "$label"

  if [ "$DRY_RUN" = "1" ]; then
    printf '+ %s\n' "$*" >> "$INSTALL_LOG"
    ok "$label"
    return 0
  fi

  if "$@" >> "$INSTALL_LOG" 2>&1; then
    ok "$label"
  else
    warn "$label failed. See log: $INSTALL_LOG"
    return 1
  fi
}

read_from_tty() {
  local prompt="$1"
  local default_value="${2:-}"
  local value=""

  if [ "$NON_INTERACTIVE" = "1" ] || [ ! -r /dev/tty ]; then
    printf '%s\n' "$default_value"
    return 0
  fi

  if [ -n "$default_value" ]; then
    printf "%s [%s]: " "$prompt" "$default_value" > /dev/tty
  else
    printf "%s: " "$prompt" > /dev/tty
  fi

  IFS= read -r value < /dev/tty || true
  if [ -z "$value" ]; then
    value="$default_value"
  fi
  printf '%s\n' "$value"
}

read_yes_no() {
  local prompt="$1"
  local default_value="${2:-Y}"
  local value=""

  if [ "$NON_INTERACTIVE" = "1" ] || [ ! -r /dev/tty ]; then
    printf '%s\n' "$default_value"
    return 0
  fi

  printf "%s " "$prompt" > /dev/tty
  IFS= read -r value < /dev/tty || true
  if [ -z "$value" ]; then
    value="$default_value"
  fi
  printf '%s\n' "$value"
}

read_secret_from_tty() {
  local prompt="$1"
  local default_value="${2:-}"
  local value=""

  if [ "$NON_INTERACTIVE" = "1" ] || [ ! -r /dev/tty ]; then
    printf '%s\n' "$default_value"
    return 0
  fi

  if [ -n "$default_value" ]; then
    printf "%s [hidden, press Enter to keep existing]: " "$prompt" > /dev/tty
  else
    printf "%s [hidden]: " "$prompt" > /dev/tty
  fi

  stty -echo < /dev/tty 2>/dev/null || true
  IFS= read -r value < /dev/tty || true
  stty echo < /dev/tty 2>/dev/null || true
  printf "\n" > /dev/tty

  if [ -z "$value" ]; then
    value="$default_value"
  fi
  printf '%s\n' "$value"
}

find_real_codex() {
  local wrapper_path="$1"
  local candidate=""

  if [ -n "${CODEEPSEEDEX_REAL_CODEX:-}" ] && [ -x "$CODEEPSEEDEX_REAL_CODEX" ]; then
    printf '%s\n' "$CODEEPSEEDEX_REAL_CODEX"
    return 0
  fi

  while IFS= read -r candidate; do
    if [ "$candidate" != "$wrapper_path" ] && [ -x "$candidate" ]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done < <(type -P -a codex 2>/dev/null || true)

  return 1
}

write_env_file() {
  local stable_port="$1"
  local thinking_port="$2"
  local api_key="$3"

  if [ "$DRY_RUN" = "1" ]; then
    printf '+ mkdir -p %q\n' "$(dirname "$ENV_FILE")" >> "$INSTALL_LOG"
    printf '+ write %q with chmod 600\n' "$ENV_FILE" >> "$INSTALL_LOG"
    ok "Local env file written"
    return 0
  fi

  mkdir -p "$(dirname "$ENV_FILE")"

  {
    printf '# deepseek-responses-proxy local environment\n'
    printf '# Generated by scripts/install.sh\n'
    printf 'export DEEPSEEK_API_KEY=%q\n' "$api_key"
    printf 'export DEEPSEEK_PROXY_PORT=%q\n' "$stable_port"
    printf 'export DEEPSEEK_PROXY_THINKING_PORT=%q\n' "$thinking_port"
    printf 'export DEEPSEEK_PROXY_MODEL=%q\n' "deepseek-v4-pro"
    printf 'export DEEPSEEK_REASONING_EFFORT=%q\n' "xhigh"
    printf 'export DEEPSEEK_PROXY_FORCE_MODEL=%q\n' "1"
    printf 'export DEEPSEEK_PROXY_TOOL_MAX_ROUNDS=%q\n' "6"
    printf 'export DEEPSEEK_PROXY_COMPACT_POLICY=%q\n' "adaptive"
    printf 'export DEEPSEEK_PROXY_AGENT_LIVENESS_GUARD=%q\n' "1"
    printf 'export DEEPSEEK_PROXY_AGENT_LIVENESS_JUDGE_ENABLED=%q\n' "1"
    printf 'export DEEPSEEK_PROXY_AGENT_LIVENESS_JUDGE_MODEL=%q\n' "v4-flash-no-thinking"
    printf 'export DEEPSEEK_PROXY_CODEX_TOOL_PROTOCOL_INSTRUCTION=%q\n' "1"
  } > "$ENV_FILE"

  chmod 600 "$ENV_FILE"
  ok "Local env file written"
}

write_dsproxy_wrapper() {
  if [ "$DRY_RUN" = "1" ]; then
    printf '+ mkdir -p %q\n' "$BIN_DIR" >> "$INSTALL_LOG"
    printf '+ write %q\n' "$BIN_DIR/dsproxy" >> "$INSTALL_LOG"
    ok "dsproxy command installed"
    return 0
  fi

  mkdir -p "$BIN_DIR"

  cat > "$BIN_DIR/dsproxy" <<EOF
#!/usr/bin/env bash
set -euo pipefail
ENV_FILE="\${DEEPSEEK_PROXY_ENV_FILE:-$ENV_FILE}"
if [ -f "\$ENV_FILE" ]; then
  source "\$ENV_FILE"
fi
exec "$INSTALL_DIR/.venv/bin/dsproxy" "\$@"
EOF

  chmod +x "$BIN_DIR/dsproxy"
  ok "dsproxy command installed"
}

write_codex_wrapper() {
  local stable_port="$1"
  local thinking_port="$2"
  local wrapper_path="$BIN_DIR/codex"
  local real_codex=""
  local backup_path=""

  if [ "$INSTALL_CODEX_WRAPPER" != "1" ]; then
    ok "Codex wrapper skipped"
    return 0
  fi

  real_codex="$(find_real_codex "$wrapper_path" || true)"

  if [ -e "$wrapper_path" ] && ! grep -q "CoDeepSeedeX codex wrapper" "$wrapper_path" 2>/dev/null; then
    backup_path="$wrapper_path.codeepseedex.bak.$(date +%Y%m%d_%H%M%S)"
    if [ "$DRY_RUN" = "1" ]; then
      printf '+ backup existing %q to %q\n' "$wrapper_path" "$backup_path" >> "$INSTALL_LOG"
    else
      mv "$wrapper_path" "$backup_path"
      if [ -z "$real_codex" ]; then
        real_codex="$backup_path"
      fi
    fi
  fi

  if [ -z "$real_codex" ]; then
    warn "real codex command not found; Codex wrapper skipped"
    return 0
  fi

  if [ "$DRY_RUN" = "1" ]; then
    printf '+ write %q\n' "$wrapper_path" >> "$INSTALL_LOG"
    ok "Codex wrapper installed"
    return 0
  fi

  mkdir -p "$BIN_DIR"

  cat > "$wrapper_path" <<EOF
#!/usr/bin/env bash
# CoDeepSeedeX codex wrapper
set -euo pipefail

REAL_CODEX="$real_codex"
DSPROXY="$INSTALL_DIR/.venv/bin/dsproxy"
ENV_FILE="\${DEEPSEEK_PROXY_ENV_FILE:-$ENV_FILE}"

if [ -f "\$ENV_FILE" ]; then
  source "\$ENV_FILE"
fi

profile=""
prev=""
for arg in "\$@"; do
  if [ "\$prev" = "--profile" ] || [ "\$prev" = "-p" ]; then
    profile="\$arg"
    break
  fi
  case "\$arg" in
    --profile=*) profile="\${arg#--profile=}"; break ;;
    -p*) profile="\${arg#-p}"; break ;;
  esac
  prev="\$arg"
done

case "\$profile" in
  deepseek)
    "\$DSPROXY" start >/dev/null
    ;;
  deepseek-thinking)
    "\$DSPROXY" start --thinking >/dev/null
    ;;
esac

exec "\$REAL_CODEX" "\$@"
EOF

  chmod +x "$wrapper_path"

  cat > "$MANIFEST_FILE" <<EOF
CODEX_WRAPPER_PATH="$wrapper_path"
CODEX_WRAPPER_BACKUP="$backup_path"
REAL_CODEX="$real_codex"
ENV_FILE="$ENV_FILE"
INSTALL_DIR="$INSTALL_DIR"
BIN_DIR="$BIN_DIR"
STABLE_PORT="$stable_port"
THINKING_PORT="$thinking_port"
EOF

  chmod 600 "$MANIFEST_FILE" 2>/dev/null || true
  ok "Codex wrapper installed"
}

uninstall() {
  logo
  step "Uninstalling CoDeepSeedeX integration"

  local wrapper_path="$BIN_DIR/codex"
  local backup_path=""

  if [ -f "$MANIFEST_FILE" ]; then
    # shellcheck disable=SC1090
    source "$MANIFEST_FILE" || true
    wrapper_path="${CODEX_WRAPPER_PATH:-$wrapper_path}"
    backup_path="${CODEX_WRAPPER_BACKUP:-}"
  fi

  if [ -x "$INSTALL_DIR/.venv/bin/dsproxy" ]; then
    run_quiet "Codex profile removed: deepseek" "$INSTALL_DIR/.venv/bin/dsproxy" uninstall-codex-profile --name deepseek --no-backup || true
    run_quiet "Codex profile removed: deepseek-thinking" "$INSTALL_DIR/.venv/bin/dsproxy" uninstall-codex-profile --name deepseek-thinking --no-backup || true
  fi

  if [ -f "$wrapper_path" ] && grep -q "CoDeepSeedeX codex wrapper" "$wrapper_path" 2>/dev/null; then
    if [ "$DRY_RUN" = "1" ]; then
      printf '+ remove %q\n' "$wrapper_path" >> "$INSTALL_LOG"
    else
      rm -f "$wrapper_path"
    fi
    ok "Codex wrapper removed"

    if [ -n "$backup_path" ] && [ -f "$backup_path" ]; then
      if [ "$DRY_RUN" = "1" ]; then
        printf '+ restore %q to %q\n' "$backup_path" "$wrapper_path" >> "$INSTALL_LOG"
      else
        mv "$backup_path" "$wrapper_path"
      fi
      ok "Previous codex command restored"
    fi
  fi

  if [ -f "$BIN_DIR/dsproxy" ] && grep -q "$INSTALL_DIR/.venv/bin/dsproxy" "$BIN_DIR/dsproxy" 2>/dev/null; then
    if [ "$DRY_RUN" = "1" ]; then
      printf '+ remove %q\n' "$BIN_DIR/dsproxy" >> "$INSTALL_LOG"
    else
      rm -f "$BIN_DIR/dsproxy"
    fi
    ok "dsproxy wrapper removed"
  fi

  if [ "$REMOVE_FILES" = "1" ]; then
    if [ "$DRY_RUN" = "1" ]; then
      printf '+ remove install/env files\n' >> "$INSTALL_LOG"
    else
      rm -rf "$INSTALL_DIR"
      rm -f "$ENV_FILE"
      rm -f "$MANIFEST_FILE"
    fi
    ok "Install files removed"
  fi

  step "Done"
  sub_title "Install log"
  printf '  %s\n' "$INSTALL_LOG"
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    --non-interactive) NON_INTERACTIVE=1 ;;
    --install-dir) INSTALL_DIR="$2"; shift ;;
    --repo-url) REPO_URL="$2"; shift ;;
    --bin-dir) BIN_DIR="$2"; shift ;;
    --config-dir) CONFIG_DIR="$2"; ENV_FILE="$CONFIG_DIR/env"; MANIFEST_FILE="$CONFIG_DIR/install-manifest.env" ;;
    --env-file) ENV_FILE="$2" ;;
    --no-codex-profile) INSTALL_CODEX_PROFILE=0 ;;
    --no-codex-wrapper) INSTALL_CODEX_WRAPPER=0 ;;
    --uninstall) UNINSTALL=1 ;;
    --remove-files) REMOVE_FILES=1 ;;
    -h|--help|-H) usage; exit 0 ;;
    *) echo "ERROR: unknown argument: $1" >&2; exit 2 ;;
  esac
  shift
done

: > "$INSTALL_LOG"

if [ "$UNINSTALL" = "1" ]; then
  uninstall
  exit 0
fi

logo

divider
section_title "Setup plan"
printf '%s\n' "  1. Check Python and Git"
printf '%s\n' "  2. Install or update repository"
printf '%s\n' "  3. Create virtual environment"
printf '%s\n' "  4. Install dsproxy"
printf '%s\n' "  5. Save local env file"
printf '%s\n' "  6. Install Codex profiles"
printf '%s\n' "  7. Install safe Codex wrapper, recommended"
sub_title "Install log"
printf '  %s\n' "$INSTALL_LOG"

step "Checking requirements"

PY_VERSION="$(python3 - <<'PY'
import sys
if sys.version_info < (3, 11):
    raise SystemExit("ERROR: Python >= 3.11 is required")
print(sys.version.split()[0])
PY
)"
ok "Python $PY_VERSION"

if ! command -v git >/dev/null 2>&1; then
  echo "ERROR: git is required" >&2
  exit 1
fi
ok "Git available"

step "Configuration"

DEFAULT_STABLE_PORT="${DEEPSEEK_PROXY_PORT:-8000}"
DEFAULT_THINKING_PORT="${DEEPSEEK_PROXY_THINKING_PORT:-8001}"
STABLE_PORT="$(read_from_tty "Stable proxy port" "$DEFAULT_STABLE_PORT")"
THINKING_PORT="$(read_from_tty "Thinking proxy port" "$DEFAULT_THINKING_PORT")"
API_KEY="$(read_secret_from_tty "DeepSeek API key" "${DEEPSEEK_API_KEY:-}")"
WRAPPER_CHOICE="$(read_yes_no "Install codex wrapper for deepseek/deepseek-thinking profiles? [Y/n] (Recommended):" "Y")"

case "$WRAPPER_CHOICE" in
  n|N|no|NO|No) INSTALL_CODEX_WRAPPER=0 ;;
  *) INSTALL_CODEX_WRAPPER=1 ;;
esac

if [ -z "$API_KEY" ]; then
  warn "DEEPSEEK_API_KEY is empty; set it before using the proxy"
fi

step "Installing"

if [ -d "$INSTALL_DIR/.git" ]; then
  run_quiet "Repository updated" git -C "$INSTALL_DIR" pull --ff-only
else
  run_quiet "Install parent directory ready" mkdir -p "$(dirname "$INSTALL_DIR")"
  run_quiet "Repository installed" git clone "$REPO_URL" "$INSTALL_DIR"
fi

run_quiet "Virtual environment ready" python3 -m venv "$INSTALL_DIR/.venv"
run_quiet "pip upgraded" "$INSTALL_DIR/.venv/bin/python" -m pip install --upgrade pip
run_quiet "Python package installed" "$INSTALL_DIR/.venv/bin/python" -m pip install -e "$INSTALL_DIR"

write_env_file "$STABLE_PORT" "$THINKING_PORT" "$API_KEY"
write_dsproxy_wrapper

run_quiet "dsproxy config initialized" "$INSTALL_DIR/.venv/bin/dsproxy" config init

if [ "$INSTALL_CODEX_PROFILE" = "1" ]; then
  run_quiet "Codex profile installed: deepseek" "$INSTALL_DIR/.venv/bin/dsproxy" install-codex-profile \
    --name deepseek \
    --provider-name deepseek-proxy \
    --base-url "http://127.0.0.1:${STABLE_PORT}/v1" \
    --model deepseek-v4-flash \
    --reasoning-effort medium

  run_quiet "Codex profile installed: deepseek-thinking" "$INSTALL_DIR/.venv/bin/dsproxy" install-codex-profile \
    --name deepseek-thinking \
    --provider-name deepseek-thinking-proxy \
    --base-url "http://127.0.0.1:${THINKING_PORT}/v1" \
    --model deepseek-v4-pro \
    --reasoning-effort xhigh
fi

write_codex_wrapper "$STABLE_PORT" "$THINKING_PORT"

step "Done"

sub_title "Next steps"
printf '%s\n' "  codex --profile deepseek"
printf '%s\n' "  codex --profile deepseek-thinking"

sub_title "Inside Codex TUI"
printf '%s\n' "  /status       show session/runtime status"
printf '%s\n' "  /model        switch model or reasoning effort"
printf '%s\n' "  /plan         plan before implementation"
printf '%s\n' "  check balance"

sub_title "Shell commands"
printf '%s\n' "  dsproxy balance"
printf '%s\n' "  dsproxy config show"
printf '%s\n' "  dsproxy config set-model deepseek-v4-flash"
printf '%s\n' "  dsproxy config set-effort high"

sub_title "Continue a previous Codex conversation"
printf '%s\n' "  codex --profile deepseek-thinking resume"

sub_title "Uninstall integration"
printf '%s\n' "  bash scripts/install.sh --uninstall"

sub_title "Install log"
printf '  %s\n' "$INSTALL_LOG"

divider