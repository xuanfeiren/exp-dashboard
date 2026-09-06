#!/bin/bash
# Regression scenarios beyond the smoke test: csv-without-timestamps RL sweep, result-file-only sweep, hostile plan.
# Usage: scripts/scenarios.sh [workdir] [port]   → prints lint/check results and writes screenshots <workdir>/<scenario>_<tab>.png
set -u
HERE="$(cd "$(dirname "$0")/.." && pwd)"; WORK="${1:-/tmp/expdash-scenarios}"; PORT="${2:-8420}"
CHROME=""; for c in "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" "$(command -v google-chrome 2>/dev/null)" "$(command -v chromium 2>/dev/null)"; do [ -n "$c" ] && [ -x "$c" ] && { CHROME="$c"; break; }; done
COL="$HERE/templates/collector.py"; rm -rf "$WORK"; python3 "$HERE/scripts/gen_scenarios.py" "$WORK" || exit 1
shot() { [ -n "$CHROME" ] || return 0; "$CHROME" --headless=new --disable-gpu --hide-scrollbars --window-size=1400,1700 --virtual-time-budget=6000 --screenshot="$WORK/$1_$2.png" "http://localhost:$PORT/$1/#tab=$2${3:-}" >/dev/null 2>&1 && echo "  screenshot $WORK/$1_$2.png"; }
fail=0
echo "== rl: csv without timestamps, step axis, higher-is-better, DONE markers =="
mkdir -p "$WORK/rl/site"; cp "$HERE/templates/dashboard.html" "$WORK/rl/site/index.html"
python3 "$COL" --plan "$WORK/rl/plan.json" --runs "$WORK/rl/runs" --out "$WORK/rl/site/live.json" --adapter "$HERE/adapters/csv_rows.py" --check | tail -4 || fail=1
python3 - "$WORK/rl/site/live.json" <<'EOF' || fail=1
import json, sys; d = json.load(open(sys.argv[1])); a = next(x for x in d["arms"] if x["status"] == "done")
pts = len(a["curves"]["reward"]["step"]); print(f"  done arm {a['id']}: reward-vs-step points = {pts} (must be > 100), progress = {a['progress']}, final = {a['scalars']['final_reward']}")
assert pts > 100, "curves collapsed"; assert a["progress"] and a["progress"]["total"] == 1000000, "arm_defaults.total_steps not applied"
g = d["gates"][0]["result"]; print(f"  gate G1: kind={g['kind']} p={g['p']} effect={g['effect']} n={g['n']} provisional={g['provisional']} auto={g.get('auto_status')}")
r = next(x for x in d["arms"] if x["status"] == "running"); print(f"  running arm {r['id']}: progress={r['progress']}")
EOF
echo "== sweep: single factor, result file only, no phases/baseline/budget =="
mkdir -p "$WORK/sweep/site"; cp "$HERE/templates/dashboard.html" "$WORK/sweep/site/index.html"
python3 "$COL" --plan "$WORK/sweep/plan.json" --runs "$WORK/sweep/runs" --out "$WORK/sweep/site/live.json" --check | tail -3 || fail=1
python3 - "$WORK/sweep/site/live.json" <<'EOF' || fail=1
import json, sys; d = json.load(open(sys.argv[1])); st = [a["status"] for a in d["arms"]]; print("  statuses:", st)
assert st.count("done") == 5 and st.count("queued") == 1, "status-only arms not recognised"
assert all(a["start"] for a in d["arms"] if a["status"] == "done"), "done arms without start (Gantt would start in 1970)"
EOF
echo "== edge: hostile plan → lint must fail; fixed plan + NaN records → page must render =="
python3 "$COL" --plan "$WORK/edge/plan.json" --lint > "$WORK/edge/lint.txt" 2>&1; rc=$?; head -6 "$WORK/edge/lint.txt" | sed 's/^/  /'
[ $rc -eq 2 ] && echo "  lint exit 2 as expected" || { echo "  LINT SHOULD HAVE FAILED"; fail=1; }
mkdir -p "$WORK/edge/site"; cp "$HERE/templates/dashboard.html" "$WORK/edge/site/index.html"
python3 "$COL" --plan "$WORK/edge/plan.fixed.json" --runs "$WORK/edge/runs" --out "$WORK/edge/site/live.json" --check | tail -2 || fail=1
python3 -c "import json,sys; json.load(open(sys.argv[1]), parse_constant=lambda c: (_ for _ in ()).throw(ValueError('bare '+c))); print('  live.json is strict JSON (no bare NaN/Infinity)')" "$WORK/edge/site/live.json" || { echo "  BARE NaN IN JSON"; fail=1; }
( cd "$WORK" && exec python3 -m http.server "$PORT" --bind 127.0.0.1 ) > "$WORK/http.log" 2>&1 & SRV=$!
sleep 1
for s in rl sweep edge; do for t in overview progress results; do shot "$s/site" "$t" ""; done; done
shot "rl/site" explore "&type=heatmap&y=final_reward&group=algo&facet=env"
if [ -n "$CHROME" ]; then for s in rl sweep edge; do
  "$CHROME" --headless=new --disable-gpu --virtual-time-budget=6000 --dump-dom "http://localhost:$PORT/$s/site/#tab=overview" 2>/dev/null | grep -o '<h1 id="title">[^<]*' | head -1 | grep -qv '…' && echo "  $s: JS rendered" || { echo "  $s: JS DID NOT RENDER"; fail=1; }
  "$CHROME" --headless=new --disable-gpu --virtual-time-budget=6000 --dump-dom "http://localhost:$PORT/$s/site/#tab=overview" 2>/dev/null | grep -q "<title>XSS" && { echo "  $s: XSS EXECUTED"; fail=1; }
done; fi
kill $SRV 2>/dev/null
[ $fail -eq 0 ] && echo "SCENARIOS OK" || { echo "SCENARIOS FAILED"; exit 1; }
