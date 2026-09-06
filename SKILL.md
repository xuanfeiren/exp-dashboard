---
name: exp-dashboard
description: Build a live, tabbed web dashboard for any experiment campaign an agent is about to launch or is running — arms × factors, phases with time estimates that keep updating, every declared metric plotted against every x-axis while data streams in, results tables, hypotheses and pre-registered gates (with built-in statistics), incidents and narrative log. Use right after writing an experiment plan and before launching it; when the user asks to monitor / track / watch an experiment, wants a dashboard, 看板, 前端 or 实时监控 instead of reading a terminal; or when long runs live on remote machines. Covers plan.json → lint → on-host collector → live.json → laptop puller → single-file HTML, liveness checks, hub registration, logging and a final snapshot.
---

# exp-dashboard

Outcome: the user opens one URL and never has to read the terminal. The page explains the plan,
says where the campaign is and when each phase will finish, and draws every metric the plan
declared while the data is still arriving. Everything the agent would have typed in chat about
progress goes onto the page instead.

## Pipeline (4 pieces, 3 places)

```
data host                                laptop                              browser
────────────────────────────             ──────────────────────────          ──────────────────────────
runs/…  (events / csv / logs) ─┐         ~/<name>-dashboard/                 index.html (tabs: overview,
plan.json  (design, phases,    ├─► collector.py ─► live.json ──scp──►  live.json                        plan, progress, results,
            metrics, plots)    │   every 30 s, atomic            (serve.sh or hub-serve.sh)     explore, ops) refetches
state.json (narrative log) ────┘                                                                 every 25 s
```

| path | role |
|---|---|
| `templates/plan.minimal.json` | smallest useful plan (a sweep with a higher-is-better metric) — start here |
| `templates/plan.example.json` | fully worked plan: waves, manual phase, 3 metrics × 3 x-axes, 9 plots, gates with statistics |
| `templates/collector.py` | generic collector; never edited per experiment; `--lint`, `--check`, `--adapter` |
| `adapters/*.py` | data readers: jsonl events (default), csv rows, log regex, multi-lane teams |
| `templates/dashboard.html` | the page; only the CONFIG block is ever edited |
| `templates/serve.sh`, `templates/hub.html`, `templates/hub-serve.sh` | laptop side: single campaign, or one hub for many |
| `scripts/logline.py` | narrate: log / now_doing / phase status / gate & hypothesis verdicts / incidents → state.json |
| `scripts/simulate.py`, `scripts/smoke_test.sh`, `scripts/scenarios.sh` | fake campaign + per-tab screenshots; regression scenarios (csv without timestamps, result-file-only sweep, hostile plan) |
| `scripts/snapshot.py` | freeze the page into one self-contained HTML at the end |
| `reference/live-schema.md`, `reference/plot-spec.md` | data contracts |
| `reference/ops-lessons.md`, `reference/design-guide.md` | why each rule exists; how the page should look |

## Workflow

1. **Translate the plan into `plan.json`** while it is fresh (see "Writing the plan"). Start from
   `plan.minimal.json` or `plan.example.json`; keep the user's wording in `description`,
   `hypotheses`, and each phase's purpose / method / criteria / outputs.
2. **Lint it:** `python3 collector.py --plan plan.json --lint`. Every id reference is checked (plots
   ↔ metrics/scalars/x-axes/factors, baseline level, arms ↔ phases, `depends_on` graph, gate tests).
   Fix errors; read the warnings (missing `est_min`, missing `explain`).
3. **Pick or write the adapter.** Runner already writes one JSON per evaluation → default adapter.
   CSV per run → `adapters/csv_rows.py` (pass `--adapter-arg time_col=…`; have the runner touch a
   `DONE` marker and a `.started` marker). Progress lines in a log → `adapters/log_regex.py`.
   Teams of parallel workers → `adapters/multi_lane.py`. Otherwise copy the closest file and
   implement `collect_arm()` (≈30 lines); `src` must be the real path you read.
4. **Liveness check before anything else:**
   `python3 collector.py --plan plan.json --runs <root> --out live.json [--adapter …] --check`
   prints lint results, each arm's status and data source, and exits non-zero if nothing is readable.
   Pre-launch, pass `--allow-empty` and re-check within minutes of launch. If the campaign is
   expensive, run `scripts/smoke_test.sh` first to watch the whole pipeline render on fake data.
5. **Detach the collector on the data host:**
   `setsid nohup python3 collector.py … --state state.json --interval 30 < /dev/null > collector.log 2>&1 &`
   and confirm `updated` in live.json advances across two reads. Copy scripts with scp; never
   paste them through an ssh heredoc.
6. **Stand up the page.** `mkdir ~/<name>-dashboard && cp templates/dashboard.html …/index.html`.
   One campaign → `serve.sh` (edit REMOTE / REMOTE_FILES / PORT). Several → the hub: symlink the dir
   into the hub folder, add a line to `pull.list` and an entry to `campaigns.json`. If a hub is
   already serving, add the lines and restart it (kill by exact command line, then relaunch).
7. **Look at it before announcing it.** Headless screenshot of each tab (`smoke_test.sh` shows the
   Chrome command) and read the PNGs. Fix empty panels, wrong units, unreadable labels.
8. **Run the campaign through the page.** Arm and phase transitions are logged automatically; you
   add what the collector cannot know via `scripts/logline.py`: `now_doing` whenever what you are
   doing changes (it is timestamped and greys out when stale), `phase <id> running|done` for manual
   phases, `gate <id> pass|fail`, `hypothesis <id> supported|refuted`, `incident warn|error`, `log`.
9. **Close out.** Mark the last phase done, set final verdicts, then
   `scripts/snapshot.py index.html live.json snapshot_<date>.html` into the campaign folder.

## Writing the plan (what makes the page good)

- **factors**: every independent variable, including replicates (`seed`); a factor named
  seed/rep/run/trial (or flagged `replicate: true`) is pooled in medians. Give levels short labels
  and a one-line `desc`. `baseline` names the reference level for dashed lines, ratios, catch-up
  times and gate tests.
- **arms**: `null` → full cartesian product with ids `level-level-level`; list them explicitly when
  ids carry tags or the design is unbalanced. `arm_defaults` (e.g. `{"total_steps": 400}`,
  `{"budget_min": 60}`) is merged into every generated arm.
- **phases**, in dependency order, each with `est_min` (your prior), `depends_on`, and
  `purpose · method · criteria · outputs`. `kind: "arms"` phases get their status from their arms —
  assign arms with `match` (regex on arm id), `arms` (id list) or `arm.phase`; a phase with neither
  catches everything. `kind: "manual"` phases (analysis, report) are driven by
  `logline.py phase …`. The page re-estimates every phase end on every refresh: running arms from
  budget or progress rate, queued arms packed onto `concurrency` slots no earlier than their
  dependencies finish, durations learned from finished arms, `est_min` as the fallback prior;
  unknown stays "unknown", late shows as orange "overdue" — never a made-up number.
- **metrics** are per-record series (`best_so_far`, `raw`, or `cumsum`; set `lower_is_better:
  false` for rewards/accuracy — the default is true); **x_axes** are anything a record can be placed
  on (`minutes`, `evals`, `step`, or any numeric field, optionally cumulative); **scalars** are one
  number per arm, adapter-provided or derived (`best/last/first/sum/mean/min/max/count/count_ok/
  first_ok_min/catchup`; direction inherited from the metric). The collector builds every
  metric × x-axis curve, so the Explore tab can combine them freely. A scalar with `unit: "$"` is
  summed into the cost tile.
- **plots**: one per question the plan asks; for every hypothesis at least one plot that could
  refute it. Types: `curve`, `bar`, `box`, `scatter`, `cdf`, `heatmap`, `table`
  (reference/plot-spec.md). `tab: "overview"` marks headline plots. Every plot gets an `explain`.
- **gates**: `id` (short, e.g. `G1`), `name`, `status: pending`, optionally `test`:
  `{"kind": "paired_wilcoxon"|"mann_whitney"|"welch_t", "scalar": …, "a": {factor: level},
  "b": {factor: level}, "pair_by": [factors], "alpha": 0.05, "min_effect": 0.05}` — the collector
  computes p / effect / n on every tick and shows a provisional verdict (`pass*`) until every
  compared arm is finished; a manual `logline.py gate` verdict always wins.
- **hypotheses**: `id`, `text`, `prediction`, `status: pending`; verdicts via logline.
- `lang` sets the UI language (`en`/`zh`); write plan text in the user's language.

## Adapter recipes

- **Agent harness with per-evaluation JSON** → default adapter (`events.jsonl` + optional
  `status.json` + `started`). Teams of parallel workers → `adapters/multi_lane.py`
  (best-over-lanes; `live_root` for harnesses that write to a scratch dir while running).
- **Training runs** → `adapters/csv_rows.py` or `adapters/log_regex.py`; `x_axes: step`,
  `metrics: {curve: "raw", lower_is_better: false}`, `arm_defaults.total_steps` for progress %.
  Make the runner write `<arm>.DONE` when finished and `<arm>.started` at launch; without a time
  column timestamps are approximated from file times.
- **Sweeps with a final number per cell** → a `status.json` per arm (`{"status": "done",
  "val_acc": 0.91}`) is enough; curves hide themselves, the Results tab carries the page.
- **Stage pipelines** → phases with explicit `arms` lists or `kind: "manual"` driven by logline.
- **Qualitative / audit studies** → conditions as factors, audits as gates, contamination checks
  as incidents.

## Reading the page honestly

- `*` = provisional: the arm is unfinished **or was auto-closed** (budget elapsed with no status
  file — a crash looks like this). Auto-closed arms are excluded from baseline medians and gate
  tests and are listed on the Ops tab.
- Every aggregate shows `n`; curves only extend as far as half the group's arms have data; raw
  metrics are interpolated, never held flat past an arm's last point.
- Italic = estimate, upright = observed, orange = overdue, "unknown" = no basis for a number.

## Rules (details and the incidents behind them: reference/ops-lessons.md)

- Never trust a monitor that has not shown real data. `--lint`, `--check`, read `src`, then detach.
- Collector and orchestration live on the data host; the laptop only pulls and displays.
- Heartbeat badge, silent-arm detection, mass-silence incident, auto-close marking and disk % are
  always on.
- All levels of the grouping factor in every plot; `n` next to every aggregate.
- No CDN, no build step: one HTML file that opens from `python3 -m http.server` offline and can
  be frozen into a single snapshot file.
- `setsid nohup … < /dev/null &`, kill by exact command line, scp scripts instead of heredocs.
