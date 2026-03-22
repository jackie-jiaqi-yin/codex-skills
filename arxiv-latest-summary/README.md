# arxiv-latest-summary

Generate readable summaries of the latest arXiv papers from a plain-language topic, then export polished `Markdown`, `HTML`, and `PDF` reports.

## When To Use It

Use this skill when you want to:

- quickly understand a topic through recent arXiv papers,
- turn a broad interest into a valid arXiv query,
- get one concise report instead of reading many abstracts,
- optionally convert the run into a recurring Codex automation.

## What It Produces

A typical run writes artifacts like:

- `outputs/<date>/<topic-slug>/query.json`
- `outputs/<date>/<topic-slug>/catalog.csv`
- `outputs/<date>/<topic-slug>/analysis.md`
- `outputs/<date>/<topic-slug>/report.md`
- `outputs/<date>/<topic-slug>/report.html`
- `outputs/<date>/<topic-slug>/report.pdf`

## Inputs

Required:

- `interest text`

Optional:

- `window days` with default `7`
- `max papers` with default `66`
- `report style` with default `academic formal`
- `manual arXiv query`

## How To Use In Codex

Copy this into a Codex chat:

```text
Use $arxiv-latest-summary to summarize the latest arXiv papers for my topic.
Interest text: multimodal LLM agents for robotics.
Window days: 14.
Max papers: 40.
Report style: academic formal.
Start by restating the resolved run plan and asking me to confirm before execution.
```

The skill should ask for missing inputs, restate the resolved plan, and wait for your confirmation before it runs anything.

## Typical Workflow

1. You provide the topic and optional constraints.
2. Codex confirms the run plan.
3. The skill builds or accepts an arXiv query.
4. It fetches recent papers and prepares chunked synthesis inputs.
5. Codex writes `analysis.md`.
6. The skill renders the final `Markdown`, `HTML`, and `PDF` report.
7. After the run, Codex asks whether you want to turn it into a recurring automation.

## Quick Command Reference

Prepare:

```bash
python scripts/workflow.py prepare --interest "multimodal LLM agents for robotics"
```

Finalize after `analysis.md` is written:

```bash
python scripts/workflow.py finalize --run-dir "<run_dir>"
```

## Notes

- This skill is designed to ask questions first and not execute until you confirm.
- If you provide a manual arXiv query, it skips auto query generation.
- For recurring runs, the skill can propose a Codex automation prompt after a successful report.
