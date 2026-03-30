#!/usr/bin/env python3

from __future__ import annotations

import argparse
import base64
import html
import io
import re
import textwrap
from pathlib import Path
from string import Template

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd

from common import read_json
from load_data import load_dataset


PALETTE = ["#A4452A", "#355C7D", "#7AA59B", "#E6B89C", "#5C3D2E", "#D97D54", "#457B6E"]
GRID_COLOR = "#d5c6b8"
TEXT_COLOR = "#1f1a17"
MUTED = "#6b625c"


def _inline_markup(text: str) -> str:
    escaped = html.escape(text)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    return escaped


def markdown_to_html(markdown_text: str) -> str:
    parts = ['<div class="narrative-body">']
    in_list = False
    for raw_line in markdown_text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            if in_list:
                parts.append("</ul>")
                in_list = False
            continue
        if stripped.startswith("### "):
            if in_list:
                parts.append("</ul>")
                in_list = False
            parts.append(f"<h3>{_inline_markup(stripped[4:])}</h3>")
            continue
        if stripped.startswith("## "):
            if in_list:
                parts.append("</ul>")
                in_list = False
            parts.append(f"<h2>{_inline_markup(stripped[3:])}</h2>")
            continue
        if stripped.startswith("# "):
            if in_list:
                parts.append("</ul>")
                in_list = False
            parts.append(f"<h1>{_inline_markup(stripped[2:])}</h1>")
            continue
        if stripped.startswith("- "):
            if not in_list:
                parts.append("<ul>")
                in_list = True
            parts.append(f"<li>{_inline_markup(stripped[2:])}</li>")
            continue
        if in_list:
            parts.append("</ul>")
            in_list = False
        parts.append(f"<p>{_inline_markup(stripped)}</p>")
    if in_list:
        parts.append("</ul>")
    parts.append("</div>")
    return "\n".join(parts)


def _figure_to_data_uri(fig) -> str:
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=180, bbox_inches="tight", facecolor="#fffaf2")
    plt.close(fig)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _style_axes(ax) -> None:
    ax.set_facecolor("#fffaf2")
    ax.grid(True, axis="x", color=GRID_COLOR, alpha=0.75, linewidth=0.8)
    ax.grid(False, axis="y")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(GRID_COLOR)
    ax.spines["bottom"].set_color(GRID_COLOR)
    ax.tick_params(colors=TEXT_COLOR, labelsize=9)
    ax.title.set_color(TEXT_COLOR)


def _short_label(text: str, width: int = 36) -> str:
    return textwrap.shorten(str(text), width=width, placeholder="…")


def _make_role_bar(overview: dict) -> str | None:
    counts = overview.get("role_counts", {})
    if not counts:
        return None
    total = sum(counts.values())
    items = sorted(counts.items(), key=lambda item: item[1], reverse=True)
    labels = [item[0] for item in items][::-1]
    values = [item[1] for item in items][::-1]
    fig, ax = plt.subplots(figsize=(4.4, max(1.9, 0.45 * len(labels) + 0.9)))
    bars = ax.barh(labels, values, color=PALETTE[: len(labels)][::-1])
    ax.set_xlabel("Columns")
    ax.set_title("Variable role balance", loc="left", fontsize=12, fontweight="bold")
    _style_axes(ax)
    ax.grid(True, axis="x", color=GRID_COLOR, alpha=0.75, linewidth=0.8)
    ax.grid(False, axis="y")
    for bar, value in zip(bars, values):
        share = value / total if total else 0.0
        ax.text(
            value + 0.4,
            bar.get_y() + bar.get_height() / 2,
            f"{value} ({share:.1%})",
            va="center",
            fontsize=8.3,
            color=TEXT_COLOR,
        )
    fig.tight_layout()
    return _figure_to_data_uri(fig)


def _make_missingness_bar(missingness: dict) -> str | None:
    rows = [row for row in missingness.get("column_missing", []) if row["missing_rate"] > 0][:12]
    if not rows:
        return None
    labels = [_short_label(row["column"], 30) for row in rows][::-1]
    values = [row["missing_rate"] * 100 for row in rows][::-1]
    height = max(3.4, 0.45 * len(rows) + 1.4)
    fig, ax = plt.subplots(figsize=(7.4, height))
    bars = ax.barh(labels, values, color="#A4452A")
    ax.set_xlabel("Missing rate (%)")
    ax.set_title("Columns with the most missingness", loc="left", fontsize=12, fontweight="bold")
    _style_axes(ax)
    for bar, value in zip(bars, values):
        ax.text(value + 0.6, bar.get_y() + bar.get_height() / 2, f"{value:.1f}%", va="center", fontsize=8.5, color=TEXT_COLOR)
    fig.tight_layout()
    return _figure_to_data_uri(fig)


def _make_missingness_pairs(missingness: dict) -> str | None:
    rows = missingness.get("co_missing_pairs", [])[:10]
    if not rows:
        return None
    labels = [_short_label(f"{row['left']} × {row['right']}", 42) for row in rows][::-1]
    values = [row["joint_missing_rate"] * 100 for row in rows][::-1]
    overlaps = [row["jaccard_missingness"] for row in rows][::-1]
    height = max(3.6, 0.48 * len(rows) + 1.4)
    fig, ax = plt.subplots(figsize=(7.6, height))
    bars = ax.barh(labels, values, color="#355C7D")
    ax.set_xlabel("Rows where both columns are missing (%)")
    ax.set_title("Co-missing column pairs", loc="left", fontsize=12, fontweight="bold")
    _style_axes(ax)
    for bar, value, overlap in zip(bars, values, overlaps):
        ax.text(
            value + 0.6,
            bar.get_y() + bar.get_height() / 2,
            f"{value:.1f}% | overlap {overlap:.2f}",
            va="center",
            fontsize=8.3,
            color=TEXT_COLOR,
        )
    fig.tight_layout()
    return _figure_to_data_uri(fig)


def _make_numeric_correlation_bar(associations: dict) -> str | None:
    rows = associations.get("numeric_numeric", {}).get("top_pairs", [])[:12]
    if not rows:
        return None
    labels = [_short_label(f"{row['left']} × {row['right']}", 42) for row in rows][::-1]
    values = [row["correlation"] for row in rows][::-1]
    colors = ["#355C7D" if value < 0 else "#A4452A" for value in values]
    height = max(3.6, 0.48 * len(rows) + 1.4)
    fig, ax = plt.subplots(figsize=(7.6, height))
    bars = ax.barh(labels, values, color=colors)
    ax.axvline(0, color=GRID_COLOR, linewidth=1.0)
    ax.set_xlabel("Pearson correlation")
    ax.set_xlim(-1.05, 1.05)
    ax.set_title("Strongest numeric correlations", loc="left", fontsize=12, fontweight="bold")
    _style_axes(ax)
    for bar, value in zip(bars, values):
        anchor = value + 0.03 if value >= 0 else value - 0.03
        align = "left" if value >= 0 else "right"
        ax.text(anchor, bar.get_y() + bar.get_height() / 2, f"{value:+.2f}", va="center", ha=align, fontsize=8.5, color=TEXT_COLOR)
    fig.tight_layout()
    return _figure_to_data_uri(fig)


def _make_numeric_correlation_heatmap(associations: dict) -> str | None:
    pearson = associations.get("numeric_numeric", {}).get("pearson", {})
    top_pairs = associations.get("numeric_numeric", {}).get("top_pairs", [])
    dense_pairs = [row for row in top_pairs if row["abs_correlation"] >= 0.75]
    if len(dense_pairs) < 6:
        return None
    selected = []
    for row in dense_pairs:
        for feature in (row["left"], row["right"]):
            if feature not in selected:
                selected.append(feature)
    selected = selected[:10]
    columns = pearson.get("columns", [])
    matrix = pearson.get("matrix", [])
    if not columns or not matrix or len(selected) < 3:
        return None
    frame = pd.DataFrame(matrix, index=columns, columns=columns)
    available = [column for column in selected if column in frame.index]
    if len(available) < 3:
        return None
    sub = frame.loc[available, available]
    fig_size = max(4.4, 0.72 * len(available) + 1.6)
    fig, ax = plt.subplots(figsize=(fig_size, fig_size))
    image = ax.imshow(sub.values, cmap="coolwarm", vmin=-1, vmax=1)
    ax.set_xticks(range(len(available)))
    ax.set_yticks(range(len(available)))
    ax.set_xticklabels([_short_label(name, 14) for name in available], rotation=35, ha="right")
    ax.set_yticklabels([_short_label(name, 16) for name in available])
    ax.set_title("High-correlation feature map", loc="left", fontsize=12, fontweight="bold")
    ax.tick_params(colors=TEXT_COLOR, labelsize=8.4)
    for spine in ax.spines.values():
        spine.set_edgecolor(GRID_COLOR)
    for row_index in range(len(available)):
        for column_index in range(len(available)):
            ax.text(
                column_index,
                row_index,
                f"{sub.values[row_index, column_index]:.2f}",
                ha="center",
                va="center",
                fontsize=7.3,
                color=TEXT_COLOR,
            )
    colorbar = fig.colorbar(image, ax=ax, fraction=0.045, pad=0.03)
    colorbar.ax.tick_params(labelsize=8, colors=TEXT_COLOR)
    colorbar.outline.set_edgecolor(GRID_COLOR)
    fig.tight_layout()
    return _figure_to_data_uri(fig)


def _make_categorical_association_bar(associations: dict) -> str | None:
    rows = associations.get("categorical_categorical", {}).get("top_pairs", [])[:10]
    if not rows:
        return None
    labels = [_short_label(f"{row['left']} × {row['right']}", 42) for row in rows][::-1]
    values = [row["score"] for row in rows][::-1]
    height = max(3.6, 0.48 * len(rows) + 1.4)
    fig, ax = plt.subplots(figsize=(7.6, height))
    bars = ax.barh(labels, values, color="#7AA59B")
    ax.set_xlabel("Cramer's V")
    ax.set_xlim(0, max(values) * 1.15 if values else 1.0)
    ax.set_title("Strongest categorical associations", loc="left", fontsize=12, fontweight="bold")
    _style_axes(ax)
    for bar, value in zip(bars, values):
        ax.text(value + 0.01, bar.get_y() + bar.get_height() / 2, f"{value:.2f}", va="center", fontsize=8.5, color=TEXT_COLOR)
    fig.tight_layout()
    return _figure_to_data_uri(fig)


def _make_feature_strength_bar(target_analysis: dict, target: str) -> str | None:
    payload = target_analysis.get(target, {})
    rows = payload.get("top_features", [])[:12]
    if not rows:
        return None
    labels = [_short_label(row["feature"], 36) for row in rows][::-1]
    values = [row["score"] for row in rows][::-1]
    height = max(3.8, 0.5 * len(rows) + 1.4)
    fig, ax = plt.subplots(figsize=(7.8, height))
    bars = ax.barh(labels, values, color="#5C3D2E")
    ax.set_xlabel("Association score")
    ax.set_xlim(0, max(values) * 1.12 if values else 1.0)
    ax.set_title(f"Top associations for target '{target}'", loc="left", fontsize=12, fontweight="bold")
    _style_axes(ax)
    for bar, value in zip(bars, values):
        ax.text(value + 0.01, bar.get_y() + bar.get_height() / 2, f"{value:.2f}", va="center", fontsize=8.5, color=TEXT_COLOR)
    fig.tight_layout()
    return _figure_to_data_uri(fig)


def _bucket_other(series: pd.Series, top_n: int = 10) -> pd.Series:
    labels = series.astype(str).fillna("Missing")
    counts = labels.value_counts()
    top_labels = set(counts.head(top_n).index)
    return labels.map(lambda value: value if value in top_labels else "Other")


def _make_distribution_chart(df: pd.DataFrame, column_profiles: dict, column: str) -> str | None:
    profile = column_profiles.get(column)
    if not profile:
        return None
    role = profile["role"]
    series = df[column]

    if role == "numeric":
        clean = pd.to_numeric(series, errors="coerce").dropna()
        if clean.empty:
            return None
        if len(clean) > 5000:
            clean = clean.sample(5000, random_state=7)
        fig, ax = plt.subplots(figsize=(7.0, 3.6))
        ax.hist(clean, bins=28, color="#A4452A", edgecolor="#fffaf2", alpha=0.9)
        ax.axvline(clean.mean(), color="#355C7D", linestyle="--", linewidth=1.6, label=f"mean {clean.mean():.1f}")
        ax.axvline(clean.median(), color="#7AA59B", linestyle="-.", linewidth=1.6, label=f"median {clean.median():.1f}")
        ax.set_title(f"Distribution of '{column}'", loc="left", fontsize=12, fontweight="bold")
        ax.set_xlabel(column)
        ax.set_ylabel("Rows")
        _style_axes(ax)
        ax.legend(frameon=False, fontsize=8, loc="upper right")
        fig.tight_layout()
        return _figure_to_data_uri(fig)

    if role in {"categorical", "boolean"}:
        bucketed = _bucket_other(series, top_n=8)
        counts = bucketed.value_counts().head(9)
        labels = [_short_label(label, 24) for label in counts.index.tolist()][::-1]
        values = counts.values.tolist()[::-1]
        height = max(3.2, 0.42 * len(values) + 1.2)
        fig, ax = plt.subplots(figsize=(7.0, height))
        bars = ax.barh(labels, values, color="#355C7D")
        ax.set_title(f"Distribution of '{column}'", loc="left", fontsize=12, fontweight="bold")
        ax.set_xlabel("Rows")
        _style_axes(ax)
        for bar, value in zip(bars, values):
            ax.text(value + max(values) * 0.01, bar.get_y() + bar.get_height() / 2, str(value), va="center", fontsize=8.5, color=TEXT_COLOR)
        fig.tight_layout()
        return _figure_to_data_uri(fig)

    if role == "datetime":
        clean = pd.to_datetime(series, errors="coerce").dropna()
        if clean.empty:
            return None
        monthly = clean.dt.to_period("M").astype(str).value_counts().sort_index()
        fig, ax = plt.subplots(figsize=(7.0, 3.6))
        ax.plot(monthly.index.tolist(), monthly.values.tolist(), color="#7AA59B", linewidth=1.8)
        ax.set_title(f"Distribution of '{column}' over time", loc="left", fontsize=12, fontweight="bold")
        ax.set_ylabel("Rows")
        ax.tick_params(axis="x", rotation=45)
        _style_axes(ax)
        fig.tight_layout()
        return _figure_to_data_uri(fig)

    return None


def _render_chart_explanation(chart: dict) -> str:
    paragraph = (
        f"<p class='chart-context'><strong>Why:</strong> {html.escape(chart['why_selected'])} "
        f"<strong>Read:</strong> {html.escape(chart['how_to_read'])} "
        f"<strong>Caution:</strong> {html.escape(chart['watch_out_for'])}</p>"
    )
    if chart.get("term_note"):
        paragraph += f"<p class='chart-term-note'>Term note: {html.escape(chart['term_note'])}</p>"
    return paragraph


def _make_chart_image(chart: dict, overview: dict, missingness: dict, associations: dict, target_analysis: dict, analysis_df: pd.DataFrame, column_profiles: dict) -> str | None:
    kind = chart["kind"]
    if kind == "role-bar":
        return _make_role_bar(overview)
    if kind == "missingness-bar":
        return _make_missingness_bar(missingness)
    if kind == "missingness-pairs":
        return _make_missingness_pairs(missingness)
    if kind == "numeric-correlation-bar":
        return _make_numeric_correlation_bar(associations)
    if kind == "numeric-correlation-heatmap":
        return _make_numeric_correlation_heatmap(associations)
    if kind == "categorical-association-bar":
        return _make_categorical_association_bar(associations)
    if kind == "feature-strength-bar":
        return _make_feature_strength_bar(target_analysis, chart["target"])
    if kind == "distribution":
        return _make_distribution_chart(analysis_df, column_profiles, chart["column"])
    return None


def render_report(run_dir: str | Path, output_path: str | Path | None = None) -> Path:
    run_dir = Path(run_dir).resolve()
    skill_dir = Path(__file__).resolve().parent.parent
    template = Template((skill_dir / "assets" / "report_template.html").read_text())
    css = (skill_dir / "assets" / "report_style.css").read_text()

    manifest = read_json(run_dir / "run_manifest.json")
    overview = read_json(run_dir / "profile_overview.json")
    column_profiles = read_json(run_dir / "column_profiles.json")
    missingness = read_json(run_dir / "missingness.json")
    associations = read_json(run_dir / "associations.json")
    target_analysis = read_json(run_dir / "target_analysis.json")
    chart_manifest = read_json(run_dir / "chart_manifest.json")

    analysis_path = run_dir / "analysis.md"
    brief_path = run_dir / "analysis_brief.md"
    analysis_text = analysis_path.read_text().strip() if analysis_path.exists() else ""
    if not analysis_text:
        analysis_text = brief_path.read_text()

    df, _ = load_dataset(manifest["input_path"], sheet_name=manifest.get("sheet_name"))
    excluded = set(manifest.get("ignore_columns", [])) | set(manifest.get("auto_excluded_columns", []))
    analysis_df = df[[column for column in df.columns if column not in excluded]].copy()

    section_blocks = []
    for section in chart_manifest.get("sections", []):
        chart_cards = []
        for chart in section.get("charts", []):
            image_uri = _make_chart_image(chart, overview, missingness, associations, target_analysis, analysis_df, column_profiles)
            if image_uri is None:
                continue
            card_class = "chart-card sidecar" if chart.get("layout") == "sidecar" else "chart-card"
            chart_cards.append(
                f"""
                <article class="{card_class}">
                  <div class="chart-text">
                    <h3>{html.escape(chart['title'])}</h3>
                    <p class="chart-subtitle">{html.escape(chart['subtitle'])}</p>
                    {_render_chart_explanation(chart)}
                  </div>
                  <div class="chart-frame">
                    <img class="chart-image" src="{image_uri}" alt="{html.escape(chart['title'])}">
                  </div>
                </article>
                """
            )

        if not chart_cards:
            continue
        section_blocks.append(
            f"""
            <section class="section-shell">
              <div class="section-header">
                <p class="section-kicker">{html.escape(section['title'])}</p>
                <h2>{html.escape(section['title'])}</h2>
              </div>
              <p class="section-description">{html.escape(section['description'])}</p>
              <div class="chart-grid">
                {''.join(chart_cards)}
              </div>
            </section>
            """
        )

    summary_cards = [
        ("Rows", f"{overview['row_count']:,}", "Total observations loaded."),
        ("Analyzed Columns", str(overview["analyzed_column_count"]), "After user ignores and auto-excluded index fields."),
        ("Missing Rate", f"{overview['total_missing_rate']:.1%}", "Across analyzed cells."),
        ("Targets", ", ".join(manifest.get("target_columns", [])) or "None", "Columns treated as outcomes."),
    ]
    summary_card_html = "\n".join(
        f"""
        <article class="metric-card">
          <p class="metric-label">{html.escape(label)}</p>
          <p class="metric-value">{html.escape(value)}</p>
          <p class="metric-subtext">{html.escape(subtext)}</p>
        </article>
        """
        for label, value, subtext in summary_cards
    )

    meta_card_payloads = [
        ("Source", Path(manifest["input_path"]).name),
        ("Format", manifest["format"]),
        ("Auto-excluded", ", ".join(manifest.get("auto_excluded_columns", [])) or "None"),
        ("Generated", manifest["created_at"]),
    ]
    meta_cards = "\n".join(
        f"""
        <article class="meta-card">
          <p class="meta-label">{html.escape(label)}</p>
          <p class="meta-value">{html.escape(value)}</p>
        </article>
        """
        for label, value in meta_card_payloads
    )

    subtitle = (
        f"Compact HTML exploration of {Path(manifest['input_path']).name} with embedded plots, "
        f"stable layout, and grounded narrative."
    )
    html_output = template.safe_substitute(
        title=manifest["report_title"],
        css=css,
        subtitle=subtitle,
        meta_cards=meta_cards,
        summary_cards=summary_card_html,
        narrative_html=markdown_to_html(analysis_text),
        sections_html="".join(section_blocks) if section_blocks else '<section class="section-shell"><div class="empty-state">No charts met the rendering criteria for this run.</div></section>',
    )

    destination = Path(output_path).resolve() if output_path else run_dir / "report.html"
    destination.write_text(html_output)
    return destination


def main():
    parser = argparse.ArgumentParser(description="Render HTML report with embedded plots.")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--output-path", default=None)
    args = parser.parse_args()
    output = render_report(args.run_dir, args.output_path)
    print(output)


if __name__ == "__main__":
    main()
