#!/usr/bin/env python3
"""Scan one workspace for experiment artifacts and git delta."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from common import (
    CODE_EXTENSIONS,
    DEFAULT_IGNORE_GLOBS,
    NOTEBOOK_DIRNAME,
    PLOT_EXTENSIONS,
    STRUCTURED_EXTENSIONS,
    git,
    is_git_repo,
    load_structured_metrics,
    matches_any_glob,
    metric_value,
    now_utc_iso,
    read_json,
    relative_path,
    sha256_file,
    should_ignore,
    write_json,
)


def _collect_commits(repo_root: Path, previous_commit: str | None) -> list[dict[str, Any]]:
    if not is_git_repo(repo_root):
        return []

    fmt = "%H%x1f%an%x1f%ad%x1f%s"
    if previous_commit:
        check = git(["rev-parse", "--verify", previous_commit], cwd=repo_root)
        log_args = ["log", "--date=iso-strict", f"--format={fmt}", "--name-only", f"{previous_commit}..HEAD"]
        if check.returncode != 0:
            log_args = ["log", "-n", "5", "--date=iso-strict", f"--format={fmt}", "--name-only"]
    else:
        log_args = ["log", "-n", "5", "--date=iso-strict", f"--format={fmt}", "--name-only"]

    result = git(log_args, cwd=repo_root)
    if result.returncode != 0:
        return []

    commits: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for line in result.stdout.splitlines():
        if "\x1f" in line:
            if current:
                commits.append(current)
            sha, author, authored_at, subject = line.split("\x1f", 3)
            current = {
                "sha": sha,
                "author": author,
                "authored_at": authored_at,
                "subject": subject,
                "files": [],
            }
            continue
        if current is None:
            continue
        stripped = line.strip()
        if stripped:
            current["files"].append(stripped)

    if current:
        commits.append(current)
    return commits


def _collect_file_index(
    workspace_root: Path,
    scope_root: Path,
    experiment_globs: list[str],
    ignore_globs: list[str],
) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for path in scope_root.rglob("*"):
        if not path.is_file():
            continue
        rel_path = relative_path(path, workspace_root)
        if should_ignore(rel_path, ignore_globs):
            continue
        if not matches_any_glob(rel_path, experiment_globs):
            continue

        suffix = path.suffix.lower()
        if suffix in STRUCTURED_EXTENSIONS:
            kind = "structured"
        elif suffix in PLOT_EXTENSIONS:
            kind = "plot"
        elif suffix in CODE_EXTENSIONS:
            kind = "code"
        else:
            continue

        index[rel_path] = {
            "path": rel_path,
            "absolute_path": str(path),
            "kind": kind,
            "suffix": suffix,
            "fingerprint": sha256_file(path),
            "size_bytes": path.stat().st_size,
        }
    return index


def _group_runs(
    workspace_root: Path,
    file_index: dict[str, dict[str, Any]],
    changed_paths: list[str],
    primary_metric: str,
) -> list[dict[str, Any]]:
    runs: dict[str, dict[str, Any]] = {}
    for rel_path, metadata in file_index.items():
        if rel_path not in changed_paths:
            continue

        parent = Path(rel_path).parent
        run_id = str(parent).replace("\\", "/") if str(parent) not in {"", "."} else "root"
        run = runs.setdefault(
            run_id,
            {
                "run_id": run_id,
                "path": run_id,
                "structured_files": [],
                "plot_files": [],
                "code_files": [],
                "metrics": {},
                "primary_metric_value": None,
            },
        )

        absolute_path = Path(metadata["absolute_path"])
        if metadata["kind"] == "structured":
            run["structured_files"].append(rel_path)
            metrics = load_structured_metrics(absolute_path)
            for key, value in metrics.items():
                run["metrics"].setdefault(key, value)
        elif metadata["kind"] == "plot":
            run["plot_files"].append(rel_path)
        else:
            run["code_files"].append(rel_path)

    for run in runs.values():
        run["primary_metric_value"] = metric_value(run["metrics"], primary_metric)

    return sorted(runs.values(), key=lambda item: item["run_id"])


def _collect_code_context(changed_paths: list[str]) -> list[str]:
    preferred = []
    for rel_path in changed_paths:
        suffix = Path(rel_path).suffix.lower()
        if suffix in {".py", ".sh", ".toml", ".json", ".yaml", ".yml", ".md"}:
            preferred.append(rel_path)
    return preferred[:20]


def _status_changed_paths(repo_root: Path) -> list[str]:
    if not is_git_repo(repo_root):
        return []
    result = git(["status", "--short"], cwd=repo_root)
    if result.returncode != 0:
        return []
    changed = []
    for line in result.stdout.splitlines():
        if len(line) < 4:
            continue
        changed.append(line[3:].strip())
    return changed


def scan_workspace(
    workspace_root: Path,
    checkpoint: dict[str, Any] | None = None,
    primary_metric: str = "",
    study_title: str | None = None,
    scope_subdir: str | None = None,
    experiment_globs: list[str] | None = None,
    ignore_globs: list[str] | None = None,
) -> dict[str, Any]:
    workspace_root = workspace_root.resolve()
    checkpoint = checkpoint or {}
    experiment_globs = experiment_globs or []
    ignore_globs = [*DEFAULT_IGNORE_GLOBS, *(ignore_globs or [])]
    scope_root = (workspace_root / scope_subdir).resolve() if scope_subdir else workspace_root

    if not scope_root.exists():
        raise SystemExit(f"Scope path does not exist: {scope_root}")

    file_index = _collect_file_index(workspace_root, scope_root, experiment_globs, ignore_globs)
    prior_fingerprints = checkpoint.get("artifact_fingerprints", {})

    current_paths = set(file_index)
    changed_paths = sorted(
        [
            rel_path
            for rel_path, metadata in file_index.items()
            if prior_fingerprints.get(rel_path) != metadata["fingerprint"]
        ]
    )
    removed_paths = sorted([path for path in prior_fingerprints if path not in current_paths])

    repo_root = workspace_root
    current_commit = ""
    previous_commit = checkpoint.get("last_commit_sha")
    if is_git_repo(repo_root):
        commit_result = git(["rev-parse", "HEAD"], cwd=repo_root)
        if commit_result.returncode == 0:
            current_commit = commit_result.stdout.strip()

    commit_paths = _status_changed_paths(repo_root)
    for rel_path in commit_paths:
        if rel_path in file_index and rel_path not in changed_paths:
            changed_paths.append(rel_path)
    changed_paths = sorted(set(changed_paths))

    changed_artifacts = [file_index[path] for path in changed_paths if path in file_index]
    run_candidates = _group_runs(workspace_root, file_index, changed_paths, primary_metric)
    changed_commits = _collect_commits(repo_root, previous_commit)

    baseline = not bool(checkpoint)
    has_delta = baseline or bool(changed_artifacts) or bool(removed_paths)
    warnings = []
    if not run_candidates:
        warnings.append("No run candidates with structured metrics were detected in the current delta.")

    summary = {
        "workspace_root": str(workspace_root),
        "study_title": study_title or workspace_root.name,
        "scope_root": str(scope_root),
        "scope_subdir": scope_subdir or "",
        "scanned_at": now_utc_iso(),
        "baseline": baseline,
        "has_delta": has_delta,
        "current_commit": current_commit,
        "previous_commit": previous_commit or "",
        "artifact_counts": {
            "structured": sum(1 for item in file_index.values() if item["kind"] == "structured"),
            "plots": sum(1 for item in file_index.values() if item["kind"] == "plot"),
            "code": sum(1 for item in file_index.values() if item["kind"] == "code"),
        },
        "artifact_fingerprints": {path: metadata["fingerprint"] for path, metadata in file_index.items()},
        "changed_artifacts": changed_artifacts,
        "removed_paths": removed_paths,
        "changed_paths": changed_paths,
        "changed_commits": changed_commits,
        "run_candidates": run_candidates,
        "code_context_paths": _collect_code_context(changed_paths),
        "warnings": warnings,
    }
    return summary


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Scan a workspace for experiment deltas")
    parser.add_argument("--workspace-root", required=True)
    parser.add_argument("--primary-metric", required=True)
    parser.add_argument("--study-title")
    parser.add_argument("--scope-subdir")
    parser.add_argument("--checkpoint")
    parser.add_argument("--output", required=True)
    parser.add_argument("--experiment-glob", action="append", default=[])
    parser.add_argument("--ignore-glob", action="append", default=[])
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    checkpoint = read_json(Path(args.checkpoint)) if args.checkpoint else {}
    payload = scan_workspace(
        workspace_root=Path(args.workspace_root),
        checkpoint=checkpoint,
        primary_metric=args.primary_metric,
        study_title=args.study_title,
        scope_subdir=args.scope_subdir,
        experiment_globs=args.experiment_glob,
        ignore_globs=args.ignore_glob,
    )
    write_json(Path(args.output), payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
