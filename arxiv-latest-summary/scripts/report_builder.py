#!/usr/bin/env python3
"""Compose final markdown report from catalog + Codex analysis.

This module is intentionally self-contained for skill isolation.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime
from pathlib import Path
import re


def _read_catalog(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return [dict(row) for row in reader]


def _parse_day(value: str) -> str:
    if not value:
        return ""
    # published field from arXiv is usually ISO date-time.
    return value[:10]


def _date_range(rows: list[dict[str, str]]) -> str:
    dates = sorted([_parse_day(row.get("published", "")) for row in rows if _parse_day(row.get("published", ""))])
    if not dates:
        return "N/A"
    if dates[0] == dates[-1]:
        return dates[0]
    return f"{dates[0]} to {dates[-1]}"


def _table_escape(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ").strip()


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def _build_top_table(rows: list[dict[str, str]], limit: int = 20) -> str:
    header = "| # | Title | Date | Primary Category | Link |\n|---:|---|---|---|---|\n"
    lines = []
    for idx, row in enumerate(rows[:limit], start=1):
        title = _table_escape(row.get("title", "Untitled"))
        date = _parse_day(row.get("published", "")) or "N/A"
        category = _table_escape(row.get("primary_category", "")) or "N/A"
        link = row.get("url", "")
        link_md = f"[arXiv]({link})" if link else "N/A"
        lines.append(f"| {idx} | {title} | {date} | {category} | {link_md} |")
    return header + "\n".join(lines)


def _build_appendix(rows: list[dict[str, str]], abstract_limit: int = 700) -> str:
    sections: list[str] = ["## Paper Appendix"]
    for idx, row in enumerate(rows, start=1):
        title = row.get("title", "Untitled")
        authors = row.get("authors", "Unknown")
        date = _parse_day(row.get("published", "")) or "N/A"
        category = row.get("primary_category", "N/A")
        url = row.get("url", "")
        pdf_url = row.get("pdf_url", "")
        abstract = _truncate((row.get("abstract") or "").strip(), abstract_limit)

        sections.append(f"### {idx}. {title}")
        sections.append(f"- Authors: {authors}")
        sections.append(f"- Published: {date}")
        sections.append(f"- Primary Category: {category}")
        if url:
            sections.append(f"- arXiv Page: {url}")
        if pdf_url:
            sections.append(f"- PDF: {pdf_url}")
        if abstract:
            sections.append(f"- Abstract: {abstract}")

    return "\n".join(sections)


def _analysis_has_paper_catalog_header(text: str) -> bool:
    patterns = [
        r"^##\s+\*\*Paper Catalog\*\*",
        r"^##\s+Paper Catalog",
    ]
    return any(re.search(pattern, text, flags=re.MULTILINE) for pattern in patterns)


def _short_citation_label(label: str) -> str:
    clean = label.strip()
    if len(clean) <= 20:
        return clean

    stopwords = {
        "a",
        "an",
        "and",
        "as",
        "at",
        "by",
        "for",
        "from",
        "in",
        "into",
        "is",
        "of",
        "on",
        "or",
        "the",
        "to",
        "towards",
        "via",
        "with",
        "when",
        "what",
        "how",
        "why",
    }

    def _is_acronym(token: str) -> bool:
        return bool(re.match(r"^[A-Z][A-Z0-9\-]{1,14}$", token))

    def _compact_phrase(text: str, max_words: int = 2) -> str:
        words = re.findall(r"[A-Za-z0-9\-]+", text)
        if not words:
            return ""
        significant = [w for w in words if w.lower() not in stopwords]
        generic_prefixes = {
            "analyzing",
            "benchmarking",
            "detecting",
            "evaluating",
            "improving",
            "learning",
            "measuring",
            "modeling",
            "rethinking",
            "scaling",
            "simplifying",
            "thinking",
            "understanding",
            "unmasking",
            "using",
            "with",
            "without",
            "trust",
        }
        while len(significant) >= 3 and significant[0].lower() in generic_prefixes:
            significant = significant[1:]
        chosen = significant if significant else words
        return " ".join(chosen[:max_words]).strip()

    # First token acronym, e.g., FENCE / TFL / SPQ.
    first_token = re.findall(r"[A-Za-z0-9\-]+", clean)
    if first_token and _is_acronym(first_token[0]):
        return first_token[0]

    # First parenthetical acronym.
    acronym_match = re.search(r"\(([A-Z][A-Z0-9\-]{1,12})\)", clean)
    if acronym_match:
        return acronym_match.group(1)

    # Prefer phrase before ':' and compact it.
    if ":" in clean:
        prefix = clean.split(":", 1)[0].strip()
        if prefix:
            compact_prefix = _compact_phrase(prefix, max_words=2)
            if 3 <= len(compact_prefix) <= 34:
                return compact_prefix

    # Generic compact phrase.
    compact = _compact_phrase(clean, max_words=2)
    if 3 <= len(compact) <= 34:
        return compact

    # Last resort: acronym from first significant words.
    words = re.findall(r"[A-Za-z0-9\-]+", clean)
    significant = [w for w in words if w.lower() not in stopwords]
    if len(significant) >= 2:
        acronym = "".join(w[0].upper() for w in significant[:4])
        if 2 <= len(acronym) <= 10:
            return acronym

    # Absolute fallback, but avoid ellipsis-heavy labels.
    return clean[:34].strip()


def _compact_markdown_citations(text: str) -> str:
    pattern = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")

    def _replace(match: re.Match[str]) -> str:
        label, url = match.group(1), match.group(2)
        return f"[{_short_citation_label(label)}]({url})"

    return pattern.sub(_replace, text)


def _normalize_notable_to_bullets(text: str) -> str:
    lines = text.splitlines()
    output: list[str] = []
    idx = 0
    notable_header_pattern = re.compile(r"^##\s+\*\*Notable Papers to Read First\*\*|^##\s+Notable Papers to Read First")

    while idx < len(lines):
        line = lines[idx]
        stripped = line.strip()

        if not notable_header_pattern.match(stripped):
            output.append(line)
            idx += 1
            continue

        # Keep section header.
        output.append(line)
        idx += 1

        # Capture section body until next H2 header.
        section_lines: list[str] = []
        while idx < len(lines) and not re.match(r"^##\s+", lines[idx].strip()):
            section_lines.append(lines[idx])
            idx += 1

        items: list[dict[str, object]] = []
        current: dict[str, object] | None = None
        preface: list[str] = []

        def flush_current() -> None:
            nonlocal current
            if current is not None:
                items.append(current)
                current = None

        for raw in section_lines:
            s = raw.strip()
            if not s:
                continue

            item_match = re.match(r"^\s*(?:\d+\.\s+|-\s+)(.+)$", raw)
            if item_match:
                flush_current()
                body = item_match.group(1).strip()
                current = {"head": body, "summary": "", "why": "", "extra": []}

                # Separate markdown link head from trailing text when present.
                link_head_match = re.match(r"^(\[[^\]]+\]\([^)]+\))(?:\s*[:\-–]\s*(.*))?$", body)
                if link_head_match:
                    current["head"] = link_head_match.group(1).strip()
                    trailing = (link_head_match.group(2) or "").strip()
                    if trailing:
                        current["extra"] = [trailing]
                continue

            lower = s.lower()
            if lower.startswith("one-sentence summary:"):
                if current is not None:
                    current["summary"] = s.split(":", 1)[1].strip()
                else:
                    preface.append(raw)
                continue

            if lower.startswith("why read first:"):
                if current is not None:
                    current["why"] = s.split(":", 1)[1].strip()
                else:
                    preface.append(raw)
                continue

            cleaned = re.sub(r"^\s*[-*]\s+", "", s)
            if current is not None:
                extras = current.get("extra", [])
                if isinstance(extras, list):
                    extras.append(cleaned)
                    current["extra"] = extras
            else:
                preface.append(raw)

        flush_current()

        # Preserve non-item lead-in text if present.
        if preface:
            output.extend(preface)
            output.append("")

        # One paper = one bullet. Keep details in the same bullet line.
        for item in items:
            head = str(item.get("head", "")).strip()
            summary = str(item.get("summary", "")).strip()
            why = str(item.get("why", "")).strip()
            extras = item.get("extra", [])
            extras_list = [str(x).strip() for x in extras] if isinstance(extras, list) else []

            detail_parts: list[str] = []
            if summary:
                detail_parts.append(f"One-sentence summary: {summary}")
            if why:
                detail_parts.append(f"Why read first: {why}")
            for extra in extras_list:
                if extra:
                    detail_parts.append(extra)

            if detail_parts:
                output.append(f"- {head} — {' '.join(detail_parts)}")
            else:
                output.append(f"- {head}")

        output.append("")

    return "\n".join(output).rstrip()


def _normalize_challenges_numbering(text: str) -> str:
    lines = text.splitlines()
    output: list[str] = []
    idx = 0
    challenges_header_pattern = re.compile(
        r"^##\s+\*\*Challenges and Future Directions\*\*|^##\s+Challenges and Future Directions"
    )

    while idx < len(lines):
        line = lines[idx]
        stripped = line.strip()

        if not challenges_header_pattern.match(stripped):
            output.append(line)
            idx += 1
            continue

        output.append(line)
        idx += 1

        section_lines: list[str] = []
        while idx < len(lines) and not re.match(r"^##\s+", lines[idx].strip()):
            section_lines.append(lines[idx])
            idx += 1

        items: list[dict[str, str]] = []
        current: dict[str, str] | None = None
        preface: list[str] = []

        def flush_current() -> None:
            nonlocal current
            if current is not None:
                items.append(current)
                current = None

        for raw in section_lines:
            s = raw.strip()
            if not s:
                continue

            m = re.match(r"^\s*\d+\.\s+(.+)$", raw)
            if m:
                flush_current()
                current = {"head": m.group(1).strip(), "detail": ""}
                continue

            if current is not None:
                if current["detail"]:
                    current["detail"] += " " + s
                else:
                    current["detail"] = s
            else:
                preface.append(raw)

        flush_current()

        if preface:
            output.extend(preface)
            output.append("")

        # Force canonical sequential numbering for stable rendering.
        for i, item in enumerate(items, start=1):
            head = item["head"].strip()
            detail = item["detail"].strip()
            if detail:
                output.append(f"{i}. {head} {detail}")
            else:
                output.append(f"{i}. {head}")

        output.append("")

    return "\n".join(output).rstrip()


def _normalize_heading_style(text: str) -> str:
    heading_map = {
        "Paper Catalog": "## **Paper Catalog**",
        "Key Research Themes": "## **Key Research Themes**",
        "Methodological Approaches": "## **Methodological Approaches**",
        "Notable Papers to Read First": "## **Notable Papers to Read First**",
        "What Is New in This Window": "## **What Is New in This Window**",
        "Challenges and Future Directions": "## **Challenges and Future Directions**",
        "Concluding Overview": "## **Concluding Overview**",
    }

    updated = text
    for raw, styled in heading_map.items():
        updated = re.sub(
            rf"^##\s+\*\*{re.escape(raw)}\*\*$",
            styled,
            updated,
            flags=re.MULTILINE,
        )
        updated = re.sub(
            rf"^##\s+{re.escape(raw)}$",
            styled,
            updated,
            flags=re.MULTILINE,
        )

    return updated


def build_report_markdown(
    *,
    topic: str,
    report_style: str,
    query: str,
    window_days: int,
    rows: list[dict[str, str]],
    analysis_md: str,
    include_appendix: bool,
) -> str:
    today = datetime.now().strftime("%Y-%m-%d")

    cleaned_analysis = analysis_md.strip()
    cleaned_analysis = _normalize_heading_style(cleaned_analysis)
    cleaned_analysis = _normalize_notable_to_bullets(cleaned_analysis)
    cleaned_analysis = _normalize_challenges_numbering(cleaned_analysis)
    cleaned_analysis = _compact_markdown_citations(cleaned_analysis)
    parts: list[str] = []

    if not _analysis_has_paper_catalog_header(cleaned_analysis):
        parts.append("## **Paper Catalog**")
        parts.append("")
        parts.append(f"**Date Range**: {_date_range(rows)}")
        parts.append("")
        parts.append(f"**Total Papers Analyzed**: {len(rows)}")
        parts.append("")
        parts.append("---")
        parts.append("")

    parts.append(cleaned_analysis)
    parts.append("")
    if include_appendix:
        parts.append("---")
        parts.append("")
        parts.append("## **Top Recent Papers (Quick Index)**")
        parts.append("")
        parts.append(_build_top_table(rows))
        parts.append("")
        parts.append(_build_appendix(rows))
        parts.append("")

    parts.append("---")
    parts.append("")
    parts.append("## **Run Metadata**")
    parts.append("")
    parts.append(f"- **Topic**: {topic}")
    parts.append(f"- **Generated On**: {today}")
    parts.append(f"- **Time Window**: Last {window_days} days")
    parts.append(f"- **Report Style**: {report_style}")
    parts.append(f"- **Publication Range**: {_date_range(rows)}")
    parts.append(f"- **arXiv Query**: `{query}`")
    parts.append("")

    return "\n".join(parts).rstrip() + "\n"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build report.md from catalog.csv and analysis.md")
    parser.add_argument("--catalog-csv", required=True)
    parser.add_argument("--analysis-md", required=True)
    parser.add_argument("--query", required=True)
    parser.add_argument("--topic", required=True)
    parser.add_argument("--window-days", type=int, default=7)
    parser.add_argument("--report-style", default="academic formal")
    parser.add_argument(
        "--include-appendix",
        action="store_true",
        help="Append table index and paper appendix to the report.",
    )
    parser.add_argument("--output-md", required=True)
    return parser


def main() -> int:
    args = _build_parser().parse_args()

    catalog_path = Path(args.catalog_csv)
    analysis_path = Path(args.analysis_md)
    output_path = Path(args.output_md)

    if not catalog_path.exists():
        raise SystemExit(f"Catalog not found: {catalog_path}")
    if not analysis_path.exists():
        raise SystemExit(f"Analysis markdown not found: {analysis_path}")

    rows = _read_catalog(catalog_path)
    analysis_md = analysis_path.read_text(encoding="utf-8")

    report_md = build_report_markdown(
        topic=args.topic,
        report_style=args.report_style,
        query=args.query,
        window_days=args.window_days,
        rows=rows,
        analysis_md=analysis_md,
        include_appendix=args.include_appendix,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report_md, encoding="utf-8")

    print(str(output_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
