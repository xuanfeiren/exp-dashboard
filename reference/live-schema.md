# live.json — schema `expdash/2`

One file, rewritten atomically by the collector every `collector_interval_s`. The page is a pure function
of this file plus the browser clock; anything not listed is ignored, so adapters may add fields freely.

```jsonc
{
  "schema": "expdash/2", "name": "demo", "title": "…", "subtitle": "…", "lang": "en" | "zh",
  "updated": 1788726531.8,            // epoch s; page badge turns red when older than 3×interval + 15 s
  "collector_interval_s": 30, "host": "machine-name",

  "plan": {
    "description": "markdown",        // rendered on the Plan tab (#, ##, -, **b**, *i*, `code`, [t](url))
    "factors": [ { "id": "condition", "label": "condition", "replicate": false,
                   "levels": [ { "id": "baseline", "label": "no channel", "color": "#7a7a72", "desc": "…" } ] } ],
    "baseline": { "factor": "condition", "level": "baseline" },     // reference for dashed lines, ratios, catch-up
    "budget_min": 300, "finalize_min": 10, "concurrency": 12, "silent_after_min": 10, "t0": epoch,
    "metrics":  [ { "id": "latency_us", "label": "latency", "unit": "µs", "lower_is_better": true, "log": true,
                    "curve": "best_so_far" | "raw" | "cumsum" } ],
    "x_axes":   [ { "id": "minutes", "label": "wall-clock (min)" }, { "id": "evals" }, { "id": "step" },
                  { "id": "tokens_m", "label": "…", "cumsum": true } ],          // any numeric record field
    "scalars":  [ { "id": "final_latency_us", "label": "…", "unit": "µs", "lower_is_better": true,
                    "derive": { "metric": "latency_us", "how": "best" } } ],  // how ∈ best|last|sum|mean|min|max|count|count_ok|first_ok_min|catchup
    "plots":    [ … see plot-spec.md … ],
    "links":    [ { "label": "plan.md", "url": "…" } ], "notes": "…"
  },

  "hypotheses": [ { "id": "H1", "text": "…", "prediction": "…", "status": "pending|supported|refuted|inconclusive", "evidence": "…" } ],
  "gates":      [ { "id": "G1", "name": "G1 · …", "status": "pending|pass|fail|warn", "detail": "p=0.004",
                  "test": { "kind": "paired_wilcoxon|mann_whitney|welch_t", "scalar": "…", "a": {factor: level}, "b": {factor: level}, "pair_by": ["task","seed"], "alpha": 0.05, "min_effect": 0.05 },
                  "result": { "kind": "…", "p": 0.004, "effect": 0.12, "n": 6, "n_a": 6, "n_b": 6, "provisional": false, "auto_status": "pass|fail", "stat": 3.0 } } ],
  "notes": "…", "phase_note": "one-line banner", "now_doing": "what the agent is doing right now", "now_doing_t": epoch,
  "plan_warnings": [ "phase w1: no est_min …" ], "adapter_errors": { "<arm id>": "repr(exception)" },

  "phases": [ { "id": "w1", "name": "Wave 1", "kind": "arms" | "manual", "status": "queued|running|done",
                "est_min": 60, "depends_on": ["smoke"], "purpose": "…", "method": "…", "criteria": "…", "outputs": "…", "note": "…",
                "n": 20, "n_done": 7, "n_finished": 8, "n_auto_closed": 1, "n_running": 4, "n_silent": 0, "n_failed": 0, "arms": ["…ids…"],
                "start": epoch|null, "end": epoch|null } ],

  "arms": [ {
    "id": "W1-lessons-taskA-s1", "factors": { "condition": "lessons", "task": "taskA", "seed": "1" }, "phase": "w1",
    "status": "queued|running|silent|done|failed|killed", "auto_closed": true,   // done only because the budget elapsed — treat as unfinished
    "start": epoch|null, "end": epoch|null, "last_event": epoch|null, "total_steps": 400,
    "budget_min": 300, "progress": { "step": 210, "total": 400 } | null,
    "curves": { "<metric_id>": { "<x_axis_id>": [[x, y], …] } },       // every declared metric × x-axis, ≤250 points each
    "scalars": { "n_records": 141, "n_ok": 97, "n_err": 12, "first_ok_min": 1.3, "duration_min": 297.4,
                 "final_latency_us": 34.1, "cost_usd": 13.7, … },       // derived + adapter-provided; null when nothing measured yet
    "tail": [ {…last 3 records…} ], "note": "…", "src": "/path/the/adapter/read"
  } ],

  "anchors":   [ { "name": "reference kernel", "ref": 28.39, "latest": 28.52, "n": 3, "unit": "µs", "drift_pct": 0.46, "ok": true } ],
  "resources": { "load": 4.2, "ncpu": 192, "disk_free_gb": 291.6, "disk_pct_used": 41,
                 "gpus": [ { "id": 0, "util": 97, "mem_mib": 61234, "mem_total_mib": 81920 } ],
                 "cores": { "0": "arm-tag", … }, "n_cores": 64 },
  "incidents": [ { "t": epoch, "severity": "warn|error", "text": "…", "auto": true } ],
  "log":       [ { "t": epoch|null, "text": "…", "auto": true } ]     // auto = collector-generated status transition
}
```

## Derivations done by the page

- **Schedule / ETA** — running arms end at `start + budget + finalize`, or are extrapolated from
  `progress` when present; queued arms are packed onto `concurrency` slots in array order, no earlier
  than the end of their phase's `depends_on`; arms without a budget use the median duration of
  finished arms in their phase, then campaign-wide, then `est_min × slots / n`. `kind: "manual"`
  phases start when their dependencies end and last `est_min`. If a projected end is in the past the
  item is *overdue* (orange, end = now); with no basis at all it is *unknown* (dotted). Estimates are
  italic / hatched. The ETA tile keeps a local history and draws its drift as a sparkline.
- **Catch-up** (`derive.how: "catchup"`) — first x (minutes) at which an arm's best-so-far reaches the
  baseline's final median for the same cell (all non-replicate factors equal except the baseline
  factor). `Infinity` = finished without reaching it; `null` = still running.
- **Aggregates** — median (even n → mean of the two middle values), quartiles, mean, sd, over the
  arms of a group; the `n` shown is the number of arms with a value.
- **Provisional** — any arm not done/failed/killed, **or auto-closed**; its best-so-far is shown with `*` and it is excluded from baseline medians and gate tests.
- **Stale / silent** — stale = collector heartbeat old (collector, puller or link died); silent = arm
  alive by status but no record for `silent_after_min` (process died, credentials expired, host hung).

## Status derivation in the collector

adapter says done/failed/killed → that · no start → queued · `budget + finalize + silent_after` elapsed
without a status file → done with `auto_closed: true` (note appended; a crash looks like this) · no record
for `silent_after_min` → silent · else running. NaN / inf anywhere → null (the file is strict JSON).
