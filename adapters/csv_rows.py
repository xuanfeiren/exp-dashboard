"""CSV adapter — one metrics CSV per arm (training loops, sweeps).

Layout: <runs>/<arm_id>.csv  or  <runs>/<arm_id>/metrics.csv   with a header row.
Options (--adapter-arg):
    time_col=t          column holding epoch seconds (default "t"; if absent, file mtime is used for the last row
                        and the `minutes` axis is unavailable — use x_axes "step" instead)
    step_col=step       column holding the iteration index
    ok_col=             column whose truthiness marks a verified/valid row (default: all rows ok)
    done_marker=DONE    a file <runs>/<arm_id>/DONE (or <arm_id>.DONE) marks the arm finished
"""
import csv, os


def _num(s):
    try: return float(s)
    except (TypeError, ValueError): return None


def collect_arm(arm, plan, ctx):
    o = ctx["opts"]; runs = ctx["runs"]
    cands = [os.path.join(runs, arm["id"] + ".csv"), os.path.join(runs, arm["id"], "metrics.csv")]
    path = next((p for p in cands if os.path.exists(p)), cands[0])
    tcol, scol, okcol = o.get("time_col", "t"), o.get("step_col", "step"), o.get("ok_col")
    records = []
    try:
        with open(path, newline="") as f:
            for row in csv.DictReader(f):
                rec = {k: (_num(v) if _num(v) is not None else v) for k, v in row.items() if k}
                if tcol in rec and isinstance(rec[tcol], float): rec["t"] = rec.pop(tcol)
                if scol in rec and isinstance(rec[scol], float): rec["step"] = int(rec.pop(scol))
                if okcol: rec["ok"] = str(row.get(okcol, "1")).strip().lower() not in ("0", "false", "no", "")
                records.append(rec)
    except OSError:
        pass
    if records and "t" not in records[-1] and os.path.exists(path):
        records[-1]["t"] = os.path.getmtime(path)  # at least make last_event meaningful for silence detection
    marker = o.get("done_marker", "DONE")
    done = os.path.exists(os.path.join(runs, arm["id"], marker)) or os.path.exists(os.path.join(runs, arm["id"] + "." + marker))
    total = arm.get("total_steps")
    prog = {"step": records[-1]["step"], "total": total} if (records and total and "step" in records[-1]) else None
    return {"records": records, "scalars": {}, "status": "done" if done else None, "start": None, "end": None,
            "progress": prog, "note": None, "src": path}
