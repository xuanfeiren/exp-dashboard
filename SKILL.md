---
name: exp-dashboard
description: Build or improve a visually distinctive, information-rich live dashboard for an experiment campaign, including its plan, progress, results and operational health. Use when the user asks to monitor or compare experiments, turn an experiment plan into a dashboard, or improve an existing experiment dashboard (看板、实验前端、实时监控). Includes an offline single-file frontend and live-data collection; monitoring does not itself authorize launching experiments.
---

# exp-dashboard

Outcome: a beautifully composed research workspace that makes the experiment understandable at a
glance and supports serious comparison without returning to the terminal. **Visual quality and design
character are the first priority; usefulness and information density must be achieved within that
standard.** Correct data, readable evidence and working controls are prerequisites: decoration cannot
compensate for misleading results or an unusable page.

## Design contract

Read [reference/design-guide.md](reference/design-guide.md) before composing or modifying the page.
Treat the supplied HTML as a working implementation, not an approved final design. Preserve its data
contracts and offline operation; adapt its CSS, markup and rendering code when the campaign needs it.

- Choose a coherent visual direction appropriate to the user's taste or existing product: typography,
  palette, spacing, surface treatment and chart styling must form one system. Avoid substituting a
  fashionable theme, gradient or a wall of rounded cards for actual composition.
- Let the main research question determine the visual hierarchy. Give its most useful comparison
  substantial space; keep operational context compact and urgent problems conspicuous.
- Increase **useful comparisons per viewport**, not the number of boxes or tiny labels. Use aligned
  tables, readable small multiples and concise annotations; disclose long logs and raw records on demand.
- Keep all declared metrics and axes available in Results / Explore. Curate the initial view rather
  than rendering the full Cartesian product as equally important charts.
- Inspect rendered output and try its primary interactions. Apply the adversarial review in the design
  guide, repair concrete failures, and report any unverified behavior. A successful render is not a
  design approval.

## Start with the actual task

Inspect the existing plan, page, data reader, and a representative output before changing them.
Resolve paths relative to this skill's directory; shell examples below assume the repository root.
Keep campaign output outside the bundled templates.

| Request | Work to perform |
|---|---|
| New dashboard | Establish the question and data contract, then follow the workflow below. |
| Redesign an existing dashboard | Preserve its working connection; read the design guide, change the relevant UI, and verify affected views. Do not launch another collector unnecessarily. |
| Connect or repair live data | Trace one arm from source through adapter to `live.json` and rendered value. Repair the broken boundary. |
| Offline demo or report | Use clearly labeled simulated data or an existing snapshot; no remote deployment required. |

Infer routine choices from the repository and user request. Ask only for missing facts that materially
change correctness, such as an ambiguous metric direction or source location. Do not invent experiment
results, completion states, hypotheses, or statistical evidence. Monitoring does not authorize launching
experiments, changing budgets, or terminating their processes.

## Components

The collector runs where the experiment data is readable and writes `live.json` atomically. The page
fetches that file from a local HTTP server. If the data is remote, a puller can copy it to the viewing
machine; a single machine needs no puller. A snapshot embeds the data for direct offline opening.

| path | role |
|---|---|
| `templates/plan.minimal.json` | smallest useful plan (a sweep with a higher-is-better metric) — start here |
| `templates/plan.example.json` | fully worked plan: waves, manual phase, 3 metrics × 3 x-axes, 9 plots, gates with statistics |
| `templates/collector.py` | generic collector; never edited per experiment; `--lint`, `--check`, `--adapter` |
| `adapters/*.py` | data readers: jsonl events (default), csv rows, log regex, multi-lane teams |
| `templates/dashboard.html` | functional starting point; CONFIG for wiring, CSS / markup / JS for deliberate design changes |
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
2. **Lint it:** `python3 templates/collector.py --plan plan.json --lint`. Every id reference is checked (plots
   ↔ metrics/scalars/x-axes/factors, baseline level, arms ↔ phases, `depends_on` graph, gate tests).
   Fix errors; read the warnings (missing `est_min`, missing `explain`).
3. **Pick or write the adapter.** Runner already writes one JSON per evaluation → default adapter.
   CSV per run → `adapters/csv_rows.py` (pass `--adapter-arg time_col=…`; have the runner touch a
   `DONE` marker and a `.started` marker). Progress lines in a log → `adapters/log_regex.py`.
   Teams of parallel workers → `adapters/multi_lane.py`. Otherwise copy the closest file and
   implement `collect_arm()`; keep source hints truthful and inspect the actual input files, including
   status-only inputs. Follow that adapter's marker conventions; they are not interchangeable.
4. **Liveness check before anything else:**
   `python3 templates/collector.py --plan plan.json --runs <root> --out live.json [--adapter …] --check`
   prints lint results, each arm's status and data source, and exits non-zero if nothing is readable.
   Pre-launch, pass `--allow-empty` and re-check within minutes of launch. If the campaign is
   expensive, run `scripts/smoke_test.sh` first to watch the whole pipeline render on fake data.
5. **Run the collector where the data is.** Start in the foreground for local development. For
   unattended Linux operation, use the existing supervisor or detach:
   `setsid nohup python3 templates/collector.py … --state state.json --interval 30 < /dev/null > collector.log 2>&1 &`
   and confirm `updated` in live.json advances across two reads. Copy scripts with scp; never
   paste them through an ssh heredoc.
6. **Compose and stand up the page.** Choose the visual direction and primary comparison using the
   design guide. Adapt the copied template to the campaign; do not stop at changing its title or palette.
   `mkdir ~/<name>-dashboard && cp templates/dashboard.html …/index.html`.
   One campaign → `serve.sh` (edit REMOTE / REMOTE_FILES / PORT). Several → the hub: symlink the dir
   into the hub folder, add a line to `pull.list` and an entry to `campaigns.json`. If a hub is
   already serving, add the lines and restart it (kill by exact command line, then relaunch).
7. **Review the actual experience before announcing it.** Inspect each populated tab, then the
   primary view at a normal laptop viewport and a narrow viewport. A tall full-page screenshot alone
   hides first-screen problems. Use the design guide's adversarial checks for hierarchy, chart
   readability, dense and sparse states, theme contrast and working interactions. Existing smoke /
   scenario scripts supply fixtures, not proof of visual quality. Fix demonstrated defects and recheck
   affected views; if rendering or interaction tools are unavailable, state that limitation.
8. **Narrate the campaign when requested.** Arm and phase transitions are logged automatically; you
   add what the collector cannot know via `scripts/logline.py`: `now_doing` whenever what you are
   doing changes (it is timestamped and greys out when stale), `phase <id> running|done` for manual
   phases, `gate <id> pass|fail`, `hypothesis <id> supported|refuted`, `incident warn|error`, `log`.
9. **Close out with evidence.** Mark phases done only when their completion criteria are met; leave
   unresolved hypotheses pending. Record the evidence for manual verdicts. A snapshot may be created at
   any stage with `python3 scripts/snapshot.py index.html live.json snapshot_<date>.html`; verify its
   contents and label unfinished or simulated campaigns accurately.

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
  compared arm is finished; a manual `logline.py gate` verdict always wins. `min_effect` is relative improvement, not
  percentage points. These repeated checks have no sequential or multiple-testing correction; choose
  tests and comparable replicates deliberately, and do not equate a failed gate with a refuted hypothesis.
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
- Every aggregate shows `n`; curve support is based on the lanes with data, not all planned arms; raw
  metrics are interpolated, never held flat past an arm's last point.
- Italic = estimate, upright = observed, orange = overdue, "unknown" = no basis for a number.

## Rules (details and the incidents behind them: reference/ops-lessons.md)

- Never trust a monitor that has not shown real data. `--lint`, `--check`, read `src`, then detach.
- For remote campaigns, keep collection on the data host; the viewing machine pulls and displays.
- Heartbeat badge, silent-arm detection, mass-silence incident, auto-close marking and disk % are
  always on.
- All group levels accounted for in every comparison; explicit filters / facets for crowding, never
  silent omission. Keep `n` next to every aggregate.
- No CDN, no build step: one HTML file that opens from `python3 -m http.server` offline and can
  be frozen into a single snapshot file.
- `setsid nohup … < /dev/null &`, kill by exact command line, scp scripts instead of heredocs.

## Completion criteria

Before handing off, confirm the relevant outcomes—not just that files were written:

- **Data:** lint passes; a real arm's values, units, direction and status agree with its source;
  live freshness advances if live collection is in scope. Simulated fixtures are labeled.
- **Design:** the first viewport communicates the main question, useful comparison and urgent issues;
  labels and sample sizes are readable; dense and sparse views remain coherent.
- **Interaction:** exercise affected navigation, filters, legends, enlarged charts and arm details;
  check narrow layout and theme contrast when UI changes. Report unavailable checks explicitly.
- **Delivery:** provide the usable page or snapshot location, summarize changes and verification,
  and name remaining limitations. Do not claim deployment, commits, synchronization or validation
  without observing their success.
