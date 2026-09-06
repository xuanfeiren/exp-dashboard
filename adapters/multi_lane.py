"""Multi-lane adapter — an arm is a TEAM of parallel workers ("lanes"), each with its own events file;
the arm's record stream is the union of lane records, so best_so_far curves become best-over-team.

Layout: <runs>/<arm_id>/<lane>/events.jsonl   (lane dirs matched by lane_glob, default "w*")
        <runs>/<arm_id>/status.json            optional {status, end, cost_usd, ...}
Options (--adapter-arg):
    lane_glob=w*
    live_root=/tmp/sandboxes      optional second root where lanes write WHILE running (harnesses that only
                                  copy results into <runs> at the end). Pattern: <live_root>/*<arm_id>*/<lane>/events.jsonl
Each record gets a "lane" field so the page can show per-lane detail.
"""
import glob, json, os


def _jsonl(path):
    out = []
    try:
        for line in open(path):
            line = line.strip()
            if line:
                try: out.append(json.loads(line))
                except json.JSONDecodeError: pass
    except OSError:
        pass
    return out


def collect_arm(arm, plan, ctx):
    o = ctx["opts"]; d = os.path.join(ctx["runs"], arm["id"]); lane_glob = o.get("lane_glob", "w*")
    files = sorted(glob.glob(os.path.join(d, lane_glob, "events.jsonl")))
    if o.get("live_root"):
        live = sorted(glob.glob(os.path.join(o["live_root"], f"*{arm['id']}*", lane_glob, "events.jsonl")))
        if live: files = live  # prefer the live sandbox while it exists
    records = []
    for f in files:
        lane = os.path.basename(os.path.dirname(f))
        for r in _jsonl(f):
            r["lane"] = lane; records.append(r)
    records.sort(key=lambda r: r.get("t", 0))
    try: st = json.load(open(os.path.join(d, "status.json")))
    except (OSError, json.JSONDecodeError): st = {}
    scalars = {k: v for k, v in st.items() if isinstance(v, (int, float)) and not isinstance(v, bool) and k not in ("end", "start")}
    scalars["n_lanes"] = len(files)
    return {"records": records, "scalars": scalars, "status": st.get("status"), "start": st.get("start"), "end": st.get("end"),
            "progress": None, "note": st.get("note"), "src": files[0] if files else os.path.join(d, lane_glob, "events.jsonl")}
