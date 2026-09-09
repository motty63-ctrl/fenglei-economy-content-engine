"""Bounded PDF text extraction with page-level provenance."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from io import BytesIO

from pypdf import PdfReader

from fanglei.errors import ProviderError


@dataclass(frozen=True)
class PdfExtraction:
    text: str
    pages: list[dict[str, object]]
    document_hash: str


class PdfTextExtractor:
    def __init__(self, max_bytes: int = 20_000_000, max_pages: int = 300, max_text_chars: int = 5_000_000):
        self.max_bytes = max_bytes
        self.max_pages = max_pages
        self.max_text_chars = max_text_chars

    def extract(self, raw: bytes) -> PdfExtraction:
        if not raw.startswith(b"%PDF-"):
            raise ProviderError("invalid_pdf: missing PDF file signature")
        if len(raw) > self.max_bytes:
            raise ProviderError("pdf_size_limit: PDF exceeds configured download limit")
        try:
            reader = PdfReader(BytesIO(raw), strict=True)
            if reader.is_encrypted:
                raise ProviderError("pdf_encrypted: encrypted PDF is not eligible")
            if len(reader.pages) > self.max_pages:
                raise ProviderError("pdf_page_limit: PDF exceeds configured page limit")
            pages: list[dict[str, object]] = []
            total = 0
            for page_number, page in enumerate(reader.pages, 1):
                text = (page.extract_text() or "").strip()
                total += len(text)
                if total > self.max_text_chars:
                    raise ProviderError("pdf_text_limit: extracted PDF text exceeds configured limit")
                pages.append({
                    "page_number": page_number,
                    "text": text,
                    "content_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                })
        except ProviderError:
            raise
        except Exception:
            raise ProviderError("invalid_pdf: PDF parser rejected the document") from None
        if not any(page["text"] for page in pages):
            raise ProviderError("pdf_no_extractable_text: PDF contains no extractable text")
        return PdfExtraction(
            text="\n\n".join(str(page["text"]) for page in pages if page["text"]),
            pages=pages,
            document_hash=hashlib.sha256(raw).hexdigest(),
        )
