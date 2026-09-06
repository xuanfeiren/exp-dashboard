"""CSV adapter — one metrics CSV per arm (training loops, sweeps).

Layout: <runs>/<arm_id>.csv  or  <runs>/<arm_id>/metrics.csv   with a header row.
Options (--adapter-arg):
    time_col=t          column holding epoch seconds. STRONGLY RECOMMENDED. Without it, timestamps are
                        synthesised by spreading rows evenly between the file's creation time and its mtime
                        (good enough for silence detection and rough wall-clock curves; use x_axes "step" for real curves).
                        A `<runs>/<arm>.started` (or <arm>/started) marker file sets the launch time precisely.
    step_col=step       column holding the iteration index (→ `step` x-axis and progress % when arm.total_steps is set)
    ok_col=             column whose truthiness marks a valid row (default: all rows ok)
    done_marker=DONE    <runs>/<arm_id>/DONE or <runs>/<arm_id>.DONE marks the arm finished. Have your runner touch it —
                        otherwise a finished run looks "silent" after silent_after_min.
"""
import csv, os


def _num(s):
    try:
        v = float(s); return v if v == v and abs(v) != float("inf") else None
    except (TypeError, ValueError): return None


def _birth(path):
    st = os.stat(path); return min(getattr(st, "st_birthtime", None) or st.st_ctime, st.st_mtime)


def _started(runs, arm_id):
    """<runs>/<arm_id>/started or <runs>/<arm_id>.started: an empty file whose mtime is the launch time (write it from your runner)."""
    for p in (os.path.join(runs, arm_id, "started"), os.path.join(runs, arm_id + ".started")):
        if os.path.exists(p): return os.path.getmtime(p)
    return None


def collect_arm(arm, plan, ctx):
    o = ctx["opts"]; runs = ctx["runs"]
    cands = [os.path.join(runs, arm["id"] + ".csv"), os.path.join(runs, arm["id"], "metrics.csv")]
    path = next((p for p in cands if os.path.exists(p)), cands[0])
    tcol, scol, okcol = o.get("time_col", "t"), o.get("step_col", "step"), o.get("ok_col")
    records = []
    try:
        with open(path, newline="") as f:
            for row in csv.DictReader(f):
                rec = {}
                for k, v in row.items():
                    if not k: continue
                    n = _num(v); rec[k] = n if n is not None else v
                if isinstance(rec.get(tcol), float): rec["t"] = rec.pop(tcol)
                if isinstance(rec.get(scol), float): rec["step"] = int(rec.pop(scol))
                if okcol: rec["ok"] = str(row.get(okcol, "1")).strip().lower() not in ("0", "false", "no", "")
                records.append(rec)
    except OSError:
        pass
    start = None
    if records and os.path.exists(path) and not all(isinstance(r.get("t"), float) for r in records):
        t0, t1 = _started(runs, arm["id"]) or _birth(path), os.path.getmtime(path); n = len(records)
        for i, r in enumerate(records): r.setdefault("t", t0 + (t1 - t0) * (i / (n - 1) if n > 1 else 1.0))
        start = t0
    marker = o.get("done_marker", "DONE")
    done = os.path.exists(os.path.join(runs, arm["id"], marker)) or os.path.exists(os.path.join(runs, arm["id"] + "." + marker))
    total = arm.get("total_steps")
    prog = {"step": records[-1]["step"], "total": total} if (records and total and "step" in records[-1]) else None
    return {"records": records, "scalars": {}, "status": "done" if done else None, "start": start or _started(runs, arm["id"]), "end": None, "progress": prog, "note": None, "src": path}
