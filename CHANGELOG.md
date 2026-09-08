# Changelog

## Design-first template refresh (2026-09-06)

- Make visual quality and design character the leading skill criteria, backed by concrete adversarial checks.
- Replace equal-weight tiles with compact summaries, dedicated navigation and a wide primary comparison.
- Improve typography, facet sizing, compact axis ticks, narrow layouts and light / dark / system themes.
- Add keyboard legends, chart enlargement affordances, modal focus management and Escape dismissal.
- Preserve search and filters across refresh; keep inspected observations stable while updating heartbeat.
- Align campaign hub styling and escape labels; retain the offline, dependency-free data contract.
- Include a standalone simulated-data demo and refreshed screenshots.


## v2.1 — after an adversarial review (2026-09-06)

An independent reviewer scored the first public version on ten dimensions, ran it on three self-built
scenarios (RL training CSVs without timestamps, a result-file-only sweep, a hostile plan) and a 150-arm
scale probe, and returned 12 ranked findings. All blockers and majors are addressed:

- **NaN safety** — a single NaN/inf anywhere used to make `live.json` unparsable and blank every tab.
  The collector now writes strict JSON (`allow_nan=False`, recursive clean); the page keeps rendering
  the last good data on fetch errors.
- **Training logs without timestamps** collapsed to one point per arm. Records are no longer dropped
  for lacking `t`; the CSV/log adapters synthesise times from `.started` markers or file times.
- **Result-file-only arms and single-factor designs** failed `--check` and drew a 1970 Gantt. A
  `status.json` alone is now data; the matrix and heatmap/table work with one factor; Explore picks a
  sensible default chart when there are no metrics.
- **ETA honesty** — the plan's `est_min` prior is used (spread over arms per slot), progress rate
  extrapolates running arms, queued arms respect `depends_on`, cycles are guarded, overdue work is
  shown in orange, and "unknown" is displayed instead of a fabricated 10-minute default.
- **Auto-closed ≠ done** — arms whose budget elapsed with no status file are flagged `auto_closed`,
  starred, excluded from baseline medians and gate tests, and listed on Ops.
- **Plan validation** — `collector.py --lint` (also run by `--check`) cross-checks every id reference,
  phase coverage of arms, dependency graph and gate tests; typo'd plot specs render as an error box.
- **Statistics for gates** — declarative `test` blocks (paired Wilcoxon, Mann-Whitney, Welch t)
  computed live with provisional verdicts; gates and hypotheses are addressed by `id`.
- **Curve aggregation** — raw metrics are interpolated within each arm's range instead of held flat
  forever; an aggregate point needs at least half the arms; `n` is shown in tooltips.
- **Charts** — nice tick values, log decades, thousands separators, capped plot width, rotated bar
  labels when crowded, log-scale notes for non-positive values, in-place legend toggling, no full
  re-render when nothing changed, `history.replaceState` for the hash.
- **Snapshots** freeze the clock; `now_doing` carries a timestamp and greys out when stale.
- **Automatic event feed** — arm/phase status transitions are logged by the collector.
- **Docs** — `match` / `arms` / `arm.phase`, `arm_defaults`, DONE/`.started` markers, `lower_is_better`
  default and the gate-id rule are documented; `plan.minimal.json` added; regression scenarios in
  `scripts/scenarios.sh`.

## v2 — first public version

Six-tab single-file dashboard, generic plan contract (factors, phases, metrics × x-axes, scalars, plot
specs, hypotheses, gates), pluggable adapters, liveness check, narrative logging, snapshot.
