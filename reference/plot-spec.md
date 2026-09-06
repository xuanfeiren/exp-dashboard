# Plot specs (`plan.plots[]`)

Every entry becomes one card on the Results tab (and on Overview when `tab: "overview"`). Click a card
title to enlarge; click a legend entry to hide that group. The Explore tab builds the same specs
interactively, so anything drawable there can be pinned into the plan.

Common fields: `id` (unique), `title`, `explain` (one sentence on how to read it), `group` (factor id →
one series/bar per level, coloured), `facet` (factor id → one panel per level), `tab`.

| type | required | optional | notes |
|---|---|---|---|
| `curve` | `y` = metric id, `x` = x-axis id | `agg` ∈ `median_iqr` (default) / `mean_sd` / `lanes`; `ref: "baseline_final"`; `logy`, `logx` | step curves for `best_so_far`/`cumsum` metrics, lines for `raw`; band drawn when ≥3 arms; running arms extend to now on the `minutes` axis |
| `bar` | `y` = scalar id | `agg` ∈ `median` / `mean`; `ref: "baseline"` | bar = aggregate, whisker = min–max, dots = arms, label starred when provisional |
| `box` | `y` = scalar id | | box = quartiles, line = median, whiskers = range |
| `scatter` | `x`, `y` = scalar ids | `color` = factor id (alias of `group`) | one dot per arm; provisional arms dashed |
| `cdf` | `y` = scalar id (typically a time-to-threshold such as a `catchup` scalar) | | fraction of the group's arms with value ≤ x; arms with no value (never / still running) keep the curve below 1 |
| `heatmap` | `value` = scalar id, `rows`, `cols` = factor ids | `agg`; `normalize: "row_best"` | cell = aggregate over arms in that cell; normalised cells show ×ratio to the row's best, coloured green→red |
| `table` | `values` = [scalar ids], `rows`, `cols` | `agg` | first value normalised/bolded like a heatmap; others listed with n |

Examples (from `templates/plan.example.json`):

```jsonc
{ "id": "curve_time", "tab": "overview", "type": "curve", "title": "Best-so-far latency vs wall-clock",
  "y": "latency_us", "x": "minutes", "group": "condition", "facet": "task", "agg": "median_iqr", "ref": "baseline_final",
  "explain": "Median over seeds of each team's best verified latency; band = IQR (≥3 seeds). Dashed = baseline final median." }

{ "id": "cost_scatter", "type": "scatter", "title": "Cost vs final latency", "x": "cost_usd", "y": "final_latency_us",
  "color": "condition", "facet": "task", "explain": "One dot per arm. Bottom-left is the frontier." }

{ "id": "catchup_cdf", "type": "cdf", "title": "Time to reach the baseline endpoint", "y": "catchup_min",
  "group": "condition", "facet": "task", "explain": "Fraction of arms that have reached the baseline's final median by minute x." }

{ "id": "heat", "type": "heatmap", "title": "Median final, normalised to row best", "value": "final_latency_us",
  "rows": "task", "cols": "condition", "agg": "median", "normalize": "row_best" }
```

## Choosing plots

- One plot per question the plan asks; for every hypothesis, at least one plot that could refute it.
- Put the 1–2 plots the user will check every hour on `tab: "overview"`.
- Pair a wall-clock curve with the same metric on a cost axis (`evals`, tokens, dollars): the first
  says who wins, the second says whether they paid for it.
- Use a `cdf` of a catch-up scalar to show *when* conditions reach a bar, not just *whether*.
- A `heatmap` normalised to row best is the fastest way to read a factor × factor design.
- Always keep every level of the grouping factor in the plot; hide interactively, never by omission.
