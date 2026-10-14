#!/usr/bin/env bash
# Start the XiaomiTV debloat page (or just open it if it is already running).
# Set XIAOMITV_TV to your TV's address if it is not the default.
cd "$(dirname "$(readlink -f "$0")")/.." || exit 1
TV="${XIAOMITV_TV:-192.168.1.6}"
PORT=8080

if ss -ltn 2>/dev/null | grep -q ":$PORT "; then
  echo "Already running; opening http://127.0.0.1:$PORT"
  xdg-open "http://127.0.0.1:$PORT" >/dev/null 2>&1
  exit 0
fi

if [ ! -x .venv/bin/python ]; then
  echo "Missing .venv. Run: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
  read -r -p "Press Enter to close"
  exit 1
fi

echo "Starting XiaomiTV Debloat (TV $TV). Close this window or press Ctrl+C to stop."
.venv/bin/python -m xiaomitv --tv "$TV" --port "$PORT"
read -r -p "Stopped. Press Enter to close"
