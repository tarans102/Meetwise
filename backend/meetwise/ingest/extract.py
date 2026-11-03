"""Turn uploaded TXT / PDF / DOCX bytes into plain text."""

from __future__ import annotations

import io
from pathlib import Path

SUPPORTED_EXTENSIONS = (".txt", ".pdf", ".docx")


class UnsupportedFormatError(ValueError):
    pass


def extract_text(filename: str, data: bytes) -> str:
    ext = Path(filename or "").suffix.lower()
    if ext == ".txt":
        return data.decode("utf-8", errors="replace")
    if ext == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    if ext == ".docx":
        import docx

        document = docx.Document(io.BytesIO(data))
        return "\n".join(paragraph.text for paragraph in document.paragraphs)
    raise UnsupportedFormatError(
        f"Unsupported file type '{ext or 'none'}'. Upload a TXT, PDF, or DOCX transcript."
    )
