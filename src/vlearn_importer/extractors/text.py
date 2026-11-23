"""First-stage text-only extraction from DOCX or searchable PDFs.

This does NOT yet parse TOEIC questions or do OCR.
"""

from pathlib import Path


def extract_text(path: Path) -> str:
    if not path.is_file():
        raise FileNotFoundError(path)
    suffix = path.suffix.lower()
    if suffix == ".docx":
        try:
            from docx import Document
        except ImportError as exc:
            raise RuntimeError("Install with: pip install -e '.[extract]'") from exc
        doc = Document(str(path))
        paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
        for table in doc.tables:
            for row in table.rows:
                line = " | ".join(cell.text.strip() for cell in row.cells)
                if line.strip(" |"):
                    paragraphs.append(line)
        return "\n".join(paragraphs)
    if suffix == ".pdf":
        try:
            import pymupdf
        except ImportError as exc:
            raise RuntimeError("Install with: pip install -e '.[extract]'") from exc
        parts: list[str] = []
        with pymupdf.open(str(path)) as pdf:
            for page in pdf:
                parts.append(page.get_text("text"))
        return "\n".join(parts)
    raise ValueError("Unsupported file type; only .pdf and .docx are accepted")
