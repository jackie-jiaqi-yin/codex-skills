#!/usr/bin/env python3
"""Build primary-metric comparisons for current and historical runs."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from common import choose_metric_view, metric_value, now_utc_iso, read_json, write_json


def _sort_runs(runs: list[dict[str, Any]], direction: str) -> list[dict[str, Any]]:
    reverse = direction == "max"
    return sorted(
        [run for run in runs if run.get("primary_metric_value") is not None],
        key=lambda item: float(item["primary_metric_value"]),
        reverse=reverse,
    )


def _load_history(entries_root: Path) -> list[dict[str, Any]]:
    history: list[dict[str, Any]] = []
    if not entries_root.exists():
        return history

    for metrics_path in sorted(entries_root.glob("*/metrics_summary.json")):
        payload = read_json(metrics_path, default={})
        entry_id = payload.get("entry_id") or metrics_path.parent.name
        for run in payload.get("runs", []):
            history.append(
                {
                    "entry_id": entry_id,
                    "run_id": run.get("run_id"),
                    "path": run.get("path"),
                    "primary_metric_value": run.get("primary_metric_value"),
                    "metrics": run.get("metrics", {}),
                    "sources": run.get("sources", []),
                }
            )
    return history


def build_comparison(
    scan_manifest: dict[str, Any],
    entries_root: Path,
    primary_metric: str,
    direction: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    current_runs = []
    for run in scan_manifest.get("run_candidates", []):
        value = run.get("primary_metric_value")
        current_runs.append(
            {
                "run_id": run.get("run_id"),
                "path": run.get("path"),
                "primary_metric_value": value,
                "metrics": run.get("metrics", {}),
                "sources": sorted(run.get("structured_files", []) + run.get("plot_files", []) + run.get("code_files", [])),
            }
        )

    history_runs = _load_history(entries_root)
    metric_view = choose_metric_view(
        runs=[*history_runs, *current_runs],
        preferred_metric=primary_metric,
        preferred_direction=direction,
    )
    ranking_metric = metric_view.get("ranking_metric", "")
    ranking_direction = metric_view.get("ranking_direction", direction)

    for run in current_runs:
        run["ranking_metric"] = ranking_metric
        run["ranking_metric_value"] = metric_value(run.get("metrics", {}), ranking_metric)
        run["display_metrics"] = {
            metric: run.get("metrics", {}).get(metric)
            for metric in metric_view.get("display_metrics", [])
            if run.get("metrics", {}).get(metric) is not None
        }
        run["primary_metric_value"] = run["ranking_metric_value"]

    for run in history_runs:
        run["ranking_metric"] = ranking_metric
        run["ranking_metric_value"] = metric_value(run.get("metrics", {}), ranking_metric)
        run["primary_metric_value"] = run["ranking_metric_value"]

    sorted_history = _sort_runs(history_runs, ranking_direction)
    sorted_current = _sort_runs(current_runs, ranking_direction)
    prior_best = sorted_history[0] if sorted_history else None
    current_best = sorted_current[0] if sorted_current else None

    comparison_rows = []
    for run in current_runs:
        value = run.get("ranking_metric_value")
        delta = None
        if value is not None and prior_best and prior_best.get("ranking_metric_value") is not None:
            delta = float(value) - float(prior_best["ranking_metric_value"])
        comparison_rows.append(
            {
                "run_id": run.get("run_id"),
                "path": run.get("path"),
                "ranking_metric_value": value,
                "delta_vs_prior_best": delta,
                "has_ranking_metric": value is not None,
                "display_metrics": run.get("display_metrics", {}),
            }
        )

    comparison = {
        "generated_at": now_utc_iso(),
        "primary_metric": primary_metric,
        "direction": direction,
        "ranking_metric": ranking_metric,
        "ranking_direction": ranking_direction,
        "ranking_source": metric_view.get("ranking_source", "none"),
        "display_metrics": metric_view.get("display_metrics", []),
        "metric_catalog": metric_view.get("metric_catalog", []),
        "notes": metric_view.get("notes", []),
        "history_run_count": len(history_runs),
        "current_run_count": len(current_runs),
        "prior_best": prior_best,
        "current_best": current_best,
        "comparison_rows": comparison_rows,
        "comparison_available": prior_best is not None and any(row["has_ranking_metric"] for row in comparison_rows),
    }

    metrics_summary = {
        "generated_at": now_utc_iso(),
        "entry_id": "",
        "primary_metric": primary_metric,
        "direction": direction,
        "ranking_metric": ranking_metric,
        "ranking_direction": ranking_direction,
        "ranking_source": metric_view.get("ranking_source", "none"),
        "display_metrics": metric_view.get("display_metrics", []),
        "metric_catalog": metric_view.get("metric_catalog", []),
        "runs": current_runs,
        "best_run": current_best,
        "prior_best": prior_best,
    }
    return comparison, metrics_summary


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build experiment comparisons")
    parser.add_argument("--scan-manifest", required=True)
    parser.add_argument("--entries-root", required=True)
    parser.add_argument("--primary-metric", default="")
    parser.add_argument("--direction", default="", choices=["", "max", "min"])
    parser.add_argument("--comparison-output", required=True)
    parser.add_argument("--metrics-summary-output", required=True)
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    comparison, metrics_summary = build_comparison(
        scan_manifest=read_json(Path(args.scan_manifest)),
        entries_root=Path(args.entries_root),
        primary_metric=args.primary_metric,
        direction=args.direction,
    )
    write_json(Path(args.comparison_output), comparison)
    write_json(Path(args.metrics_summary_output), metrics_summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
