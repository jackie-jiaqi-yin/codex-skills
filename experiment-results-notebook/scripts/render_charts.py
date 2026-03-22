#!/usr/bin/env python3
"""Select reusable figures and derive compact result tables."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt

from common import (
    load_tabular_rows,
    normalize_metric_key,
    now_utc_iso,
    read_json,
    slugify,
    write_json,
)


PLOT_CATEGORY_HINTS = {
    "loss_curves": 100,
    "optimization_history": 95,
    "param_importance": 88,
    "parallel_coordinate": 84,
    "scatter_test": 98,
    "scatter": 82,
    "residuals_test": 94,
    "residuals": 80,
    "error_distribution_test": 92,
    "error_distribution": 78,
    "confusion": 96,
    "roc": 96,
    "pr_curve": 90,
}
TABLE_HINTS = ("topk", "top_k", "summary", "comparison", "leaderboard", "best", "report")


def _run_label(run_id: str) -> str:
    parts = [part for part in str(run_id).split("/") if part]
    if len(parts) >= 3:
        return "/".join(parts[-3:])
    return run_id


def _family_name(rel_path: str) -> str:
    parts = Path(rel_path).parts
    if "experiments" in parts:
        idx = parts.index("experiments")
        if idx + 1 < len(parts):
            return parts[idx + 1]
    return parts[0] if parts else "workspace"


def _plot_category(rel_path: str) -> str:
    stem = Path(rel_path).stem.lower()
    for key in PLOT_CATEGORY_HINTS:
        if key in stem:
            return key
    return stem


def _plot_score(rel_path: str) -> int:
    lowered = rel_path.lower()
    category = _plot_category(rel_path)
    score = PLOT_CATEGORY_HINTS.get(category, 40)
    if "/trial_" in lowered or "/best" in lowered:
        score += 8
    if "test" in lowered:
        score += 6
    return score


def _destination_name(rel_path: str) -> str:
    family = slugify(_family_name(rel_path))
    stem = slugify(Path(rel_path).stem)
    suffix = Path(rel_path).suffix.lower()
    return f"{family}-{stem}{suffix}"


def _copy_selected_figures(
    scan_manifest: dict[str, Any],
    workspace_root: Path,
    output_dir: Path,
    limit: int = 6,
) -> list[dict[str, Any]]:
    candidates = [
        artifact
        for artifact in scan_manifest.get("changed_artifacts", [])
        if artifact.get("kind") == "plot" and artifact.get("path")
    ]
    ranked = sorted(
        candidates,
        key=lambda item: (-_plot_score(item["path"]), item["path"]),
    )

    figures: list[dict[str, Any]] = []
    per_family: dict[str, int] = {}
    seen_categories: set[tuple[str, str]] = set()

    for artifact in ranked:
        rel_path = artifact["path"]
        source = workspace_root / rel_path
        if not source.exists():
            continue
        family = _family_name(rel_path)
        category = _plot_category(rel_path)
        if per_family.get(family, 0) >= 3:
            continue
        if (family, category) in seen_categories and len(figures) >= 3:
            continue

        destination = output_dir / _destination_name(rel_path)
        shutil.copy2(source, destination)
        figures.append(
            {
                "kind": "reused",
                "path": destination.name,
                "caption": f"Selected reusable `{category}` figure from `{rel_path}`.",
                "source": rel_path,
                "family": family,
                "category": category,
            }
        )
        per_family[family] = per_family.get(family, 0) + 1
        seen_categories.add((family, category))
        if len(figures) >= limit:
            break

    return figures


def _generate_metric_chart(
    comparison: dict[str, Any],
    output_dir: Path,
) -> list[dict[str, Any]]:
    rows = [row for row in comparison.get("comparison_rows", []) if row.get("ranking_metric_value") is not None]
    if not rows:
        return []

    ranking_metric = comparison.get("ranking_metric") or "metric"
    rows = sorted(rows, key=lambda item: float(item["ranking_metric_value"]), reverse=comparison.get("ranking_direction") != "min")[:8]
    labels = [_run_label(row["run_id"]) for row in rows]
    values = [float(row["ranking_metric_value"]) for row in rows]

    plt.figure(figsize=(max(6.5, len(labels) * 1.2), 4.4))
    plt.bar(labels, values, color="#2563eb")
    plt.ylabel(ranking_metric)
    plt.xticks(rotation=20, ha="right")
    plt.tight_layout()

    generated_path = output_dir / "ranking-metric-comparison.png"
    plt.savefig(generated_path, dpi=220)
    plt.close()
    return [
        {
            "kind": "generated",
            "path": generated_path.name,
            "caption": f"Auto-generated comparison of `{ranking_metric}` across the strongest current runs.",
            "source": "generated",
            "family": "generated",
            "category": "ranking_metric_comparison",
        }
    ]


def _match_columns(rows: list[dict[str, Any]], comparison: dict[str, Any]) -> list[str]:
    if not rows:
        return []

    keys = list(rows[0].keys())
    normalized = {key: normalize_metric_key(key) for key in keys}

    chosen: list[str] = []
    for candidate in ("rank", "trial", "run", "run_id", "model", "name"):
        for key in keys:
            if normalized[key] == normalize_metric_key(candidate) and key not in chosen:
                chosen.append(key)

    metric_targets = [comparison.get("ranking_metric", ""), *comparison.get("display_metrics", [])]
    for target in metric_targets:
        norm_target = normalize_metric_key(target)
        if not norm_target:
            continue
        for key in keys:
            norm_key = normalized[key]
            if norm_key == norm_target or norm_key.endswith(norm_target) or norm_target.endswith(norm_key):
                if key not in chosen:
                    chosen.append(key)

    for key in keys:
        lowered = key.lower()
        if key not in chosen and any(token in lowered for token in ("test", "val", "metric", "score")):
            chosen.append(key)

    if not chosen:
        chosen = keys[:6]
    return chosen[:6]


def _best_runs_table(comparison: dict[str, Any]) -> dict[str, Any] | None:
    rows = [row for row in comparison.get("comparison_rows", []) if row.get("display_metrics")]
    if not rows:
        return None

    ranking_direction = comparison.get("ranking_direction", "max")
    rows = sorted(
        rows,
        key=lambda item: float(item["ranking_metric_value"]) if item.get("ranking_metric_value") is not None else float("-inf"),
        reverse=ranking_direction != "min",
    )[:6]
    display_metrics = comparison.get("display_metrics", [])[:4]
    columns = ["Run", *display_metrics]
    table_rows: list[dict[str, Any]] = []
    for row in rows:
        rendered = {"Run": _run_label(row["run_id"])}
        for metric in display_metrics:
            rendered[metric] = row.get("display_metrics", {}).get(metric)
        table_rows.append(rendered)
    return {
        "kind": "derived",
        "title": "Best-run summary",
        "caption": "Auto-derived summary of the strongest current runs using the selected display metrics.",
        "columns": columns,
        "rows": table_rows,
        "source": "comparison.json",
    }


def _summary_tables(
    scan_manifest: dict[str, Any],
    comparison: dict[str, Any],
    workspace_root: Path,
    limit: int = 2,
) -> list[dict[str, Any]]:
    tables: list[dict[str, Any]] = []

    best_table = _best_runs_table(comparison)
    if best_table:
        tables.append(best_table)

    ranked_candidates: list[tuple[int, str, list[dict[str, Any]]]] = []
    for artifact in scan_manifest.get("changed_artifacts", []):
        if artifact.get("kind") != "structured":
            continue
        rel_path = artifact.get("path", "")
        if not rel_path:
            continue
        lowered = rel_path.lower()
        if "training_log" in lowered:
            continue
        score = sum(1 for hint in TABLE_HINTS if hint in lowered)
        if score <= 0:
            continue
        rows = load_tabular_rows(workspace_root / rel_path, row_limit=8)
        if not rows or len(rows[0]) < 2:
            continue
        ranked_candidates.append((score, rel_path, rows))

    ranked_candidates.sort(key=lambda item: (-item[0], item[1]))
    for _, rel_path, rows in ranked_candidates[:limit]:
        columns = _match_columns(rows, comparison)
        if len(columns) < 2:
            continue
        rendered_rows = [{column: row.get(column) for column in columns} for row in rows[:5]]
        tables.append(
            {
                "kind": "reused",
                "title": Path(rel_path).stem.replace("_", " ").title(),
                "caption": f"Selected summary table from `{rel_path}`.",
                "columns": columns,
                "rows": rendered_rows,
                "source": rel_path,
            }
        )
    return tables


def render_charts(
    scan_manifest: dict[str, Any],
    comparison: dict[str, Any],
    workspace_root: Path,
    output_dir: Path,
) -> dict[str, Any]:
    workspace_root = workspace_root.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    figures = _copy_selected_figures(scan_manifest, workspace_root, output_dir)
    if not figures:
        figures = _generate_metric_chart(comparison, output_dir)
    elif comparison.get("comparison_rows"):
        figures.extend(_generate_metric_chart(comparison, output_dir))

    tables = _summary_tables(scan_manifest, comparison, workspace_root)

    return {
        "generated_at": now_utc_iso(),
        "figures": figures,
        "figure_count": len(figures),
        "tables": tables,
        "table_count": len(tables),
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Select reusable figures and derive compact result tables")
    parser.add_argument("--scan-manifest", required=True)
    parser.add_argument("--comparison", required=True)
    parser.add_argument("--workspace-root", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--output", required=True)
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    payload = render_charts(
        scan_manifest=read_json(Path(args.scan_manifest)),
        comparison=read_json(Path(args.comparison)),
        workspace_root=Path(args.workspace_root),
        output_dir=Path(args.output_dir),
    )
    write_json(Path(args.output), payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
