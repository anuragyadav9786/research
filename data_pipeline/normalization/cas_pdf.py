"""Extracts text from an uploaded CAS (Consolidated Account Statement) PDF.

Uses pypdf (a pure-Python library, already a backend dependency) rather
than shelling out to poppler's pdftotext — this runs inside the FastAPI
request handler, and the deployed backend has no guaranteed system
dependency on poppler-utils.

A genuine CAMS/KFintech-generated CAS PDF carries a real text layer (its
Folio No / ISIN / Closing Unit Balance lines are selectable text, not
pixels) — confirmed by directly inspecting a real CAS PDF's rendered
pages. An image-only PDF (e.g. a screen "Print to PDF" of a viewer rather
than the original CAMS/KFintech file) has no text to extract at all; this
raises CASUnreadableError rather than silently returning nothing, so the
caller can tell the user exactly what to re-upload instead of getting a
confusing "no holdings found" result.
"""
from __future__ import annotations

import io

from pypdf import PdfReader
from pypdf.errors import PdfReadError


class CASPasswordError(Exception):
    """Raised when the PDF is encrypted and no password, or the wrong
    password, was supplied."""


class CASUnreadableError(Exception):
    """Raised when the file isn't a readable PDF, or has no extractable
    text layer at all."""


def extract_cas_text(pdf_bytes: bytes, password: str | None) -> str:
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
    except (PdfReadError, ValueError) as exc:
        raise CASUnreadableError(f"Could not open this file as a PDF: {exc}") from exc

    if reader.is_encrypted:
        if not password:
            raise CASPasswordError("This PDF is password-protected. Enter its password.")
        # pypdf's decrypt returns a truthy PasswordType on success, 0 (falsy) on failure.
        if not reader.decrypt(password):
            raise CASPasswordError("Incorrect PDF password.")

    # "layout" mode preserves the document's visual reading order
    # (matching poppler's pdftotext -layout) — confirmed necessary against
    # a real CAS PDF: the default extraction mode reads text runs in an
    # order that scrambles which ISIN/folio/market-value belong together
    # across a multi-column, multi-folio page, while layout mode keeps
    # each folio's fields correctly grouped. Per-page, not per-document:
    # this is parsing an arbitrary user upload, so one malformed page
    # (e.g. no content stream at all) raises a library-internal error
    # (pypdf can throw KeyError, not just its own PdfReadError, for a
    # page with no /Contents) that shouldn't sink extraction of every
    # other page — it's treated as that one page contributing no text.
    pages_text = []
    for page in reader.pages:
        try:
            pages_text.append(page.extract_text(extraction_mode="layout") or "")
        except Exception:  # noqa: BLE001 - any per-page extraction failure degrades to no text, never a 500
            pages_text.append("")

    text = "\n".join(pages_text)
    if not text.strip():
        raise CASUnreadableError(
            "This PDF has no extractable text — it looks like a scanned or image-only file "
            "(e.g. a screenshot or a \"Print to PDF\" copy of a viewer, rather than the "
            "original). Upload the CAS PDF exactly as emailed by CAMS/KFintech; it should be "
            "possible to select and copy text from it in any PDF viewer."
        )
    return text
