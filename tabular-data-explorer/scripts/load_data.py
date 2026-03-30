#!/usr/bin/env python3

from __future__ import annotations

import warnings
from pathlib import Path

import pandas as pd


SUPPORTED_SUFFIXES = {
    ".csv": "csv",
    ".tsv": "tsv",
    ".txt": "text",
    ".xls": "excel",
    ".xlsx": "excel",
    ".parquet": "parquet",
}


def _coerce_sheet_name(sheet_name):
    if sheet_name is None:
        return None
    if isinstance(sheet_name, int):
        return sheet_name
    if isinstance(sheet_name, str) and sheet_name.isdigit():
        return int(sheet_name)
    return sheet_name


def _coerce_datetime_columns(df: pd.DataFrame) -> pd.DataFrame:
    converted = df.copy()
    for column in converted.columns:
        series = converted[column]
        if not pd.api.types.is_object_dtype(series) and not pd.api.types.is_string_dtype(series):
            continue
        non_null = series.dropna()
        if non_null.empty or len(non_null) < 10:
            continue
        sample = non_null.astype(str).head(100)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=UserWarning)
            parsed_sample = pd.to_datetime(sample, errors="coerce", utc=False)
        success_rate = parsed_sample.notna().mean()
        if success_rate < 0.95:
            continue
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=UserWarning)
            parsed = pd.to_datetime(series, errors="coerce", utc=False)
        if parsed.notna().sum() / max(len(non_null), 1) >= 0.95:
            converted[column] = parsed
    return converted


def load_dataset(input_path: str | Path, sheet_name=None) -> tuple[pd.DataFrame, dict]:
    path = Path(input_path).expanduser().resolve()
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        allowed = ", ".join(sorted(SUPPORTED_SUFFIXES))
        raise ValueError(f"Unsupported file type '{suffix}'. Supported types: {allowed}")

    resolved_sheet_name = _coerce_sheet_name(sheet_name)

    if suffix == ".csv":
        df = pd.read_csv(path)
    elif suffix == ".tsv":
        df = pd.read_csv(path, sep="\t")
    elif suffix == ".txt":
        df = pd.read_csv(path, sep=None, engine="python")
    elif suffix in {".xls", ".xlsx"}:
        df = pd.read_excel(path, sheet_name=resolved_sheet_name if resolved_sheet_name is not None else 0)
    elif suffix == ".parquet":
        df = pd.read_parquet(path)
    else:
        raise ValueError(f"Unhandled file type '{suffix}'")

    df = _coerce_datetime_columns(df)

    metadata = {
        "input_path": str(path),
        "dataset_name": path.stem,
        "format": SUPPORTED_SUFFIXES[suffix],
        "sheet_name": resolved_sheet_name,
        "row_count": int(len(df)),
        "column_count": int(len(df.columns)),
    }
    return df, metadata
