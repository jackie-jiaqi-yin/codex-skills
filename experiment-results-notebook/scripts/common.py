#!/usr/bin/env python3
"""Shared helpers for the experiment results notebook skill."""

from __future__ import annotations

import csv
import hashlib
import json
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


NOTEBOOK_DIRNAME = ".experiment-results-notebook"
STRUCTURED_EXTENSIONS = {".csv", ".json", ".yaml", ".yml"}
PLOT_EXTENSIONS = {".png", ".jpg", ".jpeg", ".svg", ".pdf"}
CODE_EXTENSIONS = {
    ".py",
    ".sh",
    ".toml",
    ".ini",
    ".cfg",
    ".conf",
    ".md",
    ".txt",
    ".tex",
    ".sql",
}
DEFAULT_IGNORE_GLOBS = [
    ".git/**",
    ".venv/**",
    "venv/**",
    "node_modules/**",
    "__pycache__/**",
    ".pytest_cache/**",
    ".mypy_cache/**",
    ".idea/**",
    ".vscode/**",
    ".experiment-results-notebook/**",
]
REQUIRED_SECTION_TITLES = [
    "Context",
    "Methodology Delta",
    "New Results",
    "Comparison vs Prior Best",
    "Figures and Tables",
    "User Notes Revised",
    "Risks/Anomalies",
    "Next Questions",
]
INDEX_LIKE_TOKENS = {
    "step",
    "steps",
    "epoch",
    "epochs",
    "iter",
    "iteration",
    "iterations",
    "seed",
    "fold",
    "rank",
}
CONFIG_LIKE_TOKENS = {
    "lr",
    "learningrate",
    "wd",
    "weightdecay",
    "dropout",
    "droppath",
    "batchsize",
    "accumulationsteps",
    "warmup",
    "momentum",
    "epsilon",
    "eps",
    "alpha",
    "beta",
    "gamma",
    "temperature",
    "threshold",
    "ratio",
    "fraction",
    "topk",
    "beam",
    "maxlength",
    "minlength",
    "layers",
    "hidden",
    "dim",
    "heads",
    "width",
    "depth",
    "kernel",
    "budget",
}
CONFIG_ROLE_TOKENS = {
    "config",
    "setting",
    "parameter",
    "param",
    "spec",
    "schema",
    "manifest",
    "registry",
    "format",
    "template",
    "prompt",
    "optimizer",
    "scheduler",
    "objective",
    "criterion",
    "model",
    "module",
    "architecture",
    "training",
    "trainer",
    "pipeline",
    "stage",
    "artifact",
    "resource",
    "file",
    "path",
    "dir",
    "directory",
    "uri",
    "url",
    "cache",
    "checkpoint",
    "resume",
    "dataset",
    "corpus",
    "data",
    "table",
    "record",
    "loader",
    "sampler",
    "collate",
    "reader",
    "parser",
    "augmentation",
    "ingest",
    "preprocess",
    "process",
    "clean",
    "normalize",
    "standardize",
    "scale",
    "tokenize",
    "detokenize",
    "transform",
    "parse",
    "encode",
    "decode",
    "embed",
    "extract",
    "aggregate",
    "group",
    "merge",
    "join",
    "align",
    "sync",
    "resample",
    "resize",
    "crop",
    "mask",
    "trim",
    "clip",
    "interpolate",
    "impute",
    "dedup",
    "deduplicate",
    "filter",
    "feature",
    "target",
    "label",
    "source",
    "input",
    "output",
    "split",
    "partition",
    "holdout",
    "sample",
    "sampling",
    "shuffle",
    "stratify",
    "bootstrap",
    "shard",
    "window",
    "sequence",
    "segment",
    "chunk",
    "context",
    "stride",
    "hop",
    "fold",
    "seed",
    "batch",
    "epoch",
    "layer",
    "head",
    "hidden",
    "embedding",
    "projection",
    "backbone",
    "adapter",
    "pooling",
    "classifier",
    "regressor",
    "encoder",
    "decoder",
    "dropout",
    "patience",
    "warmup",
    "decay",
    "clip",
    "worker",
    "device",
    "precision",
    "dtype",
    "distributed",
    "regularization",
    "finetune",
    "pretrain",
    "freeze",
    "unfreeze",
    "teacher",
    "student",
    "distill",
    "trial",
    "pruner",
    "budget",
    "sweep",
    "search",
}
RESULT_ROLE_TOKENS = {
    "metric",
    "score",
    "accuracy",
    "acc",
    "precision",
    "recall",
    "specificity",
    "sensitivity",
    "selectivity",
    "tpr",
    "tnr",
    "f1",
    "auc",
    "auroc",
    "auprc",
    "ap",
    "roc",
    "pr",
    "map",
    "mrr",
    "ndcg",
    "bleu",
    "rouge",
    "meteor",
    "cider",
    "spice",
    "em",
    "iou",
    "dice",
    "psnr",
    "ssim",
    "reward",
    "winrate",
    "loss",
    "error",
    "rmse",
    "mae",
    "mse",
    "mape",
    "smape",
    "msle",
    "r2",
    "rm2",
    "cindex",
    "concordance",
    "nll",
    "brier",
    "ece",
    "calibration",
    "sharpness",
    "uncertainty",
    "entropy",
    "coverage",
    "stability",
    "robustness",
    "fairness",
    "parity",
    "bias",
    "drift",
    "variance",
    "std",
    "stderr",
    "mean",
    "median",
    "percentile",
    "quantile",
    "correlation",
    "covariance",
    "pearson",
    "spearman",
    "kendall",
    "hitrate",
    "passrate",
    "success",
    "failure",
    "latency",
    "memory",
    "flops",
    "throughput",
    "runtime",
    "perplexity",
    "ppl",
}
RESULT_CONTEXT_TOKENS = {
    "benchmark",
    "dev",
    "eval",
    "evaluation",
    "holdout",
    "leaderboard",
    "test",
    "train",
    "training",
    "val",
    "valid",
    "validation",
}
LOWER_IS_BETTER_HINTS = (
    "loss",
    "error",
    "wer",
    "cer",
    "latency",
    "runtime",
    "time",
    "perplexity",
    "ppl",
    "rmse",
    "mae",
    "mse",
)
RESULT_PRIORITY_HINTS = (
    "testr2",
    "r2",
    "testcindex",
    "cindex",
    "testmae",
    "mae",
    "testrmse",
    "rmse",
    "testmape",
    "mape",
    "accuracy",
    "acc",
    "f1",
    "precision",
    "recall",
    "auc",
    "auroc",
    "auprc",
    "map",
    "mrr",
    "ndcg",
    "passrate",
    "success",
    "perplexity",
    "ppl",
    "brier",
    "ece",
    "bleu",
    "rouge",
    "exactmatch",
    "em",
    "iou",
    "dice",
    "psnr",
    "ssim",
    "reward",
    "winrate",
    "loss",
    "latency",
    "throughput",
)

ENTRY_START_RE = re.compile(r"<!--\s*ern:entry\s+start\s+id=(?P<id>[A-Za-z0-9_-]+)\s*-->")
ENTRY_END_RE = re.compile(r"<!--\s*ern:entry\s+end\s+id=(?P<id>[A-Za-z0-9_-]+)\s*-->")
SECTION_RE = re.compile(
    r'<!--\s*ern:section\s+entry=(?P<entry>[A-Za-z0-9_-]+)\s+id=(?P<id>[A-Za-z0-9_-]+)\s+title="(?P<title>[^"]+)"\s*-->'
)


@dataclass
class NotebookSection:
    entry_id: str
    section_id: str
    title: str
    marker_start: int
    content_start: int
    content_end: int
    content: str


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def timestamp_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def slugify(text: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower())
    return value.strip("-") or "item"


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def read_json(path: Path, default: Any | None = None) -> Any:
    if not path.exists():
        return {} if default is None else default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def read_yaml(path: Path, default: Any | None = None) -> Any:
    if not path.exists():
        return {} if default is None else default
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if loaded is None:
        return {} if default is None else default
    return loaded


def write_yaml(path: Path, payload: Any) -> None:
    ensure_dir(path.parent)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_text(text: str) -> str:
    lines = [line.rstrip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    normalized = "\n".join(lines).strip()
    return normalized


def normalize_metric_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", key.strip().lower())


def metric_tokens(name: str) -> list[str]:
    pieces = re.split(r"[^a-zA-Z0-9]+", name.strip().lower())
    tokens: list[str] = []
    for piece in pieces:
        if not piece:
            continue
        tokens.extend(part for part in re.findall(r"[a-z]+|\d+", piece) if part)
    return tokens


def try_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def flatten_mapping(value: Any, prefix: str = "") -> dict[str, float]:
    flattened: dict[str, float] = {}
    if isinstance(value, dict):
        for key, item in value.items():
            nested_prefix = f"{prefix}.{key}" if prefix else str(key)
            flattened.update(flatten_mapping(item, nested_prefix))
        return flattened
    if isinstance(value, list):
        for idx, item in enumerate(value):
            nested_prefix = f"{prefix}[{idx}]"
            flattened.update(flatten_mapping(item, nested_prefix))
        return flattened
    numeric = try_float(value)
    if numeric is not None and prefix:
        flattened[prefix] = numeric
    return flattened


def _representative_table_row(rows: list[dict[str, Any]]) -> dict[str, Any]:
    ranked_rows: list[tuple[float, int, dict[str, Any]]] = []
    for idx, row in enumerate(rows):
        rank_value = try_float(row.get("rank"))
        if rank_value is None:
            rank_value = try_float(row.get("trial_rank"))
        ranked_rows.append((rank_value if rank_value is not None else float(idx + 1), idx, row))
    ranked_rows.sort(key=lambda item: (item[0], item[1]))
    return ranked_rows[0][2] if ranked_rows else {}


def flatten_structured_payload(value: Any) -> dict[str, float]:
    if isinstance(value, list):
        dict_rows = [item for item in value if isinstance(item, dict)]
        if dict_rows and len(dict_rows) == len(value):
            return flatten_mapping(_representative_table_row(dict_rows))
        return {}
    return flatten_mapping(value)


def load_structured_metrics(path: Path) -> dict[str, float]:
    suffix = path.suffix.lower()
    try:
        if suffix == ".csv":
            return _load_csv_metrics(path)
        if suffix == ".json":
            return flatten_structured_payload(json.loads(path.read_text(encoding="utf-8")))
        if suffix in {".yaml", ".yml"}:
            return flatten_structured_payload(yaml.safe_load(path.read_text(encoding="utf-8")))
    except Exception:
        return {}
    return {}


def load_tabular_rows(path: Path, row_limit: int = 20) -> list[dict[str, Any]]:
    suffix = path.suffix.lower()
    try:
        if suffix == ".csv":
            with path.open("r", encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle)
                return [dict(row) for _, row in zip(range(row_limit), reader)]
        if suffix == ".json":
            payload = json.loads(path.read_text(encoding="utf-8"))
            return _tabular_rows_from_payload(payload, row_limit=row_limit)
        if suffix in {".yaml", ".yml"}:
            payload = yaml.safe_load(path.read_text(encoding="utf-8"))
            return _tabular_rows_from_payload(payload, row_limit=row_limit)
    except Exception:
        return []
    return []


def _tabular_rows_from_payload(value: Any, row_limit: int = 20) -> list[dict[str, Any]]:
    if isinstance(value, list) and value and all(isinstance(item, dict) for item in value):
        return [dict(item) for item in value[:row_limit]]
    if isinstance(value, dict):
        for item in value.values():
            if isinstance(item, list) and item and all(isinstance(row, dict) for row in item):
                return [dict(row) for row in item[:row_limit]]
    return []


def _load_csv_metrics(path: Path) -> dict[str, float]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = [dict(row) for row in reader]

    if not rows:
        return {}

    fieldnames = reader.fieldnames or []
    metrics: dict[str, float] = {}

    lower_fields = {name.lower(): name for name in fieldnames}
    if "metric" in lower_fields and "value" in lower_fields:
        metric_col = lower_fields["metric"]
        value_col = lower_fields["value"]
        for row in rows:
            metric_name = str(row.get(metric_col, "")).strip()
            metric_value = try_float(row.get(value_col))
            if metric_name and metric_value is not None:
                metrics[metric_name] = metric_value

    for name in fieldnames:
        numeric_values = [try_float(row.get(name)) for row in rows]
        numeric_values = [value for value in numeric_values if value is not None]
        if numeric_values:
            metrics[name] = numeric_values[-1]

    return metrics


def metric_value(metrics: dict[str, float], primary_metric: str) -> float | None:
    if not primary_metric or not primary_metric.strip():
        return None
    normalized_target = normalize_metric_key(primary_metric)
    exact_match = None
    suffix_match = None
    for key, value in metrics.items():
        normalized_key = normalize_metric_key(key)
        if normalized_key == normalized_target:
            exact_match = value
            break
        if normalized_key.endswith(normalized_target) or normalized_target.endswith(normalized_key):
            suffix_match = value
    return exact_match if exact_match is not None else suffix_match


def match_metric_key(metric_names: list[str], preferred_metric: str) -> str | None:
    if not preferred_metric or not preferred_metric.strip():
        return None
    normalized_target = normalize_metric_key(preferred_metric)
    exact_match = None
    suffix_match = None
    for key in metric_names:
        normalized_key = normalize_metric_key(key)
        if normalized_key == normalized_target:
            exact_match = key
            break
        if normalized_key.endswith(normalized_target) or normalized_target.endswith(normalized_key):
            suffix_match = key
    return exact_match or suffix_match


def metric_kind(metric_name: str) -> str:
    normalized = normalize_metric_key(metric_name)
    lowered = metric_name.strip().lower()
    tokens = metric_tokens(metric_name)
    token_set = set(tokens)

    if lowered.startswith("[") or "[0]" in lowered or "[1]" in lowered or "]." in lowered:
        return "index"
    if normalized in INDEX_LIKE_TOKENS or token_set.intersection(INDEX_LIKE_TOKENS):
        return "index"

    result_score = 0
    config_score = 0

    if normalized in RESULT_ROLE_TOKENS:
        result_score += 2
    if normalized in CONFIG_LIKE_TOKENS:
        config_score += 2

    result_score += len(token_set.intersection(RESULT_ROLE_TOKENS))
    config_score += len(token_set.intersection(CONFIG_LIKE_TOKENS))
    config_score += len(token_set.intersection(CONFIG_ROLE_TOKENS))

    if token_set.intersection(RESULT_CONTEXT_TOKENS) and result_score:
        result_score += 1
    if token_set.intersection({"path", "file", "dir", "directory", "cache", "checkpoint", "manifest", "registry", "schema"}):
        config_score += 2
    if any(token in normalized for token in LOWER_IS_BETTER_HINTS):
        result_score += 1

    if result_score > config_score:
        return "result"
    if config_score > result_score:
        return "config"
    if token_set.intersection(CONFIG_ROLE_TOKENS):
        return "config"
    return "result"


def infer_metric_direction(metric_name: str) -> str:
    normalized = normalize_metric_key(metric_name)
    if any(token in normalized for token in LOWER_IS_BETTER_HINTS):
        return "min"
    return "max"


def metric_priority(metric_name: str) -> int:
    normalized = normalize_metric_key(metric_name)
    for idx, token in enumerate(RESULT_PRIORITY_HINTS):
        if token in normalized:
            return len(RESULT_PRIORITY_HINTS) - idx
    return 0


def metric_split_prefix(metric_name: str) -> str:
    lowered = metric_name.strip().lower()
    for prefix in ("test.", "test_", "val.", "val_", "train.", "train_"):
        if lowered.startswith(prefix):
            return prefix.split(".")[0].split("_")[0]
    return ""


def choose_metric_view(
    runs: list[dict[str, Any]],
    preferred_metric: str = "",
    preferred_direction: str = "",
    limit: int = 5,
) -> dict[str, Any]:
    metric_counts: dict[str, int] = {}
    metric_samples: dict[str, list[float]] = {}

    for run in runs:
        for key, value in (run.get("metrics") or {}).items():
            if metric_kind(key) != "result":
                continue
            metric_counts[key] = metric_counts.get(key, 0) + 1
            metric_samples.setdefault(key, []).append(float(value))

    metric_names = list(metric_counts.keys())
    matched_preferred = match_metric_key(metric_names, preferred_metric)

    ranked_metrics = sorted(
        metric_names,
        key=lambda key: (
            0 if key == matched_preferred else 1,
            -metric_priority(key),
            -metric_counts.get(key, 0),
            key.lower(),
        ),
    )

    ranking_metric = matched_preferred or (ranked_metrics[0] if ranked_metrics else None)
    ranking_direction = preferred_direction or (infer_metric_direction(ranking_metric) if ranking_metric else "")
    ranking_source = "user" if matched_preferred else ("inferred" if ranking_metric else "none")

    display_metrics: list[str] = []
    seen_normalized: set[str] = set()

    def add_metric(metric: str | None) -> None:
        if not metric:
            return
        normalized = normalize_metric_key(metric)
        if normalized in seen_normalized:
            return
        seen_normalized.add(normalized)
        display_metrics.append(metric)

    add_metric(ranking_metric)
    ranking_prefix = metric_split_prefix(ranking_metric or "")
    if ranking_prefix:
        companion_metrics = sorted(
            [
                key
                for key in ranked_metrics
                if key != ranking_metric and metric_split_prefix(key) == ranking_prefix
            ],
            key=lambda key: (-metric_priority(key), -metric_counts.get(key, 0), key.lower()),
        )
        for key in companion_metrics:
            add_metric(key)
            if len(display_metrics) >= limit:
                break

    for key in ranked_metrics:
        add_metric(key)
        if len(display_metrics) >= limit:
            break

    notes: list[str] = []
    if preferred_metric and not matched_preferred:
        notes.append(
            f"Preferred primary metric `{preferred_metric}` was not a strong display candidate in the scanned outputs."
        )
    if not ranking_metric:
        notes.append("No suitable result metric was found for ranking; the notebook should still summarize methodology and artifacts.")

    catalog = [
        {
            "metric": key,
            "run_count": metric_counts.get(key, 0),
            "direction": infer_metric_direction(key),
            "priority": metric_priority(key),
        }
        for key in ranked_metrics
    ]

    return {
        "display_metrics": display_metrics,
        "ranking_metric": ranking_metric or "",
        "ranking_direction": ranking_direction,
        "ranking_source": ranking_source,
        "metric_catalog": catalog,
        "notes": notes,
    }


def git(args: list[str], cwd: Path, check: bool = False) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        text=True,
        capture_output=True,
        check=False,
    )
    if check and result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or f"git {' '.join(args)} failed")
    return result


def is_git_repo(path: Path) -> bool:
    result = git(["rev-parse", "--is-inside-work-tree"], cwd=path)
    return result.returncode == 0 and result.stdout.strip() == "true"


def parse_github_remote(url: str) -> dict[str, str] | None:
    value = url.strip()
    patterns = [
        r"^git@github\.com:(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?$",
        r"^https://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?/?$",
        r"^ssh://git@github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?$",
    ]
    for pattern in patterns:
        match = re.match(pattern, value)
        if match:
            return {"owner": match.group("owner"), "repo": match.group("repo")}
    return None


def relative_path(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except Exception:
        return str(path)


def should_ignore(rel_path: str, ignore_globs: list[str]) -> bool:
    from fnmatch import fnmatch

    normalized = rel_path.replace("\\", "/")
    return any(fnmatch(normalized, pattern) for pattern in ignore_globs)


def matches_any_glob(rel_path: str, globs: list[str]) -> bool:
    from fnmatch import fnmatch

    if not globs:
        return True
    normalized = rel_path.replace("\\", "/")
    return any(fnmatch(normalized, pattern) for pattern in globs)


def parse_marked_sections(text: str) -> list[NotebookSection]:
    section_matches = list(SECTION_RE.finditer(text))
    end_matches = list(ENTRY_END_RE.finditer(text))
    sections: list[NotebookSection] = []

    for idx, match in enumerate(section_matches):
        next_section_start = section_matches[idx + 1].start() if idx + 1 < len(section_matches) else len(text)
        later_entry_ends = [item.start() for item in end_matches if item.start() > match.end()]
        next_entry_end = later_entry_ends[0] if later_entry_ends else len(text)
        content_end = min(next_section_start, next_entry_end)
        content = text[match.end() : content_end]
        sections.append(
            NotebookSection(
                entry_id=match.group("entry"),
                section_id=match.group("id"),
                title=match.group("title"),
                marker_start=match.start(),
                content_start=match.end(),
                content_end=content_end,
                content=content,
            )
        )
    return sections


def section_hash_index(text: str) -> dict[str, dict[str, str]]:
    index: dict[str, dict[str, str]] = {}
    for section in parse_marked_sections(text):
        index[section.section_id] = {
            "entry_id": section.entry_id,
            "title": section.title,
            "hash": sha256_text(normalize_text(section.content)),
        }
    return index


def replace_section_content(text: str, section_id: str, new_content: str) -> str:
    sections = parse_marked_sections(text)
    for section in sections:
        if section.section_id != section_id:
            continue
        cleaned = new_content.strip("\n")
        replacement = "\n" + cleaned + "\n\n"
        return text[: section.content_start] + replacement + text[section.content_end :]
    return text


def remove_entry_blocks(text: str, entry_id: str) -> str:
    pattern = re.compile(
        rf"<!--\s*ern:entry\s+start\s+id={re.escape(entry_id)}\s*-->.*?<!--\s*ern:entry\s+end\s+id={re.escape(entry_id)}\s*-->",
        flags=re.DOTALL,
    )
    cleaned = pattern.sub("", text)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def parse_h2_sections(markdown_text: str) -> dict[str, str]:
    matches = list(re.finditer(r"^##\s+(.+?)\s*$", markdown_text, flags=re.MULTILINE))
    sections: dict[str, str] = {}
    for idx, match in enumerate(matches):
        title = match.group(1).strip()
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(markdown_text)
        sections[title] = markdown_text[start:end].strip()
    return sections
