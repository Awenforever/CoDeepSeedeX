#!/usr/bin/env bash
set -euo pipefail

PROJECT="${DEEPSEEK_PROXY_PROJECT:-$HOME/projects/deepseek-responses-proxy}"
BIN_DIR="${DEEPSEEK_PROXY_BIN_DIR:-$HOME/bin}"

mkdir -p "$BIN_DIR"

for name in \
  dsproxy-start \
  dsproxy-start-thinking \
  dsproxy-stop \
  dsproxy-stop-thinking \
  dsproxy-status \
  dsproxy-status-thinking \
  dsproxy-config
do
  install -m 0755 "$PROJECT/scripts/$name" "$BIN_DIR/$name"
  echo "installed $BIN_DIR/$name"
done

echo
echo "Runtime scripts installed."
echo
echo "To enable Codex auto-start, copy the function from:"
echo "  $PROJECT/scripts/codex-wrapper.bash"
echo "into ~/.bashrc, then run:"
echo "  source ~/.bashrc"
echo "  hash -r"
