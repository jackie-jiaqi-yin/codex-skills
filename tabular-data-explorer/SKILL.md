---
name: tabular-data-explorer
description: Explore CSV, Excel, Parquet, TSV, and similar tabular datasets with type-aware profiling, descriptive statistics, missingness review, correlation and association analysis, optional target-aware feature exploration, and polished interactive HTML reporting. Use when users want to inspect an unfamiliar dataset, profile data quality, compare features against one or more target columns, or generate explainable charts plus grounded narrative from mixed-format tabular data. Especially useful for health, epidemiology, biostatistics, biology, and life-science workflows where users need interpretable views of missingness, multicollinearity, follow-up variables, and target-feature relationships before choosing explainable methods.
---

# Tabular Data Explorer

## Overview

Use this skill to turn one tabular dataset into a grounded exploratory report with deterministic artifacts and an adaptive Codex-written narrative.

The report should feel like an analyst-built HTML notebook, not a rigid template dump. Keep the page structure stable, but let the narrative and which charts appear depend on the data.

Bias the interpretation toward explainable exploratory work for health and life-science teams. That means paying extra attention to:

- missingness blocks that may come from questionnaire gating or assay availability,
- multicollinearity and redundancy that can destabilize interpretable models,
- follow-up or censoring variables that may behave like leakage in prediction settings,
- target imbalance and target availability when the outcome is only observed for a subset.

## Inputs

Resolve these inputs before execution.

1. `input path` (required)
- Meaning: dataset file to analyze.
- Supported formats: `csv`, `tsv`, `txt`, `xlsx`, `xls`, `parquet`.

2. `sheet name` (optional)
- Meaning: Excel worksheet name or index.
- Use only for Excel files.

3. `primary columns` (optional)
- Meaning: columns the user especially cares about.
- Use them to prioritize charts and narrative coverage.

4. `target columns` (optional)
- Meaning: columns to treat as targets for target-aware exploration.
- If target columns are given, assume the remaining non-ignored columns are candidate features.

5. `ignore columns` (optional)
- Meaning: columns to exclude from profiling and target-aware ranking.
- Common examples: row IDs, free-text notes, leakage columns, or audit timestamps the user does not want analyzed.

6. `report title` (optional)
- Meaning: human-facing title for the final HTML report.
- Default: derived from the dataset filename.

## Input Explanation (Must Explain Before Asking)

Before asking the user for any of the optional fields, explain them in plain language with one short concrete example.

1. `input path`
- Plain-language explanation: the file you want analyzed.
- Example: `/Users/me/data/patients.csv`

2. `target columns`
- Plain-language explanation: the outcome or result you want the report to compare other variables against.
- Example: if you want to know which columns relate to death status, `mortstat` is a target.

3. `primary columns`
- Plain-language explanation: columns you especially care about and want the report to spend more attention on.
- Example: `age`, `bmi`, `sleep_duration`

4. `ignore columns`
- Plain-language explanation: columns you want the analysis to skip.
- Example: `patient_id`, `free_text_notes`

5. `sheet name`
- Plain-language explanation: which worksheet to read inside an Excel file.
- Example: `Sheet1` or `0`
- Rule: do not ask for this when the file is `csv`, `tsv`, `txt`, or `parquet`.

6. `report title`
- Plain-language explanation: the display title shown at the top of the HTML report.
- Example: `NHANES mortality exploration`

## Suggested User-Facing Prompting Style

Use a short explanation like this before collecting values:

"I can analyze this dataset and generate an interactive HTML report. I need the file path and, optionally, a target column if you want target-aware analysis. If the file is Excel, I may also need the sheet name. If there are columns you especially care about, tell me those as primary columns; otherwise I can choose them automatically."

## Mandatory Question Gate

Do not run `workflow.py prepare` until the following is complete.

1. Explain the optional inputs in plain language before asking:
- what a `target column` means,
- what `primary columns` mean,
- what `ignore columns` mean,
- what `sheet name` means when relevant,
- what `report title` means.

2. Resolve what you can from the user request:
- input path
- sheet name
- primary columns
- target columns
- ignore columns
- report title

3. Ask only the fields that are still relevant:
- do not ask for `sheet name` on non-Excel files,
- do not ask for `primary columns` if the user is happy with auto-selection,
- do not ask for `report title` unless a custom title would help.

4. Restate the planned run in one short block using plain-language labels:
- dataset file
- target column, if any
- priority columns, if any
- ignored columns, if any
- Excel sheet, if relevant
- report title

5. Ask for explicit confirmation before execution.

6. Only continue after the user confirms.

## Workflow

Follow this order.

### 1. Prepare the deterministic analysis artifacts

Run:

```bash
python scripts/workflow.py prepare \
  --input-path "<dataset_path>" \
  --report-title "<report_title>"
```

Add optional flags only when needed:

```bash
  --sheet-name "<sheet_name>" \
  --primary-column "<primary_col_a>" \
  --primary-column "<primary_col_b>" \
  --target-column "<target_col_a>" \
  --ignore-column "<ignore_col_a>"
```

`prepare` creates a run directory inside:

- `<dataset_parent>/.tabular-data-explorer/runs/<timestamp>/`

It writes:

- `run_manifest.json`
- `profile_overview.json`
- `column_profiles.json`
- `missingness.json`
- `associations.json`
- `target_analysis.json`
- `chart_manifest.json`
- `analysis_brief.md`
- `analysis.md`

### 2. Read the artifacts before writing any narrative

Read:

- `references/report_sections.md`
- `references/chart_rules.md`
- `references/narrative_grounding.md`
- `<run_dir>/analysis_brief.md`
- `<run_dir>/profile_overview.json`
- `<run_dir>/column_profiles.json`
- `<run_dir>/missingness.json`
- `<run_dir>/associations.json`
- `<run_dir>/target_analysis.json`
- `<run_dir>/chart_manifest.json`

### 3. Write or revise `analysis.md`

Use `analysis.md` as a grounded narrative layer on top of the deterministic artifacts.

Requirements:

- Base every claim on computed artifacts or rendered charts.
- Prefer project-specific observations over generic EDA filler.
- Mention exact column names and numeric evidence when possible.
- Explain why a pattern matters before suggesting a next step.
- Skip empty sections instead of padding the report.
- Do not force a rigid template when the data does not support it.
- If targets exist, distinguish target-aware signals from general descriptive findings.
- If a chart is visually striking but analytically weak, say so explicitly.
- In health-oriented datasets, call out multicollinearity, follow-up variables, subset-defined targets, and module-based missingness when they matter.

### 4. Finalize the interactive HTML report

Run:

```bash
python scripts/workflow.py finalize --run-dir "<run_dir>"
```

This step reads the artifacts plus `analysis.md` and writes:

- `<run_dir>/report.html`

### 5. Verify outputs

Confirm these exist:

- `<run_dir>/run_manifest.json`
- `<run_dir>/profile_overview.json`
- `<run_dir>/column_profiles.json`
- `<run_dir>/missingness.json`
- `<run_dir>/associations.json`
- `<run_dir>/target_analysis.json`
- `<run_dir>/chart_manifest.json`
- `<run_dir>/analysis_brief.md`
- `<run_dir>/analysis.md`
- `<run_dir>/report.html`

## Chart Rules

- Favor stable embedded plots inside HTML over JS-heavy interactivity when layout reliability is at risk.
- Prefer bar charts and histograms over pie charts unless there is a clear analytical reason to do otherwise.
- Auto-exclude obvious index or identifier columns from relationship and target-aware analysis.
- When many strong feature-feature correlations exist, add a compact 2D correlation map to help multicollinearity review.
- Every chart must include:
  - why this chart was selected,
  - how to read it,
  - what caveats apply.
- If a chart uses technical terminology, add one subtle plain-language note explaining the term.
- Do not overload the page with every possible plot. Show the most decision-relevant ones.
- Prefer top-N summaries over unreadable full-cardinality visuals.
- Avoid decorative charts with no analytical purpose.

## Narrative Rules

- Treat the HTML shell as stable and the insights as adaptive.
- Let the data decide which findings deserve emphasis.
- Use `analysis_brief.md` as scaffolding, not as the final voice.
- If the user asks for stronger business framing, sharpen the narrative without inventing unsupported claims.

## Resources

- `scripts/workflow.py`: entry point for `prepare` and `finalize`.
- `scripts/load_data.py`: load mixed-format tabular files and infer lightweight schema hints.
- `scripts/profile_data.py`: compute overview, per-column stats, missingness, associations, and target-aware rankings.
- `scripts/build_chart_manifest.py`: choose explainable chart candidates from the profiling artifacts.
- `scripts/render_html_report.py`: render the final interactive HTML report.
- `references/report_sections.md`: guidance for report composition without forcing a rigid template.
- `references/chart_rules.md`: visual and explanatory standards for chart selection.
- `references/narrative_grounding.md`: rules for grounded, non-generic insight writing.
