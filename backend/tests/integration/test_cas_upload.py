"""Integration tests for POST /api/portfolio/cas/parse, against the real
local Postgres database. Builds minimal real PDFs on the fly (via pypdf's
own object model — see _make_pdf) rather than shipping a binary fixture,
and inserts a temporary "CAS Test" scheme/variant so the matched-holding
path has a real ISIN to match against without touching seed data.
"""
from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from app.core.database import SessionLocal
from app.main import app
from app.models.reference import AMC, FundFamily, Scheme, SchemeVariant

client = TestClient(app)

TEST_AMC_NAME = "CAS Test Fund House"
TEST_ISIN = "INF000CAS001"


def _pdf_with_lines(lines: list[str]) -> bytes:
    """A one-page PDF whose content stream draws each string in `lines`
    on its own line (descending Y position), so pypdf's layout-mode
    extraction reconstructs real line breaks between them — matches how
    a genuine CAS PDF's text is laid out, just built directly rather than
    shipped as a binary fixture."""
    writer = PdfWriter()
    page = writer.add_blank_page(width=1000, height=50 * (len(lines) + 2))

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

    def _escape(s: str) -> str:
        return s.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")

    ops = ["BT", "/F1 10 Tf", f"10 {50 * (len(lines) + 1)} Td", "12 TL"]
    for line in lines:
        ops.append(f"({_escape(line)}) Tj")
        ops.append("T*")
    ops.append("ET")

    stream = DecodedStreamObject()
    stream.set_data("\n".join(ops).encode())
    page[NameObject("/Contents")] = writer._add_object(stream)

    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


CAS_LINES = [
    "Consolidated Account Statement",
    "01-Jan-2003 To 22-Sep-2026",
    "PORTFOLIO SUMMARY",
    "Date Transaction Amount Units Price Unit Balance",
    "Test Fund House Mutual Fund",
    "Folio No: 12345678 / 0    PAN: ABCDE1234F    KYC: OK PAN: OK",
    "Test Investor",
    f"900TESTGG-Test Fund House Flexi Cap Fund - Regular Plan - Growth (Non Demat) - ISIN: {TEST_ISIN}(Advisor: ARN-1)",
    "Nominee 1: Jane Doe    Nominee 2:    Nominee 3:",
    "Opening Unit Balance: 0.000",
    "10-Jun-2024   Purchase    999.95    38.129    26.222    38.129",
    "Closing Unit Balance: 38.129    NAV on 22-Sep-2026: INR 30.5    Total Cost Value: 999.95    Market Value on 22-Sep-2026: INR 1163.94",
    "Entry Load: Nil; Exit Load: Nil.",
    "Unknown Registrar Mutual Fund",
    "Folio No: 99998888 / 0    PAN: ABCDE1234F    KYC: OK PAN: OK",
    "Test Investor",
    "700ZZZGG-Some Other Fund - Regular Plan - Growth (Non Demat) - ISIN: INF999ZZZ999(Advisor: ARN-1)",
    "Nominee 1:    Nominee 2:    Nominee 3:",
    "Opening Unit Balance: 0.000",
    "11-Mar-2024   Purchase    500.00    50.000    10.00    50.000",
    "Closing Unit Balance: 50.000    NAV on 22-Sep-2026: INR 11.0    Total Cost Value: 500.00    Market Value on 22-Sep-2026: INR 550.00",
    "Entry Load: Nil; Exit Load: Nil.",
]


@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def test_scheme(db):
    amc = AMC(name=TEST_AMC_NAME)
    db.add(amc)
    db.flush()
    family = FundFamily(amc_id=amc.id, name=TEST_AMC_NAME)
    db.add(family)
    db.flush()
    scheme = Scheme(fund_family_id=family.id, name="CAS Test Flexi Cap Fund", category="Equity - Flexi Cap")
    db.add(scheme)
    db.flush()
    variant = SchemeVariant(scheme_id=scheme.id, plan="regular", option="growth", isin=TEST_ISIN)
    db.add(variant)
    db.commit()

    yield scheme

    db.query(SchemeVariant).filter(SchemeVariant.scheme_id == scheme.id).delete()
    db.query(Scheme).filter(Scheme.id == scheme.id).delete()
    db.query(FundFamily).filter(FundFamily.id == family.id).delete()
    db.query(AMC).filter(AMC.id == amc.id).delete()
    db.commit()


def test_parses_and_matches_a_holding_by_isin(test_scheme):
    pdf_bytes = _pdf_with_lines(CAS_LINES)
    response = client.post(
        "/api/portfolio/cas/parse",
        files={"file": ("cas.pdf", pdf_bytes, "application/pdf")},
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert len(body["matched_holdings"]) == 1
    matched = body["matched_holdings"][0]
    assert matched["fund_id"] == test_scheme.id
    assert matched["isin"] == TEST_ISIN
    assert matched["market_value"] == pytest.approx(1163.94)
    assert matched["weight_pct"] == pytest.approx(100.0)  # sole matched holding, renormalized to 100%

    assert len(body["unmatched_holdings"]) == 1
    unmatched = body["unmatched_holdings"][0]
    assert unmatched["isin"] == "INF999ZZZ999"
    assert unmatched["reason"] == "isin_not_found"

    assert body["total_market_value"] == pytest.approx(1163.94 + 550.00)
    assert body["matched_market_value"] == pytest.approx(1163.94)
    assert body["as_of_date"] == "2026-09-22"


def test_missing_password_on_encrypted_pdf_returns_422():
    from pypdf import PdfWriter as _Writer

    writer = _Writer()
    writer.add_blank_page(width=200, height=200)
    writer.encrypt(user_password="Abc@1234", owner_password="Abc@1234")
    buf = io.BytesIO()
    writer.write(buf)

    response = client.post(
        "/api/portfolio/cas/parse",
        files={"file": ("cas.pdf", buf.getvalue(), "application/pdf")},
    )
    assert response.status_code == 422
    assert "password" in response.json()["detail"].lower()


def test_correct_password_unlocks_encrypted_pdf(test_scheme):
    pdf_bytes = _pdf_with_lines(CAS_LINES)
    reader_writer = PdfWriter(clone_from=io.BytesIO(pdf_bytes))
    reader_writer.encrypt(user_password="Abc@1234", owner_password="Abc@1234")
    buf = io.BytesIO()
    reader_writer.write(buf)

    response = client.post(
        "/api/portfolio/cas/parse",
        files={"file": ("cas.pdf", buf.getvalue(), "application/pdf")},
        data={"password": "Abc@1234"},
    )
    assert response.status_code == 200, response.text
    assert len(response.json()["matched_holdings"]) == 1


def test_non_pdf_upload_returns_422():
    response = client.post(
        "/api/portfolio/cas/parse",
        files={"file": ("cas.pdf", b"not a pdf", "application/pdf")},
    )
    assert response.status_code == 422


def test_image_only_pdf_returns_clear_error():
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)  # no content stream at all -> no text
    buf = io.BytesIO()
    writer.write(buf)

    response = client.post(
        "/api/portfolio/cas/parse",
        files={"file": ("cas.pdf", buf.getvalue(), "application/pdf")},
    )
    assert response.status_code == 422
    assert "no extractable text" in response.json()["detail"].lower()
