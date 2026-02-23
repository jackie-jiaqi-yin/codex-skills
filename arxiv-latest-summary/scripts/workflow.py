#!/usr/bin/env python3
"""Convenience workflow for prepare/finalize steps.

Prepare mode:
- generate arXiv query
- fetch latest papers
- create recursive chunk inputs for staged summarization
- create run manifest + analysis template

Finalize mode:
- build report markdown
- render pretty HTML + PDF
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from arxiv_fetch import fetch_latest_papers, write_catalog
from interest_query_builder import build_query
from recursive_summary import generate_recursive_pack


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower())
    return slug.strip("-") or "topic"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _analysis_template(topic: str, report_style: str) -> str:
    return f"""## Key Research Themes

Summarize 4-6 major themes for "{topic}" from recursive chunk summaries.
Use a numbered list (1., 2., 3., ...).
For each theme item, start with `**<theme keyword>:**` and write a paragraph (4-7 sentences) that includes:
- what the theme is,
- what changed in this recent window,
- why it matters for researchers/practitioners.
Use citations (title + arXiv URL) as evidence.

## Methodological Approaches

Describe 3-6 recurring approaches.
Use a numbered list (1., 2., 3., ...).
For each approach item, start with `**<approach keyword>:**` and write a paragraph (4-7 sentences) with mechanism, strengths, tradeoffs, and at least one caveat/failure mode.
Cite papers for each approach.

## Notable Papers to Read First

Pick up to 6 papers and explain for each bullet (2-4 sentences):
- What the paper is about in plain language
- Why it matters now
- Who should read it first
- Caveat or best-use context

## What Is New in This Window

Write 3-5 substantial bullets on notable shifts.
Each bullet should include a "then vs now" contrast supported by citations.

## Challenges and Future Directions

Write 4-6 numbered challenges.
Each challenge should include:
- concrete bottleneck,
- evidence from papers,
- plausible near-term direction.

## Concluding Overview

Write 10-14 sentences in {report_style} tone.
End with a 2-3 sentence reading order recommendation for newcomers.
"""


def _prepare(args: argparse.Namespace) -> int:
    date_part = datetime.now().strftime("%Y-%m-%d")
    topic_slug = _slugify(args.topic or args.interest)

    run_dir = Path(args.output_root) / date_part / topic_slug
    run_dir.mkdir(parents=True, exist_ok=True)

    query_result = build_query(
        interest=args.interest,
        strictness=args.strictness,
        window_days=args.window_days,
        max_results=args.max_results,
        manual_query=args.query,
        include_categories=[c.strip() for c in args.include_categories.split(",") if c.strip()] if args.include_categories else [],
        exclude_categories=[c.strip() for c in args.exclude_categories.split(",") if c.strip()] if args.exclude_categories else [],
    )

    query_payload = {
        "interest": query_result.interest,
        "query": query_result.query,
        "strictness": query_result.strictness,
        "window_days": query_result.window_days,
        "max_results": query_result.max_results,
        "categories": query_result.categories,
        "keywords": query_result.keywords,
        "notes": query_result.notes,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    _write_json(run_dir / "query.json", query_payload)

    records, meta = fetch_latest_papers(
        query=query_result.query,
        window_days=args.window_days,
        max_results=args.max_results,
        timeout_sec=args.timeout_sec,
    )

    if not records:
        raise SystemExit("No arXiv papers found for this query. Try a broader interest or strictness=broad.")

    catalog_path = write_catalog(records, run_dir)

    recursive_payload = generate_recursive_pack(
        catalog_csv=catalog_path,
        output_dir=run_dir / "recursive",
        topic=args.topic or args.interest,
        chunk_size=args.chunk_size,
    )

    fetch_payload = {
        "query": query_result.query,
        "returned_count": len(records),
        "window_days": args.window_days,
        "max_results": args.max_results,
        "metadata": meta,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    _write_json(run_dir / "fetch_metadata.json", fetch_payload)

    analysis_path = run_dir / "analysis.md"
    if not analysis_path.exists():
        analysis_path.write_text(_analysis_template(args.topic or args.interest, args.report_style), encoding="utf-8")

    manifest = {
        "topic": args.topic or args.interest,
        "interest": args.interest,
        "run_dir": str(run_dir),
        "window_days": args.window_days,
        "max_results": args.max_results,
        "chunk_size": args.chunk_size,
        "report_style": args.report_style,
        "query": query_result.query,
        "catalog_csv": str(catalog_path),
        "recursive_manifest": recursive_payload["recursive_manifest"],
        "recursive_chunk_inputs_dir": recursive_payload["chunk_inputs_dir"],
        "recursive_chunk_summaries_dir": recursive_payload["chunk_summaries_dir"],
        "recursive_merge_instructions": recursive_payload["merge_instructions"],
        "recursive_chunk_count": recursive_payload["chunk_count"],
        "analysis_md": str(analysis_path),
        "report_md": str(run_dir / "report.md"),
        "report_html": str(run_dir / "report.html"),
        "report_pdf": str(run_dir / "report.pdf"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    _write_json(run_dir / "run_manifest.json", manifest)

    print(json.dumps(manifest, indent=2))
    return 0


def _finalize(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir)
    manifest_path = run_dir / "run_manifest.json"
    if not manifest_path.exists():
        raise SystemExit(f"Missing manifest: {manifest_path}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    catalog_csv = Path(manifest["catalog_csv"])
    analysis_md = Path(manifest["analysis_md"])
    report_md = Path(manifest["report_md"])
    report_html = Path(manifest["report_html"])
    report_pdf = Path(manifest["report_pdf"])

    if not analysis_md.exists():
        raise SystemExit(f"Missing analysis file: {analysis_md}")

    report_builder = SCRIPT_DIR / "report_builder.py"
    pdf_exporter = SCRIPT_DIR / "pdf_export.py"

    build_cmd = [
        sys.executable,
        str(report_builder),
        "--catalog-csv",
        str(catalog_csv),
        "--analysis-md",
        str(analysis_md),
        "--query",
        manifest["query"],
        "--topic",
        manifest["topic"],
        "--window-days",
        str(manifest["window_days"]),
        "--report-style",
        manifest["report_style"],
        "--output-md",
        str(report_md),
    ]
    subprocess.run(build_cmd, check=True)

    export_cmd = [
        sys.executable,
        str(pdf_exporter),
        "--input-md",
        str(report_md),
        "--output-html",
        str(report_html),
        "--output-pdf",
        str(report_pdf),
        "--title",
        args.title or f"{manifest['topic']}: Latest arXiv Summary",
    ]
    subprocess.run(export_cmd, check=True)

    print(
        json.dumps(
            {
                "run_dir": str(run_dir),
                "report_md": str(report_md),
                "report_html": str(report_html),
                "report_pdf": str(report_pdf),
            },
            indent=2,
        )
    )

    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepare/finalize latest arXiv summary workflow")
    sub = parser.add_subparsers(dest="command", required=True)

    prepare = sub.add_parser("prepare", help="Generate query, fetch papers, and create run files")
    prepare.add_argument("--interest", required=True, help="Plain-language user interest")
    prepare.add_argument("--topic", help="Optional display topic for report title")
    prepare.add_argument("--query", help="Optional explicit arXiv query override")
    prepare.add_argument("--strictness", default="normal", choices=["broad", "normal", "focused"])
    prepare.add_argument("--window-days", type=int, default=7)
    prepare.add_argument("--max-results", type=int, default=66)
    prepare.add_argument("--chunk-size", type=int, default=30)
    prepare.add_argument("--report-style", default="academic formal")
    prepare.add_argument("--include-categories")
    prepare.add_argument("--exclude-categories")
    prepare.add_argument("--timeout-sec", type=int, default=30)
    prepare.add_argument("--output-root", default=str(SCRIPT_DIR.parent / "outputs"))

    finalize = sub.add_parser("finalize", help="Build report and export HTML/PDF")
    finalize.add_argument("--run-dir", required=True)
    finalize.add_argument("--title", help="Optional report title override")

    return parser


def main() -> int:
    args = _build_parser().parse_args()
    if args.command == "prepare":
        return _prepare(args)
    if args.command == "finalize":
        return _finalize(args)
    raise SystemExit(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
