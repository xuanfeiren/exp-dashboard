"""Log-regex adapter — parse progress lines out of a plain log file.

Layout: <runs>/<arm_id>/<log_name>   (default log_name=train.log; glob allowed, e.g. "*.log")
Options (--adapter-arg):
    regex=...       Python regex with NAMED groups; numeric groups become record fields. Special names:
                    t (epoch seconds), step (iteration), ok (truthy → valid row). Example:
                    regex=iter=(?P<step>\\d+).*loss=(?P<loss>[\\d.eE+-]+).*acc=(?P<acc>[\\d.]+)
    log_name=train.log
    pid_file=pid    <runs>/<arm_id>/pid with a live pid → still running even when quiet
    done_marker=DONE
Timestamps: if the regex has no `t` group, matched lines are spread evenly between the file's creation
time and its mtime (approximate; use the `step` x-axis for real curves).
"""
import glob, os, re


def _alive(pid):
    try: os.kill(int(pid), 0); return True
    except (OSError, ValueError): return False


def _birth(path):
    st = os.stat(path); return min(getattr(st, "st_birthtime", None) or st.st_ctime, st.st_mtime)


def _started(runs, arm_id):
    """<runs>/<arm_id>/started or <runs>/<arm_id>.started: an empty file whose mtime is the launch time (write it from your runner)."""
    for p in (os.path.join(runs, arm_id, "started"), os.path.join(runs, arm_id + ".started")):
        if os.path.exists(p): return os.path.getmtime(p)
    return None


def collect_arm(arm, plan, ctx):
    o = ctx["opts"]; d = os.path.join(ctx["runs"], arm["id"])
    rx = re.compile(o["regex"]) if o.get("regex") else None
    files = sorted(glob.glob(os.path.join(d, o.get("log_name", "train.log"))))
    records, src = [], (files[-1] if files else os.path.join(d, o.get("log_name", "train.log")))
    if rx and files:
        try:
            with open(files[-1], errors="ignore") as f:
                for line in f:
                    m = rx.search(line)
                    if not m: continue
                    rec = {}
                    for k, v in m.groupdict().items():
                        if v is None: continue
                        try: rec[k] = int(float(v)) if k == "step" else float(v)
                        except ValueError: rec[k] = v
                    if "ok" in rec: rec["ok"] = str(rec["ok"]).lower() not in ("0", "false", "no", "0.0")
                    records.append(rec)
        except OSError:
            pass
    start = None
    if records and not all(isinstance(r.get("t"), float) for r in records):
        t0, t1 = _started(ctx["runs"], arm["id"]) or _birth(files[-1]), os.path.getmtime(files[-1]); n = len(records)
        for i, r in enumerate(records): r.setdefault("t", t0 + (t1 - t0) * (i / (n - 1) if n > 1 else 1.0))
        start = t0
    pidf = os.path.join(d, o.get("pid_file", "pid")); running = os.path.exists(pidf) and _alive(open(pidf).read().strip())
    done = os.path.exists(os.path.join(d, o.get("done_marker", "DONE")))
    total = arm.get("total_steps")
    prog = {"step": records[-1]["step"], "total": total} if (records and total and "step" in records[-1]) else None
    return {"records": records, "scalars": {}, "status": "done" if done else None, "start": start or _started(ctx["runs"], arm["id"]) or (_birth(files[0]) if files else None), "end": None,
            "progress": prog, "note": "process alive" if running else None, "src": src}
