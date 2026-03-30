#!/usr/bin/env python3

from __future__ import annotations

import math
from collections import Counter

import numpy as np
import pandas as pd

from common import as_display


ID_HINTS = ("id", "_id", "uuid", "guid", "key")
INDEX_NAME_HINTS = {"seqn", "index", "row_index", "rowid", "row_id", "record_id", "recordid"}
BOOLEAN_TOKENS = {"0", "1", "true", "false", "yes", "no", "y", "n", "t", "f"}


def _is_id_like(name: str, unique_ratio: float) -> bool:
    lowered = name.lower()
    return unique_ratio >= 0.95 and (
        any(token in lowered for token in ID_HINTS)
        or lowered in INDEX_NAME_HINTS
        or lowered.startswith("unnamed:")
    )


def _looks_like_index_sequence(series: pd.Series) -> bool:
    non_null = series.dropna()
    if non_null.empty:
        return False
    unique_ratio = non_null.nunique() / max(len(non_null), 1)
    if unique_ratio < 0.98:
        return False
    numeric = pd.to_numeric(non_null, errors="coerce")
    if numeric.isna().any():
        return False
    if not (((numeric - numeric.round()).abs() < 1e-9).all()):
        return False
    if not (numeric.is_monotonic_increasing or numeric.is_monotonic_decreasing):
        return False
    diffs = numeric.diff().dropna().round(8)
    if diffs.empty:
        return False
    return diffs.nunique() <= 2


def detect_auto_excluded_columns(
    df: pd.DataFrame,
    protected_columns: list[str] | None = None,
) -> dict[str, str]:
    protected = set(protected_columns or [])
    excluded = {}
    for column in df.columns:
        if column in protected:
            continue
        lowered = str(column).strip().lower()
        series = df[column]
        non_null = series.dropna()
        unique_ratio = non_null.nunique() / max(len(non_null), 1)
        if lowered.startswith("unnamed:"):
            excluded[column] = "auto_excluded_index_like"
            continue
        if lowered in INDEX_NAME_HINTS and unique_ratio >= 0.95:
            excluded[column] = "auto_excluded_identifier"
            continue
        if pd.api.types.is_numeric_dtype(series) and _looks_like_index_sequence(series):
            excluded[column] = "auto_excluded_index_like"
    return excluded


def infer_column_role(series: pd.Series) -> str:
    non_null = series.dropna()
    unique_count = int(non_null.nunique())
    unique_ratio = unique_count / max(len(non_null), 1)

    if pd.api.types.is_bool_dtype(series):
        return "boolean"
    if pd.api.types.is_datetime64_any_dtype(series):
        return "datetime"
    if pd.api.types.is_numeric_dtype(series):
        if unique_count <= 2:
            values = {str(value) for value in non_null.unique()}
            if values.issubset({"0", "1", "0.0", "1.0"}):
                return "boolean"
        if _is_id_like(series.name or "", unique_ratio) or _looks_like_index_sequence(series):
            return "id"
        return "numeric"

    sample_tokens = {str(value).strip().lower() for value in non_null.head(25)}
    if sample_tokens and sample_tokens.issubset(BOOLEAN_TOKENS):
        return "boolean"

    average_length = float(non_null.astype(str).str.len().mean()) if not non_null.empty else 0.0
    if _is_id_like(series.name or "", unique_ratio):
        return "id"
    if average_length > 40 and unique_ratio >= 0.4:
        return "text"
    return "categorical"


def infer_column_roles(df: pd.DataFrame) -> dict[str, str]:
    return {column: infer_column_role(df[column]) for column in df.columns}


def _top_values(series: pd.Series, top_n: int = 8) -> list[dict]:
    non_null = series.dropna()
    if non_null.empty:
        return []
    counts = non_null.astype(str).value_counts(dropna=True).head(top_n)
    total = int(len(non_null))
    return [
        {
            "value": as_display(index, limit=50),
            "count": int(count),
            "rate": float(count / total),
        }
        for index, count in counts.items()
    ]


def _quantile(series: pd.Series, q: float):
    if series.empty:
        return None
    return float(series.quantile(q))


def _numeric_profile(series: pd.Series) -> dict:
    clean = pd.to_numeric(series, errors="coerce").dropna()
    if clean.empty:
        return {}
    return {
        "mean": float(clean.mean()),
        "std": float(clean.std(ddof=1)) if len(clean) > 1 else 0.0,
        "min": float(clean.min()),
        "q1": _quantile(clean, 0.25),
        "median": _quantile(clean, 0.5),
        "q3": _quantile(clean, 0.75),
        "max": float(clean.max()),
        "skew": float(clean.skew()) if len(clean) > 2 else 0.0,
    }


def _datetime_profile(series: pd.Series) -> dict:
    clean = pd.to_datetime(series, errors="coerce").dropna()
    if clean.empty:
        return {}
    return {
        "min": clean.min().isoformat(),
        "max": clean.max().isoformat(),
        "range_days": float((clean.max() - clean.min()).total_seconds() / 86400.0),
    }


def build_column_profiles(df: pd.DataFrame, roles: dict[str, str]) -> dict[str, dict]:
    profiles = {}
    row_count = max(len(df), 1)
    for column in df.columns:
        series = df[column]
        non_null = series.dropna()
        unique_count = int(non_null.nunique())
        role = roles[column]
        profile = {
            "name": column,
            "role": role,
            "pandas_dtype": str(series.dtype),
            "non_null_count": int(non_null.shape[0]),
            "missing_count": int(series.isna().sum()),
            "missing_rate": float(series.isna().mean()),
            "unique_count": unique_count,
            "unique_rate": float(unique_count / row_count),
            "is_constant": bool(unique_count <= 1),
            "sample_values": [as_display(value) for value in non_null.astype(str).head(5).tolist()],
        }
        if role == "numeric":
            profile["numeric_summary"] = _numeric_profile(series)
        elif role in {"categorical", "boolean", "id", "text"}:
            profile["top_values"] = _top_values(series)
        elif role == "datetime":
            profile["datetime_summary"] = _datetime_profile(series)
        profiles[column] = profile
    return profiles


def build_missingness(df: pd.DataFrame) -> dict:
    column_missing = (
        df.isna()
        .mean()
        .sort_values(ascending=False)
        .rename_axis("column")
        .reset_index(name="missing_rate")
    )
    column_missing["missing_count"] = column_missing["column"].map(lambda col: int(df[col].isna().sum()))

    per_row_missing = df.isna().sum(axis=1)
    summary = {
        "mean_missing_columns": float(per_row_missing.mean()) if len(df) else 0.0,
        "median_missing_columns": float(per_row_missing.median()) if len(df) else 0.0,
        "p90_missing_columns": float(per_row_missing.quantile(0.9)) if len(df) else 0.0,
        "max_missing_columns": int(per_row_missing.max()) if len(df) else 0,
    }

    candidate_columns = [row["column"] for _, row in column_missing.iterrows() if row["missing_count"] > 0][:20]
    pair_summaries = []
    for index, left in enumerate(candidate_columns):
        left_mask = df[left].isna()
        left_rate = float(left_mask.mean())
        if left_rate == 0:
            continue
        for right in candidate_columns[index + 1 :]:
            right_mask = df[right].isna()
            joint = float((left_mask & right_mask).mean())
            if joint == 0:
                continue
            union = float((left_mask | right_mask).mean())
            jaccard = joint / union if union else None
            pair_summaries.append(
                {
                    "left": left,
                    "right": right,
                    "joint_missing_rate": joint,
                    "jaccard_missingness": jaccard,
                }
            )

    pair_summaries.sort(
        key=lambda item: (
            item["joint_missing_rate"] if item["joint_missing_rate"] is not None else -1.0,
            item["jaccard_missingness"] if item["jaccard_missingness"] is not None else -1.0,
        ),
        reverse=True,
    )

    return {
        "column_missing": column_missing.to_dict(orient="records"),
        "row_missing_summary": summary,
        "co_missing_pairs": pair_summaries[:15],
    }


def _corr_matrix(df: pd.DataFrame, method: str) -> dict:
    if df.shape[1] < 2:
        return {"columns": list(df.columns), "matrix": []}
    corr = df.corr(method=method)
    return {
        "columns": list(corr.columns),
        "matrix": corr.fillna(0.0).round(6).values.tolist(),
    }


def _top_numeric_pairs(df: pd.DataFrame, method: str, limit: int = 15) -> list[dict]:
    if df.shape[1] < 2:
        return []
    corr = df.corr(method=method)
    pairs = []
    columns = list(corr.columns)
    for index, left in enumerate(columns):
        for right in columns[index + 1 :]:
            value = corr.loc[left, right]
            if pd.isna(value):
                continue
            pairs.append(
                {
                    "left": left,
                    "right": right,
                    "correlation": float(value),
                    "abs_correlation": abs(float(value)),
                    "method": method,
                }
            )
    pairs.sort(key=lambda item: item["abs_correlation"], reverse=True)
    return pairs[:limit]


def cramers_v(left: pd.Series, right: pd.Series):
    paired = pd.DataFrame({"left": left, "right": right}).dropna()
    if paired.empty:
        return None
    table = pd.crosstab(paired["left"], paired["right"])
    if table.empty or min(table.shape) <= 1:
        return None

    observed = table.to_numpy(dtype=float)
    total = observed.sum()
    if total <= 1:
        return None
    row_totals = observed.sum(axis=1, keepdims=True)
    col_totals = observed.sum(axis=0, keepdims=True)
    expected = row_totals @ col_totals / total
    with np.errstate(divide="ignore", invalid="ignore"):
        chi2 = np.nansum(((observed - expected) ** 2) / expected)
    phi2 = chi2 / total
    rows, cols = observed.shape
    phi2_corr = max(0.0, phi2 - ((cols - 1) * (rows - 1)) / (total - 1))
    rows_corr = rows - ((rows - 1) ** 2) / (total - 1)
    cols_corr = cols - ((cols - 1) ** 2) / (total - 1)
    denominator = min(cols_corr - 1, rows_corr - 1)
    if denominator <= 0:
        return None
    return float(math.sqrt(phi2_corr / denominator))


def eta_squared(categories: pd.Series, numeric: pd.Series):
    paired = pd.DataFrame({"category": categories, "numeric": pd.to_numeric(numeric, errors="coerce")}).dropna()
    if paired.empty:
        return None
    if paired["category"].nunique() < 2:
        return None
    grand_mean = paired["numeric"].mean()
    ss_total = ((paired["numeric"] - grand_mean) ** 2).sum()
    if ss_total == 0:
        return None
    ss_between = 0.0
    for _, group in paired.groupby("category")["numeric"]:
        ss_between += float(len(group) * (group.mean() - grand_mean) ** 2)
    return float(ss_between / ss_total)


def build_associations(df: pd.DataFrame, roles: dict[str, str], max_categorical_levels: int = 25) -> dict:
    numeric_columns = [column for column, role in roles.items() if role == "numeric"]
    categorical_columns = [
        column
        for column, role in roles.items()
        if role in {"categorical", "boolean"} and df[column].dropna().nunique() <= max_categorical_levels
    ]

    numeric_df = df[numeric_columns].apply(pd.to_numeric, errors="coerce") if numeric_columns else pd.DataFrame()
    numeric_numeric = {
        "pearson": _corr_matrix(numeric_df, "pearson"),
        "spearman": _corr_matrix(numeric_df, "spearman"),
        "top_pairs": _top_numeric_pairs(numeric_df, "pearson"),
    }

    categorical_pairs = []
    limited_categoricals = categorical_columns[:12]
    for index, left in enumerate(limited_categoricals):
        for right in limited_categoricals[index + 1 :]:
            score = cramers_v(df[left], df[right])
            if score is None:
                continue
            categorical_pairs.append(
                {
                    "left": left,
                    "right": right,
                    "score": score,
                    "method": "cramers_v",
                }
            )
    categorical_pairs.sort(key=lambda item: item["score"], reverse=True)

    mixed_pairs = []
    for categorical in limited_categoricals:
        for numeric in numeric_columns[:20]:
            score = eta_squared(df[categorical], df[numeric])
            if score is None:
                continue
            mixed_pairs.append(
                {
                    "categorical": categorical,
                    "numeric": numeric,
                    "score": score,
                    "method": "eta_squared",
                }
            )
    mixed_pairs.sort(key=lambda item: item["score"], reverse=True)

    return {
        "numeric_columns": numeric_columns,
        "categorical_columns": limited_categoricals,
        "numeric_numeric": numeric_numeric,
        "categorical_categorical": {
            "top_pairs": categorical_pairs[:15],
        },
        "numeric_categorical": {
            "top_pairs": mixed_pairs[:20],
        },
    }


def build_target_analysis(
    df: pd.DataFrame,
    roles: dict[str, str],
    target_columns: list[str],
    max_categorical_levels: int = 25,
) -> dict:
    results = {}
    for target in target_columns:
        if target not in df.columns:
            continue
        role = roles[target]
        candidate_numeric = [column for column, value in roles.items() if value == "numeric" and column != target]
        candidate_categorical = [
            column
            for column, value in roles.items()
            if value in {"categorical", "boolean"} and column != target and df[column].dropna().nunique() <= max_categorical_levels
        ]

        summary = {
            "target": target,
            "target_role": role,
        }
        rankings = []

        if role == "numeric":
            clean_target = pd.to_numeric(df[target], errors="coerce")
            summary["distribution"] = _numeric_profile(clean_target)
            for column in candidate_numeric:
                paired = pd.DataFrame({"feature": pd.to_numeric(df[column], errors="coerce"), "target": clean_target}).dropna()
                if len(paired) < 3:
                    continue
                corr = paired["feature"].corr(paired["target"])
                if pd.isna(corr):
                    continue
                rankings.append(
                    {
                        "feature": column,
                        "score": abs(float(corr)),
                        "signed_score": float(corr),
                        "method": "pearson_abs",
                    }
                )
            for column in candidate_categorical:
                score = eta_squared(df[column], clean_target)
                if score is None:
                    continue
                rankings.append(
                    {
                        "feature": column,
                        "score": score,
                        "signed_score": None,
                        "method": "eta_squared",
                    }
                )
        elif role in {"categorical", "boolean"}:
            summary["class_balance"] = _top_values(df[target], top_n=10)
            for column in candidate_numeric:
                score = eta_squared(df[target], df[column])
                if score is None:
                    continue
                rankings.append(
                    {
                        "feature": column,
                        "score": score,
                        "signed_score": None,
                        "method": "eta_squared",
                    }
                )
            for column in candidate_categorical:
                score = cramers_v(df[target], df[column])
                if score is None:
                    continue
                rankings.append(
                    {
                        "feature": column,
                        "score": score,
                        "signed_score": None,
                        "method": "cramers_v",
                    }
                )
        else:
            summary["note"] = f"Target role '{role}' is not ranked in v1."

        rankings.sort(key=lambda item: item["score"], reverse=True)
        summary["top_features"] = rankings[:20]
        results[target] = summary

    return results


def choose_priority_columns(
    column_profiles: dict[str, dict],
    associations: dict,
    target_analysis: dict,
    primary_columns: list[str],
    target_columns: list[str],
) -> list[str]:
    ordered = []

    def add(column):
        if column in column_profiles and column not in ordered:
            ordered.append(column)

    for column in primary_columns + target_columns:
        add(column)

    missing_ranked = sorted(
        column_profiles.values(),
        key=lambda item: item["missing_rate"],
        reverse=True,
    )
    for profile in missing_ranked[:3]:
        if 0.05 <= profile["missing_rate"] <= 0.85:
            add(profile["name"])

    numeric_pairs = associations.get("numeric_numeric", {}).get("top_pairs", [])
    for pair in numeric_pairs[:3]:
        add(pair["left"])
        add(pair["right"])

    for target in target_analysis.values():
        for item in target.get("top_features", [])[:4]:
            if item["score"] < 0.02:
                continue
            add(item["feature"])

    skew_candidates = []
    for profile in column_profiles.values():
        if profile["role"] != "numeric":
            continue
        if profile["missing_rate"] > 0.6:
            continue
        skew = profile.get("numeric_summary", {}).get("skew")
        if skew is None:
            continue
        skew_candidates.append((abs(skew), profile["name"]))
    for _, name in sorted(skew_candidates, reverse=True)[:3]:
        add(name)

    return ordered[:8]


def build_profile(
    df: pd.DataFrame,
    primary_columns: list[str] | None = None,
    target_columns: list[str] | None = None,
    ignore_columns: list[str] | None = None,
) -> dict:
    primary_columns = primary_columns or []
    target_columns = target_columns or []
    ignore_columns = ignore_columns or []

    auto_excluded = detect_auto_excluded_columns(df, protected_columns=primary_columns + target_columns + ignore_columns)
    analysis_columns = [column for column in df.columns if column not in ignore_columns and column not in auto_excluded]
    analysis_df = df[analysis_columns].copy()

    roles = infer_column_roles(analysis_df)
    column_profiles = build_column_profiles(analysis_df, roles)
    missingness = build_missingness(analysis_df)
    associations = build_associations(analysis_df, roles)
    target_analysis = build_target_analysis(analysis_df, roles, [column for column in target_columns if column in analysis_df.columns])

    role_counts = dict(Counter(roles.values()))
    total_cells = int(analysis_df.shape[0] * analysis_df.shape[1]) if not analysis_df.empty else 0
    total_missing_cells = int(analysis_df.isna().sum().sum()) if not analysis_df.empty else 0

    overview = {
        "row_count": int(len(df)),
        "original_column_count": int(len(df.columns)),
        "analyzed_column_count": int(len(analysis_df.columns)),
        "duplicate_row_count": int(analysis_df.duplicated().sum()) if not analysis_df.empty else 0,
        "duplicate_row_rate": float(analysis_df.duplicated().mean()) if not analysis_df.empty else 0.0,
        "memory_usage_bytes": int(analysis_df.memory_usage(deep=True).sum()) if not analysis_df.empty else 0,
        "total_missing_cells": total_missing_cells,
        "total_missing_rate": float(total_missing_cells / total_cells) if total_cells else 0.0,
        "role_counts": role_counts,
        "primary_columns": primary_columns,
        "target_columns": target_columns,
        "ignore_columns": ignore_columns,
        "auto_excluded_columns": list(auto_excluded.keys()),
        "auto_excluded_reasons": auto_excluded,
    }
    overview["priority_columns"] = choose_priority_columns(column_profiles, associations, target_analysis, primary_columns, target_columns)

    return {
        "overview": overview,
        "column_profiles": column_profiles,
        "missingness": missingness,
        "associations": associations,
        "target_analysis": target_analysis,
    }


def build_analysis_brief(
    overview: dict,
    missingness: dict,
    associations: dict,
    target_analysis: dict,
) -> str:
    lines = []
    role_counts = overview.get("role_counts", {})
    role_summary = ", ".join(f"{role}: {count}" for role, count in sorted(role_counts.items()))
    lines.append(
        f"- Dataset shape: {overview['row_count']} rows, {overview['analyzed_column_count']} analyzed columns ({role_summary})."
    )
    lines.append(
        f"- Data quality: duplicate row rate {overview['duplicate_row_rate']:.1%}, missing cell rate {overview['total_missing_rate']:.1%}."
    )
    if overview.get("auto_excluded_columns"):
        lines.append(
            "- Auto-excluded likely index or identifier columns: "
            + ", ".join(overview["auto_excluded_columns"][:8])
            + "."
        )

    top_missing = [item for item in missingness.get("column_missing", []) if item["missing_rate"] > 0][:5]
    if top_missing:
        missing_summary = ", ".join(f"{item['column']} ({item['missing_rate']:.1%})" for item in top_missing)
        lines.append(f"- Highest missingness: {missing_summary}.")

    top_corr = associations.get("numeric_numeric", {}).get("top_pairs", [])[:3]
    if top_corr:
        corr_summary = ", ".join(
            f"{item['left']} vs {item['right']} ({item['correlation']:+.2f})" for item in top_corr
        )
        lines.append(f"- Strongest numeric correlations: {corr_summary}.")

    for target, payload in target_analysis.items():
        top_features = payload.get("top_features", [])[:5]
        if not top_features:
            continue
        if top_features[0]["score"] < 0.02:
            lines.append(f"- Target '{target}' did not show strong associations above 0.02 in this run.")
            continue
        feature_summary = ", ".join(f"{item['feature']} ({item['score']:.2f}, {item['method']})" for item in top_features)
        lines.append(f"- Target '{target}' strongest signals: {feature_summary}.")

    priority_columns = overview.get("priority_columns", [])
    if priority_columns:
        lines.append(f"- Priority columns for charts and commentary: {', '.join(priority_columns)}.")

    return "# Deterministic Brief\n\n" + "\n".join(lines) + "\n"
