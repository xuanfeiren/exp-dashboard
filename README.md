# exp-dashboard

**Make an experiment understandable at a glance—and worth looking at.**

An agent skill and a self-contained dashboard for research campaigns: compare conditions, follow
progress, inspect evidence, and catch stalled runs. Visual quality comes first, with useful information
density and practical interactions built into the same design.

No frontend build. No CDN. A Python collector, your experiment data, and one HTML page.

[Try the offline demo](docs/demo.html) · [Agent instructions](SKILL.md) · [Design guide](reference/design-guide.md) · [Data contract](reference/live-schema.md)

<p align="center"><img src="docs/overview.png" width="1000" alt="Experiment overview with compact status summaries and a prominent comparison chart; simulated data"></p>

## See it before connecting data

The screenshots and demo use **simulated data**. Download `docs/demo.html` and open it directly in a
browser, or serve the checked-out demo locally:

```bash
git clone https://github.com/xuanfeiren/exp-dashboard.git
cd exp-dashboard
python3 -m http.server 8399 --bind 127.0.0.1 --directory docs
```

Open <http://localhost:8399/demo.html>. Stop the server with Ctrl-C. The snapshot needs no collector
or network connection; it demonstrates the interface with frozen data.

## Use it with your agent

Point your coding agent at this repository's `SKILL.md`, or install the repository in the skill
directory supported by your agent. Keep the accompanying `reference/`, `templates/`, `adapters/`,
and `scripts/` directories together; the skill uses them during implementation.

A useful first request:

> Read SKILL.md and build a dashboard for my experiment. The plan is at [path] and the run outputs
> are at [path]. Prioritize a distinctive, beautiful interface, readable comparisons, and useful
> information density. Check a real run before connecting the page, then inspect the rendered
> dashboard and test its main interactions. Do not launch experiments.

For an existing dashboard:

> Read SKILL.md and adversarially review this dashboard. Improve its hierarchy, chart readability,
> information density, and interaction quality. Preserve the data contract and explain what you
> verified. You may redesign the template completely.

The HTML is a working starting point, not a design constraint. The skill asks the agent to choose
an intentional visual direction, give the main research question enough space, and repair problems
found in rendered views. Monitoring a campaign does **not** authorize starting or changing it.

## What you can inspect

| View | Questions it answers |
|---|---|
| **Overview** | What is happening? What needs attention? Which comparison matters most? |
| **Plan** | What are the hypotheses, factors, phases, methods, and decision criteria? |
| **Progress** | Which arms are running, queued, late, or finished? What is observed versus estimated? |
| **Results** | How do conditions compare across curves, distributions, scalar summaries, and tables? |
| **Explore** | What changes when I choose another metric, axis, grouping, facet, or aggregation? |
| **Ops** | Is the data fresh? Which arms are silent? What do incidents and host measurements show? |

The template includes light, dark, and system themes, chart enlargement, group toggles, arm details,
and sortable/filterable run tables. Results support curves, bars, boxes, scatter plots, CDFs,
heatmaps, and tables; see the [plot specification](reference/plot-spec.md).

<p align="center"><img src="docs/results.png" width="1000" alt="Results view showing several complementary comparisons of simulated experiment conditions"></p>

## Connect a real campaign

**Requirements:** Python 3 for the collector and local server, a modern browser, and readable run
outputs. The bundled collector and adapters use Python's standard library. Remote pulling additionally
needs SSH/SCP; Linux detachment commands are optional deployment choices.

Run these commands from the repository root. Use a new campaign directory; replace the example run
path with your own.

```bash
mkdir my-campaign
cp templates/plan.minimal.json my-campaign/plan.json
cp templates/dashboard.html my-campaign/index.html
```

1. **Edit the plan.** Define your actual factors, arm IDs, metric names and units, direction of
   improvement, phases, and headline plots. The minimal example is a learning-rate sweep with
   `val_acc` and CSV data. Its generated IDs must match your run filenames/directories. Use
   [the full example](templates/plan.example.json) for more elaborate phases and gates.
2. **Choose a reader.** The default reads JSONL events and optional status files. For CSV, use the
   command below. Other options and exact marker conventions are in [adapters/README.md](adapters/README.md).
3. **Validate and collect one real sample.** `--lint` checks the plan; `--check` also writes one
   `live.json`, reports arm statuses and sources, and fails if no data is readable.

```bash
python3 templates/collector.py --plan my-campaign/plan.json --lint
python3 templates/collector.py \
  --plan my-campaign/plan.json --runs /absolute/path/to/runs \
  --adapter adapters/csv_rows.py --out my-campaign/live.json --check
```

Inspect the reported sources and compare at least one arm's values and status with its original
output. `--allow-empty` is only for checking pre-launch wiring; it is not evidence of a live connection.

4. **Start collection**, keeping the same adapter settings used in the check:

```bash
python3 templates/collector.py \
  --plan my-campaign/plan.json --runs /absolute/path/to/runs \
  --adapter adapters/csv_rows.py --out my-campaign/live.json --interval 30
```

5. **In another terminal, serve the page:**

```bash
python3 -m http.server 8399 --bind 127.0.0.1 --directory my-campaign
```

Open <http://localhost:8399>. Confirm the data timestamp advances across two collection cycles.
Stop foreground processes with Ctrl-C. For a remote campaign, run collection on the data host and
configure [serve.sh](templates/serve.sh) to pull the resulting file; use an existing supervisor or
the Linux detachment recipe in [SKILL.md](SKILL.md) for unattended operation.

## Design for the experiment

A good dashboard should make the important comparison obvious without hiding the rest of the evidence.
The [design guide](reference/design-guide.md) turns that goal into a concrete review:

- Choose a coherent typography, palette, spacing, and chart system; avoid a wall of interchangeable cards.
- Give the primary question a prominent comparison. Keep operational summaries compact.
- Fit more **useful comparisons** into the viewport through alignment and hierarchy, not tiny text.
- Account for every condition through visible groups, filters, or facets. Show sample sizes and units.
- Inspect desktop and narrow views, sparse and dense data, theme contrast, and actual interactions.

Adapting a title and accent color is not a complete design pass. Conversely, an existing design that
already serves the experiment does not need a cosmetic rewrite.

## Read results honestly

- **Freshness matters.** A responsive page can still show stale data. Check the heartbeat and source files.
- **Provisional is not finished.** Unfinished and auto-closed values are starred. Auto-closure can mean
  a run exceeded its budget without an explicit completion status; it is not proof of success.
  Auto-closed arms are excluded from baseline medians and gate tests, but may appear in other summaries.
- **Estimates are estimates.** ETAs use budgets, progress, completed durations, and phase priors.
  Unknown remains unknown; overdue work is highlighted.
- **Units are literal.** A `%` label does not turn `0.91` into `91`; align source values and plan units.
- **Gates are aids to review.** The collector offers paired Wilcoxon, Mann–Whitney, and Welch tests,
  with provisional results while comparison arms remain unresolved. `min_effect: 0.01` means a
  1% relative improvement, not one percentage point. These repeated checks do not implement sequential
  or multiple-testing corrections. A failed gate does not by itself refute a hypothesis.
- **Grouping is a scientific choice.** Pool comparable replicates; facet or separate materially different
  tasks and environments. A chart cannot establish that pooling is valid.

## Record decisions and share a snapshot

Pass `--state my-campaign/state.json` to the collector to include narrative updates:

```bash
python3 scripts/logline.py my-campaign/state.json now_doing "Reviewing completed runs"
python3 scripts/logline.py my-campaign/state.json log "Investigating a stalled arm"
```

Record phase completion or hypothesis verdicts only when supported by evidence. To freeze a collected
page for sharing—even before a campaign finishes—run:

```bash
python3 scripts/snapshot.py my-campaign/index.html my-campaign/live.json my-campaign/snapshot.html
```

The resulting HTML includes the data and opens offline. Check its contents before sharing: it can
contain experiment descriptions, paths, logs, and results.

## Troubleshooting and validation

| Symptom | First check |
|---|---|
| No arms readable | Match plan arm IDs to directories/files; check `--runs`, adapter choice, and printed sources. |
| Metric or chart missing | Match numeric record keys to metric IDs and axes; check plot references with `--lint`. |
| Finished run appears silent | Write the completion marker supported by that specific adapter. |
| Page loads but data is stale | Check collector output timestamp, then any remote puller and browser fetch errors. |
| CSV option not applied | Repeat the flag for each setting: `--adapter-arg time_col=t --adapter-arg step_col=step`. |

For maintainers, `scripts/scenarios.sh` exercises CSV without timestamps, result-only runs, and a
hostile plan. `scripts/smoke_test.sh` runs a simulated campaign and can capture screenshots when Chrome
is available. Read these scripts first: they recreate their work directories, and the smoke test starts
background processes. Use disposable paths. Automated fixtures do not replace visual or interaction review.

## Repository map

| Path | Purpose |
|---|---|
| [SKILL.md](SKILL.md) | Agent routing, workflow, data integrity, and completion criteria |
| [reference/design-guide.md](reference/design-guide.md) | Visual composition and adversarial review |
| [reference/live-schema.md](reference/live-schema.md) / [plot-spec.md](reference/plot-spec.md) | Data and chart contracts |
| [reference/ops-lessons.md](reference/ops-lessons.md) | Operational failure modes and lessons |
| `templates/` | Plans, collector, dashboard, and optional remote/hub serving helpers |
| `adapters/` | JSONL, CSV, regex-log, and multi-lane readers |
| `scripts/` | Simulation, regression fixtures, narrative updates, and snapshots |
| `docs/` | Screenshots and standalone simulated demo |

## License

[MIT](LICENSE)
