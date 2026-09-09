from io import BytesIO

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from fanglei.errors import ProviderError
from fanglei.providers.pdf_fetch import PdfTextExtractor


def _pdf_with_pages(lines: list[str]) -> bytes:
    writer = PdfWriter()
    font = DictionaryObject({
        NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica"),
    })
    font_ref = writer._add_object(font)
    for line in lines:
        page = writer.add_blank_page(width=400, height=200)
        page[NameObject("/Resources")] = DictionaryObject({
            NameObject("/Font"): DictionaryObject({NameObject("/F1"): font_ref})
        })
        stream = DecodedStreamObject()
        stream.set_data(f"BT /F1 12 Tf 20 100 Td ({line}) Tj ET".encode("ascii"))
        page[NameObject("/Contents")] = writer._add_object(stream)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def test_pdf_extraction_preserves_page_numbers_and_document_hash() -> None:
    raw = _pdf_with_pages(["Overview", "Real GDP grew 2.8 percent in 2024."])
    result = PdfTextExtractor().extract(raw)
    assert result.document_hash
    assert len(result.pages) == 2
    assert result.pages[1]["page_number"] == 2
    assert "2.8 percent" in result.pages[1]["text"]
    assert "2.8 percent" in result.text


def test_pdf_rejects_invalid_header_page_limit_and_no_text() -> None:
    with pytest.raises(ProviderError, match="invalid_pdf"):
        PdfTextExtractor().extract(b"not a pdf")
    with pytest.raises(ProviderError, match="pdf_page_limit"):
        PdfTextExtractor(max_pages=1).extract(_pdf_with_pages(["one", "two"]))
    with pytest.raises(ProviderError, match="pdf_no_extractable_text"):
        PdfTextExtractor().extract(_pdf_with_pages(["", ""]))


def test_pdf_rejects_download_and_extracted_text_size_limits() -> None:
    raw = _pdf_with_pages(["A" * 100])
    with pytest.raises(ProviderError, match="pdf_size_limit"):
        PdfTextExtractor(max_bytes=10).extract(raw)
    with pytest.raises(ProviderError, match="pdf_text_limit"):
        PdfTextExtractor(max_text_chars=10).extract(raw)
