#!/usr/bin/env python3
"""Fake campaign for smoke-testing the whole pipeline (plan → collector → live.json → page).

    python3 simulate.py --out /tmp/expdash-smoke --backfill 2 --silent 1 --duration 900

Writes <out>/plan.json (from templates/plan.example.json, budgets shortened), state.json, anchors.json
and streams records into <out>/runs/<arm_id>/events.jsonl in the default adapter's format, with real
wall-clock timestamps so ETA / silence / auto-close logic is exercised for real. After ~60 s the page
shows done + running + silent + queued arms simultaneously.
"""
import argparse, json, math, os, random, time

EXAMPLE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "templates", "plan.example.json")
BASE = {"taskA": 120.0, "taskB": 4800.0}
FACTOR = {"baseline": 1.0, "lessons": 0.85, "code": 0.72}
TOKENS = {"baseline": 1.6, "lessons": 1.3, "code": 0.9}  # M tokens per eval


def write_plan(out, budget_min):
    plan = json.load(open(EXAMPLE))
    plan.update({"name": "smoke", "title": "exp-dashboard smoke test (simulated data)", "lang": plan.get("lang", "en"),
                 "subtitle": "3 conditions × 2 tasks × 2 seeds · %g min per arm · 4 concurrent · every number is fake" % budget_min,
                 "budget_min": budget_min, "finalize_min": 0, "concurrency": 4, "silent_after_min": 0.5})
    for ph in plan["phases"]:
        if ph["kind"] == "arms": ph["est_min"] = round(budget_min * (1 if ph["id"] == "smoke" else 1.6), 1)
        else: ph["est_min"] = 3
    arms = []
    for t in ("taskA", "taskB"): arms.append({"id": f"S-baseline-{t}-s1", "factors": {"condition": "baseline", "task": t, "seed": "1"}})
    for c in ("lessons", "code"):
        for t in ("taskA", "taskB"): arms.append({"id": f"W1-{c}-{t}-s1", "factors": {"condition": c, "task": t, "seed": "1"}})
    for c in ("baseline", "lessons", "code"):
        for t in ("taskA", "taskB"): arms.append({"id": f"W2-{c}-{t}-s2", "factors": {"condition": c, "task": t, "seed": "2"}})
    plan["arms"] = arms
    json.dump(plan, open(os.path.join(out, "plan.json"), "w"), ensure_ascii=False, indent=1)
    return plan


def value_at(arm, frac, rng):
    c, t = arm["factors"]["condition"], arm["factors"]["task"]
    floor = BASE[t] * FACTOR[c] * rng.uniform(0.95, 1.05); start = BASE[t] * 3.0
    return floor + (start - floor) * math.exp(-4.0 * frac) * rng.uniform(0.8, 1.6)


def emit(d, ev):
    with open(os.path.join(d, "events.jsonl"), "a") as f: f.write(json.dumps(ev) + "\n")


def record(arm, frac, rng, t):
    ok = rng.random() < 0.85
    tok = TOKENS[arm["factors"]["condition"]] * rng.uniform(0.6, 1.4)
    if ok: return {"t": t, "ok": True, "latency_us": round(value_at(arm, frac, rng), 3), "tokens_m": round(tok, 3)}
    return {"t": t, "ok": False, "error": rng.choice(["compile: sbuf overflow", "execute: nan in output", "timeout"]), "tokens_m": round(tok, 3)}


def backfill(out, arm, budget_s, now):
    d = os.path.join(out, "runs", arm["id"]); os.makedirs(d, exist_ok=True)
    rng = random.Random(arm["id"]); start = now - budget_s - 300
    open(os.path.join(d, "started"), "w").close(); os.utime(os.path.join(d, "started"), (start, start))
    for i in range(18): emit(d, record(arm, (i + 1) / 19, rng, start + budget_s * (i + 1) / 19))
    json.dump({"status": "done", "end": start + budget_s, "cost_usd": round(rng.uniform(3, 9), 2)}, open(os.path.join(d, "status.json"), "w"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True); ap.add_argument("--budget-min", type=float, default=2.0)
    ap.add_argument("--backfill", type=int, default=2); ap.add_argument("--silent", type=int, default=1)
    ap.add_argument("--duration", type=int, default=900); ap.add_argument("--concurrency", type=int, default=4)
    args = ap.parse_args()
    os.makedirs(os.path.join(args.out, "runs"), exist_ok=True)
    plan = write_plan(args.out, args.budget_min); budget_s = args.budget_min * 60; now = time.time()
    json.dump([{"name": "reference kernel A", "ref": 28.39, "unit": "µs", "tol_pct": 2.0, "values": [28.41, 28.33, 28.52]},
               {"name": "reference kernel B", "ref": 95.67, "unit": "µs", "tol_pct": 2.0, "values": [95.9, 98.4]}], open(os.path.join(args.out, "anchors.json"), "w"))
    state = {"phase_note": "Wave 1 running; smoke arms finished and passed their criteria.",
             "now_doing": "Launching wave 1 (4 arms in parallel); wave 2 queued behind it; analysis starts when wave 2 finishes.",
             "log": [{"t": now - 900, "text": "T0: smoke arms launched (2 arms)"}, {"t": now - 600, "text": "smoke passed criteria → launching wave 1"},
                     {"t": now, "text": "wave 1 launched (4 arms); wave 2 queued (6 arms)"}],
             "incidents": [{"t": now - 620, "severity": "warn", "text": "S-baseline-taskB-s1: compile cache hit 12 GB, cleaned"}],
             "phases": {"analysis": {"status": "queued"}}}
    json.dump(state, open(os.path.join(args.out, "state.json"), "w"), ensure_ascii=False, indent=1)
    arms = plan["arms"]
    for a in arms[:args.backfill]: backfill(args.out, a, budget_s, now)
    pending = arms[args.backfill:]; running = []; silent_left = args.silent; t_end = now + args.duration
    while time.time() < t_end:
        t = time.time()
        while pending and len(running) < args.concurrency:
            a = pending.pop(0); d = os.path.join(args.out, "runs", a["id"]); os.makedirs(d, exist_ok=True)
            open(os.path.join(d, "started"), "w").close()
            running.append([a, t, random.Random(a["id"] + "x"), silent_left > 0]); silent_left -= 1
        for r in list(running):
            a, start, rng, is_silent = r; frac = (t - start) / budget_s; d = os.path.join(args.out, "runs", a["id"])
            if frac >= 1.0:
                json.dump({"status": "done", "end": t, "cost_usd": round(rng.uniform(3, 9), 2)}, open(os.path.join(d, "status.json"), "w"))
                running.remove(r); continue
            if is_silent and frac > 0.4: continue
            if rng.random() < 0.6: emit(d, record(a, frac, rng, t))
        if not running and not pending: break
        time.sleep(2)


if __name__ == "__main__":
    main()
