"""Default adapter (identical to the one built into collector.py) — the reference to copy from.

Layout per arm:
    <runs>/<arm_id>/events.jsonl   {"t": epoch, "ok": true, "<metric>": value, ...} one per line
    <runs>/<arm_id>/status.json    {"status": "done"|"failed", "end": epoch, "cost_usd": 3.2, "note": "..."}   (optional;
                                   for sweeps that only produce a final number, this file alone is enough)
    <runs>/<arm_id>/started        empty file whose mtime is the launch time                                  (optional)
"""
import json, math, os


def _num(v): return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


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
    d = os.path.join(ctx["runs"], arm["id"])
    ev = os.path.join(d, "events.jsonl"); records = _jsonl(ev)
    sp = os.path.join(d, "status.json")
    try: st = json.load(open(sp))
    except (OSError, json.JSONDecodeError): st = {}
    started = os.path.join(d, "started")
    start = os.path.getmtime(started) if os.path.exists(started) else None
    end = st.get("end")
    if not records and st.get("status") and os.path.exists(sp):
        mt = os.path.getmtime(sp); start = start or st.get("start") or mt; end = end or mt
    scalars = {k: v for k, v in st.items() if _num(v) and k not in ("end", "start")}
    return {"records": records, "scalars": scalars, "status": st.get("status"), "start": start, "end": end,
            "progress": st.get("progress"), "note": st.get("note"), "src": ev}
