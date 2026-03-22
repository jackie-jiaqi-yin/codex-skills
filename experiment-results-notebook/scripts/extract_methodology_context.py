#!/usr/bin/env python3
"""Extract methodology evidence from experiment artifacts plus supporting repo code."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import yaml

from common import (
    CODE_EXTENSIONS,
    DEFAULT_IGNORE_GLOBS,
    now_utc_iso,
    read_json,
    relative_path,
    should_ignore,
    write_json,
)


THEMES = [
    {
        "id": "data_preprocessing",
        "title": "Data and preprocessing",
        "path_terms": (
            "config",
            "data",
            "dataset",
            "corpus",
            "table",
            "ingest",
            "reader",
            "prep",
            "preprocess",
            "clean",
            "feature",
            "transform",
            "tokenize",
            "normalize",
            "standardize",
            "scale",
            "align",
            "merge",
            "join",
            "filter",
            "dedup",
            "impute",
        ),
        "content_terms": (
            "preprocess",
            "clean",
            "filter",
            "merge",
            "join",
            "normalize",
            "standardize",
            "scale",
            "transform",
            "tokenize",
            "detokenize",
            "align",
            "resample",
            "interpolate",
            "clip",
            "trim",
            "mask",
            "dedup",
            "impute",
            "parquet",
            "csv",
            "jsonl",
            "arrow",
        ),
        "field_terms": (
            "data",
            "dataset",
            "corpus",
            "source",
            "input",
            "inputs",
            "feature",
            "features",
            "target",
            "label",
            "outcome",
            "response",
            "column",
            "columns",
            "schema",
            "clean",
            "filter",
            "normalize",
            "standardize",
            "scale",
            "transform",
            "tokenize",
            "align",
            "merge",
            "join",
            "dedup",
            "impute",
            "resample",
        ),
        "preferred_prefixes": ("configs/", "scripts/data/", "src/preprocessing/", "src/training/"),
    },
    {
        "id": "split_windowing",
        "title": "Splits and sampling",
        "path_terms": (
            "split",
            "sample",
            "sampler",
            "window",
            "chunk",
            "segment",
            "partition",
            "fold",
            "bootstrap",
            "shard",
            "dataset",
            "loader",
            "collate",
            "pipeline",
        ),
        "content_terms": (
            "split",
            "sample",
            "stratify",
            "shuffle",
            "window",
            "chunk",
            "segment",
            "partition",
            "stride",
            "context",
            "fold",
            "bootstrap",
            "holdout",
            "loader",
            "batch",
            "collate",
        ),
        "field_terms": (
            "split",
            "partition",
            "holdout",
            "fold",
            "sample",
            "sampling",
            "sampler",
            "window",
            "sequence",
            "segment",
            "context",
            "stride",
            "hop",
            "bootstrap",
            "seed",
            "shuffle",
            "stratify",
            "loader",
            "collate",
            "batch",
            "shard",
        ),
        "preferred_prefixes": ("src/data/", "src/training/", "scripts/experiments/", "configs/experiments/"),
    },
    {
        "id": "model_training",
        "title": "Model and training",
        "path_terms": (
            "model",
            "train",
            "trainer",
            "experiment",
            "factory",
            "architecture",
            "backbone",
            "encoder",
            "decoder",
            "adapter",
            "finetune",
            "pretrain",
            "objective",
            "loss",
        ),
        "content_terms": (
            "model",
            "train",
            "optimizer",
            "scheduler",
            "dropout",
            "hidden",
            "layer",
            "encoder",
            "decoder",
            "backbone",
            "adapter",
            "freeze",
            "unfreeze",
            "finetune",
            "pretrain",
            "objective",
            "criterion",
            "distill",
        ),
        "field_terms": (
            "model",
            "module",
            "architecture",
            "backbone",
            "encoder",
            "decoder",
            "adapter",
            "head",
            "pooling",
            "classifier",
            "regressor",
            "optimizer",
            "scheduler",
            "training",
            "trainer",
            "dropout",
            "hidden",
            "layer",
            "width",
            "depth",
            "finetune",
            "pretrain",
            "freeze",
            "unfreeze",
            "objective",
            "criterion",
            "distill",
        ),
        "preferred_prefixes": ("src/models/", "src/training/", "configs/experiments/", "scripts/experiments/"),
    },
    {
        "id": "evaluation_reporting",
        "title": "Evaluation and reporting",
        "path_terms": (
            "report",
            "metric",
            "evaluate",
            "benchmark",
            "leaderboard",
            "ablation",
            "plot",
            "visual",
            "analysis",
            "summary",
            "table",
            "figure",
        ),
        "content_terms": (
            "metric",
            "evaluate",
            "evaluation",
            "validation",
            "test",
            "benchmark",
            "leaderboard",
            "ablation",
            "report",
            "plot",
            "curve",
            "chart",
            "summary",
            "comparison",
            "diagnostic",
            "error",
        ),
        "field_terms": (
            "metric",
            "score",
            "report",
            "summary",
            "comparison",
            "rank",
            "trial",
            "eval",
            "evaluation",
            "validation",
            "test",
            "benchmark",
            "leaderboard",
            "ablation",
            "plot",
            "figure",
            "table",
            "diagnostic",
            "confidence",
            "interval",
        ),
        "preferred_prefixes": ("scripts/reports/", "scripts/exploration/", "src/utils/", "src/visualization/"),
    },
]

MAX_FILES_PER_THEME = 3
MAX_SNIPPETS_PER_FILE = 4


def _tokens(value: str) -> list[str]:
    return [token for token in re.split(r"[^a-z0-9]+", value.lower()) if token]


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def _load_payload(path: Path) -> Any:
    suffix = path.suffix.lower()
    try:
        if suffix == ".json":
            return json.loads(path.read_text(encoding="utf-8"))
        if suffix in {".yaml", ".yml"}:
            return yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return None


def _walk_strings(value: Any, prefix: str = "") -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    if isinstance(value, dict):
        for key, item in value.items():
            nested = f"{prefix}.{key}" if prefix else str(key)
            pairs.extend(_walk_strings(item, nested))
        return pairs
    if isinstance(value, list):
        if value and all(isinstance(item, str) for item in value):
            pairs.append((prefix, ", ".join(str(item) for item in value[:12])))
            return pairs
        for idx, item in enumerate(value[:20]):
            nested = f"{prefix}[{idx}]"
            pairs.extend(_walk_strings(item, nested))
        return pairs
    if isinstance(value, str) and value.strip():
        pairs.append((prefix, value.strip()))
    return pairs


def _walk_scalars(value: Any, prefix: str = "") -> list[tuple[str, Any]]:
    pairs: list[tuple[str, Any]] = []
    if isinstance(value, dict):
        for key, item in value.items():
            nested = f"{prefix}.{key}" if prefix else str(key)
            pairs.extend(_walk_scalars(item, nested))
        return pairs
    if isinstance(value, list):
        for idx, item in enumerate(value[:20]):
            nested = f"{prefix}[{idx}]"
            pairs.extend(_walk_scalars(item, nested))
        return pairs
    if prefix:
        pairs.append((prefix, value))
    return pairs


def _looks_like_data_path(text: str) -> bool:
    lowered = text.lower()
    if lowered.endswith((".parquet", ".csv", ".tsv", ".feather", ".pkl", ".npz", ".npy", ".jsonl", ".arrow", ".h5", ".hdf5", ".tfrecord")):
        return True
    return any(
        token in lowered
        for token in (
            "/data/",
            "data/",
            "/dataset",
            "dataset/",
            "/inputs/",
            "inputs/",
            "/raw/",
            "/processed/",
            "/features/",
            "/labels/",
            "/tables/",
            "/corpus/",
        )
    )


def _theme_matches_key(theme: dict[str, Any], key: str) -> bool:
    key_tokens = set(_tokens(key))
    return bool(key_tokens.intersection(theme.get("field_terms", ())))


def _unique_keep_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        if not item or item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


def _gather_facts(workspace_root: Path, scan_manifest: dict[str, Any]) -> dict[str, Any]:
    data_paths: list[str] = []
    target_columns: list[str] = []
    feature_columns: list[str] = []
    model_terms: list[str] = []
    evaluation_files: list[str] = []
    params_by_theme: dict[str, list[str]] = {theme["id"]: [] for theme in THEMES}
    source_paths: list[str] = []

    for artifact in scan_manifest.get("changed_artifacts", []):
        rel_path = artifact.get("path", "")
        if artifact.get("kind") != "structured" or not rel_path:
            continue
        path = workspace_root / rel_path
        payload = _load_payload(path)
        if payload is None:
            continue
        source_paths.append(rel_path)

        for key, value in _walk_strings(payload):
            lowered_key = key.lower()
            lowered_value = value.lower()
            if _looks_like_data_path(lowered_value):
                data_paths.append(value)
            if any(token in _tokens(lowered_key) for token in ("target", "targets", "label", "labels", "outcome", "response", "groundtruth")) and "mode" not in _tokens(lowered_key) and len(value) < 80:
                target_columns.append(value)
            if any(token in _tokens(lowered_key) for token in ("feature", "features", "input", "inputs", "predictor", "predictors", "covariate", "covariates", "signal", "signals", "channel", "channels")):
                feature_columns.extend([item.strip() for item in value.split(",") if item.strip()])
            if any(token in _tokens(lowered_key) for token in ("model", "module", "architecture", "backbone", "encoder", "decoder", "adapter", "head", "pooling", "family", "type", "name")) and len(value) < 80:
                model_terms.append(value)

        for key, value in _walk_scalars(payload):
            lowered_key = key.lower()
            if any(token in rel_path.lower() for token in ("report", "summary", "eval", "metric", "leaderboard", "comparison", "result", "score", "table", "plot", "figure", "chart", "benchmark", "ablation")):
                evaluation_files.append(rel_path)
            rendered_value = value
            if isinstance(value, float):
                rendered_value = f"{value:.6g}"
            fact = f"`{key}` = `{rendered_value}`"
            for theme in THEMES:
                if _theme_matches_key(theme, lowered_key):
                    params_by_theme[theme["id"]].append(fact)

    return {
        "data_paths": _unique_keep_order(data_paths)[:8],
        "target_columns": _unique_keep_order(target_columns)[:6],
        "feature_columns": _unique_keep_order(feature_columns)[:12],
        "model_terms": _unique_keep_order(model_terms)[:8],
        "evaluation_files": _unique_keep_order(evaluation_files)[:8],
        "params_by_theme": {key: _unique_keep_order(value)[:12] for key, value in params_by_theme.items()},
        "source_paths": _unique_keep_order(source_paths),
    }


def _candidate_repo_files(workspace_root: Path) -> list[Path]:
    preferred_roots = ["configs", "scripts", "src", "docs", "tests"]
    files: list[Path] = []
    ignore_globs = DEFAULT_IGNORE_GLOBS

    for root_name in preferred_roots:
        root = workspace_root / root_name
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            rel_path = relative_path(path, workspace_root)
            if should_ignore(rel_path, ignore_globs):
                continue
            if path.suffix.lower() not in CODE_EXTENSIONS.union({".json", ".yaml", ".yml"}):
                continue
            files.append(path)
    return files


def _search_terms_for_theme(facts: dict[str, Any], theme_id: str) -> list[str]:
    terms: list[str] = []
    if theme_id == "data_preprocessing":
        for item in facts.get("data_paths", []):
            terms.append(Path(item).name.lower())
            parts = [part for part in Path(item).parts if part not in {"data", "processed", "raw"}]
            terms.extend(part.lower() for part in parts[-3:])
        terms.extend(term.lower() for term in facts.get("target_columns", []))
        terms.extend(term.lower() for term in facts.get("feature_columns", []))
        generic = [
            "dataset",
            "corpus",
            "input",
            "feature",
            "target",
            "label",
            "schema",
            "clean",
            "filter",
            "normalize",
            "standardize",
            "scale",
            "transform",
            "merge",
            "join",
            "align",
            "dedup",
            "impute",
            "resample",
            "tokenize",
        ]
    elif theme_id == "split_windowing":
        generic = [
            "split",
            "partition",
            "sample",
            "sampler",
            "stratify",
            "shuffle",
            "holdout",
            "window",
            "chunk",
            "segment",
            "context",
            "stride",
            "fold",
            "bootstrap",
            "loader",
            "collate",
            "batch",
        ]
    elif theme_id == "model_training":
        terms.extend(term.lower() for term in facts.get("model_terms", []))
        generic = [
            "model",
            "module",
            "architecture",
            "backbone",
            "encoder",
            "decoder",
            "adapter",
            "optimizer",
            "scheduler",
            "trainer",
            "finetune",
            "pretrain",
            "objective",
            "criterion",
            "freeze",
            "unfreeze",
        ]
    else:
        generic = [
            "metric",
            "evaluate",
            "evaluation",
            "benchmark",
            "leaderboard",
            "ablation",
            "report",
            "summary",
            "comparison",
            "plot",
            "figure",
            "table",
            "chart",
            "curve",
            "validation",
            "test",
        ]
    terms.extend(generic)
    return [term for term in _unique_keep_order([term.strip() for term in terms if term.strip()]) if len(term) >= 3]


def _file_score(path: Path, text: str, theme: dict[str, Any], search_terms: list[str], workspace_root: Path) -> int:
    rel_path = relative_path(path, workspace_root).lower()
    score = 0
    for prefix in theme.get("preferred_prefixes", ()):
        if rel_path.startswith(prefix):
            score += 8
    if theme["id"] == "data_preprocessing" and any(token in rel_path for token in ("preprocess", "clean", "normalize", "feature", "transform", "data_pipeline")):
        score += 12
    if theme["id"] == "split_windowing" and any(token in rel_path for token in ("split", "window", "sample", "sampler", "partition", "dataset", "loader", "collate", "pipeline")):
        score += 12
    if theme["id"] == "model_training" and any(token in rel_path for token in ("model", "trainer", "factory", "backbone", "encoder", "decoder", "adapter", "finetune", "pretrain", "objective")):
        score += 10
    if theme["id"] == "evaluation_reporting" and any(token in rel_path for token in ("report", "metric", "visual", "plot", "figure", "table", "evaluate", "analysis", "benchmark", "ablation")):
        score += 10
    for term in theme["path_terms"]:
        if term in rel_path:
            score += 4
    lowered = text.lower()
    for term in theme["content_terms"]:
        if term in lowered:
            score += 2
    for term in search_terms:
        if term in lowered:
            score += 1
    return score


def _top_docstring(text: str) -> str:
    match = re.search(r'^[ \t]*("""|\'\'\')(?P<body>.*?)(\1)', text, re.DOTALL | re.MULTILINE)
    if not match:
        return ""
    body = " ".join(line.strip() for line in match.group("body").splitlines() if line.strip())
    return body[:220].strip()


def _extract_snippets(text: str, terms: list[str]) -> list[str]:
    snippets: list[str] = []
    docstring = _top_docstring(text)
    if docstring:
        snippets.append(docstring)

    lowered_terms = [term.lower() for term in terms if term]
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("import ", "from ", "# noqa")):
            continue
        lowered = stripped.lower()
        if any(term in lowered for term in lowered_terms):
            if len(stripped) > 180:
                stripped = stripped[:177] + "..."
            snippets.append(stripped)
        if len(snippets) >= MAX_SNIPPETS_PER_FILE:
            break
    return _unique_keep_order(snippets)[:MAX_SNIPPETS_PER_FILE]


def _evidence_for_theme(workspace_root: Path, facts: dict[str, Any], theme: dict[str, Any]) -> list[dict[str, Any]]:
    search_terms = _search_terms_for_theme(facts, theme["id"])
    scored: list[tuple[int, str, Path, str]] = []
    for path in _candidate_repo_files(workspace_root):
        text = _read_text(path)
        if not text:
            continue
        score = _file_score(path, text, theme, search_terms, workspace_root)
        if score <= 0:
            continue
        scored.append((score, relative_path(path, workspace_root), path, text))
    scored.sort(key=lambda item: (-item[0], item[1]))

    evidence: list[dict[str, Any]] = []
    for score, rel_path, _, text in scored[:MAX_FILES_PER_THEME]:
        evidence.append(
            {
                "path": rel_path,
                "score": score,
                "snippets": _extract_snippets(text, [*theme["content_terms"], *search_terms]),
            }
        )
    return evidence


def _short_list(items: list[str], limit: int = 4) -> str:
    return ", ".join(f"`{item}`" for item in items[:limit])


def _build_sections(workspace_root: Path, facts: dict[str, Any]) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    for theme in THEMES:
        bullets: list[str] = []
        if theme["id"] == "data_preprocessing":
            if facts["data_paths"]:
                bullets.append(f"Primary input artifacts referenced in experiment configs: {_short_list(facts['data_paths'])}.")
            if facts["target_columns"] or facts["feature_columns"]:
                target_text = _short_list(facts["target_columns"], limit=2) or "not recovered"
                feature_text = _short_list(facts["feature_columns"], limit=6) or "not recovered"
                bullets.append(f"Detected prediction target(s): {target_text}; detected input feature columns: {feature_text}.")
        elif theme["id"] == "split_windowing":
            if facts["params_by_theme"][theme["id"]]:
                bullets.append(
                    "Split/windowing parameters recovered from configs include "
                    + ", ".join(facts["params_by_theme"][theme["id"]][:6])
                    + "."
                )
        elif theme["id"] == "model_training":
            if facts["model_terms"]:
                bullets.append(f"Model families or architecture terms visible in paths/configs: {_short_list(facts['model_terms'])}.")
            if facts["params_by_theme"][theme["id"]]:
                bullets.append(
                    "Model/training controls recovered from configs include "
                    + ", ".join(facts["params_by_theme"][theme["id"]][:6])
                    + "."
                )
        elif theme["id"] == "evaluation_reporting":
            if facts["evaluation_files"]:
                bullets.append(f"Evaluation/report artifacts include {_short_list(facts['evaluation_files'])}.")
            if facts["params_by_theme"][theme["id"]]:
                bullets.append(
                    "Evaluation/reporting controls recovered from configs include "
                    + ", ".join(facts["params_by_theme"][theme["id"]][:6])
                    + "."
                )

        evidence = _evidence_for_theme(workspace_root, facts, theme)
        if evidence:
            bullets.append(
                "Most relevant supporting code paths: "
                + ", ".join(f"`{item['path']}`" for item in evidence[:MAX_FILES_PER_THEME])
                + "."
            )
        sections.append(
            {
                "id": theme["id"],
                "title": theme["title"],
                "summary_bullets": bullets,
                "evidence": evidence,
            }
        )
    return sections


def extract_methodology_context(workspace_root: Path, scan_manifest: dict[str, Any]) -> dict[str, Any]:
    workspace_root = workspace_root.resolve()
    facts = _gather_facts(workspace_root, scan_manifest)
    sections = _build_sections(workspace_root, facts)
    warnings = []
    if not any(section.get("summary_bullets") for section in sections):
        warnings.append("No structured methodology facts were recovered from the scoped artifacts.")
    if not any(section.get("evidence") for section in sections):
        warnings.append("No supporting code files were matched outside the scoped experiment artifacts.")
    return {
        "generated_at": now_utc_iso(),
        "workspace_root": str(workspace_root),
        "facts": facts,
        "sections": sections,
        "warnings": warnings,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Extract methodology evidence from experiment artifacts and code")
    parser.add_argument("--workspace-root", required=True)
    parser.add_argument("--scan-manifest", required=True)
    parser.add_argument("--output", required=True)
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    payload = extract_methodology_context(
        workspace_root=Path(args.workspace_root),
        scan_manifest=read_json(Path(args.scan_manifest)),
    )
    write_json(Path(args.output), payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
