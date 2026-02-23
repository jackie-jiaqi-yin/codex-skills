#!/usr/bin/env python3
"""Render report markdown to pretty HTML and same-content PDF.

This module is intentionally self-contained for skill isolation.
"""

from __future__ import annotations

import argparse
import html
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path


MD_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^\s)]+)\)")
MD_BOLD_RE = re.compile(r"\*\*([^*]+)\*\*")
MD_ITALIC_RE = re.compile(r"(?<!\*)\*([^*\n]+)\*(?!\*)")
MD_CODE_RE = re.compile(r"`([^`]+)`")


def _inline_markdown_to_html(text: str) -> str:
    escaped = html.escape(text, quote=True)

    def _link_sub(match: re.Match[str]) -> str:
        label = match.group(1)
        url = html.escape(html.unescape(match.group(2)), quote=True)
        return f'<a href="{url}" target="_blank" rel="noopener noreferrer">{label}</a>'

    escaped = MD_LINK_RE.sub(_link_sub, escaped)
    escaped = MD_CODE_RE.sub(r"<code>\1</code>", escaped)
    escaped = MD_BOLD_RE.sub(r"<strong>\1</strong>", escaped)
    escaped = MD_ITALIC_RE.sub(r"<em>\1</em>", escaped)

    return escaped


def _split_table_row(line: str) -> list[str]:
    core = line.strip().strip("|")
    return [cell.strip() for cell in core.split("|")]


def _is_table_separator(line: str) -> bool:
    stripped = line.strip()
    if not stripped.startswith("|"):
        return False
    core = stripped.strip("|").replace(" ", "")
    if not core:
        return False
    return all(ch in "-:" for ch in core)


def _looks_like_table(lines: list[str], idx: int) -> bool:
    if idx + 1 >= len(lines):
        return False
    current = lines[idx].strip()
    nxt = lines[idx + 1].strip()
    return current.startswith("|") and nxt.startswith("|") and _is_table_separator(nxt)


def _starts_special_line(lines: list[str], idx: int) -> bool:
    if idx >= len(lines):
        return True
    stripped = lines[idx].strip()
    if not stripped:
        return True
    if stripped.startswith("```"):
        return True
    if re.match(r"^#{1,6}\s+", stripped):
        return True
    if re.match(r"^[-*]\s+", stripped):
        return True
    if re.match(r"^\d+\.\s+", stripped):
        return True
    if stripped.startswith(">"):
        return True
    if stripped in {"---", "***", "___"}:
        return True
    if _looks_like_table(lines, idx):
        return True
    return False


def _render_table_html(table_lines: list[str]) -> str:
    if len(table_lines) < 2 or not _is_table_separator(table_lines[1]):
        return ""

    header = _split_table_row(table_lines[0])
    body_rows = [_split_table_row(line) for line in table_lines[2:]]

    if not header:
        return ""

    html_parts: list[str] = ["<table>", "<thead>", "<tr>"]
    for cell in header:
        html_parts.append(f"<th>{_inline_markdown_to_html(cell)}</th>")
    html_parts.extend(["</tr>", "</thead>", "<tbody>"])

    for row in body_rows:
        html_parts.append("<tr>")
        padded = row + [""] * (len(header) - len(row))
        for cell in padded[: len(header)]:
            html_parts.append(f"<td>{_inline_markdown_to_html(cell)}</td>")
        html_parts.append("</tr>")

    html_parts.extend(["</tbody>", "</table>"])
    return "\n".join(html_parts)


def _convert_markdown_fallback(md_text: str) -> str:
    lines = md_text.splitlines()
    html_lines: list[str] = []
    idx = 0
    list_mode: str | None = None

    def _close_list() -> None:
        nonlocal list_mode
        if list_mode == "ul":
            html_lines.append("</ul>")
        elif list_mode == "ol":
            html_lines.append("</ol>")
        list_mode = None

    while idx < len(lines):
        line = lines[idx]
        stripped = line.strip()

        if not stripped:
            _close_list()
            idx += 1
            continue

        if stripped.startswith("```"):
            _close_list()
            idx += 1
            code_lines: list[str] = []
            while idx < len(lines) and not lines[idx].strip().startswith("```"):
                code_lines.append(lines[idx])
                idx += 1
            if idx < len(lines):
                idx += 1
            code = html.escape("\n".join(code_lines), quote=True)
            html_lines.append(f"<pre><code>{code}</code></pre>")
            continue

        if _looks_like_table(lines, idx):
            _close_list()
            table_lines: list[str] = []
            while idx < len(lines) and lines[idx].strip().startswith("|"):
                table_lines.append(lines[idx])
                idx += 1
            table_html = _render_table_html(table_lines)
            if table_html:
                html_lines.append(table_html)
            continue

        heading_match = re.match(r"^(#{1,6})\s+(.+)$", stripped)
        if heading_match:
            _close_list()
            level = min(len(heading_match.group(1)), 6)
            content = _inline_markdown_to_html(heading_match.group(2).strip())
            html_lines.append(f"<h{level}>{content}</h{level}>")
            idx += 1
            continue

        if stripped in {"---", "***", "___"}:
            _close_list()
            html_lines.append("<hr/>")
            idx += 1
            continue

        if stripped.startswith(">"):
            _close_list()
            quote_lines: list[str] = []
            while idx < len(lines) and lines[idx].strip().startswith(">"):
                quote_lines.append(lines[idx].strip().lstrip(">").strip())
                idx += 1
            quote_text = " ".join([q for q in quote_lines if q])
            html_lines.append(f"<blockquote><p>{_inline_markdown_to_html(quote_text)}</p></blockquote>")
            continue

        ul_match = re.match(r"^[-*]\s+(.+)$", stripped)
        if ul_match:
            if list_mode != "ul":
                _close_list()
                html_lines.append("<ul>")
                list_mode = "ul"
            html_lines.append(f"<li>{_inline_markdown_to_html(ul_match.group(1).strip())}</li>")
            idx += 1
            continue

        ol_match = re.match(r"^\d+\.\s+(.+)$", stripped)
        if ol_match:
            if list_mode != "ol":
                _close_list()
                html_lines.append("<ol>")
                list_mode = "ol"
            html_lines.append(f"<li>{_inline_markdown_to_html(ol_match.group(1).strip())}</li>")
            idx += 1
            continue

        _close_list()
        para_parts = [stripped]
        idx += 1
        while idx < len(lines) and not _starts_special_line(lines, idx):
            next_stripped = lines[idx].strip()
            if next_stripped:
                para_parts.append(next_stripped)
            idx += 1

        paragraph = " ".join(para_parts)
        html_lines.append(f"<p>{_inline_markdown_to_html(paragraph)}</p>")

    _close_list()
    return "\n".join(html_lines)


def _convert_markdown(md_text: str) -> str:
    try:
        import markdown2  # type: ignore

        return markdown2.markdown(
            md_text,
            extras=[
                "fenced-code-blocks",
                "tables",
                "strike",
                "break-on-newline",
                "cuddled-lists",
            ],
        )
    except Exception:
        return _convert_markdown_fallback(md_text)


def _load_template(template_path: Path) -> str:
    if template_path.exists():
        return template_path.read_text(encoding="utf-8")
    return """<!doctype html>
<html lang='en'>
<head>
  <meta charset='utf-8' />
  <meta name='viewport' content='width=device-width, initial-scale=1' />
  <title>{{TITLE}}</title>
  <style>{{CSS}}</style>
</head>
<body>
  <main class='report'>
    {{CONTENT}}
  </main>
</body>
</html>
"""


def _load_css(css_path: Path) -> str:
    if css_path.exists():
        return css_path.read_text(encoding="utf-8")
    return "body { font-family: Georgia, serif; margin: 24px; }"


def _render_html(*, title: str, body_html: str, template: str, css: str) -> str:
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    page = template
    page = page.replace("{{TITLE}}", html.escape(title))
    page = page.replace("{{CSS}}", css)
    page = page.replace("{{GENERATED_AT}}", html.escape(generated_at))
    page = page.replace("{{CONTENT}}", body_html)
    return page


def _pdf_with_weasyprint(html_path: Path, pdf_path: Path) -> bool:
    try:
        from weasyprint import HTML  # type: ignore

        HTML(filename=str(html_path), base_url=str(html_path.parent)).write_pdf(str(pdf_path))
        return True
    except Exception:
        return False


def _pdf_with_wkhtmltopdf(html_path: Path, pdf_path: Path) -> bool:
    binary = shutil.which("wkhtmltopdf")
    if not binary:
        return False

    cmd = [binary, "--enable-local-file-access", str(html_path), str(pdf_path)]
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return True
    except subprocess.CalledProcessError:
        return False


def _pdf_with_xhtml2pdf(html_page: str, pdf_path: Path) -> bool:
    try:
        from xhtml2pdf import pisa  # type: ignore
    except Exception:
        return False

    try:
        with pdf_path.open("wb") as handle:
            result = pisa.CreatePDF(src=html_page, dest=handle)
        return not bool(result.err)
    except Exception:
        return False


def _inline_markdown_to_reportlab(text: str) -> str:
    escaped = html.escape(text, quote=True)

    def _link_sub(match: re.Match[str]) -> str:
        label = match.group(1)
        url = html.escape(html.unescape(match.group(2)), quote=True)
        return f'<a href="{url}"><u>{label}</u></a>'

    escaped = MD_LINK_RE.sub(_link_sub, escaped)
    escaped = MD_CODE_RE.sub(r"<font name='Courier'>\1</font>", escaped)
    escaped = MD_BOLD_RE.sub(r"<b>\1</b>", escaped)
    escaped = MD_ITALIC_RE.sub(r"<i>\1</i>", escaped)
    return escaped


def _pdf_with_reportlab(md_text: str, pdf_path: Path) -> bool:
    try:
        from reportlab.lib import colors  # type: ignore
        from reportlab.lib.pagesizes import A4  # type: ignore
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet  # type: ignore
        from reportlab.lib.units import mm  # type: ignore
        from reportlab.platypus import (  # type: ignore
            ListFlowable,
            ListItem,
            Paragraph,
            Preformatted,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )
    except Exception:
        return False

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ReportH1",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=19,
        leading=23,
        spaceAfter=8,
        textColor=colors.HexColor("#14283f"),
    )
    h2_style = ParagraphStyle(
        "ReportH2",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=14,
        leading=18,
        spaceBefore=9,
        spaceAfter=6,
        textColor=colors.HexColor("#17385d"),
    )
    h3_style = ParagraphStyle(
        "ReportH3",
        parent=styles["Heading3"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=15,
        spaceBefore=8,
        spaceAfter=4,
        textColor=colors.HexColor("#1b4f72"),
    )
    body_style = ParagraphStyle(
        "ReportBody",
        parent=styles["BodyText"],
        fontName="Times-Roman",
        fontSize=10.5,
        leading=14,
        spaceAfter=6,
    )
    quote_style = ParagraphStyle(
        "ReportQuote",
        parent=body_style,
        leftIndent=10,
        rightIndent=6,
        textColor=colors.HexColor("#4a5563"),
        backColor=colors.HexColor("#f3f7fb"),
        borderColor=colors.HexColor("#c9d8e6"),
        borderWidth=0.5,
        borderPadding=5,
        spaceBefore=4,
        spaceAfter=8,
    )
    code_style = ParagraphStyle(
        "ReportCode",
        parent=body_style,
        fontName="Courier",
        fontSize=8.8,
        leading=11,
        leftIndent=6,
        rightIndent=6,
        backColor=colors.HexColor("#f5f7fa"),
        borderColor=colors.HexColor("#d6dee8"),
        borderWidth=0.5,
        borderPadding=5,
        spaceBefore=4,
        spaceAfter=8,
    )

    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        title="Latest arXiv Summary",
    )

    story: list = []
    lines = md_text.splitlines()
    idx = 0

    def _add_heading(level: int, text: str) -> None:
        safe = _inline_markdown_to_reportlab(text)
        if level == 1:
            story.append(Paragraph(safe, title_style))
        elif level == 2:
            story.append(Paragraph(safe, h2_style))
        else:
            story.append(Paragraph(safe, h3_style))

    while idx < len(lines):
        raw = lines[idx]
        stripped = raw.strip()

        if not stripped:
            idx += 1
            continue

        if stripped.startswith("```"):
            idx += 1
            code_lines: list[str] = []
            while idx < len(lines) and not lines[idx].strip().startswith("```"):
                code_lines.append(lines[idx])
                idx += 1
            if idx < len(lines):
                idx += 1
            story.append(Preformatted("\n".join(code_lines), code_style))
            continue

        if _looks_like_table(lines, idx):
            table_lines: list[str] = []
            while idx < len(lines) and lines[idx].strip().startswith("|"):
                table_lines.append(lines[idx])
                idx += 1

            header = _split_table_row(table_lines[0])
            body_rows = [_split_table_row(line) for line in table_lines[2:]]
            if header:
                data = [[Paragraph(_inline_markdown_to_reportlab(cell), body_style) for cell in header]]
                for row in body_rows:
                    padded = row + [""] * (len(header) - len(row))
                    data.append([Paragraph(_inline_markdown_to_reportlab(cell), body_style) for cell in padded[: len(header)]])

                table = Table(data, repeatRows=1)
                table.setStyle(
                    TableStyle(
                        [
                            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8f0f8")),
                            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#12304a")),
                            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#c9d8e6")),
                            ("VALIGN", (0, 0), (-1, -1), "TOP"),
                            ("LEFTPADDING", (0, 0), (-1, -1), 5),
                            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                            ("TOPPADDING", (0, 0), (-1, -1), 4),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                        ]
                    )
                )
                story.append(table)
                story.append(Spacer(1, 8))
            continue

        heading_match = re.match(r"^(#{1,6})\s+(.+)$", stripped)
        if heading_match:
            level = len(heading_match.group(1))
            _add_heading(level, heading_match.group(2).strip())
            idx += 1
            continue

        if stripped in {"---", "***", "___"}:
            story.append(Spacer(1, 6))
            idx += 1
            continue

        if stripped.startswith(">"):
            quote_lines: list[str] = []
            while idx < len(lines) and lines[idx].strip().startswith(">"):
                quote_lines.append(lines[idx].strip().lstrip(">").strip())
                idx += 1
            quote_text = " ".join([q for q in quote_lines if q])
            story.append(Paragraph(_inline_markdown_to_reportlab(quote_text), quote_style))
            continue

        ul_match = re.match(r"^[-*]\s+(.+)$", stripped)
        if ul_match:
            items = []
            while idx < len(lines):
                current = lines[idx].strip()
                m = re.match(r"^[-*]\s+(.+)$", current)
                if not m:
                    break
                items.append(ListItem(Paragraph(_inline_markdown_to_reportlab(m.group(1).strip()), body_style)))
                idx += 1
            story.append(ListFlowable(items, bulletType="bullet", leftIndent=16))
            story.append(Spacer(1, 4))
            continue

        ol_match = re.match(r"^\d+\.\s+(.+)$", stripped)
        if ol_match:
            items = []
            while idx < len(lines):
                current = lines[idx].strip()
                m = re.match(r"^\d+\.\s+(.+)$", current)
                if not m:
                    break
                items.append(ListItem(Paragraph(_inline_markdown_to_reportlab(m.group(1).strip()), body_style)))
                idx += 1
            story.append(ListFlowable(items, bulletType="1", leftIndent=16))
            story.append(Spacer(1, 4))
            continue

        para_parts = [stripped]
        idx += 1
        while idx < len(lines) and not _starts_special_line(lines, idx):
            nxt = lines[idx].strip()
            if nxt:
                para_parts.append(nxt)
            idx += 1

        paragraph = " ".join(para_parts)
        story.append(Paragraph(_inline_markdown_to_reportlab(paragraph), body_style))

    if not story:
        story.append(Paragraph("No content available.", body_style))

    try:
        doc.build(story)
        return True
    except Exception:
        return False


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export markdown report to HTML and PDF")
    parser.add_argument("--input-md", required=True)
    parser.add_argument("--output-html", required=True)
    parser.add_argument("--output-pdf", required=True)
    parser.add_argument("--title", default="Latest arXiv Summary")
    parser.add_argument("--template", help="Optional HTML template path")
    parser.add_argument("--css", help="Optional CSS path")
    return parser


def main() -> int:
    args = _build_parser().parse_args()

    input_md = Path(args.input_md)
    output_html = Path(args.output_html)
    output_pdf = Path(args.output_pdf)

    if not input_md.exists():
        raise SystemExit(f"Markdown input not found: {input_md}")

    script_dir = Path(__file__).resolve().parent
    default_template = script_dir.parent / "assets" / "report_template.html"
    default_css = script_dir.parent / "assets" / "report_style.css"

    template_path = Path(args.template) if args.template else default_template
    css_path = Path(args.css) if args.css else default_css

    md_text = input_md.read_text(encoding="utf-8")
    body_html = _convert_markdown(md_text)
    template = _load_template(template_path)
    css = _load_css(css_path)

    html_page = _render_html(title=args.title, body_html=body_html, template=template, css=css)

    output_html.parent.mkdir(parents=True, exist_ok=True)
    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    output_html.write_text(html_page, encoding="utf-8")

    if _pdf_with_weasyprint(output_html, output_pdf):
        print(f"PDF generated via weasyprint: {output_pdf}")
        return 0

    if _pdf_with_wkhtmltopdf(output_html, output_pdf):
        print(f"PDF generated via wkhtmltopdf: {output_pdf}")
        return 0

    if _pdf_with_xhtml2pdf(html_page, output_pdf):
        print(f"PDF generated via xhtml2pdf: {output_pdf}")
        return 0

    if _pdf_with_reportlab(md_text, output_pdf):
        print(f"PDF generated via reportlab rich fallback: {output_pdf}")
        print("Tip: install weasyprint or wkhtmltopdf for highest-fidelity HTML-to-PDF rendering.")
        return 0

    raise SystemExit(
        "Could not generate PDF. Install one of: weasyprint, wkhtmltopdf, xhtml2pdf, or reportlab. "
        "HTML output was generated successfully."
    )


if __name__ == "__main__":
    raise SystemExit(main())
