#!/usr/bin/env python3
"""exp-dashboard collector — turns raw experiment output into one live.json (schema expdash/2).

Runs ON THE MACHINE WHERE THE DATA IS. Stdlib only, single file. Never edit it for a new experiment:
point --adapter at a small module implementing collect_arm() (see adapters/), or use the default.

    python3 collector.py --plan plan.json --lint                                  # validate the plan only
    python3 collector.py --plan plan.json --runs runs/ --out live.json --check    # lint + one tick + what each arm's data looks like
    setsid nohup python3 collector.py --plan plan.json --runs runs/ --out live.json \
        --state state.json --interval 30 < /dev/null > collector.log 2>&1 &

Adapter contract (adapters/<name>.py):
    def collect_arm(arm: dict, plan: dict, ctx: dict) -> dict
        {"records": [ {"t": epoch, "ok": bool?, "step": int?, <metric_id>: number, ...}, ... ],
         "scalars": {<scalar_id>: number},                 # adapter-known per-arm numbers (optional)
         "status": "done"|"failed"|"killed"|None,          # None → derived from timing / silence
         "start": epoch|None, "end": epoch|None, "progress": {"step": n, "total": N}|None,
         "note": str|None, "src": str}                     # src = the path you read (printed by --check)
    ctx = {"runs": <--runs>, "now": epoch, "opts": {<--adapter-arg k=v>}}

Generic here: plan validation, curves for every metric × x-axis, derived scalars, status derivation
(incl. auto-close + silence + mass-death incident), phase roll-up, status-transition event feed,
gate statistics (paired Wilcoxon / Mann-Whitney / Welch t), NaN-safe atomic writes, state.json merge.
"""
import argparse, glob, importlib.util, itertools, json, math, os, platform, re, shutil, subprocess, sys, time
from collections import Counter

# ----------------------------------------------------------------------------- basics

def num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def clean(o):
    """NaN/inf → null everywhere (a single bare NaN makes the whole file unparsable in the browser)."""
    if isinstance(o, float) and not math.isfinite(o): return None
    if isinstance(o, dict): return {k: clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)): return [clean(v) for v in o]
    return o


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
        json.dump(clean(obj), f, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    os.replace(tmp, path)


def gate_key(g):
    """Gates are addressed by id, or by the part of their name before "·" (so `logline.py gate G2 …` works)."""
    return str(g.get("id") or g.get("name") or "").split("·")[0].strip()


# ----------------------------------------------------------------------------- plan

PLOT_TYPES = ("curve", "bar", "box", "scatter", "cdf", "heatmap", "table")
DERIVE_HOWS = ("best", "last", "first", "sum", "mean", "min", "max", "count", "count_ok", "first_ok_min", "catchup")


def load_plan(path):
    plan = json.load(open(path))
    plan.setdefault("schema", "expdash/2")
    for k, v in (("budget_min", None), ("finalize_min", 0), ("silent_after_min", 10), ("metrics", []), ("scalars", []),
                 ("plots", []), ("phases", []), ("gates", []), ("hypotheses", []), ("arm_defaults", {})):
        plan.setdefault(k, v)
    if not plan.get("x_axes"): plan["x_axes"] = [{"id": "minutes", "label": "wall-clock (min)"}]
    for m in plan["metrics"]:
        m.setdefault("curve", "best_so_far"); m.setdefault("lower_is_better", True)
    mdir = {m["id"]: m["lower_is_better"] for m in plan["metrics"]}
    for s in plan["scalars"]:
        dv = s.get("derive") or {}
        if "lower_is_better" not in s: s["lower_is_better"] = mdir.get(dv.get("metric"), True)
    factors = plan.get("factors") or []
    for f in factors:
        f["levels"] = [lv if isinstance(lv, dict) else {"id": str(lv)} for lv in f.get("levels", [])]
        for lv in f["levels"]:
            lv["id"] = str(lv["id"]); lv.setdefault("label", lv["id"])
    if not plan.get("arms"):
        combos = itertools.product(*[[lv["id"] for lv in f["levels"]] for f in factors]) if factors else [()]
        plan["arms"] = [{"id": "-".join(c) or "arm", "factors": {f["id"]: c[i] for i, f in enumerate(factors)}} for c in combos]
    for a in plan["arms"]:
        for k, v in (plan["arm_defaults"] or {}).items(): a.setdefault(k, v)
        a["factors"] = {k: str(v) for k, v in (a.get("factors") or {}).items()}
        a.setdefault("budget_min", plan["budget_min"])
    if not plan["phases"]:
        plan["phases"] = [{"id": "campaign", "name": "campaign", "kind": "arms"}]
    for i, ph in enumerate(plan["phases"]):
        ph.setdefault("id", f"phase{i}"); ph.setdefault("name", ph["id"]); ph.setdefault("kind", "arms"); ph.setdefault("depends_on", [])
    for g in plan["gates"]: g.setdefault("id", gate_key(g)); g.setdefault("status", "pending")
    for h in plan["hypotheses"]: h.setdefault("status", "pending")
    return plan


def phase_of(arm, plan):
    if arm.get("phase"): return arm["phase"] if any(p["id"] == arm["phase"] for p in plan["phases"]) else None
    arms_phases = [p for p in plan["phases"] if p.get("kind", "arms") == "arms"]
    for ph in arms_phases:
        if arm["id"] in set(ph.get("arms") or []): return ph["id"]
        if ph.get("match") and re.search(ph["match"], arm["id"]): return ph["id"]
    catch_all = [p for p in arms_phases if not p.get("arms") and not p.get("match")]
    return catch_all[0]["id"] if catch_all else None


def validate_plan(plan):
    """Every id reference an agent could typo, checked up front. Returns (errors, warnings)."""
    errs, warns = [], []
    factors = plan.get("factors") or []
    fids = [f["id"] for f in factors]
    if len(set(fids)) != len(fids): errs.append("duplicate factor ids")
    for f in factors:
        ids = [lv["id"] for lv in f["levels"]]
        if not ids: errs.append(f"factor {f['id']!r} has no levels")
        if len(set(ids)) != len(ids): errs.append(f"factor {f['id']!r} has duplicate level ids")
    b = plan.get("baseline")
    if b:
        f = next((f for f in factors if f["id"] == b.get("factor")), None)
        if not f: errs.append(f"baseline.factor {b.get('factor')!r} is not a factor")
        elif not any(lv["id"] == str(b.get("level")) for lv in f["levels"]): errs.append(f"baseline.level {b.get('level')!r} is not a level of {b['factor']!r}")
    mids = [m["id"] for m in plan["metrics"]]; xids = [x["id"] for x in plan["x_axes"]]; sids = [s["id"] for s in plan["scalars"]]
    for name, ids in (("metric", mids), ("x_axis", xids), ("scalar", sids)):
        if len(set(ids)) != len(ids): errs.append(f"duplicate {name} ids")
    for m in plan["metrics"]:
        if m.get("curve") not in ("best_so_far", "raw", "cumsum"): errs.append(f"metric {m['id']}: curve must be best_so_far|raw|cumsum")
    for s in plan["scalars"]:
        dv = s.get("derive")
        if dv:
            if dv.get("how") not in DERIVE_HOWS: errs.append(f"scalar {s['id']}: derive.how {dv.get('how')!r} unknown")
            if dv.get("how") in ("best", "last", "first", "sum", "mean", "min", "max", "catchup") and dv.get("metric") not in mids:
                errs.append(f"scalar {s['id']}: derive.metric {dv.get('metric')!r} is not a declared metric")
    for p in plan["plots"]:
        pid = p.get("id", "?"); t = p.get("type", "curve")
        if t not in PLOT_TYPES: errs.append(f"plot {pid}: type {t!r} unknown"); continue
        if not p.get("id"): errs.append("a plot has no id")
        for key, pool in (("group", fids), ("color", fids), ("facet", fids), ("rows", fids), ("cols", fids)):
            if p.get(key) and p[key] not in fids: errs.append(f"plot {pid}: {key}={p[key]!r} is not a factor")
        if t == "curve":
            if p.get("y") not in mids: errs.append(f"plot {pid}: y={p.get('y')!r} is not a metric")
            if p.get("x") not in xids: errs.append(f"plot {pid}: x={p.get('x')!r} is not an x-axis")
        elif t == "scatter":
            for key in ("x", "y"):
                if p.get(key) not in sids: errs.append(f"plot {pid}: {key}={p.get(key)!r} is not a scalar")
        elif t in ("bar", "box", "cdf"):
            if p.get("y") not in sids: errs.append(f"plot {pid}: y={p.get('y')!r} is not a scalar")
            if not p.get("group"): warns.append(f"plot {pid}: no group — one bar for everything")
        elif t == "heatmap":
            if p.get("value") not in sids: errs.append(f"plot {pid}: value={p.get('value')!r} is not a scalar")
            if not p.get("rows"): errs.append(f"plot {pid}: heatmap needs rows")
        elif t == "table":
            for v in p.get("values") or []:
                if v not in sids: errs.append(f"plot {pid}: values contains {v!r}, not a scalar")
            if not p.get("rows"): errs.append(f"plot {pid}: table needs rows")
        if not p.get("explain"): warns.append(f"plot {pid}: no explain text")
    pids = [ph["id"] for ph in plan["phases"]]
    if len(set(pids)) != len(pids): errs.append("duplicate phase ids")
    by = {ph["id"]: ph for ph in plan["phases"]}
    for ph in plan["phases"]:
        for d in ph.get("depends_on") or []:
            if d not in by: errs.append(f"phase {ph['id']}: depends_on {d!r} unknown")
        if ph.get("kind") not in ("arms", "manual"): errs.append(f"phase {ph['id']}: kind must be arms|manual")
        if not ph.get("est_min"): warns.append(f"phase {ph['id']}: no est_min (ETA will rely on budgets / learned durations only)")
        if ph.get("match"):
            try: re.compile(ph["match"])
            except re.error as e: errs.append(f"phase {ph['id']}: bad match regex ({e})")
    state = {}
    def dfs(pid):
        if state.get(pid) == 1: return True
        if state.get(pid) == 2: return False
        state[pid] = 1
        cyc = any(dfs(d) for d in (by.get(pid, {}).get("depends_on") or []) if d in by)
        state[pid] = 2; return cyc
    if any(dfs(pid) for pid in by): errs.append("phase depends_on contains a cycle")
    orphans = [a["id"] for a in plan["arms"] if phase_of(a, plan) is None]
    if orphans: errs.append(f"{len(orphans)} arm(s) match no phase (check phases[].match / arms / arm.phase): {orphans[:5]}")
    for g in plan["gates"]:
        t = g.get("test")
        if not t: continue
        if t.get("kind") not in ("paired_wilcoxon", "mann_whitney", "welch_t"): errs.append(f"gate {g['id']}: test.kind unknown")
        if t.get("scalar") not in sids: errs.append(f"gate {g['id']}: test.scalar {t.get('scalar')!r} is not a scalar")
        for side in ("a", "b"):
            for fk, lv in (t.get(side) or {}).items():
                f = next((f for f in factors if f["id"] == fk), None)
                if not f or not any(l["id"] == str(lv) for l in f["levels"]): errs.append(f"gate {g['id']}: test.{side} {fk}={lv!r} is not a factor level")
        for fk in t.get("pair_by") or []:
            if fk not in fids: errs.append(f"gate {g['id']}: pair_by {fk!r} is not a factor")
    for m in plan["metrics"]:
        if "lower_is_better" not in m.get("_orig", m) and m.get("lower_is_better") is True and m.get("_defaulted"): pass
    return errs, warns


def load_adapter(path):
    if not path: return default_collect_arm
    spec = importlib.util.spec_from_file_location("expdash_adapter", path)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod.collect_arm


# ----------------------------------------------------------------------------- default adapter (jsonl events)

def default_collect_arm(arm, plan, ctx):
    """<runs>/<arm_id>/events.jsonl + optional status.json {status, end, cost_usd, ...} + optional `started` (mtime = launch)."""
    d = os.path.join(ctx["runs"], arm["id"])
    ev = os.path.join(d, "events.jsonl"); records = read_jsonl(ev)
    sp = os.path.join(d, "status.json"); st = read_json(sp, {}) or {}
    started = os.path.join(d, "started")
    start = os.path.getmtime(started) if os.path.exists(started) else None
    end = st.get("end")
    if not records and st.get("status") and os.path.exists(sp):  # result-file-only arms (sweeps): the file's time is all we know
        mt = os.path.getmtime(sp); start = start or st.get("start") or mt; end = end or mt
    scalars = {k: v for k, v in st.items() if num(v) and k not in ("end", "start")}
    return {"records": records, "scalars": scalars, "status": st.get("status"), "start": start, "end": end,
            "progress": st.get("progress"), "note": st.get("note"), "src": ev}


# ----------------------------------------------------------------------------- derivation

def downsample(points, n=250):
    if len(points) <= n: return points
    step = len(points) / (n - 1)
    return [points[int(i * step)] for i in range(n - 1)] + [points[-1]]


def ordered(records):
    """Chronological order: by t when every record has one, else the adapter's order (log/CSV order)."""
    if records and all(num(r.get("t")) for r in records): return sorted(records, key=lambda r: r["t"])
    return list(records)


def build_curves(recs, start, plan):
    xs = {}
    for xa in plan["x_axes"]:
        xid = xa["id"]; vals = []; acc = 0.0
        for i, r in enumerate(recs, 1):
            if xid == "minutes": vals.append((r["t"] - start) / 60.0 if (start and num(r.get("t"))) else None)
            elif xid == "evals": vals.append(i)
            elif xid == "step": vals.append(r.get("step") if num(r.get("step")) else i)
            else:
                v = r.get(xid)
                if xa.get("cumsum"): acc += v if num(v) else 0.0; vals.append(acc)
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
                    if best is None or (v < best if lower else v > best): best = v; pts.append([round(x, 4), v])
                elif how == "cumsum": acc += v; pts.append([round(x, 4), round(acc, 6)])
                else: pts.append([round(x, 4), v])
            per_x[xid] = downsample(pts)
        curves[mid] = per_x
    return curves


def derive_scalars(recs, start, plan, adapter_scalars):
    ext = {k: v for k, v in (adapter_scalars or {}).items() if num(v) or v is None}
    if not recs:
        out = {"n_records": 0, "n_ok": None, "n_err": None, "first_ok_min": None}
        out.update({s["id"]: None for s in plan["scalars"] if s.get("derive")}); out.update(ext); return out
    ok_recs = [r for r in recs if r.get("ok", True)]
    out = {"n_records": len(recs), "n_ok": len(ok_recs), "n_err": sum(1 for r in recs if r.get("error"))}
    first_ok = next((r["t"] for r in ok_recs if num(r.get("t"))), None)
    out["first_ok_min"] = round((first_ok - start) / 60.0, 2) if (first_ok and start) else None
    for s in plan["scalars"]:
        dv = s.get("derive")
        if not dv or dv.get("how") == "catchup": continue  # catch-up needs other arms → page-side
        how, mid = dv.get("how"), dv.get("metric")
        src = [r for r in recs if mid and num(r.get(mid)) and (r.get("ok", True) or how not in ("best", "last", "first"))]
        vals = [r[mid] for r in src]; lower = s.get("lower_is_better", True)
        out[s["id"]] = ({"best": lambda: (min(vals) if lower else max(vals)), "last": lambda: vals[-1], "first": lambda: vals[0],
                         "sum": lambda: round(sum(vals), 6), "mean": lambda: round(sum(vals) / len(vals), 6), "min": lambda: min(vals), "max": lambda: max(vals),
                         "count": lambda: len(recs), "count_ok": lambda: len(ok_recs), "first_ok_min": lambda: out["first_ok_min"]}[how]()
                        if (vals or how in ("count", "count_ok", "first_ok_min")) else None)
    out.update(ext)
    return out


def derive_status(arm, rec, plan, now):
    if rec.get("status") in ("done", "failed", "killed"): return rec["status"]
    if not rec.get("start"): return "queued"
    last = rec.get("last_event") or rec["start"]
    budget = arm.get("budget_min") or plan.get("budget_min")
    elapsed_min = (now - rec["start"]) / 60.0
    if budget and elapsed_min > budget + (plan.get("finalize_min") or 0) + plan["silent_after_min"]:
        rec["end"] = rec.get("end") or rec["start"] + budget * 60; rec["auto_closed"] = True
        rec["note"] = ((rec.get("note") or "") + " [auto-closed: budget elapsed with no status file — treat as unfinished]").strip()
        return "done"
    if (now - last) / 60.0 > plan["silent_after_min"]: return "silent"
    return "running"


FINISHED = ("done", "failed", "killed")


def roll_up_phases(plan, arms, state):
    overrides = state.get("phases", {}) if isinstance(state.get("phases"), dict) else {}
    out = []
    for ph in plan["phases"]:
        members = [a for a in arms if a.get("phase") == ph["id"]]; sts = [a["status"] for a in members]; ov = overrides.get(ph["id"], {})
        rec = {k: ph.get(k) for k in ("id", "name", "kind", "est_min", "depends_on", "purpose", "method", "criteria", "outputs", "note")}
        rec.update({"n": len(members), "n_done": sum(1 for a in members if a["status"] == "done" and not a.get("auto_closed")),
                    "n_auto_closed": sum(1 for a in members if a.get("auto_closed")), "n_finished": sum(1 for s in sts if s in FINISHED),
                    "n_running": sum(1 for s in sts if s == "running"), "n_silent": sum(1 for s in sts if s == "silent"),
                    "n_failed": sum(1 for s in sts if s in ("failed", "killed")), "arms": [a["id"] for a in members]})
        if ph.get("kind", "arms") == "arms" and members:
            if all(s in FINISHED for s in sts): status = "done"
            elif any(s != "queued" for s in sts): status = "running"
            else: status = "queued"
            starts = [a["start"] for a in members if a.get("start")]; ends = [a["end"] for a in members if a.get("end")]
            rec.update({"status": status, "start": min(starts) if starts else None, "end": max(ends) if (status == "done" and ends) else None})
        else:
            rec.update({"status": ov.get("status", "queued"), "start": ov.get("start"), "end": ov.get("end")})
        if ov.get("note"): rec["note"] = ov["note"]
        if ov.get("status") and ph.get("kind", "arms") == "arms": rec["status"] = ov["status"]
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
                        "text": f"{j - i + 1} arms went silent within {window_min} min (around {time.strftime('%H:%M UTC', time.gmtime(silent[j]))}) — credentials / host / disk?"})
        i = j + 1
    return inc


# ----------------------------------------------------------------------------- status-transition event feed (persisted across ticks)

def transitions(prev, arms, phases, now):
    """Compare with the previous tick's statuses; return auto log entries + the new snapshot."""
    events, snap = [], {"arms": {a["id"]: a["status"] + ("*" if a.get("auto_closed") else "") for a in arms}, "phases": {p["id"]: p["status"] for p in phases}}
    if prev:
        for a in arms:
            o, n = prev.get("arms", {}).get(a["id"]), snap["arms"][a["id"]]
            if o == n or o is None and n == "queued": continue
            label = {"running": "started", "done": "finished", "done*": "auto-closed (budget elapsed, no status file)", "failed": "FAILED", "killed": "killed",
                     "silent": "went silent", "queued": "reset to queued"}.get(n, n)
            events.append({"t": now, "auto": True, "text": f"arm {a['id']} {label}" + (f" (was {o})" if o and o != 'queued' else "")})
        for p in phases:
            o, n = prev.get("phases", {}).get(p["id"]), snap["phases"][p["id"]]
            if o != n and n in ("running", "done"): events.append({"t": now, "auto": True, "text": f"phase {p['name']} {'started' if n == 'running' else 'finished'}"})
    return events, snap


# ----------------------------------------------------------------------------- gate statistics (stdlib only)

def _norm_sf(z): return 0.5 * math.erfc(z / math.sqrt(2))


def _betacf(a, b, x, it=200, eps=3e-12):
    qab, qap, qam = a + b, a + 1, a - 1; c, d = 1.0, 1 - qab * x / qap
    d = 1 / (d if abs(d) > 1e-300 else 1e-300); h = d
    for m in range(1, it + 1):
        m2 = 2 * m; aa = m * (b - m) * x / ((qam + m2) * (a + m2)); d = 1 + aa * d; d = 1 / (d if abs(d) > 1e-300 else 1e-300); c = 1 + aa / (c if abs(c) > 1e-300 else 1e-300); h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2)); d = 1 + aa * d; d = 1 / (d if abs(d) > 1e-300 else 1e-300); c = 1 + aa / (c if abs(c) > 1e-300 else 1e-300); de = d * c; h *= de
        if abs(de - 1) < eps: break
    return h


def _betainc(a, b, x):
    if x <= 0: return 0.0
    if x >= 1: return 1.0
    lb = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log(1 - x)
    return math.exp(lb) * _betacf(a, b, x) / a if x < (a + 1) / (a + b + 2) else 1 - math.exp(lb) * _betacf(b, a, 1 - x) / b


def _t_sf2(t, df):  # two-sided p for Student t
    x = df / (df + t * t); return _betainc(df / 2, 0.5, x)


def _median(v): v = sorted(v); n = len(v); return None if not n else (v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2)


def compute_gate(gate, arms, plan):
    t = gate.get("test")
    if not t: return gate
    sid = t["scalar"]; sdef = next((s for s in plan["scalars"] if s["id"] == sid), {}); lower = sdef.get("lower_is_better", True)
    def sel(side): return [a for a in arms if all(a["factors"].get(k) == str(v) for k, v in (t.get(side) or {}).items())]
    A, B = sel("a"), sel("b")
    finished = lambda a: a["status"] == "done" and not a.get("auto_closed") and num(a["scalars"].get(sid))
    Af, Bf = [a for a in A if finished(a)], [a for a in B if finished(a)]
    provisional = len(Af) < len([a for a in A if a["status"] not in ("failed", "killed")]) or len(Bf) < len([a for a in B if a["status"] not in ("failed", "killed")])
    better = (lambda x, y: (y - x) / abs(y)) if lower else (lambda x, y: (x - y) / abs(y))  # relative improvement of a over b
    res = {"kind": t["kind"], "n_a": len(Af), "n_b": len(Bf), "provisional": provisional, "p": None, "effect": None, "n": 0}
    try:
        if t["kind"] == "paired_wilcoxon":
            keys = t.get("pair_by") or [f["id"] for f in plan["factors"] if f["id"] not in (t.get("a") or {})]
            kb = {tuple(b["factors"].get(k) for k in keys): b["scalars"][sid] for b in Bf}
            pairs = [(a["scalars"][sid], kb[tuple(a["factors"].get(k) for k in keys)]) for a in Af if tuple(a["factors"].get(k) for k in keys) in kb]
            d = [x - y for x, y in pairs if x != y]; n = len(d); res["n"] = len(pairs)
            if n >= 1:
                ranks = sorted(range(n), key=lambda i: abs(d[i])); r = [0.0] * n
                i = 0
                while i < n:  # average ranks for ties
                    j = i
                    while j + 1 < n and abs(d[ranks[j + 1]]) == abs(d[ranks[i]]): j += 1
                    for k in range(i, j + 1): r[ranks[k]] = (i + j) / 2 + 1
                    i = j + 1
                wp = sum(r[i] for i in range(n) if d[i] > 0); wm = sum(r[i] for i in range(n) if d[i] < 0); w = min(wp, wm)
                if n <= 12:  # exact: enumerate sign assignments
                    cnt = sum(1 for mask in range(1 << n) if min(sum(r[i] for i in range(n) if mask >> i & 1), sum(r[i] for i in range(n) if not mask >> i & 1)) <= w)
                    res["p"] = min(1.0, cnt / (1 << n))
                else:
                    mu, sd = n * (n + 1) / 4, math.sqrt(n * (n + 1) * (2 * n + 1) / 24); res["p"] = min(1.0, 2 * _norm_sf((mu - w - 0.5) / sd))
                res["effect"] = _median([better(x, y) for x, y in pairs if y]); res["stat"] = w
        elif t["kind"] == "mann_whitney":
            xa, xb = [a["scalars"][sid] for a in Af], [b["scalars"][sid] for b in Bf]; n1, n2 = len(xa), len(xb); res["n"] = n1 + n2
            if n1 and n2:
                u = sum(1 if x > y else 0.5 if x == y else 0 for x in xa for y in xb); mu, sd = n1 * n2 / 2, math.sqrt(n1 * n2 * (n1 + n2 + 1) / 12)
                res["p"] = min(1.0, 2 * _norm_sf((abs(u - mu) - 0.5) / sd)) if sd else None; res["stat"] = u
                mb = _median(xb); res["effect"] = better(_median(xa), mb) if mb else None
        elif t["kind"] == "welch_t":
            xa, xb = [a["scalars"][sid] for a in Af], [b["scalars"][sid] for b in Bf]; n1, n2 = len(xa), len(xb); res["n"] = n1 + n2
            if n1 >= 2 and n2 >= 2:
                m1, m2 = sum(xa) / n1, sum(xb) / n2; v1 = sum((x - m1) ** 2 for x in xa) / (n1 - 1); v2 = sum((x - m2) ** 2 for x in xb) / (n2 - 1)
                se = math.sqrt(v1 / n1 + v2 / n2)
                if se > 0:
                    tt = (m1 - m2) / se; df = (v1 / n1 + v2 / n2) ** 2 / ((v1 / n1) ** 2 / (n1 - 1) + (v2 / n2) ** 2 / (n2 - 1))
                    res["p"] = _t_sf2(tt, df); res["stat"] = round(tt, 3); res["df"] = round(df, 1)
                res["effect"] = better(m1, m2) if m2 else None
    except Exception as e:  # never let statistics break the page
        res["error"] = repr(e)
    alpha, min_eff = t.get("alpha", 0.05), t.get("min_effect", 0.0)
    if res["p"] is not None and res["effect"] is not None:
        res["auto_status"] = "pass" if (res["p"] <= alpha and res["effect"] >= min_eff) else "fail"
    g = dict(gate); g["result"] = res
    return g


# ----------------------------------------------------------------------------- optional probes

def collect_resources(args, plan):
    res = {}
    try: res["load"] = round(os.getloadavg()[0], 1); res["ncpu"] = os.cpu_count()
    except (OSError, AttributeError): pass
    try: du = shutil.disk_usage(args.runs); res["disk_free_gb"] = round(du.free / 1e9, 1); res["disk_pct_used"] = round(100 * du.used / du.total, 1)
    except OSError: pass
    if shutil.which("nvidia-smi"):
        try:
            out = subprocess.run(["nvidia-smi", "--query-gpu=index,utilization.gpu,memory.used,memory.total", "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=10).stdout
            res["gpus"] = [dict(zip(("id", "util", "mem_mib", "mem_total_mib"), map(int, map(str.strip, l.split(","))))) for l in out.strip().splitlines() if l.strip()]
        except Exception: pass
    if args.core_env and os.path.isdir("/proc"):  # generic: which accelerator/core ids are claimed, by which arm (arm id found in the process cmdline)
        busy, ids = {}, [a["id"].encode() for a in plan["arms"]]
        for envp in glob.glob("/proc/[0-9]*/environ"):
            try: raw = open(envp, "rb").read(); cmd = open(envp.replace("environ", "cmdline"), "rb").read()
            except OSError: continue
            for kv in raw.split(b"\x00"):
                if kv.startswith(args.core_env.encode() + b"="):
                    tag = next((i.decode() for i in ids if i in cmd), "?")
                    for c in re.findall(r"\d+", kv.split(b"=", 1)[1].decode(errors="ignore")): busy[c] = tag
        res["cores"] = busy; res["n_cores"] = args.n_cores or (max((int(c) for c in busy), default=0) + 1)
    return res


def collect_anchors(args):
    out = []
    for a in (read_json(args.anchors, []) or []) if args.anchors else []:
        vals = [v for v in a.get("values", []) if num(v)]; latest = vals[-1] if vals else None; ref = a.get("ref")
        drift = 100.0 * (latest - ref) / ref if (latest is not None and ref) else None
        out.append({"name": a.get("name"), "ref": ref, "latest": latest, "n": len(vals), "unit": a.get("unit"),
                    "drift_pct": None if drift is None else round(drift, 2), "ok": None if drift is None else abs(drift) <= a.get("tol_pct", 2.0)})
    return out


# ----------------------------------------------------------------------------- tick

def merge_by_key(base, override, keyf):
    if not override: return base or []
    out = [dict(b) for b in (base or [])]; idx = {keyf(b): i for i, b in enumerate(out)}
    for o in override:
        if not isinstance(o, dict): continue
        k = keyf(o)
        if k in idx: out[idx[k]].update({kk: vv for kk, vv in o.items() if vv not in (None, "")})
        else: out.append(o)
    return out


def tick(plan, args, adapter, now, prev):
    ctx = {"runs": args.runs, "now": now, "opts": dict(kv.split("=", 1) for kv in (args.adapter_arg or []))}
    arms, adapter_errors = [], {}
    for a in plan["arms"]:
        try: raw = adapter(a, plan, ctx) or {}
        except Exception as e: raw = {"records": [], "src": "?"}; adapter_errors[a["id"]] = repr(e)
        recs = ordered([r for r in raw.get("records") or [] if isinstance(r, dict)])
        timed = [r["t"] for r in recs if num(r.get("t"))]
        start = raw.get("start") or (min(timed) if timed else None); last_event = max(timed) if timed else None
        rec = {"id": a["id"], "factors": a["factors"], "phase": phase_of(a, plan), "budget_min": a.get("budget_min"), "total_steps": a.get("total_steps"),
               "status": raw.get("status"), "start": start, "end": raw.get("end"), "last_event": last_event, "progress": raw.get("progress"),
               "curves": build_curves(recs, start, plan), "scalars": derive_scalars(recs, start, plan, raw.get("scalars")),
               "tail": [{k: v for k, v in r.items() if k != "raw"} for r in recs[-3:]], "note": raw.get("note"), "src": raw.get("src"),
               "adapter_has_data": bool(recs) or bool(raw.get("scalars")) or bool(raw.get("status"))}
        if a["id"] in adapter_errors: rec["note"] = f"adapter error: {adapter_errors[a['id']]}"
        if rec["progress"] is None and rec["total_steps"] and recs and num(recs[-1].get("step")): rec["progress"] = {"step": recs[-1]["step"], "total": rec["total_steps"]}
        rec["status"] = derive_status(a, rec, plan, now)
        if rec["status"] in FINISHED and not rec.get("end"): rec["end"] = last_event or start
        rec["scalars"]["duration_min"] = round(((rec["end"] or now) - start) / 60.0, 2) if start else None
        arms.append(rec)
    state = read_json(args.state, {}) or {}
    phases = roll_up_phases(plan, arms, state)
    events, snap = transitions(prev.get("snap"), arms, phases, now)
    auto_log = (prev.get("auto_log") or []) + events
    prev.update({"snap": snap, "auto_log": auto_log[-200:]})
    log = [({"t": None, "text": x} if isinstance(x, str) else x) for x in state.get("log", [])] + auto_log
    log.sort(key=lambda e: e.get("t") or 0)
    incidents = [({"t": None, "severity": "warn", "text": x} if isinstance(x, str) else x) for x in state.get("incidents", [])] + auto_incidents(arms)
    gates = [compute_gate(g, arms, plan) for g in merge_by_key(plan["gates"], state.get("gates"), gate_key)]
    live = {
        "schema": "expdash/2", "name": plan.get("name"), "title": plan.get("title"), "subtitle": plan.get("subtitle"),
        "lang": plan.get("lang", "en"), "updated": now, "collector_interval_s": args.interval, "host": platform.node(),
        "plan": {k: plan.get(k) for k in ("description", "factors", "baseline", "budget_min", "finalize_min", "concurrency", "silent_after_min",
                                            "metrics", "x_axes", "scalars", "plots", "links", "notes")},
        "plan_warnings": prev.get("warnings", []),
        "hypotheses": merge_by_key(plan["hypotheses"], state.get("hypotheses"), lambda h: h.get("id")),
        "gates": gates, "notes": state.get("notes", plan.get("notes", "")),
        "phase_note": state.get("phase_note", ""), "now_doing": state.get("now_doing", ""), "now_doing_t": state.get("now_doing_t"),
        "phases": phases, "arms": arms, "anchors": collect_anchors(args), "resources": collect_resources(args, plan),
        "incidents": incidents[-40:], "log": log[-120:], "adapter_errors": adapter_errors,
    }
    starts = [a["start"] for a in arms if a.get("start")]
    live["plan"]["t0"] = plan.get("t0") or (min(starts) if starts else None)
    return live


def liveness_report(live, errs, warns):
    for e in errs: print(f"[lint] ERROR {e}")
    for w in warns: print(f"[lint] warn  {w}")
    arms = live["arms"]; with_data = [a for a in arms if a["adapter_has_data"]]
    print(f"[check] host={live['host']} arms={len(arms)} with_data={len(with_data)} statuses={dict(Counter(a['status'] for a in arms))}")
    shown = 0
    for a in arms:
        flag = "ADAPTER-ERROR " if a["id"] in live["adapter_errors"] else ""
        if shown < 15 or flag or a["adapter_has_data"] and shown < 40:
            print(f"  {a['id']:<30} {a['status']:<8} n={a['scalars']['n_records']:<5} {flag}src={a.get('src')}"); shown += 1
    if len(arms) > shown: print(f"  … {len(arms) - shown} more")
    for aid, err in list(live["adapter_errors"].items())[:5]: print(f"  adapter error on {aid}: {err}")
    return len(with_data)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--plan", required=True); ap.add_argument("--runs", default=".", help="root of per-arm data (meaning depends on the adapter)")
    ap.add_argument("--out", default="live.json"); ap.add_argument("--adapter", default=None); ap.add_argument("--adapter-arg", action="append", default=[], metavar="K=V")
    ap.add_argument("--state", default=None); ap.add_argument("--anchors", default=None); ap.add_argument("--interval", type=int, default=30)
    ap.add_argument("--core-env", default=None, help="env var whose value lists the accelerator/core ids a process holds (Linux /proc scan)"); ap.add_argument("--n-cores", type=int, default=0)
    ap.add_argument("--once", action="store_true"); ap.add_argument("--check", action="store_true"); ap.add_argument("--lint", action="store_true"); ap.add_argument("--allow-empty", action="store_true")
    args = ap.parse_args()
    plan = load_plan(args.plan); errs, warns = validate_plan(plan)
    if args.lint:
        for e in errs: print(f"ERROR {e}")
        for w in warns: print(f"warn  {w}")
        print("plan OK" if not errs else f"{len(errs)} error(s)"); sys.exit(2 if errs else 0)
    adapter = load_adapter(args.adapter)
    prev_path = args.out + ".prev.json"; prev = read_json(prev_path, {}) or {}; prev["warnings"] = warns
    if args.check:
        live = tick(plan, args, adapter, time.time(), prev); atomic_write(args.out, live)
        n = liveness_report(live, errs, warns)
        if errs: print(f"[check] FAIL: {len(errs)} plan error(s) above.", file=sys.stderr); sys.exit(2)
        if n == 0 and not args.allow_empty: print("[check] FAIL: no arm has readable data. Fix --runs / the adapter before detaching.", file=sys.stderr); sys.exit(2)
        print("[check] OK"); return
    if errs:
        for e in errs: print(f"[lint] ERROR {e}", file=sys.stderr)
        print("[collector] refusing to run with plan errors (use --lint to iterate)", file=sys.stderr); sys.exit(2)
    while True:
        t0 = time.time()
        try:
            atomic_write(args.out, tick(plan, args, adapter, t0, prev)); atomic_write(prev_path, {k: prev[k] for k in ("snap", "auto_log") if k in prev})
        except Exception as e: print(f"[collector] tick failed: {e!r}", file=sys.stderr)
        if args.once: return
        time.sleep(max(1, args.interval - (time.time() - t0)))


if __name__ == "__main__":
    main()
