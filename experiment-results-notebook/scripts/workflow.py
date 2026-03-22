#!/usr/bin/env python3
"""Prepare and finalize the experiment results notebook workflow."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from build_comparison import build_comparison
from common import (
    NOTEBOOK_DIRNAME,
    REQUIRED_SECTION_TITLES,
    now_utc_iso,
    read_json,
    read_yaml,
    timestamp_slug,
    write_json,
    write_yaml,
)
from detect_manual_edits import detect_manual_edits
from extract_methodology_context import extract_methodology_context
from export_latex_pdf import export_markdown
from fetch_github_context import fetch_github_context
from render_charts import render_charts
from render_report import render_report
from scan_workspace import scan_workspace


def _analysis_template() -> str:
    sections = []
    for title in REQUIRED_SECTION_TITLES:
        sections.append(f"## {title}\n\nReplace this section with polished notebook prose grounded in the generated evidence files.\n")
    return "\n".join(sections).rstrip() + "\n"


def _analysis_brief(
    scan_manifest: dict[str, Any],
    comparison: dict[str, Any],
    github_context: dict[str, Any],
    manual_edits: dict[str, Any],
    methodology_manifest: dict[str, Any],
    chart_manifest: dict[str, Any],
    run_dir: Path,
) -> str:
    lines = [
        f"# Analysis Brief for `{run_dir.name}`",
        "",
        "Use this brief together with the JSON artifacts to write `analysis.md`.",
        "",
        "## Ground Truth",
        f"- Workspace: `{scan_manifest.get('workspace_root')}`",
        f"- Study title: {scan_manifest.get('study_title')}",
        f"- Baseline run: `{scan_manifest.get('baseline')}`",
        f"- Changed artifacts: {len(scan_manifest.get('changed_artifacts', []))}",
        f"- Removed paths: {len(scan_manifest.get('removed_paths', []))}",
        f"- Current runs detected: {comparison.get('current_run_count', 0)}",
        f"- Historical runs available: {comparison.get('history_run_count', 0)}",
        f"- Manual edit revisions detected: {len(manual_edits.get('edited_sections', [])) + len(manual_edits.get('orphan_notes', []))}",
        f"- Figures available: {chart_manifest.get('figure_count', 0)}",
        f"- Tables available: {chart_manifest.get('table_count', 0)}",
        f"- Display metrics: {', '.join(comparison.get('display_metrics', [])) or 'none'}",
        f"- Ranking metric: {comparison.get('ranking_metric') or 'none'} ({comparison.get('ranking_source', 'none')})",
        "",
        "## Writing Rules",
        "- Answer the core methodology questions explicitly: what data enters the pipeline, how it is preprocessed, how it is split or sampled, what the model predicts, and how evaluation is done.",
        "- Be explicit about what changed in code, config, data, or evaluation procedure.",
        "- Use exact metric values when available, and prioritize the best display metrics rather than dumping every numeric field.",
        "- Do not stop at parameter lists. Explain what the parameters imply operationally and why they matter for the experiment.",
        "- Separate confirmed facts from inference.",
        "- If the user-provided primary metric is weak or missing, summarize the experiments anyway and rely on the inferred display metrics.",
        "- If manual notebook edits were detected, preserve their claims but rewrite the prose into clearer academic English.",
        "",
        "## Evidence Files",
        f"- `scan_manifest.json`: {run_dir / 'scan_manifest.json'}",
        f"- `comparison.json`: {run_dir / 'comparison.json'}",
        f"- `metrics_summary.json`: {run_dir / 'metrics_summary.json'}",
        f"- `github_context.json`: {run_dir / 'github_context.json'}",
        f"- `manual_edits.json`: {run_dir / 'manual_edits.json'}",
        f"- `methodology_manifest.json`: {run_dir / 'methodology_manifest.json'}",
        f"- `chart_manifest.json`: {run_dir / 'chart_manifest.json'}",
        "",
    ]

    sections = methodology_manifest.get("sections", [])
    if sections:
        lines.append("## Auto-Extracted Methodology Evidence")
        for section in sections:
            bullets = section.get("summary_bullets", [])
            evidence = section.get("evidence", [])
            if not bullets and not evidence:
                continue
            lines.append(f"### {section.get('title')}")
            for bullet in bullets[:4]:
                lines.append(f"- {bullet}")
            if evidence:
                for item in evidence[:2]:
                    lines.append(
                        f"- Evidence file: `{item.get('path')}`"
                        + (f" | snippets: {' ; '.join(item.get('snippets', [])[:2])}" if item.get("snippets") else "")
                    )
            lines.append("")

    prior_best = comparison.get("prior_best")
    current_best = comparison.get("current_best")
    if current_best:
        lines.append("## Current Best")
        lines.append(
            f"- `{current_best.get('run_id')}`: "
            f"{comparison.get('ranking_metric') or 'ranking metric'} = {current_best.get('ranking_metric_value')}"
        )
        lines.append("")
    if prior_best:
        lines.append("## Historical Prior Best")
        lines.append(
            f"- `{prior_best.get('run_id')}`: "
            f"{comparison.get('ranking_metric') or 'ranking metric'} = {prior_best.get('ranking_metric_value')}"
        )
        lines.append("")
    if github_context.get("pull_request"):
        pr = github_context["pull_request"]
        lines.append("## Related PR")
        lines.append(f"- [{pr.get('title')}]({pr.get('html_url')})")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _resolve_config(args: argparse.Namespace, config_path: Path) -> dict[str, Any]:
    existing = read_yaml(config_path, default={})
    config = {
        "primary_metric": args.primary_metric if args.primary_metric is not None else existing.get("primary_metric", ""),
        "direction": args.direction if args.direction is not None else existing.get("direction", ""),
        "study_title": args.study_title or existing.get("study_title") or Path(args.workspace_root).resolve().name,
        "scope_subdir": args.scope_subdir or existing.get("scope_subdir") or "",
        "experiment_globs": args.experiment_glob or existing.get("experiment_globs") or [],
        "ignore_globs": args.ignore_glob or existing.get("ignore_globs") or [],
        "language": existing.get("language") or "en",
    }
    write_yaml(config_path, config)
    return config


def _write_run_manifest(run_manifest_path: Path, payload: dict[str, Any]) -> None:
    write_json(run_manifest_path, payload)
    print(json.dumps(payload, indent=2))


def _prepare(args: argparse.Namespace) -> int:
    workspace_root = Path(args.workspace_root).resolve()
    notebook_root = workspace_root / NOTEBOOK_DIRNAME
    state_dir = notebook_root / "state"
    entries_root = notebook_root / "entries"
    latest_dir = notebook_root / "latest"
    notebook_path = notebook_root / "notebook.md"
    config_path = state_dir / "workspace_config.yaml"
    checkpoint_path = state_dir / "checkpoint.json"

    state_dir.mkdir(parents=True, exist_ok=True)
    entries_root.mkdir(parents=True, exist_ok=True)
    latest_dir.mkdir(parents=True, exist_ok=True)

    config = _resolve_config(args, config_path)
    checkpoint = read_json(checkpoint_path, default={})

    entry_id = timestamp_slug()
    run_dir = entries_root / entry_id
    figures_dir = run_dir / "figures"
    run_dir.mkdir(parents=True, exist_ok=True)

    scan_manifest = scan_workspace(
        workspace_root=workspace_root,
        checkpoint=checkpoint,
        primary_metric=config["primary_metric"],
        study_title=config["study_title"],
        scope_subdir=config["scope_subdir"] or None,
        experiment_globs=config["experiment_globs"],
        ignore_globs=config["ignore_globs"],
    )
    write_json(run_dir / "scan_manifest.json", scan_manifest)

    manual_edits = detect_manual_edits(notebook_path, checkpoint)
    write_json(run_dir / "manual_edits.json", manual_edits)

    has_new_content = bool(scan_manifest.get("has_delta") or manual_edits.get("has_manual_edits"))
    github_context = fetch_github_context(
        workspace_root=workspace_root,
        scan_manifest=scan_manifest,
        github_pr_url=args.github_pr_url,
    )
    write_json(run_dir / "github_context.json", github_context)

    comparison, metrics_summary = build_comparison(
        scan_manifest=scan_manifest,
        entries_root=entries_root,
        primary_metric=config["primary_metric"],
        direction=config["direction"],
    )
    metrics_summary["entry_id"] = entry_id
    write_json(run_dir / "comparison.json", comparison)
    write_json(run_dir / "metrics_summary.json", metrics_summary)

    methodology_manifest = extract_methodology_context(
        workspace_root=workspace_root,
        scan_manifest=scan_manifest,
    )
    write_json(run_dir / "methodology_manifest.json", methodology_manifest)

    chart_manifest = render_charts(
        scan_manifest=scan_manifest,
        comparison=comparison,
        workspace_root=workspace_root,
        output_dir=figures_dir,
    )
    write_json(run_dir / "chart_manifest.json", chart_manifest)

    analysis_md = run_dir / "analysis.md"
    if not analysis_md.exists():
        analysis_md.write_text(_analysis_template(), encoding="utf-8")

    analysis_brief = run_dir / "analysis_brief.md"
    analysis_brief.write_text(
        _analysis_brief(
            scan_manifest,
            comparison,
            github_context,
            manual_edits,
            methodology_manifest,
            chart_manifest,
            run_dir,
        ),
        encoding="utf-8",
    )

    run_manifest = {
        "generated_at": now_utc_iso(),
        "status": "ready" if has_new_content else "no_changes",
        "entry_id": entry_id,
        "workspace_root": str(workspace_root),
        "notebook_root": str(notebook_root),
        "run_dir": str(run_dir),
        "entry_md": str(run_dir / "entry.md"),
        "entry_tex": str(run_dir / "entry.tex"),
        "entry_pdf": str(run_dir / "entry.pdf"),
        "notebook_md": str(notebook_path),
        "latest_md": str(latest_dir / "results.md"),
        "latest_tex": str(latest_dir / "results.tex"),
        "latest_pdf": str(latest_dir / "results.pdf"),
        "analysis_md": str(analysis_md),
        "analysis_brief": str(analysis_brief),
        "scan_manifest": str(run_dir / "scan_manifest.json"),
        "comparison": str(run_dir / "comparison.json"),
        "metrics_summary": str(run_dir / "metrics_summary.json"),
        "github_context": str(run_dir / "github_context.json"),
        "manual_edits": str(run_dir / "manual_edits.json"),
        "methodology_manifest": str(run_dir / "methodology_manifest.json"),
        "chart_manifest": str(run_dir / "chart_manifest.json"),
        "workspace_config": str(config_path),
        "checkpoint": str(checkpoint_path),
        "github_pr_url": args.github_pr_url or "",
        "template": str(SCRIPT_DIR.parent / "assets" / "report_template.tex"),
    }
    _write_run_manifest(run_dir / "run_manifest.json", run_manifest)
    return 0


def _finalize(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir).resolve()
    run_manifest = read_json(run_dir / "run_manifest.json")
    if not run_manifest:
        raise SystemExit(f"Missing run manifest in {run_dir}")

    if run_manifest.get("status") == "no_changes":
        print(json.dumps({"status": "no_changes", "run_dir": str(run_dir)}, indent=2))
        return 0

    render_payload = render_report(
        entry_id=run_manifest["entry_id"],
        workspace_root=Path(run_manifest["workspace_root"]),
        notebook_path=Path(run_manifest["notebook_md"]),
        entry_md_path=Path(run_manifest["entry_md"]),
        latest_md_path=Path(run_manifest["latest_md"]),
        analysis_md_path=Path(run_manifest["analysis_md"]),
        scan_manifest=read_json(Path(run_manifest["scan_manifest"])),
        comparison=read_json(Path(run_manifest["comparison"])),
        github_context=read_json(Path(run_manifest["github_context"])),
        methodology_manifest=read_json(Path(run_manifest["methodology_manifest"])),
        chart_manifest=read_json(Path(run_manifest["chart_manifest"])),
        manual_edits=read_json(Path(run_manifest["manual_edits"])),
    )
    write_json(run_dir / "render_manifest.json", render_payload)

    template_path = Path(run_manifest["template"])
    study_title = read_json(Path(run_manifest["scan_manifest"])).get("study_title", "Experiment Results Notebook")

    export_markdown(
        markdown_path=Path(run_manifest["entry_md"]),
        tex_path=Path(run_manifest["entry_tex"]),
        pdf_path=Path(run_manifest["entry_pdf"]),
        title=f"{study_title} Entry {run_manifest['entry_id']}",
        template_path=template_path,
    )
    export_markdown(
        markdown_path=Path(run_manifest["latest_md"]),
        tex_path=Path(run_manifest["latest_tex"]),
        pdf_path=Path(run_manifest["latest_pdf"]),
        title=f"{study_title} Experiment Results Notebook",
        template_path=template_path,
    )

    scan_manifest = read_json(Path(run_manifest["scan_manifest"]))
    github_context = read_json(Path(run_manifest["github_context"]))
    checkpoint = {
        "updated_at": now_utc_iso(),
        "last_commit_sha": scan_manifest.get("current_commit", ""),
        "artifact_fingerprints": scan_manifest.get("artifact_fingerprints", {}),
        "last_seen_github": {
            "repo_updated_at": ((github_context.get("repo") or {}).get("updated_at") or ""),
            "pull_request_updated_at": ((github_context.get("pull_request") or {}).get("updated_at") or ""),
        },
        "entry_index": [
            {
                "entry_id": path.parent.name,
                "path": str(path.parent),
            }
            for path in sorted((Path(run_manifest["notebook_root"]) / "entries").glob("*/entry.md"))
        ],
        "section_hashes": render_payload.get("section_hashes", {}),
    }
    write_json(Path(run_manifest["checkpoint"]), checkpoint)

    final_payload = {
        "status": "finalized",
        "run_dir": str(run_dir),
        "entry_md": run_manifest["entry_md"],
        "entry_tex": run_manifest["entry_tex"],
        "entry_pdf": run_manifest["entry_pdf"],
        "latest_md": run_manifest["latest_md"],
        "latest_tex": run_manifest["latest_tex"],
        "latest_pdf": run_manifest["latest_pdf"],
        "checkpoint": run_manifest["checkpoint"],
    }
    print(json.dumps(final_payload, indent=2))
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepare and finalize experiment notebook runs")
    sub = parser.add_subparsers(dest="command", required=True)

    prepare = sub.add_parser("prepare", help="Scan workspace and create analysis inputs")
    prepare.add_argument("--workspace-root", required=True)
    prepare.add_argument("--primary-metric")
    prepare.add_argument("--direction", choices=["max", "min"])
    prepare.add_argument("--study-title")
    prepare.add_argument("--scope-subdir")
    prepare.add_argument("--github-pr-url")
    prepare.add_argument("--experiment-glob", action="append", default=[])
    prepare.add_argument("--ignore-glob", action="append", default=[])

    finalize = sub.add_parser("finalize", help="Update notebook and export Markdown/LaTeX/PDF")
    finalize.add_argument("--run-dir", required=True)
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    if args.command == "prepare":
        return _prepare(args)
    return _finalize(args)


if __name__ == "__main__":
    raise SystemExit(main())
