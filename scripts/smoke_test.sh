#!/bin/bash
# End-to-end smoke test: fake campaign → collector → live.json → http.server → headless screenshots of every tab.
# Usage: scripts/smoke_test.sh [workdir] [port] [wait_s]
# Then LOOK at the screenshots (Read tool / open the PNGs) before wiring the dashboard to a real experiment.
set -u
HERE="$(cd "$(dirname "$0")/.." && pwd)"
WORK="${1:-/tmp/expdash-smoke}"; PORT="${2:-8399}"; WAIT="${3:-60}"
CHROME=""; for c in "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" "$(command -v google-chrome 2>/dev/null)" "$(command -v chromium 2>/dev/null)" "$(command -v chromium-browser 2>/dev/null)"; do [ -n "$c" ] && [ -x "$c" ] && { CHROME="$c"; break; }; done
pkill -f "http.server $PORT" 2>/dev/null; pkill -f "collector.py --plan $WORK" 2>/dev/null; pkill -f "simulate.py --out $WORK" 2>/dev/null
rm -rf "$WORK"; mkdir -p "$WORK/site"
python3 "$HERE/scripts/simulate.py" --out "$WORK" --backfill 2 --silent 1 --duration 900 > "$WORK/sim.log" 2>&1 &
sleep 3
echo "== liveness check (a real collector must pass this before being detached) =="
python3 "$HERE/templates/collector.py" --plan "$WORK/plan.json" --runs "$WORK/runs" --out "$WORK/site/live.json" \
  --state "$WORK/state.json" --anchors "$WORK/anchors.json" --check || { echo "liveness check FAILED"; exit 2; }
python3 "$HERE/templates/collector.py" --plan "$WORK/plan.json" --runs "$WORK/runs" --out "$WORK/site/live.json" \
  --state "$WORK/state.json" --anchors "$WORK/anchors.json" --interval 3 > "$WORK/collector.log" 2>&1 &
cp "$HERE/templates/dashboard.html" "$WORK/site/index.html"
( cd "$WORK/site" && exec python3 -m http.server "$PORT" --bind 127.0.0.1 ) > "$WORK/http.log" 2>&1 &
echo "== dashboard: http://localhost:$PORT  (waiting ${WAIT}s so done/running/silent/queued arms coexist) =="
sleep "$WAIT"
python3 "$HERE/scripts/logline.py" "$WORK/state.json" gate G1 pass "manual verdict example (demo)" > /dev/null
python3 "$HERE/scripts/logline.py" "$WORK/state.json" hypothesis H1 supported "both channels below baseline on taskA (demo)" > /dev/null
sleep 4
python3 - "$WORK/site/live.json" <<'EOF'
import json, sys, time, collections
d = json.load(open(sys.argv[1]))
print("heartbeat age s:", round(time.time() - d["updated"], 1), "| arms:", dict(collections.Counter(a["status"] for a in d["arms"])),
      "| phases:", [(p["id"], p["status"], f'{p["n_done"]}/{p["n"]}') for p in d["phases"]], "| incidents:", len(d["incidents"]))
a = next(x for x in d["arms"] if x["status"] == "done"); print("sample done arm curves:", {m: {x: len(v) for x, v in xs.items()} for m, xs in a["curves"].items()}, "scalars:", a["scalars"])
EOF
if [ -n "$CHROME" ]; then
  for tab in overview plan progress results explore ops; do
    "$CHROME" --headless=new --disable-gpu --hide-scrollbars --window-size=1400,2400 --virtual-time-budget=6000 \
      --screenshot="$WORK/shot_$tab.png" "http://localhost:$PORT/#tab=$tab" > /dev/null 2>&1 && echo "screenshot: $WORK/shot_$tab.png"
  done
  "$CHROME" --headless=new --disable-gpu --virtual-time-budget=6000 --dump-dom "http://localhost:$PORT/#tab=overview" 2>/dev/null | grep -o '<h1 id="title">[^<]*' | head -1 | grep -qv '…' && echo "JS rendered title: OK" || echo "JS DID NOT RENDER (title still placeholder) — open the page and check the console"
else
  echo "(no Chrome/Chromium found; open http://localhost:$PORT manually)"
fi
echo "collector.log tail:"; tail -3 "$WORK/collector.log"
echo "stop with: pkill -f 'http.server $PORT'; pkill -f 'collector.py --plan $WORK'; pkill -f 'simulate.py --out $WORK'"
