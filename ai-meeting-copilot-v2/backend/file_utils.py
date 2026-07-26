"""
Extract plain text from uploaded PDF, DOCX, or TXT files.
"""
import os
from pypdf import PdfReader
from docx import Document as DocxDocument


def extract_text(file_path: str) -> str:
    ext = os.path.splitext(file_path)[1].lower()

    if ext == ".pdf":
        reader = PdfReader(file_path)
        return "\n".join((page.extract_text() or "") for page in reader.pages)

    if ext == ".docx":
        doc = DocxDocument(file_path)
        return "\n".join(p.text for p in doc.paragraphs)

    if ext == ".txt":
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()

    raise ValueError(f"Unsupported file type: {ext}")
