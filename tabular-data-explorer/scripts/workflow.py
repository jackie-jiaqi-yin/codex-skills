#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path

from build_chart_manifest import build_chart_manifest
from common import ensure_dir, iso_now, timestamp_slug, write_json
from load_data import load_dataset
from profile_data import build_analysis_brief, build_profile


def _write_analysis_template(run_dir: Path, brief: str) -> None:
    template = f"""# Narrative Draft

Use this file to turn the deterministic artifacts into a grounded story for this dataset.

Suggested angles:

- what is structurally unusual about the dataset,
- where the main data quality risks sit,
- which distributions deserve attention,
- which relationships look strong enough to investigate,
- what target-aware signals stand out, if targets were provided,
- what next checks should happen before modeling or reporting.

Rules:

- use exact column names,
- cite quantitative evidence when possible,
- avoid generic filler,
- separate descriptive evidence from interpretation,
- remove any section that has no real signal.

{brief}
"""
    (run_dir / "analysis.md").write_text(template)


def prepare_run(args) -> Path:
    df, metadata = load_dataset(args.input_path, sheet_name=args.sheet_name)
    report_title = args.report_title or metadata["dataset_name"].replace("_", " ").replace("-", " ").title()

    output_root = (
        Path(args.output_root).expanduser().resolve()
        if args.output_root
        else Path(metadata["input_path"]).parent / ".tabular-data-explorer" / "runs"
    )
    run_dir = ensure_dir(output_root / timestamp_slug())

    profile = build_profile(
        df,
        primary_columns=args.primary_column,
        target_columns=args.target_column,
        ignore_columns=args.ignore_column,
    )
    chart_manifest = build_chart_manifest(
        profile["overview"],
        profile["column_profiles"],
        profile["missingness"],
        profile["associations"],
        profile["target_analysis"],
    )
    brief = build_analysis_brief(
        profile["overview"],
        profile["missingness"],
        profile["associations"],
        profile["target_analysis"],
    )

    run_manifest = {
        **metadata,
        "report_title": report_title,
        "run_dir": str(run_dir),
        "created_at": iso_now(),
        "primary_columns": args.primary_column,
        "target_columns": args.target_column,
        "ignore_columns": args.ignore_column,
        "auto_excluded_columns": profile["overview"].get("auto_excluded_columns", []),
    }

    write_json(run_dir / "run_manifest.json", run_manifest)
    write_json(run_dir / "profile_overview.json", profile["overview"])
    write_json(run_dir / "column_profiles.json", profile["column_profiles"])
    write_json(run_dir / "missingness.json", profile["missingness"])
    write_json(run_dir / "associations.json", profile["associations"])
    write_json(run_dir / "target_analysis.json", profile["target_analysis"])
    write_json(run_dir / "chart_manifest.json", chart_manifest)
    (run_dir / "analysis_brief.md").write_text(brief)
    _write_analysis_template(run_dir, brief)
    return run_dir


def finalize_run(args) -> Path:
    run_dir = Path(args.run_dir).expanduser().resolve()
    from render_html_report import render_report
    return render_report(run_dir, args.output_path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Tabular Data Explorer workflow")
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare", help="Create deterministic profiling artifacts")
    prepare.add_argument("--input-path", required=True)
    prepare.add_argument("--sheet-name", default=None)
    prepare.add_argument("--report-title", default=None)
    prepare.add_argument("--output-root", default=None)
    prepare.add_argument("--primary-column", action="append", default=[])
    prepare.add_argument("--target-column", action="append", default=[])
    prepare.add_argument("--ignore-column", action="append", default=[])

    finalize = subparsers.add_parser("finalize", help="Render the interactive HTML report")
    finalize.add_argument("--run-dir", required=True)
    finalize.add_argument("--output-path", default=None)
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "prepare":
        run_dir = prepare_run(args)
        print(run_dir)
    elif args.command == "finalize":
        output = finalize_run(args)
        print(output)


if __name__ == "__main__":
    main()
