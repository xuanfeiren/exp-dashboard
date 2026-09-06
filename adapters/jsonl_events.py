"""Default adapter (same as the one built into collector.py) — kept here as the reference to copy.

Layout per arm:
    <runs>/<arm_id>/events.jsonl   {"t": epoch, "ok": true, "<metric>": value, ...} one per line
    <runs>/<arm_id>/status.json    {"status": "done"|"failed", "end": epoch, "cost_usd": 3.2, "note": "..."}   (optional)
    <runs>/<arm_id>/started        empty file whose mtime is the launch time                                  (optional)
"""
import json, os


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
    records = _jsonl(os.path.join(d, "events.jsonl"))
    try: st = json.load(open(os.path.join(d, "status.json")))
    except (OSError, json.JSONDecodeError): st = {}
    started = os.path.join(d, "started")
    start = os.path.getmtime(started) if os.path.exists(started) else None
    scalars = {k: v for k, v in st.items() if isinstance(v, (int, float)) and not isinstance(v, bool) and k not in ("end", "start")}
    return {"records": records, "scalars": scalars, "status": st.get("status"), "start": start, "end": st.get("end"),
            "progress": st.get("progress"), "note": st.get("note"), "src": os.path.join(d, "events.jsonl")}
