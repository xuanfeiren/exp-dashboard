#!/usr/bin/env python3
"""Generate three regression scenarios that broke earlier versions (used by scripts/scenarios.sh):

  rl     RL-style training: 3 algorithms × 2 envs × 3 seeds, one metrics CSV per arm WITHOUT a timestamp column,
         x = step, raw higher-is-better metric, DONE markers → exercises adapters/csv_rows.py, step curves, progress %,
         learned durations.
  sweep  Single factor, no phases, no baseline, no budget; arms have ONLY a status.json with a final number
         → exercises result-file-only arms, 1-D matrix, bar/table with one factor, Explore defaults.
  edge   Hostile plan: NaN records, unicode ids, XSS strings, typo'd plot ids, log-scale ≤0 values, unmatched phase regex
         → `--lint` must FAIL with a clear list; the page must survive the NaN when run with a fixed plan.

    python3 gen_scenarios.py <outdir>          # writes <outdir>/{rl,sweep,edge}/{plan.json,runs/}
"""
import json, math, os, random, sys, time

out = sys.argv[1] if len(sys.argv) > 1 else "/tmp/expdash-scenarios"
now = time.time()


def w(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f: json.dump(obj, f, ensure_ascii=False, indent=1)


# ---------------------------------------------------------------- rl (csv, no timestamp column)
rl = os.path.join(out, "rl"); os.makedirs(os.path.join(rl, "runs"), exist_ok=True)
w(os.path.join(rl, "plan.json"), {
    "schema": "expdash/2", "name": "rl-sweep", "title": "RL algorithm comparison (scenario: csv without timestamps)", "lang": "en",
    "subtitle": "3 algorithms × 2 envs × 3 seeds · 1M steps · 6 concurrent · metrics.csv has no time column",
    "description": "# Goal\nWhich algorithm reaches the highest return in 1M steps?\n\n# Design\nPPO / SAC / TD3 on two environments, 3 seeds each; return logged every 5k steps.",
    "hypotheses": [{"id": "H1", "text": "SAC > PPO at 1M steps on both envs", "prediction": "final return SAC > PPO", "status": "pending"}],
    "factors": [{"id": "algo", "label": "algorithm", "levels": [{"id": "ppo", "label": "PPO"}, {"id": "sac", "label": "SAC"}, {"id": "td3", "label": "TD3"}]},
                {"id": "env", "label": "environment", "levels": [{"id": "hopper", "label": "Hopper"}, {"id": "walker", "label": "Walker"}]},
                {"id": "seed", "label": "seed", "levels": ["1", "2", "3"]}],
    "baseline": {"factor": "algo", "level": "ppo"}, "arm_defaults": {"total_steps": 1000000}, "concurrency": 6, "silent_after_min": 10,
    "phases": [{"id": "train", "name": "Training", "kind": "arms", "est_min": 240, "purpose": "Train all 18 runs.", "method": "6 concurrent on one box.", "criteria": "all runs reach 1M steps.", "outputs": "checkpoints + metrics.csv"},
               {"id": "eval", "name": "Final evaluation", "kind": "manual", "est_min": 30, "depends_on": ["train"], "purpose": "100-episode eval of final checkpoints."}],
    "metrics": [{"id": "reward", "label": "episodic return", "lower_is_better": False, "curve": "raw"}, {"id": "loss", "label": "critic loss", "lower_is_better": True, "curve": "raw", "log": True}],
    "x_axes": [{"id": "step", "label": "env steps"}, {"id": "minutes", "label": "wall-clock (min)"}],
    "scalars": [{"id": "final_reward", "label": "final return", "derive": {"metric": "reward", "how": "last"}}, {"id": "best_reward", "label": "best return", "derive": {"metric": "reward", "how": "best"}},
                {"id": "n_logs", "label": "# log rows", "derive": {"how": "count"}}],
    "plots": [{"id": "ret_step", "tab": "overview", "type": "curve", "title": "Return vs env steps", "y": "reward", "x": "step", "group": "algo", "facet": "env", "agg": "median_iqr", "explain": "Median over seeds; band = IQR. Higher is better; a curve only extends as far as half its arms have data."},
              {"id": "loss_step", "type": "curve", "title": "Critic loss vs env steps (log)", "y": "loss", "x": "step", "group": "algo", "facet": "env", "agg": "lanes", "explain": "One thin line per run."},
              {"id": "final_bar", "tab": "overview", "type": "bar", "title": "Final return by algorithm", "y": "final_reward", "group": "algo", "facet": "env", "agg": "median", "ref": "baseline", "explain": "Median over seeds; dots = runs; dashed = PPO."},
              {"id": "heat", "type": "heatmap", "title": "Final return, normalised to row best", "value": "final_reward", "rows": "env", "cols": "algo", "agg": "median", "normalize": "row_best", "explain": "1.00 = best algorithm for that environment."}],
    "gates": [{"id": "G1", "name": "G1 · SAC beats PPO (Welch t, p<0.05)", "status": "pending", "test": {"kind": "welch_t", "scalar": "final_reward", "a": {"algo": "sac"}, "b": {"algo": "ppo"}, "alpha": 0.05}}]})
TOTAL, LOG_EVERY = 1_000_000, 5000
ceil = {"hopper": {"ppo": 2600, "sac": 3300, "td3": 3100}, "walker": {"ppo": 3800, "sac": 4900, "td3": 4300}}
arms = [(a, e, s) for a in ("ppo", "sac", "td3") for e in ("hopper", "walker") for s in ("1", "2", "3")]
for i, (a, e, s) in enumerate(arms):
    aid = f"{a}-{e}-{s}"; rng = random.Random(aid)
    if i in (0, 1, 2, 6, 7, 12): frac, done = 1.0, True          # ppo×3, sac×2, td3×1 finished → Welch test has data
    elif i in (3, 4, 8, 9, 13, 14): frac, done = rng.uniform(0.2, 0.7), False
    else: continue
    n = int(TOTAL * frac / LOG_EVERY); dur = 150 * 60 * frac; start = now - dur - (600 if done else 0)
    path = os.path.join(rl, "runs", aid + ".csv")
    with open(path, "w") as f:
        f.write("step,reward,loss\n")
        for k in range(1, n + 1):
            st = k * LOG_EVERY; p = st / TOTAL
            f.write(f"{st},{-150 + (ceil[e][a] + 150) * (1 - math.exp(-4 * p)) + rng.gauss(0, 120):.1f},{50 * math.exp(-3 * p) + rng.uniform(0.5, 3):.3f}\n")
    os.utime(path, (start, start + dur)); m = os.path.join(rl, "runs", aid + ".started"); open(m, "w").close(); os.utime(m, (start, start))  # launch marker + mtime carry the timing
    if done: open(os.path.join(rl, "runs", aid + ".DONE"), "w").close()

# ---------------------------------------------------------------- sweep (status.json only)
sw = os.path.join(out, "sweep"); os.makedirs(os.path.join(sw, "runs"), exist_ok=True)
levels = ["0.0001", "0.0003", "0.001", "0.003", "0.01", "0.03"]
w(os.path.join(sw, "plan.json"), {
    "schema": "expdash/2", "name": "lr-sweep", "title": "Learning-rate sweep (scenario: result file only)", "lang": "en", "subtitle": "6 learning rates · one number per run · no phases, no baseline, no budget",
    "description": "Pick the learning rate with the best validation accuracy after 3 epochs.",
    "factors": [{"id": "lr", "label": "learning rate", "levels": levels}],
    "metrics": [], "x_axes": [{"id": "minutes", "label": "wall-clock (min)"}],
    "scalars": [{"id": "val_acc", "label": "validation accuracy", "unit": "%", "lower_is_better": False}],
    "plots": [{"id": "bar", "tab": "overview", "type": "bar", "title": "Validation accuracy by learning rate", "y": "val_acc", "group": "lr", "agg": "mean", "explain": "One run per learning rate."},
              {"id": "tbl", "type": "table", "title": "All values", "values": ["val_acc"], "rows": "lr", "explain": "Raw numbers."}]})
for i, lr in enumerate(levels):
    if i == 5: continue  # one arm not run yet
    d = os.path.join(sw, "runs", lr); os.makedirs(d, exist_ok=True)
    acc = round(100 * (0.62 + 0.3 * (1 - abs(i - 2.5) / 3) + random.Random(lr).uniform(-0.02, 0.02)), 2)
    w(os.path.join(d, "status.json"), {"status": "done", "val_acc": acc}); os.utime(os.path.join(d, "status.json"), (now - 3600 + i * 400, now - 3600 + i * 400))

# ---------------------------------------------------------------- edge (hostile)
ed = os.path.join(out, "edge"); os.makedirs(os.path.join(ed, "runs"), exist_ok=True)
plan = {"schema": "expdash/2", "name": "edge", "title": "<img src=x onerror=\"document.title='XSS'\"> edge & 边界 <b>案例</b>", "subtitle": "unicode ids · NaN · typos · log≤0", "lang": "zh",
        "description": "# 目标\n[bad link](javascript:alert(1)) and <script>document.title='XSS-DESC'</script>",
        "factors": [{"id": "模型", "label": "模型", "levels": [{"id": "模型A", "color": "#f00\" onmouseover=\"document.title='XSS-COLOR'"}, {"id": "模型B"}]}, {"id": "seed", "levels": [1, 2]}],
        "baseline": {"factor": "模型", "level": "模型A"}, "budget_min": 30, "concurrency": 2, "silent_after_min": 5,
        "phases": [{"id": "p1", "name": "阶段一", "kind": "arms", "match": "^NOPE", "est_min": 60}],
        "metrics": [{"id": "score", "label": "score", "lower_is_better": False, "curve": "best_so_far"}, {"id": "delta", "label": "delta (log, has ≤0)", "log": True, "curve": "raw"}],
        "x_axes": [{"id": "minutes"}, {"id": "step"}],
        "scalars": [{"id": "final_score", "lower_is_better": False, "derive": {"metric": "score", "how": "best"}}],
        "plots": [{"id": "typo", "tab": "overview", "type": "curve", "title": "typo'd metric id", "y": "scor", "x": "minutes", "group": "模型"},
                  {"id": "badx", "type": "curve", "title": "typo'd x", "y": "score", "x": "steps", "group": "模型"},
                  {"id": "logneg", "type": "curve", "title": "log with ≤0", "y": "delta", "x": "step", "group": "模型", "agg": "lanes"},
                  {"id": "badgroup", "type": "bar", "title": "typo'd factor", "y": "final_score", "group": "model"},
                  {"id": "ok", "type": "curve", "title": "fine", "y": "score", "x": "minutes", "group": "模型", "facet": "seed"}]}
w(os.path.join(ed, "plan.json"), plan)
fixed = json.loads(json.dumps(plan)); fixed["phases"][0]["match"] = "."; fixed["plots"] = [p for p in fixed["plots"] if p["id"] in ("logneg", "ok")]
for p in fixed["plots"]: p["explain"] = "edge case plot"
w(os.path.join(ed, "plan.fixed.json"), fixed)
for m in ("模型A", "模型B"):
    for s in ("1", "2"):
        d = os.path.join(ed, "runs", f"{m}-{s}"); os.makedirs(d, exist_ok=True); rng = random.Random(m + s); start = now - 600
        open(os.path.join(d, "started"), "w").close(); os.utime(os.path.join(d, "started"), (start, start))
        with open(os.path.join(d, "events.jsonl"), "w") as f:
            for k in range(1, 21):
                rec = {"t": start + 30 * k, "ok": True, "step": k, "score": round(50 + 40 * (1 - math.exp(-k / 6)) + rng.gauss(0, 3), 2), "delta": round(rng.gauss(0, 2), 3)}
                if k == 7: rec["score"] = float("nan"); rec["delta"] = float("inf")   # must not kill the page
                f.write(json.dumps(rec) + "\n")
print("wrote", out)
