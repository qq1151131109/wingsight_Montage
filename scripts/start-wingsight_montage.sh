#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
COMPANION_WEB_DIR="$PROJECT_DIR/apps/companion/web"
RUNTIME_DIR="$PROJECT_DIR/.tmp/wingsight-companion"
PID_FILE="$RUNTIME_DIR/companion.pid"
CLOUDFLARED_PID_FILE="$RUNTIME_DIR/cloudflared.pid"
STDOUT_LOG="$RUNTIME_DIR/companion.log"
STDERR_LOG="$RUNTIME_DIR/companion.error.log"
CLOUDFLARED_LOG="$RUNTIME_DIR/cloudflared.log"
PORT="${PORT:-3456}"
HOST="${HOST:-0.0.0.0}"

export BUN_INSTALL="${BUN_INSTALL:-$HOME/.bun}"
export WINGSIGHT_MONTAGE_PROJECT_DIR="$PROJECT_DIR"
export WINGSIGHT_MONTAGE_USER_MODE="${WINGSIGHT_MONTAGE_USER_MODE:-1}"
export VITE_WINGSIGHT_MONTAGE_USER_MODE="$WINGSIGHT_MONTAGE_USER_MODE"
export COMPANION_PORT="$PORT"
export PORT
export HOST

PROJECT_VENV="$PROJECT_DIR/.venv"
if [ -x "$PROJECT_VENV/bin/python" ]; then
  export VIRTUAL_ENV="$PROJECT_VENV"
  export PYTHON="$PROJECT_VENV/bin/python"
  export PYTHON3="$PROJECT_VENV/bin/python"
  export PIP="$PROJECT_VENV/bin/pip"
  export PATH="$PROJECT_VENV/bin:$BUN_INSTALL/bin:$PATH"
else
  export PATH="$BUN_INSTALL/bin:$PATH"
fi

if ! command -v bun >/dev/null 2>&1; then
  echo "bun was not found. Install Bun first: curl -fsSL https://bun.sh/install | bash" >&2
  exit 1
fi

COMPANION_CLI="$COMPANION_WEB_DIR/bin/cli.ts"
if [ ! -f "$COMPANION_CLI" ]; then
  echo "Local Companion source was not found at apps/companion/web" >&2
  exit 1
fi

mkdir -p "$RUNTIME_DIR"

is_pid_running() {
  local pid="${1:-}"
  [ -n "$pid" ] && kill -0 "$pid" >/dev/null 2>&1
}

pid_from_file() {
  if [ -f "$PID_FILE" ]; then
    tr -cd '0-9' < "$PID_FILE"
  fi
}

running_pid() {
  local pid
  pid="$(pid_from_file)"
  if is_pid_running "$pid"; then
    printf '%s\n' "$pid"
  fi
}

cloudflared_pid_from_file() {
  if [ -f "$CLOUDFLARED_PID_FILE" ]; then
    tr -cd '0-9' < "$CLOUDFLARED_PID_FILE"
  fi
}

running_cloudflared_pid() {
  local pid
  pid="$(cloudflared_pid_from_file)"
  if is_pid_running "$pid"; then
    printf '%s\n' "$pid"
  fi
}

lan_url() {
  local ip
  ip="$(hostname -I 2>/dev/null | tr ' ' '\n' | grep -E '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$' | grep -Ev '^(127|172)\.' | head -1 || true)"
  if [ -n "$ip" ]; then
    printf 'http://%s:%s\n' "$ip" "$PORT"
  fi
}

public_url_from_cloudflared_log() {
  if [ ! -f "$CLOUDFLARED_LOG" ]; then
    return 0
  fi
  grep -Eo 'https://[-a-zA-Z0-9.]+\.trycloudflare\.com' "$CLOUDFLARED_LOG" | tail -1 || true
}

wait_for_health() {
  for _ in $(seq 1 80); do
    if curl -fsS "http://localhost:$PORT/health" >/dev/null 2>&1; then
      return 0
    fi
    sleep 0.25
  done
  return 1
}

wait_for_public_url() {
  for _ in $(seq 1 80); do
    local url
    url="$(public_url_from_cloudflared_log)"
    if [ -n "$url" ]; then
      printf '%s\n' "$url"
      return 0
    fi
    sleep 0.25
  done
  return 1
}

start_server() {
  local pid
  pid="$(running_pid || true)"
  if [ -n "$pid" ]; then
    echo "Wingsight Companion is already running (PID: $pid)"
    echo "URL: http://localhost:$PORT"
    return 0
  fi

  if curl -fsS "http://localhost:$PORT/health" >/dev/null 2>&1; then
    echo "Port $PORT already has a Companion-compatible server responding." >&2
    echo "Stop that process first, or run with PORT=<port>." >&2
    return 1
  fi

  cd "$COMPANION_WEB_DIR"
  setsid nohup env \
    NODE_ENV=production \
    __COMPANION_PACKAGE_ROOT="$COMPANION_WEB_DIR" \
    WINGSIGHT_MONTAGE_PROJECT_DIR="$WINGSIGHT_MONTAGE_PROJECT_DIR" \
    WINGSIGHT_MONTAGE_USER_MODE="$WINGSIGHT_MONTAGE_USER_MODE" \
    VITE_WINGSIGHT_MONTAGE_USER_MODE="$VITE_WINGSIGHT_MONTAGE_USER_MODE" \
    COMPANION_PORT="$COMPANION_PORT" \
    PORT="$PORT" \
    HOST="$HOST" \
    VIRTUAL_ENV="${VIRTUAL_ENV:-}" \
    PYTHON="${PYTHON:-}" \
    PYTHON3="${PYTHON3:-}" \
    PIP="${PIP:-}" \
    PATH="$PATH" \
    bun server/index.ts >"$STDOUT_LOG" 2>"$STDERR_LOG" &

  pid="$!"
  printf '%s\n' "$pid" > "$PID_FILE"

  if wait_for_health; then
    echo "Wingsight Companion started (PID: $pid)"
    echo "URL: http://localhost:$PORT"
    local lan
    lan="$(lan_url)"
    if [ -n "$lan" ]; then
      echo "LAN URL: $lan"
    fi
    return 0
  fi

  echo "Wingsight Companion did not become healthy. Logs:" >&2
  echo "  $STDOUT_LOG" >&2
  echo "  $STDERR_LOG" >&2
  return 1
}

start_tunnel() {
  local server_pid tunnel_pid public_url
  server_pid="$(running_pid || true)"
  if [ -z "$server_pid" ]; then
    start_server
  fi

  tunnel_pid="$(running_cloudflared_pid || true)"
  if [ -n "$tunnel_pid" ]; then
    echo "Cloudflare tunnel is already running (PID: $tunnel_pid)"
    public_url="$(public_url_from_cloudflared_log)"
    if [ -n "$public_url" ]; then
      echo "Public URL: $public_url"
    fi
    return 0
  fi

  if ! command -v cloudflared >/dev/null 2>&1; then
    echo "cloudflared was not found. Install it or use router port forwarding to expose http://<public-ip>:$PORT." >&2
    return 1
  fi

  : > "$CLOUDFLARED_LOG"
  setsid nohup cloudflared tunnel --url "http://127.0.0.1:$PORT" --protocol http2 --no-autoupdate >"$CLOUDFLARED_LOG" 2>&1 &
  tunnel_pid="$!"
  printf '%s\n' "$tunnel_pid" > "$CLOUDFLARED_PID_FILE"

  public_url="$(wait_for_public_url || true)"
  echo "Cloudflare tunnel started (PID: $tunnel_pid)"
  if [ -n "$public_url" ]; then
    echo "Public URL: $public_url"
    update_public_url "$public_url" || true
  else
    echo "Public URL is not ready yet. Check: $CLOUDFLARED_LOG" >&2
  fi
}

stop_tunnel() {
  local pid
  pid="$(running_cloudflared_pid || true)"
  if [ -z "$pid" ]; then
    rm -f "$CLOUDFLARED_PID_FILE"
    echo "Cloudflare tunnel is not running."
    return 0
  fi

  kill "$pid" >/dev/null 2>&1 || true
  for _ in $(seq 1 40); do
    if ! is_pid_running "$pid"; then
      rm -f "$CLOUDFLARED_PID_FILE"
      echo "Cloudflare tunnel stopped."
      return 0
    fi
    sleep 0.25
  done

  kill -9 "$pid" >/dev/null 2>&1 || true
  rm -f "$CLOUDFLARED_PID_FILE"
  echo "Cloudflare tunnel stopped."
}

update_public_url() {
  local public_url="$1"
  cd "$COMPANION_WEB_DIR"
  bun -e '
    import { updateSettings } from "./server/settings-manager.ts";
    updateSettings({ publicUrl: process.argv[1] });
  ' "$public_url" >/dev/null
}

stop_server() {
  local pid
  pid="$(running_pid || true)"
  if [ -z "$pid" ]; then
    rm -f "$PID_FILE"
    echo "Wingsight Companion is not running."
    return 0
  fi

  kill "$pid" >/dev/null 2>&1 || true
  for _ in $(seq 1 40); do
    if ! is_pid_running "$pid"; then
      rm -f "$PID_FILE"
      echo "Wingsight Companion stopped."
      return 0
    fi
    sleep 0.25
  done

  kill -9 "$pid" >/dev/null 2>&1 || true
  rm -f "$PID_FILE"
  echo "Wingsight Companion stopped."
}

show_status() {
  local pid
  pid="$(running_pid || true)"
  if [ -n "$pid" ] && curl -fsS "http://localhost:$PORT/health" >/dev/null 2>&1; then
    echo "Wingsight Companion is running (PID: $pid)"
    echo "URL: http://localhost:$PORT"
    local lan tunnel_pid public_url
    lan="$(lan_url)"
    if [ -n "$lan" ]; then
      echo "LAN URL: $lan"
    fi
    tunnel_pid="$(running_cloudflared_pid || true)"
    if [ -n "$tunnel_pid" ]; then
      echo "Cloudflare tunnel is running (PID: $tunnel_pid)"
      public_url="$(public_url_from_cloudflared_log)"
      if [ -n "$public_url" ]; then
        echo "Public URL: $public_url"
      fi
    fi
    return 0
  fi

  if curl -fsS "http://localhost:$PORT/health" >/dev/null 2>&1; then
    echo "A Companion server is running on port $PORT, but it is not managed by this script."
    echo "URL: http://localhost:$PORT"
    return 0
  fi

  rm -f "$PID_FILE"
  echo "Wingsight Companion is not running."
  return 1
}

tail_logs() {
  touch "$STDOUT_LOG" "$STDERR_LOG"
  touch "$CLOUDFLARED_LOG"
  tail -f "$STDOUT_LOG" "$STDERR_LOG" "$CLOUDFLARED_LOG"
}

COMMAND="${1:-serve}"
case "$COMMAND" in
  serve|--foreground)
    cd "$COMPANION_WEB_DIR"
    export NODE_ENV=production
    export __COMPANION_PACKAGE_ROOT="$COMPANION_WEB_DIR"
    exec bun server/index.ts
    ;;
  start)
    start_server
    ;;
  stop)
    stop_tunnel >/dev/null || true
    stop_server
    ;;
  restart)
    stop_tunnel >/dev/null || true
    stop_server >/dev/null || true
    start_server
    ;;
  public|tunnel)
    start_tunnel
    ;;
  restart-public|restart-tunnel)
    stop_tunnel >/dev/null || true
    start_tunnel
    ;;
  stop-public|stop-tunnel)
    stop_tunnel
    ;;
  status)
    show_status
    ;;
  logs)
    tail_logs
    ;;
  install|uninstall)
    echo "Service install/uninstall is intentionally disabled for this project wrapper." >&2
    echo "Use: scripts/start-wingsight_montage.sh start" >&2
    exit 1
    ;;
  *)
    cd "$COMPANION_WEB_DIR"
    exec bun "$COMPANION_CLI" "$@"
    ;;
esac
