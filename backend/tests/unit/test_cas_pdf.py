import io

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from data_pipeline.normalization.cas_pdf import CASPasswordError, CASUnreadableError, extract_cas_text


def _make_pdf(text: str | None, password: str | None = None) -> bytes:
    """Builds a minimal one-page PDF, optionally with a text content
    stream and/or a user password, using pypdf's own object model —
    avoids depending on a PDF-generation library just for tests."""
    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=300)

    if text is not None:
        font = DictionaryObject()
        font[NameObject("/Type")] = NameObject("/Font")
        font[NameObject("/Subtype")] = NameObject("/Type1")
        font[NameObject("/BaseFont")] = NameObject("/Helvetica")
        font_ref = writer._add_object(font)

        resources = DictionaryObject()
        fonts = DictionaryObject()
        fonts[NameObject("/F1")] = font_ref
        resources[NameObject("/Font")] = fonts
        page[NameObject("/Resources")] = resources

        stream = DecodedStreamObject()
        stream.set_data(f"BT /F1 12 Tf 10 250 Td ({text}) Tj ET".encode())
        page[NameObject("/Contents")] = writer._add_object(stream)

    if password is not None:
        writer.encrypt(user_password=password, owner_password=password)

    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def test_extracts_text_from_an_unencrypted_pdf():
    pdf_bytes = _make_pdf("Folio No: 1 / 0")
    text = extract_cas_text(pdf_bytes, password=None)
    assert "Folio No: 1 / 0" in text


def test_encrypted_pdf_without_password_raises():
    pdf_bytes = _make_pdf("Folio No: 1 / 0", password="Abc@1234")
    with pytest.raises(CASPasswordError):
        extract_cas_text(pdf_bytes, password=None)


def test_encrypted_pdf_with_wrong_password_raises():
    pdf_bytes = _make_pdf("Folio No: 1 / 0", password="Abc@1234")
    with pytest.raises(CASPasswordError):
        extract_cas_text(pdf_bytes, password="wrong-password")


def test_encrypted_pdf_with_correct_password_extracts_text():
    pdf_bytes = _make_pdf("Folio No: 1 / 0", password="Abc@1234")
    text = extract_cas_text(pdf_bytes, password="Abc@1234")
    assert "Folio No: 1 / 0" in text


def test_pdf_with_no_text_layer_raises_unreadable():
    pdf_bytes = _make_pdf(text=None)  # blank page, no content stream at all
    with pytest.raises(CASUnreadableError):
        extract_cas_text(pdf_bytes, password=None)


def test_non_pdf_bytes_raise_unreadable():
    with pytest.raises(CASUnreadableError):
        extract_cas_text(b"not a pdf at all", password=None)
