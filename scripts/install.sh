#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="${DEEPSEEK_PROXY_INSTALL_DIR:-$HOME/.local/share/deepseek-responses-proxy}"
REPO_URL="${DEEPSEEK_PROXY_REPO_URL:-https://github.com/Awenforever/CoDeepSeedeX.git}"
BIN_DIR="${DEEPSEEK_PROXY_BIN_DIR:-$HOME/.local/bin}"
DRY_RUN=0
INSTALL_CODEX_PROFILE=1

while [ "$#" -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    --install-dir) INSTALL_DIR="$2"; shift ;;
    --repo-url) REPO_URL="$2"; shift ;;
    --bin-dir) BIN_DIR="$2"; shift ;;
    --no-codex-profile) INSTALL_CODEX_PROFILE=0 ;;
    -h|--help)
      cat <<'USAGE'
Usage: scripts/install.sh [--dry-run] [--install-dir DIR] [--repo-url URL] [--bin-dir DIR] [--no-codex-profile]
USAGE
      exit 0
      ;;
    *) echo "ERROR: unknown argument: $1" >&2; exit 2 ;;
  esac
  shift
done

run() {
  echo "+ $*"
  if [ "$DRY_RUN" = "0" ]; then
    "$@"
  fi
}

echo "DeepSeek Responses Proxy installer"
echo "INSTALL_DIR=$INSTALL_DIR"
echo "REPO_URL=$REPO_URL"
echo "BIN_DIR=$BIN_DIR"
echo "DRY_RUN=$DRY_RUN"

python3 - <<'PY'
import sys
if sys.version_info < (3, 11):
    raise SystemExit("ERROR: Python >= 3.11 is required")
print("python =", sys.version.split()[0])
PY

if ! command -v git >/dev/null 2>&1; then
  echo "ERROR: git is required" >&2
  exit 1
fi

if [ -d "$INSTALL_DIR/.git" ]; then
  run git -C "$INSTALL_DIR" pull --ff-only
else
  run mkdir -p "$(dirname "$INSTALL_DIR")"
  run git clone "$REPO_URL" "$INSTALL_DIR"
fi

run python3 -m venv "$INSTALL_DIR/.venv"
run "$INSTALL_DIR/.venv/bin/python" -m pip install --upgrade pip
run "$INSTALL_DIR/.venv/bin/python" -m pip install -e "$INSTALL_DIR"

run mkdir -p "$BIN_DIR"
if [ "$DRY_RUN" = "0" ]; then
  cat > "$BIN_DIR/dsproxy" <<EOF
#!/usr/bin/env bash
exec "$INSTALL_DIR/.venv/bin/dsproxy" "\$@"
EOF
  chmod +x "$BIN_DIR/dsproxy"
else
  echo "+ write $BIN_DIR/dsproxy"
fi

run "$INSTALL_DIR/.venv/bin/dsproxy" config init

if [ "$INSTALL_CODEX_PROFILE" = "1" ]; then
  run "$INSTALL_DIR/.venv/bin/dsproxy" install-codex-profile
fi

echo
echo "Installed. Next steps:"
echo "  export DEEPSEEK_API_KEY=..."
echo "  dsproxy start --thinking"
echo "  codex --profile deepseek-thinking"
