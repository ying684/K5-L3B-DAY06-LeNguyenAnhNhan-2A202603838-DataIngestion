"""Extract a declared PDF subset, preserving physical page provenance."""
import re
import unicodedata
from pathlib import Path
from pypdf import PdfReader
from .models import DocumentPage


def normalize_text(text: str) -> str:
    text = unicodedata.normalize('NFC', text).replace('\x00', '')
    for old, new in [('ﬁ', 'fi'), ('ﬂ', 'fl'), ('\u00ad', '')]:
        text = text.replace(old, new)
    paragraphs, current = [], []
    for line in text.splitlines():
        line = re.sub(r'[^\S\n]+', ' ', line).strip()
        if not line:
            if current:
                paragraphs.append(' '.join(current)); current = []
            continue
        if re.match(r'^(?:\d+\s+)?CHƯƠNG\s+\d+\.', line) or line == 'Machine Learning cơ bản https://machinelearningcoban.com':
            continue
        heading = bool(re.match(r'^(?:\d+\.\d+(?:\.\d+)?\s|Chương \d+$|[•])', line))
        if heading and current:
            paragraphs.append(' '.join(current)); current = []
        current.append(line)
        if heading or re.search(r'[.!?:]$', line):
            paragraphs.append(' '.join(current)); current = []
    if current: paragraphs.append(' '.join(current))
    return '\n\n'.join(paragraphs)


def load_pdf(path: Path, document_id: str, source: str,
             page_numbers: list[int] | None = None) -> list[DocumentPage]:
    reader = PdfReader(path)
    pages = []
    numbers = page_numbers if page_numbers is not None else list(range(1, len(reader.pages)+1))
    for number in numbers:
        if not 1 <= number <= len(reader.pages): raise ValueError(f'Invalid physical page: {number}')
        text = normalize_text(reader.pages[number-1].extract_text() or '')
        if not text: raise ValueError(f'Empty text on selected physical page {number}; OCR/review required')
        pages.append(DocumentPage(document_id, source, number, text))
    return pages
