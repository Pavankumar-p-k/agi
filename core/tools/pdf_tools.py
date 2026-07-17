"""core/tools/pdf_tools.py
PDF generation tools using fpdf2 (fpdf2 library).
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Optional

from core.tools._constants import ToolBlock

try:
    from fpdf import FPDF
except ImportError:
    FPDF = None

logger = logging.getLogger(__name__)


class PDFGenerator:
    """PDF generation using fpdf2."""

    def __init__(self, output_dir: Optional[str] = None):
        if FPDF is None:
            raise RuntimeError("fpdf2 not installed. Install with: pip install fpdf2")
        self.output_dir = Path(output_dir or ".")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_report(
        self,
        title: str,
        content: str,
        output_filename: Optional[str] = None,
        author: str = "JARVIS",
    ) -> dict[str, Any]:
        """Generate a PDF report from title and content.

        Args:
            title: Report title
            content: Report content (markdown or plain text)
            output_filename: Optional output filename (auto-generated if not provided)
            author: Author name

        Returns:
            Dict with success status, output path, and any error
        """
        try:
            if not output_filename:
                safe_title = "".join(c if c.isalnum() else "_" for c in title)[:50]
                output_filename = f"{safe_title}_report.pdf"

            output_path = self.output_dir / output_filename

            pdf = FPDF()
            pdf.set_auto_page_break(auto=True, margin=15)
            pdf.add_page()

            # Title
            pdf.set_font("Helvetica", "B", 16)
            pdf.cell(0, 10, title, ln=True, align="C")
            pdf.ln(5)

            # Content
            pdf.set_font("Helvetica", "", 11)
            pdf.multi_cell(0, 5, content)

            pdf.output(str(output_path))

            logger.info(f"PDF generated: {output_path}")
            return {
                "success": True,
                "output_path": str(output_path),
                "filename": output_filename,
            }

        except Exception as e:
            logger.exception("PDF generation failed")
            return {"success": False, "error": str(e)}

    def generate_from_markdown(
        self,
        markdown_content: str,
        output_filename: Optional[str] = None,
    ) -> dict[str, Any]:
        """Generate PDF from markdown content.

        Simple markdown to PDF conversion.
        """
        # Basic markdown to text conversion
        content = markdown_content.replace("# ", "").replace("## ", "").replace("### ", "")
        return self.generate_report("Report", content, output_filename)


def do_generate_pdf(content: str, owner: str | None = None) -> dict:
    """Generate a PDF document from content.

    Args:
        content: JSON with keys: title, content, output_filename (optional), author (optional)
        owner: Optional owner for authentication

    Returns:
        Dict with success status, output_path, and filename
    """
    try:
        args = json.loads(content)
    except json.JSONDecodeError as e:
        return {"error": f"Invalid JSON: {e}", "exit_code": 1}

    title = args.get("title", "Report")
    content = args.get("content", "")
    output_filename = args.get("output_filename")
    author = args.get("author", "JARVIS")

    if not content:
        return {"error": "content is required", "exit_code": 1}

    try:
        generator = PDFGenerator()
        result = generator.generate_report(title, content, output_filename, author)
        return result
    except Exception as e:
        return {"error": str(e), "exit_code": 1}


# Tool registration
PDF_TOOLS = [
    {
        "name": "generate_pdf",
        "description": "Generate a PDF document from title and content",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Report title"},
                "content": {"type": "string", "description": "Report content (markdown or plain text)"},
                "output_filename": {"type": "string", "description": "Optional output filename"},
                "author": {"type": "string", "description": "Author name"},
            },
            "required": ["title", "content"],
        },
    }
]