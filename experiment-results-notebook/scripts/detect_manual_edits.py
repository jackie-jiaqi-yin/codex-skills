#!/usr/bin/env python3
"""Detect and lightly polish manual notebook edits."""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

from common import (
    ENTRY_END_RE,
    ENTRY_START_RE,
    normalize_text,
    parse_marked_sections,
    read_json,
    sha256_text,
    write_json,
)


FORMAL_REPLACEMENTS = {
    "a lot of": "substantial",
    "kinda": "somewhat",
    "kind of": "",
    "sort of": "",
    "pretty good": "strong",
    "pretty bad": "weak",
    "doesn't": "does not",
    "can't": "cannot",
    "won't": "will not",
}


def _normalize_sentence(text: str) -> str:
    compact = re.sub(r"\s+", " ", text.strip())
    for source, target in FORMAL_REPLACEMENTS.items():
        compact = re.sub(rf"\b{re.escape(source)}\b", target, compact, flags=re.IGNORECASE)
    compact = re.sub(r"\s+", " ", compact).strip(" -")
    if not compact:
        return ""
    compact = compact[0].upper() + compact[1:]
    if compact[-1] not in ".!?":
        compact += "."
    return compact


def polish_markdown(text: str) -> str:
    lines = text.strip().splitlines()
    heading_lines = []
    while lines and re.match(r"^#{1,6}\s+", lines[0].strip()):
        heading_lines.append(lines.pop(0).rstrip())
    body_text = "\n".join(lines).strip()
    blocks = [block for block in re.split(r"\n\s*\n", body_text) if block.strip()]
    polished_blocks: list[str] = []
    for block in blocks:
        lines = [line.rstrip() for line in block.splitlines() if line.strip()]
        if not lines:
            continue

        if all(line.lstrip().startswith(("-", "*")) for line in lines):
            bullets = []
            for line in lines:
                body = line.lstrip()[1:].strip()
                bullets.append(f"- {_normalize_sentence(body)}")
            polished_blocks.append("\n".join(bullets))
            continue

        if any(line.lstrip().startswith(tuple(str(i) + "." for i in range(1, 10))) for line in lines):
            cleaned = []
            for line in lines:
                match = re.match(r"^(\s*\d+\.\s+)(.+)$", line)
                if match:
                    cleaned.append(f"{match.group(1)}{_normalize_sentence(match.group(2))}")
                else:
                    cleaned.append(_normalize_sentence(line))
            polished_blocks.append("\n".join(cleaned))
            continue

        polished_blocks.append(_normalize_sentence(" ".join(lines)))
    body = "\n\n".join(block for block in polished_blocks if block.strip())
    if heading_lines and body:
        return "\n".join(heading_lines) + "\n" + body
    if heading_lines:
        return "\n".join(heading_lines)
    return body


def _orphan_notes(text: str) -> list[str]:
    intervals: list[tuple[int, int]] = []
    starts = list(ENTRY_START_RE.finditer(text))
    ends = list(ENTRY_END_RE.finditer(text))
    for start in starts:
        later_ends = [item for item in ends if item.start() > start.end()]
        if later_ends:
            end = later_ends[0]
            intervals.append((start.start(), end.end()))

    notes: list[str] = []
    cursor = 0
    for start, end in intervals:
        outside = text[cursor:start].strip()
        if outside:
            notes.append(outside)
        cursor = end
    tail = text[cursor:].strip()
    if tail:
        notes.append(tail)
    return notes


def detect_manual_edits(notebook_path: Path, checkpoint: dict[str, Any]) -> dict[str, Any]:
    if not notebook_path.exists():
        return {"has_manual_edits": False, "edited_sections": [], "orphan_notes": []}

    notebook_text = notebook_path.read_text(encoding="utf-8")
    prior_hashes = checkpoint.get("section_hashes", {})
    edits = []

    for section in parse_marked_sections(notebook_text):
        prior = prior_hashes.get(section.section_id)
        if not prior:
            continue
        current_hash = sha256_text(normalize_text(section.content))
        if current_hash == prior.get("hash"):
            continue
        polished = polish_markdown(section.content)
        edits.append(
            {
                "entry_id": section.entry_id,
                "section_id": section.section_id,
                "title": section.title,
                "raw_text": section.content.strip(),
                "polished_text": polished,
                "prior_hash": prior.get("hash"),
                "current_hash": current_hash,
            }
        )

    orphan_notes = []
    for note in _orphan_notes(notebook_text):
        polished = polish_markdown(note)
        orphan_notes.append({"raw_text": note, "polished_text": polished})

    return {
        "has_manual_edits": bool(edits or orphan_notes),
        "edited_sections": edits,
        "orphan_notes": orphan_notes,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Detect manual notebook edits")
    parser.add_argument("--notebook", required=True)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--output", required=True)
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    payload = detect_manual_edits(Path(args.notebook), read_json(Path(args.checkpoint)))
    write_json(Path(args.output), payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
