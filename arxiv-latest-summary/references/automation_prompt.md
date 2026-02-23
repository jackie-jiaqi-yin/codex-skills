# Automation Prompt Builder

Use this reference only when the user explicitly asks to turn a scoped run into recurring automation.

## Goal

Produce two deliverables:

1. A complete automation task prompt with concrete values.
2. A suggested Codex automation directive that uses that prompt.

## Inputs Required

From summary scope:

- `interest text`
- `window days`
- `max papers`
- `report style`
- `manual arXiv query` (optional)
- `strictness` (default `normal`)
- `chunk size` (default `30`)

From automation setup:

- `automation name`
- `schedule` (weekly or hourly interval)
- `workspace path` (absolute)

## Prompt Quality Rules

- Write a fully filled prompt, not a template.
- Do not leave placeholders such as `<run_dir>` or `<user_interest>`.
- Keep schedule and workspace path out of prompt body.
- Make the prompt self-sufficient: include exact commands, output expectations, and fallback behavior.
- Keep the task focused on workflow execution, synthesis quality, and output reporting.

## Prompt Construction Pattern

Use this structure and fill values concretely:

```markdown
Generate the latest arXiv summary for this fixed scope and produce final report artifacts.

Scope:
- Interest: "<interest text>"
- Window days: <window days>
- Max papers: <max papers>
- Report style: "<report style>"
- Strictness: "<strictness>"
- Manual query override: <manual query text or "none">
- Chunk size: <chunk size>

Execution requirements:
1. Run prepare:
   python scripts/workflow.py prepare --interest "<interest text>" --window-days <window days> --max-results <max papers> --strictness <strictness> --chunk-size <chunk size> --report-style "<report style>" [--query "<manual query>"]
2. Read the generated run manifest JSON and capture `run_dir`.
3. Read:
   - references/summary_prompt.md
   - <run_dir>/catalog.csv
   - <run_dir>/recursive/chunk_inputs/*.md
   - <run_dir>/recursive/merge_instructions.md
4. Create all chunk summaries under:
   - <run_dir>/recursive/chunk_summaries/
5. Merge chunk summaries into:
   - <run_dir>/analysis.md
6. Finalize report artifacts:
   python scripts/workflow.py finalize --run-dir "<run_dir>"

Output requirements:
- Return a concise run summary with paper count, date range, and key themes.
- Return absolute paths for:
  - <run_dir>/query.json
  - <run_dir>/catalog.csv
  - <run_dir>/analysis.md
  - <run_dir>/report.md
  - <run_dir>/report.html
  - <run_dir>/report.pdf

Fallback:
- If zero papers are found, rerun prepare once with `--strictness broad` and keep other scope values unchanged.
```

## Directive Pattern

After writing the complete prompt, emit a suggested create directive with concrete values:

```text
::automation-update{mode="suggested create" name="<automation name>" prompt="<complete prompt>" rrule="<RRULE>" cwds="<workspace path>" status="ACTIVE"}
```

RRULE constraints:

- Weekly schedule: `FREQ=WEEKLY;BYDAY=<DAY>;BYHOUR=<HH>;BYMINUTE=<MM>`
- Hourly schedule: `FREQ=HOURLY;INTERVAL=<N>`
