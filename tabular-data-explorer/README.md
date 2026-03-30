# tabular-data-explorer

Interactive tabular data profiling for Codex, tuned for explainable analysis.

This skill ingests mixed-format tabular data such as `csv`, `xlsx`, and `parquet`, computes deterministic EDA artifacts, and helps Codex produce a grounded interactive HTML report with explainable charts.

It is especially aimed at health, epidemiology, biostatistics, biology, and broader life-science workflows where users need to inspect missingness structure, multicollinearity, follow-up variables, and target-aware relationships before choosing interpretable downstream methods.

## Scope

Current v1 capabilities:

- descriptive statistics
- type-aware column profiling
- missingness analysis
- numeric/categorical association analysis
- feature-feature correlation screening for multicollinearity review
- optional target-aware feature exploration
- interactive HTML report generation
- compact embedded plot rendering for layout-stable HTML output

Current non-goals:

- clustering
- anomaly detection
- model training
- SHAP or model explainability

## Main files

- `SKILL.md`: Codex-facing workflow and execution guidance
- `scripts/workflow.py`: prepare/finalize entry point
- `scripts/load_data.py`: file ingestion
- `scripts/profile_data.py`: profiling logic
- `scripts/build_chart_manifest.py`: chart selection metadata
- `scripts/render_html_report.py`: HTML renderer

## Example workflow

Prepare a run:

```bash
python scripts/workflow.py prepare \
  --input-path /absolute/path/to/data.parquet \
  --target-column churn \
  --primary-column revenue \
  --report-title "Churn dataset exploration"
```

Then finalize the HTML:

```bash
python scripts/workflow.py finalize \
  --run-dir /absolute/path/to/.tabular-data-explorer/runs/<timestamp>
```

The main deliverable is:

- `<run_dir>/report.html`
