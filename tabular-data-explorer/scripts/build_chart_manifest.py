#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path

from common import read_json, write_json


def _distribution_reason(column: str, role: str) -> tuple[str, str, str]:
    if role == "numeric":
        return (
            f"Inspect the shape, spread, and outliers in '{column}'.",
            "Look for skew, multi-modality, and whether the box plot shows extreme values relative to the central mass.",
            "Heavy tails or clipping can make averages misleading; use this with quantiles, not in isolation.",
        )
    if role in {"categorical", "boolean"}:
        return (
            f"Inspect how '{column}' is distributed across categories.",
            "Focus on dominant levels, imbalance, and whether the long tail has been collapsed into 'Other'.",
            "High-cardinality categories are intentionally compressed, so rare-but-important labels may be hidden.",
        )
    if role == "datetime":
        return (
            f"Inspect the temporal coverage of '{column}'.",
            "Check whether events are evenly spread or concentrated in narrow windows.",
            "Datetime histograms depend on binning; apparent spikes may reflect irregular logging or backfills.",
        )
    return (
        f"Inspect the content pattern of '{column}'.",
        "Use this as a quick shape check rather than a full semantic interpretation.",
        "ID and text-like columns are usually diagnostic, not explanatory.",
    )


def build_chart_manifest(
    overview: dict,
    column_profiles: dict,
    missingness: dict,
    associations: dict,
    target_analysis: dict,
) -> dict:
    sections = []

    overview_charts = [
        {
            "id": "role-balance",
            "kind": "role-bar",
            "layout": "sidecar",
            "title": "Variable role balance",
            "subtitle": "How the dataset breaks down across numeric, categorical, boolean, datetime, text, and ID-like columns.",
            "why_selected": "This gives fast context on what kinds of analysis are appropriate for the rest of the report.",
            "how_to_read": "Large numeric or categorical shares suggest what analyses will dominate later sections.",
            "watch_out_for": "Role inference is heuristic, especially for messy object columns.",
        }
    ]
    sections.append(
        {
            "id": "overview",
            "title": "Overview",
            "description": "Start with the structural shape of the dataset before diving into quality or relationships.",
            "charts": overview_charts,
        }
    )

    quality_charts = []
    if any(item["missing_rate"] > 0 for item in missingness.get("column_missing", [])):
        quality_charts.append(
            {
                "id": "missingness-bar",
                "kind": "missingness-bar",
                "title": "Columns with the most missingness",
                "subtitle": "Sorted view of the worst missing-rate columns.",
                "why_selected": "Missingness is often the fastest way to spot data collection gaps or unreliable features.",
                "how_to_read": "Compare both the rate and the ordering; a few bad columns matter differently from broad low-grade sparsity.",
                "watch_out_for": "Low missingness can still be harmful if it is concentrated in target-critical rows.",
            }
        )
    if missingness.get("co_missing_pairs"):
        quality_charts.append(
            {
                "id": "missingness-pairs",
                "kind": "missingness-pairs",
                "title": "Co-missing column pairs",
                "subtitle": "Pairs of columns that tend to go missing together.",
                "why_selected": "Co-missing patterns often reveal shared upstream failures or optional data capture paths.",
                "how_to_read": "Higher joint missingness and higher Jaccard values indicate tighter alignment in absence patterns.",
                "watch_out_for": "A pair can look strong simply because both columns are rare overall.",
                "term_note": "Jaccard overlap means the share of missing rows the two columns have in common among rows where either one is missing.",
            }
        )
    if quality_charts:
        sections.append(
            {
                "id": "quality",
                "title": "Data Quality",
                "description": "Focus on sparsity and structural quality risks before trusting downstream relationships.",
                "charts": quality_charts,
            }
        )

    relationship_charts = []
    top_numeric_pairs = associations.get("numeric_numeric", {}).get("top_pairs", [])
    if len(associations.get("numeric_numeric", {}).get("pearson", {}).get("columns", [])) >= 2:
        relationship_charts.append(
            {
                "id": "numeric-correlation",
                "kind": "numeric-correlation-bar",
                "title": "Strongest numeric correlations",
                "subtitle": "Top Pearson correlation pairs among numeric columns after auto-excluding index-like fields.",
                "why_selected": "This surfaces linear relationships, redundancy, and potential leakage candidates.",
                "how_to_read": "Bars near 1 or -1 indicate stronger positive or negative linear co-movement.",
                "watch_out_for": "Correlation is linear and pairwise; it misses nonlinear effects and can be distorted by outliers.",
                "term_note": "Pearson correlation ranges from -1 to 1 and summarizes straight-line association between two numeric variables.",
            }
        )
    dense_pairs = [row for row in top_numeric_pairs if row["abs_correlation"] >= 0.75]
    if len(dense_pairs) >= 6:
        relationship_charts.append(
            {
                "id": "numeric-correlation-heatmap",
                "kind": "numeric-correlation-heatmap",
                "title": "High-correlation feature map",
                "subtitle": "2D correlation view for the numeric features that repeatedly appear in the strongest linear pairs.",
                "why_selected": "When strong linear relationships are dense rather than isolated, a 2D map makes multicollinearity structure easier to inspect.",
                "how_to_read": "Look for dark blocks or clusters: they indicate groups of features that move together and may be partially redundant.",
                "watch_out_for": "This is still pairwise linear correlation, so it does not prove causality or replace domain review.",
                "term_note": "This heatmap is intended for multicollinearity screening, which is especially useful before explainable regression or survival modeling.",
            }
        )
    top_categorical = associations.get("categorical_categorical", {}).get("top_pairs", [])
    if top_categorical:
        relationship_charts.append(
            {
                "id": "categorical-association",
                "kind": "categorical-association-bar",
                "title": "Strongest categorical associations",
                "subtitle": "Top Cramer's V scores among low-cardinality categorical variables.",
                "why_selected": "This shows where category structure overlaps strongly enough to warrant deeper inspection.",
                "how_to_read": "Higher bars mean tighter category association, not necessarily useful predictive value.",
                "watch_out_for": "Cramer's V can look strong in small or imbalanced groups; inspect counts before over-interpreting.",
                "term_note": "Cramer's V is a 0 to 1 score for how strongly two categorical variables move together.",
            }
        )
    if relationship_charts:
        sections.append(
            {
                "id": "relationships",
                "title": "Relationships",
                "description": "Surface the strongest variable-to-variable structure before narrowing to one target.",
                "charts": relationship_charts,
            }
        )

    if target_analysis:
        target_charts = []
        for target, payload in target_analysis.items():
            top_features = payload.get("top_features", [])
            if top_features and top_features[0]["score"] >= 0.02:
                target_charts.append(
                    {
                        "id": f"target-strength-{target}",
                        "kind": "feature-strength-bar",
                        "target": target,
                        "title": f"Top associations for target '{target}'",
                        "subtitle": "A ranked view of the strongest target-feature relationships in this run.",
                        "why_selected": "This makes target-aware exploration concrete instead of leaving it as generic EDA.",
                        "how_to_read": "Higher scores mean a stronger association under the method shown for each feature.",
                        "watch_out_for": "Scores are descriptive, not causal, and methods differ between numeric and categorical features.",
                        "term_note": "Eta-squared is a 0 to 1 effect-size score showing how much target separation is explained by a feature.",
                    }
                )
        if target_charts:
            sections.append(
                {
                    "id": "targets",
                    "title": "Target Exploration",
                    "description": "Highlight how the declared targets relate to the rest of the dataset.",
                    "charts": target_charts,
                }
            )

    distribution_charts = []
    for column in overview.get("priority_columns", [])[:6]:
        profile = column_profiles.get(column)
        if not profile:
            continue
        why_selected, how_to_read, watch_out_for = _distribution_reason(column, profile["role"])
        distribution_charts.append(
            {
                "id": f"distribution-{column}",
                "kind": "distribution",
                "column": column,
                "title": f"Distribution of '{column}'",
                "subtitle": f"Detailed view for the {profile['role']} column '{column}'.",
                "why_selected": why_selected,
                "how_to_read": how_to_read,
                "watch_out_for": watch_out_for,
            }
        )
    if distribution_charts:
        sections.append(
            {
                "id": "distributions",
                "title": "Priority Distributions",
                "description": "Zoom in on the columns most likely to drive interpretation in this dataset.",
                "charts": distribution_charts,
            }
        )

    return {"sections": sections}


def main():
    parser = argparse.ArgumentParser(description="Build chart manifest from profiling artifacts.")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    run_dir = Path(args.run_dir).resolve()
    manifest = build_chart_manifest(
        read_json(run_dir / "profile_overview.json"),
        read_json(run_dir / "column_profiles.json"),
        read_json(run_dir / "missingness.json"),
        read_json(run_dir / "associations.json"),
        read_json(run_dir / "target_analysis.json"),
    )
    output_path = Path(args.output).resolve() if args.output else run_dir / "chart_manifest.json"
    write_json(output_path, manifest)


if __name__ == "__main__":
    main()
