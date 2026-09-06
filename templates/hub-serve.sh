#!/bin/bash
# exp-dashboard hub: one local port, many campaigns. Each campaign is a sub-directory holding index.html + live.json.
#   ~/dashboard/
#     hub.html            (copy of templates/hub.html, served as /)
#     campaigns.json      [{"name":"b1","title":"Benchmark campaign","path":"b1/"}, ...]  ← hub sidebar
#     pull.list           one line per file to mirror:  <ssh-target>:<remote path>  <local path>
#     b1/ → symlink to ~/b1-dashboard   (index.html, live.json)
# Usage: ./hub-serve.sh   →  http://localhost:8300
cd "$(dirname "$0")"
PORT="${PORT:-8300}"; PULL_EVERY="${PULL_EVERY:-20}"
[ -f hub.html ] && [ ! -e index.html ] && ln -s hub.html index.html
pull_all() {
  [ -f pull.list ] || return
  while read -r src dst; do
    [ -z "$src" ] && continue; case "$src" in \#*) continue;; esac
    mkdir -p "$(dirname "$dst")"
    scp -q -o ConnectTimeout=8 -o BatchMode=yes "$src" "$dst.tmp" 2>/dev/null && mv "$dst.tmp" "$dst"
  done < pull.list
}
( while true; do pull_all; sleep "$PULL_EVERY"; done ) > /dev/null 2>&1 &
PULLER=$!; trap 'kill $PULLER 2>/dev/null' EXIT
echo "hub: http://localhost:$PORT"
exec python3 -m http.server "$PORT" --bind 127.0.0.1
