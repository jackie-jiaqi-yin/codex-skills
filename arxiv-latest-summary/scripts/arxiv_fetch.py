#!/usr/bin/env python3
"""Fetch latest arXiv papers into a normalized CSV catalog.

This module is intentionally self-contained for skill isolation.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from xml.etree import ElementTree as ET

import requests


ARXIV_API = "https://export.arxiv.org/api/query"
ATOM_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
}


def _clean_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _parse_iso8601(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _entry_to_record(entry: ET.Element) -> dict[str, Any]:
    paper_id = _clean_whitespace(entry.findtext("atom:id", default="", namespaces=ATOM_NS))
    title = _clean_whitespace(entry.findtext("atom:title", default="", namespaces=ATOM_NS))
    summary = _clean_whitespace(entry.findtext("atom:summary", default="", namespaces=ATOM_NS))
    published = _clean_whitespace(entry.findtext("atom:published", default="", namespaces=ATOM_NS))
    updated = _clean_whitespace(entry.findtext("atom:updated", default="", namespaces=ATOM_NS))

    authors = [
        _clean_whitespace(a.findtext("atom:name", default="", namespaces=ATOM_NS))
        for a in entry.findall("atom:author", ATOM_NS)
    ]

    categories = [c.attrib.get("term", "") for c in entry.findall("atom:category", ATOM_NS)]

    primary = entry.find("arxiv:primary_category", ATOM_NS)
    primary_category = primary.attrib.get("term", "") if primary is not None else (categories[0] if categories else "")

    pdf_url = ""
    html_url = paper_id
    for link in entry.findall("atom:link", ATOM_NS):
        href = link.attrib.get("href", "")
        rel = link.attrib.get("rel", "")
        link_type = link.attrib.get("type", "")
        link_title = link.attrib.get("title", "")

        if rel == "alternate" and href:
            html_url = href

        if link_title == "pdf" or link_type == "application/pdf":
            pdf_url = href

    if not pdf_url and paper_id:
        pdf_url = paper_id.replace("/abs/", "/pdf/") + ".pdf"

    return {
        "id": paper_id,
        "title": title,
        "authors": ", ".join([a for a in authors if a]),
        "author_count": len([a for a in authors if a]),
        "abstract": summary,
        "published": published,
        "updated": updated,
        "primary_category": primary_category,
        "categories": ", ".join([c for c in categories if c]),
        "url": html_url,
        "pdf_url": pdf_url,
    }


def _fetch_feed_page(query: str, start: int, max_results: int, timeout_sec: int) -> ET.Element:
    params = {
        "search_query": query,
        "start": start,
        "max_results": max_results,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    }
    url = ARXIV_API + "?" + urlencode(params)
    response = requests.get(url, timeout=timeout_sec)
    response.raise_for_status()
    return ET.fromstring(response.text)


def fetch_latest_papers(
    *,
    query: str,
    window_days: int,
    max_results: int,
    timeout_sec: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    # Pull extra records to allow post-filtering by time window.
    fetch_target = min(max(max_results * 3, max_results), 2000)
    page_size = 200
    pages = int(math.ceil(fetch_target / page_size))

    all_records: list[dict[str, Any]] = []

    for page in range(pages):
        start = page * page_size
        batch = min(page_size, fetch_target - start)
        if batch <= 0:
            break

        root = _fetch_feed_page(query=query, start=start, max_results=batch, timeout_sec=timeout_sec)
        entries = root.findall("atom:entry", ATOM_NS)
        if not entries:
            break

        page_records = [_entry_to_record(entry) for entry in entries]
        all_records.extend(page_records)

        if len(entries) < batch:
            break

    if not all_records:
        return [], {"source_count": 0, "window_filtered_count": 0, "window_applied": True}

    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)

    filtered: list[dict[str, Any]] = []
    for record in all_records:
        published = record.get("published", "")
        if not published:
            continue
        try:
            published_dt = _parse_iso8601(published)
        except ValueError:
            continue

        if published_dt >= cutoff:
            filtered.append(record)

    if filtered:
        final = filtered[:max_results]
        window_applied = True
    else:
        # Fallback: return latest available entries even if outside the requested window.
        final = all_records[:max_results]
        window_applied = False

    meta = {
        "source_count": len(all_records),
        "window_filtered_count": len(filtered),
        "window_applied": window_applied,
    }
    return final, meta


def write_catalog(records: list[dict[str, Any]], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    out_csv = output_dir / "catalog.csv"

    fields = [
        "id",
        "title",
        "authors",
        "author_count",
        "abstract",
        "published",
        "updated",
        "primary_category",
        "categories",
        "url",
        "pdf_url",
    ]

    with out_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in records:
            writer.writerow(row)

    return out_csv


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fetch latest arXiv papers and write catalog.csv")
    parser.add_argument("--query", required=True, help="Validated arXiv search query string")
    parser.add_argument("--window-days", type=int, default=7, help="Lookback window in days")
    parser.add_argument("--max-results", type=int, default=66, help="Maximum papers in output catalog")
    parser.add_argument("--output-dir", required=True, help="Directory where catalog.csv is written")
    parser.add_argument("--timeout-sec", type=int, default=30, help="HTTP timeout per request")
    parser.add_argument("--metadata-output", help="Optional path for JSON metadata")
    return parser


def main() -> int:
    args = _build_parser().parse_args()

    records, meta = fetch_latest_papers(
        query=args.query,
        window_days=args.window_days,
        max_results=args.max_results,
        timeout_sec=args.timeout_sec,
    )

    if not records:
        raise SystemExit("No papers returned from arXiv. Try relaxing the query.")

    output_dir = Path(args.output_dir)
    catalog_path = write_catalog(records, output_dir)

    output_payload = {
        "query": args.query,
        "window_days": args.window_days,
        "max_results": args.max_results,
        "returned_count": len(records),
        "catalog_csv": str(catalog_path),
        "metadata": meta,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    if args.metadata_output:
        metadata_path = Path(args.metadata_output)
        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        metadata_path.write_text(json.dumps(output_payload, indent=2), encoding="utf-8")

    print(json.dumps(output_payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
