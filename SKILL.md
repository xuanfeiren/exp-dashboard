---
name: exp-dashboard
description: Build a live, tabbed web dashboard for any experiment campaign an agent is about to launch or is running — arms × factors, phases with time estimates that keep updating, every declared metric plotted against every x-axis while data streams in, results tables, hypotheses and pre-registered gates, incidents and narrative log. Use right after writing an experiment plan and before launching it; when the user asks to monitor / track / watch an experiment, wants a dashboard, 看板, 前端 or 实时监控 instead of reading a terminal; or when long runs live on remote machines. Covers plan.json → on-host collector → live.json → laptop puller → single-file HTML, liveness checks, hub registration, logging and a final snapshot.
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

Files in this skill:

| path | role |
|---|---|
| `templates/plan.example.json` | the plan contract, fully worked example — copy and edit |
| `templates/collector.py` | generic collector; never edited per experiment; `--adapter` plugs in the data reader |
| `adapters/*.py` | data readers: jsonl events (default), csv rows, log regex, multi-lane teams |
| `templates/dashboard.html` | the page; only the CONFIG block is ever edited |
| `templates/serve.sh`, `templates/hub.html`, `templates/hub-serve.sh` | laptop side: single campaign, or one hub for many |
| `scripts/logline.py` | append log / incident / gate / hypothesis / phase status / now_doing to state.json |
| `scripts/simulate.py`, `scripts/smoke_test.sh` | fake campaign + per-tab screenshots; run before touching real data |
| `scripts/snapshot.py` | freeze the page into one self-contained HTML at the end |
| `reference/live-schema.md`, `reference/plot-spec.md` | data contracts |
| `reference/ops-lessons.md`, `reference/design-guide.md` | why each rule exists; how the page should look |

## Workflow

1. **Translate the plan into `plan.json`** while it is fresh (see "Writing the plan" below).
   Start from `templates/plan.example.json`; keep the user's wording in `description`,
   `hypotheses`, and each phase's purpose / method / criteria / outputs.
2. **Pick or write the adapter.** If the runner already writes one JSON per evaluation, the default
   adapter needs nothing. Otherwise copy the closest file in `adapters/` and implement
   `collect_arm()` (≈30 lines). `src` must be the real path you read.
3. **Liveness check, before anything else:**
   `python3 collector.py --plan plan.json --runs <root> --out live.json [--adapter …] --check`
   It prints each arm's status and data source and exits non-zero if nothing is readable. Pre-launch,
   pass `--allow-empty` and re-check within minutes of launch. If the campaign is expensive, run
   `scripts/smoke_test.sh` first to see the whole pipeline render on fake data.
4. **Detach the collector on the data host:**
   `setsid nohup python3 collector.py … --state state.json --interval 30 < /dev/null > collector.log 2>&1 &`
   and confirm `updated` in live.json advances across two reads. Copy scripts to the host with
   scp; never paste them through an ssh heredoc.
5. **Stand up the page.** `mkdir ~/<name>-dashboard && cp templates/dashboard.html …/index.html`.
   One campaign → `serve.sh` (edit REMOTE / REMOTE_FILES / PORT). Several → the hub: symlink the dir
   into the hub folder, add a line to `pull.list` and an entry to `campaigns.json`. If a hub is
   already serving, add the lines and restart it (kill by exact command line, then relaunch).
6. **Look at it before announcing it.** Headless screenshot of each tab (`smoke_test.sh` shows the
   Chrome command) and read the PNGs. Fix empty panels, wrong units, unreadable labels.
7. **Run the campaign through the page.** Every launch, wave boundary, verdict, kill and incident
   goes through `scripts/logline.py` — `log`, `now_doing`, `phase <id> running|done`,
   `gate <name> pass|fail`, `hypothesis <id> supported|refuted`, `incident warn|error`. Update
   `now_doing` whenever what you are doing changes; it is the first line the user reads.
8. **Close out.** Mark the last phase done, set final gate/hypothesis verdicts, then
   `scripts/snapshot.py index.html live.json snapshot_<date>.html` into the campaign folder.

## Writing the plan (what makes the page good)

- **factors**: every independent variable, including replicates (`seed`); a factor named
  seed/rep/run/trial is treated as a replicate and pooled in medians. Give levels short labels and
  one-line `desc`; the Plan tab shows them. `baseline` names the reference level for dashed lines,
  ratios and catch-up times.
- **arms**: leave `null` for a full cartesian product; list them explicitly when ids carry tags or
  the design is unbalanced. Give each a `budget_min` if arms differ.
- **phases**: one per wave / stage / analysis step, in dependency order, with `est_min` (your
  prior), `depends_on`, and `purpose · method · criteria · outputs`. `kind: "arms"` phases get
  their status from their arms; `kind: "manual"` phases are driven by `logline.py phase …`.
  The page re-estimates every phase's end on every refresh from the queue simulation
  (running arms' budgets + queued arms over `concurrency` slots) and learned durations.
- **metrics** are per-record series (`best_so_far`, `raw`, or `cumsum`); **x_axes** are anything a
  record can be placed on (`minutes`, `evals`, `step`, or any numeric field, optionally cumulative);
  **scalars** are one number per arm, either adapter-provided or derived (`best/last/sum/mean/
  count/count_ok/first_ok_min/catchup`). The collector builds every metric × x-axis curve, so the
  Explore tab can combine them freely.
- **plots**: one for each question the plan asks. For every hypothesis include at least one plot
  that could refute it. Mix types: `curve` (metric vs x, median±IQR / mean±sd / individual arms),
  `bar` and `box` (a scalar by group), `scatter` (scalar vs scalar, one dot per arm), `cdf`
  (time-to-threshold), `heatmap` (rows × cols of an aggregated scalar, normalised to row best),
  `table`. `tab: "overview"` marks headline plots. Every plot gets an `explain` sentence — the
  user returns weeks later.
- **gates** and **hypotheses** start `pending`; the page shows them next to the data so verdicts
  are read against the frozen bar.
- `lang` sets the UI language (`en`/`zh`); write the plan text in the user's language.

## Adapter recipes

- **Agent harness with per-evaluation JSON** → default adapter. Arm = one team or one agent.
  Teams of parallel workers → `adapters/multi_lane.py` (best-over-lanes; `live_root` for
  harnesses that write to a scratch dir while running and copy results out at the end).
- **Training runs** → `adapters/csv_rows.py` or `adapters/log_regex.py`; `x_axes: step`,
  `metrics: {curve: "raw"}`, `arm.total_steps` for progress %.
- **Sweeps with a final number per cell** → default adapter with a one-line events file or an
  adapter that reads the result file; curves hide themselves, the results tab carries the page.
- **Stage pipelines** → phases with explicit `arms` lists or `kind: "manual"` driven by logline.
- **Qualitative / audit studies** → conditions as factors, audits as gates, contamination checks
  as incidents.

## Rules (details and the incidents behind them: reference/ops-lessons.md)

- Never trust a monitor that has not shown real data. `--check`, read `src`, then detach.
- Collector and orchestration live on the data host; the laptop only pulls and displays.
- Heartbeat badge, silent-arm detection, mass-silence incident and disk % are always on.
- All conditions in every plot; `n` next to every aggregate; estimates italic; provisional values
  starred.
- No CDN, no build step: one HTML file that opens from `python3 -m http.server` offline and can
  be frozen into a single snapshot file.
- `setsid nohup … < /dev/null &`, kill by exact command line, scp scripts instead of heredocs.
