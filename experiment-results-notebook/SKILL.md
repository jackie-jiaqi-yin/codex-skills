---
name: experiment-results-notebook
description: Summarize new experiment results from one local repo plus GitHub context into an incrementally maintained research notebook with polished methodology, results, comparison, Markdown, LaTeX, and PDF exports. Use when researchers want to review newly produced experiment artifacts, compare against the prior best run, preserve evolving lab notes, or detect and polish manual notebook edits into cleaner academic writing.
---

# Experiment Results Notebook

## Overview

Use this skill to turn one experiment workspace into a continuously updated research notebook.

The workflow is designed for iterative research:

- scan one repo root for new or changed experiment artifacts since the last checkpoint,
- inspect local git plus optional GitHub repo and PR context,
- centralize already-run experiments into one readable notebook even when the run order is messy,
- summarize methodology, results, and comparisons in top-conference English,
- preserve the editable notebook as the canonical document,
- export the latest notebook to `Markdown`, `LaTeX`, and `PDF`.

The notebook is user-editable. If the user manually adds or rewrites content and a later run detects those edits, treat them as source material and polish them in place while preserving the meaning.

## Inputs (Resolve Locally Before Asking)

Before asking the user for anything beyond `workspace root`, first resolve what you can from persisted state and the local repo itself.

- Read `.experiment-results-notebook/state/workspace_config.yaml` if it already exists.
- Inspect local git remotes and the current branch to infer GitHub repo and PR context.
- Treat explicit GitHub input from the user as an override, not a default requirement.
- If `workspace root` is already the current repo, do not ask the user for the GitHub link or PR list.

1. `workspace root` (required)
- Meaning: the repo root to analyze.
- Example: `/Users/Placebo/MyExperiments/project-alpha`.

2. `primary metric` (optional, persisted after)
- Meaning: a user hint for ranking or "best run" selection, not the only metric that may be shown.
- Example: `accuracy`, `macro_f1`, or `val_loss`.

3. `direction` (optional, persisted after)
- Meaning: whether higher or lower is better for the ranking metric when the user already knows it.
- Example: `max` for accuracy, `min` for loss.

4. `study title` (optional, default repo name)
- Meaning: human-facing title used in notebook and export headers.
- Example: `Sparse MoE Ablations for Medical QA`.

5. `scope subdir` (optional)
- Meaning: restrict analysis to a subdirectory inside the repo.
- Example: `runs/ablation_round_3`.

6. `GitHub PR URL` (optional override only)
- Meaning: force one specific PR when the user wants to override auto-discovery.
- Default behavior: infer GitHub repo and PR context from the local repo, current branch, repo open PRs, and recent closed PRs.
- Example override: `https://github.com/org/repo/pull/42`.

7. `experiment globs` (optional)
- Meaning: include only paths matching these glob patterns.
- Example: `runs/**`, `outputs/**`.

8. `ignore globs` (optional)
- Meaning: exclude noisy or irrelevant paths.
- Example: `.venv/**`, `node_modules/**`, `checkpoints/**`.

If the user only gives `workspace root`, continue. Ask for a primary metric only if ranking is important and the user already has one in mind.

## GitHub Rules

- Public GitHub repo and PR context should be auto-resolved from the local git remotes and current branch by default.
- On first-time or baseline runs, inspect both open PRs and recent closed PRs so historical experiment context is not lost.
- On later runs, prefer the current-branch PR when one exists, but still keep repo-level PR summaries available.
- Private repo or PR access requires the user to authenticate locally with `gh auth login`.
- If GitHub access is unavailable, continue with local-only analysis and say exactly what context was skipped.

## Mandatory Question Gate

Do not start `workflow.py prepare` until the following is complete.

Lightweight local inspection is allowed before confirmation when it helps resolve values automatically.

1. Resolve what you can without asking:
- workspace root from the user prompt or current repo,
- persisted config from `.experiment-results-notebook/state/workspace_config.yaml`,
- GitHub repo from local git remotes,
- current-branch PR if any,
- repo open PRs,
- recent closed PRs, especially on a first run.
2. Restate the resolved run plan in one short block:
- workspace root
- study title
- primary metric and direction
- scope subdir if any
- GitHub repo and resolved PR context if any
- experiment globs / ignore globs if any
3. Ask for explicit confirmation.
4. Only continue after the user confirms.

## Workflow

Follow this order.

### 1. Prepare Workspace Analysis

Run:

```bash
python scripts/workflow.py prepare \
  --workspace-root "<workspace_root>" \
  --primary-metric "<primary_metric>" \
  --direction <max_or_min> \
  --study-title "<study_title>" \
  --scope-subdir "<scope_subdir>"
```

Only add the override flag when the user explicitly wants to force one PR:

```bash
  --github-pr-url "<github_pr_url>"
```

Use repeated flags when needed:

```bash
  --experiment-glob "runs/**" \
  --experiment-glob "outputs/**" \
  --ignore-glob ".venv/**" \
  --ignore-glob "node_modules/**"
```

`prepare` creates a run directory inside:

- `<workspace_root>/.experiment-results-notebook/entries/<timestamp>/`

It also writes:

- `scan_manifest.json`
- `github_context.json`
- `comparison.json`
- `metrics_summary.json`
- `manual_edits.json`
- `methodology_manifest.json`
- `chart_manifest.json`
- `analysis_brief.md`
- `analysis.md` (template to fill)
- `run_manifest.json`

### 2. Read Context Before Writing

Read:

- `references/report_outline.md`
- `references/methodology_extraction.md`
- `references/chart_rules.md`
- `<run_dir>/analysis_brief.md`
- `<run_dir>/scan_manifest.json`
- `<run_dir>/comparison.json`
- `<run_dir>/manual_edits.json`
- `<run_dir>/github_context.json`
- `<run_dir>/methodology_manifest.json`
- `<run_dir>/chart_manifest.json`

### 3. Write or Revise `analysis.md`

Open `<run_dir>/analysis.md` and replace the template text with a polished notebook entry.

Requirements:

- Use the exact section headings:
  - `## Context`
  - `## Methodology Delta`
  - `## New Results`
  - `## Comparison vs Prior Best`
  - `## Figures and Tables`
  - `## User Notes Revised`
  - `## Risks/Anomalies`
  - `## Next Questions`
- Keep claims grounded in the files, commits, metrics, figures, and GitHub context.
- In `Methodology Delta`, explicitly answer:
  - what data artifact enters the experiment,
  - how that data is cleaned, filtered, merged, downsampled, or otherwise preprocessed,
  - how splits, windows, or sampling are formed,
  - what the model predicts and from which inputs,
  - how evaluation or post-eval ranking is produced.
- Do not assume the user-provided primary metric is the only metric that matters.
- After scanning the outputs, identify the most informative result metrics to display. Prefer metrics that are comparable across runs and useful for fast scientific review.
- If the user-provided primary metric looks weak, sparse, or not representative, say so explicitly and rely on better display metrics while still preserving the user's hint in the notes.
- If comparison is unavailable, say why explicitly.
- If `manual_edits.json` contains revised text, use that material as authoritative content and polish it into clear academic prose.
- Prefer short tables, real figure embeds, concise figure captions, and precise numeric statements over vague praise.
- Use `methodology_manifest.json` to go beyond parameter lists; it exists to surface the operational pipeline hidden behind the configs and code.

### 4. Finalize Notebook and Exports

Run:

```bash
python scripts/workflow.py finalize --run-dir "<run_dir>"
```

This step:

- updates the cumulative `notebook.md`,
- revises detected manual edits in place,
- writes per-run `entry.md`, `entry.tex`, `entry.pdf`,
- writes latest cumulative `results.md`, `results.tex`, `results.pdf`,
- updates the checkpoint state for the next incremental run.

### 5. Verify Outputs

Confirm these exist:

- `<workspace_root>/.experiment-results-notebook/notebook.md`
- `<workspace_root>/.experiment-results-notebook/latest/results.md`
- `<workspace_root>/.experiment-results-notebook/latest/results.tex`
- `<workspace_root>/.experiment-results-notebook/latest/results.pdf`
- `<run_dir>/entry.md`
- `<run_dir>/entry.tex`
- `<run_dir>/entry.pdf`
- `<workspace_root>/.experiment-results-notebook/state/workspace_config.yaml`
- `<workspace_root>/.experiment-results-notebook/state/checkpoint.json`

## Behavior Rules

- First run creates the baseline entry.
- Later runs summarize only new or changed artifacts since the checkpoint.
- Never require the user to provide a GitHub repo link or PR number when the local repo already exposes that information.
- Treat explicit GitHub PR input as an override only; otherwise auto-discover from local git state plus repo PR summaries.
- The notebook's first responsibility is centralization and summarization of existing experiments, not forcing every run into a rigid metric matrix.
- When many metrics are present, choose a small set of headline result metrics plus optional supporting diagnostics rather than dumping every numeric field.
- Supporting code outside the scoped experiment artifact folders may still be methodologically essential. Use repo-level configs, preprocessing scripts, data pipeline code, split utilities, and report scripts when the experiment outputs alone are too shallow.
- The final notebook entry should contain actual tables and actual figure references when those artifacts are available; do not leave `Figures and Tables` as pure narrative.
- If there is no new experiment delta and no detected manual notebook edit, stop after reporting that there is nothing new to append.
- Large binary artifacts should be referenced, not deeply parsed.
- Jupyter notebooks are out of scope as first-class inputs in v1.

## References and Assets

- Report structure and tone: `references/report_outline.md`
- Methodology extraction guidance: `references/methodology_extraction.md`
- Figure and chart rules: `references/chart_rules.md`
- LaTeX template: `assets/report_template.tex`
