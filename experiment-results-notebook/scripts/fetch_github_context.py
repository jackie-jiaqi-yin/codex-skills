#!/usr/bin/env python3
"""Fetch public GitHub repo and PR context with local fallback."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

from common import git, now_utc_iso, parse_github_remote, read_json, write_json


GITHUB_API = "https://api.github.com"


def _has_gh_auth() -> bool:
    if shutil.which("gh") is None:
        return False
    result = subprocess.run(
        ["gh", "auth", "status", "-h", "github.com"],
        text=True,
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


def _gh_api(path: str) -> dict[str, Any] | None:
    result = subprocess.run(
        ["gh", "api", path],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    return json.loads(result.stdout)


def _http_get(path: str) -> tuple[dict[str, Any] | None, int]:
    response = requests.get(
        f"{GITHUB_API}{path}",
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "experiment-results-notebook",
        },
        timeout=20,
    )
    if response.status_code != 200:
        return None, response.status_code
    return response.json(), response.status_code


def _repo_remote(workspace_root: Path) -> tuple[str, dict[str, str] | None]:
    remote = git(["remote", "get-url", "origin"], cwd=workspace_root)
    if remote.returncode != 0:
        return "", None
    remote_url = remote.stdout.strip()
    return remote_url, parse_github_remote(remote_url)


def _parse_pr_url(url: str) -> dict[str, str] | None:
    parsed = urlparse(url)
    parts = [part for part in parsed.path.split("/") if part]
    if parsed.netloc != "github.com" or len(parts) < 4 or parts[2] != "pull":
        return None
    return {"owner": parts[0], "repo": parts[1], "number": parts[3]}


def _fetch_repo(owner: str, repo: str, allow_private: bool) -> tuple[dict[str, Any] | None, list[str]]:
    warnings: list[str] = []
    payload, status = _http_get(f"/repos/{owner}/{repo}")
    if payload:
        return payload, warnings
    if status in {401, 403, 404} and allow_private and _has_gh_auth():
        gh_payload = _gh_api(f"/repos/{owner}/{repo}")
        if gh_payload:
            return gh_payload, warnings
    warnings.append(f"GitHub repo metadata was not available for {owner}/{repo}.")
    return None, warnings


def _fetch_pr(owner: str, repo: str, number: str, allow_private: bool) -> tuple[dict[str, Any] | None, list[str]]:
    warnings: list[str] = []
    pr_payload, status = _http_get(f"/repos/{owner}/{repo}/pulls/{number}")
    files_payload, _ = _http_get(f"/repos/{owner}/{repo}/pulls/{number}/files")
    if pr_payload:
        pr_payload["files"] = files_payload or []
        return pr_payload, warnings

    if status in {401, 403, 404} and allow_private and _has_gh_auth():
        gh_pr = _gh_api(f"/repos/{owner}/{repo}/pulls/{number}")
        gh_files = _gh_api(f"/repos/{owner}/{repo}/pulls/{number}/files")
        if gh_pr:
            gh_pr["files"] = gh_files or []
            return gh_pr, warnings

    warnings.append(f"GitHub PR metadata was not available for {owner}/{repo}#{number}.")
    return None, warnings


def fetch_github_context(
    workspace_root: Path,
    scan_manifest: dict[str, Any],
    github_pr_url: str | None = None,
) -> dict[str, Any]:
    workspace_root = workspace_root.resolve()
    remote_url, repo_ref = _repo_remote(workspace_root)
    warnings: list[str] = []
    repo_payload = None
    repo_info: dict[str, Any] | None = None

    if repo_ref:
        repo_payload, repo_warnings = _fetch_repo(repo_ref["owner"], repo_ref["repo"], allow_private=True)
        warnings.extend(repo_warnings)
        repo_info = {
            "owner": repo_ref["owner"],
            "repo": repo_ref["repo"],
            "remote_url": remote_url,
            "html_url": f"https://github.com/{repo_ref['owner']}/{repo_ref['repo']}",
        }
        if repo_payload:
            repo_info.update(
                {
                    "description": repo_payload.get("description"),
                    "default_branch": repo_payload.get("default_branch"),
                    "private": bool(repo_payload.get("private")),
                    "updated_at": repo_payload.get("updated_at"),
                }
            )

    pr_info = None
    if github_pr_url:
        pr_ref = _parse_pr_url(github_pr_url)
        if pr_ref:
            pr_payload, pr_warnings = _fetch_pr(pr_ref["owner"], pr_ref["repo"], pr_ref["number"], allow_private=True)
            warnings.extend(pr_warnings)
            if pr_payload:
                pr_info = {
                    "number": pr_payload.get("number"),
                    "title": pr_payload.get("title"),
                    "state": pr_payload.get("state"),
                    "html_url": pr_payload.get("html_url") or github_pr_url,
                    "author": (pr_payload.get("user") or {}).get("login"),
                    "updated_at": pr_payload.get("updated_at"),
                    "body": pr_payload.get("body") or "",
                    "files": [
                        {
                            "filename": item.get("filename"),
                            "status": item.get("status"),
                            "additions": item.get("additions"),
                            "deletions": item.get("deletions"),
                        }
                        for item in (pr_payload.get("files") or [])[:30]
                    ],
                }
        else:
            warnings.append(f"Could not parse GitHub PR URL: {github_pr_url}")

    commits = []
    if repo_info:
        for item in scan_manifest.get("changed_commits", []):
            commits.append(
                {
                    "sha": item.get("sha"),
                    "subject": item.get("subject"),
                    "author": item.get("author"),
                    "authored_at": item.get("authored_at"),
                    "files": item.get("files", []),
                    "html_url": f"{repo_info['html_url']}/commit/{item.get('sha')}" if item.get("sha") else "",
                }
            )

    return {
        "generated_at": now_utc_iso(),
        "repo": repo_info,
        "pull_request": pr_info,
        "commits": commits,
        "warnings": warnings,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fetch GitHub repo and PR context")
    parser.add_argument("--workspace-root", required=True)
    parser.add_argument("--scan-manifest", required=True)
    parser.add_argument("--github-pr-url")
    parser.add_argument("--output", required=True)
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    payload = fetch_github_context(
        workspace_root=Path(args.workspace_root),
        scan_manifest=read_json(Path(args.scan_manifest)),
        github_pr_url=args.github_pr_url,
    )
    write_json(Path(args.output), payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
