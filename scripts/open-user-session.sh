#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SESSION_CLI="$SCRIPT_DIR/start-wingsight_montage.sh"
SESSION_NAME="${WINGSIGHT_MONTAGE_SESSION_NAME:-wingsight_montage 视频助手}"
BACKEND="${WINGSIGHT_MONTAGE_BACKEND:-codex}"
MODEL="${WINGSIGHT_MONTAGE_MODEL:-gpt-5.5}"
PERMISSION_MODE="${WINGSIGHT_MONTAGE_PERMISSION:-bypassPermissions}"
REUSE_SESSION=0
PYTHON_BIN="$PROJECT_DIR/.venv/bin/python"

if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="python3"
fi

if [ "${1:-}" = "--reuse" ]; then
  REUSE_SESSION=1
fi

"$SESSION_CLI" start >/dev/null

for _ in $(seq 1 40); do
  if "$SESSION_CLI" status >/dev/null 2>&1; then
    break
  fi
  sleep 0.25
done

mkdir -p "$PROJECT_DIR/projects/uploads"

find_session() {
  "$SESSION_CLI" sessions list \
    | "$PYTHON_BIN" -c '
import json
import os
import sys

project_dir = os.environ["PROJECT_DIR"]
session_name = os.environ["SESSION_NAME"]
sessions = json.load(sys.stdin)
for item in sessions:
    if item.get("archived") or item.get("state") == "exited":
        continue
    name = item.get("name") or ""
    if item.get("cwd") == project_dir and name.startswith(session_name):
        print(item["sessionId"])
        break
'
}

export PROJECT_DIR SESSION_NAME
SESSION_ID="$(find_session || true)"

if [ "$REUSE_SESSION" -eq 0 ]; then
  SESSION_ID=""
fi

if [ -z "$SESSION_ID" ]; then
  CREATE_OUTPUT="$("$SESSION_CLI" sessions create \
    --backend "$BACKEND" \
    --model "$MODEL" \
    --cwd "$PROJECT_DIR" \
    --permission-mode "$PERMISSION_MODE")"
  SESSION_ID="$(printf '%s' "$CREATE_OUTPUT" | "$PYTHON_BIN" -c 'import json,sys; print(json.load(sys.stdin)["sessionId"])')"

  "$SESSION_CLI" sessions rename "$SESSION_ID" "$SESSION_NAME $(date +%m%d-%H%M%S)" >/dev/null || true
fi

URL="http://localhost:3456/#/session/$SESSION_ID"

if command -v xdg-open >/dev/null 2>&1; then
  xdg-open "$URL" >/dev/null 2>&1 || true
fi

printf '%s\n' "$URL"
