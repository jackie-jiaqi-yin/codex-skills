# Report Outline

The notebook entry must read like a disciplined research memo, not a marketing update.

Required sections:

## Context

- State the workspace, scope, experiment window, relevant commits, and GitHub provenance.
- Explain what changed since the last checkpoint.

## Methodology Delta

- Describe concrete code, config, dataset, or procedure changes.
- Tie claims to files, commits, or PR details.
- Explain the operational pipeline, not just hyperparameters:
  - data source,
  - preprocessing/filtering/downsampling,
  - split or sampling protocol,
  - model inputs and target,
  - evaluation or post-eval selection procedure.

## New Results

- Report the strongest new quantitative and qualitative outcomes.
- Prefer exact values, clear table references, and compact interpretation.
- If a compact result table exists, include it or explicitly point to it.

## Comparison vs Prior Best

- Compare against the historical best run using the configured primary metric.
- If unavailable, say exactly why: missing metric, baseline only, or incomparable run.

## Figures and Tables

- Reference reused figures first.
- If a generated chart is used, explain what it shows and what it does not prove.
- This section should contain real tables and/or real figure embeds when those assets exist, not only prose describing them.

## User Notes Revised

- When manual notebook edits are detected, preserve the substance and rewrite the prose into clearer academic English.
- Do not invent claims not present in the supplied notes.

## Risks/Anomalies

- List regressions, missing data, unstable conclusions, suspicious metrics, or incomplete provenance.

## Next Questions

- End with 3-5 concrete follow-up questions or next experiments.
