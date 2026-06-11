#!/usr/bin/env bash
set -euo pipefail

REPO_URL="${COX_REPO_URL:-https://github.com/Awenforever/CodeXchange.git}"
LATEST_RELEASE_API_URL="${COX_LATEST_RELEASE_API_URL:-https://api.github.com/repos/Awenforever/CodeXchange/releases/latest}"
INSTALL_REF="${COX_INSTALL_REF:-}"
INSTALLER_URL_WAS_EXPLICIT=0
if [ -n "${COX_INSTALLER_URL:-}" ]; then
  INSTALLER_URL_WAS_EXPLICIT=1
fi
INSTALLER_URL="${COX_INSTALLER_URL:-https://github.com/Awenforever/CodeXchange/releases/latest/download/install.sh}"
ALT_INSTALLER_URL="${COX_ALT_INSTALLER_URL:-}"
THIRD_INSTALLER_URL="${COX_THIRD_INSTALLER_URL:-}"
RESOLVED_INSTALL_REF=""
RESOLVED_INSTALLER_SOURCE=""
INSTALL_LOG="${COX_BOOTSTRAP_LOG:-/tmp/codexchange-bootstrap-$(date +%Y%m%d_%H%M%S).log}"
BOOTSTRAP_WORKDIR="${COX_BOOTSTRAP_WORKDIR:-/tmp/codexchange-bootstrap-$(date +%Y%m%d_%H%M%S)-work}"
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


resolve_install_ref() {
  if [ -n "$INSTALL_REF" ]; then
    printf '%s\n' "$INSTALL_REF"
    return 0
  fi

  local tag
  tag="$(curl -fsSL --retry 5 --retry-all-errors --retry-delay 2 --connect-timeout 15 --max-time 60 "$LATEST_RELEASE_API_URL" |
    sed -nE 's/.*"tag_name"[[:space:]]*:[[:space:]]*"([^"]+)".*/\1/p' |
    head -n 1)"
  if [ -z "$tag" ]; then
    return 1
  fi
  printf '%s\n' "$tag"
}

usage() {
  cat <<'USAGE'
Usage: bootstrap.sh [bootstrap options] [-- install.sh options]

Bootstrap options:
  --dry-run                  Show bootstrap plan without installing system packages or running install.sh
  --install-ref REF          Download install.sh from this release tag/ref before falling back
  --print-python-selection   Print selected Python interpreter and stop
  -h, -H, --help             Show help

Examples:
  curl -fsSL https://github.com/Awenforever/CodeXchange/releases/latest/download/bootstrap.sh | bash
  curl -fsSL https://github.com/Awenforever/CodeXchange/releases/download/v0.3.8-alpha/bootstrap.sh | bash -s -- --install-ref v0.3.8-alpha
  bash bootstrap.sh -- --non-interactive
  bash bootstrap.sh -- --repo-url /path/to/local/CodeXchange
USAGE
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --install-ref)
      if [ "$#" -lt 2 ]; then
        fail "--install-ref requires a value"
        HELP_REQUESTED=1
        break
      fi
      INSTALL_REF="$2"
      shift 2
      ;;
    --install-ref=*)
      INSTALL_REF="${1#--install-ref=}"
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
  for candidate in "${COX_PYTHON_BIN:-}" python3.13 python3.12 python3.11 python3; do
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

  local fallback_ref=""
  if [ "$DRY_RUN" = "1" ]; then
    fallback_ref="$INSTALL_REF"
  else
    fallback_ref="$(resolve_install_ref || true)"
  fi
  if [ -n "$fallback_ref" ]; then
    RESOLVED_INSTALL_REF="$fallback_ref"
  fi

  local primary_url="$INSTALLER_URL"
  local alt_url="$ALT_INSTALLER_URL"
  local third_url="$THIRD_INSTALLER_URL"
  if [ -n "$fallback_ref" ]; then
    if [ "$INSTALLER_URL_WAS_EXPLICIT" != "1" ]; then
      primary_url="https://github.com/Awenforever/CodeXchange/releases/download/${fallback_ref}/install.sh"
    fi
    alt_url="${alt_url:-https://raw.githubusercontent.com/Awenforever/CodeXchange/${fallback_ref}/scripts/install.sh}"
    third_url="${third_url:-https://github.com/Awenforever/CodeXchange/raw/refs/tags/${fallback_ref}/scripts/install.sh}"
  fi

  RESOLVED_INSTALLER_SOURCE="$primary_url"

  if [ "$DRY_RUN" = "1" ]; then
    warn "dry-run: would download install.sh from $primary_url"
    warn "dry-run: install ref is ${fallback_ref:-<unresolved latest>}"
    warn "dry-run: fallback URLs are ${alt_url:-<none>} and ${third_url:-<none>}"
    return 0
  fi

  if curl -fL --retry 8 --retry-all-errors --retry-delay 3 --connect-timeout 20 --max-time 240 "$primary_url" -o "$INSTALLER_PATH" >> "$INSTALL_LOG" 2>&1; then
    RESOLVED_INSTALLER_SOURCE="$primary_url"
    chmod +x "$INSTALLER_PATH"
    return 0
  fi

  warn "Primary install.sh download failed. Trying install ref raw fallback."

  if [ -z "$alt_url" ]; then
    fail "Could not resolve the GitHub install ref for raw fallback."
    warn "Bootstrap log: $INSTALL_LOG"
    return 1
  fi

  if curl -fL --retry 8 --retry-all-errors --retry-delay 3 --connect-timeout 20 --max-time 240 "$alt_url" -o "$INSTALLER_PATH" >> "$INSTALL_LOG" 2>&1; then
    RESOLVED_INSTALLER_SOURCE="$alt_url"
    chmod +x "$INSTALLER_PATH"
    return 0
  fi

  warn "raw.githubusercontent.com install.sh download failed. Trying alternate install ref raw URL."

  if [ -n "$third_url" ] && curl -fL --retry 8 --retry-all-errors --retry-delay 3 --connect-timeout 20 --max-time 240 "$third_url" -o "$INSTALLER_PATH" >> "$INSTALL_LOG" 2>&1; then
    RESOLVED_INSTALLER_SOURCE="$third_url"
    chmod +x "$INSTALLER_PATH"
    return 0
  fi

  warn "Raw installer download failed. Trying install ref shallow git clone fallback."

  if [ -z "$fallback_ref" ]; then
    fail "Could not resolve the GitHub install ref for git clone fallback."
    warn "Bootstrap log: $INSTALL_LOG"
    return 1
  fi

  local clone_dir="$BOOTSTRAP_WORKDIR/repo"
  rm -rf "$clone_dir"
  if git clone --depth 1 --branch "$fallback_ref" "$REPO_URL" "$clone_dir" >> "$INSTALL_LOG" 2>&1 && [ -f "$clone_dir/scripts/install.sh" ]; then
    RESOLVED_INSTALL_REF="$fallback_ref"
    RESOLVED_INSTALLER_SOURCE="git clone $REPO_URL@$fallback_ref"
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
  printf 'bootstrap log: %s\n' "$INSTALL_LOG" >> "$INSTALL_LOG"
  printf 'bootstrap source: %s\n' "${COX_BOOTSTRAP_SOURCE:-downloaded or local bootstrap.sh}" >> "$INSTALL_LOG"
  printf 'requested install ref: %s\n' "${INSTALL_REF:-<GitHub Latest Release>}" >> "$INSTALL_LOG"

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
  printf 'python: %s via %s\n' "$(python_version_text "$selected_python")" "$selected_python" >> "$INSTALL_LOG"

  download_installer
  printf 'installer ready: %s\n' "$INSTALLER_PATH" >> "$INSTALL_LOG"
  printf 'installer source: %s\n' "${RESOLVED_INSTALLER_SOURCE:-unknown}" >> "$INSTALL_LOG"
  printf 'install ref: %s\n' "${RESOLVED_INSTALL_REF:-${INSTALL_REF:-<GitHub Latest Release>}}" >> "$INSTALL_LOG"

  if [ "$DRY_RUN" = "1" ]; then
    warn "dry-run: would run install.sh with COX_PYTHON_BIN=$selected_python"
    warn "dry-run: would pass COX_INSTALL_REF=${RESOLVED_INSTALL_REF:-${INSTALL_REF:-<install.sh resolves latest>}}"
    warn "dry-run: would pass COX_INSTALLER_SOURCE=${RESOLVED_INSTALLER_SOURCE:-unknown}"
    printf '  install args:'
    printf ' %q' "${INSTALL_ARGS[@]}"
    printf '\n'
    return 0
  fi

  unset COX_PUBLIC_COMMIT
  unset COX_INTERNAL_COMMIT
  unset COX_INTERNAL_VERSION

  if [ -n "$RESOLVED_INSTALL_REF" ] && [ -z "${COX_INSTALL_REF:-}" ]; then
    COX_BOOTSTRAP_LOG="$INSTALL_LOG" COX_INSTALL_REF="$RESOLVED_INSTALL_REF" COX_INSTALLER_SOURCE="${RESOLVED_INSTALLER_SOURCE:-unknown}" COX_PYTHON_BIN="$selected_python" bash "$INSTALLER_PATH" --python-bin "$selected_python" "${INSTALL_ARGS[@]}"
  else
    COX_BOOTSTRAP_LOG="$INSTALL_LOG" COX_INSTALLER_SOURCE="${RESOLVED_INSTALLER_SOURCE:-unknown}" COX_PYTHON_BIN="$selected_python" bash "$INSTALLER_PATH" --python-bin "$selected_python" "${INSTALL_ARGS[@]}"
  fi
}

main "$@"
