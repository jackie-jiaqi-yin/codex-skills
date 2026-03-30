#!/usr/bin/env python3
"""Fetch GitHub repo and PR context with local auto-discovery and fallback."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlparse

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


def _http_get(path: str, params: dict[str, Any] | None = None) -> tuple[Any | None, int]:
    response = requests.get(
        f"{GITHUB_API}{path}",
        params=params,
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
    remote = git(["remote", "-v"], cwd=workspace_root)
    if remote.returncode != 0:
        return "", None

    seen_urls: set[str] = set()
    github_remotes: list[tuple[str, str, dict[str, str]]] = []
    for line in remote.stdout.splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        name, remote_url = parts[0], parts[1]
        if remote_url in seen_urls:
            continue
        seen_urls.add(remote_url)
        repo_ref = parse_github_remote(remote_url)
        if repo_ref:
            github_remotes.append((name, remote_url, repo_ref))

    if not github_remotes:
        return "", None

    for name, remote_url, repo_ref in github_remotes:
        if name == "origin":
            return remote_url, repo_ref
    _, remote_url, repo_ref = github_remotes[0]
    return remote_url, repo_ref


def _current_branch(workspace_root: Path) -> str:
    branch = git(["branch", "--show-current"], cwd=workspace_root)
    if branch.returncode != 0:
        return ""
    return branch.stdout.strip()


def _parse_pr_url(url: str) -> dict[str, str] | None:
    parsed = urlparse(url)
    parts = [part for part in parsed.path.split("/") if part]
    if parsed.netloc != "github.com" or len(parts) < 4 or parts[2] != "pull":
        return None
    return {"owner": parts[0], "repo": parts[1], "number": parts[3]}


def _fetch_repo(owner: str, repo: str, allow_private: bool) -> tuple[dict[str, Any] | None, list[str]]:
    warnings: list[str] = []
    payload, status = _http_get(f"/repos/{owner}/{repo}")
    if payload is not None:
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
    if pr_payload is not None:
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


def _gh_api_with_params(path: str, params: dict[str, Any] | None = None) -> Any | None:
    query = urlencode(params or {}, doseq=True)
    query_path = f"{path}?{query}" if query else path
    return _gh_api(query_path)


def _fetch_pr_list(
    owner: str,
    repo: str,
    allow_private: bool,
    *,
    branch: str | None = None,
    state: str = "open",
    limit: int = 20,
) -> tuple[list[dict[str, Any]] | None, list[str]]:
    warnings: list[str] = []
    params: dict[str, Any] = {"state": state, "per_page": str(limit)}
    if branch:
        params["head"] = f"{owner}:{branch}"

    payload, status = _http_get(f"/repos/{owner}/{repo}/pulls", params=params)
    if payload is not None:
        return payload, warnings

    if status in {401, 403, 404} and allow_private and _has_gh_auth():
        gh_payload = _gh_api_with_params(f"/repos/{owner}/{repo}/pulls", params=params)
        if isinstance(gh_payload, list):
            return gh_payload, warnings

    scope = f" for branch `{branch}`" if branch else ""
    warnings.append(f"GitHub PR list was not available for {owner}/{repo}{scope}.")
    return None, warnings


def _pr_summary(pr_payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "number": pr_payload.get("number"),
        "title": pr_payload.get("title"),
        "state": pr_payload.get("state"),
        "html_url": pr_payload.get("html_url"),
        "author": (pr_payload.get("user") or {}).get("login"),
        "updated_at": pr_payload.get("updated_at"),
        "head_ref": pr_payload.get("head", {}).get("ref"),
        "base_ref": pr_payload.get("base", {}).get("ref"),
        "draft": bool(pr_payload.get("draft")),
    }


def fetch_github_context(
    workspace_root: Path,
    scan_manifest: dict[str, Any],
    github_pr_url: str | None = None,
) -> dict[str, Any]:
    workspace_root = workspace_root.resolve()
    remote_url, repo_ref = _repo_remote(workspace_root)
    current_branch = _current_branch(workspace_root)
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
            "current_branch": current_branch,
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

    if not repo_ref:
        warnings.append("Could not resolve a GitHub repo from local git remotes; continuing with local-only context.")

    pr_info = None
    open_prs: list[dict[str, Any]] = []
    closed_prs: list[dict[str, Any]] = []
    resolution = {
        "requested_pr_url": github_pr_url or "",
        "current_branch": current_branch,
        "source": "none",
        "notes": [],
    }
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
                    "head_ref": pr_payload.get("head", {}).get("ref"),
                    "base_ref": pr_payload.get("base", {}).get("ref"),
                    "draft": bool(pr_payload.get("draft")),
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
                resolution["source"] = "explicit"
                resolution["notes"].append("Used the user-provided GitHub PR URL.")
        else:
            warnings.append(f"Could not parse GitHub PR URL: {github_pr_url}")
    if repo_info and not github_pr_url:
        branch_pr_payloads, pr_warnings = _fetch_pr_list(
            repo_info["owner"],
            repo_info["repo"],
            allow_private=True,
            branch=current_branch or None,
            state="all",
            limit=10,
        )
        warnings.extend(pr_warnings)
        if branch_pr_payloads:
            chosen_pr_number = str(branch_pr_payloads[0].get("number"))
            pr_payload, chosen_warnings = _fetch_pr(
                repo_info["owner"],
                repo_info["repo"],
                chosen_pr_number,
                allow_private=True,
            )
            warnings.extend(chosen_warnings)
            if pr_payload:
                pr_info = {
                    "number": pr_payload.get("number"),
                    "title": pr_payload.get("title"),
                    "state": pr_payload.get("state"),
                    "html_url": pr_payload.get("html_url"),
                    "author": (pr_payload.get("user") or {}).get("login"),
                    "updated_at": pr_payload.get("updated_at"),
                    "body": pr_payload.get("body") or "",
                    "head_ref": pr_payload.get("head", {}).get("ref"),
                    "base_ref": pr_payload.get("base", {}).get("ref"),
                    "draft": bool(pr_payload.get("draft")),
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
                resolution["source"] = "current_branch"
                resolution["notes"].append("Auto-resolved the PR that matches the current local branch.")

    if repo_info:
        open_pr_payloads, pr_list_warnings = _fetch_pr_list(
            repo_info["owner"],
            repo_info["repo"],
            allow_private=True,
            limit=20,
        )
        warnings.extend(pr_list_warnings)
        if open_pr_payloads:
            open_prs = [_pr_summary(item) for item in open_pr_payloads[:20]]
            if not pr_info:
                resolution["notes"].append(
                    f"No branch-matched PR was resolved automatically; found {len(open_prs)} open PR(s) in the repo."
                )
        elif not pr_info:
            resolution["notes"].append("No open PR was discovered for the repo.")

        closed_pr_payloads, closed_pr_warnings = _fetch_pr_list(
            repo_info["owner"],
            repo_info["repo"],
            allow_private=True,
            state="closed",
            limit=20,
        )
        warnings.extend(closed_pr_warnings)
        if closed_pr_payloads:
            closed_prs = [_pr_summary(item) for item in closed_pr_payloads[:20]]
            resolution["notes"].append(f"Collected {len(closed_prs)} recent closed PR(s) for historical context.")
        else:
            resolution["notes"].append("No recent closed PRs were discovered for the repo.")

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
        "open_pull_requests": open_prs,
        "closed_pull_requests": closed_prs,
        "resolution": resolution,
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
