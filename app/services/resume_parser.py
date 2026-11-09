from __future__ import annotations

import io
from pathlib import Path


def extract_text(filename: str, content: bytes) -> str:
    ext = Path(filename).suffix.lower()
    if ext == ".pdf":
        return _pdf_text(content)
    if ext in {".docx", ".doc"}:
        return _docx_text(content)
    try:
        return content.decode("utf-8", errors="ignore")
    except Exception:
        return ""


def extract_text_from_path(path: str | Path) -> str:
    p = Path(path)
    return extract_text(p.name, p.read_bytes())


def _pdf_text(content: bytes) -> str:
    try:
        import pymupdf  # type: ignore
    except Exception:  # pragma: no cover
        import fitz as pymupdf  # type: ignore

    parts: list[str] = []
    with pymupdf.open(stream=content, filetype="pdf") as doc:
        for page in doc:
            parts.append(page.get_text())
    return "\n".join(parts).strip()


def _docx_text(content: bytes) -> str:
    from docx import Document

    doc = Document(io.BytesIO(content))
    lines = [p.text for p in doc.paragraphs]
    for table in doc.tables:
        for row in table.rows:
            lines.append(" | ".join(cell.text for cell in row.cells))
    return "\n".join(lines).strip()
