#!/usr/bin/env bash
# Run Investing Nexus locally: the static site (docs/) and the calculator
# backend (server/).
#
#   scripts/nexus.sh --start     start both in the background
#   scripts/nexus.sh --stop      stop both
#   scripts/nexus.sh --status    show what is running
#   scripts/nexus.sh --restart   stop, then start
#
# Site:    http://localhost:8080  (pages detect localhost and call the local backend;
#          a clone at ../nexus-design is used instead of the hosted design system)
# Backend: http://localhost:8000  (health check: /health)
#
# The first --start creates .venv/ and installs server/requirements.txt;
# later runs reinstall only when that file changes. It picks the first Python
# >= 3.10 (final release) that can create a venv; set NEXUS_PYTHON to choose
# one. Logs and PID files go to .run/. The ports are fixed because the pages
# and the backend's CORS list expect exactly these two.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DIR="$ROOT/.run"
VENV="$ROOT/.venv"
REQS="$ROOT/server/requirements.txt"
SITE_PORT=8080
API_PORT=8000

usage() {
  sed -n '2,11p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
  exit "${1:-0}"
}

# --- process helpers -------------------------------------------------------

pid_of() {  # pid_of NAME -> prints the PID if NAME is running, else nothing
  local f="$RUN_DIR/$1.pid" pid cmd=""
  [[ -f "$f" ]] || return 0
  pid="$(cat "$f")"
  # Only trust the PID file if that process is still ours (PIDs get reused).
  # Read the cmdline into a variable: piping into grep -q would SIGPIPE tr and,
  # under pipefail, report a running process as gone.
  [[ -r "/proc/$pid/cmdline" ]] && cmd="$(tr '\0' ' ' < "/proc/$pid/cmdline")"
  if [[ "$cmd" == *"$2"* ]]; then
    echo "$pid"
  else
    rm -f "$f"
  fi
}

port_busy() {
  (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null
}

wait_for_url() {  # wait_for_url URL SECONDS
  local i
  for ((i = 0; i < $2 * 4; i++)); do
    curl -fs -o /dev/null "$1" && return 0
    sleep 0.25
  done
  return 1
}

# --- environment -----------------------------------------------------------

find_python() {
  # An activated venv from another project can shadow python3 with one that
  # lacks ensurepip, so check each candidate instead of trusting PATH order.
  local p
  for p in ${NEXUS_PYTHON:-} /usr/bin/python3 python3.13 python3.12 python3.11 python3.10 python3; do
    command -v "$p" >/dev/null 2>&1 || continue
    if "$p" -c 'import sys, ensurepip, venv; sys.exit(not (sys.version_info >= (3, 10) and sys.version_info.releaselevel == "final"))' 2>/dev/null; then
      echo "$p"
      return 0
    fi
  done
  echo "No suitable Python found (need >= 3.10 with venv support, e.g. apt install python3-venv)." >&2
  echo "Point NEXUS_PYTHON at one to override." >&2
  return 1
}

ensure_venv() {
  local stamp="$VENV/.requirements.sha" want py
  want="$(sha256sum "$REQS" | cut -d' ' -f1)"
  if [[ ! -x "$VENV/bin/python" ]]; then
    py="$(find_python)"
    echo "Creating virtual environment in .venv/ with $py ($("$py" -V 2>&1)) ..."
    rm -rf "$VENV"
    "$py" -m venv "$VENV"
  fi
  if [[ "$(cat "$stamp" 2>/dev/null)" != "$want" ]]; then
    echo "Installing backend dependencies (server/requirements.txt) ..."
    "$VENV/bin/pip" install --quiet --upgrade pip
    "$VENV/bin/pip" install --quiet -r "$REQS"
    echo "$want" > "$stamp"
  fi
}

# --- commands --------------------------------------------------------------

start_one() {  # start_one NAME MATCH PORT COMMAND...
  local name="$1" match="$2" port="$3"
  shift 3
  if [[ -n "$(pid_of "$name" "$match")" ]]; then
    echo "  $name already running (pid $(pid_of "$name" "$match"))"
    return 0
  fi
  if port_busy "$port"; then
    echo "  Port $port is already in use by another program; stop it first." >&2
    return 1
  fi
  # Background only the server command itself, so $! is the server's PID
  # (env and nohup exec into it) and no wrapper shell keeps our stdout open.
  (
    cd "$ROOT" || exit 1
    env -u API_TOKEN nohup "$@" < /dev/null > "$RUN_DIR/$name.log" 2>&1 &
    echo $! > "$RUN_DIR/$name.pid"
  )
}

cmd_start() {
  mkdir -p "$RUN_DIR"
  ensure_venv
  echo "Starting Investing Nexus ..."
  start_one backend "uvicorn server.main:app" "$API_PORT" \
    "$VENV/bin/python" -m uvicorn server.main:app --host 127.0.0.1 --port "$API_PORT"
  start_one site "serve_site.py --port $SITE_PORT" "$SITE_PORT" \
    "$VENV/bin/python" "$ROOT/scripts/serve_site.py" --port "$SITE_PORT"

  if ! wait_for_url "http://127.0.0.1:$API_PORT/health" 30; then
    echo "Backend did not come up. Last log lines (.run/backend.log):" >&2
    tail -n 20 "$RUN_DIR/backend.log" >&2
    cmd_stop >/dev/null
    exit 1
  fi
  if ! wait_for_url "http://127.0.0.1:$SITE_PORT/" 10; then
    echo "Site server did not come up. Last log lines (.run/site.log):" >&2
    tail -n 20 "$RUN_DIR/site.log" >&2
    cmd_stop >/dev/null
    exit 1
  fi
  echo
  echo "  Site     http://localhost:$SITE_PORT  ($(head -n 1 "$RUN_DIR/site.log"))"
  echo "  Backend  http://localhost:$API_PORT  (docs: /docs)"
  echo
  echo "Stop with: scripts/nexus.sh --stop"
}

stop_one() {  # stop_one NAME MATCH
  local pid i
  pid="$(pid_of "$1" "$2")"
  if [[ -z "$pid" ]]; then
    echo "  $1 not running"
    return 0
  fi
  kill "$pid"
  for ((i = 0; i < 40; i++)); do
    kill -0 "$pid" 2>/dev/null || break
    sleep 0.25
  done
  kill -0 "$pid" 2>/dev/null && kill -9 "$pid"
  rm -f "$RUN_DIR/$1.pid"
  echo "  $1 stopped"
}

cmd_stop() {
  echo "Stopping Investing Nexus ..."
  stop_one site "serve_site.py --port $SITE_PORT"
  stop_one backend "uvicorn server.main:app"
}

cmd_status() {
  local pid
  pid="$(pid_of site "serve_site.py --port $SITE_PORT")"
  [[ -n "$pid" ]] && echo "  site     running  pid $pid  http://localhost:$SITE_PORT" || echo "  site     stopped"
  pid="$(pid_of backend "uvicorn server.main:app")"
  [[ -n "$pid" ]] && echo "  backend  running  pid $pid  http://localhost:$API_PORT" || echo "  backend  stopped"
}

case "${1:-}" in
  --start)   cmd_start ;;
  --stop)    cmd_stop ;;
  --status)  cmd_status ;;
  --restart) cmd_stop; cmd_start ;;
  -h|--help) usage 0 ;;
  *)         usage 1 ;;
esac
