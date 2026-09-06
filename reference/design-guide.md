# Design guide — how the page should look and behave

The template already follows these; keep them when extending it.

**Structure.** Header (title, subtitle, heartbeat badge) → banner (what is happening now + phase strip)
→ tabs. The banner answers "where are we?" in one line before anything else. Tabs answer, in order:
what is this (Plan), where is it (Progress), what did we find (Results), let me look myself (Explore),
is the machinery healthy (Ops).

**Typography of certainty.** Observed = upright. Estimated = italic and hatched. Provisional
(unfinished arm) = starred. Baseline = dashed. Every aggregate carries its `n`.

**Colour.** One colour per level of the grouping factor, identical across every panel, table header,
legend, matrix column and swatch on the Plan tab (`factor.levels[].color` or the palette by index).
Status colours are fixed: green done, blue running (pulsing), magenta silent, red failed, grey queued.
Light/dark follows the OS.

**Every chart is self-explaining.** Title says what, subtitle says y vs x and the aggregate, the
legend shows done/total per group, one sentence below says how to read it. Axes format units
(µs → ms when large, $ prefix, % suffix). Hover gives exact values; click the title to enlarge.

**Clickable everywhere.** Tabs, phase strip segments (→ Progress), phase cards (expand), legend items
(toggle), plot titles (enlarge), arm chips and table rows (drawer with scalars, curves, last records,
source path), table headers (sort), matrix axes and Explore controls (selects), URL hash (deep link).

**Density.** Tiles for the six numbers that matter; tables for anything with more than four rows;
small multiples (facets) instead of one crowded chart; logs and incidents at the bottom of the tab,
newest first.

**Language.** UI strings come from the `L` table keyed by `plan.lang`; plan content is whatever the
author wrote. Add a language by adding one dictionary.

**No dependencies.** Vanilla JS + inline SVG. No CDN, no bundler, no framework. The file must render
from a bare `python3 -m http.server` on an offline machine and be embeddable as a single snapshot.
