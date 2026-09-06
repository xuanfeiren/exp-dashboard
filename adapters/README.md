# Adapters

An adapter is one Python file with one function. It is the only experiment-specific code in the
whole pipeline: it knows where *this* experiment writes its output and turns that into records.

```python
def collect_arm(arm: dict, plan: dict, ctx: dict) -> dict:
    """
    arm  = {"id": "...", "factors": {"condition": "...", "task": "...", ...}, "budget_min": ...}
    plan = the loaded plan.json (metrics / x_axes / scalars tell you which fields matter)
    ctx  = {"runs": "<--runs>", "now": epoch_seconds, "opts": {"k": "v", ...}}   # opts from --adapter-arg k=v
    return {
      "records": [ {"t": epoch, "ok": True, "step": 12, "loss": 0.31, "tokens_m": 1.2, ...}, ... ],
      "scalars": {"cost_usd": 4.2},                   # optional adapter-known per-arm numbers
      "status":  None | "done" | "failed" | "killed", # None → collector derives from timing/silence
      "start": epoch | None, "end": epoch | None,     # None → first/last record
      "progress": {"step": 120, "total": 400} | None,
      "note": "...", "src": "/path/i/read/from",      # src is printed by --check; keep it truthful
    }
    """
```

Records are free-form dicts. Every declared `metric.id` and `x_axes[].id` in plan.json is looked up
by key; `t` (epoch seconds) drives the `minutes` axis; `ok` (default true) gates `best_so_far`
curves; `step` is used by the `step` axis; `error` (string) is counted.

Bundled adapters:

| file | reads | typical use |
|---|---|---|
| `jsonl_events.py` (default, built into collector) | `<runs>/<arm>/events.jsonl` + `status.json` + `started` | agent harnesses that already log one JSON per evaluation |
| `csv_rows.py` | `<runs>/<arm>.csv` or `<runs>/<arm>/metrics.csv` | training loops that append a metrics CSV |
| `log_regex.py` | `<runs>/<arm>/*.log` parsed with a regex of named groups | anything that only prints progress lines |
| `multi_lane.py` | `<runs>/<arm>/<lane>/events.jsonl` (team-of-agents arms) | best-over-lanes curves for multi-agent teams |

Run `python3 collector.py --adapter adapters/csv_rows.py --adapter-arg time_col=timestamp …`.

Writing a new one: copy the closest file, keep `src` honest, run `--check`, read the printed
statuses and sources, then detach.
