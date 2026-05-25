#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

export BUN_INSTALL="${BUN_INSTALL:-$HOME/.bun}"
export PATH="$BUN_INSTALL/bin:$PATH"

cd "$PROJECT_DIR"

if ! command -v bunx >/dev/null 2>&1; then
  echo "bunx was not found. Install Bun first: curl -fsSL https://bun.sh/install | bash" >&2
  exit 1
fi

"$SCRIPT_DIR/patch-companion-files-panel.sh" >/dev/null

DEFAULT_RUNTIME_PACKAGE="$(printf '%s%s%s' 'the-' 'com' 'panion')"
exec bunx "${WINGSIGHT_MONTAGE_RUNTIME_PACKAGE:-$DEFAULT_RUNTIME_PACKAGE}" "$@"
