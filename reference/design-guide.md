# Design guide — beautiful, useful, information-rich

This is a design brief and review standard, not a claim that the bundled template already meets it.
The template supplies working behavior. Change its presentation deliberately; preserve its data
contract, honest uncertainty and offline snapshot support. No remote fonts, CDN or framework required.

## Establish a visual direction

Before coding, identify the question the user repeatedly returns to, the comparison that answers it,
and the action they take next. Choose a direction in a few concrete sentences: type hierarchy,
palette, composition, chart treatment and one distinguishing detail. Honor a supplied reference or
existing design system. Without one, a precise research instrument with restrained editorial
typography is a useful starting point, not a mandatory theme.

Express character through proportion, alignment, typography and intentional contrast. A wide primary
chart, disciplined numeric columns, a compact status rail and excellent chart labels often contribute
more than ornaments. Use a bounded spacing scale and shared surface / border / radius tokens. Reserve
strong color and large type for elements deserving attention. Avoid equal emphasis on every panel,
nested card borders, oversized KPI digits, decorative hero sections and gratuitous motion.

Use a dependable offline font stack with good Chinese fallback; use tabular numerals for comparisons
and monospace selectively for identifiers and raw records. Keep text readable at normal zoom: around
13–15 px for working content and 11–12 px for secondary chart labels is a starting point. If content
does not fit, change its layout before shrinking the type. Low contrast is not sophistication.

## Compose around the decision

The initial viewport should expose campaign identity, freshness, present activity, urgent exceptions
and meaningful evidence. On a typical 1440 × 900 laptop view, do not spend the whole screen on a
header, status cards and navigation before the main comparison begins. A dominant chart or results
table should be readable there, not reduced to a decorative sparkline.

Choose a few consequential summary values; the template's eight tiles are not a requirement. Combine
related counts in a compact strip or table. Avoid a large zero-cost tile when cost is not measured.
Show an unavailable important measure as unavailable rather than inventing a value. Reserve whitespace
for grouping and emphasis, not empty panels that push evidence below the fold.

Keep useful destinations: Overview for decisions, Plan for rationale, Progress for schedule, Results
for evidence, Explore for comparison, Ops for diagnosis. Adjust emphasis to the data:

| Campaign | Primary visual | Supporting context |
|---|---|---|
| Learning curves | Legible metric vs step or time, with uncertainty | Baseline, sample count, budget and failures |
| Final-result sweep | Aligned result table or factor heatmap | Replicates, missing cells and metric direction |
| Multi-stage pipeline | Current stage and dependency-aware timeline | Blocking condition, outputs and estimated finish |
| Before launch | Compact plan, expected comparisons and readiness | Explicit absence of observations |

Use progressive disclosure for raw logs, full source paths and long methods. Do not hide the caveat
needed to interpret the headline value in a tooltip or another tab. Critical stale / failed states
must remain visible from the primary view, even when diagnostic detail belongs in Ops.

## Density through structure

Use common baselines, aligned columns, shared legends and concise annotations to make comparisons
cheap. Prefer a sortable table for many arms; keep units in headers, values aligned and precision
consistent. Pin identifying columns or headers only when scrolling warrants it. Search and filters
should show their active state and retained / total count.

Size panels according to their job rather than forcing everything into equal cards. Use small
multiples when curves overlap, with shared scales when comparison requires them. If many categories
make marks or legends unreadable, facet, scroll a comparison region, or expose explicit filters.
Account for every level and make omissions visible; never silently select only favorable conditions.
Do not draw hundreds of unreadable lines to satisfy an all-levels rule literally.

On narrow screens, stack panels and keep the primary evidence early. Let wide tables scroll inside
their own region; avoid whole-page horizontal overflow. Long English identifiers and Chinese labels
must not crush the plot. Wrap descriptive text; truncate identifiers only with an accessible way to
recover the full value. Avoid fixed column minimums wider than the available content area.

## Charts carry the design

Each chart has a concrete comparison title, readable units and direction, a clear baseline, and a
compact explanation of aggregation / uncertainty. A finding may become a title only when supported
by the shown data. State n and provisional status near the value they qualify. For n=1, do not imply
an uncertainty estimate. Distinguish IQR, SD and confidence intervals rather than labeling all bands
as confidence. Missing observations are gaps / missing values, never zeros.

Keep axes and gridlines quiet but readable; give data marks the strongest contrast. Use consistent
group colors across charts, legends, tables and filters, independent of sorting. Distinguish group
identity from good / bad status through labels and line or marker styles. Check both light and dark
themes; a palette that works on white can disappear on charcoal. Do not rely on red versus green alone.

Use honest scales: bars generally start at zero; disclose an intentional restricted range on a line
chart; do not compare facets as if their scales were equal when they are not. Show uncertainty,
baseline and denominators without making the plot a tangle. Exact values should be available through
working inspection or a table, including on touch / keyboard paths when hover is unavailable.

Observed values are upright; estimates also have explicit wording, not only italics. Provisional
values carry a visible marker with a nearby explanation. Baselines are dashed and labeled. Auto-closed
arms remain distinguishable from confirmed completions. Live gate tests remain provisional during
collection; an interim p-value does not establish a confirmed discovery.

## Interactions earn their place

Use recognizable controls for switching views, sorting, filtering and opening details. A title that
opens a larger chart needs an affordance; arbitrary text should not look secretly clickable. Controls
must change the expected content and expose their selected state. Provide visible keyboard focus,
descriptive labels and practical hit areas. Dialogs should support Escape, focus entry / return and
keyboard containment. Respect reduced-motion preferences instead of continuously pulsing dense grids.

Live refresh should preserve filters, sorting, open details, focus and useful scroll position. Verify
this across a refresh, not just immediately after a click. A disconnected feed should retain the last
observation with a conspicuous age / stale state, not look live or collapse into an empty screen.
URL sharing and the final offline snapshot must still work after presentation changes.

## Adversarial acceptance review

Try to disprove that the page is ready. Use real campaign data or clearly marked fixtures. Start with
existing smoke / scenario fixtures and add only cases relevant to changed behavior. Inspect actual
rendered images at normal zoom; source inspection and a DOM title check cannot establish visual quality.

| Attack | Failure to look for | Required response |
|---|---|---|
| Five-second glance | Everything has equal weight; the main question is unclear | Recompose hierarchy and give evidence more area |
| Mentally remove decorative styling | The design is only a color change and rounded boxes | Improve typography, proportions, alignment and chart craft |
| Normal laptop viewport | Navigation / KPI scaffolding consumes the first screen | Compress context and promote the main comparison |
| Many arms, groups or long bilingual labels | Overlapping legends, tiny plots, excessive cards | Use tables, facets, wrapping and explicit filters |
| No data, one arm or missing metrics | Empty chart wall, fabricated zero, false uncertainty | Use concise truthful states and an appropriate primary view |
| Stale feed, failed or auto-closed arms | A healthy-looking headline hides invalid evidence | Surface freshness and qualification where the result is read |
| Dark theme and narrow viewport | Low contrast, clipped controls, page overflow | Repair tokens and responsive sizing |
| Keyboard, details and one live refresh | Dead controls, lost selection / focus, jumping content | Repair the interaction and repeat that path |

Judge visual character and composition first, then scan efficiency, analytic readability and
interaction quality. Data truth and usable access are non-negotiable gates, not points that aesthetics
can offset. Do not use a self-assigned numeric score as evidence that a design passed. Record concrete
observations, repair consequential failures, and recheck affected views. Stop when those failures
are resolved; report remaining limitations honestly rather than promising universal perfection.
