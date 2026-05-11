#!/usr/bin/env bash
set -euo pipefail

cat <<'__CODEEPSEEDEX_RUNTIME_SCRIPT_DEPRECATED_MESSAGE__'
install-runtime-scripts.sh is deprecated.

Use scripts/install.sh for normal installation, or use the installed dsproxy CLI directly:

  dsproxy start
  dsproxy start thinking
  dsproxy stop
  dsproxy stop thinking
  dsproxy status
  dsproxy status thinking

The old standalone shortcut scripts are no longer the recommended runtime entrypoints.
__CODEEPSEEDEX_RUNTIME_SCRIPT_DEPRECATED_MESSAGE__
