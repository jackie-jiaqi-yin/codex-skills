#!/usr/bin/env python3
"""Build recursive summarization artifacts from catalog.csv.

This module prepares chunk-level inputs so synthesis can run in two stages:
1) summarize each chunk of abstracts
2) merge chunk summaries into final analysis.md
"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path


def _read_catalog(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return [dict(row) for row in reader]


def _parse_day(value: str) -> str:
    if not value:
        return ""
    return value[:10]


def _date_range(rows: list[dict[str, str]]) -> str:
    days = sorted([_parse_day(r.get("published", "")) for r in rows if _parse_day(r.get("published", ""))])
    if not days:
        return "N/A"
    if days[0] == days[-1]:
        return days[0]
    return f"{days[0]} to {days[-1]}"


def _chunk(rows: list[dict[str, str]], chunk_size: int) -> list[list[dict[str, str]]]:
    return [rows[idx : idx + chunk_size] for idx in range(0, len(rows), chunk_size)]


def _record_block(global_idx: int, row: dict[str, str]) -> str:
    title = (row.get("title") or "Untitled").strip()
    url = (row.get("url") or "").strip()
    published = _parse_day(row.get("published", "")) or "N/A"
    category = (row.get("primary_category") or "N/A").strip() or "N/A"
    authors = (row.get("authors") or "Unknown").strip() or "Unknown"
    abstract = (row.get("abstract") or "").replace("\n", " ").strip()

    lines = [
        f"### Paper {global_idx}",
        f"- Title: {title}",
        f"- URL: {url or 'N/A'}",
        f"- Published: {published}",
        f"- Primary Category: {category}",
        f"- Authors: {authors}",
        f"- Abstract: {abstract or 'N/A'}",
        "",
    ]
    return "\n".join(lines)


def _chunk_prompt(
    *,
    topic: str,
    chunk_index: int,
    total_chunks: int,
    start_idx: int,
    end_idx: int,
    rows: list[dict[str, str]],
) -> str:
    header = [
        f"# Recursive Chunk {chunk_index}/{total_chunks}",
        "",
        f"- Topic: {topic}",
        f"- Global paper range: {start_idx}-{end_idx}",
        f"- Papers in this chunk: {len(rows)}",
        f"- Date range in this chunk: {_date_range(rows)}",
        "",
        "## Task",
        "",
        "Summarize this chunk only. Keep it information-dense and explanatory.",
        "Do not try to summarize all papers one by one.",
        "Avoid one-line bullets; each key point should include mechanism, evidence, and implication.",
        "",
        "## Required Output Format",
        "",
        "## Key Research Themes",
        "- 3-5 themes in a numbered list (1., 2., 3., ...).",
        "- For each theme, start with `**<theme keyword>:**` and write a short paragraph (4-7 sentences).",
        "- Include representative evidence citations (title + URL).",
        "",
        "## Methodological Approaches",
        "- 3-5 approaches in a numbered list (1., 2., 3., ...).",
        "- For each approach, start with `**<approach keyword>:**` and write a paragraph (4-7 sentences) describing mechanism, strengths, and tradeoffs.",
        "- Include at least one caveat or failure mode per approach.",
        "",
        "## Notable Papers to Read First",
        "- 4-6 bullets using compact link labels.",
        "- Each bullet should be 2-4 sentences total (summary + why read first + practical caveat/use-case).",
        "",
        "## What Is New in This Window",
        "- 3-5 substantial bullets describing shifts or emerging patterns.",
        "- Each bullet should include a 'then vs now' contrast and evidence citation(s).",
        "",
        "## Challenges and Future Directions",
        "- 4-6 numbered items.",
        "- Each item should include bottleneck, evidence, and plausible near-term direction (2-4 sentences).",
        "",
        "## Chunk Concluding Overview",
        "- 2 short paragraphs (8-12 sentences total).",
        "- Include practical takeaway: what to read first and why.",
        "",
        "## Paper Data",
        "",
    ]

    blocks: list[str] = []
    for offset, row in enumerate(rows):
        blocks.append(_record_block(start_idx + offset, row))

    return "\n".join(header + blocks).rstrip() + "\n"


def _merge_instructions(topic: str, chunk_entries: list[dict[str, object]], total_papers: int) -> str:
    lines = [
        "# Recursive Merge Instructions",
        "",
        f"Topic: {topic}",
        f"Total papers: {total_papers}",
        f"Chunk summaries expected: {len(chunk_entries)}",
        "",
        "## Step 1: Summarize each chunk",
        "",
        "For each chunk input in `chunk_inputs/`, create a paired summary file in `chunk_summaries/`.",
        "Use the same index number to preserve ordering.",
        "",
        "## Step 2: Merge chunk summaries into final analysis",
        "",
        "Read all files in `chunk_summaries/` and write a consolidated `analysis.md`.",
        "The merge must deduplicate repeated points and repeated papers.",
        "Merge for depth: preserve explanatory detail from chunk summaries; do not collapse to one-liners.",
        "",
        "Use this exact final structure:",
        "",
        "## Key Research Themes",
        "## Methodological Approaches",
        "## Notable Papers to Read First",
        "## What Is New in This Window",
        "## Challenges and Future Directions",
        "## Concluding Overview",
        "",
        "Merge quality rules:",
        "- Prefer consensus patterns that appear across multiple chunks.",
        "- Keep citations concise using compact markdown labels linked to arXiv URLs.",
        "- Avoid numeric ranking formulas and paper scores.",
        "- Keep the writeup educational and readable for non-experts.",
        "- Ensure each major section has substantive prose (not just short bullets).",
        "- In `Key Research Themes` and `Methodological Approaches`, use numbered lists with bold keyword leads.",
        "- Include mechanism + evidence + implication in major claims.",
        "- For large runs (100+ papers), target a final analysis in the 1,500-3,000 word range.",
        "",
        "## Chunk Summary Targets",
        "",
    ]

    for item in chunk_entries:
        lines.append(
            f"- Chunk {item['chunk_index']}: input `{item['input_file']}` -> summary `{item['summary_file']}` "
            f"(papers {item['paper_start']}-{item['paper_end']})"
        )

    lines.append("")
    return "\n".join(lines)


def generate_recursive_pack(*, catalog_csv: Path, output_dir: Path, topic: str, chunk_size: int) -> dict[str, object]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be > 0")

    rows = _read_catalog(catalog_csv)
    chunks = _chunk(rows, chunk_size)

    output_dir.mkdir(parents=True, exist_ok=True)
    chunk_inputs_dir = output_dir / "chunk_inputs"
    chunk_summaries_dir = output_dir / "chunk_summaries"
    chunk_inputs_dir.mkdir(parents=True, exist_ok=True)
    chunk_summaries_dir.mkdir(parents=True, exist_ok=True)

    chunk_entries: list[dict[str, object]] = []

    cursor = 1
    for idx, chunk_rows in enumerate(chunks, start=1):
        input_file = chunk_inputs_dir / f"chunk_{idx:03d}.md"
        summary_file = chunk_summaries_dir / f"chunk_{idx:03d}_summary.md"
        start_idx = cursor
        end_idx = cursor + len(chunk_rows) - 1

        input_text = _chunk_prompt(
            topic=topic,
            chunk_index=idx,
            total_chunks=len(chunks),
            start_idx=start_idx,
            end_idx=end_idx,
            rows=chunk_rows,
        )
        input_file.write_text(input_text, encoding="utf-8")

        if not summary_file.exists():
            summary_file.write_text(
                "\n".join(
                    [
                        f"# Chunk {idx} Summary",
                        "",
                        "Fill this file using the paired chunk input.",
                        "",
                        "## Key Research Themes",
                        "",
                        "## Methodological Approaches",
                        "",
                        "## Notable Papers to Read First",
                        "",
                        "## What Is New in This Window",
                        "",
                        "## Challenges and Future Directions",
                        "",
                        "## Chunk Concluding Overview",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

        chunk_entries.append(
            {
                "chunk_index": idx,
                "paper_start": start_idx,
                "paper_end": end_idx,
                "paper_count": len(chunk_rows),
                "input_file": str(input_file),
                "summary_file": str(summary_file),
            }
        )
        cursor = end_idx + 1

    merge_path = output_dir / "merge_instructions.md"
    merge_path.write_text(
        _merge_instructions(topic=topic, chunk_entries=chunk_entries, total_papers=len(rows)),
        encoding="utf-8",
    )

    payload = {
        "topic": topic,
        "catalog_csv": str(catalog_csv),
        "output_dir": str(output_dir),
        "chunk_size": chunk_size,
        "total_papers": len(rows),
        "chunk_count": len(chunks),
        "chunk_inputs_dir": str(chunk_inputs_dir),
        "chunk_summaries_dir": str(chunk_summaries_dir),
        "merge_instructions": str(merge_path),
        "chunks": chunk_entries,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    manifest_path = output_dir / "recursive_manifest.json"
    manifest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    payload["recursive_manifest"] = str(manifest_path)
    return payload


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepare recursive chunk files for staged summarization")
    parser.add_argument("--catalog-csv", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--topic", required=True)
    parser.add_argument("--chunk-size", type=int, default=30)
    return parser


def main() -> int:
    args = _build_parser().parse_args()

    payload = generate_recursive_pack(
        catalog_csv=Path(args.catalog_csv),
        output_dir=Path(args.output_dir),
        topic=args.topic,
        chunk_size=args.chunk_size,
    )
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
