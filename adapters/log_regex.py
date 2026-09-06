"""Log-regex adapter — parse progress lines out of a plain log file.

Layout: <runs>/<arm_id>/<log_name>   (default log_name=train.log; glob allowed, e.g. "*.log")
Options (--adapter-arg):
    regex=...       Python regex with NAMED groups; numeric groups become record fields. Special names:
                    t (epoch seconds), step (iteration), ok (truthy → verified). Example:
                    regex=iter=(?P<step>\\d+).*loss=(?P<loss>[\\d.eE+-]+).*acc=(?P<acc>[\\d.]+)
    log_name=train.log
    pid_file=pid    if <runs>/<arm_id>/pid exists and that pid is alive → still running even when quiet
    done_marker=DONE
Timestamps: if the regex has no `t` group, the file's mtime is assigned to the last matched line only
(so silence detection works) and the `step` axis should be used for curves.
"""
import glob, os, re


def _alive(pid):
    try: os.kill(int(pid), 0); return True
    except (OSError, ValueError): return False


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
                        try: rec[k] = float(v) if k not in ("step",) else int(float(v))
                        except ValueError: rec[k] = v
                    if "ok" in rec: rec["ok"] = str(rec["ok"]).lower() not in ("0", "false", "no", "0.0")
                    records.append(rec)
        except OSError:
            pass
        if records and "t" not in records[-1]: records[-1]["t"] = os.path.getmtime(files[-1])
    pidf = os.path.join(d, o.get("pid_file", "pid")); running = os.path.exists(pidf) and _alive(open(pidf).read().strip())
    done = os.path.exists(os.path.join(d, o.get("done_marker", "DONE")))
    start = os.path.getctime(files[0]) if files else None
    total = arm.get("total_steps")
    prog = {"step": records[-1]["step"], "total": total} if (records and total and "step" in records[-1]) else None
    return {"records": records, "scalars": {}, "status": "done" if done else None, "start": start, "end": None,
            "progress": prog, "note": "process alive" if running else None, "src": src}
