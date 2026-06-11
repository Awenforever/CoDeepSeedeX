#!/usr/bin/env bash
set -euo pipefail

cat <<'__COX_RUNTIME_SCRIPT_DEPRECATED_MESSAGE__'
install-runtime-scripts.sh is deprecated.

Use scripts/install.sh for normal installation, or use the installed cox CLI directly:

  cox start
  cox start thinking
  cox stop
  cox stop thinking
  cox status
  cox status thinking

The old standalone shortcut scripts are no longer the recommended runtime entrypoints.
__COX_RUNTIME_SCRIPT_DEPRECATED_MESSAGE__
