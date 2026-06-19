#!/usr/bin/env bash
set -euo pipefail

cat <<'__COX_RUNTIME_SCRIPT_DEPRECATED_MESSAGE__'
install-runtime-scripts.sh is deprecated.

Use scripts/install.sh for normal installation, or use the installed cox CLI directly:

  cox start
  cox start reasoning
  cox stop
  cox stop reasoning
  cox status
  cox status reasoning

Legacy aliases such as thinking and non-thinking remain accepted for compatibility,
but new scripts and user-facing examples should use reasoning and standard.
__COX_RUNTIME_SCRIPT_DEPRECATED_MESSAGE__
