#!/usr/bin/env python3
"""Build arXiv search queries from plain-language interests.

This module is intentionally self-contained for skill isolation.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


DEFAULT_WINDOW_DAYS = 7
DEFAULT_MAX_RESULTS = 66

STOPWORDS = {
    "paper",
    "papers",
    "research",
    "latest",
    "recent",
    "study",
    "studies",
    "topic",
    "about",
    "on",
    "for",
    "the",
    "a",
    "an",
    "and",
    "or",
}

CATEGORY_RULES = [
    (("ai", "artificial intelligence"), ["cs.AI"]),
    (("llm", "large language model", "language model", "prompt", "rag", "retrieval"), ["cs.CL", "cs.AI"]),
    (("nlp", "text generation", "summarization", "translation"), ["cs.CL"]),
    (("machine learning", "deep learning", "representation learning", "foundation model"), ["cs.LG", "stat.ML"]),
    (("reinforcement learning", "policy optimization"), ["cs.LG", "cs.AI"]),
    (("vision", "image", "video", "multimodal", "vision-language", "vla"), ["cs.CV", "cs.AI"]),
    (("robot", "robotics", "embodied", "agentic"), ["cs.RO", "cs.AI"]),
    (("security", "privacy", "adversarial", "cyber"), ["cs.CR"]),
    (("recommendation", "retrieval", "search", "ranking"), ["cs.IR"]),
    (("database", "data management", "query optimization"), ["cs.DB"]),
    (("distributed", "systems", "serving", "inference optimization", "latency"), ["cs.DC", "cs.SE"]),
    (("quantum", "quantum computing", "quantum information"), ["quant-ph"]),
    (("finance", "trading", "portfolio", "market"), ["q-fin.TR", "q-fin.ST"]),
    (("biology", "genomics", "protein", "drug discovery", "bioinformatics"), ["q-bio.QM", "q-bio.GN"]),
    (("math optimization", "convex optimization", "optimization theory"), ["math.OC"]),
]

SYNONYM_HINTS = {
    "llm": ["large language model", "language model", "instruction tuning", "reasoning model"],
    "rag": ["retrieval augmented generation", "retrieval-augmented generation"],
    "agent": ["ai agent", "agentic workflow", "tool use"],
    "multimodal": ["vision language", "text image", "audio language"],
    "safety": ["alignment", "robustness", "hallucination"],
    "benchmark": ["benchmark protocol", "leaderboard"],
}


@dataclass
class QueryBuildResult:
    interest: str
    query: str
    strictness: str
    window_days: int
    max_results: int
    categories: list[str]
    keywords: list[str]
    notes: list[str]


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip()).lower()


def _dedupe_keep_order(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _extract_quoted_phrases(text: str) -> list[str]:
    return _dedupe_keep_order([_norm(match) for match in re.findall(r'"([^"]+)"', text)])


def _split_interest_phrases(text: str) -> list[str]:
    text_wo_quotes = re.sub(r'"[^"]+"', " ", text)
    parts = re.split(r",|;|/|\band\b|\bor\b|\+", text_wo_quotes, flags=re.IGNORECASE)
    cleaned: list[str] = []
    for part in parts:
        normalized = _norm(part)
        if not normalized:
            continue
        tokens = [tok for tok in re.split(r"[^a-z0-9\-]+", normalized) if tok]
        if not tokens:
            continue
        filtered = [tok for tok in tokens if tok not in STOPWORDS]
        phrase = " ".join(filtered).strip()
        if phrase:
            cleaned.append(phrase)
    return _dedupe_keep_order(cleaned)


def _infer_categories(interest: str, include_categories: list[str], exclude_categories: list[str]) -> list[str]:
    interest_norm = _norm(interest)
    padded = f" {interest_norm} "
    inferred: list[str] = []

    for triggers, categories in CATEGORY_RULES:
        matched = False
        for trigger in triggers:
            trigger_norm = _norm(trigger)
            if len(trigger_norm) <= 3:
                if f" {trigger_norm} " in padded:
                    matched = True
                    break
            elif trigger_norm in interest_norm:
                matched = True
                break
        if matched:
            inferred.extend(categories)

    inferred.extend(include_categories)
    inferred = _dedupe_keep_order(inferred)

    if exclude_categories:
        exclude = set(exclude_categories)
        inferred = [cat for cat in inferred if cat not in exclude]

    return inferred


def _expand_keywords(base_keywords: list[str]) -> list[str]:
    expanded = list(base_keywords)
    text = " ".join(base_keywords)
    for key, values in SYNONYM_HINTS.items():
        if key in text:
            expanded.extend(values)
    return _dedupe_keep_order(expanded)


def _recall_expand_keywords(base_keywords: list[str]) -> list[str]:
    expanded: list[str] = []
    for phrase in base_keywords:
        phrase_norm = _norm(phrase)
        tokens = [tok for tok in re.split(r"[^a-z0-9]+", phrase_norm) if tok and tok not in STOPWORDS]
        if not tokens:
            continue

        expanded.append(phrase_norm)

        # For long phrases, add shorter variants to avoid over-constraining the query.
        if len(tokens) >= 3:
            expanded.append(" ".join(tokens[:2]))
            expanded.append(" ".join(tokens[-2:]))
        if len(tokens) >= 4:
            expanded.append(" ".join(tokens[:3]))

        # Add high-signal single tokens.
        for tok in tokens:
            if len(tok) >= 4 or tok in {"ai", "llm", "rag"}:
                expanded.append(tok)

    return _dedupe_keep_order(expanded)


def _single_keyword_clause(keyword: str) -> str:
    escaped = keyword.replace('"', "")
    return f'(ti:"{escaped}" OR abs:"{escaped}")'


def _build_keyword_clause(keywords: list[str], strictness: str) -> str:
    if not keywords:
        return ""

    if strictness == "broad":
        selected = keywords[:12]
        return "(" + " OR ".join(_single_keyword_clause(kw) for kw in selected) + ")"

    if strictness == "focused" and len(keywords) >= 2:
        required = keywords[:2]
        optional = keywords[2:6]
        required_clause = " AND ".join(_single_keyword_clause(kw) for kw in required)
        if optional:
            optional_clause = " OR ".join(_single_keyword_clause(kw) for kw in optional)
            return f"(({required_clause}) AND ({optional_clause}))"
        return f"({required_clause})"

    selected = keywords[:8]
    return "(" + " OR ".join(_single_keyword_clause(kw) for kw in selected) + ")"


def _build_category_clause(categories: list[str]) -> str:
    if not categories:
        return ""
    return "(" + " OR ".join(f"cat:{category}" for category in categories) + ")"


def _is_balanced_parentheses(text: str) -> bool:
    depth = 0
    for char in text:
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth < 0:
                return False
    return depth == 0


def validate_query_syntax(query: str) -> tuple[bool, str]:
    if not query or not query.strip():
        return False, "Query is empty."
    if not _is_balanced_parentheses(query):
        return False, "Query has unbalanced parentheses."
    return True, "ok"


def build_query(
    *,
    interest: str,
    strictness: str,
    window_days: int,
    max_results: int,
    manual_query: str | None,
    include_categories: list[str],
    exclude_categories: list[str],
) -> QueryBuildResult:
    if manual_query:
        ok, reason = validate_query_syntax(manual_query)
        if not ok:
            raise ValueError(f"Manual query invalid: {reason}")
        return QueryBuildResult(
            interest=interest,
            query=manual_query,
            strictness=strictness,
            window_days=window_days,
            max_results=max_results,
            categories=include_categories,
            keywords=[],
            notes=["Used user-provided query without modification."],
        )

    quoted = _extract_quoted_phrases(interest)
    split_phrases = _split_interest_phrases(interest)
    keywords = _dedupe_keep_order(quoted + split_phrases)

    if not keywords:
        keywords = [_norm(interest)]

    keywords = _recall_expand_keywords(keywords)
    keywords = _expand_keywords(keywords)
    categories = _infer_categories(interest, include_categories, exclude_categories)

    keyword_clause = _build_keyword_clause(keywords, strictness)
    category_clause = _build_category_clause(categories)

    if category_clause and keyword_clause:
        query = f"{category_clause} AND {keyword_clause}"
    elif keyword_clause:
        query = keyword_clause
    elif category_clause:
        query = category_clause
    else:
        # Should not happen because interest text is required.
        query = f'(all:"{_norm(interest)}")'

    ok, reason = validate_query_syntax(query)
    if not ok:
        raise ValueError(f"Generated query invalid: {reason}")

    notes: list[str] = []
    if categories:
        notes.append("Included inferred category constraints.")
    else:
        notes.append("No category constraints inferred; using keyword-only query.")

    return QueryBuildResult(
        interest=interest,
        query=query,
        strictness=strictness,
        window_days=window_days,
        max_results=max_results,
        categories=categories,
        keywords=keywords,
        notes=notes,
    )


def _parse_csv_list(value: str | None) -> list[str]:
    if not value:
        return []
    parts = [item.strip() for item in value.split(",")]
    return _dedupe_keep_order([item for item in parts if item])


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate an arXiv query from user interests.")
    parser.add_argument("--interest", required=True, help="Plain-language research interest.")
    parser.add_argument("--query", help="Optional manual arXiv query override.")
    parser.add_argument(
        "--strictness",
        default="normal",
        choices=["broad", "normal", "focused"],
        help="How tightly to constrain the keyword query.",
    )
    parser.add_argument("--include-categories", help="Comma-separated categories to force include.")
    parser.add_argument("--exclude-categories", help="Comma-separated categories to exclude.")
    parser.add_argument("--window-days", type=int, default=DEFAULT_WINDOW_DAYS)
    parser.add_argument("--max-results", type=int, default=DEFAULT_MAX_RESULTS)
    parser.add_argument("--output", help="Optional path to write JSON output.")
    parser.add_argument(
        "--plain-output",
        action="store_true",
        help="Print only the query string to stdout.",
    )
    return parser


def main() -> int:
    args = _build_arg_parser().parse_args()

    include_categories = _parse_csv_list(args.include_categories)
    exclude_categories = _parse_csv_list(args.exclude_categories)

    result = build_query(
        interest=args.interest,
        strictness=args.strictness,
        window_days=args.window_days,
        max_results=args.max_results,
        manual_query=args.query,
        include_categories=include_categories,
        exclude_categories=exclude_categories,
    )

    payload = asdict(result)

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    if args.plain_output:
        print(result.query)
    else:
        print(json.dumps(payload, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
