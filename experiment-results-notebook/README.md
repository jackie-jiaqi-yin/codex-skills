# experiment-results-notebook

Summarize newly produced experiment artifacts from one local repo into a continuously maintained research notebook, then export the latest notebook as `Markdown`, `LaTeX`, and `PDF`.

## When To Use It

Use this skill when you want to:

- review only the new experiment results since the last summary,
- centralize many already-run experiments into one place even if they were executed in a messy order,
- compare the current delta against the prior best run,
- combine local files, git history, and optional GitHub PR context,
- keep a notebook that researchers can edit manually between runs,
- polish rough user-written notes into cleaner academic prose on the next run.

## What It Produces

Inside the target workspace, the skill maintains:

- `.experiment-results-notebook/notebook.md`
- `.experiment-results-notebook/latest/results.md`
- `.experiment-results-notebook/latest/results.tex`
- `.experiment-results-notebook/latest/results.pdf`
- `.experiment-results-notebook/state/workspace_config.yaml`
- `.experiment-results-notebook/state/checkpoint.json`

Each run also creates:

- `.experiment-results-notebook/entries/<timestamp>/scan_manifest.json`
- `.experiment-results-notebook/entries/<timestamp>/comparison.json`
- `.experiment-results-notebook/entries/<timestamp>/manual_edits.json`
- `.experiment-results-notebook/entries/<timestamp>/methodology_manifest.json`
- `.experiment-results-notebook/entries/<timestamp>/chart_manifest.json`
- `.experiment-results-notebook/entries/<timestamp>/entry.md`
- `.experiment-results-notebook/entries/<timestamp>/entry.tex`
- `.experiment-results-notebook/entries/<timestamp>/entry.pdf`

## Inputs

Usually provided on the first run:

- `workspace root`

Optional:

- `primary metric`
- `direction` as `max` or `min`
- `study title`
- `scope subdir`
- `GitHub PR URL`
- `experiment globs`
- `ignore globs`

The skill persists the metric rule in `.experiment-results-notebook/state/workspace_config.yaml`, but it can still run without one. If no strong primary metric is provided, it should infer which result metrics are most useful to display.

## How To Use In Codex

Copy this into a Codex chat:

```text
Use $experiment-results-notebook to summarize the newest experiment results in one repo.
Workspace root: /absolute/path/to/my/experiment-repo
Primary metric: accuracy
Direction: max
Study title: Ablation Notebook for Retrieval-Augmented QA
Start by restating the resolved run plan and asking me to confirm before execution.
```

Optional PR enrichment:

```text
GitHub PR URL: https://github.com/org/repo/pull/42
```

Optional scan restrictions:

```text
Experiment globs: runs/**, outputs/**
Ignore globs: .venv/**, checkpoints/**
```

## Typical Workflow

1. You provide the repo root and any missing first-run settings.
2. Codex restates the resolved run plan and waits for confirmation.
3. The skill scans the repo for new or changed structured result files, plots, code, and git commits.
4. It optionally fetches public GitHub repo and PR context.
5. It identifies which metrics are actually useful to headline, instead of assuming every numeric field belongs in the summary.
6. It extracts supporting methodology evidence from configs plus repo code such as preprocessing scripts, split/windowing utilities, and report scripts.
7. It prepares manifests, comparisons, compact tables, selected plots, and an `analysis.md` template.
8. Codex writes or revises the analysis entry.
9. The skill updates `notebook.md`, revises detected manual notebook edits in place, and exports the latest `Markdown`, `LaTeX`, and `PDF`.

## Metric Selection Behavior

- `primary metric` is a ranking hint, not a hard requirement.
- The skill should scan all structured outputs and decide which metrics are worth showing in the notebook.
- If the user-provided primary metric is sparse, misleading, or clearly not a result metric, the notebook should say so and still summarize the experiments with better headline metrics.
- The goal is fast scientific review and centralized note-taking, not forcing every project into a rigid matrix.

## Methodology Behavior

- The skill should not rely on experiment outputs alone when those outputs only expose hyperparameters.
- It should trace from experiment artifacts back into supporting repo code to recover the real pipeline:
  - data source,
  - preprocessing/filtering/downsampling,
  - split or window construction,
  - model inputs and target,
  - evaluation and post-eval selection logic.
- The generated notebook should explain `what`, `how`, and `so what`, not just enumerate config values.

## Tables And Figures Behavior

- If compact summary tables exist, the notebook should surface them directly rather than only paraphrasing their conclusions.
- If native experiment plots exist, the notebook should embed a small curated subset of the most informative ones.
- The `Figures and Tables` section should contain actual tables and actual figure references whenever the artifacts are available.

## Manual Notes Behavior

Researchers can manually edit `.experiment-results-notebook/notebook.md`.

On a later run, if the skill detects those edits:

- the user-written content is treated as source material,
- the meaning is preserved,
- the prose is polished into cleaner academic writing,
- the notebook remains the canonical document.

## GitHub Notes

- Public GitHub repo and PR context work by default.
- Private GitHub access requires local authentication with `gh auth login`.
- If GitHub context is unavailable, the skill continues with local-only analysis and reports what was skipped.

## Quick Command Reference

Prepare:

```bash
python scripts/workflow.py prepare \
  --workspace-root "/absolute/path/to/my/experiment-repo" \
  --primary-metric "accuracy" \
  --direction max
```

Finalize after `analysis.md` is written:

```bash
python scripts/workflow.py finalize --run-dir "<run_dir>"
```

## Notes

- The first run creates the baseline entry.
- Later runs summarize only the delta since the saved checkpoint.
- When many metrics are present, the notebook should show a compact set of useful headline metrics instead of dumping every number.
- If there is no experiment delta and no manual notebook edit, the skill reports that there is nothing new to append.
- Jupyter notebooks are not first-class inputs in v1.
