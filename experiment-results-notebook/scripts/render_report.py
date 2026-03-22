#!/usr/bin/env python3
"""Render one notebook entry and update the cumulative notebook."""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

from common import (
    REQUIRED_SECTION_TITLES,
    remove_entry_blocks,
    parse_h2_sections,
    read_json,
    replace_section_content,
    section_hash_index,
    write_json,
)


def _format_cell(value: Any) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, float):
        return f"{value:.4f}" if abs(value) < 1000 else f"{value:.3g}"
    return str(value)


def _markdown_table(columns: list[str], rows: list[dict[str, Any]]) -> str:
    if not columns or not rows:
        return "No table rows were available."
    header = "| " + " | ".join(columns) + " |\n"
    header += "|" + "|".join(["---"] + ["---:" for _ in columns[1:]]) + "|\n"
    body = []
    for row in rows:
        cells = [_format_cell(row.get(column)) for column in columns]
        body.append("| " + " | ".join(cells) + " |")
    return header + "\n".join(body)


def _comparison_table(comparison: dict[str, Any]) -> str:
    rows = comparison.get("comparison_rows", [])
    if not rows:
        return "No comparable current runs with structured metrics were detected."

    display_metrics = comparison.get("display_metrics", [])[:4]
    ranking_metric = comparison.get("ranking_metric") or ""
    columns = ["Run", *display_metrics]
    if ranking_metric:
        columns.append("Delta vs prior best")

    rendered_rows: list[dict[str, Any]] = []
    for row in rows:
        rendered = {"Run": f"`{row.get('run_id', 'unknown')}`"}
        per_run_metrics = row.get("display_metrics", {})
        for metric in display_metrics:
            rendered[metric] = per_run_metrics.get(metric)
        if ranking_metric:
            rendered["Delta vs prior best"] = row.get("delta_vs_prior_best")
        rendered_rows.append(rendered)
    return _markdown_table(columns, rendered_rows)


def _figure_block(figures: list[dict[str, Any]], path_prefix: str) -> str:
    if not figures:
        return "No reusable figure or generated chart was available for this entry."

    blocks = []
    for idx, figure in enumerate(figures, start=1):
        path = f"{path_prefix.rstrip('/')}/{figure['path']}"
        title = figure.get("category") or f"Figure {idx}"
        blocks.append(f"### Figure {idx}: {title}")
        blocks.append(figure.get("caption", "").strip() or "Figure without caption.")
        if Path(path).suffix.lower() in {".png", ".jpg", ".jpeg", ".svg"}:
            blocks.append(f"![Figure {idx}]({path})")
        else:
            blocks.append(f"[Figure {idx}]({path})")
    return "\n\n".join(blocks)


def _table_block(tables: list[dict[str, Any]]) -> str:
    if not tables:
        return "No compact result table was available for this entry."

    blocks = []
    for idx, table in enumerate(tables, start=1):
        blocks.append(f"### Table {idx}: {table.get('title', f'Table {idx}')}")
        if table.get("caption"):
            blocks.append(table["caption"])
        blocks.append(_markdown_table(table.get("columns", []), table.get("rows", [])))
    return "\n\n".join(blocks)


def _methodology_block(methodology_manifest: dict[str, Any]) -> str:
    sections = methodology_manifest.get("sections", [])
    if not sections:
        return "No supporting methodology evidence was auto-extracted."

    blocks = []
    for section in sections:
        bullets = section.get("summary_bullets", [])
        evidence = section.get("evidence", [])
        if not bullets and not evidence:
            continue
        blocks.append(f"### {section.get('title')}")
        for bullet in bullets[:4]:
            blocks.append(f"- {bullet}")
        for item in evidence[:2]:
            snippets = item.get("snippets", [])
            line = f"- Evidence: `{item.get('path')}`"
            if snippets:
                line += f" | snippets: {' ; '.join(snippets[:2])}"
            blocks.append(line)
    return "\n".join(blocks) if blocks else "No supporting methodology evidence was auto-extracted."


def _fallback_sections(
    scan_manifest: dict[str, Any],
    comparison: dict[str, Any],
    github_context: dict[str, Any],
    methodology_manifest: dict[str, Any],
    chart_manifest: dict[str, Any],
    manual_edits: dict[str, Any],
    figure_prefix: str,
) -> dict[str, str]:
    repo = github_context.get("repo") or {}
    pr = github_context.get("pull_request") or {}
    warnings = [
        *scan_manifest.get("warnings", []),
        *github_context.get("warnings", []),
        *methodology_manifest.get("warnings", []),
    ]

    result_lines = []
    for run in scan_manifest.get("run_candidates", [])[:6]:
        display_metrics = comparison.get("display_metrics", [])[:4]
        reported = []
        for metric in display_metrics:
            value = run.get("metrics", {}).get(metric)
            if value is not None:
                reported.append(f"`{metric}` = {float(value):.4f}")
        if reported:
            result_lines.append(f"- `{run.get('run_id')}` reports " + ", ".join(reported) + ".")
    if not result_lines:
        result_lines.append("- No current run exposed a stable result metric that was strong enough to headline in the summary.")

    prior_best = comparison.get("prior_best")
    current_best = comparison.get("current_best")
    ranking_metric = comparison.get("ranking_metric") or ""
    ranking_source = comparison.get("ranking_source") or "none"
    ranking_note = (
        f"The notebook uses `{ranking_metric}` as the {'user-provided' if ranking_source == 'user' else 'inferred'} ranking metric."
        if ranking_metric
        else "No single ranking metric was enforced; the notebook instead centralizes the most informative reported metrics."
    )

    if prior_best and current_best and current_best.get("ranking_metric_value") is not None and ranking_metric:
        delta = float(current_best["ranking_metric_value"]) - float(prior_best["ranking_metric_value"])
        comparison_text = (
            f"{ranking_note} The strongest current run is `{current_best.get('run_id')}` with "
            f"`{ranking_metric}` = {float(current_best['ranking_metric_value']):.4f}. "
            f"The historical prior best is `{prior_best.get('run_id')}` at "
            f"{float(prior_best['ranking_metric_value']):.4f}, giving a delta of {delta:+.4f}."
        )
    else:
        comparison_text = (
            f"{ranking_note} Comparison against the prior best is unavailable because either this is the baseline entry "
            "or the current experiments did not expose a comparable ranking metric."
        )

    revised_notes = []

    def _strip_heading_block(text: str) -> str:
        lines = text.strip().splitlines()
        while lines and lines[0].lstrip().startswith("#"):
            lines.pop(0)
        return "\n".join(lines).strip()

    for item in manual_edits.get("edited_sections", []):
        revised_body = _strip_heading_block(item.get("polished_text", ""))
        revised_notes.append(f"### Revised {item.get('title')}\n{revised_body}".strip())
    for idx, item in enumerate(manual_edits.get("orphan_notes", []), start=1):
        revised_notes.append(f"### Revised freeform note {idx}\n{item.get('polished_text', '').strip()}")
    user_notes_text = "\n\n".join(revised_notes) if revised_notes else "No user-authored notebook edits were detected for revision in this run."

    risk_lines = [f"- {warning}" for warning in warnings]
    risk_lines.extend(f"- {note}" for note in comparison.get("notes", []))
    if not risk_lines:
        risk_lines.append("- No immediate anomaly was flagged beyond the normal uncertainty of iterative experiments.")

    next_questions = [
        "- Which upstream data or preprocessing step is most likely to explain the strongest result change?",
        "- Do the current gains survive a repeat run or alternative split/seed?",
        "- Which missing artifact would most improve interpretability: a richer metric file, a clearer figure, or stronger supporting code context?",
    ]

    context_lines = [
        f"Workspace root: `{scan_manifest.get('workspace_root')}`.",
        f"Study title: {scan_manifest.get('study_title')}.",
        f"Changed artifact count: {len(scan_manifest.get('changed_artifacts', []))}.",
    ]
    if scan_manifest.get("current_commit"):
        context_lines.append(f"Current commit: `{scan_manifest.get('current_commit')[:12]}`.")
    if scan_manifest.get("previous_commit"):
        context_lines.append(f"Previous checkpoint commit: `{scan_manifest.get('previous_commit')[:12]}`.")
    if repo:
        context_lines.append(f"GitHub repo: [{repo.get('owner')}/{repo.get('repo')}]({repo.get('html_url')}).")
    if pr:
        context_lines.append(f"Related PR: [{pr.get('title')}]({pr.get('html_url')}).")

    return {
        "Context": " ".join(context_lines),
        "Methodology Delta": _methodology_block(methodology_manifest),
        "New Results": (
            "Highlighted result metrics: "
            + (", ".join(f"`{metric}`" for metric in comparison.get("display_metrics", [])[:5]) or "none")
            + ".\n\n"
            + "\n".join(result_lines)
            + "\n\n### Auto-selected result table\n"
            + _comparison_table(comparison)
        ),
        "Comparison vs Prior Best": comparison_text + "\n\n" + _comparison_table(comparison),
        "Figures and Tables": (
            "### Auto-selected tables\n"
            + _table_block(chart_manifest.get("tables", []))
            + "\n\n### Auto-selected figures\n"
            + _figure_block(chart_manifest.get("figures", []), figure_prefix)
        ),
        "User Notes Revised": user_notes_text,
        "Risks/Anomalies": "\n".join(risk_lines),
        "Next Questions": "\n".join(next_questions),
    }


def _entry_markdown(entry_id: str, study_title: str, analysis_sections: dict[str, str]) -> str:
    lines = [
        f"<!-- ern:entry start id={entry_id} -->",
        f"# {study_title} Notebook Entry",
        "",
        f"_Entry ID: `{entry_id}`_",
        "",
    ]

    for title in REQUIRED_SECTION_TITLES:
        section_id = f"{entry_id}-{title.lower().replace('/', '-').replace(' ', '-')}"
        lines.append(f'<!-- ern:section entry={entry_id} id={section_id} title="{title}" -->')
        lines.append(f"## {title}")
        lines.append(analysis_sections.get(title, "").strip())
        lines.append("")

    lines.append(f"<!-- ern:entry end id={entry_id} -->")
    lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _append_auto_block(base: str, heading: str, block: str) -> str:
    stripped = base.strip()
    if not block or "No " in block[:8]:
        return stripped
    marker = f"### {heading}"
    if marker in stripped:
        return stripped
    if stripped:
        stripped += "\n\n"
    stripped += f"### {heading}\n{block}"
    return stripped


def _has_table(text: str) -> bool:
    return "| ---" in text or bool(re.search(r"^\|.+\|$", text, flags=re.MULTILINE))


def _has_figure(text: str) -> bool:
    return "![" in text or bool(re.search(r"\[Figure [0-9]+\]", text))


def _augment_sections(
    sections: dict[str, str],
    comparison: dict[str, Any],
    methodology_manifest: dict[str, Any],
    chart_manifest: dict[str, Any],
    figure_prefix: str,
) -> dict[str, str]:
    augmented = dict(sections)
    augmented["Methodology Delta"] = _append_auto_block(
        augmented.get("Methodology Delta", ""),
        "Auto-extracted methodology evidence",
        _methodology_block(methodology_manifest),
    )

    if not _has_table(augmented.get("New Results", "")):
        augmented["New Results"] = _append_auto_block(
            augmented.get("New Results", ""),
            "Auto-selected result table",
            _comparison_table(comparison),
        )

    tables_block = _table_block(chart_manifest.get("tables", []))
    figures_block = _figure_block(chart_manifest.get("figures", []), figure_prefix)
    augmented["Figures and Tables"] = _append_auto_block(
        augmented.get("Figures and Tables", ""),
        "Auto-selected tables",
        tables_block,
    )
    if not _has_figure(augmented.get("Figures and Tables", "")):
        augmented["Figures and Tables"] = _append_auto_block(
            augmented.get("Figures and Tables", ""),
            "Auto-selected figures",
            figures_block,
        )
    return augmented


def render_report(
    entry_id: str,
    workspace_root: Path,
    notebook_path: Path,
    entry_md_path: Path,
    latest_md_path: Path,
    analysis_md_path: Path,
    scan_manifest: dict[str, Any],
    comparison: dict[str, Any],
    github_context: dict[str, Any],
    methodology_manifest: dict[str, Any],
    chart_manifest: dict[str, Any],
    manual_edits: dict[str, Any],
) -> dict[str, Any]:
    workspace_root = workspace_root.resolve()
    notebook_text = notebook_path.read_text(encoding="utf-8") if notebook_path.exists() else ""

    for item in manual_edits.get("edited_sections", []):
        notebook_text = replace_section_content(notebook_text, item["section_id"], item.get("polished_text", ""))
    notebook_text = remove_entry_blocks(notebook_text, entry_id)

    authored_sections = parse_h2_sections(analysis_md_path.read_text(encoding="utf-8")) if analysis_md_path.exists() else {}
    entry_sections = _fallback_sections(
        scan_manifest,
        comparison,
        github_context,
        methodology_manifest,
        chart_manifest,
        manual_edits,
        figure_prefix="figures",
    )
    notebook_sections = _fallback_sections(
        scan_manifest,
        comparison,
        github_context,
        methodology_manifest,
        chart_manifest,
        manual_edits,
        figure_prefix=f"entries/{entry_id}/figures",
    )
    for title, content in authored_sections.items():
        stripped = content.strip()
        if title in entry_sections and stripped and not stripped.startswith("Replace this section with polished notebook prose"):
            entry_sections[title] = stripped
            notebook_sections[title] = stripped

    entry_sections = _augment_sections(entry_sections, comparison, methodology_manifest, chart_manifest, figure_prefix="figures")
    notebook_sections = _augment_sections(
        notebook_sections,
        comparison,
        methodology_manifest,
        chart_manifest,
        figure_prefix=f"entries/{entry_id}/figures",
    )

    entry_text = _entry_markdown(entry_id, scan_manifest.get("study_title", workspace_root.name), entry_sections)
    notebook_entry_text = _entry_markdown(entry_id, scan_manifest.get("study_title", workspace_root.name), notebook_sections)
    updated_notebook = notebook_text.rstrip()
    if updated_notebook:
        updated_notebook += "\n\n"
    updated_notebook += notebook_entry_text
    updated_notebook = updated_notebook.rstrip() + "\n"
    latest_text = updated_notebook.replace("](entries/", "](../entries/")

    entry_md_path.parent.mkdir(parents=True, exist_ok=True)
    latest_md_path.parent.mkdir(parents=True, exist_ok=True)
    notebook_path.parent.mkdir(parents=True, exist_ok=True)
    entry_md_path.write_text(entry_text, encoding="utf-8")
    notebook_path.write_text(updated_notebook, encoding="utf-8")
    latest_md_path.write_text(latest_text, encoding="utf-8")

    return {
        "entry_md": str(entry_md_path),
        "notebook_md": str(notebook_path),
        "latest_md": str(latest_md_path),
        "section_hashes": section_hash_index(updated_notebook),
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Render one notebook entry and update notebook.md")
    parser.add_argument("--entry-id", required=True)
    parser.add_argument("--workspace-root", required=True)
    parser.add_argument("--notebook", required=True)
    parser.add_argument("--entry-md", required=True)
    parser.add_argument("--latest-md", required=True)
    parser.add_argument("--analysis-md", required=True)
    parser.add_argument("--scan-manifest", required=True)
    parser.add_argument("--comparison", required=True)
    parser.add_argument("--github-context", required=True)
    parser.add_argument("--methodology-manifest", required=True)
    parser.add_argument("--chart-manifest", required=True)
    parser.add_argument("--manual-edits", required=True)
    parser.add_argument("--output", required=True)
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    payload = render_report(
        entry_id=args.entry_id,
        workspace_root=Path(args.workspace_root),
        notebook_path=Path(args.notebook),
        entry_md_path=Path(args.entry_md),
        latest_md_path=Path(args.latest_md),
        analysis_md_path=Path(args.analysis_md),
        scan_manifest=read_json(Path(args.scan_manifest)),
        comparison=read_json(Path(args.comparison)),
        github_context=read_json(Path(args.github_context)),
        methodology_manifest=read_json(Path(args.methodology_manifest)),
        chart_manifest=read_json(Path(args.chart_manifest)),
        manual_edits=read_json(Path(args.manual_edits)),
    )
    write_json(Path(args.output), payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
