#!/bin/bash
# exp-dashboard single-campaign server: mirror live.json from the data host every PULL_EVERY s and serve this dir.
# Usage: ./serve.sh   →  http://localhost:$PORT
# Running several campaigns? Use templates/hub-serve.sh + hub.html instead (one port, sidebar of campaigns).
cd "$(dirname "$0")"
# ---------------- CONFIG ----------------
PORT=8310
REMOTE="user@datahost"                 # ssh target of the machine running collector.py; "" = local (collector writes here)
REMOTE_FILES=("~/experiments/<campaign>/live.json")
PULL_EVERY=20
# ----------------------------------------
pull() { local src="$1" dst; dst="$(basename "$src")"
  scp -q -o ConnectTimeout=8 -o BatchMode=yes "$REMOTE:$src" "$dst.tmp" 2>/dev/null && mv "$dst.tmp" "$dst"; }   # atomic: never serve a half file
if [ -n "$REMOTE" ]; then
  ( while true; do for f in "${REMOTE_FILES[@]}"; do pull "$f"; done; sleep "$PULL_EVERY"; done ) > /dev/null 2>&1 &
  PULLER=$!; trap 'kill $PULLER 2>/dev/null' EXIT
fi
echo "dashboard: http://localhost:$PORT"
exec python3 -m http.server "$PORT" --bind 127.0.0.1
