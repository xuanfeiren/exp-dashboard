#!/usr/bin/env python3
"""exp-dashboard collector — turns raw experiment output into one live.json (schema expdash/2).

Runs ON THE MACHINE WHERE THE DATA IS. Stdlib only. Never edit this file for a new experiment:
point --adapter at a small module that implements collect_arm() (see adapters/), or rely on the
default jsonl adapter.

    # liveness check: one tick, prints what every arm's data source looks like, exit 2 if nothing is readable
    python3 collector.py --plan plan.json --runs runs/ --out live.json --check
    # detached, survives ssh disconnects
    setsid nohup python3 collector.py --plan plan.json --runs runs/ --out live.json \
        --state state.json --interval 30 < /dev/null > collector.log 2>&1 &

Adapter contract (adapters/<name>.py):
    def collect_arm(arm: dict, plan: dict, ctx: dict) -> dict
        returns {"records": [ {"t": epoch, "ok": bool?, "step": int?, <metric_id>: number, ...}, ... ],
                 "scalars": {<scalar_id>: number, ...},            # optional, adapter-known scalars (cost, ...)
                 "status": "done"|"failed"|"killed"|None,          # None = let the collector derive it
                 "start": epoch|None, "end": epoch|None, "progress": {"step": n, "total": N}|None,
                 "note": str|None, "src": str}                     # src = where you read from (debugging)
    ctx = {"runs": <--runs>, "now": epoch, "opts": {<--adapter-arg k=v>}}

Everything else is generic: curves for every declared metric × x-axis, derived scalars, status
derivation, silence + mass-death detection, phase roll-up, atomic writes, hand-written state merge.
"""
import argparse, glob, importlib.util, itertools, json, os, re, shutil, subprocess, sys, time

# ----------------------------------------------------------------------------- plan

def load_plan(path):
    plan = json.load(open(path))
    plan.setdefault("schema", "expdash/2")
    plan.setdefault("budget_min", None); plan.setdefault("finalize_min", 0); plan.setdefault("silent_after_min", 10)
    plan.setdefault("metrics", []); plan.setdefault("x_axes", [{"id": "minutes", "label": "wall-clock (min)"}])
    plan.setdefault("scalars", []); plan.setdefault("plots", []); plan.setdefault("phases", [])
    for m in plan["metrics"]:
        m.setdefault("curve", "best_so_far"); m.setdefault("lower_is_better", True)
    factors = plan.get("factors") or []
    for f in factors:
        f["levels"] = [lv if isinstance(lv, dict) else {"id": str(lv)} for lv in f.get("levels", [])]
        for lv in f["levels"]:
            lv["id"] = str(lv["id"]); lv.setdefault("label", lv["id"])
    if not plan.get("arms"):
        combos = itertools.product(*[[lv["id"] for lv in f["levels"]] for f in factors]) if factors else [()]
        plan["arms"] = [{"id": "-".join(c) or "arm", "factors": {f["id"]: c[i] for i, f in enumerate(factors)}} for c in combos]
    for a in plan["arms"]:
        a.setdefault("factors", {}); a["factors"] = {k: str(v) for k, v in a["factors"].items()}
        a.setdefault("budget_min", plan["budget_min"])
    if not plan["phases"]:
        plan["phases"] = [{"id": "campaign", "name": "campaign", "kind": "arms"}]
    for i, ph in enumerate(plan["phases"]):
        ph.setdefault("id", f"phase{i}"); ph.setdefault("name", ph["id"]); ph.setdefault("kind", "arms"); ph.setdefault("depends_on", [])
    return plan


def load_adapter(path):
    if not path:
        from_default = sys.modules[__name__]
        return from_default.default_collect_arm
    spec = importlib.util.spec_from_file_location("expdash_adapter", path)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod.collect_arm


# ----------------------------------------------------------------------------- io helpers

def read_jsonl(path):
    out = []
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    try: out.append(json.loads(line))
                    except json.JSONDecodeError: pass
    except OSError:
        pass
    return out


def read_json(path, default=None):
    try: return json.load(open(path))
    except (OSError, json.JSONDecodeError, TypeError): return default


def atomic_write(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, path)


def num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


# ----------------------------------------------------------------------------- default adapter (jsonl)

def default_collect_arm(arm, plan, ctx):
    """<runs>/<arm_id>/events.jsonl + optional status.json {status, final?, end, cost_usd, note} + optional `started` file."""
    d = os.path.join(ctx["runs"], arm["id"])
    records = read_jsonl(os.path.join(d, "events.jsonl"))
    st = read_json(os.path.join(d, "status.json"), {}) or {}
    started = os.path.join(d, "started")
    start = os.path.getmtime(started) if os.path.exists(started) else (min((r.get("t", ctx["now"]) for r in records), default=None))
    scalars = {k: v for k, v in st.items() if num(v) and k not in ("end", "start")}
    return {"records": records, "scalars": scalars, "status": st.get("status"), "start": start, "end": st.get("end"),
            "progress": st.get("progress"), "note": st.get("note"), "src": os.path.join(d, "events.jsonl")}


# ----------------------------------------------------------------------------- generic derivation

def downsample(points, n=250):
    if len(points) <= n: return points
    step = len(points) / (n - 1)
    return [points[int(i * step)] for i in range(n - 1)] + [points[-1]]


def build_curves(records, start, plan):
    """curves[metric_id][x_axis_id] = [[x, y], ...] for every declared metric × x-axis."""
    recs = sorted((r for r in records if num(r.get("t"))), key=lambda r: r["t"]) if start else list(records)
    xs = {}
    for xa in plan["x_axes"]:
        xid = xa["id"]; vals = []; acc = 0.0; cnt = 0
        for r in recs:
            cnt += 1
            if xid == "minutes": vals.append((r["t"] - start) / 60.0 if start and num(r.get("t")) else None)
            elif xid == "evals": vals.append(cnt)
            elif xid == "step": vals.append(r.get("step") if num(r.get("step")) else cnt)
            else:
                v = r.get(xid)
                if xa.get("cumsum"):
                    acc += v if num(v) else 0.0; vals.append(acc)
                else: vals.append(v if num(v) else None)
        xs[xid] = vals
    curves = {}
    for m in plan["metrics"]:
        mid, how, lower = m["id"], m.get("curve", "best_so_far"), m.get("lower_is_better", True)
        per_x = {}
        for xid, xvals in xs.items():
            pts, best, acc = [], None, 0.0
            for r, x in zip(recs, xvals):
                v = r.get(mid)
                if mid == "ok" and v is None: v = 1 if r.get("ok", True) else 0
                if isinstance(v, bool): v = int(v)
                if x is None or not num(v): continue
                if how == "best_so_far":
                    if not r.get("ok", True): continue
                    if best is None or (v < best if lower else v > best):
                        best = v; pts.append([round(x, 4), v])
                elif how == "cumsum":
                    acc += v; pts.append([round(x, 4), round(acc, 6)])
                else:
                    pts.append([round(x, 4), v])
            per_x[xid] = downsample(pts)
        curves[mid] = per_x
    return curves


def merge_by_key(base, override, key):
    """plan list + state.json overrides → one list; matching entries update status/evidence, new ones append."""
    if not override: return base or []
    out = [dict(b) for b in (base or [])]; idx = {b.get(key): i for i, b in enumerate(out)}
    for o in override:
        if not isinstance(o, dict): continue
        k = o.get(key)
        if k in idx: out[idx[k]].update({kk: vv for kk, vv in o.items() if vv not in (None, "")})
        else: out.append(o)
    return out


def derive_scalars(records, start, curves, plan, adapter_scalars):
    if not records:  # queued / never-started arm: nothing is measurable yet, don't report zeros
        out = {"n_records": 0, "n_ok": None, "n_err": None, "first_ok_min": None}
        out.update({s["id"]: None for s in plan["scalars"] if s.get("derive")})
        out.update({k: v for k, v in (adapter_scalars or {}).items() if num(v) or v is None})
        return out
    ok_recs = [r for r in records if r.get("ok", True)]
    out = {"n_records": len(records), "n_ok": len(ok_recs), "n_err": sum(1 for r in records if r.get("error"))}
    first_ok = min((r["t"] for r in ok_recs if num(r.get("t"))), default=None)
    out["first_ok_min"] = round((first_ok - start) / 60.0, 2) if (first_ok and start) else None
    for s in plan["scalars"]:
        dv = s.get("derive")
        if not dv: continue
        how, mid = dv.get("how"), dv.get("metric")
        vals = [r[mid] for r in records if mid and num(r.get(mid)) and (r.get("ok", True) or how not in ("best", "last"))]
        lower = next((m.get("lower_is_better", True) for m in plan["metrics"] if m["id"] == mid), True)
        if how == "best": out[s["id"]] = (min(vals) if lower else max(vals)) if vals else None
        elif how == "last": out[s["id"]] = vals[-1] if vals else None
        elif how == "sum": out[s["id"]] = round(sum(vals), 6) if vals else None
        elif how == "mean": out[s["id"]] = round(sum(vals) / len(vals), 6) if vals else None
        elif how == "min": out[s["id"]] = min(vals) if vals else None
        elif how == "max": out[s["id"]] = max(vals) if vals else None
        elif how == "count": out[s["id"]] = len(records)
        elif how == "count_ok": out[s["id"]] = len(ok_recs)
        elif how == "first_ok_min": out[s["id"]] = out["first_ok_min"]
        # "catchup" and other cross-arm derivations are done by the page (need other arms' data)
    out.update({k: v for k, v in (adapter_scalars or {}).items() if num(v) or v is None})
    return out


def derive_status(arm, rec, plan, now):
    if rec.get("status") in ("done", "failed", "killed"):
        return rec["status"]
    if not rec.get("start"):
        return "queued"
    last = rec.get("last_event") or rec["start"]
    budget = arm.get("budget_min") or plan.get("budget_min")
    elapsed_min = (now - rec["start"]) / 60.0
    if budget and elapsed_min > budget + (plan.get("finalize_min") or 0) + plan["silent_after_min"]:
        rec["end"] = rec.get("end") or rec["start"] + budget * 60
        rec["note"] = ((rec.get("note") or "") + " [auto-closed: budget elapsed, no status file]").strip()
        return "done"
    if (now - last) / 60.0 > plan["silent_after_min"]:
        return "silent"
    return "running"


def phase_of(arm, plan):
    if arm.get("phase"): return arm["phase"]
    for ph in plan["phases"]:
        if ph.get("kind", "arms") != "arms": continue
        if arm["id"] in set(ph.get("arms") or []): return ph["id"]
        if ph.get("match") and re.search(ph["match"], arm["id"]): return ph["id"]
    arms_phases = [p for p in plan["phases"] if p.get("kind", "arms") == "arms" and not p.get("arms") and not p.get("match")]
    return arms_phases[0]["id"] if arms_phases else None


def roll_up_phases(plan, arms, state):
    overrides = state.get("phases", {}) if isinstance(state.get("phases"), dict) else {}
    out = []
    for ph in plan["phases"]:
        members = [a for a in arms if a.get("phase") == ph["id"]]
        sts = [a["status"] for a in members]
        ov = overrides.get(ph["id"], {})
        rec = {k: ph.get(k) for k in ("id", "name", "kind", "est_min", "depends_on", "purpose", "method", "criteria", "outputs", "note")}
        rec.update({"n": len(members), "n_done": sum(1 for s in sts if s in ("done", "failed", "killed")),
                    "n_running": sum(1 for s in sts if s == "running"), "n_silent": sum(1 for s in sts if s == "silent"),
                    "n_failed": sum(1 for s in sts if s in ("failed", "killed")), "arms": [a["id"] for a in members]})
        if ph.get("kind", "arms") == "arms" and members:
            if all(s in ("done", "failed", "killed") for s in sts): status = "done"
            elif any(s in ("running", "silent") for s in sts) or any(s != "queued" for s in sts): status = "running"
            else: status = "queued"
            starts = [a["start"] for a in members if a.get("start")]; ends = [a["end"] for a in members if a.get("end")]
            rec.update({"status": status, "start": min(starts) if starts else None, "end": max(ends) if (status == "done" and ends) else None})
        else:  # manual / analysis phases are driven by state.json (logline.py phase <id> running|done)
            rec.update({"status": ov.get("status", "queued"), "start": ov.get("start"), "end": ov.get("end")})
        if ov.get("note"): rec["note"] = ov["note"]
        if ov.get("status") and ph.get("kind", "arms") == "arms": rec["status"] = ov["status"]  # explicit override wins
        out.append(rec)
    return out


def auto_incidents(arms, window_min=3, k=3):
    silent = sorted(a["last_event"] for a in arms if a["status"] == "silent" and a.get("last_event"))
    inc, i = [], 0
    while i < len(silent):
        j = i
        while j + 1 < len(silent) and silent[j + 1] - silent[i] <= window_min * 60: j += 1
        if j - i + 1 >= k:
            inc.append({"t": silent[j], "severity": "error", "auto": True,
                        "text": f"{j - i + 1} arms went silent within {window_min} min (~{time.strftime('%H:%M UTC', time.gmtime(silent[j]))}) — credentials / host / disk?"})
        i = j + 1
    return inc


# ----------------------------------------------------------------------------- optional generic probes

def collect_resources(args):
    res = {}
    try: res["load"] = round(os.getloadavg()[0], 1); res["ncpu"] = os.cpu_count()
    except (OSError, AttributeError): pass
    try:
        du = shutil.disk_usage(args.runs); res["disk_free_gb"] = round(du.free / 1e9, 1); res["disk_pct_used"] = round(100 * du.used / du.total, 1)
    except OSError: pass
    if shutil.which("nvidia-smi"):
        try:
            out = subprocess.run(["nvidia-smi", "--query-gpu=index,utilization.gpu,memory.used,memory.total", "--format=csv,noheader,nounits"],
                                 capture_output=True, text=True, timeout=10).stdout
            res["gpus"] = [dict(zip(("id", "util", "mem_mib", "mem_total_mib"), map(int, map(str.strip, l.split(","))))) for l in out.strip().splitlines() if l.strip()]
        except Exception: pass
    if args.core_env and os.path.isdir("/proc"):
        busy = {}
        for envp in glob.glob("/proc/[0-9]*/environ"):
            try: raw = open(envp, "rb").read(); cmd = open(envp.replace("environ", "cmdline"), "rb").read()
            except OSError: continue
            for kv in raw.split(b"\x00"):
                if kv.startswith(args.core_env.encode() + b"="):
                    val = kv.split(b"=", 1)[1].decode(errors="ignore")
                    m = re.search(rb"--tag\x00([^\x00]+)", cmd); tag = m.group(1).decode(errors="ignore") if m else "?"
                    for c in re.findall(r"\d+", val): busy[c] = tag
        res["cores"] = busy; res["n_cores"] = args.n_cores
    return res


def collect_anchors(args):
    """--anchors JSON: [{name, ref, tol_pct, values:[...]}] → drift table."""
    out = []
    for a in (read_json(args.anchors, []) or []) if args.anchors else []:
        vals = [v for v in a.get("values", []) if num(v)]; latest = vals[-1] if vals else None; ref = a.get("ref")
        drift = 100.0 * (latest - ref) / ref if (latest is not None and ref) else None
        out.append({"name": a.get("name"), "ref": ref, "latest": latest, "n": len(vals), "unit": a.get("unit"),
                    "drift_pct": None if drift is None else round(drift, 2), "ok": None if drift is None else abs(drift) <= a.get("tol_pct", 2.0)})
    return out


# ----------------------------------------------------------------------------- tick

def tick(plan, args, adapter, now):
    ctx = {"runs": args.runs, "now": now, "opts": dict(kv.split("=", 1) for kv in (args.adapter_arg or []))}
    arms = []
    for a in plan["arms"]:
        try:
            raw = adapter(a, plan, ctx) or {}
        except Exception as e:
            raw = {"records": [], "note": f"adapter error: {e!r}", "src": "?"}
        records = [r for r in raw.get("records") or [] if isinstance(r, dict)]
        start = raw.get("start") or (min((r["t"] for r in records if num(r.get("t"))), default=None))
        last_event = max((r["t"] for r in records if num(r.get("t"))), default=None)
        curves = build_curves(records, start, plan)
        rec = {"id": a["id"], "factors": a["factors"], "phase": phase_of(a, plan), "budget_min": a.get("budget_min"),
               "status": raw.get("status"), "start": start, "end": raw.get("end"), "last_event": last_event,
               "progress": raw.get("progress"), "curves": curves,
               "scalars": derive_scalars(records, start, curves, plan, raw.get("scalars")),
               "tail": [{k: v for k, v in r.items() if k != "raw"} for r in records[-3:]],
               "note": raw.get("note"), "src": raw.get("src")}
        rec["status"] = derive_status(a, rec, plan, now)
        if rec["status"] in ("done", "failed", "killed") and not rec.get("end"): rec["end"] = last_event or now
        rec["scalars"]["duration_min"] = round(((rec["end"] or now) - start) / 60.0, 2) if start else None
        arms.append(rec)
    state = read_json(args.state, {}) or {}
    log = [({"t": None, "text": x} if isinstance(x, str) else x) for x in state.get("log", [])]
    incidents = [({"t": None, "severity": "warn", "text": x} if isinstance(x, str) else x) for x in state.get("incidents", [])] + auto_incidents(arms)
    live = {
        "schema": "expdash/2", "name": plan.get("name"), "title": plan.get("title"), "subtitle": plan.get("subtitle"),
        "lang": plan.get("lang", "en"), "updated": now, "collector_interval_s": args.interval, "host": os.uname().nodename,
        "plan": {k: plan.get(k) for k in ("description", "factors", "baseline", "budget_min", "finalize_min", "concurrency", "silent_after_min",
                                            "metrics", "x_axes", "scalars", "plots", "links", "notes")},
        "hypotheses": merge_by_key(plan.get("hypotheses", []), state.get("hypotheses"), "id"),
        "gates": merge_by_key(plan.get("gates", []), state.get("gates"), "name"),
        "notes": state.get("notes", plan.get("notes", "")),
        "phase_note": state.get("phase_note", ""), "now_doing": state.get("now_doing", ""),
        "phases": roll_up_phases(plan, arms, state),
        "arms": arms,
        "anchors": collect_anchors(args), "resources": collect_resources(args),
        "incidents": incidents[-40:], "log": log[-80:],
    }
    starts = [a["start"] for a in arms if a.get("start")]
    live["plan"]["t0"] = plan.get("t0") or (min(starts) if starts else None)
    return live


def liveness_report(live):
    with_data = [a for a in live["arms"] if a["scalars"]["n_records"] > 0]
    from collections import Counter
    print(f"[check] host={live['host']} arms={len(live['arms'])} with_data={len(with_data)} statuses={dict(Counter(a['status'] for a in live['arms']))}")
    for a in live["arms"][:15]:
        print(f"  {a['id']:<30} {a['status']:<8} n={a['scalars']['n_records']:<4} src={a.get('src')}")
    if len(live["arms"]) > 15: print(f"  … {len(live['arms']) - 15} more")
    return len(with_data)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--plan", required=True); ap.add_argument("--runs", required=True, help="root of per-arm data (meaning depends on the adapter)")
    ap.add_argument("--out", required=True, help="live.json path (written atomically)")
    ap.add_argument("--adapter", default=None, help="python file exposing collect_arm(arm, plan, ctx); default = jsonl events")
    ap.add_argument("--adapter-arg", action="append", default=[], metavar="K=V")
    ap.add_argument("--state", default=None, help="hand-maintained JSON (scripts/logline.py writes it)")
    ap.add_argument("--anchors", default=None); ap.add_argument("--interval", type=int, default=30)
    ap.add_argument("--core-env", default=None, help="env var to scan in /proc for busy cores (Linux)"); ap.add_argument("--n-cores", type=int, default=64)
    ap.add_argument("--once", action="store_true"); ap.add_argument("--check", action="store_true"); ap.add_argument("--allow-empty", action="store_true")
    args = ap.parse_args()
    plan = load_plan(args.plan); adapter = load_adapter(args.adapter)
    if args.check:
        live = tick(plan, args, adapter, time.time()); atomic_write(args.out, live)
        n = liveness_report(live)
        if n == 0 and not args.allow_empty:
            print("[check] FAIL: no arm has readable data. Fix --runs / the adapter before detaching.", file=sys.stderr); sys.exit(2)
        print("[check] OK"); return
    while True:
        t0 = time.time()
        try: atomic_write(args.out, tick(plan, args, adapter, t0))
        except Exception as e: print(f"[collector] tick failed: {e!r}", file=sys.stderr)
        if args.once: return
        time.sleep(max(1, args.interval - (time.time() - t0)))


if __name__ == "__main__":
    main()
