# Chart Rules

Every chart should answer a question, not just visualize a column.

## Required metadata per chart

- `why_selected`: why the chart belongs in this report
- `how_to_read`: the intended interpretation frame
- `watch_out_for`: caveats, bias, or scaling issues

## Selection rules

- Prefer stable embedded plots over fragile interactive widgets when layout quality is at stake.
- Prefer bar charts and histograms. Avoid pie charts unless the comparison is genuinely part-to-whole and very low-cardinality.
- Auto-ignore obvious index or identifier columns such as unnamed row indices or record IDs.
- Prefer charts that help diagnose quality, distribution shape, association strength, or target relevance.
- For categorical variables, default to top-N plus an `Other` bucket when cardinality is high.
- For missingness, prefer sorted bars and compact matrices over giant unreadable grids.
- For correlations, avoid giant heatmaps that are likely to overflow or become unreadable; a ranked bar chart is often better.
- For target-aware rankings, choose effect size or association strength, not raw p-values alone.

## Styling rules

- Use a consistent palette across the report.
- Keep the page compact; do not spend vertical space on three separate explanation cards when one compact paragraph will do.
- Make sure plots fit inside their containers without clipping, overlap, or hidden axes.
- Use concise titles tied to columns and questions.
- Avoid overloaded legends and unreadable axis labels.
- If a chart uses technical terminology such as `Jaccard`, `Cramer's V`, or `eta-squared`, add a subtle one-line explanation.
