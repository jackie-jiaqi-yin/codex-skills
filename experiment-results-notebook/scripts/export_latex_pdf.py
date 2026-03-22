#!/usr/bin/env python3
"""Export Markdown to LaTeX and PDF with pandoc and latexmk."""

from __future__ import annotations

import argparse
import shutil
import subprocess
from datetime import datetime
from pathlib import Path


def export_markdown(markdown_path: Path, tex_path: Path, pdf_path: Path, title: str, template_path: Path) -> dict[str, str]:
    if shutil.which("pandoc") is None:
        raise SystemExit("pandoc is required but was not found on PATH.")
    if shutil.which("latexmk") is None:
        raise SystemExit("latexmk is required but was not found on PATH.")

    markdown_path = markdown_path.resolve()
    tex_path = tex_path.resolve()
    pdf_path = pdf_path.resolve()
    template_path = template_path.resolve()
    tex_path.parent.mkdir(parents=True, exist_ok=True)
    pdf_path.parent.mkdir(parents=True, exist_ok=True)

    pandoc_cmd = [
        "pandoc",
        str(markdown_path),
        "--from",
        "markdown+pipe_tables+raw_html",
        "--standalone",
        "--template",
        str(template_path),
        "--metadata",
        f"title={title}",
        "--metadata",
        f"date={datetime.fromtimestamp(markdown_path.stat().st_mtime).strftime('%Y-%m-%d %H:%M:%S')}",
        "--resource-path",
        str(markdown_path.parent),
        "-o",
        str(tex_path),
    ]
    subprocess.run(pandoc_cmd, check=True)

    latexmk_cmd = [
        "latexmk",
        "-pdf",
        "-interaction=nonstopmode",
        "-halt-on-error",
        f"-output-directory={pdf_path.parent}",
        str(tex_path),
    ]
    subprocess.run(latexmk_cmd, check=True, cwd=str(tex_path.parent))

    generated_pdf = pdf_path.parent / f"{tex_path.stem}.pdf"
    if generated_pdf != pdf_path and generated_pdf.exists():
        shutil.copy2(generated_pdf, pdf_path)

    return {
        "markdown": str(markdown_path),
        "tex": str(tex_path),
        "pdf": str(pdf_path),
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export notebook markdown to LaTeX and PDF")
    parser.add_argument("--input-md", required=True)
    parser.add_argument("--output-tex", required=True)
    parser.add_argument("--output-pdf", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--template", required=True)
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    export_markdown(
        markdown_path=Path(args.input_md),
        tex_path=Path(args.output_tex),
        pdf_path=Path(args.output_pdf),
        title=args.title,
        template_path=Path(args.template),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
