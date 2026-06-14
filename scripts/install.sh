#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="${COX_INSTALL_DIR:-$HOME/.local/share/codexchange}"
REPO_URL="${COX_REPO_URL:-https://github.com/Awenforever/CoDeepSeedeX.git}"
LATEST_RELEASE_API_URL="${COX_LATEST_RELEASE_API_URL:-https://api.github.com/repos/Awenforever/CoDeepSeedeX/releases/latest}"
INSTALL_REF="${COX_INSTALL_REF:-}"
COX_PUBLIC_RELEASE_TAG="${COX_LATEST_RELEASE_FALLBACK_TAG:-v0.4.12-alpha}"
BIN_DIR="${COX_BIN_DIR:-$HOME/.local/bin}"
CONFIG_DIR="${COX_CONFIG_DIR:-$HOME/.config/codexchange}"
ENV_FILE="${COX_ENV_FILE:-$CONFIG_DIR/env}"
MANIFEST_FILE="${COX_MANIFEST_FILE:-$CONFIG_DIR/install-manifest.env}"
INSTALL_LOG="${COX_INSTALL_LOG:-/tmp/codexchange-install-$(date +%Y%m%d_%H%M%S).log}"
BOOTSTRAP_LOG="${COX_BOOTSTRAP_LOG:-}"
LOCAL_BACKUP_DIR="${COX_BACKUP_DIR:-/tmp/codexchange-install-backups-$(date +%Y%m%d_%H%M%S)}"
if [ -n "${COX_PYTHON_BIN:-}" ]; then
  PYTHON_BIN="$COX_PYTHON_BIN"
  PYTHON_BIN_EXPLICIT=1
else
  PYTHON_BIN=""
  PYTHON_BIN_EXPLICIT=0
fi

DRY_RUN=0
NON_INTERACTIVE=0
FORCE_CODEX_WRAPPER="${COX_FORCE_CODEX_WRAPPER:-0}"
FORCE_COX_WRAPPER="${COX_FORCE_COX_WRAPPER:-0}"
INSTALL_CODEX_PROFILE=1
INSTALL_CODEX_WRAPPER=1
INSTALL_SHELL_PROFILE=1
SHELL_PROFILE_FILE=""
UNINSTALL=0
REMOVE_FILES=0
PROMPTED_MODEL_PROVIDER=""
PROMPTED_MODEL_BASE_URL=""
PROMPTED_MODEL_NAME=""
RESOLVED_MODEL_PROVIDER=""
RESOLVED_MODEL_BASE_URL=""
RESOLVED_MODEL_NAME=""
PROMPTED_CUSTOM_PROVIDER_NAME=""
RESOLVED_MODEL_PROVIDER_DISPLAY_NAME=""
RESOLVED_MODEL_PROVIDER_TYPE=""
MODEL_PROVIDER_REGISTRY_FILE="${COX_MODEL_PROVIDER_REGISTRY:-$CONFIG_DIR/model-providers.json}"

show_version_source() {
  sub_title "Version source"
  printf '  Install ref: %s\n' "${INSTALL_REF:-<GitHub Latest Release>}"
  printf '  Installer source: %s\n' "${COX_INSTALLER_SOURCE:-local script or current checkout}"
  printf '  Repository source: %s\n' "$REPO_URL"
}

logo() {
  cat <<'COX_INSTALLER_LOGO_ART'
   ____      ____                 ____              _      __  __
  / ___|___ |  _ \  ___  ___ _ __/ ___|  ___  ___  __| | ___ \ \/ /
 | |   / _ \| | | |/ _ \/ _ \ '_ \___ \ / _ \/ _ \/ _` |/ _ \ \  /
 | |__| (_) | |_| |  __/  __/ |_) |__) |  __/  __/ (_| |  __/ /  \
  \____\___/|____/ \___|\___| .__/____/ \___|\___|\__,_|\___|/_/\_\
                             |_|

COX_INSTALLER_LOGO_ART
  printf '  CodeXchange \033[1;35m%s\033[0m\n' "${INSTALL_REF:-GitHub Latest}"
  cat <<'COX_INSTALLER_LOGO_SUBTITLE'
  Codex × multi-provider local Responses exchange
COX_INSTALLER_LOGO_SUBTITLE
}

usage() {
  cat <<'USAGE'
Usage: scripts/install.sh [options]

Options:
  --dry-run              Print actions without applying changes
  --non-interactive      Do not prompt; use environment/default values
  --install-dir DIR      Installation directory
  --repo-url URL         Git repository URL
  --install-ref REF      Target release tag or explicit git ref; defaults to GitHub Latest Release
  --bin-dir DIR          Directory for cox and optional codex wrapper
  --config-dir DIR       Config directory
  --env-file FILE        Env file path
  --python-bin PATH     Python interpreter for venv, default: $COX_PYTHON_BIN or python3
  --no-codex-profile     Skip Codex profile installation
  --no-codex-wrapper     Skip safe codex wrapper installation
  --no-shell-profile    Do not update shell startup files for PATH/env loading
  --uninstall            Remove profiles and wrappers installed by CodeXchange
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



ui_terminal_width() {
  local cols="${COLUMNS:-}"
  if [ -z "$cols" ] && command -v tput >/dev/null 2>&1; then
    cols="$(tput cols 2>/dev/null || true)"
  fi
  case "$cols" in
    ''|*[!0-9]*) cols=82 ;;
  esac
  if [ "$cols" -lt 72 ]; then
    cols=72
  fi
  if [ "$cols" -gt 82 ]; then
    cols=82
  fi
  printf '%s\n' "$cols"
}



ui_repeat() {
  local char="$1"
  local count="$2"
  local out=""
  while [ "$count" -gt 0 ]; do
    out="${out}${char}"
    count=$((count - 1))
  done
  printf '%s' "$out"
}

ui_trim_text() {
  local text="$1"
  local max="$2"
  if [ "$max" -lt 8 ]; then
    max=8
  fi
  if [ "${#text}" -gt "$max" ]; then
    printf '%s…\n' "${text:0:$((max - 1))}"
  else
    printf '%s\n' "$text"
  fi
}

ui_wrap_text() {
  local text="${1:-}"
  local max="${2:-72}"
  local cut segment
  if [ -z "$text" ]; then
    printf '\n'
    return 0
  fi
  while [ "${#text}" -gt "$max" ]; do
    cut="$max"
    while [ "$cut" -gt 28 ] && [ "${text:$cut:1}" != " " ]; do
      cut=$((cut - 1))
    done
    if [ "$cut" -le 28 ]; then
      cut="$max"
    fi
    segment="${text:0:$cut}"
    printf '%s\n' "${segment%"${segment##*[![:space:]]}"}"
    text="${text:$cut}"
    text="${text#"${text%%[![:space:]]*}"}"
  done
  printf '%s\n' "$text"
}



ui_box_top() {
  local title="${1:-CodeXchange}"
  local width="${2:-$(ui_terminal_width)}"
  local clipped=""
  local fill_count=0
  clipped="$(ui_trim_text "$title" "$((width - 8))")"
  fill_count=$((width - ${#clipped} - 4))
  if [ "$fill_count" -lt 4 ]; then
    fill_count=4
  fi
  printf '\n\033[38;5;33m─ %s %s\033[0m\033[K\n' "$clipped" "$(ui_repeat "─" "$fill_count")"
}

ui_box_separator() {
  printf '\n'
}

ui_box_bottom() {
  local width="${1:-$(ui_terminal_width)}"
  printf '\033[38;5;33m%s\033[0m\033[K\n' "$(ui_repeat "─" "$width")"
}

ui_box_line() {
  local text="${1:-}"
  local width="${2:-$(ui_terminal_width)}"
  ui_box_line_styled "$text" "$width" ""
}

ui_box_line_styled() {
  local text="${1:-}"
  local width="${2:-$(ui_terminal_width)}"
  local style="${3:-}"
  local inner=$((width - 4))
  local line=""
  while IFS= read -r line; do
    line="$(ui_trim_text "$line" "$inner")"
    if [ -n "$style" ]; then
      printf '  %b%s\033[0m\033[K\n' "$style" "$line"
    else
      printf '  %s\033[K\n' "$line"
    fi
  done < <(ui_wrap_text "$text" "$inner")
}

ui_step_footer() {
  local text="${1:-Step 1/1}"
  local width="${2:-$(ui_terminal_width)}"
  local prefix="─ ${text} "
  local fill_len=$((width - ${#prefix}))
  if [ "$fill_len" -lt 4 ]; then
    fill_len=4
  fi
  printf '\033[38;5;33m%s%s\033[0m\033[K\n' "$prefix" "$(ui_repeat "─" "$fill_len")"
}

print_install_logs() {
  sub_title "Install logs"
  if [ -n "${BOOTSTRAP_LOG:-}" ]; then
    printf '  \033[2mbootstrap\033[0m %s\n' "$BOOTSTRAP_LOG"
  fi
  printf '  \033[2minstall  \033[0m %s\n' "$INSTALL_LOG"
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

run_git_quiet() {
  local label="$1"
  local operation="$2"
  shift 2
  printf '  ... %s\n' "$label"

  if [ "$DRY_RUN" = "1" ]; then
    printf '+ %s\n' "$*" >> "$INSTALL_LOG"
    ok "$label"
    return 0
  fi

  if "$@" >> "$INSTALL_LOG" 2>&1; then
    ok "$label"
    return 0
  fi

  warn "$label failed. See log: $INSTALL_LOG"
  warn "Git repository setup failed during: $operation"
  warn "Possible causes: network/TLS/proxy interruption, GitHub access failure, invalid --repo-url, repository permission issue, or a conflicting install directory."
  warn "Next step: retry after checking network/proxy/CA certificates, or use --repo-url /path/to/local-or-mirrored-repo."

  {
    printf '\n===== CodeXchange git setup diagnosis =====\n'
    printf 'operation=%s\n' "$operation"
    printf 'repo_url=%s\n' "$REPO_URL"
    printf 'install_dir=%s\n' "$INSTALL_DIR"
    printf 'hint=%s\n' "If this is a GitHub TLS/network failure, retry later or rerun with --repo-url pointing to a local or mirrored repository."
    printf 'hint=%s\n' "If the install directory exists but is not a valid clone, move it aside or choose another --install-dir."
  } >> "$INSTALL_LOG"

  return 1
}


resolve_install_ref() {
  if [ -n "$INSTALL_REF" ]; then
    printf '%s\n' "$INSTALL_REF"
    return 0
  fi

  local raw=""
  local tag=""
  if raw="$(curl -fsSL --retry 5 --retry-all-errors --retry-delay 2 --connect-timeout 15 --max-time 60 "$LATEST_RELEASE_API_URL" 2>> "$INSTALL_LOG")"; then
    tag="$(printf '%s\n' "$raw" | sed -nE 's/.*"tag_name"[[:space:]]*:[[:space:]]*"([^"]+)".*/\1/p' | head -n 1)"
  fi
  if [ -n "$tag" ]; then
    printf '%s\n' "$tag"
    return 0
  fi

  if [ -n "$COX_PUBLIC_RELEASE_TAG" ]; then
    warn "Could not resolve GitHub Latest Release tag through API; falling back to packaged public release tag: $COX_PUBLIC_RELEASE_TAG"
    printf '+ Latest Release API fallback used: %s\n' "$COX_PUBLIC_RELEASE_TAG" >> "$INSTALL_LOG"
    printf '%s\n' "$COX_PUBLIC_RELEASE_TAG"
    return 0
  fi

  echo "ERROR: could not resolve GitHub Latest Release tag; set COX_INSTALL_REF or pass --install-ref" >&2
  return 1
}


clean_tty_input_value() {
  local py="${PYTHON_BIN:-python3}"
  "$py" - "$1" <<'PYCOX_CLEAN_TTY_INPUT_P218A3'
import sys
raw = sys.argv[1] if len(sys.argv) > 1 else ""
buf = []
for ch in raw:
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
print("".join(buf).strip())
PYCOX_CLEAN_TTY_INPUT_P218A3
}

normalize_openai_base_url() {
  local py="${PYTHON_BIN:-python3}"
  "$py" - "$1" <<'PYCOX_NORMALIZE_BASE_URL_P218A3'
import re
import sys
url = sys.argv[1] if len(sys.argv) > 1 else ""
url = re.sub(r"[\x00-\x1f\x7f]", "", url).strip().rstrip("/")
for suffix in ("/chat/completions", "/responses", "/models"):
    if url.endswith(suffix):
        url = url[: -len(suffix)]
        break
url = url.rstrip("/")
print(url)
PYCOX_NORMALIZE_BASE_URL_P218A3
}

is_probable_api_key_value() {
  local py="${PYTHON_BIN:-python3}"
  "$py" - "$1" <<'PYCOX_PROBABLE_API_KEY_P218A5'
import re
import sys

value = (sys.argv[1] if len(sys.argv) > 1 else "").strip()
lower = value.lower()
if not value:
    raise SystemExit(1)
if lower.startswith(("sk-", "sk_", "bearer ", "api-key", "apikey", "x-api-key")):
    raise SystemExit(0)
if re.fullmatch(r"[A-Za-z0-9_.=-]{32,}", value):
    model_words = ("deepseek", "gpt", "glm", "qwen", "kimi", "moonshot", "zhipu", "doubao", "baichuan", "mimo", "flash", "pro", "chat", "model", "reasoner", "coder", "vision", "image", "embedding")
    if not any(word in lower for word in model_words):
        raise SystemExit(0)
raise SystemExit(1)
PYCOX_PROBABLE_API_KEY_P218A5
}

is_valid_model_name_value() {
  local value="$1"
  value="$(clean_tty_input_value "$value")"
  [ -n "$value" ] || return 1
  case "$value" in
    http://*|https://*|*/*|*$'\177'*|*$'\b'*|*" "*|*$'\t'*)
      return 1
      ;;
  esac
  if is_probable_api_key_value "$value"; then
    return 1
  fi
  return 0
}

ui_render_input_panel() {
  local title="${1:-Input}"
  local prompt="${2:-}"
  local default_value="${3:-}"
  local helper="${4:-}"
  local footer="${5:-Step 2/5}"
  local kind="${6:-text}"
  local width
  width="$(ui_terminal_width)"

  printf '\033[?25h' > /dev/tty 2>/dev/null || true
  ui_box_top "CodeXchange" "$width" > /dev/tty
  ui_box_line "" "$width" > /dev/tty
  ui_box_line_styled "$title" "$width" "\033[1;38;5;75m" > /dev/tty
  ui_box_line "" "$width" > /dev/tty
  ui_box_line "$prompt" "$width" > /dev/tty
  if [ -n "$default_value" ]; then
    if [ "$kind" = "secret" ]; then
      ui_box_line "Default: existing hidden value" "$width" > /dev/tty
    else
      ui_box_line "Default: $default_value" "$width" > /dev/tty
    fi
  fi
  if [ -n "$helper" ]; then
    ui_box_line_styled "Hint: $helper" "$width" "\033[2m" > /dev/tty
  fi
  ui_box_line "" "$width" > /dev/tty
  if [ "$kind" = "secret" ]; then
    ui_box_line_styled "Input is hidden. Press Enter to keep the existing value when one is available." "$width" "\033[2m" > /dev/tty
    ui_box_line_styled "hidden · Enter keeps existing" "$width" "\033[2m" > /dev/tty
    ui_box_line_styled "Backspace on an empty input returns to the previous step." "$width" "\033[2m" > /dev/tty
  else
    ui_box_line_styled "Press Enter to keep the default value." "$width" "\033[2m" > /dev/tty
    ui_box_line_styled "Backspace on an empty input returns to the previous step." "$width" "\033[2m" > /dev/tty
  fi
  ui_step_footer "$footer" "$width" > /dev/tty
}


cox_should_skip_interactive_hold() {
  [ "${COX_NONINTERACTIVE:-}" = "1" ] && return 0
  [ "${CI:-}" = "1" ] && return 0
  [ ! -t 2 ] && return 0
  return 1
}

show_model_api_validation_hold() {
  if cox_should_skip_interactive_hold; then
    return 0
  fi
  local width
  local key_state
  local provider_label
  local provider_type
  width="$(ui_terminal_width)"
  key_state="$(model_api_key_state_label)"
  provider_label="$(model_api_provider_display_label)"
  provider_type="$(model_api_provider_type_label)"

  if [ "$NON_INTERACTIVE" = "1" ] || [ ! -r /dev/tty ] || [ ! -w /dev/tty ]; then
    return 0
  fi

  ui_box_top "CodeXchange" "$width" > /dev/tty
  ui_box_line "" "$width" > /dev/tty
  ui_box_line_styled "${provider_label} validation" "$width" "\033[1;38;5;75m" > /dev/tty
  ui_box_line "" "$width" > /dev/tty
  ui_box_line "Provider: ${provider_label:-<unset>}" "$width" > /dev/tty
  ui_box_line "Provider type: ${provider_type:-<unset>}" "$width" > /dev/tty
  ui_box_line "Base URL: ${PROMPTED_MODEL_BASE_URL:-<unset>}" "$width" > /dev/tty
  ui_box_line "Active model: ${PROMPTED_MODEL_NAME:-<unset>}" "$width" > /dev/tty
  ui_box_line "API key: ${key_state}" "$width" > /dev/tty
  ui_box_line "" "$width" > /dev/tty
  ui_box_line "Validation: ${MODEL_API_VALIDATION_STATUS:-not_run}" "$width" > /dev/tty
  ui_box_line "Method: ${MODEL_API_VALIDATION_METHOD:-<not_run>}" "$width" > /dev/tty
  ui_box_line "URL: ${MODEL_API_VALIDATION_URL:-<not_run>}" "$width" > /dev/tty
  if [ -n "${MODEL_API_VALIDATION_ERROR:-}" ]; then
    ui_box_line "Detail: ${MODEL_API_VALIDATION_ERROR}" "$width" > /dev/tty
  fi
  ui_box_line "" "$width" > /dev/tty
  ui_box_line_styled "Press Enter to continue." "$width" "\033[1;38;5;75m" > /dev/tty
  ui_step_footer "Step 2/5" "$width" > /dev/tty

  printf "\n  Press Enter to continue..." > /dev/tty
  IFS= read -r COX_MODEL_API_VALIDATION_CONTINUE < /dev/tty || true
  printf "\n" > /dev/tty
}

show_install_completion_hold() {
  if cox_should_skip_interactive_hold; then
    return 0
  fi
  local width
  local public_version
  local internal_version
  local detected_public
  local detected_internal
  width="$(ui_terminal_width)"
  public_version="${COX_PUBLIC_VERSION:-v0.4.12-alpha}"
  internal_version="${COX_INTERNAL_VERSION:-}"

  if [ -x "${INSTALL_DIR:-}/.venv/bin/cox" ]; then
    detected_public="$("${INSTALL_DIR}/.venv/bin/cox" --version 2>/dev/null | sed -n 's/^public version: //p' | head -1 || true)"
    detected_internal="$("${INSTALL_DIR}/.venv/bin/cox" --version 2>/dev/null | sed -n 's/^internal version: //p' | head -1 || true)"
    if [ -n "$detected_public" ]; then
      public_version="$detected_public"
    fi
    if [ -n "$detected_internal" ]; then
      internal_version="$detected_internal"
    fi
  fi
  if [ -z "$internal_version" ]; then
    internal_version="unknown"
  fi

  if [ "$NON_INTERACTIVE" = "1" ] || [ ! -r /dev/tty ] || [ ! -w /dev/tty ]; then
    return 0
  fi

  ui_box_top "CodeXchange" "$width" > /dev/tty
  ui_box_line "" "$width" > /dev/tty
  ui_box_line_styled "Setup complete" "$width" "\033[1;38;5;75m" > /dev/tty
  ui_box_line "" "$width" > /dev/tty
  ui_box_line "Version: ${public_version} / ${internal_version}" "$width" > /dev/tty
  ui_box_line "Install dir: ${INSTALL_DIR:-<unknown>}" "$width" > /dev/tty
  ui_box_line "Config dir: ${CONFIG_DIR:-<unknown>}" "$width" > /dev/tty
  ui_box_line "Env file: ${ENV_FILE:-<unknown>}" "$width" > /dev/tty
  ui_box_line "Codex dir: ${CODEX_HOME:-$HOME/.codex}" "$width" > /dev/tty
  ui_box_line "" "$width" > /dev/tty
  ui_box_line "Provider configuration:" "$width" > /dev/tty
  ui_box_line "  Provider: ${PROMPTED_CUSTOM_PROVIDER_NAME:-${RESOLVED_MODEL_PROVIDER_DISPLAY_NAME:-${PROMPTED_MODEL_PROVIDER:-${RESOLVED_MODEL_PROVIDER:-<unset>}}}}" "$width" > /dev/tty
  ui_box_line "  Provider type: ${RESOLVED_MODEL_PROVIDER_TYPE:-$(model_api_provider_type_label)}" "$width" > /dev/tty
  ui_box_line "  Base URL: ${PROMPTED_MODEL_BASE_URL:-${RESOLVED_MODEL_BASE_URL:-<unset>}}" "$width" > /dev/tty
  ui_box_line "  Active model: ${PROMPTED_MODEL_NAME:-${RESOLVED_MODEL_NAME:-<unset>}}" "$width" > /dev/tty
  ui_box_line "  Validation: ${MODEL_API_VALIDATION_STATUS:-not_run}" "$width" > /dev/tty
  ui_box_line "  Method: ${MODEL_API_VALIDATION_METHOD:-<not_run>}" "$width" > /dev/tty
  ui_box_line "  URL: ${MODEL_API_VALIDATION_URL:-<not_run>}" "$width" > /dev/tty
  if [ -n "${MODEL_API_VALIDATION_ERROR:-}" ]; then
    ui_box_line "  Detail: ${MODEL_API_VALIDATION_ERROR}" "$width" > /dev/tty
  fi
  ui_box_line "" "$width" > /dev/tty
  ui_box_line "Start using CodeXchange:" "$width" > /dev/tty
  ui_box_line "  codex --profile cox" "$width" > /dev/tty
  ui_box_line "" "$width" > /dev/tty
  ui_box_line "Optional verification:" "$width" > /dev/tty
  ui_box_line "  cox --version" "$width" > /dev/tty
  ui_box_line "  cox config show" "$width" > /dev/tty
  ui_box_line "" "$width" > /dev/tty
  ui_box_line_styled "Press Enter to finish." "$width" "\033[1;38;5;75m" > /dev/tty
  ui_step_footer "Complete" "$width" > /dev/tty

  printf "\n  Press Enter to finish..." > /dev/tty
  IFS= read -r COX_FINISH_SETUP < /dev/tty || true
  printf "\n" > /dev/tty
}

read_from_tty() {
  local prompt="$1"
  local default_value="${2:-}"
  local value=""
  local title="${COX_INPUT_TITLE:-$prompt}"
  local footer="${COX_INPUT_STEP:-$(menu_step_label_for_prompt "$prompt")}"
  local helper="${COX_INPUT_DETAIL:-}"
  local key=""
  local old_stty=""

  if [ "$NON_INTERACTIVE" = "1" ] || [ ! -r /dev/tty ] || [ ! -w /dev/tty ]; then
    printf '%s\n' "$default_value"
    return 0
  fi

  stty sane < /dev/tty 2>/dev/null || true
  ui_render_input_panel "$title" "$prompt" "$default_value" "$helper" "$footer" "text"
  printf '\n  > ' > /dev/tty

  old_stty="$(stty -g < /dev/tty 2>/dev/null || true)"
  stty -icanon -echo min 1 time 0 < /dev/tty 2>/dev/null || true

  while IFS= read -rsn1 key < /dev/tty; do
    case "$key" in
      "")
        [ -n "$old_stty" ] && stty "$old_stty" < /dev/tty 2>/dev/null || stty sane < /dev/tty 2>/dev/null || true
        printf '\n' > /dev/tty
        value="$(clean_tty_input_value "$value")"
        if [ -z "$value" ]; then
          value="$default_value"
        fi
        printf '%s\n' "$value"
        return 0
        ;;
      $'\x7f'|$'\b')
        if [ -z "$value" ]; then
          [ -n "$old_stty" ] && stty "$old_stty" < /dev/tty 2>/dev/null || stty sane < /dev/tty 2>/dev/null || true
          printf '\n' > /dev/tty
          printf '%s\n' "__COX_BACK__"
          return 0
        fi
        value="${value%?}"
        printf '\b \b' > /dev/tty
        ;;
      $'\x1b')
        # Ignore escape sequences in text input; arrow-key navigation is handled by menu surfaces.
        local rest=""
        IFS= read -rsn2 -t 0.05 rest < /dev/tty || true
        ;;
      *)
        value="${value}${key}"
        printf '%s' "$key" > /dev/tty
        ;;
    esac
  done

  [ -n "$old_stty" ] && stty "$old_stty" < /dev/tty 2>/dev/null || stty sane < /dev/tty 2>/dev/null || true
  printf '\n' > /dev/tty
  printf '%s\n' "$default_value"
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
  local helper="${3:-}"
  local value=""
  local title="${COX_INPUT_TITLE:-$prompt}"
  local footer="${COX_INPUT_STEP:-$(menu_step_label_for_prompt "$prompt")}"
  local detail="${COX_INPUT_DETAIL:-$helper}"
  local key=""
  local old_stty=""

  if [ "$NON_INTERACTIVE" = "1" ] || [ ! -r /dev/tty ] || [ ! -w /dev/tty ]; then
    printf '%s\n' "$default_value"
    return 0
  fi

  stty sane < /dev/tty 2>/dev/null || true
  ui_render_input_panel "$title" "$prompt" "$default_value" "$detail" "$footer" "secret"
  printf '\n  > ' > /dev/tty

  old_stty="$(stty -g < /dev/tty 2>/dev/null || true)"
  stty -icanon -echo min 1 time 0 < /dev/tty 2>/dev/null || true

  while IFS= read -rsn1 key < /dev/tty; do
    case "$key" in
      "")
        [ -n "$old_stty" ] && stty "$old_stty" < /dev/tty 2>/dev/null || stty sane < /dev/tty 2>/dev/null || true
        printf "\n\n" > /dev/tty
        value="$(clean_tty_input_value "$value")"
        if [ -z "$value" ] && [ -n "$default_value" ]; then
          printf '%s\n' "__COX_KEEP_EXISTING__"
          return 0
        fi
        printf '%s\n' "$value"
        return 0
        ;;
      $'\x7f'|$'\b')
        if [ -z "$value" ]; then
          [ -n "$old_stty" ] && stty "$old_stty" < /dev/tty 2>/dev/null || stty sane < /dev/tty 2>/dev/null || true
          printf "\n\n" > /dev/tty
          printf '%s\n' "__COX_BACK__"
          return 0
        fi
        value="${value%?}"
        printf '\b \b' > /dev/tty
        ;;
      $'\x1b')
        local rest=""
        IFS= read -rsn2 -t 0.05 rest < /dev/tty || true
        ;;
      *)
        value="${value}${key}"
        printf '*' > /dev/tty
        ;;
    esac
  done

  [ -n "$old_stty" ] && stty "$old_stty" < /dev/tty 2>/dev/null || stty sane < /dev/tty 2>/dev/null || true
  printf "\n\n" > /dev/tty
  printf '%s\n' "$default_value"
}

is_codexchange_codex_wrapper_candidate() {
  local path="$1"

  if [ -z "$path" ] || [ ! -f "$path" ]; then
    return 1
  fi

  case "$path" in
    /tmp/codexchange-*/.local/bin/codex|/tmp/codexchange-*/*/codex)
      return 0
      ;;
  esac

  grep -qE 'CodeXchange codex wrapper|COX_COMMAND|start_cox_profile|codexchange' "$path" 2>/dev/null
}

codex_candidate_looks_node_backed() {
  local candidate="$1"

  if [ -z "$candidate" ] || [ ! -f "$candidate" ]; then
    return 1
  fi

  head -n 1 "$candidate" 2>/dev/null | grep -Eq '(^#!.*node|/env[[:space:]]+node)' && return 0
  grep -qE 'node|@openai/codex|codex-cli' "$candidate" 2>/dev/null
}

is_valid_real_codex_candidate() {
  local candidate="$1"
  local wrapper_path="$2"
  local candidate_real=""
  local wrapper_real=""
  local version_text=""

  if [ -z "$candidate" ] || [ ! -x "$candidate" ]; then
    return 1
  fi

  candidate_real="$(readlink -f "$candidate" 2>/dev/null || printf '%s\n' "$candidate")"
  wrapper_real="$(readlink -f "$wrapper_path" 2>/dev/null || printf '%s\n' "$wrapper_path")"

  if [ "$candidate" = "$wrapper_path" ] || [ "$candidate_real" = "$wrapper_real" ]; then
    return 1
  fi

  if is_codexchange_codex_wrapper_candidate "$candidate"; then
    return 1
  fi
  if [ "$candidate_real" != "$candidate" ] && is_codexchange_codex_wrapper_candidate "$candidate_real"; then
    return 1
  fi

  case "$candidate_real" in
    /tmp/codexchange-*/.local/bin/codex|/tmp/codexchange-*/*/codex)
      return 1
      ;;
  esac

  version_text="$("$candidate" --version 2>&1 || true)"
  if printf '%s\n' "$version_text" | grep -qE 'codex-cli|OpenAI Codex'; then
    return 0
  fi

  # If Node.js is missing, the real Codex launcher may be present but unable to
  # print a version. Accept a non-CodeXchange executable named codex so the
  # managed wrapper can surface a clear CodeXchange diagnostic instead of
  # letting the shell fall through to /usr/local/bin/codex.
  if [ "$(basename "$candidate_real")" = "codex" ]; then
    return 0
  fi

  return 1
}

find_real_codex() {
  local wrapper_path="$1"
  local candidate=""
  local candidate_real=""
  local seen_file=""

  if [ -n "${COX_REAL_CODEX:-}" ]; then
    if is_valid_real_codex_candidate "$COX_REAL_CODEX" "$wrapper_path"; then
      readlink -f "$COX_REAL_CODEX" 2>/dev/null || printf '%s
' "$COX_REAL_CODEX"
      return 0
    fi
    warn "COX_REAL_CODEX is not a valid real Codex binary or points to a CodeXchange wrapper: $COX_REAL_CODEX"
    return 1
  fi

  seen_file="/tmp/codexchange-real-codex-candidates-$$.txt"
  : > "$seen_file"

  add_real_codex_candidate() {
    local item="$1"
    [ -n "$item" ] || return 0
    if grep -Fxq "$item" "$seen_file" 2>/dev/null; then
      return 0
    fi
    printf '%s
' "$item" >> "$seen_file"
    if is_valid_real_codex_candidate "$item" "$wrapper_path"; then
      readlink -f "$item" 2>/dev/null || printf '%s
' "$item"
      rm -f "$seen_file"
      return 0
    fi
    return 1
  }

  while IFS= read -r candidate; do
    candidate="${candidate#codex is }"
    candidate="${candidate#codex }"
    add_real_codex_candidate "$candidate" && return 0
  done < <(type -a codex 2>/dev/null | sed -n 's/^codex is //p')

  if command -v npm >/dev/null 2>&1; then
    local npm_prefix=""
    npm_prefix="$(npm config get prefix 2>/dev/null || true)"
    if [ -n "$npm_prefix" ] && [ "$npm_prefix" != "undefined" ] && [ "$npm_prefix" != "null" ]; then
      add_real_codex_candidate "$npm_prefix/bin/codex" && return 0
    fi
  fi

  for candidate in \
    "$HOME/.npm-global/bin/codex" \
    "$HOME/.local/share/npm/bin/codex" \
    "$HOME/.node_modules/bin/codex" \
    "/usr/local/bin/codex" \
    "/usr/bin/codex"
  do
    add_real_codex_candidate "$candidate" && return 0
  done

  rm -f "$seen_file"
  return 1
}

canonical_path() {
  if [ -n "${1:-}" ]; then
    readlink -f "$1" 2>/dev/null || printf '%s\n' "$1"
  fi
}

resolve_python_candidate_path() {
  local candidate="$1"
  if [ -z "$candidate" ]; then
    return 1
  fi

  case "$candidate" in
    */*)
      if [ -x "$candidate" ]; then
        printf '%s\n' "$candidate"
        return 0
      fi
      ;;
    *)
      command -v "$candidate" 2>/dev/null || true
      ;;
  esac
}

python_candidate_supports_codexchange() {
  local candidate="$1"
  local require_venv="${2:-1}"

  if [ -z "$candidate" ] || [ ! -x "$candidate" ]; then
    return 1
  fi

  "$candidate" - "$require_venv" <<'PYCOX_P221A2_PYTHON_CANDIDATE_CHECK'
import sys

require_venv = len(sys.argv) > 1 and sys.argv[1] == "1"
if sys.version_info < (3, 11):
    raise SystemExit(10)
if require_venv:
    try:
        import venv  # noqa: F401
    except Exception:
        raise SystemExit(11)
print(sys.version.split()[0])
PYCOX_P221A2_PYTHON_CANDIDATE_CHECK
}

is_existing_install_venv_python() {
  local candidate="$1"
  local venv_python="$INSTALL_DIR/.venv/bin/python"

  if [ -z "$candidate" ] || [ ! -x "$venv_python" ]; then
    return 1
  fi

  [ "$(canonical_path "$candidate")" = "$(canonical_path "$venv_python")" ]
}

select_codexchange_python_bin() {
  local explicit="${PYTHON_BIN_EXPLICIT:-0}"
  local candidate
  local candidate_path
  local require_venv
  local version

  if [ -n "${PYTHON_BIN:-}" ]; then
    candidate_path="$(resolve_python_candidate_path "$PYTHON_BIN")"
    require_venv=1
    if is_existing_install_venv_python "$candidate_path"; then
      require_venv=0
    fi
    if version="$(python_candidate_supports_codexchange "$candidate_path" "$require_venv" 2>/dev/null)"; then
      PYTHON_BIN="$candidate_path"
      COX_SELECTED_PYTHON_VERSION="$version"
      return 0
    fi
    if [ "$explicit" = "1" ]; then
      echo "ERROR: Python >= 3.11 is required by the selected interpreter: ${PYTHON_BIN:-<empty>}" >&2
      echo "Install Python 3.11+ or pass --python-bin /path/to/python3.11+. CodeXchange does not install or patch Python automatically." >&2
      return 1
    fi
  fi

  for candidate in \
    python3.13 \
    python3.12 \
    python3.11 \
    "$INSTALL_DIR/.venv/bin/python" \
    python3 \
    python
  do
    candidate_path="$(resolve_python_candidate_path "$candidate")"
    if [ -z "$candidate_path" ]; then
      continue
    fi

    require_venv=1
    if is_existing_install_venv_python "$candidate_path"; then
      require_venv=0
    fi

    if version="$(python_candidate_supports_codexchange "$candidate_path" "$require_venv" 2>/dev/null)"; then
      PYTHON_BIN="$candidate_path"
      COX_SELECTED_PYTHON_VERSION="$version"
      return 0
    fi
  done

  echo "ERROR: Python >= 3.11 is required, but no compatible interpreter was found." >&2
  echo "Checked: python3.13, python3.12, python3.11, existing install venv, python3, python." >&2
  echo "Install Python 3.11+ or pass --python-bin /path/to/python3.11+. CodeXchange does not install or patch Python automatically." >&2
  return 1
}

ensure_codexchange_python_bin() {
  if [ -n "${PYTHON_BIN:-}" ] && [ -n "${COX_SELECTED_PYTHON_VERSION:-}" ]; then
    return 0
  fi
  select_codexchange_python_bin
  printf '+ Python selected: %s (%s)\n' "$PYTHON_BIN" "${COX_SELECTED_PYTHON_VERSION:-unknown}" >> "$INSTALL_LOG"
}

json_string() {
  "$PYTHON_BIN" - "$1" <<'PY'
import json
import sys
print(json.dumps(sys.argv[1]))
PY
}

test_deepseek_api_key() {
  local api_key="$1"
  if [ -z "$api_key" ]; then
    return 1
  fi
  local result
  result="$("$PYTHON_BIN" - "$api_key" <<'PY'
import json
import sys
import urllib.request
import urllib.error

api_key = sys.argv[1]
request = urllib.request.Request(
    "https://api.deepseek.com/user/balance",
    headers={
        "Authorization": "Bearer " + api_key,
        "Accept": "application/json",
    },
    method="GET",
)
try:
    with urllib.request.urlopen(request, timeout=10) as response:
        response.read()
        print("ok" if 200 <= int(response.status) < 300 else "bad")
except Exception:
    print("bad")
PY
)"
  [ "$result" = "ok" ]
}


test_web_search_api_key() {
  local provider="$1"
  local api_key="$2"
  if [ -z "$provider" ] || [ -z "$api_key" ]; then
    return 1
  fi
  local result
  result="$("$PYTHON_BIN" - "$provider" "$api_key" <<'PYCOX_INSTALL_WEB_VALIDATION_P28A1'
import json
import sys
import urllib.parse
import urllib.request

provider = sys.argv[1].strip().lower()
api_key = sys.argv[2]
query = "test"

def has_auth_error(raw):
    try:
        data = json.loads(raw.decode("utf-8"))
    except Exception:
        return False
    if not isinstance(data, dict):
        return False
    values = []
    for key in ("error", "error_message", "message", "msg", "detail", "code", "status_code"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            values.append(value)
        elif isinstance(value, dict):
            for nested in ("message", "detail"):
                nested_value = value.get(nested)
                if isinstance(nested_value, str) and nested_value.strip():
                    values.append(nested_value)
    for value in values:
        lowered = value.lower()
        if any(token in lowered for token in ("unauthorized", "forbidden", "api key", "api-key", "apikey", "access key", "access token", "token", "authentication", "authorization", "auth", "invalid api key", "invalid apikey", "invalid token", "invalid authentication", "invalid authorization")) or lowered in {"1002", "401", "403"}:
            return True
    if str(data.get("status") or "").strip().lower() in {"error", "failed", "failure"}:
        return True
    return False

def request(method, url, headers=None, payload=None):
    data = None
    request_headers = dict(headers or {})
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/json")
    request_headers.setdefault("Accept", "application/json")
    req = urllib.request.Request(url, data=data, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read()
            return 200 <= int(resp.status) < 300 and not has_auth_error(raw)
    except Exception:
        return False

if provider == "serpapi":
    params = urllib.parse.urlencode({"engine": "google", "q": query, "api_key": api_key, "num": "1"})
    ok = request("GET", "https://serpapi.com/search.json?" + params)
elif provider == "tavily":
    ok = request("POST", "https://api.tavily.com/search", {"Authorization": "Bearer " + api_key}, {"query": query, "max_results": 1, "search_depth": "basic", "include_answer": False})
elif provider == "exa":
    ok = request("POST", "https://api.exa.ai/search", {"Authorization": "Bearer " + api_key}, {"query": query, "numResults": 1})
elif provider == "firecrawl":
    ok = request("POST", "https://api.firecrawl.dev/v2/search", {"Authorization": "Bearer " + api_key}, {"query": query, "limit": 1})
else:
    ok = False
print("ok" if ok else "bad")
PYCOX_INSTALL_WEB_VALIDATION_P28A1
)"
  [ "$result" = "ok" ]
}

test_image_api_key() {
  local provider="$1"
  local api_key="$2"
  LAST_IMAGE_VALIDATION_ARTIFACT=""

  if [ -z "$provider" ] || [ -z "$api_key" ]; then
    return 1
  fi

  local out_dir="${TMPDIR:-/tmp}/codexchange-image-validation-$(date +%Y%m%d_%H%M%S)"
  mkdir -p "$out_dir"

  local result_file="$out_dir/result.env"
  "$PYTHON_BIN" - "$provider" "$api_key" "$out_dir" <<'PYCOX_INSTALL_LIVE_IMAGE_VALIDATION_P210A24' > "$result_file"
import base64
import json
import mimetypes
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

provider = sys.argv[1].strip().lower().replace("-", "_")
api_key = sys.argv[2]
out_dir = Path(sys.argv[3])
out_dir.mkdir(parents=True, exist_ok=True)

prompt = 'A breathtaking glamorous adult anime-style woman, confident and alluring gaze, sleek off-shoulder evening dress, elegant curves, long flowing hair, luxury fashion editorial style, dramatic cinematic lighting, vivid colors, high detail, tasteful sensual atmosphere, safe for work, fully clothed, no nudity.'
timeout = 90

def emit(**items):
    for key, value in items.items():
        value = "" if value is None else str(value)
        value = value.replace("\n", " ").replace("\r", " ")
        print(f"{key}={value}")

def canonical(value):
    aliases = {
        "zhipuai": "zhipu",
        "bigmodel": "zhipu",
        "zhipu": "zhipu",
        "glm": "zai",
        "z_ai": "zai",
        "z.ai": "zai",
        "zai": "zai",
        "qwen": "qwen_image",
        "qwen_image": "qwen_image",
        "qwen_image_beijing": "qwen_image",
        "qwen_beijing": "qwen_image",
        "dashscope_beijing": "qwen_image",
        "qwen_image_singapore": "qwen_image_singapore",
        "qwen_singapore": "qwen_image_singapore",
        "dashscope_singapore": "qwen_image_singapore",
        "stability_ai": "stability",
        "stable_image": "stability",
        "stability": "stability",
        "fal_ai": "fal",
        "fal.ai": "fal",
        "fal": "fal",
    }
    return aliases.get(value, value)

def request_json(url, headers, payload, method="POST"):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    for key, value in headers.items():
        req.add_header(key, value)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
        return int(resp.status), json.loads(raw.decode("utf-8"))

def request_binary(url, headers, payload_bytes, content_type, method="POST"):
    req = urllib.request.Request(url, data=payload_bytes, method=method)
    for key, value in headers.items():
        req.add_header(key, value)
    if content_type:
        req.add_header("Content-Type", content_type)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return int(resp.status), resp.headers.get("content-type", ""), resp.read()

def download_image(url, target):
    req = urllib.request.Request(url, headers={"User-Agent": "CodeXchange image validation"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        content_type = resp.headers.get("content-type", "")
        raw = resp.read()
    if not raw:
        raise RuntimeError("empty image download")
    suffix = ".png"
    guessed = mimetypes.guess_extension(content_type.split(";")[0].strip())
    if guessed in {".png", ".jpg", ".jpeg", ".webp"}:
        suffix = guessed
    path = target.with_suffix(suffix)
    path.write_bytes(raw)
    return path

def save_base64(value, target):
    if "," in value and value.strip().startswith("data:"):
        value = value.split(",", 1)[1]
    raw = base64.b64decode(value)
    if not raw:
        raise RuntimeError("empty base64 image")
    path = target.with_suffix(".png")
    path.write_bytes(raw)
    return path

def first_image_evidence(data):
    candidates = []
    if isinstance(data, dict):
        candidates.append(data)
        for key in ("data", "images", "output", "results"):
            value = data.get(key)
            if isinstance(value, list):
                candidates.extend(x for x in value if isinstance(x, dict))
            elif isinstance(value, dict):
                candidates.append(value)
        output = data.get("output")
        if isinstance(output, dict):
            for key in ("choices", "results"):
                value = output.get(key)
                if isinstance(value, list):
                    candidates.extend(x for x in value if isinstance(x, dict))
    elif isinstance(data, list):
        candidates.extend(x for x in data if isinstance(x, dict))

    for item in candidates:
        for key in ("url", "image_url", "signed_url"):
            value = item.get(key)
            if isinstance(value, str) and value.startswith(("http://", "https://")):
                return ("url", value)
        for key in ("b64_json", "base64", "image_base64"):
            value = item.get(key)
            if isinstance(value, str) and len(value) > 80:
                return ("base64", value)
        image = item.get("image")
        if isinstance(image, str):
            if image.startswith(("http://", "https://")):
                return ("url", image)
            if len(image) > 80:
                return ("base64", image)
        if isinstance(image, dict):
            for key in ("url", "b64_json", "base64"):
                value = image.get(key)
                if isinstance(value, str):
                    if value.startswith(("http://", "https://")):
                        return ("url", value)
                    if len(value) > 80:
                        return ("base64", value)
    return ("", "")

def stability_multipart(prompt_text):
    boundary = "----CodeXchangeBoundary%d" % int(time.time() * 1000)
    parts = []
    def add(name, value):
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode())
    add("prompt", prompt_text)
    add("output_format", "png")
    add("aspect_ratio", "1:1")
    parts.append(f"--{boundary}--\r\n".encode())
    return boundary, b"".join(parts)

provider = canonical(provider)
target = out_dir / "test-image"

try:
    if provider == "zhipu":
        status, data = request_json(
            "https://open.bigmodel.cn/api/paas/v4/images/generations",
            {"Authorization": "Bearer " + api_key, "Content-Type": "application/json"},
            {"model": "cogview-4-250304", "prompt": prompt, "size": "1024x1024"},
        )
        kind, evidence = first_image_evidence(data)
    elif provider == "zai":
        status, data = request_json(
            "https://api.z.ai/api/paas/v4/images/generations",
            {"Authorization": "Bearer " + api_key, "Content-Type": "application/json"},
            {"model": "cogview-4-250304", "prompt": prompt, "size": "1024x1024"},
        )
        kind, evidence = first_image_evidence(data)
    elif provider == "qwen_image":
        status, data = request_json(
            "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation",
            {"Authorization": "Bearer " + api_key, "Content-Type": "application/json"},
            {"model": "qwen-image-2.0-pro", "input": {"messages": [{"role": "user", "content": [{"text": prompt}]}]}, "parameters": {"size": "1024*1024", "n": 1}},
        )
        kind, evidence = first_image_evidence(data)
    elif provider == "qwen_image_singapore":
        status, data = request_json(
            "https://dashscope-intl.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation",
            {"Authorization": "Bearer " + api_key, "Content-Type": "application/json"},
            {"model": "qwen-image-2.0-pro", "input": {"messages": [{"role": "user", "content": [{"text": prompt}]}]}, "parameters": {"size": "1024*1024", "n": 1}},
        )
        kind, evidence = first_image_evidence(data)
    elif provider == "stability":
        boundary, body = stability_multipart(prompt)
        status, content_type, raw = request_binary(
            "https://api.stability.ai/v2beta/stable-image/generate/core",
            {"Authorization": "Bearer " + api_key, "Accept": "image/*"},
            body,
            "multipart/form-data; boundary=" + boundary,
        )
        if status < 200 or status >= 300 or not raw:
            raise RuntimeError(f"unexpected_status_{status}")
        path = target.with_suffix(".png")
        path.write_bytes(raw)
        emit(status="ok", artifact=path, provider=provider, evidence="binary_image", http_status=status)
        raise SystemExit(0)
    elif provider == "fal":
        status, data = request_json(
            "https://fal.run/fal-ai/fast-sdxl",
            {"Authorization": "Key " + api_key, "Content-Type": "application/json"},
            {"prompt": prompt, "image_size": "square_hd", "num_images": 1},
        )
        kind, evidence = first_image_evidence(data)
    else:
        raise RuntimeError("unsupported_provider_for_live_install_validation")

    if kind == "url":
        artifact = download_image(evidence, target)
    elif kind == "base64":
        artifact = save_base64(evidence, target)
    else:
        debug_path = out_dir / "response.json"
        try:
            debug_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass
        raise RuntimeError("missing_image_evidence")

    emit(status="ok", artifact=artifact, provider=provider, evidence=kind, http_status=status)
except urllib.error.HTTPError as exc:
    body = exc.read().decode("utf-8", errors="replace")
    msg = re.sub(r"\s+", " ", body)[:240]
    emit(status="bad", provider=provider, error=f"http_{exc.code}", message=msg, artifact="")
except Exception as exc:
    emit(status="bad", provider=provider, error=type(exc).__name__, message=str(exc)[:240], artifact="")
PYCOX_INSTALL_LIVE_IMAGE_VALIDATION_P210A24

  local status=""
  local artifact=""
  local error=""
  local message=""
  status="$(sed -n 's/^status=//p' "$result_file" | tail -1)"
  artifact="$(sed -n 's/^artifact=//p' "$result_file" | tail -1)"
  error="$(sed -n 's/^error=//p' "$result_file" | tail -1)"
  message="$(sed -n 's/^message=//p' "$result_file" | tail -1)"

  if [ "$status" = "ok" ] && [ -n "$artifact" ] && [ -s "$artifact" ]; then
    LAST_IMAGE_VALIDATION_ARTIFACT="$artifact"
    return 0
  fi

  if [ -n "$error" ]; then
    warn "Live image validation error: $error ${message:+- $message}"
  fi
  warn "Live image validation workspace: $out_dir"
  return 1
}
model_api_base_url() {
  local provider="$1"
  case "$provider" in
    deepseek) printf '%s\n' "https://api.deepseek.com" ;;
    kimi|moonshot) printf '%s\n' "https://api.moonshot.ai/v1" ;;
    zhipu|zhipuai|bigmodel) printf '%s\n' "https://open.bigmodel.cn/api/paas/v4" ;;
    zhipu-coding|zhipu_coding|bigmodel-coding|bigmodel_coding) printf '%s\n' "https://open.bigmodel.cn/api/coding/paas/v4" ;;
    zai|z.ai|glm) printf '%s\n' "https://api.z.ai/api/paas/v4" ;;
    zai-coding|zai_coding|z.ai-coding|z.ai_coding) printf '%s\n' "https://api.z.ai/api/coding/paas/v4" ;;
    qwen-beijing|qwen_beijing|qwen|dashscope|aliyun) printf '%s\n' "https://dashscope.aliyuncs.com/compatible-mode/v1" ;;
    qwen-singapore|qwen_singapore|dashscope-singapore|dashscope_singapore) printf '%s\n' "https://dashscope-intl.aliyuncs.com/compatible-mode/v1" ;;
    qwen-us|qwen_us|qwen-us-virginia|qwen_us_virginia|dashscope-us|dashscope_us) printf '%s\n' "https://dashscope-us.aliyuncs.com/compatible-mode/v1" ;;
    custom) printf '%s\n' "" ;;
    *) printf '%s\n' "" ;;
  esac
}

model_api_default_model() {
  local provider="$1"
  case "$provider" in
    deepseek) printf '%s\n' "deepseek-v4-pro" ;;
    kimi|moonshot) printf '%s\n' "kimi-latest" ;;
    zhipu|zhipuai|bigmodel|zhipu-coding|zhipu_coding|bigmodel-coding|bigmodel_coding|zai|z.ai|glm) printf '%s\n' "glm-5.1" ;;
    zai-coding|zai_coding|z.ai-coding|z.ai_coding) printf '%s\n' "glm-4.7" ;;
    qwen-beijing|qwen_beijing|qwen|dashscope|aliyun|qwen-singapore|qwen_singapore|dashscope-singapore|dashscope_singapore) printf '%s\n' "qwen-plus" ;;
    qwen-us|qwen_us|qwen-us-virginia|qwen_us_virginia|dashscope-us|dashscope_us) printf '%s\n' "qwen-plus-us" ;;
    custom) printf '%s\n' "" ;;
    *) printf '%s\n' "" ;;
  esac
}

test_model_api_key() {
  local provider="$1"
  local api_key="$2"
  local base_url="$3"
  if [ -z "$api_key" ]; then
    return 1
  fi
  if [ "$provider" = "deepseek" ]; then
    test_deepseek_api_key "$api_key"
    return $?
  fi
  if [ -z "$base_url" ]; then
    return 1
  fi
  local result
  result="$($PYTHON_BIN - "$api_key" "$base_url" <<'PYCOX_INSTALL_MODEL_API_VALIDATION_P28A4'
import sys
import urllib.request

api_key = sys.argv[1]
base_url = sys.argv[2].rstrip("/")
request = urllib.request.Request(
    base_url + "/models",
    headers={"Authorization": "Bearer " + api_key, "Accept": "application/json"},
    method="GET",
)
try:
    with urllib.request.urlopen(request, timeout=10) as response:
        response.read()
        print("ok" if 200 <= int(response.status) < 300 else "bad")
except Exception:
    print("bad")
PYCOX_INSTALL_MODEL_API_VALIDATION_P28A4
)"
  [ "$result" = "ok" ]
}

menu_tty_printf() {
  printf "$@" > /dev/tty
}

menu_terminal_cols() {
  local cols=""
  if command -v tput >/dev/null 2>&1; then
    cols="$(tput cols 2>/dev/null || true)"
  fi
  case "$cols" in
    ''|*[!0-9]*) cols=80 ;;
  esac
  if [ "$cols" -lt 50 ]; then
    cols=50
  fi
  printf '%s\n' "$cols"
}

menu_truncate_line() {
  local line="$1"
  local width="$2"
  local max="$((width - 1))"
  if [ "$max" -lt 40 ]; then
    max=40
  fi
  if [ "${#line}" -gt "$max" ]; then
    printf '%s...\n' "${line:0:$((max - 3))}"
  else
    printf '%s\n' "$line"
  fi
}

menu_status_suffix() {
  local status="$1"
  case "$status" in
    supported) printf '[Supported]' ;;
    experimental) printf '[Experimental]' ;;
    custom) printf '[Custom]' ;;
    "model unavailable") printf '[Model unavailable]' ;;
    unsupported) printf '[Unsupported]' ;;
    plain|skip|'') printf '' ;;
    *) printf '[Unsupported]' ;;
  esac
}


menu_render_option_line() {
  local selected="$1"
  local value="$2"
  local label="$3"
  local status="$4"
  local width="$5"
  local inner=$((width - 4))
  local suffix=""
  local marker="○"
  local row=""
  local rendered=""

  if [ "$selected" = "1" ]; then
    marker="●"
  fi

  suffix="$(menu_status_suffix "$status")"
  if [ -n "$suffix" ]; then
    row="$(printf '%s [%s] %s  %s' "$marker" "$value" "$label" "$suffix")"
  else
    row="$(printf '%s [%s] %s' "$marker" "$value" "$label")"
  fi

  rendered="$(menu_truncate_line "$row" "$inner")"
  if [ "$selected" = "1" ]; then
    menu_tty_printf '  \033[1;38;5;75m%s\033[0m\033[K\n' "$rendered"
  else
    case "$status" in
      supported) menu_tty_printf '  \033[38;5;114m%s\033[0m\033[K\n' "$rendered" ;;
      experimental) menu_tty_printf '  \033[38;5;177m%s\033[0m\033[K\n' "$rendered" ;;
      custom) menu_tty_printf '  \033[38;5;215m%s\033[0m\033[K\n' "$rendered" ;;
      "model unavailable"|unsupported) menu_tty_printf '  \033[2m%s\033[0m\033[K\n' "$rendered" ;;
      *) menu_tty_printf '  %s\033[K\n' "$rendered" ;;
    esac
  fi
}

menu_back_value() {
  local option value _label _status
  for option in "$@"; do
    IFS='|' read -r value _label _status <<< "$option"
    if [ "$value" = "0" ]; then
      printf '0\n'
      return 0
    fi
  done
  for option in "$@"; do
    IFS='|' read -r value _label _status <<< "$option"
    if [ "$value" = "N" ]; then
      printf 'N\n'
      return 0
    fi
  done
  printf '\n'
}

menu_print_separator() {
  printf '\n'
}


menu_step_label_for_prompt() {
  local prompt="${1:-}"
  case "$prompt" in
    *"Install codex wrapper"*) printf 'Step 5/5\n' ;;
    *"image generation"*|*"Image"*|*"Qwen Image"*) printf 'Step 4/5\n' ;;
    *"web search"*|*"Web search"*) printf 'Step 3/5\n' ;;
    *"model"*|*"Model"*|*"ZhipuAI"*|*"Z.AI"*|*"Qwen / DashScope"*) printf 'Step 2/5\n' ;;
    *) printf 'Step 2/5\n' ;;
  esac
}



read_menu_choice_from_tty() {
  local prompt="$1"
  local default="${2:-}"
  shift 2 || true
  local options=("$@")
  local count="${#options[@]}"

  if [ "$count" -eq 0 ]; then
    printf '%s\n' "$default"
    return 0
  fi

  if [ ! -r /dev/tty ] || [ ! -w /dev/tty ] || [ "${COX_NO_ARROW_MENUS:-0}" = "1" ]; then
    printf '%s\n' "$default"
    return 0
  fi

  local selected=0
  local i
  for i in "${!options[@]}"; do
    IFS='|' read -r value _label _status <<< "${options[$i]}"
    if [ "$value" = "$default" ]; then
      selected="$i"
      break
    fi
  done

  local step_label="${COX_MENU_STEP:-}"
  if [ -z "$step_label" ]; then
    step_label="$(menu_step_label_for_prompt "$prompt")"
  fi
  local detail="${COX_NEXT_MENU_DETAIL:-}"
  COX_NEXT_MENU_DETAIL=""
  COX_MENU_HELP_SHOWN=1

  local render_panel
  render_panel() {
    local width
    width="$(ui_terminal_width)"
    menu_tty_printf '\033[?25l\033[2J\033[3J\033[H'
    ui_box_top "CodeXchange" "$width" > /dev/tty
    ui_box_line "" "$width" > /dev/tty
    ui_box_line_styled "$prompt" "$width" "\033[1;38;5;75m" > /dev/tty
    ui_box_line "" "$width" > /dev/tty
    if [ -n "$detail" ]; then
      ui_box_line_styled "Hint" "$width" "\033[2m" > /dev/tty
      ui_box_line_styled "$detail" "$width" "\033[2m" > /dev/tty
      ui_box_line "" "$width" > /dev/tty
    fi
    for i in "${!options[@]}"; do
      IFS='|' read -r value label status <<< "${options[$i]}"
      if [ "$i" -eq "$selected" ]; then
        menu_render_option_line "1" "$value" "$label" "$status" "$width"
      else
        menu_render_option_line "0" "$value" "$label" "$status" "$width"
      fi
    done
    ui_box_line "" "$width" > /dev/tty
    ui_box_line_styled "Use ↑/↓ or j/k to move, Enter to select, Backspace to previous step." "$width" "\033[2m" > /dev/tty
    ui_step_footer "$step_label" "$width" > /dev/tty
  }

  local key
  menu_tty_printf '\033[?25l'
  while true; do
    render_panel

    IFS= read -rsn1 key < /dev/tty || {
      menu_tty_printf '\033[?25h\n'
      printf '%s\n' "$default"
      return 0
    }

    case "$key" in
      "")
        IFS='|' read -r value _label _status <<< "${options[$selected]}"
        menu_tty_printf '\033[?25h\n'
        printf '%s\n' "$value"
        return 0
        ;;
      $'\x1b')
        local rest=""
        IFS= read -rsn2 -t 0.15 rest < /dev/tty || true
        case "$rest" in
          "[A") selected=$(( (selected + count - 1) % count )) ;;
          "[B") selected=$(( (selected + 1) % count )) ;;
          *) ;;
        esac
        ;;
      k|K)
        selected=$(( (selected + count - 1) % count ))
        ;;
      j|J)
        selected=$(( (selected + 1) % count ))
        ;;
      $'\x7f'|$'\b')
        menu_tty_printf '\033[?25h\n'
        printf '%s\n' "__COX_BACK__"
        return 0
        ;;
      *) ;;
    esac
  done
}




read_yes_no_menu() {
  local prompt="$1"
  local default="${2:-N}"
  local yes_label="Yes"
  local no_label="No"

  case "$default" in
    y|Y|yes|YES|Yes)
      read_menu_choice_from_tty "$prompt" "Y" "Y|$yes_label|plain" "N|$no_label|plain"
      ;;
    *)
      read_menu_choice_from_tty "$prompt" "N" "Y|$yes_label|plain" "N|$no_label|plain"
      ;;
  esac
}

choose_installer_language() {
  local existing="${COX_INSTALL_LOCALE:-}"
  if [ -z "$existing" ]; then
    existing="$(env_file_value COX_LOCALE)"
  fi
  case "$existing" in
    zh|zh-CN|zh_CN|cn|CN) existing="zh-CN" ;;
    *) existing="en" ;;
  esac
  if [ "$NON_INTERACTIVE" = "1" ]; then
    COX_INSTALL_LOCALE="$existing"
    return 0
  fi
  COX_MENU_STEP="Step 1/5"
  local chosen=""
  chosen="$(read_menu_choice_from_tty "Choose your language / 选择语言" "$existing" \
    "en|English|plain" \
    "zh-CN|简体中文|plain")"
  COX_MENU_STEP=""
  case "$chosen" in
    __COX_BACK__|"") chosen="$existing" ;;
  esac
  COX_INSTALL_LOCALE="$chosen"
}

port_is_available() {
  local port="$1"
  "$PYTHON_BIN" - "$port" <<'PYCOX_PORT_CHECK'
import socket, sys
port = int(sys.argv[1])
ok = "0"
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
try:
    s.bind(("127.0.0.1", port))
    ok = "1"
except OSError:
    ok = "0"
finally:
    s.close()
print(ok)
PYCOX_PORT_CHECK
}

choose_available_port() {
  local preferred="$1"
  local avoid="${2:-}"
  local port=""
  case "$preferred" in
    ''|*[!0-9]*) preferred=8000 ;;
  esac
  port="$preferred"
  while [ "$port" -lt $((preferred + 80)) ]; do
    if [ -n "$avoid" ] && [ "$port" = "$avoid" ]; then
      port=$((port + 1))
      continue
    fi
    if [ "$(port_is_available "$port")" = "1" ]; then
      printf '%s\n' "$port"
      return 0
    fi
    port=$((port + 1))
  done
  printf '%s\n' "$preferred"
}

provider_option_line() {
  local number="$1"
  local name="$2"
  local status="$3"
  if [ "$status" = "supported" ]; then
    printf '  \033[1;32m%s\033[0m %s  \033[1;32mSupported\033[0m\n' "$number." "$name"
  else
    printf '  \033[2m%s %s  Unsupported\033[0m\n' "$number." "$name"
  fi
}



model_api_validation_url_for_provider() {
  local provider="$1"
  local base_url="$2"
  case "$provider" in
    deepseek) printf '%s\n' "https://api.deepseek.com/user/balance" ;;
    *) printf '%s\n' "${base_url%/}/models" ;;
  esac
}

model_api_validation_method_for_provider() {
  local provider="$1"
  case "$provider" in
    deepseek) printf '%s\n' "deepseek_balance" ;;
    *) printf '%s\n' "openai_compatible_models" ;;
  esac
}

reset_model_api_validation_summary() {
  MODEL_API_VALIDATION_STATUS="not_run"
  MODEL_API_VALIDATION_METHOD=""
  MODEL_API_VALIDATION_URL=""
  MODEL_API_VALIDATION_ERROR=""
}

record_model_api_validation_summary() {
  local status="$1"
  local error="${2:-}"
  MODEL_API_VALIDATION_STATUS="$status"
  MODEL_API_VALIDATION_METHOD="$(model_api_validation_method_for_provider "${PROMPTED_MODEL_PROVIDER:-}" "${PROMPTED_MODEL_BASE_URL:-}")"
  MODEL_API_VALIDATION_URL="$(model_api_validation_url_for_provider "${PROMPTED_MODEL_PROVIDER:-}" "${PROMPTED_MODEL_BASE_URL:-}")"
  MODEL_API_VALIDATION_ERROR="$error"
}


model_api_provider_display_label() {
  local provider="${PROMPTED_MODEL_PROVIDER:-${RESOLVED_MODEL_PROVIDER:-}}"
  local custom_name="${PROMPTED_CUSTOM_PROVIDER_NAME:-${RESOLVED_MODEL_PROVIDER_DISPLAY_NAME:-}}"
  if [ "$provider" = "custom" ]; then
    if [ -n "$custom_name" ]; then
      printf '%s\n' "$custom_name"
    else
      printf '%s\n' "Custom Provider"
    fi
    return 0
  fi
  case "$provider" in
    deepseek) printf '%s\n' "DeepSeek Provider" ;;
    kimi) printf '%s\n' "Kimi Provider" ;;
    zhipu|zhipu-coding) printf '%s\n' "ZhipuAI Provider" ;;
    zai|zai-coding) printf '%s\n' "Z.AI Provider" ;;
    qwen-beijing|qwen-singapore|qwen-us) printf '%s\n' "Qwen Provider" ;;  # qwen-us remains a current explicit regional provider
    "") printf '%s\n' "Provider" ;;
    *) printf '%s\n' "$provider" ;;
  esac
}

model_api_provider_type_label() {
  case "${PROMPTED_MODEL_PROVIDER:-${RESOLVED_MODEL_PROVIDER:-}}" in
    custom) printf '%s\n' "Custom OpenAI-compatible" ;;
    deepseek) printf '%s\n' "DeepSeek official" ;;
    custom) printf '%s\n' "Built-in OpenAI-compatible" ;;
    kimi|zhipu|zhipu-coding|zai|zai-coding|qwen-beijing|qwen-singapore|qwen-us) printf '%s\n' "Built-in native adapter" ;;
    *) printf '%s\n' "Model API" ;;
  esac
}

write_model_provider_registry() {
  local provider="$1"
  local display_name="$2"
  local base_url="$3"
  local model_name="$4"
  local api_key="$5"

  if [ "$provider" != "custom" ]; then
    return 0
  fi
  if [ -z "$display_name" ] || [ -z "$base_url" ] || [ -z "$model_name" ]; then
    return 0
  fi

  if [ "$DRY_RUN" = "1" ]; then
    printf '+ write %q with custom provider registry entry for %q\n' "$MODEL_PROVIDER_REGISTRY_FILE" "$display_name" >> "$INSTALL_LOG"
    return 0
  fi

  mkdir -p "$(dirname "$MODEL_PROVIDER_REGISTRY_FILE")"
  "$PYTHON_BIN" - "$MODEL_PROVIDER_REGISTRY_FILE" "$display_name" "$base_url" "$model_name" "$api_key" <<'PYCOX_MODEL_PROVIDER_REGISTRY_P219A1'
import json
import os
import re
import sys
from pathlib import Path

path = Path(sys.argv[1])
display_name = sys.argv[2].strip() or "Custom Provider"
base_url = sys.argv[3].strip().rstrip("/")
model_name = sys.argv[4].strip()
api_key = sys.argv[5]

def slug(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip().lower()).strip("-._")
    return text or "custom-provider"

provider_id = slug(display_name)
if path.exists():
    try:
        data = json.loads(path.read_text(encoding="utf-8") or "{}")
    except Exception:
        data = {}
else:
    data = {}

if not isinstance(data, dict):
    data = {}
providers = data.setdefault("providers", {})
if not isinstance(providers, dict):
    providers = {}
    data["providers"] = providers

entry = providers.get(provider_id)
if not isinstance(entry, dict):
    entry = {}
models = entry.get("models")
if not isinstance(models, list):
    models = []
if model_name and model_name not in models:
    models.append(model_name)

entry.update({
    "id": provider_id,
    "type": "custom_openai_compatible",
    "display_name": display_name,
    "base_url": base_url,
    "active_model": model_name,
    "models": models,
})
if api_key:
    entry["api_key"] = api_key

providers[provider_id] = entry
data["version"] = 1
data["active_provider"] = provider_id
path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
os.chmod(path, 0o600)
PYCOX_MODEL_PROVIDER_REGISTRY_P219A1
}

model_api_key_state_label() {
  if [ -n "${PROMPTED_API_KEY:-}" ]; then
    printf '%s\n' "configured, hidden"
  else
    printf '%s\n' "empty"
  fi
}

review_model_api_config() {
  local key_state
  key_state="$(model_api_key_state_label)"
  COX_NEXT_MENU_DETAIL="Provider: ${PROMPTED_MODEL_PROVIDER:-<unset>} · Base URL: ${PROMPTED_MODEL_BASE_URL:-<empty>} · Model: ${PROMPTED_MODEL_NAME:-<empty>} · API key: ${key_state}. API key material is never displayed."
  read_menu_choice_from_tty "Review model API configuration" "1" \
    "1|Continue with this configuration|supported" \
    "2|Edit base URL|custom" \
    "3|Edit model name|custom" \
    "4|Edit API key|custom" \
    "5|Back to provider selection|experimental" \
    "0|Skip model API|skip"
}



custom_provider_registry_count() {
  "$PYTHON_BIN" - "$MODEL_PROVIDER_REGISTRY_FILE" <<'PYCOX_CUSTOM_PROVIDER_COUNT_P219A2'
import json
import sys
from pathlib import Path
path = Path(sys.argv[1])
try:
    data = json.loads(path.read_text(encoding="utf-8") or "{}") if path.exists() else {}
except Exception:
    data = {}
providers = data.get("providers") if isinstance(data, dict) else {}
if not isinstance(providers, dict):
    providers = {}
print(len(providers))
PYCOX_CUSTOM_PROVIDER_COUNT_P219A2
}

custom_provider_registry_hint() {
  "$PYTHON_BIN" - "$MODEL_PROVIDER_REGISTRY_FILE" <<'PYCOX_CUSTOM_PROVIDER_HINT_P219A2'
import json
import sys
from pathlib import Path
path = Path(sys.argv[1])
try:
    data = json.loads(path.read_text(encoding="utf-8") or "{}") if path.exists() else {}
except Exception:
    data = {}
providers = data.get("providers") if isinstance(data, dict) else {}
if not isinstance(providers, dict) or not providers:
    print("No saved custom providers yet.")
else:
    active = data.get("active_provider")
    parts = []
    for key, entry in providers.items():
        if not isinstance(entry, dict):
            continue
        marker = "*" if key == active else "-"
        name = entry.get("display_name") or key
        model = entry.get("active_model") or "<no active model>"
        parts.append(f"{marker} {name}: {model}")
    print("; ".join(parts[:6]))
PYCOX_CUSTOM_PROVIDER_HINT_P219A2
}

prompt_custom_provider_mode() {
  local count
  local choice
  count="$(custom_provider_registry_count 2>/dev/null || printf '0')"

  if [ "${count:-0}" = "0" ]; then
    COX_NEXT_MENU_DETAIL="No saved custom providers yet. Add a new custom provider first."
    choice="$(read_menu_choice_from_tty "Custom provider setup" "2" \
      "2|Add new custom provider|custom" \
      "0|Back to provider selection|skip")"
    case "$choice" in
      __COX_BACK__|0|back|Back) printf '%s\n' "back" ;;
      2|new|add) printf '%s\n' "new" ;;
      *) printf '%s\n' "new" ;;
    esac
    return 0
  fi

  COX_NEXT_MENU_DETAIL="$(custom_provider_registry_hint 2>/dev/null || printf 'Saved custom providers are available.')"
  choice="$(read_menu_choice_from_tty "Custom provider setup" "1" \
    "1|Use existing custom provider|supported" \
    "2|Add new custom provider|custom" \
    "3|Add model to existing provider|custom" \
    "4|Switch active model|custom" \
    "0|Back to provider selection|skip")"
  case "$choice" in
    __COX_BACK__) printf '%s\n' "back" ;;
    0|back|Back) printf '%s\n' "back" ;;
    1|use|existing) printf '%s\n' "use" ;;
    2|new|add) printf '%s\n' "new" ;;
    3|add-model) printf '%s\n' "add_model" ;;
    4|switch|switch-model) printf '%s\n' "switch_model" ;;
    *) printf '%s\n' "use" ;;
  esac
}

prompt_existing_custom_provider_name_field() {
  local options_file
  local default_choice
  local choice
  local options=()
  options_file="/tmp/codexchange-custom-provider-menu-options-$$.txt"

  if ! "$PYTHON_BIN" - "$MODEL_PROVIDER_REGISTRY_FILE" > "$options_file" <<'PYCOX_CUSTOM_PROVIDER_MENU_OPTIONS_P219A6'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
try:
    data = json.loads(path.read_text(encoding="utf-8") or "{}") if path.exists() else {}
except Exception:
    data = {}
providers = data.get("providers") if isinstance(data, dict) else {}
if not isinstance(providers, dict) or not providers:
    raise SystemExit(2)

active = data.get("active_provider")
ordered = []
if active in providers:
    ordered.append(active)
for key in sorted(providers):
    if key not in ordered:
        ordered.append(key)

default = ordered[0]
print(default)
for key in ordered:
    entry = providers.get(key)
    if not isinstance(entry, dict):
        continue
    display = str(entry.get("display_name") or key)
    model = str(entry.get("active_model") or "<no active model>")
    suffix = " · active" if key == active else ""
    label = f"{display} · {model}{suffix}"
    label = label.replace("\n", " ").replace("|", "/")
    print(f"{key}|{label}|custom")
PYCOX_CUSTOM_PROVIDER_MENU_OPTIONS_P219A6
  then
    rm -f "$options_file"
    warn "No saved custom providers yet. Add a new custom provider first."
    return 30
  fi

  default_choice="$(sed -n '1p' "$options_file" 2>/dev/null || true)"
  if command -v mapfile >/dev/null 2>&1; then
    mapfile -t options < <(tail -n +2 "$options_file")
  else
    while IFS= read -r line; do
      options+=("$line")
    done <<EOF
$(tail -n +2 "$options_file")
EOF
  fi
  rm -f "$options_file"

  if [ "${#options[@]}" -eq 0 ]; then
    warn "No saved custom providers yet. Add a new custom provider first."
    return 30
  fi

  COX_NEXT_MENU_DETAIL="$(custom_provider_registry_hint 2>/dev/null || printf 'Select a saved custom provider.')"
  choice="$(read_menu_choice_from_tty "Custom Provider · Select provider" "$default_choice" \
    "${options[@]}" \
    "0|Back to custom provider setup|skip")"

  case "$choice" in
    __COX_BACK__|0|back|Back)
      return 20
      ;;
  esac

  PROMPTED_CUSTOM_PROVIDER_NAME="$(clean_tty_input_value "$choice")"
  if [ -z "$PROMPTED_CUSTOM_PROVIDER_NAME" ]; then
    warn "Provider selection is required."
    return 30
  fi
  return 0
}

prompt_existing_custom_provider_model_field() {
  local value=""
  COX_INPUT_TITLE="$(model_api_provider_display_label) · Active model"
  COX_INPUT_STEP="Step 2/5"
  COX_INPUT_DETAIL="Model name is sent to cox/upstream and must exactly match this provider. Leave empty to keep the provider's active model."
  value="$(read_from_tty "Model name" "${PROMPTED_MODEL_NAME:-}")"
  COX_INPUT_TITLE=""
  COX_INPUT_STEP=""
  COX_INPUT_DETAIL=""
  if [ "$value" = "__COX_BACK__" ]; then
    return 20
  fi
  PROMPTED_MODEL_NAME="$(clean_tty_input_value "$value")"
  return 0
}

apply_custom_provider_from_registry() {
  local mode="$1"
  local provider_name="$2"
  local model_name="${3:-}"
  local assign_file
  assign_file="/tmp/codexchange-custom-provider-registry-assign-$$.sh"
  "$PYTHON_BIN" - "$MODEL_PROVIDER_REGISTRY_FILE" "$mode" "$provider_name" "$model_name" > "$assign_file" <<'PYCOX_APPLY_CUSTOM_PROVIDER_P219A2'
import json
import os
import re
import shlex
import sys
from pathlib import Path

path = Path(sys.argv[1])
mode = sys.argv[2]
provider_name = (sys.argv[3] or "").strip()
model_name = (sys.argv[4] or "").strip()

def slug(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip().lower()).strip("-._")
    return text or "custom-provider"

try:
    data = json.loads(path.read_text(encoding="utf-8") or "{}") if path.exists() else {}
except Exception:
    data = {}
providers = data.get("providers") if isinstance(data, dict) else {}
if not isinstance(providers, dict):
    providers = {}

provider_id = slug(provider_name)
entry = providers.get(provider_id)
if not isinstance(entry, dict):
    raise SystemExit(2)

models = entry.get("models")
if not isinstance(models, list):
    models = []
entry["models"] = models

if mode in {"add_model", "switch_model"}:
    if not model_name:
        raise SystemExit(3)
    if model_name not in models:
        models.append(model_name)
    entry["active_model"] = model_name
elif mode == "use":
    if model_name:
        if model_name not in models:
            models.append(model_name)
        entry["active_model"] = model_name

active_model = entry.get("active_model") or (models[0] if models else "")
if not active_model:
    raise SystemExit(4)
entry["active_model"] = active_model
data["active_provider"] = provider_id
data["version"] = 1
providers[provider_id] = entry
data["providers"] = providers
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
os.chmod(path, 0o600)

assignments = {
    "PROMPTED_MODEL_PROVIDER": "custom",
    "PROMPTED_CUSTOM_PROVIDER_NAME": str(entry.get("display_name") or provider_name),
    "PROMPTED_MODEL_BASE_URL": str(entry.get("base_url") or ""),
    "PROMPTED_MODEL_NAME": str(entry.get("active_model") or active_model),
}
api_key = str(entry.get("api_key") or "")
if api_key:
    assignments["PROMPTED_API_KEY"] = api_key
for key, value in assignments.items():
    print(f"{key}={shlex.quote(value)}")
PYCOX_APPLY_CUSTOM_PROVIDER_P219A2
  local rc=$?
  if [ "$rc" -ne 0 ]; then
    rm -f "$assign_file"
    return "$rc"
  fi
  # shellcheck disable=SC1090
  . "$assign_file"
  rm -f "$assign_file"
  record_model_api_validation_summary "registry_selected"
  return 0
}

prompt_custom_provider_name_field() {
  local value=""
  COX_INPUT_TITLE="Custom Provider · Provider name"
  COX_INPUT_STEP="Step 2/5"
  COX_INPUT_DETAIL="Provider name is only for your display and switching; it is not sent upstream."
  value="$(read_from_tty "Provider name" "${PROMPTED_CUSTOM_PROVIDER_NAME:-${COX_CUSTOM_PROVIDER_NAME:-}}")"
  COX_INPUT_TITLE=""
  COX_INPUT_STEP=""
  COX_INPUT_DETAIL=""
  if [ "$value" = "__COX_BACK__" ]; then
    return 20
  fi
  PROMPTED_CUSTOM_PROVIDER_NAME="$(clean_tty_input_value "$value")"
  if [ -z "$PROMPTED_CUSTOM_PROVIDER_NAME" ]; then
    PROMPTED_CUSTOM_PROVIDER_NAME="Custom Provider"
  fi
  return 0
}

prompt_model_base_url_field() {
  local value=""
  COX_INPUT_TITLE="$(model_api_provider_display_label) · Base URL"
  COX_INPUT_STEP="Step 2/5"
  COX_INPUT_DETAIL="Base URL is sent to cox/upstream. /chat/completions is normalized to /v1."
  value="$(read_from_tty "Base URL" "${PROMPTED_MODEL_BASE_URL:-${COX_MODEL_BASE_URL:-}}")"
  COX_INPUT_TITLE=""
  COX_INPUT_STEP=""
  COX_INPUT_DETAIL=""
  if [ "$value" = "__COX_BACK__" ]; then
    return 20
  fi
  PROMPTED_MODEL_BASE_URL="$(normalize_openai_base_url "$value")"
  return 0
}

prompt_model_name_field() {
  local value=""
  while true; do
    COX_INPUT_TITLE="$(model_api_provider_display_label) · Model name"
    COX_INPUT_STEP="Step 2/5"
    COX_INPUT_DETAIL="Model name is sent to cox/upstream and must exactly match this provider. Example: your-model-id"
    value="$(read_from_tty "Model name" "${PROMPTED_MODEL_NAME:-${COX_MODEL:-}}")"
    COX_INPUT_TITLE=""
    COX_INPUT_STEP=""
    COX_INPUT_DETAIL=""
    if [ "$value" = "__COX_BACK__" ]; then
      return 20
    fi
    PROMPTED_MODEL_NAME="$(clean_tty_input_value "$value")"
    if [ -z "$PROMPTED_MODEL_NAME" ] || is_valid_model_name_value "$PROMPTED_MODEL_NAME"; then
      return 0
    fi
    warn "Invalid upstream model name: enter only the model id, not a URL, path, whitespace-containing value, or API key. Example: your-model-id"
    PROMPTED_MODEL_NAME=""
  done
}

prompt_model_api_key_field() {
  local attempts=0
  local empty_attempts=0
  local candidate=""
  local existing_api_key="${COX_MODEL_API_KEY:-}"
  local prompt_hint="optional; press Enter three times to skip"
  if [ -n "$existing_api_key" ]; then
    prompt_hint="optional, type a new key to replace the existing one"
  fi

  while [ "$attempts" -lt 3 ]; do
    COX_INPUT_TITLE="$(model_api_provider_display_label) · API key"
    COX_INPUT_STEP="Step 2/5"
    COX_INPUT_DETAIL="Provider: $(model_api_provider_display_label) · Model: ${PROMPTED_MODEL_NAME:-<unset>}"
    candidate="$(read_secret_from_tty "API key" "$existing_api_key" "$prompt_hint")"
    COX_INPUT_TITLE=""
    COX_INPUT_STEP=""
    COX_INPUT_DETAIL=""

    if [ "$candidate" = "__COX_BACK__" ]; then
      return 20
    fi
    if [ "$candidate" = "__COX_KEEP_EXISTING__" ]; then
      PROMPTED_API_KEY="$existing_api_key"
      record_model_api_validation_summary "kept_existing"
      ok "Existing model API key kept for provider: $PROMPTED_MODEL_PROVIDER"
      return 0
    fi
    if [ -z "$candidate" ]; then
      empty_attempts=$((empty_attempts + 1))
      if [ "$empty_attempts" -ge 3 ]; then
        PROMPTED_API_KEY=""
        record_model_api_validation_summary "skipped" "empty_api_key"
        warn "Model API key skipped after three empty submissions. Configure later with: cox config set-model --provider $PROMPTED_MODEL_PROVIDER"
        return 0
      fi
      warn "No key entered (${empty_attempts}/3). Press Enter three times to skip this configuration, or Backspace on empty input to return to model."
      continue
    fi

    ok "Received ${#candidate} characters. Validating provider: $PROMPTED_MODEL_PROVIDER"
    empty_attempts=0
    if test_model_api_key "$PROMPTED_MODEL_PROVIDER" "$candidate" "$PROMPTED_MODEL_BASE_URL"; then
      PROMPTED_API_KEY="$candidate"
      record_model_api_validation_summary "ok"
      ok "Model API key validated for provider: $PROMPTED_MODEL_PROVIDER"
      return 0
    fi

    attempts=$((attempts + 1))
    record_model_api_validation_summary "error" "validation_failed"
    warn "Model API key validation failed (${attempts}/3). Paste it again, press Backspace on empty input to edit model, or press Enter three times to skip."
  done

  PROMPTED_API_KEY=""
  record_model_api_validation_summary "error" "validation_failed"
  warn "Model API key was not saved because validation failed. Configure later with: cox config set-model --provider $PROMPTED_MODEL_PROVIDER"
  return 0
}

choose_model_provider_family() {
  local family=""
  sub_title "Model providers"
  printf '  %s\n' "Only DeepSeek is marked Supported. Other implemented model providers are Experimental until full Codex workflow validation passes."
  family="$(read_menu_choice_from_tty "Select model provider family" "1" \
    "1|DeepSeek|supported" \
    "2|Kimi / Moonshot|experimental" \
    "3|ZhipuAI / BigModel|experimental" \
    "4|Z.AI|experimental" \
    "5|Qwen / DashScope|experimental" \
    "6|Mimo|unsupported" \
    "7|Baichuan|unsupported" \
    "8|Other OpenAI-compatible server|custom" \
    "0|Skip|skip")"
  if [ "$family" = "__COX_BACK__" ]; then
    return 20
  fi

  case "$family" in
    1|deepseek|DeepSeek|DEEPSEEK)
      PROMPTED_MODEL_PROVIDER="deepseek"
      ;;
    2|kimi|moonshot|Kimi|Moonshot|KIMI|MOONSHOT)
      PROMPTED_MODEL_PROVIDER="kimi"
      ;;
    3|zhipu|zhipuai|bigmodel|ZHIPU|ZHIPUAI|BIGMODEL)
      local endpoint=""
      endpoint="$(read_menu_choice_from_tty "Select ZhipuAI / BigModel endpoint" "1" \
        "1|Domestic Token API / general endpoint|experimental" \
        "2|Domestic Coding Plan API endpoint|experimental" \
        "0|Back / skip|skip")"
      if [ "$endpoint" = "__COX_BACK__" ]; then
        return 21
      fi
      case "$endpoint" in
        1|token|general|domestic) PROMPTED_MODEL_PROVIDER="zhipu" ;;
        2|coding|coding-plan|coding_plan) PROMPTED_MODEL_PROVIDER="zhipu-coding" ;;
        *) warn "Model API skipped. Configure later with: cox config set-model --provider zhipu"; return 30 ;;
      esac
      ;;
    4|zai|z.ai|ZAI|Z.AI)
      local endpoint=""
      endpoint="$(read_menu_choice_from_tty "Select Z.AI endpoint" "1" \
        "1|International Token API / general endpoint|experimental" \
        "2|International Coding Plan API endpoint|experimental" \
        "0|Back / skip|skip")"
      if [ "$endpoint" = "__COX_BACK__" ]; then
        return 21
      fi
      case "$endpoint" in
        1|token|general|international) PROMPTED_MODEL_PROVIDER="zai" ;;
        2|coding|coding-plan|coding_plan) PROMPTED_MODEL_PROVIDER="zai-coding" ;;
        *) warn "Model API skipped. Configure later with: cox config set-model --provider zai"; return 30 ;;
      esac
      ;;
    5|qwen|dashscope|aliyun|QWEN|DASHSCOPE)
      local endpoint=""
      endpoint="$(read_menu_choice_from_tty "Select Qwen / DashScope endpoint" "1" \
        "1|Beijing pay-as-you-go OpenAI-compatible endpoint|experimental" \
        "2|Singapore pay-as-you-go OpenAI-compatible endpoint|experimental" \
        "3|US Virginia pay-as-you-go OpenAI-compatible endpoint|experimental" \
        "0|Back / skip|skip")"
      if [ "$endpoint" = "__COX_BACK__" ]; then
        return 21
      fi
      case "$endpoint" in
        1|beijing|cn) PROMPTED_MODEL_PROVIDER="qwen-beijing" ;;
        2|singapore|sg) PROMPTED_MODEL_PROVIDER="qwen-singapore" ;;
        3|us|us-virginia|virginia) PROMPTED_MODEL_PROVIDER="qwen-us" ;;
        *) warn "Model API skipped. Configure later with: cox config set-model --provider qwen-beijing"; return 30 ;;
      esac
      ;;
    6|mimo|Mimo|MIMO)
      warn "Mimo is listed for visibility but is currently unsupported in the guided installer. Configure manually as custom only if you have an OpenAI-compatible endpoint."
      return 30
      ;;
    7|baichuan|Baichuan|BAICHUAN)
      warn "Baichuan is listed for visibility but is currently unsupported in the guided installer. Configure manually as custom only if you have an OpenAI-compatible endpoint."
      return 30
      ;;
    8|custom|other|Other|CUSTOM)
      PROMPTED_MODEL_PROVIDER="custom"
      ;;
    0|skip|Skip|SKIP)
      warn "Model API skipped. Configure later with: cox config set-model --provider deepseek|kimi|zhipu|zhipu-coding|zai|zai-coding|qwen-beijing|qwen-singapore|qwen-us|custom"
      return 30
      ;;
    *)
      warn "Selected model provider is currently unsupported. Configure as custom only if it is OpenAI-compatible."
      return 30
      ;;
  esac
  return 0
}

prompt_deepseek_api_key() {
  PROMPTED_API_KEY=""
  PROMPTED_MODEL_PROVIDER=""
  PROMPTED_MODEL_BASE_URL=""
  PROMPTED_MODEL_NAME=""
  PROMPTED_CUSTOM_PROVIDER_NAME=""
  reset_model_api_validation_summary

  if [ "$NON_INTERACTIVE" = "1" ]; then
    # Existing installer env file is the migration source of truth for non-interactive upgrades.
    # Ambient shell variables can belong to another HOME/session; use them only when no env file value exists.
    PROMPTED_API_KEY="$(env_file_value COX_MODEL_API_KEY)"
    if [ -z "$PROMPTED_API_KEY" ]; then
      PROMPTED_API_KEY="${COX_MODEL_API_KEY:-}"
    fi
    PROMPTED_MODEL_PROVIDER="$(env_file_value COX_MODEL_PROVIDER)"
    PROMPTED_CUSTOM_PROVIDER_NAME="$(env_file_value COX_CUSTOM_PROVIDER_NAME)"
    if [ -z "$PROMPTED_MODEL_PROVIDER" ]; then
      PROMPTED_MODEL_PROVIDER="${COX_MODEL_PROVIDER:-}"
    fi
    if [ -z "$PROMPTED_MODEL_PROVIDER" ]; then
      PROMPTED_MODEL_PROVIDER="deepseek"
    fi
    PROMPTED_MODEL_BASE_URL="$(env_file_value COX_MODEL_BASE_URL)"
    if [ -z "$PROMPTED_MODEL_BASE_URL" ]; then
      PROMPTED_MODEL_BASE_URL="${COX_MODEL_BASE_URL:-}"
    fi
    if [ -z "$PROMPTED_MODEL_BASE_URL" ]; then
      PROMPTED_MODEL_BASE_URL="$(model_api_base_url "$PROMPTED_MODEL_PROVIDER")"
    fi
    PROMPTED_MODEL_NAME="$(env_file_value COX_MODEL)"
    if [ -z "$PROMPTED_MODEL_NAME" ]; then
      PROMPTED_MODEL_NAME="${COX_MODEL:-}"
    fi
    if [ -z "$PROMPTED_MODEL_NAME" ]; then
      PROMPTED_MODEL_NAME="$(model_api_default_model "$PROMPTED_MODEL_PROVIDER")"
    fi
    record_model_api_validation_summary "not_run" "non_interactive"
    return 0
  fi

  local configure=""
  local provider_rc=0
  local field_step="provider"
  local field_rc=0

  COX_NEXT_MENU_DETAIL="Model API is required for Codex/DeepSeek requests. Choose Yes to configure a provider now, or No to skip and configure later with cox config wizard."

  configure="$(read_yes_no_menu "Configure model API now?" "Y")"

  COX_NEXT_MENU_DETAIL=""
  case "$configure" in
    __COX_BACK__) return 20 ;;
    n|N|no|NO|No)
      record_model_api_validation_summary "skipped" "user_skipped_model_api"
      warn "Model API skipped. Configure later with: cox config wizard"
      return 0
      ;;
  esac

  while true; do
    case "$field_step" in
      provider)
        PROMPTED_API_KEY=""
        PROMPTED_MODEL_PROVIDER=""
        PROMPTED_MODEL_BASE_URL=""
        PROMPTED_MODEL_NAME=""
        PROMPTED_CUSTOM_PROVIDER_NAME=""
        reset_model_api_validation_summary

        choose_model_provider_family
        provider_rc=$?
        case "$provider_rc" in
          0)
            PROMPTED_MODEL_BASE_URL="$(model_api_base_url "$PROMPTED_MODEL_PROVIDER")"
            PROMPTED_MODEL_NAME="$(model_api_default_model "$PROMPTED_MODEL_PROVIDER")"
            if [ "$PROMPTED_MODEL_PROVIDER" = "custom" ]; then
              field_step="custom_mode"
            else
              field_step="api_key"
            fi
            ;;
          20) return 20 ;;
          21) field_step="provider" ;;
          30)
            record_model_api_validation_summary "skipped" "user_skipped_model_api"
            return 0
            ;;
          *) return "$provider_rc" ;;
        esac
        ;;

      custom_mode)
        local custom_mode=""
        custom_mode="$(prompt_custom_provider_mode)"
        case "$custom_mode" in
          back)
            field_step="provider"
            ;;
          use)
            if prompt_existing_custom_provider_name_field; then
              if apply_custom_provider_from_registry "use" "$PROMPTED_CUSTOM_PROVIDER_NAME" ""; then
                show_model_api_validation_hold
                return 0
              fi
              warn "Saved custom provider was not found. Add it again or choose a different provider."
            elif [ "$?" = "20" ]; then
              field_step="custom_mode"
            fi
            ;;
          add_model|switch_model)
            if prompt_existing_custom_provider_name_field; then
              prompt_existing_custom_provider_model_field
              field_rc=$?
              if [ "$field_rc" = "20" ]; then
                field_step="custom_mode"
                continue
              fi
              if apply_custom_provider_from_registry "$custom_mode" "$PROMPTED_CUSTOM_PROVIDER_NAME" "$PROMPTED_MODEL_NAME"; then
                show_model_api_validation_hold
                return 0
              fi
              warn "Could not update saved custom provider/model."
            elif [ "$?" = "20" ]; then
              field_step="custom_mode"
            fi
            ;;
          new|*)
            field_step="provider_name"
            ;;
        esac
        ;;

      provider_name)
        prompt_custom_provider_name_field
        field_rc=$?
        if [ "$field_rc" = "20" ]; then
          field_step="custom_mode"
          continue
        fi
        field_step="base_url"
        ;;

      base_url)
        prompt_model_base_url_field
        field_rc=$?
        if [ "$field_rc" = "20" ]; then
          field_step="provider_name"
          continue
        fi
        field_step="model"
        ;;

      model)
        prompt_model_name_field
        field_rc=$?
        if [ "$field_rc" = "20" ]; then
          if [ "$PROMPTED_MODEL_PROVIDER" = "custom" ]; then
            field_step="base_url"
          else
            field_step="provider"
          fi
          continue
        fi
        if [ -z "$PROMPTED_MODEL_NAME" ]; then
          warn "Model API skipped because model name is empty."
          PROMPTED_API_KEY=""
          PROMPTED_MODEL_PROVIDER=""
          PROMPTED_MODEL_BASE_URL=""
          record_model_api_validation_summary "skipped" "empty_model"
          return 0
        fi
        field_step="api_key"
        ;;

      api_key)
        if [ "$PROMPTED_MODEL_PROVIDER" = "custom" ] && { [ -z "$PROMPTED_MODEL_BASE_URL" ] || [ -z "$PROMPTED_MODEL_NAME" ]; }; then
          warn "Custom model API requires both base URL and model name."
          field_step="base_url"
          continue
        fi

        prompt_model_api_key_field
        field_rc=$?
        if [ "$field_rc" = "20" ]; then
          if [ "$PROMPTED_MODEL_PROVIDER" = "custom" ]; then
            field_step="model"
          else
            field_step="provider"
          fi
          continue
        fi
        show_model_api_validation_hold
        return 0
        ;;

      *)
        field_step="provider"
        ;;
    esac
  done
}

prompt_serpapi_api_key() {
  PROMPTED_SERPAPI_API_KEY=""
  PROMPTED_WEB_SEARCH_PROVIDER=""

  if [ "$NON_INTERACTIVE" = "1" ]; then
    PROMPTED_WEB_SEARCH_PROVIDER="$(env_file_value COX_WEB_SEARCH_PROVIDER)"
    if [ -z "$PROMPTED_WEB_SEARCH_PROVIDER" ]; then
      PROMPTED_WEB_SEARCH_PROVIDER="${COX_WEB_SEARCH_PROVIDER:-serpapi}"
    fi
    case "$PROMPTED_WEB_SEARCH_PROVIDER" in
      tavily) PROMPTED_SERPAPI_API_KEY="$(env_file_value TAVILY_API_KEY)" ;;
      exa) PROMPTED_SERPAPI_API_KEY="$(env_file_value EXA_API_KEY)" ;;
      firecrawl) PROMPTED_SERPAPI_API_KEY="$(env_file_value FIRECRAWL_API_KEY)" ;;
      *) PROMPTED_SERPAPI_API_KEY="$(env_file_value SERPAPI_API_KEY)" ;;
    esac
    if [ -z "$PROMPTED_SERPAPI_API_KEY" ]; then
      PROMPTED_SERPAPI_API_KEY="${SERPAPI_API_KEY:-${TAVILY_API_KEY:-${EXA_API_KEY:-${FIRECRAWL_API_KEY:-}}}}"
    fi
    return 0
  fi

  local configure=""
  COX_NEXT_MENU_DETAIL="Web search is optional. Choose Yes to configure a search provider for managed tool routing, or No to skip and configure later with cox config set-web-search-api-key."
  configure="$(read_yes_no_menu "Configure web search API now?" "N")"
  COX_NEXT_MENU_DETAIL=""
  case "$configure" in
    __COX_BACK__) return 20 ;;
    y|Y|yes|YES|Yes) ;;
    *)
      warn "Web search API skipped. Configure later with: cox config set-web-search-api-key --provider serpapi|tavily|exa|firecrawl"
      return 0
      ;;
  esac

  sub_title "Web search providers"
  local provider=""
  local prompt=""
  provider="$(read_menu_choice_from_tty "Select web search provider" "1" \
    "1|SerpAPI|supported" \
    "2|Tavily|supported" \
    "3|Exa|supported" \
    "4|Firecrawl|supported" \
    "5|Bing Web Search|unsupported" \
    "6|Google Programmable Search|unsupported" \
    "7|Other custom server|unsupported" \
    "0|Skip|skip")"
  if [ "$provider" = "__COX_BACK__" ]; then
    return 20
  fi
  case "$provider" in
    1|serpapi|SerpAPI|SERPAPI) PROMPTED_WEB_SEARCH_PROVIDER="serpapi"; prompt="SerpAPI API key" ;;
    2|tavily|Tavily|TAVILY) PROMPTED_WEB_SEARCH_PROVIDER="tavily"; prompt="Tavily API key" ;;
    3|exa|Exa|EXA) PROMPTED_WEB_SEARCH_PROVIDER="exa"; prompt="Exa API key" ;;
    4|firecrawl|Firecrawl|FIRECRAWL) PROMPTED_WEB_SEARCH_PROVIDER="firecrawl"; prompt="Firecrawl API key" ;;
    7|other|Other|OTHER|custom|Custom)
      warn "Custom web search servers are configured manually."
      return 0
      ;;
    0|skip|Skip|SKIP)
      warn "Web search API skipped. Configure later with: cox config set-web-search-api-key --provider serpapi|tavily|exa|firecrawl"
      return 0
      ;;
    *)
      warn "Selected web search provider is currently unsupported."
      return 0
      ;;
  esac

  local attempts=0
  local empty_attempts=0
  local candidate=""
  while [ "$attempts" -lt 3 ]; do
    COX_INPUT_TITLE="Web search API key"
    COX_INPUT_STEP="Step 3/5"
    COX_INPUT_DETAIL="Provider: $PROMPTED_WEB_SEARCH_PROVIDER"
    candidate="$(read_secret_from_tty "$prompt" "" "optional; press Enter three times to skip")"
    COX_INPUT_TITLE=""
    COX_INPUT_STEP=""
    COX_INPUT_DETAIL=""
    if [ -z "$candidate" ]; then
      empty_attempts=$((empty_attempts + 1))
      if [ "$empty_attempts" -ge 3 ]; then
        PROMPTED_SERPAPI_API_KEY=""
        warn "Web search API skipped after three empty submissions. Configure later with: cox config set-web-search-api-key --provider $PROMPTED_WEB_SEARCH_PROVIDER"
        return 0
      fi
      warn "No key entered (${empty_attempts}/3). Press Enter three times to skip this configuration."
      continue
    fi

    ok "Received ${#candidate} characters. Validating provider: $PROMPTED_WEB_SEARCH_PROVIDER"
    empty_attempts=0
    if test_web_search_api_key "$PROMPTED_WEB_SEARCH_PROVIDER" "$candidate"; then
      PROMPTED_SERPAPI_API_KEY="$candidate"
      ok "Web search API key validated for provider: $PROMPTED_WEB_SEARCH_PROVIDER"
      return 0
    fi

    attempts=$((attempts + 1))
    warn "Web search API key validation failed (${attempts}/3). Paste it again, or press Enter three times to skip."
  done

  PROMPTED_SERPAPI_API_KEY=""
  warn "Web search API key was not saved because validation failed. Configure later with: cox config set-web-search-api-key --provider $PROMPTED_WEB_SEARCH_PROVIDER"
}

prompt_image_generation_api_key() {
  PROMPTED_IMAGE_API_KEY=""
  PROMPTED_IMAGE_PROVIDER=""

  if [ "$NON_INTERACTIVE" = "1" ]; then
    PROMPTED_IMAGE_PROVIDER="$(env_file_value COX_IMAGE_PROVIDER)"
    if [ -z "$PROMPTED_IMAGE_PROVIDER" ]; then
      PROMPTED_IMAGE_PROVIDER="${COX_IMAGE_PROVIDER:-zhipu}"
    fi
    PROMPTED_IMAGE_API_KEY="$(env_file_value COX_IMAGE_API_KEY)"
    if [ -z "$PROMPTED_IMAGE_API_KEY" ]; then
      PROMPTED_IMAGE_API_KEY="${COX_IMAGE_API_KEY:-${DASHSCOPE_API_KEY:-${STABILITY_API_KEY:-${FAL_KEY:-}}}}"
    fi
    return 0
  fi

  local configure=""
  COX_NEXT_MENU_DETAIL="Image generation is optional. Choose Yes to configure an image provider for managed tool routing, or No to skip and configure later with cox config set-image-api-key."
  configure="$(read_yes_no_menu "Configure image generation API now?" "N")"
  COX_NEXT_MENU_DETAIL=""
  case "$configure" in
    __COX_BACK__) return 20 ;;
    y|Y|yes|YES|Yes) ;;
    *)
      warn "Image generation API skipped. Configure later with: cox config set-image-api-key --provider zhipu|zai|qwen_image_beijing|qwen_image_singapore|stability|fal"
      return 0
      ;;
  esac

  sub_title "Image generation providers"
  local family=""
  local prompt=""
  COX_NEXT_MENU_DETAIL="Live image validation will generate one safe test image and may consume provider credits. Choose Skip to avoid unexpected charges. Test image path will be shown under /tmp."
  family="$(read_menu_choice_from_tty "Select image generation provider family" "1" \
    "1|ZhipuAI / BigModel|supported" \
    "2|Z.AI / CogView|supported" \
    "3|Qwen Image / DashScope|supported" \
    "4|Stability AI|supported" \
    "5|fal.ai|supported" \
    "6|Kolors|unsupported" \
    "7|Hunyuan Image|unsupported" \
    "8|Volcengine Ark|unsupported" \
    "9|Other custom server|unsupported" \
    "0|Skip|skip")"
  if [ "$family" = "__COX_BACK__" ]; then
    return 20
  fi
  case "$family" in
    1|zhipu|ZHIPU|zhipuai|ZHIPUAI|bigmodel|BIGMODEL) PROMPTED_IMAGE_PROVIDER="zhipu"; prompt="ZhipuAI / BigModel image API key" ;;
    2|glm|GLM|cogview|CogView|zai|ZAI|z.ai|Z.AI) PROMPTED_IMAGE_PROVIDER="zai"; prompt="Z.AI image API key" ;;
    3|qwen|Qwen|qwen_image|qwen-image|dashscope|DashScope|aliyun)
      local region=""
      region="$(read_menu_choice_from_tty "Select Qwen Image / DashScope region" "1" \
        "1|Beijing multimodal generation endpoint|supported" \
        "2|Singapore multimodal generation endpoint|supported" \
        "3|US Virginia endpoint; qwen-image-2.0-pro currently unavailable|model unavailable" \
        "4|Germany Frankfurt endpoint; qwen-image-2.0-pro currently unavailable|model unavailable" \
        "0|Back / skip|skip")"
      case "$region" in
        1|beijing|cn) PROMPTED_IMAGE_PROVIDER="qwen_image_beijing"; prompt="DashScope Beijing API key" ;;
        2|singapore|sg) PROMPTED_IMAGE_PROVIDER="qwen_image_singapore"; prompt="DashScope Singapore API key" ;;
        3|us|us-virginia|virginia|4|germany|frankfurt|de)
          warn "Selected Qwen Image region is listed for clarity, but qwen-image-2.0-pro is currently unavailable there. Choose Beijing or Singapore."
          return 0
          ;;
        *) warn "Image generation API skipped. Configure later with: cox config set-image-api-key --provider qwen_image_beijing"; return 0 ;;
      esac
      ;;
    4|stability|Stability|stability_ai|stable_image) PROMPTED_IMAGE_PROVIDER="stability"; prompt="Stability AI API key" ;;
    5|fal|Fal|FAL|fal_ai|fal.ai) PROMPTED_IMAGE_PROVIDER="fal"; prompt="fal.ai API key" ;;
    9|other|Other|OTHER|custom|Custom)
      warn "Custom image generation servers are configured manually."
      return 0
      ;;
    0|skip|Skip|SKIP)
      warn "Image generation API skipped. Configure later with: cox config set-image-api-key --provider zhipu|zai|qwen_image_beijing|qwen_image_singapore|stability|fal"
      return 0
      ;;
    *)
      warn "Selected image generation provider is currently unsupported."
      return 0
      ;;
  esac

  local attempts=0
  local empty_attempts=0
  local candidate=""
  while [ "$attempts" -lt 3 ]; do
    COX_INPUT_TITLE="Image generation API key"
    COX_INPUT_STEP="Step 4/5"
    COX_INPUT_DETAIL="Provider: $PROMPTED_IMAGE_PROVIDER · Live validation may consume provider credits."
    candidate="$(read_secret_from_tty "$prompt" "" "optional; press Enter three times to skip")"
    COX_INPUT_TITLE=""
    COX_INPUT_STEP=""
    COX_INPUT_DETAIL=""
    if [ -z "$candidate" ]; then
      empty_attempts=$((empty_attempts + 1))
      if [ "$empty_attempts" -ge 3 ]; then
        PROMPTED_IMAGE_API_KEY=""
        warn "Image generation API skipped after three empty submissions. Configure later with: cox config set-image-api-key --provider $PROMPTED_IMAGE_PROVIDER"
        return 0
      fi
      warn "No key entered (${empty_attempts}/3). Press Enter three times to skip this configuration."
      continue
    fi

    ok "Received ${#candidate} characters. Creating one safe test image with provider: $PROMPTED_IMAGE_PROVIDER"
    empty_attempts=0
    if test_image_api_key "$PROMPTED_IMAGE_PROVIDER" "$candidate"; then
      PROMPTED_IMAGE_API_KEY="$candidate"
      ok "Image generation API key validated by live image generation for provider: $PROMPTED_IMAGE_PROVIDER"
      if [ -n "${LAST_IMAGE_VALIDATION_ARTIFACT:-}" ]; then
        printf '  \033[2mtest image saved: %s\033[0m\n' "$LAST_IMAGE_VALIDATION_ARTIFACT"
      fi
      return 0
    fi

    attempts=$((attempts + 1))
    warn "Live image validation failed (${attempts}/3). Paste it again, or press Enter three times to skip."
  done

  PROMPTED_IMAGE_API_KEY=""
  warn "Image generation API key was not saved because live validation failed. Configure later with: cox config set-image-api-key --provider $PROMPTED_IMAGE_PROVIDER"
}

backup_local_file_before_overwrite() {
  local path="$1"
  local label="$2"

  if [ "$DRY_RUN" = "1" ]; then
    if [ -e "$path" ]; then
      printf '+ backup existing %q before overwriting %s\n' "$path" "$label" >> "$INSTALL_LOG"
    fi
    return 0
  fi

  if [ ! -e "$path" ]; then
    return 0
  fi

  mkdir -p "$LOCAL_BACKUP_DIR"
  local safe_name
  safe_name="$(printf '%s' "$path" | sed 's#[/:]#_#g')"
  local backup_path="$LOCAL_BACKUP_DIR/${safe_name}.$(date +%Y%m%d_%H%M%S)"
  cp -p "$path" "$backup_path"
  printf '+ backup existing %q to %q before overwriting %s\n' "$path" "$backup_path" "$label" >> "$INSTALL_LOG"
  warn "Backed up existing $label to: $backup_path"
}


is_codexchange_managed_local_bin() {
  local path="$1"
  local kind="$2"

  if [ ! -e "$path" ]; then
    return 0
  fi
  if [ ! -f "$path" ]; then
    return 1
  fi

  case "$kind" in
    codex)
      grep -qE 'CodeXchange codex wrapper|COX_COMMAND|codexchange|start_cox_profile' "$path" 2>/dev/null
      ;;
    cox)
      grep -qE 'CodeXchange|codexchange|\.venv/bin/cox' "$path" 2>/dev/null
      ;;
    *)
      return 1
      ;;
  esac
}

require_safe_local_bin_overwrite() {
  local path="$1"
  local label="$2"
  local kind="$3"
  local force_value="$4"

  if [ "$DRY_RUN" = "1" ]; then
    if [ -e "$path" ] && ! is_codexchange_managed_local_bin "$path" "$kind"; then
      printf '+ would require confirmation before overwriting unknown %q for %s\n' "$path" "$label" >> "$INSTALL_LOG"
    fi
    return 0
  fi

  if [ ! -e "$path" ]; then
    return 0
  fi

  if is_codexchange_managed_local_bin "$path" "$kind"; then
    backup_local_file_before_overwrite "$path" "$label"
    return 0
  fi

  backup_local_file_before_overwrite "$path" "$label"

  if [ "$force_value" = "1" ]; then
    warn "Forcing overwrite of unknown existing $label after backup: $path"
    return 0
  fi

  if [ "$NON_INTERACTIVE" = "1" ]; then
    warn "Refusing to overwrite unknown existing $label in non-interactive mode: $path"
    warn "The existing file was backed up under: $LOCAL_BACKUP_DIR"
    warn "Re-run with the explicit force variable only if this file should be replaced."
    case "$kind" in
      codex) warn "To force this replacement: COX_FORCE_CODEX_WRAPPER=1" ;;
      cox) warn "To force this replacement: COX_FORCE_COX_WRAPPER=1" ;;
    esac
    return 1
  fi

  printf 'Existing %s at %s is not recognized as CodeXchange-managed. Overwrite after backup? [y/N] ' "$label" "$path" >&2
  local answer
  read -r answer
  case "$answer" in
    y|Y|yes|YES)
      warn "Overwriting unknown existing $label after user confirmation: $path"
      return 0
      ;;
    *)
      warn "Keeping unknown existing $label unchanged: $path"
      return 1
      ;;
  esac
}


env_file_value() {
  local key="$1"

  if [ ! -f "$ENV_FILE" ]; then
    printf '%s
' ""
    return 0
  fi

  "$PYTHON_BIN" - "$ENV_FILE" "$key" <<'PYENV'
import shlex
import sys
from pathlib import Path

path = Path(sys.argv[1])
target = sys.argv[2]
try:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
except FileNotFoundError:
    print("")
    raise SystemExit(0)

for line in lines:
    line = line.strip()
    if not line or line.startswith("#") or not line.startswith("export "):
        continue
    body = line[len("export "):]
    if "=" not in body:
        continue
    key, value = body.split("=", 1)
    if key.strip() != target:
        continue
    try:
        parts = shlex.split("x=" + value)
        if parts and parts[0].startswith("x="):
            print(parts[0][2:])
        else:
            print(value.strip("'\""))
    except Exception:
        print(value.strip("'\""))
    break
else:
    print("")
PYENV
}

choose_shell_profile_file() {
  if [ -n "${COX_SHELL_PROFILE:-}" ]; then
    printf '%s\n' "$COX_SHELL_PROFILE"
    return 0
  fi

  case "$(basename "${SHELL:-}")" in
    zsh) printf '%s\n' "$HOME/.zshrc" ;;
    bash) printf '%s\n' "$HOME/.bashrc" ;;
    *) printf '%s\n' "$HOME/.profile" ;;
  esac
}

ensure_one_shell_profile_integration() {
  local profile_file="$1"
  local label="$2"

  if [ -z "$profile_file" ]; then
    return 0
  fi

  mkdir -p "$(dirname "$profile_file")"
  touch "$profile_file"

  if grep -q "CodeXchange environment" "$profile_file" 2>/dev/null && grep -Fq "$BIN_DIR" "$profile_file" 2>/dev/null; then
    ok "Shell profile already contains CodeXchange environment: $label"
    return 0
  fi

  cat >> "$profile_file" <<EOF

# CodeXchange environment
if [ -d "$BIN_DIR" ]; then
  case ":\$PATH:" in
    *:"$BIN_DIR":*) ;;
    *) export PATH="$BIN_DIR:\$PATH" ;;
  esac
fi
if [ -f "$ENV_FILE" ]; then
  . "$ENV_FILE"
fi
EOF

  ok "Shell profile updated: $profile_file"
}

ensure_shell_profile_integration() {
  if [ "$INSTALL_SHELL_PROFILE" != "1" ]; then
    ok "Shell profile update skipped"
    return 0
  fi

  local profile_file
  profile_file="$(choose_shell_profile_file)"
  SHELL_PROFILE_FILE="$profile_file"

  ensure_one_shell_profile_integration "$profile_file" "selected shell"
  if [ "$profile_file" != "$HOME/.profile" ]; then
    ensure_one_shell_profile_integration "$HOME/.profile" "login shell"
  fi
  if [ "$profile_file" != "$HOME/.bashrc" ] && [ -f "$HOME/.bashrc" ]; then
    ensure_one_shell_profile_integration "$HOME/.bashrc" "interactive bash"
  fi

  case ":$PATH:" in
    *:"$BIN_DIR":*) ;;
    *) export PATH="$BIN_DIR:$PATH" ;;
  esac
  if [ -f "$ENV_FILE" ]; then
    # shellcheck disable=SC1090
    . "$ENV_FILE"
  fi
}

post_install_entrypoint_diagnostics() {
  if [ "$DRY_RUN" = "1" ]; then
    return 0
  fi

  local expected_cox="$BIN_DIR/cox"
  local expected_codex="$BIN_DIR/codex"
  local actual_cox=""
  local actual_codex=""

  actual_cox="$(command -v cox 2>/dev/null || true)"
  actual_codex="$(command -v codex 2>/dev/null || true)"

  if [ "$actual_cox" != "$expected_cox" ]; then
    warn "Current shell does not resolve cox to the CodeXchange wrapper: ${actual_cox:-<not found>}"
    warn "Open a new terminal, or run: export PATH=\"$BIN_DIR:\$PATH\""
  fi

  if [ "$INSTALL_CODEX_WRAPPER" = "1" ] && [ -x "$expected_codex" ] && [ "$actual_codex" != "$expected_codex" ]; then
    warn "Current shell does not resolve codex to the CodeXchange wrapper: ${actual_codex:-<not found>}"
    warn "Open a new terminal, or run: export PATH=\"$BIN_DIR:\$PATH\""
  fi

  if ! command -v node >/dev/null 2>&1; then
    warn "Node.js is not on PATH. Codex CLI requires Node.js; CodeXchange does not install or patch Node automatically."
    warn "Install Node.js/Codex CLI, then rerun the installer or run: cox profile refresh-wrapper"
  fi
}

model_catalog_json_value() {
  local catalog_path="$INSTALL_DIR/experiments/model-catalog/cox-proxy-models.json"
  if [ ! -f "$catalog_path" ]; then
    printf '%s\n' ""
    return 0
  fi
  json_string "$catalog_path"
}

ensure_managed_resources_git_excluded() {
  if ! command -v git >/dev/null 2>&1; then
    return 0
  fi
  if [ ! -d "$INSTALL_DIR" ]; then
    return 0
  fi

  local exclude_path
  exclude_path="$(git -C "$INSTALL_DIR" rev-parse --git-path info/exclude 2>> "$INSTALL_LOG" || true)"
  if [ -z "$exclude_path" ]; then
    return 0
  fi
  case "$exclude_path" in
    /*) ;;
    *) exclude_path="$INSTALL_DIR/$exclude_path" ;;
  esac

  mkdir -p "$(dirname "$exclude_path")" 2>> "$INSTALL_LOG" || return 0
  touch "$exclude_path" 2>> "$INSTALL_LOG" || return 0

  local changed="0"
  local pattern
  for pattern in "resources/" "resources/tokenizers/"; do
    if ! grep -Fxq "$pattern" "$exclude_path" 2>/dev/null; then
      printf '%s\n' "$pattern" >> "$exclude_path" || return 0
      changed="1"
    fi
  done
  if [ "$changed" = "1" ]; then
    printf '+ Managed resource git excludes updated: %s\n' "$exclude_path" >> "$INSTALL_LOG"
  fi
  return 0
}

sync_deepseek_tokenizer_resource() {
  if [ "$DRY_RUN" = "1" ]; then
    printf '+ COX_INSTALL_DIR=%q COX_TOKENIZER_RESOURCE_DIR=%q %q tokenizer sync deepseek --json --resource-dir %q\n' "$INSTALL_DIR" "$INSTALL_DIR/resources/tokenizers" "$INSTALL_DIR/.venv/bin/cox" "$INSTALL_DIR/resources/tokenizers" >> "$INSTALL_LOG"
    ok "Provider tokenizer resource sync planned: deepseek"
    return 0
  fi

  printf '  ... Provider tokenizer resource synced: deepseek\n'
  if env COX_INSTALL_DIR="$INSTALL_DIR" COX_TOKENIZER_RESOURCE_DIR="$INSTALL_DIR/resources/tokenizers" \
    "$INSTALL_DIR/.venv/bin/cox" tokenizer sync deepseek --json --resource-dir "$INSTALL_DIR/resources/tokenizers" >> "$INSTALL_LOG" 2>&1; then
    ok "Provider tokenizer resource synced: deepseek"
    return 0
  fi

  warn "Provider tokenizer resource sync failed for deepseek. Run: cox tokenizer sync deepseek --json"
  return 1
}

write_env_file() {
  local stable_port="$1"
  local thinking_port="$2"
  local api_key="$3"
  local web_search_key="$4"
  local image_api_key="$5"

  local final_api_key="$api_key"
  local final_web_search_key="$web_search_key"
  local final_image_api_key="$image_api_key"
  local final_web_search_provider="${PROMPTED_WEB_SEARCH_PROVIDER:-}"
  local final_image_provider="${PROMPTED_IMAGE_PROVIDER:-}"
  local final_model_provider="${PROMPTED_MODEL_PROVIDER:-}"
  local final_model_base_url="${PROMPTED_MODEL_BASE_URL:-}"
  local final_model_name="${PROMPTED_MODEL_NAME:-}"
  local final_custom_provider_name="${PROMPTED_CUSTOM_PROVIDER_NAME:-}"

  if [ -z "$final_api_key" ]; then
    final_api_key="$(env_file_value COX_MODEL_API_KEY)"
  fi
  if [ -z "$final_model_provider" ]; then
    final_model_provider="$(env_file_value COX_MODEL_PROVIDER)"
  fi
  if [ -z "$final_custom_provider_name" ]; then
    final_custom_provider_name="$(env_file_value COX_CUSTOM_PROVIDER_NAME)"
  fi
  if [ -z "$final_model_provider" ]; then
    final_model_provider="deepseek"
  fi
  if [ -z "$final_model_base_url" ]; then
    final_model_base_url="$(env_file_value COX_MODEL_BASE_URL)"
  fi
  if [ -z "$final_model_base_url" ]; then
    final_model_base_url="$(model_api_base_url "$final_model_provider")"
  fi
  if [ -z "$final_model_name" ]; then
    final_model_name="$(env_file_value COX_MODEL)"
  fi
  if [ -z "$final_model_name" ]; then
    final_model_name="$(model_api_default_model "$final_model_provider")"
  fi
  if [ -z "$final_model_base_url" ]; then
    final_model_base_url="https://api.deepseek.com"
  fi
  if [ -z "$final_model_name" ]; then
    final_model_name="deepseek-v4-pro"
  fi

  if [ "$final_model_provider" = "custom" ] && [ -z "$final_custom_provider_name" ]; then
    final_custom_provider_name="Custom Provider"
  fi

  RESOLVED_MODEL_PROVIDER="$final_model_provider"
  RESOLVED_MODEL_BASE_URL="$final_model_base_url"
  RESOLVED_MODEL_NAME="$final_model_name"
  RESOLVED_MODEL_PROVIDER_DISPLAY_NAME="${final_custom_provider_name:-$final_model_provider}"
  RESOLVED_MODEL_PROVIDER_TYPE="$(PROMPTED_MODEL_PROVIDER="$final_model_provider" model_api_provider_type_label)"

  if [ -z "$final_web_search_provider" ]; then
    final_web_search_provider="$(env_file_value COX_WEB_SEARCH_PROVIDER)"
  fi
  if [ -z "$final_web_search_provider" ]; then
    final_web_search_provider="serpapi"
  fi
  if [ -z "$final_web_search_key" ]; then
    case "$final_web_search_provider" in
      tavily) final_web_search_key="$(env_file_value TAVILY_API_KEY)" ;;
      *) final_web_search_key="$(env_file_value SERPAPI_API_KEY)" ;;
    esac
  fi
  if [ -z "$final_image_provider" ]; then
    final_image_provider="$(env_file_value COX_IMAGE_PROVIDER)"
  fi
  if [ -z "$final_image_provider" ]; then
    final_image_provider="zhipu"
  fi
  if [ -z "$final_image_api_key" ]; then
    final_image_api_key="$(env_file_value COX_IMAGE_API_KEY)"
  fi

  if [ "$DRY_RUN" = "1" ]; then
    printf '+ mkdir -p %q
' "$(dirname "$ENV_FILE")" >> "$INSTALL_LOG"
    printf '+ write %q with chmod 600
' "$ENV_FILE" >> "$INSTALL_LOG"
    ok "Local env file written"
    return 0
  fi

  mkdir -p "$(dirname "$ENV_FILE")"
  backup_local_file_before_overwrite "$ENV_FILE" "local env file"

  {
    printf '# codexchange local environment
'
    printf '# Generated by scripts/install.sh
'
    printf 'export COX_MODEL_API_KEY=%q
' "$final_api_key"
    printf 'export COX_MODEL_BASE_URL=%q
' "$final_model_base_url"
    printf 'export COX_MODEL_PROVIDER=%q
' "$final_model_provider"
    printf 'export COX_CUSTOM_PROVIDER_NAME=%q
' "$final_custom_provider_name"
    printf 'export COX_MODEL_PROVIDER_REGISTRY=%q
' "$MODEL_PROVIDER_REGISTRY_FILE"
    printf 'export COX_INSTALL_DIR=%q
' "$INSTALL_DIR"
    printf 'export COX_TOKENIZER_RESOURCE_DIR=%q
' "$INSTALL_DIR/resources/tokenizers"
    printf 'export COX_PORT=%q
' "$stable_port"
    printf 'export COX_THINKING_PORT=%q
' "$thinking_port"
    printf 'export COX_MODEL=%q
' "$final_model_name"
    printf 'export COX_REASONING_EFFORT=%q
' "max"
    printf 'export COX_FORCE_MODEL=%q
' "1"
    if [ -n "${INSTALL_TARGET_INTERNAL_VERSION:-}" ]; then
      printf 'export COX_INTERNAL_VERSION=%q
' "$INSTALL_TARGET_INTERNAL_VERSION"
    fi
    if [ -n "${INSTALL_TARGET_COMMIT:-}" ]; then
      printf 'export COX_PUBLIC_COMMIT=%q
' "$INSTALL_TARGET_COMMIT"
      printf 'export COX_INTERNAL_COMMIT=%q
' "$INSTALL_TARGET_COMMIT"
    fi
    printf 'export COX_TOOL_MAX_ROUNDS=%q
' "6"
    printf 'export COX_COMPACT_POLICY=%q
' "adaptive"
    printf 'export COX_AGENT_LIVENESS_GUARD=%q
' "1"
    printf 'export COX_AGENT_LIVENESS_JUDGE_ENABLED=%q
' "1"
    printf 'export COX_AGENT_LIVENESS_JUDGE_MODEL=%q
' "v4-flash-no-thinking"
    printf 'export COX_CODEX_TOOL_PROTOCOL_INSTRUCTION=%q
' "1"
    if [ -n "$final_web_search_key" ]; then
      printf 'export COX_TOOL_BRIDGE=%q
' "1"
      printf 'export COX_WEB_SEARCH_PROVIDER=%q
' "$final_web_search_provider"
      printf 'export COX_WEB_SEARCH_MAX_RESULTS=%q
' "6"
      printf 'export COX_WEB_SEARCH_TIMEOUT_SECONDS=%q
' "12.5"
      case "$final_web_search_provider" in
        tavily)
          printf 'export TAVILY_API_KEY=%q
' "$final_web_search_key"
          ;;
        exa)
          printf 'export EXA_API_KEY=%q
' "$final_web_search_key"
          ;;
        firecrawl)
          printf 'export FIRECRAWL_API_KEY=%q
' "$final_web_search_key"
          ;;
        *)
          printf 'export SERPAPI_API_KEY=%q
' "$final_web_search_key"
          ;;
      esac
    fi
    if [ -n "$final_image_api_key" ]; then
      printf 'export COX_TOOL_BRIDGE=%q
' "1"
      printf 'export COX_IMAGE_PROVIDER=%q
' "$final_image_provider"
      if [ "$final_image_provider" = "qwen_image" ] || [ "$final_image_provider" = "qwen_image_beijing" ] || [ "$final_image_provider" = "qwen_image_singapore" ]; then
        printf 'export COX_IMAGE_MODEL=%q
' "qwen-image-2.0-pro"
      elif [ "$final_image_provider" = "stability" ]; then
        printf 'export COX_IMAGE_MODEL=%q
' "stable-image-core"
      elif [ "$final_image_provider" = "fal" ]; then
        printf 'export COX_IMAGE_MODEL=%q
' "fal-ai/flux/schnell"
      else
        printf 'export COX_IMAGE_MODEL=%q
' "cogView-4-250304"
      fi
      printf 'export COX_IMAGE_SIZE=%q
' "1024x1024"
      printf 'export COX_IMAGE_N=%q
' "1"
      printf 'export COX_IMAGE_DOWNLOAD=%q
' "1"
      printf 'export COX_IMAGE_API_KEY=%q
' "$final_image_api_key"
    fi
  } > "$ENV_FILE"

  chmod 600 "$ENV_FILE"
  write_model_provider_registry "$final_model_provider" "$final_custom_provider_name" "$final_model_base_url" "$final_model_name" "$final_api_key"
  ok "Local env file written"
}

refresh_canonical_codex_wrapper_template() {
  local target template script_dir
  target="$BIN_DIR/codex"
  [ -f "$target" ] || return 0

  if ! grep -qE 'CodeXchange|codexchange|COX|PROFILE-AGNOSTIC RUNTIME AUTOSTART|EXECUTABLE WRAPPER DISPATCHER' "$target" 2>/dev/null; then
    warn "Existing codex command is not a CodeXchange-managed wrapper; canonical wrapper refresh skipped"
    return 0
  fi

  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  for template in \
    "$INSTALL_DIR/scripts/codex-wrapper.bash" \
    "$script_dir/codex-wrapper.bash" \
    "$PWD/scripts/codex-wrapper.bash"; do
    [ -f "$template" ] || continue
    cp "$template" "$target"
    chmod +x "$target"
    ok "codex wrapper refreshed from canonical scripts/codex-wrapper.bash"
    return 0
  done

  warn "Canonical scripts/codex-wrapper.bash not found; leaving existing codex wrapper in place"
  return 0
}

write_cox_wrapper() {
  if [ "$DRY_RUN" = "1" ]; then
    printf '+ mkdir -p %q\n' "$BIN_DIR" >> "$INSTALL_LOG"
    printf '+ write %q\n' "$BIN_DIR/cox" >> "$INSTALL_LOG"
    ok "cox command installed"
    return 0
  fi

  mkdir -p "$BIN_DIR"
  require_safe_local_bin_overwrite "$BIN_DIR/cox" "cox command wrapper" "cox" "$FORCE_COX_WRAPPER" || return 1

  cat > "$BIN_DIR/cox" <<EOF
#!/usr/bin/env bash
set -euo pipefail
ENV_FILE="\${COX_ENV_FILE:-$ENV_FILE}"
if [ -f "\$ENV_FILE" ]; then
  source "\$ENV_FILE"
fi
exec "$INSTALL_DIR/.venv/bin/cox" "\$@"
EOF

  chmod +x "$BIN_DIR/cox"
  ok "cox command installed"
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
  if [ -z "$real_codex" ]; then
    if ! command -v node >/dev/null 2>&1; then
      warn "Node.js is not on PATH. Codex CLI requires Node.js; CodeXchange will not install a recursive or blind codex wrapper."
      warn "Install Node.js/Codex CLI first, then rerun the installer. CodeXchange does not install or patch Node automatically."
    else
      warn "real codex command not found; Codex wrapper skipped. Install Codex CLI, set COX_REAL_CODEX, or rerun without --no-codex-wrapper after Codex is available."
    fi
    warn "CodeXchange install can continue without the optional Codex wrapper; cox and managed Codex profile installation remain complete."
    ok "Codex wrapper skipped"
    return 0
  fi

  local existing_wrapper_is_unknown="0"

  if [ -e "$wrapper_path" ] && ! is_codexchange_managed_local_bin "$wrapper_path" "codex"; then
    existing_wrapper_is_unknown="1"
  fi

  if [ "$DRY_RUN" = "1" ]; then
    require_safe_local_bin_overwrite "$wrapper_path" "codex command wrapper" "codex" "$FORCE_CODEX_WRAPPER"
    printf '+ write %q\n' "$wrapper_path" >> "$INSTALL_LOG"
    ok "Codex wrapper installed"
    return 0
  fi

  mkdir -p "$BIN_DIR"
  require_safe_local_bin_overwrite "$wrapper_path" "codex command wrapper" "codex" "$FORCE_CODEX_WRAPPER" || return 1

  if [ "$existing_wrapper_is_unknown" = "1" ]; then
    backup_path="$wrapper_path.codexchange.bak.$(date +%Y%m%d_%H%M%S)"
    mv "$wrapper_path" "$backup_path"
    if [ -z "$real_codex" ]; then
      real_codex="$backup_path"
    fi
  fi

  cat > "$wrapper_path" <<EOF
#!/usr/bin/env bash
# CodeXchange codex wrapper
set -euo pipefail

REAL_CODEX="$real_codex"
COX="\${COX_COMMAND:-$BIN_DIR/cox}"
if [ ! -x "\$COX" ] && [ -x "$INSTALL_DIR/.venv/bin/cox" ]; then
  COX="$INSTALL_DIR/.venv/bin/cox"
fi
ENV_FILE="\${COX_ENV_FILE:-$ENV_FILE}"

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

set_codexchange_terminal_title() {
  if [ ! -w /dev/tty ] && [ ! -t 1 ]; then
    return 0
  fi
  case "\${TERM:-}" in
    ""|dumb)
      return 0
      ;;
  esac

  local title="\${COX_TERMINAL_TITLE:-}"
  if [ -z "\$title" ]; then
    local emojis=("✨" "💞" "🐦‍🔥" "🔥" "❄️" "💫" "🌈" "⚡" "🌀" "🚀" "🍁" "🍒" "🧬" "🪄" "💎" "🦞" "🐋" "😻")
    local idx=\$((RANDOM % \${#emojis[@]}))
    title="\${emojis[\$idx]}CodeXchange"
    COX_TERMINAL_TITLE="\$title"
  fi

  if [ -w /dev/tty ]; then
    printf '\033]0;%s\007\033]2;%s\007' "\$title" "\$title" > /dev/tty 2>/dev/null || true
  else
    printf '\033]0;%s\007\033]2;%s\007' "\$title" "\$title" 2>/dev/null || true
  fi
}

COX_TITLE_KEEPER_PID=""

schedule_codexchange_terminal_title_refresh() {
  if [ ! -w /dev/tty ] && [ ! -t 1 ]; then
    return 0
  fi
  case "\${TERM:-}" in
    ""|dumb)
      return 0
      ;;
  esac

  (
    i=1
    max_seconds="\${COX_TITLE_KEEPER_SECONDS:-60}"
    interval_seconds="\${COX_TITLE_KEEPER_INTERVAL_SECONDS:-1}"
    while [ "\$i" -le "\$max_seconds" ]; do
      sleep "\$interval_seconds"
      set_codexchange_terminal_title
      i=\$((i + interval_seconds))
    done
  ) >/dev/null 2>&1 &
  COX_TITLE_KEEPER_PID="\$!"
}

stop_codexchange_terminal_title_keeper() {
  if [ -n "\${COX_TITLE_KEEPER_PID:-}" ]; then
    kill "\$COX_TITLE_KEEPER_PID" >/dev/null 2>&1 || true
    wait "\$COX_TITLE_KEEPER_PID" >/dev/null 2>&1 || true
    COX_TITLE_KEEPER_PID=""
  fi
}

codex_runtime_preflight() {
  if [ ! -x "\$REAL_CODEX" ]; then
    printf 'CodeXchange error: real Codex command is not executable: %s\n' "\$REAL_CODEX" >&2
    return 127
  fi

  if ! command -v node >/dev/null 2>&1; then
    if head -n 1 "\$REAL_CODEX" 2>/dev/null | grep -Eq '(^#!.*node|/env[[:space:]]+node)' || grep -qE 'node|@openai/codex|codex-cli' "\$REAL_CODEX" 2>/dev/null; then
      printf 'CodeXchange error: Codex CLI was found at %s, but Node.js is not on PATH.\n' "\$REAL_CODEX" >&2
      printf 'Install Node.js/Codex CLI first, then rerun the CodeXchange installer or: %s profile refresh-wrapper\n' "\$COX" >&2
      printf 'Boundary: CodeXchange detects this dependency but does not install or patch Node automatically.\n' >&2
      return 127
    fi
  fi
}

codex_requires_legacy_profile_tables() {
  local version_text=""
  version_text="\$("\$REAL_CODEX" --version 2>/dev/null || true)"
  case "\$version_text" in
    *" 0.130."*|*" 0.131."*|*" 0.132."*|*" 0.133."*|*"v0.130."*|*"v0.131."*|*"v0.132."*|*"v0.133."*)
      return 0
      ;;
  esac
  return 1
}

repair_codexchange_legacy_managed_profiles() {
  local thinking_port="\${COX_THINKING_PORT:-8001}"
  local model="\${COX_THINKING_MODEL:-\${COX_MODEL:-deepseek-v4-pro}}"
  local catalog_args=()
  local catalog=""

  catalog="\${COX_MODEL_CATALOG_JSON:-}"
  if [ -z "\$catalog" ]; then
    catalog="$INSTALL_DIR/experiments/model-catalog/cox-proxy-models.json"
  fi
  if [ -n "\$catalog" ] && [ -f "\$catalog" ]; then
    catalog_args=(--model-catalog-json "\$catalog")
  fi

  "\$COX" install-codex-profile \
    --name cox \
    --provider-name cox-proxy \
    --base-url "http://127.0.0.1:\${thinking_port}/v1" \
    --model "\$model" \
    --reasoning-effort xhigh \
    --profile-layout legacy_profile_tables \
    --no-backup \
    "\${catalog_args[@]}" >/dev/null
}

repair_codexchange_managed_profile_contract() {
  local profile_name="\$1"
  local status_json=""

  case "\$profile_name" in
    cox)
      ;;
    deepseek)
      printf 'CodeXchange error: profile "deepseek" is deprecated. Use: codex --profile cox\n' >&2
      return 2
      ;;
    *)
      return 0
      ;;
  esac

  if [ "\${COX_PROFILE_REPAIR_ON_LAUNCH:-1}" = "0" ]; then
    return 0
  fi

  if [ ! -x "\$COX" ]; then
    printf 'CodeXchange error: cox command is not executable: %s\n' "\$COX" >&2
    return 1
  fi

  if codex_requires_legacy_profile_tables; then
    if status_json="\$("\$COX" profile status "\$profile_name" --json 2>/dev/null)"; then
      if printf '%s' "\$status_json" | grep -q '"profile_source"[[:space:]]*:[[:space:]]*"legacy_profile_table"' \
        && ! printf '%s' "\$status_json" | grep -q '"model_conflict"[[:space:]]*:[[:space:]]*true'; then
        return 0
      fi
    fi

    if ! repair_codexchange_legacy_managed_profiles; then
      printf 'CodeXchange error: failed to repair legacy managed Codex profile before launch.\n' >&2
      printf 'Run for details: %s install-codex-profile --profile-layout legacy_profile_tables --name %s\n' "\$COX" "\$profile_name" >&2
      return 1
    fi
  else
    if ! "\$COX" profile repair --managed-only --json >/dev/null 2>&1; then
      printf 'CodeXchange error: failed to repair managed Codex profile before launch.\n' >&2
      printf 'Run for details: %s profile repair --managed-only --json\n' "\$COX" >&2
      return 1
    fi
  fi

  if ! status_json="\$("\$COX" profile status "\$profile_name" --json 2>/dev/null)"; then
    printf 'CodeXchange error: failed to verify managed Codex profile %s after repair.\n' "\$profile_name" >&2
    return 1
  fi

  if printf '%s' "\$status_json" | grep -q '"model_conflict"[[:space:]]*:[[:space:]]*true'; then
    if [ "\${COX_ALLOW_PROFILE_MODEL_CONFLICT:-0}" = "1" ]; then
      printf 'CodeXchange warning: managed Codex profile %s still has a model conflict; continuing because COX_ALLOW_PROFILE_MODEL_CONFLICT=1.\n' "\$profile_name" >&2
      return 0
    fi
    printf 'CodeXchange error: managed Codex profile %s still has a model conflict after repair.\n' "\$profile_name" >&2
    printf 'Refusing to launch Codex with a stale or incompatible profile. Run: %s profile status %s --json\n' "\$COX" "\$profile_name" >&2
    return 1
  fi
}

activate_codexchange_custom_provider_profile() {
  local profile_name="\$1"
  if [ -z "\$profile_name" ] || [ ! -x "\$COX" ]; then
    return 1
  fi
  "\$COX" config custom-provider use --name "\$profile_name" --no-profile-sync >/dev/null 2>&1
}

start_cox_profile() {
  local profile_name="\$1"
  local start_args=()
  local status_args=()

  if [ ! -x "\$COX" ]; then
    printf 'CodeXchange error: cox command is not executable: %s\n' "\$COX" >&2
    return 1
  fi

  case "\$profile_name" in
    cox)
      start_args=(start thinking)
      status_args=(status thinking)
      ;;
    *)
      return 0
      ;;
  esac

  if ! "\$COX" "\${start_args[@]}" >/dev/null 2>&1; then
    if ! "\$COX" "\${status_args[@]}" >/dev/null 2>&1; then
      printf 'CodeXchange error: failed to start cox for profile %s.\n' "\$profile_name" >&2
      printf 'Run for details: %s %s\n' "\$COX" "\${start_args[*]}" >&2
      return 1
    fi
    return 0
  fi

  if ! "\$COX" "\${status_args[@]}" >/dev/null 2>&1; then
    printf 'CodeXchange error: cox started but status check failed for profile %s.\n' "\$profile_name" >&2
    printf 'Run for details: %s %s\n' "\$COX" "\${status_args[*]}" >&2
    return 1
  fi
}

run_codexchange_codex() {
  case "\$profile" in
    deepseek)
      printf 'CodeXchange error: profile "deepseek" is deprecated. Use: codex --profile cox\n' >&2
      return 2
      ;;
    cox)
      repair_codexchange_managed_profile_contract "\$profile"
      start_cox_profile "\$profile"
      schedule_codexchange_terminal_title_refresh
      ;;
    "")
      ;;
    *)
      if activate_codexchange_custom_provider_profile "\$profile"; then
        start_cox_profile "cox"
        schedule_codexchange_terminal_title_refresh
      fi
      ;;
  esac

  if ! codex_runtime_preflight; then
    local preflight_rc=\$?
    stop_codexchange_terminal_title_keeper
    return "\$preflight_rc"
  fi

  set +e
  "\$REAL_CODEX" "\$@"
  local codex_rc=\$?
  set -e
  stop_codexchange_terminal_title_keeper
  return "\$codex_rc"
}

trap 'stop_codexchange_terminal_title_keeper' INT TERM HUP
run_codexchange_codex "\$@"
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
  step "Uninstalling CodeXchange integration"

  local wrapper_path="$BIN_DIR/codex"
  local backup_path=""

  if [ -f "$MANIFEST_FILE" ]; then
    # shellcheck disable=SC1090
    source "$MANIFEST_FILE" || true
    wrapper_path="${CODEX_WRAPPER_PATH:-$wrapper_path}"
    backup_path="${CODEX_WRAPPER_BACKUP:-}"
  fi

  if [ -x "$INSTALL_DIR/.venv/bin/cox" ]; then
    run_quiet "Codex profile removed: deepseek" "$INSTALL_DIR/.venv/bin/cox" uninstall-codex-profile --name deepseek --no-backup || true
    run_quiet "Codex profile removed: cox" "$INSTALL_DIR/.venv/bin/cox" uninstall-codex-profile --name cox --no-backup || true
  fi

  if [ -f "$wrapper_path" ] && grep -q "CodeXchange codex wrapper" "$wrapper_path" 2>/dev/null; then
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

  if [ -f "$BIN_DIR/cox" ] && grep -q "$INSTALL_DIR/.venv/bin/cox" "$BIN_DIR/cox" 2>/dev/null; then
    if [ "$DRY_RUN" = "1" ]; then
      printf '+ remove %q\n' "$BIN_DIR/cox" >> "$INSTALL_LOG"
    else
      rm -f "$BIN_DIR/cox"
    fi
    ok "cox wrapper removed"
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
  print_install_logs
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    --non-interactive) NON_INTERACTIVE=1 ;;
    --install-dir) INSTALL_DIR="$2"; shift ;;
    --repo-url) REPO_URL="$2"; shift ;;
    --install-ref) INSTALL_REF="$2"; shift ;;
    --bin-dir) BIN_DIR="$2"; shift ;;
    --config-dir) CONFIG_DIR="$2"; ENV_FILE="$CONFIG_DIR/env"; MANIFEST_FILE="$CONFIG_DIR/install-manifest.env"; MODEL_PROVIDER_REGISTRY_FILE="${COX_MODEL_PROVIDER_REGISTRY:-$CONFIG_DIR/model-providers.json}"; shift ;;
    --python-bin) PYTHON_BIN="$2"; PYTHON_BIN_EXPLICIT=1; shift ;;
    --env-file) ENV_FILE="$2"; shift ;;
    --no-codex-profile) INSTALL_CODEX_PROFILE=0 ;;
    --no-codex-wrapper) INSTALL_CODEX_WRAPPER=0 ;;
    --no-shell-profile) INSTALL_SHELL_PROFILE=0 ;;
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

printf 'Install ref: %s\n' "${INSTALL_REF:-<GitHub Latest Release>}" >> "$INSTALL_LOG"
printf 'Installer source: %s\n' "${COX_INSTALLER_SOURCE:-local script or current checkout}" >> "$INSTALL_LOG"
printf 'Repository source: %s\n' "$REPO_URL" >> "$INSTALL_LOG"

intro_width="$(ui_terminal_width)"
logo
ui_box_top "CodeXchange" "$intro_width"
ui_box_line "" "$intro_width"
ui_box_line_styled "Welcome" "$intro_width" "\033[1;38;5;75m"
ui_box_line "This guided installer will configure language, model API, web search, image generation, and Codex wrapper in a single flow." "$intro_width"
ui_box_line "" "$intro_width"
ui_box_line "[1] Language" "$intro_width"
ui_box_line "[2] Model API" "$intro_width"
ui_box_line "[3] Web search API" "$intro_width"
ui_box_line "[4] Image generation API" "$intro_width"
ui_box_line "[5] Codex wrapper" "$intro_width"
ui_box_line "" "$intro_width"
ui_box_line_styled "Press Enter to start guided setup." "$intro_width" "\033[1;38;5;75m"
ui_step_footer "Startup" "$intro_width"

if [ "$NON_INTERACTIVE" != "1" ] && [ -r /dev/tty ] && [ -w /dev/tty ]; then
  printf "\n  Press Enter to continue..." > /dev/tty
  IFS= read -r COX_START_SETUP < /dev/tty || true
  printf "\n" > /dev/tty
fi

COX_NEXT_MENU_DETAIL="Setup plan: Step 1 Language · Step 2 Model API · Step 3 Web search API · Step 4 Image generation API · Step 5 Codex wrapper. Repository, Python, cox, profile repair, and ports are handled automatically."
# Select Python before any env-backed guided setup helper uses env_file_value.
ensure_codexchange_python_bin
choose_installer_language

setup_width="$(ui_terminal_width)"
ui_box_top "CodeXchange" "$setup_width"
ui_box_line "" "$setup_width"
ui_box_line_styled "Setup plan" "$setup_width" "\033[1;38;5;75m"
ui_box_line "Step 1 Language is complete. The remaining prompts use the same guided UI." "$setup_width"
ui_box_line "" "$setup_width"
ui_box_line "[2] Model API" "$setup_width"
ui_box_line "[3] Web search API" "$setup_width"
ui_box_line "[4] Image generation API" "$setup_width"
ui_box_line "[5] Codex wrapper" "$setup_width"
ui_box_line "" "$setup_width"
ui_box_line "Proxy ports are selected automatically; occupied defaults are skipped." "$setup_width"
ui_step_footer "Step 1/5" "$setup_width"

step "Checking requirements"

ensure_codexchange_python_bin
PY_VERSION="$("$PYTHON_BIN" - <<'PY'
import sys
if sys.version_info < (3, 11):
    raise SystemExit("ERROR: Python >= 3.11 is required by the selected interpreter")
print(sys.version.split()[0])
PY
)"
ok "Python $PY_VERSION via $PYTHON_BIN"

if ! command -v git >/dev/null 2>&1; then
  echo "ERROR: git is required" >&2
  exit 1
fi
ok "Git available"

step "Guided configuration"

DEFAULT_STABLE_PORT="$(env_file_value COX_PORT)"
if [ -z "$DEFAULT_STABLE_PORT" ]; then
  DEFAULT_STABLE_PORT="${COX_PORT:-8000}"
fi
DEFAULT_THINKING_PORT="$(env_file_value COX_THINKING_PORT)"
if [ -z "$DEFAULT_THINKING_PORT" ]; then
  DEFAULT_THINKING_PORT="${COX_THINKING_PORT:-8001}"
fi
STABLE_PORT="$(choose_available_port "$DEFAULT_STABLE_PORT" "")"
THINKING_PORT="$(choose_available_port "$DEFAULT_THINKING_PORT" "$STABLE_PORT")"
ok "Proxy ports selected automatically: non-thinking=$STABLE_PORT, thinking=$THINKING_PORT"

guided_step=2
while true; do
  case "$guided_step" in
    2)
      if prompt_deepseek_api_key; then
        step_rc=0
      else
        step_rc=$?
      fi
      if [ "$step_rc" = "20" ]; then
        guided_step=2
        continue
      fi
      API_KEY="$PROMPTED_API_KEY"
      if [ -n "$PROMPTED_MODEL_NAME" ] && ! is_valid_model_name_value "$PROMPTED_MODEL_NAME"; then
        warn "Invalid upstream model name detected before writing configuration. Re-enter the model id; API keys must be entered only in the API key field."
        if [ "$NON_INTERACTIVE" = "1" ]; then
          echo "ERROR: invalid COX_MODEL value; expected model id, got an API-key-like or URL/path value" >&2
          return 1
        fi
        PROMPTED_MODEL_NAME=""
        guided_step=2
        continue
      fi
      guided_step=3
      ;;
    3)
      if prompt_serpapi_api_key; then
        step_rc=0
      else
        step_rc=$?
      fi
      if [ "$step_rc" = "20" ]; then
        guided_step=2
        continue
      fi
      SERPAPI_KEY="$PROMPTED_SERPAPI_API_KEY"
      guided_step=4
      ;;
    4)
      if prompt_image_generation_api_key; then
        step_rc=0
      else
        step_rc=$?
      fi
      if [ "$step_rc" = "20" ]; then
        guided_step=3
        continue
      fi
      IMAGE_API_KEY="$PROMPTED_IMAGE_API_KEY"
      guided_step=5
      ;;
    5)
      COX_NEXT_MENU_DETAIL="After installing, use codex --profile cox. Custom providers can use codex --profile <provider-id>. The wrapper starts or refreshes the local cox backend automatically."
      WRAPPER_CHOICE="$(read_yes_no_menu "Install codex wrapper for cox and provider-backed custom profiles? Recommended." "Y")"
      if [ "$WRAPPER_CHOICE" = "__COX_BACK__" ]; then
        guided_step=4
        continue
      fi
      case "$WRAPPER_CHOICE" in
        n|N|no|NO|No) INSTALL_CODEX_WRAPPER=0 ;;
        *) INSTALL_CODEX_WRAPPER=1 ;;
      esac
      break
      ;;
  esac
done

if [ -z "$API_KEY" ]; then
  if [ -n "$PROMPTED_MODEL_PROVIDER" ]; then
    warn "Model API key is empty; configure later with: cox config set-model --provider $PROMPTED_MODEL_PROVIDER"
  else
    warn "Model API key is empty; configure later with: cox config wizard"
  fi
fi

sync_install_checkout_to_ref() {
  local requested_ref="${1:-}"
  requested_ref="${requested_ref:-${COX_INSTALL_REF:-}}"

  if [ -z "$requested_ref" ]; then
    return 0
  fi
  if [ ! -d "$INSTALL_DIR/.git" ]; then
    return 0
  fi

  printf '+ Synchronizing installed checkout to ref: %s\n' "$requested_ref" >> "$INSTALL_LOG"

  (
    cd "$INSTALL_DIR"

    git fetch --tags --force origin >> "$INSTALL_LOG" 2>&1 || return 1

    local untracked_count
    untracked_count="$(git ls-files --others --exclude-standard | wc -l | tr -d ' ')"

    if ! git diff --quiet || ! git diff --cached --quiet || [ "$untracked_count" != "0" ]; then
      mkdir -p "$LOCAL_BACKUP_DIR"
      local dirty_patch="$LOCAL_BACKUP_DIR/installed-checkout-dirty-$(date +%Y%m%d_%H%M%S).patch"
      git diff > "$dirty_patch" || true
      git diff --cached >> "$dirty_patch" || true
      warn "Backed up local installed checkout modifications to: $dirty_patch"

      if [ "$untracked_count" != "0" ]; then
        local untracked_list="$LOCAL_BACKUP_DIR/installed-checkout-untracked-$(date +%Y%m%d_%H%M%S).txt"
        local untracked_tar="$LOCAL_BACKUP_DIR/installed-checkout-untracked-$(date +%Y%m%d_%H%M%S).tar.gz"
        git ls-files --others --exclude-standard > "$untracked_list" || true
        tar -czf "$untracked_tar" -T "$untracked_list" >> "$INSTALL_LOG" 2>&1 || true
        warn "Backed up local installed checkout untracked files to: $untracked_tar"
      fi

      if [ "${NON_INTERACTIVE:-0}" != "1" ] && [ -t 0 ]; then
        printf 'Installed checkout has local modifications. Overwrite after backup? [y/N] ' >&2
        local answer
        read -r answer
        case "$answer" in
          y|Y|yes|YES)
            ;;
          *)
            warn "Keeping local installed checkout modifications. Installation cannot refresh package code."
            return 1
            ;;
        esac
      fi

      git reset --hard >> "$INSTALL_LOG" 2>&1 || return 1
      git clean -fd >> "$INSTALL_LOG" 2>&1 || return 1
    fi

    if git show-ref --verify --quiet "refs/remotes/origin/$requested_ref"; then
      git checkout -B "$requested_ref" "origin/$requested_ref" >> "$INSTALL_LOG" 2>&1 || return 1
      return 0
    fi

    if git show-ref --verify --quiet "refs/tags/$requested_ref"; then
      git checkout -f "$requested_ref" >> "$INSTALL_LOG" 2>&1 || return 1
      return 0
    fi

    git checkout -f "$requested_ref" >> "$INSTALL_LOG" 2>&1 || return 1
  )

  ok "Repository target checked out"
}


download_source_archive_to_install_dir() {
  local ref="$1"
  if [ -z "$ref" ]; then
    return 1
  fi
  if ! command -v tar >/dev/null 2>&1; then
    warn "tar is required for source archive fallback."
    return 1
  fi

  local tmp_root="$LOCAL_BACKUP_DIR/source-archive-fallback-$(date +%Y%m%d_%H%M%S)"
  local archive="$tmp_root/source.tar.gz"
  local extract_dir="$tmp_root/extract"
  mkdir -p "$extract_dir"

  local url1="https://codeload.github.com/Awenforever/CoDeepSeedeX/tar.gz/refs/tags/$ref"
  local url2="https://github.com/Awenforever/CoDeepSeedeX/archive/refs/tags/$ref.tar.gz"

  printf '+ Source archive fallback for ref %s\n' "$ref" >> "$INSTALL_LOG"
  if ! curl -fL --retry 8 --retry-all-errors --retry-delay 3 --connect-timeout 20 --max-time 240 "$url1" -o "$archive" >> "$INSTALL_LOG" 2>&1; then
    warn "codeload source archive download failed. Trying GitHub archive URL."
    if ! curl -fL --retry 8 --retry-all-errors --retry-delay 3 --connect-timeout 20 --max-time 240 "$url2" -o "$archive" >> "$INSTALL_LOG" 2>&1; then
      warn "Source archive fallback failed. See log: $INSTALL_LOG"
      return 1
    fi
  fi

  tar -xzf "$archive" -C "$extract_dir" >> "$INSTALL_LOG" 2>&1 || return 1

  local extracted=""
  extracted="$(find "$extract_dir" -mindepth 1 -maxdepth 1 -type d | head -n 1)"
  if [ -z "$extracted" ] || [ ! -f "$extracted/scripts/install.sh" ]; then
    warn "Source archive fallback did not contain expected project layout."
    return 1
  fi

  mkdir -p "$LOCAL_BACKUP_DIR"
  if [ -e "$INSTALL_DIR" ]; then
    local backup="$LOCAL_BACKUP_DIR/install-dir-before-source-archive-$(date +%Y%m%d_%H%M%S)"
    mv "$INSTALL_DIR" "$backup"
    warn "Moved existing install directory aside for source archive fallback: $backup"
  fi

  mkdir -p "$(dirname "$INSTALL_DIR")"
  mv "$extracted" "$INSTALL_DIR"
  ok "Repository installed from source archive"
  return 0
}

prepare_install_checkout() {
  local target_ref="$1"

  if [ -d "$INSTALL_DIR/.git" ]; then
    if run_git_quiet "Repository tags fetched" "git fetch --tags --force origin" git -C "$INSTALL_DIR" fetch --tags origin; then
      return 0
    fi
    warn "Git fetch failed. Trying source archive fallback for $target_ref."
    download_source_archive_to_install_dir "$target_ref"
    return $?
  fi

  if [ -e "$INSTALL_DIR" ] && [ ! -d "$INSTALL_DIR/.git" ]; then
    if [ ! -d "$INSTALL_DIR" ] || [ -n "$(find "$INSTALL_DIR" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)" ]; then
      warn "Using source archive fallback for existing non-git install directory."
      printf '+ Existing install directory is not a git checkout, using source archive fallback: %s\n' "$INSTALL_DIR" >> "$INSTALL_LOG"
      download_source_archive_to_install_dir "$target_ref"
      return $?
    fi
  fi

  run_quiet "Install parent directory ready" mkdir -p "$(dirname "$INSTALL_DIR")"
  if run_git_quiet "Repository installed" "git clone" git clone "$REPO_URL" "$INSTALL_DIR" &&
     run_git_quiet "Repository tags fetched" "git fetch --tags --force origin" git -C "$INSTALL_DIR" fetch --tags origin; then
    return 0
  fi

  warn "Git clone/fetch failed. Trying source archive fallback for $target_ref."
  download_source_archive_to_install_dir "$target_ref"
}

resolve_install_internal_version_for_metadata() {
  local app_file="$INSTALL_DIR/codexchange_proxy/app.py"
  if [ ! -f "$app_file" ]; then
    return 0
  fi
  awk -F'"' '/^PROXY_INTERNAL_VERSION = / {print $2; exit}' "$app_file" 2>> "$INSTALL_LOG" || true
}


resolve_install_commit_for_metadata() {
  local ref="$1"

  if [ -d "$INSTALL_DIR/.git" ]; then
    git -C "$INSTALL_DIR" rev-parse --short HEAD 2>> "$INSTALL_LOG" || true
    return 0
  fi

  if [ -z "$ref" ] || ! command -v git >/dev/null 2>&1; then
    return 0
  fi

  if printf '%s\n' "$ref" | grep -Eq '^[0-9a-fA-F]{7,40}$'; then
    printf '%s\n' "$ref" | cut -c1-7
    return 0
  fi

  local refs
  refs="$(git ls-remote --tags "$REPO_URL" "$ref" "refs/tags/$ref" "refs/tags/$ref^{}" 2>> "$INSTALL_LOG" || true)"
  local peeled
  peeled="$(printf '%s\n' "$refs" | awk '$2 ~ /\^\{\}$/ {print substr($1,1,7); exit}')"
  if [ -n "$peeled" ]; then
    printf '%s\n' "$peeled"
    return 0
  fi

  printf '%s\n' "$refs" | awk 'NF >= 1 {print substr($1,1,7); exit}'
}

step "Installing"

INSTALL_TARGET_REF="$(resolve_install_ref)"
ok "Install target ref: $INSTALL_TARGET_REF"

prepare_install_checkout "$INSTALL_TARGET_REF"

sync_install_checkout_to_ref "$INSTALL_TARGET_REF"
ensure_managed_resources_git_excluded

INSTALL_TARGET_COMMIT="$(resolve_install_commit_for_metadata "$INSTALL_TARGET_REF")"
if [ -n "$INSTALL_TARGET_COMMIT" ]; then
  ok "Install target commit: $INSTALL_TARGET_COMMIT"
  printf '+ Install target commit: %s\n' "$INSTALL_TARGET_COMMIT" >> "$INSTALL_LOG"
else
  warn "Install target commit could not be resolved. Version output will use packaged fallback metadata."
fi
INSTALL_TARGET_INTERNAL_VERSION="$(resolve_install_internal_version_for_metadata)"
if [ -n "$INSTALL_TARGET_INTERNAL_VERSION" ]; then
  ok "Install internal version: $INSTALL_TARGET_INTERNAL_VERSION"
  printf '+ Install internal version: %s\n' "$INSTALL_TARGET_INTERNAL_VERSION" >> "$INSTALL_LOG"
else
  warn "Install internal version could not be resolved. Env metadata will omit COX_INTERNAL_VERSION."
fi

if is_existing_install_venv_python "$PYTHON_BIN"; then
  ok "Virtual environment ready (existing compatible venv reused)"
  printf '+ Virtual environment reused: %q
' "$INSTALL_DIR/.venv" >> "$INSTALL_LOG"
else
  run_quiet "Virtual environment ready" "$PYTHON_BIN" -m venv "$INSTALL_DIR/.venv"
fi
run_quiet "pip upgraded" env PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_PROGRESS_BAR=off "$INSTALL_DIR/.venv/bin/python" -m pip install --upgrade --quiet pip
run_quiet "Python package installed" env PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_PROGRESS_BAR=off "$INSTALL_DIR/.venv/bin/python" -m pip install --quiet --no-input -e "$INSTALL_DIR"
if ! sync_deepseek_tokenizer_resource; then
  warn "Profile tokenizer accounting will stay unavailable until tokenizer sync succeeds."
fi

write_env_file "$STABLE_PORT" "$THINKING_PORT" "$API_KEY" "$SERPAPI_KEY" "$IMAGE_API_KEY"
write_cox_wrapper
ensure_shell_profile_integration

run_quiet "cox config initialized" "$INSTALL_DIR/.venv/bin/cox" config init

MODEL_CATALOG_JSON="$(model_catalog_json_value)"
MODEL_CATALOG_ARGS=()
if [ -n "$MODEL_CATALOG_JSON" ]; then
  MODEL_CATALOG_ARGS=(--model-catalog-json "$MODEL_CATALOG_JSON")
fi

PROFILE_THINKING_MODEL="deepseek-v4-pro"
if [ -n "${RESOLVED_MODEL_NAME:-}" ] && [ "${RESOLVED_MODEL_PROVIDER:-deepseek}" != "deepseek" ]; then
  PROFILE_THINKING_MODEL="$RESOLVED_MODEL_NAME"
fi

if [ "$INSTALL_CODEX_PROFILE" = "1" ]; then
  run_quiet "Codex profile installed: cox" "$INSTALL_DIR/.venv/bin/cox" install-codex-profile \
    --name cox \
    --provider-name cox-proxy \
    --base-url "http://127.0.0.1:${THINKING_PORT}/v1" \
    --model "$PROFILE_THINKING_MODEL" \
    --reasoning-effort xhigh \
    --profile-layout split_profile_files \
    "${MODEL_CATALOG_ARGS[@]}"
fi

if [ "$INSTALL_CODEX_PROFILE" = "1" ]; then
    run_quiet "Deprecated Codex profile removed: deepseek" "$INSTALL_DIR/.venv/bin/cox" uninstall-codex-profile --name deepseek --no-backup || true
fi

write_codex_wrapper "$STABLE_PORT" "$THINKING_PORT"
post_install_entrypoint_diagnostics

step "Done"


# codexchange_repair_codex_model_catalog_json_v2746a1
if [ "$DRY_RUN" != "1" ]; then
  backup_local_file_before_overwrite "$HOME/.codex/config.toml" "Codex main config"
  "$PYTHON_BIN" - "$HOME/.codex/config.toml" "$INSTALL_DIR/experiments/model-catalog/cox-proxy-models.json" <<'PYCODEXCAT'
from __future__ import annotations

import sys
from pathlib import Path

config = Path(sys.argv[1])
catalog = sys.argv[2]
if not config.exists():
    raise SystemExit(0)

lines = config.read_text(encoding="utf-8").splitlines()
targets = {"profiles.deepseek", "profiles.cox"}
out = []
current = None
pending_insert = None

def flush_pending() -> None:
    global pending_insert
    if pending_insert is not None:
        out.append(f'model_catalog_json = "{catalog}"')
        pending_insert = None

for line in lines:
    stripped = line.strip()
    if stripped.startswith("[") and stripped.endswith("]"):
        flush_pending()
        current = stripped.strip("[]")
        out.append(line)
        pending_insert = "profile" if current in targets else None
        continue

    if current in targets and stripped.startswith("model_catalog_json"):
        if pending_insert is not None:
            out.append(f'model_catalog_json = "{catalog}"')
            pending_insert = None
        continue

    out.append(line)

    if current in targets and pending_insert is not None and stripped.startswith("model_provider"):
        out.append(f'model_catalog_json = "{catalog}"')
        pending_insert = None

flush_pending()
config.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")
PYCODEXCAT
  ok "Codex model catalog linked"
else
  ok "Codex model catalog linked"
fi

if [ "${COX_VERBOSE_INSTALL_SUMMARY:-0}" = "1" ]; then
  sub_title "Detailed install paths"
  printf '%s\n' "  env file: $ENV_FILE"
  refresh_canonical_codex_wrapper_template
  printf '%s\n' "  cox: $BIN_DIR/cox"
  if [ -n "$SHELL_PROFILE_FILE" ]; then
    printf '%s\n' "  shell profile: $SHELL_PROFILE_FILE"
  fi
  printf '%s\n' "  uninstall: bash $INSTALL_DIR/scripts/install.sh --uninstall"
fi

print_install_logs
show_install_completion_hold

divider
# Generated Codex profiles include: plan_mode_reasoning_effort = "high"
