#!/usr/bin/env bash
set -euo pipefail

REPO_URL="${DEEPSEEK_PROXY_REPO_URL:-https://github.com/Awenforever/CoDeepSeedeX.git}"
INSTALLER_URL="${DEEPSEEK_PROXY_INSTALLER_URL:-https://github.com/Awenforever/CoDeepSeedeX/releases/latest/download/install.sh}"
ALT_INSTALLER_URL="${DEEPSEEK_PROXY_ALT_INSTALLER_URL:-https://raw.githubusercontent.com/Awenforever/CoDeepSeedeX/master/scripts/install.sh}"
THIRD_INSTALLER_URL="${DEEPSEEK_PROXY_THIRD_INSTALLER_URL:-https://github.com/Awenforever/CoDeepSeedeX/raw/refs/heads/master/scripts/install.sh}"
INSTALL_LOG="${DEEPSEEK_PROXY_BOOTSTRAP_LOG:-/tmp/codeepseedex-bootstrap-$(date +%Y%m%d_%H%M%S).log}"
BOOTSTRAP_WORKDIR="${DEEPSEEK_PROXY_BOOTSTRAP_WORKDIR:-/tmp/codeepseedex-bootstrap-$(date +%Y%m%d_%H%M%S)-work}"
INSTALLER_PATH="$BOOTSTRAP_WORKDIR/install.sh"

DRY_RUN=0
PRINT_PYTHON_SELECTION=0
HELP_REQUESTED=0
INSTALL_ARGS=()

color() {
  local code="$1"
  shift
  if [ -t 1 ]; then
    printf '\033[%sm%s\033[0m\n' "$code" "$*"
  else
    printf '%s\n' "$*"
  fi
}

ok() { color "1;32" "  ✓ $*"; }
warn() { color "1;33" "  ! $*"; }
fail() { color "1;31" "  ✗ $*"; }

usage() {
  cat <<'USAGE'
Usage: bootstrap.sh [bootstrap options] [-- install.sh options]

Bootstrap options:
  --dry-run                  Show bootstrap plan without installing system packages or running install.sh
  --print-python-selection   Print selected Python interpreter and stop
  -h, -H, --help             Show help

Examples:
  curl -fsSL https://github.com/Awenforever/CoDeepSeedeX/releases/latest/download/bootstrap.sh | bash
  bash bootstrap.sh -- --non-interactive
  bash bootstrap.sh -- --repo-url /path/to/local/CoDeepSeedeX
USAGE
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --print-python-selection)
      PRINT_PYTHON_SELECTION=1
      shift
      ;;
    -h|-H|--help)
      usage
      HELP_REQUESTED=1
      break
      ;;
    --)
      shift
      INSTALL_ARGS+=("$@")
      break
      ;;
    *)
      INSTALL_ARGS+=("$1")
      shift
      ;;
  esac
done

python_version_ok() {
  local py="$1"
  "$py" - <<'BOOTPY' >/dev/null 2>&1
import sys
raise SystemExit(0 if sys.version_info >= (3, 11) else 1)
BOOTPY
}

python_version_text() {
  local py="$1"
  "$py" - <<'BOOTPY' 2>/dev/null || true
import sys
print(".".join(map(str, sys.version_info[:3])))
BOOTPY
}

select_python() {
  local candidate
  for candidate in "${DEEPSEEK_PROXY_PYTHON_BIN:-}" python3.13 python3.12 python3.11 python3; do
    if [ -z "$candidate" ]; then
      continue
    fi
    if command -v "$candidate" >/dev/null 2>&1 && python_version_ok "$candidate"; then
      command -v "$candidate"
      return 0
    fi
  done
  return 1
}

have_cmd() {
  command -v "$1" >/dev/null 2>&1
}

install_apt_packages() {
  if ! have_cmd apt-get; then
    fail "Unsupported package manager. This bootstrap currently supports apt-based Debian/Ubuntu/WSL systems."
    return 1
  fi

  if ! have_cmd sudo; then
    fail "sudo is required to install missing system packages."
    return 1
  fi

  if [ "$DRY_RUN" = "1" ]; then
    warn "dry-run: would run apt-get update and install git curl ca-certificates python3 python3-venv python3-pip"
    warn "dry-run: would also install python3.11 python3.11-venv when Python >= 3.11 is missing"
    return 0
  fi

  sudo -v
  sudo apt-get update >> "$INSTALL_LOG" 2>&1
  sudo apt-get install -y git curl ca-certificates python3 python3-venv python3-pip >> "$INSTALL_LOG" 2>&1

  if ! select_python >/dev/null 2>&1; then
    warn "Default Python is lower than 3.11 or unavailable. Trying python3.11 packages."
    if ! sudo apt-get install -y python3.11 python3.11-venv >> "$INSTALL_LOG" 2>&1; then
      fail "Python >= 3.11 is required, but python3.11 packages were not available from current apt sources."
      warn "Install Python 3.11+ manually, enable an apt source that provides python3.11, or use a newer Ubuntu release."
      warn "Bootstrap log: $INSTALL_LOG"
      return 1
    fi
  fi
}

download_installer() {
  mkdir -p "$BOOTSTRAP_WORKDIR"

  if [ "$DRY_RUN" = "1" ]; then
    warn "dry-run: would download install.sh from $INSTALLER_URL"
    warn "dry-run: fallback URLs are $ALT_INSTALLER_URL and $THIRD_INSTALLER_URL"
    return 0
  fi

  if curl -fL --retry 8 --retry-all-errors --retry-delay 3 --connect-timeout 20 --max-time 240 "$INSTALLER_URL" -o "$INSTALLER_PATH" >> "$INSTALL_LOG" 2>&1; then
    chmod +x "$INSTALLER_PATH"
    return 0
  fi

  warn "Primary install.sh download failed. Trying raw.githubusercontent.com fallback."

  if curl -fL --retry 8 --retry-all-errors --retry-delay 3 --connect-timeout 20 --max-time 240 "$ALT_INSTALLER_URL" -o "$INSTALLER_PATH" >> "$INSTALL_LOG" 2>&1; then
    chmod +x "$INSTALLER_PATH"
    return 0
  fi

  warn "raw.githubusercontent.com install.sh download failed. Trying alternate GitHub raw URL."

  if curl -fL --retry 8 --retry-all-errors --retry-delay 3 --connect-timeout 20 --max-time 240 "$THIRD_INSTALLER_URL" -o "$INSTALLER_PATH" >> "$INSTALL_LOG" 2>&1; then
    chmod +x "$INSTALLER_PATH"
    return 0
  fi

  warn "Raw installer download failed. Trying shallow git clone fallback."

  local clone_dir="$BOOTSTRAP_WORKDIR/repo"
  rm -rf "$clone_dir"
  if git clone --depth 1 "$REPO_URL" "$clone_dir" >> "$INSTALL_LOG" 2>&1 && [ -f "$clone_dir/scripts/install.sh" ]; then
    cp "$clone_dir/scripts/install.sh" "$INSTALLER_PATH"
    chmod +x "$INSTALLER_PATH"
    return 0
  fi

  fail "Could not obtain install.sh."
  warn "Possible causes: network/TLS/proxy interruption or GitHub access failure."
  warn "Bootstrap log: $INSTALL_LOG"
  return 1
}

main() {
  color "1;36" "CoDeepSeedeX bootstrap"
  printf '  log: %s\n' "$INSTALL_LOG"

  if [ "$HELP_REQUESTED" = "1" ]; then
    return 0
  fi

  if [ "$PRINT_PYTHON_SELECTION" = "1" ]; then
    if selected="$(select_python)"; then
      printf 'python_bin=%s\n' "$selected"
      printf 'python_version=%s\n' "$(python_version_text "$selected")"
      return 0
    fi
    printf 'python_bin=\n'
    printf 'python_version=\n'
    return 1
  fi

  install_apt_packages

  selected_python="$(select_python || true)"
  if [ -z "$selected_python" ]; then
    fail "Python >= 3.11 is still unavailable after dependency setup."
    warn "Bootstrap log: $INSTALL_LOG"
    return 1
  fi
  ok "Python $(python_version_text "$selected_python") via $selected_python"

  download_installer
  ok "Installer ready"

  if [ "$DRY_RUN" = "1" ]; then
    warn "dry-run: would run install.sh with DEEPSEEK_PROXY_PYTHON_BIN=$selected_python"
    printf '  install args:'
    printf ' %q' "${INSTALL_ARGS[@]}"
    printf '\n'
    return 0
  fi

  DEEPSEEK_PROXY_PYTHON_BIN="$selected_python" bash "$INSTALLER_PATH" --python-bin "$selected_python" "${INSTALL_ARGS[@]}"
}

main "$@"
