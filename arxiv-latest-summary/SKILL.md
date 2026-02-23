---
name: arxiv-latest-summary
description: Generate education-focused summaries of the latest arXiv papers from plain-language user interests and deliver polished HTML/PDF reports. Use when users want quick understanding of recent technical or academic trends, need help converting interests into valid arXiv queries, want a Codex-native workflow without external LLM API calls in scripts, or want to convert a scoped summary workflow into a recurring Codex automation with a complete task prompt.
---

# ArXiv Latest Summary

## Overview

Run an end-to-end, non-coder-friendly workflow in Codex to create a readable summary of recent arXiv papers.

If the user asks for recurring runs, convert the scoped run into a Codex automation by generating a fully filled task prompt (no placeholders).

Default values:

- `window_days`: `7`
- `max_papers`: `66`
- `chunk_size`: `30`
- `report_style`: `academic formal`

## Scope Rules

- Focus on educational synthesis and quick understanding.
- Do not output numeric paper scores.
- If user asks "which paper is best", provide qualitative recommendations (why to read first), not score formulas.

## Input Explanation (Must Explain Before Asking)

When collecting inputs, explain each field in plain language and give one concrete example.

1. `interest text` (required)
- Meaning: topic the user wants to learn quickly.
- Example: `multimodal LLM agents for robotics`.

2. `window days` (optional, default `7`)
- Meaning: how far back "latest" should look.
- Example: `7` means papers from roughly the last week.

3. `max papers` (optional, default `66`)
- Meaning: maximum number of papers to include.
- Example: `50` for faster reading, `66` for default breadth.

4. `report style` (optional, default `academic formal`)
- Meaning: writing tone and density.
- Example options: `academic formal`, `executive brief`, `beginner-friendly`.

5. `manual arXiv query` (optional)
- Meaning: advanced override; skip auto query generation.
- Example: `(cat:cs.CL OR cat:cs.AI) AND (ti:"large language model" OR abs:"large language model")`.

If user gives only interest text, continue with defaults.

## Optional Automation Inputs (Only If User Asks for Recurring Runs)

Explain these in plain language before asking:

1. `automation name` (optional)
- Meaning: short label shown in Codex automations.
- Example: `Weekly Health AI arXiv Digest`.

2. `schedule` (required for automation)
- Meaning: when to run automatically.
- Example: `every Monday at 09:00`.

3. `workspace path` (required for automation)
- Meaning: absolute directory where this skill and scripts should run.
- Example: `/Users/Placebo/MyTechProjects/codex-skills/arxiv-latest-summary`.

## Suggested User-Facing Prompting Style

Use a short explanation like this before collecting values:

"I can generate a latest arXiv summary for your topic. I need your topic, and optionally: time window (default 7 days), paper count (default 66), writing style (default academic formal), and an optional manual arXiv query if you already have one."

## Workflow

Follow this order.

### 1. Collect Inputs

Collect the five inputs above. Use defaults when missing.

### 2. Build Query

Generate query unless manual query is provided.

```bash
python scripts/interest_query_builder.py \
  --interest "<user_interest>" \
  --window-days <window_days> \
  --max-results <max_papers> \
  --output "<run_dir>/query.json"
```

### 3. Fetch Latest Papers

```bash
python scripts/arxiv_fetch.py \
  --query "<arxiv_query>" \
  --window-days <window_days> \
  --max-results <max_papers> \
  --output-dir "<run_dir>"
```

### 4. Recursive Codex Synthesis (Chunk -> Merge)

Read:

- `references/summary_prompt.md`
- `<run_dir>/catalog.csv`

Create recursive chunk artifacts (30 abstracts per chunk by default):

```bash
python scripts/recursive_summary.py \
  --catalog-csv "<run_dir>/catalog.csv" \
  --output-dir "<run_dir>/recursive" \
  --topic "<user_interest>" \
  --chunk-size 30
```

Then:

- For each file in `<run_dir>/recursive/chunk_inputs/`, write a paired summary file in `<run_dir>/recursive/chunk_summaries/`.
- Follow `<run_dir>/recursive/merge_instructions.md` to combine all chunk summaries.

Write:

- `<run_dir>/analysis.md`

Requirements:

- Explain themes and methods in clear language.
- Highlight key papers with title + URL.
- In `Notable Papers to Read First`, use bullet list and compact citation labels (for example `FENCE`, `TFL`) instead of long citation text.
- Merge chunk outputs into one cohesive summary with minimal redundancy.
- Keep output substantive, useful, and educational.
- Avoid shallow one-line bullets; each major section should include explanatory prose with evidence and practical implications.

### 5. Build Final Markdown Report

```bash
python scripts/report_builder.py \
  --catalog-csv "<run_dir>/catalog.csv" \
  --analysis-md "<run_dir>/analysis.md" \
  --query "<arxiv_query>" \
  --topic "<user_interest>" \
  --window-days <window_days> \
  --report-style "<report_style>" \
  --output-md "<run_dir>/report.md"
```

### 6. Export Pretty HTML + PDF

HTML and PDF must have the same content.

```bash
python scripts/pdf_export.py \
  --input-md "<run_dir>/report.md" \
  --output-html "<run_dir>/report.html" \
  --output-pdf "<run_dir>/report.pdf" \
  --title "<user_interest>: Latest arXiv Summary"
```

### 7. Verify Outputs

Confirm:

- `<run_dir>/query.json`
- `<run_dir>/catalog.csv`
- `<run_dir>/recursive/recursive_manifest.json`
- `<run_dir>/recursive/chunk_inputs/`
- `<run_dir>/recursive/chunk_summaries/`
- `<run_dir>/recursive/merge_instructions.md`
- `<run_dir>/analysis.md`
- `<run_dir>/report.md`
- `<run_dir>/report.html`
- `<run_dir>/report.pdf`

### 8. Optional: Convert Scoped Run to Codex Automation

Only do this when the user explicitly asks for automation.

1. Collect and confirm automation inputs:
- `automation name`
- `schedule`
- `workspace path` (absolute path)

2. Build a complete automation prompt:
- Read `references/automation_prompt.md`.
- Fill all values using the confirmed scope (`interest text`, `window days`, `max papers`, `report style`, and optional manual query).
- Do not leave placeholders like `<user_interest>` in the final prompt.
- Keep schedule and workspace details out of the prompt body; those belong to automation fields.

3. Propose automation directive:
- Use `mode="suggested create"` and include `name`, `prompt`, `rrule`, `cwds`, `status`.
- Use only supported schedule forms:
  - Weekly: `FREQ=WEEKLY;BYDAY=<DAY>;BYHOUR=<HH>;BYMINUTE=<MM>`
  - Hourly interval: `FREQ=HOURLY;INTERVAL=<N>`
- Default `status` to `ACTIVE` unless user asked to pause.

## Quick Mode

Prepare in one command:

```bash
python scripts/workflow.py prepare --interest "<user_interest>"
```

This command now also creates:

- `<run_dir>/recursive/chunk_inputs/` (chunked abstract packs)
- `<run_dir>/recursive/chunk_summaries/` (placeholders for chunk summaries)
- `<run_dir>/recursive/merge_instructions.md` (rules to merge chunks into `analysis.md`)

Finalize after writing `analysis.md`:

```bash
python scripts/workflow.py finalize --run-dir "<run_dir>"
```

## References and Assets

- Query mapping: `references/query_patterns.md`
- Summary template: `references/summary_prompt.md`
- Automation prompt builder: `references/automation_prompt.md`
- Pretty rendering: `assets/report_template.html`, `assets/report_style.css`
