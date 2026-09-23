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

from datetime import date

from app.core.database import SessionLocal
from app.main import app
from app.models.reference import AMC, FundFamily, Scheme, SchemeVariant, Security, Sector
from app.models.timeseries import DataSource, NavHistory, PortfolioHolding, PortfolioSnapshot

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
    db.flush()

    source = db.query(DataSource).filter(DataSource.source_type == "manual").first()
    if source is None:
        source = DataSource(name="TEST FIXTURE SOURCE", source_type="manual")
        db.add(source)
        db.flush()
    # Deliberately different from the CAS's own stated "NAV on 22-Sep-2026:
    # INR 30.5" -- proves the overview uses this platform's own NAV data,
    # not just echoing the statement's figure.
    db.add(NavHistory(scheme_variant_id=variant.id, date=date(2026, 9, 22), nav=32.0, source_id=source.id))
    db.commit()

    yield scheme

    db.query(NavHistory).filter(NavHistory.scheme_variant_id == variant.id).delete()
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

    overview = body["overview"]
    assert overview["matched_scheme_count"] == 1
    assert overview["unmatched_schemes"] == [{"isin": "INF999ZZZ999", "scheme_name": "Some Other Fund - Regular Plan - Growth (Non Demat)"}]

    scheme_overview = overview["per_scheme"][0]
    assert scheme_overview["fund_id"] == test_scheme.id
    assert scheme_overview["invested_amount"] == pytest.approx(999.95)
    assert scheme_overview["realized_gain"] == pytest.approx(0.0)
    assert scheme_overview["remaining_units"] == pytest.approx(38.129)
    # cost_per_unit = amount/units from the Purchase row -- not necessarily
    # bit-identical to the row's separately-reported "Price" column (26.222),
    # which can carry its own independent rounding in the RTA's own record.
    assert scheme_overview["weighted_average_purchase_nav"] == pytest.approx(999.95 / 38.129, abs=1e-4)
    # Uses OUR OWN NAV (32.0), not the CAS's own stated 30.5.
    assert scheme_overview["current_nav"] == pytest.approx(32.0)
    assert scheme_overview["current_value"] == pytest.approx(38.129 * 32.0, abs=0.01)
    assert scheme_overview["unrealized_gain"] == pytest.approx(38.129 * 32.0 - 999.95, abs=0.01)
    # Sole matched, priced holding -> 100% weight and 100% of total gain.
    assert scheme_overview["weight_pct"] == pytest.approx(100.0)
    assert scheme_overview["gain"] == pytest.approx(38.129 * 32.0 - 999.95, abs=0.01)
    assert scheme_overview["contribution_to_gain_pct"] == pytest.approx(100.0)
    assert scheme_overview["scheme_xirr_pct"] is not None
    assert scheme_overview["scheme_xirr_pct"] == pytest.approx(overview["portfolio_xirr_pct"], abs=0.01)

    # A single lumpsum Purchase, no SIP installments.
    purchase_behavior = scheme_overview["purchase_behavior"]
    assert purchase_behavior["purchase_count"] == 1
    assert purchase_behavior["lumpsum_count"] == 1
    assert purchase_behavior["sip_installment_count"] == 0
    assert purchase_behavior["first_purchase_date"] == "2024-06-10"
    assert purchase_behavior["latest_purchase_date"] == "2024-06-10"
    assert purchase_behavior["lowest_purchase_nav"] == pytest.approx(999.95 / 38.129, abs=1e-4)
    assert purchase_behavior["highest_purchase_nav"] == pytest.approx(999.95 / 38.129, abs=1e-4)
    assert purchase_behavior["average_purchase_nav"] == pytest.approx(999.95 / 38.129, abs=1e-4)

    # One Purchase transaction, in the sole matched scheme -- the other
    # holding's transactions are excluded entirely (unmatched).
    activity = {row["transaction_type"]: row for row in overview["transaction_activity"]}
    assert activity.keys() == {"PURCHASE"}
    assert activity["PURCHASE"]["count"] == 1
    assert activity["PURCHASE"]["total_amount"] == pytest.approx(999.95)

    assert overview["total_invested"] == pytest.approx(999.95)
    assert overview["total_current_value"] == pytest.approx(38.129 * 32.0, abs=0.01)
    assert overview["total_realized_gain"] == pytest.approx(0.0)
    # A single Purchase followed by a positive terminal value -> a real,
    # solvable, positive money-weighted return.
    assert overview["portfolio_xirr_pct"] is not None
    assert 0 < overview["portfolio_xirr_pct"] < 50

    # A single matched holding -> degenerate but still-correct structure:
    # 100% concentration everywhere, one asset-class/style slice.
    structure = overview["structure"]
    assert structure["scheme_concentration"]["top1_pct"] == pytest.approx(100.0)
    assert structure["scheme_concentration"]["hhi"] == pytest.approx(10000.0)
    assert structure["scheme_concentration"]["hhi_label"] == "high_concentration"
    assert structure["amc_concentration"]["count"] == 1
    assert structure["category_concentration"]["count"] == 1
    assert structure["asset_allocation"] == [
        {"label": "Equity", "value": pytest.approx(38.129 * 32.0, abs=0.01), "weight_pct": pytest.approx(100.0)}
    ]
    assert structure["equity_style_allocation"] == [
        {"label": "Flexi Cap", "value": pytest.approx(38.129 * 32.0, abs=0.01), "weight_pct": pytest.approx(100.0)}
    ]

    # One open lot (never redeemed), bought 2024-06-10, priced as of the
    # scheme's own latest NAV date (2026-09-22) -> 834 days old, and no
    # realized sales at all -- reported as an explicit absence, not 0.
    holding_period = overview["holding_period"]
    assert holding_period["open_weighted_avg_days"] == 834
    assert holding_period["open_value_by_bucket"] == [
        {"label": "1-3 years", "value": pytest.approx(38.129 * 32.0, abs=0.01), "weight_pct": pytest.approx(100.0)}
    ]
    assert holding_period["realized_avg_days"] is None
    assert holding_period["realized_median_days"] is None
    assert holding_period["realized_consumption_count"] == 0


SECOND_TEST_AMC_NAME = "CAS Test Debt House"
SECOND_TEST_ISIN = "INF000CAS002"

TWO_SCHEME_CAS_LINES = [
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
    "Test Debt Fund House Mutual Fund",
    "Folio No: 55554444 / 0    PAN: ABCDE1234F    KYC: OK PAN: OK",
    "Test Investor",
    f"800DEBTGG-Test Debt Liquid Fund - Regular Plan - Growth (Non Demat) - ISIN: {SECOND_TEST_ISIN}(Advisor: ARN-1)",
    "Nominee 1:    Nominee 2:    Nominee 3:",
    "Opening Unit Balance: 0.000",
    "11-Mar-2024   Purchase    2000.00    100.000    20.00    100.000",
    "Closing Unit Balance: 100.000    NAV on 22-Sep-2026: INR 21.0    Total Cost Value: 2000.00    Market Value on 22-Sep-2026: INR 2100.00",
    "Entry Load: Nil; Exit Load: Nil.",
]


@pytest.fixture
def second_test_scheme(db):
    amc = AMC(name=SECOND_TEST_AMC_NAME)
    db.add(amc)
    db.flush()
    family = FundFamily(amc_id=amc.id, name=SECOND_TEST_AMC_NAME)
    db.add(family)
    db.flush()
    scheme = Scheme(fund_family_id=family.id, name="CAS Test Debt Liquid Fund", category="Debt - Liquid")
    db.add(scheme)
    db.flush()
    variant = SchemeVariant(scheme_id=scheme.id, plan="regular", option="growth", isin=SECOND_TEST_ISIN)
    db.add(variant)
    db.flush()

    source = db.query(DataSource).filter(DataSource.source_type == "manual").first()
    if source is None:
        source = DataSource(name="TEST FIXTURE SOURCE", source_type="manual")
        db.add(source)
        db.flush()
    db.add(NavHistory(scheme_variant_id=variant.id, date=date(2026, 9, 22), nav=22.0, source_id=source.id))
    db.commit()

    yield scheme

    db.query(NavHistory).filter(NavHistory.scheme_variant_id == variant.id).delete()
    db.query(SchemeVariant).filter(SchemeVariant.scheme_id == scheme.id).delete()
    db.query(Scheme).filter(Scheme.id == scheme.id).delete()
    db.query(FundFamily).filter(FundFamily.id == family.id).delete()
    db.query(AMC).filter(AMC.id == amc.id).delete()
    db.commit()


def test_portfolio_structure_across_two_matched_holdings_in_different_amcs_and_asset_classes(
    test_scheme, second_test_scheme
):
    pdf_bytes = _pdf_with_lines(TWO_SCHEME_CAS_LINES)
    response = client.post(
        "/api/portfolio/cas/parse",
        files={"file": ("cas.pdf", pdf_bytes, "application/pdf")},
    )
    assert response.status_code == 200, response.text
    overview = response.json()["overview"]
    assert overview["matched_scheme_count"] == 2

    equity_value = 38.129 * 32.0  # first scheme's current value, from its own fixture NAV
    debt_value = 100.0 * 22.0  # second scheme's current value
    total_value = equity_value + debt_value

    structure = overview["structure"]

    # Two AMCs, two categories -> neither concentration summary is 100% on
    # a single group; both count as 2 distinct groups.
    assert structure["amc_concentration"]["count"] == 2
    assert structure["category_concentration"]["count"] == 2
    assert structure["amc_concentration"]["top1_pct"] < 100.0
    assert structure["category_concentration"]["top1_pct"] < 100.0

    asset_allocation = {slice_["label"]: slice_ for slice_ in structure["asset_allocation"]}
    assert set(asset_allocation.keys()) == {"Equity", "Debt"}
    assert asset_allocation["Equity"]["value"] == pytest.approx(equity_value, abs=0.01)
    assert asset_allocation["Equity"]["weight_pct"] == pytest.approx((equity_value / total_value) * 100, abs=0.1)
    assert asset_allocation["Debt"]["value"] == pytest.approx(debt_value, abs=0.01)

    # Equity style allocation only covers the equity scheme -- the debt
    # scheme contributes nothing to it, not a misleading "Debt" style row.
    assert len(structure["equity_style_allocation"]) == 1
    assert structure["equity_style_allocation"][0]["label"] == "Flexi Cap"
    assert structure["equity_style_allocation"][0]["value"] == pytest.approx(equity_value, abs=0.01)

    amc_allocation_labels = {slice_["label"] for slice_ in structure["amc_allocation"]}
    assert amc_allocation_labels == {TEST_AMC_NAME, SECOND_TEST_AMC_NAME}

    # Both schemes are fully priced and both gained value -> weight_pct
    # and contribution_to_gain_pct each partition cleanly to 100%.
    by_isin = {s["isin"]: s for s in overview["per_scheme"]}
    assert sum(s["weight_pct"] for s in by_isin.values()) == pytest.approx(100.0, abs=0.01)
    assert sum(s["contribution_to_gain_pct"] for s in by_isin.values()) == pytest.approx(100.0, abs=0.01)
    assert by_isin[TEST_ISIN]["weight_pct"] == pytest.approx((equity_value / total_value) * 100, abs=0.1)
    assert by_isin[TEST_ISIN]["scheme_xirr_pct"] is not None
    assert by_isin[SECOND_TEST_ISIN]["scheme_xirr_pct"] is not None

    # Two distinct schemes, AMCs, categories -> a small, "Simple" complexity
    # footprint; one folio per scheme -> no duplication penalty in the score.
    complexity = overview["complexity"]
    assert complexity["scheme_count"] == 2
    assert complexity["amc_count"] == 2
    assert complexity["category_count"] == 2
    assert complexity["asset_class_count"] == 2  # Equity + Debt
    assert complexity["folio_count"] == 2
    assert complexity["complexity_score"] == pytest.approx(2 * 6 + 2 * 4 + 2 * 3)
    assert complexity["complexity_label"] == "Simple"

    # Two lumpsum purchases, no switches or redemptions at all.
    behavior = overview["investor_behavior"]
    assert behavior["investing_since"] == "2024-03-11"
    assert behavior["last_activity_date"] == "2024-06-10"
    assert behavior["investing_span_days"] == 91
    assert behavior["total_switched_amount"] == pytest.approx(0.0)
    assert behavior["switch_ratio_pct"] == pytest.approx(0.0)
    assert behavior["total_redeemed_amount"] == pytest.approx(0.0)
    assert behavior["redemption_ratio_pct"] == pytest.approx(0.0)


REDEMPTION_CAS_LINES = [
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
    "06-Feb-2025   Redemption    (500.00)    (20.000)    25.00    18.129",
    "Closing Unit Balance: 18.129    NAV on 22-Sep-2026: INR 30.5    Total Cost Value: 475.00    Market Value on 22-Sep-2026: INR 553.00",
    "Entry Load: Nil; Exit Load: Nil.",
]


def test_holding_period_reflects_a_realized_partial_redemption(test_scheme):
    pdf_bytes = _pdf_with_lines(REDEMPTION_CAS_LINES)
    response = client.post(
        "/api/portfolio/cas/parse",
        files={"file": ("cas.pdf", pdf_bytes, "application/pdf")},
    )
    assert response.status_code == 200, response.text
    overview = response.json()["overview"]

    scheme_overview = overview["per_scheme"][0]
    # 20 units, bought 10-Jun-2024 at 26.222/unit (999.95/38.129), sold
    # 06-Feb-2025 at 25.00/unit -> a realized loss, FIFO-matched against
    # the only lot available.
    cost_per_unit = 999.95 / 38.129
    assert scheme_overview["realized_gain"] == pytest.approx(20 * (25.00 - cost_per_unit), abs=0.01)
    assert scheme_overview["remaining_units"] == pytest.approx(18.129)

    holding_period = overview["holding_period"]
    # The one redemption was held for exactly 241 days (10-Jun-2024 to
    # 06-Feb-2025) -- with a single realized consumption, avg == median.
    assert holding_period["realized_consumption_count"] == 1
    assert holding_period["realized_avg_days"] == 241
    assert holding_period["realized_median_days"] == 241

    # One Purchase, one Redemption -- purchase_behavior only ever counts
    # the Purchase (the redemption doesn't add a "purchase"), and
    # transaction_activity shows both at the portfolio level.
    purchase_behavior = scheme_overview["purchase_behavior"]
    assert purchase_behavior["purchase_count"] == 1
    assert purchase_behavior["first_purchase_date"] == purchase_behavior["latest_purchase_date"] == "2024-06-10"

    activity = {row["transaction_type"]: row for row in overview["transaction_activity"]}
    assert activity.keys() == {"PURCHASE", "REDEMPTION"}
    assert activity["PURCHASE"] == {"transaction_type": "PURCHASE", "count": 1, "total_amount": pytest.approx(999.95)}
    assert activity["REDEMPTION"] == {"transaction_type": "REDEMPTION", "count": 1, "total_amount": pytest.approx(500.0)}
    # The remaining 18.129 units are still the original lot, still open,
    # so open-position holding period is unaffected by the redemption.
    assert holding_period["open_weighted_avg_days"] == 834

    # 500 of the 999.95 invested has since come back via redemption ->
    # ~50% redemption ratio, and no switch activity at all in this fixture.
    behavior = overview["investor_behavior"]
    assert behavior["total_redeemed_amount"] == pytest.approx(500.0)
    assert behavior["redemption_ratio_pct"] == pytest.approx((500.0 / 999.95) * 100, abs=0.01)
    assert behavior["total_switched_amount"] == pytest.approx(0.0)
    assert behavior["switch_ratio_pct"] == pytest.approx(0.0)


DUPLICATE_FOLIO_CAS_LINES = [
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
    "Test Fund House Mutual Fund",
    "Folio No: 99991111 / 0    PAN: ABCDE1234F    KYC: OK PAN: OK",
    "Test Investor",
    f"900TESTGG-Test Fund House Flexi Cap Fund - Regular Plan - Growth (Non Demat) - ISIN: {TEST_ISIN}(Advisor: ARN-1)",
    "Nominee 1: Jane Doe    Nominee 2:    Nominee 3:",
    "Opening Unit Balance: 0.000",
    "15-Jul-2024   Purchase    500.00    18.000    27.778    18.000",
    "Closing Unit Balance: 18.000    NAV on 22-Sep-2026: INR 30.5    Total Cost Value: 500.00    Market Value on 22-Sep-2026: INR 549.00",
    "Entry Load: Nil; Exit Load: Nil.",
]


def test_complexity_counts_two_folios_of_the_same_scheme_separately(test_scheme):
    # The same ISIN across two folios is merged into one scheme
    # everywhere else in this overview (matched by ISIN) -- complexity's
    # folio_count is the one place that duplication becomes visible.
    pdf_bytes = _pdf_with_lines(DUPLICATE_FOLIO_CAS_LINES)
    response = client.post(
        "/api/portfolio/cas/parse",
        files={"file": ("cas.pdf", pdf_bytes, "application/pdf")},
    )
    assert response.status_code == 200, response.text
    overview = response.json()["overview"]

    assert overview["matched_scheme_count"] == 1
    assert overview["per_scheme"][0]["invested_amount"] == pytest.approx(999.95 + 500.0)

    complexity = overview["complexity"]
    assert complexity["scheme_count"] == 1
    assert complexity["folio_count"] == 2
    assert complexity["complexity_score"] == pytest.approx(1 * 6 + 1 * 4 + 1 * 3 + (2 - 1) * 8)
    assert complexity["complexity_label"] == "Simple"


TWR_TEST_AMC_NAME = "CAS Test TWR Fund House"
TWR_TEST_ISIN = "INF000CAS004"

TWR_CAS_LINES = [
    "Consolidated Account Statement",
    "01-Jan-2003 To 22-Sep-2026",
    "PORTFOLIO SUMMARY",
    "Date Transaction Amount Units Price Unit Balance",
    "Test TWR Fund House Mutual Fund",
    "Folio No: 33332222 / 0    PAN: ABCDE1234F    KYC: OK PAN: OK",
    "Test Investor",
    f"900TWRXGG-Test TWR Flexi Cap Fund - Regular Plan - Growth (Non Demat) - ISIN: {TWR_TEST_ISIN}(Advisor: ARN-1)",
    "Nominee 1:    Nominee 2:    Nominee 3:",
    "Opening Unit Balance: 0.000",
    "10-Jun-2024   Purchase    1000.00    40.000    25.000    40.000",
    "Closing Unit Balance: 40.000    NAV on 13-Jun-2024: INR 26.125    Total Cost Value: 1000.00    Market Value on 13-Jun-2024: INR 1045.00",
    "Entry Load: Nil; Exit Load: Nil.",
]


@pytest.fixture
def twr_test_scheme(db):
    # Four NAV points, chosen to produce known, hand-checkable sub-period
    # returns once combined with the single 10-Jun-2024 purchase below:
    # 06-10 -> 06-11: +10%, 06-11 -> 06-12: 0%, 06-12 -> 06-13: -5%.
    amc = AMC(name=TWR_TEST_AMC_NAME)
    db.add(amc)
    db.flush()
    family = FundFamily(amc_id=amc.id, name=TWR_TEST_AMC_NAME)
    db.add(family)
    db.flush()
    scheme = Scheme(fund_family_id=family.id, name="CAS Test TWR Flexi Cap Fund", category="Equity - Flexi Cap")
    db.add(scheme)
    db.flush()
    variant = SchemeVariant(scheme_id=scheme.id, plan="regular", option="growth", isin=TWR_TEST_ISIN)
    db.add(variant)
    db.flush()

    source = db.query(DataSource).filter(DataSource.source_type == "manual").first()
    if source is None:
        source = DataSource(name="TEST FIXTURE SOURCE", source_type="manual")
        db.add(source)
        db.flush()
    for nav_date, nav in [
        (date(2024, 6, 10), 25.0),
        (date(2024, 6, 11), 27.5),
        (date(2024, 6, 12), 27.5),
        (date(2024, 6, 13), 26.125),
    ]:
        db.add(NavHistory(scheme_variant_id=variant.id, date=nav_date, nav=nav, source_id=source.id))
    db.commit()

    yield scheme

    db.query(NavHistory).filter(NavHistory.scheme_variant_id == variant.id).delete()
    db.query(SchemeVariant).filter(SchemeVariant.scheme_id == scheme.id).delete()
    db.query(Scheme).filter(Scheme.id == scheme.id).delete()
    db.query(FundFamily).filter(FundFamily.id == family.id).delete()
    db.query(AMC).filter(AMC.id == amc.id).delete()
    db.commit()


def test_time_weighted_return_matches_hand_computed_sub_period_returns(twr_test_scheme):
    pdf_bytes = _pdf_with_lines(TWR_CAS_LINES)
    response = client.post(
        "/api/portfolio/cas/parse",
        files={"file": ("cas.pdf", pdf_bytes, "application/pdf")},
    )
    assert response.status_code == 200, response.text
    twr = response.json()["overview"]["time_weighted_return"]

    assert twr["priced_scheme_count"] == 1
    assert twr["start_date"] == "2024-06-10"
    assert twr["end_date"] == "2024-06-13"

    # Chain-linking +10%, 0%, -5% -> 1.10 * 1.00 * 0.95 - 1 = 4.5%. The
    # purchase itself (10-Jun) is cash-flow-neutralized, contributing no
    # sub-period return of its own -- only 3 later NAV points do.
    assert twr["cumulative_twr_pct"] == pytest.approx(4.5, abs=0.01)

    # Synthetic NAV from those same returns: 110, 110, 104.5 -> peaks at
    # the first date reaching 110 (06-11), troughs at 06-13, a real -5%
    # drawdown that hasn't recovered within this short window.
    assert twr["max_drawdown_pct"] == pytest.approx(-5.0, abs=0.01)
    assert twr["drawdown_peak_date"] == "2024-06-11"
    assert twr["drawdown_trough_date"] == "2024-06-13"
    assert twr["drawdown_recovered"] is False
    assert twr["drawdown_recovery_date"] is None

    assert twr["volatility_pct"] is not None
    # A 3-day span is nowhere near a year -- annualizing it would blow a
    # 4.5% return up into an absurd figure, so it's null, matching the
    # same >=1yr gate fund_analytics_service.py's rolling returns use.
    assert twr["annualized_twr_pct"] is None


def test_time_weighted_return_is_all_null_when_no_matched_scheme_has_nav_history():
    pdf_bytes = _pdf_with_lines(CAS_LINES)
    response = client.post(
        "/api/portfolio/cas/parse",
        files={"file": ("cas.pdf", pdf_bytes, "application/pdf")},
    )
    assert response.status_code == 200, response.text
    overview = response.json()["overview"]
    # CAS_LINES's only holdings are TEST_ISIN (unmatched here, no fixture)
    # and an always-unmatched ISIN -- nothing is priced, so the
    # reconstruction reports its absence explicitly rather than a
    # misleading 0%.
    twr = overview["time_weighted_return"]
    assert twr == {
        "cumulative_twr_pct": None,
        "annualized_twr_pct": None,
        "volatility_pct": None,
        "max_drawdown_pct": None,
        "drawdown_peak_date": None,
        "drawdown_trough_date": None,
        "drawdown_recovery_date": None,
        "drawdown_recovered": None,
        "priced_scheme_count": 0,
        "start_date": None,
        "end_date": None,
    }
    # Nothing matched at all -> no matched-scheme transactions to break
    # down, an empty list rather than a padded row of zeros.
    assert overview["transaction_activity"] == []
    # Same reasoning for investment timing -- nothing to classify.
    assert overview["investment_timing"]["regime_breakdown"] == []
    assert overview["investment_timing"]["total_classified_invested_amount"] == 0.0
    assert overview["investment_timing"]["unclassified_invested_amount"] == 0.0
    assert overview["investment_timing"]["unclassified_purchase_count"] == 0


SIP_CONSISTENCY_CAS_LINES = [
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
    "10-Jul-2024   Sys. Investment    500.00    18.500    27.027    56.629",
    "12-Aug-2024   Sys. Investment    500.00    18.000    27.778    74.629",
    "10-Sep-2024   Sys. Investment    500.00    17.800    28.090    92.429",
    "Closing Unit Balance: 92.429    NAV on 22-Sep-2026: INR 30.5    Total Cost Value: 2499.95    Market Value on 22-Sep-2026: INR 2819.08",
    "Entry Load: Nil; Exit Load: Nil.",
]


def test_sip_consistency_and_investment_timing_for_classified_purchases(test_scheme):
    pdf_bytes = _pdf_with_lines(SIP_CONSISTENCY_CAS_LINES)
    response = client.post(
        "/api/portfolio/cas/parse",
        files={"file": ("cas.pdf", pdf_bytes, "application/pdf")},
    )
    assert response.status_code == 200, response.text
    overview = response.json()["overview"]

    scheme_overview = overview["per_scheme"][0]
    purchase_behavior = scheme_overview["purchase_behavior"]
    assert purchase_behavior["purchase_count"] == 4
    assert purchase_behavior["lumpsum_count"] == 1
    assert purchase_behavior["sip_installment_count"] == 3

    # Installments on 10-Jul, 12-Aug, 10-Sep-2024 -> gaps of 33 and 29
    # days. The lumpsum Purchase on 10-Jun isn't a SIP installment, so it
    # doesn't factor into the gaps at all.
    sip = scheme_overview["sip_consistency"]
    assert sip["installment_count"] == 3
    assert sip["first_installment_date"] == "2024-07-10"
    assert sip["latest_installment_date"] == "2024-09-10"
    assert sip["min_gap_days"] == 29
    assert sip["max_gap_days"] == 33
    assert sip["average_gap_days"] == pytest.approx(31.0)
    assert sip["gap_consistency_pct"] == pytest.approx(93.5, abs=0.1)

    # All 4 purchases (2023-04-01 to 2025-03-31 is this environment's
    # seeded "Bull" market-regime window -- illustrative sample data, per
    # the response's own methodology_note) fall inside it.
    timing = overview["investment_timing"]
    assert timing["unclassified_purchase_count"] == 0
    assert timing["unclassified_invested_amount"] == pytest.approx(0.0)
    assert len(timing["regime_breakdown"]) == 1
    bull = timing["regime_breakdown"][0]
    assert bull["regime_type"] == "bull"
    assert bull["purchase_count"] == 4
    assert bull["invested_amount"] == pytest.approx(999.95 + 500 + 500 + 500)
    assert bull["weight_pct"] == pytest.approx(100.0)
    assert "illustrative" in timing["methodology_note"].lower()


UNCLASSIFIED_TIMING_CAS_LINES = [
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
    "15-Jan-2020   Purchase    999.95    38.129    26.222    38.129",
    "Closing Unit Balance: 38.129    NAV on 22-Sep-2026: INR 30.5    Total Cost Value: 999.95    Market Value on 22-Sep-2026: INR 1163.94",
    "Entry Load: Nil; Exit Load: Nil.",
]


def test_investment_timing_reports_a_purchase_outside_every_known_regime_as_unclassified(test_scheme):
    # 15-Jan-2020 is before this environment's earliest seeded market
    # regime (2021-04-01) -- never guessed into the nearest one.
    pdf_bytes = _pdf_with_lines(UNCLASSIFIED_TIMING_CAS_LINES)
    response = client.post(
        "/api/portfolio/cas/parse",
        files={"file": ("cas.pdf", pdf_bytes, "application/pdf")},
    )
    assert response.status_code == 200, response.text
    timing = response.json()["overview"]["investment_timing"]

    assert timing["regime_breakdown"] == []
    assert timing["total_classified_invested_amount"] == pytest.approx(0.0)
    assert timing["unclassified_purchase_count"] == 1
    assert timing["unclassified_invested_amount"] == pytest.approx(999.95)


LOOK_THROUGH_TEST_ISIN = "INF000CAS006"

LOOK_THROUGH_CAS_LINES = [
    "Consolidated Account Statement",
    "01-Jan-2003 To 22-Sep-2026",
    "PORTFOLIO SUMMARY",
    "Date Transaction Amount Units Price Unit Balance",
    "Test Fund House Mutual Fund",
    "Folio No: 12345678 / 0    PAN: ABCDE1234F    KYC: OK PAN: OK",
    "Test Investor",
    f"900TESTGG-Test Fund House Flexi Cap Fund - Regular Plan - Growth (Non Demat) - ISIN: {LOOK_THROUGH_TEST_ISIN}(Advisor: ARN-1)",
    "Nominee 1: Jane Doe    Nominee 2:    Nominee 3:",
    "Opening Unit Balance: 0.000",
    "10-Jun-2024   Purchase    999.95    38.129    26.222    38.129",
    "Closing Unit Balance: 38.129    NAV on 22-Sep-2026: INR 30.5    Total Cost Value: 999.95    Market Value on 22-Sep-2026: INR 1163.94",
    "Entry Load: Nil; Exit Load: Nil.",
]


@pytest.fixture
def look_through_test_scheme(db):
    amc = AMC(name="CAS Test Look-Through Fund House")
    db.add(amc)
    db.flush()
    family = FundFamily(amc_id=amc.id, name="CAS Test Look-Through Fund House")
    db.add(family)
    db.flush()
    scheme = Scheme(fund_family_id=family.id, name="CAS Test Look-Through Fund", category="Equity - Flexi Cap")
    db.add(scheme)
    db.flush()
    variant = SchemeVariant(scheme_id=scheme.id, plan="regular", option="growth", isin=LOOK_THROUGH_TEST_ISIN)
    db.add(variant)
    db.flush()

    source = db.query(DataSource).filter(DataSource.source_type == "manual").first()
    if source is None:
        source = DataSource(name="TEST FIXTURE SOURCE", source_type="manual")
        db.add(source)
        db.flush()
    db.add(NavHistory(scheme_variant_id=variant.id, date=date(2026, 9, 22), nav=32.0, source_id=source.id))

    tech = Sector(name="CAS Test Technology Sector")
    financials = Sector(name="CAS Test Financials Sector")
    db.add_all([tech, financials])
    db.flush()
    security_a = Security(isin="INF000SECA0001", name="CAS Test Security A", sector_id=tech.id, market_cap_category="large_cap")
    security_b = Security(isin="INF000SECB0001", name="CAS Test Security B", sector_id=financials.id, market_cap_category="mid_cap")
    db.add_all([security_a, security_b])
    db.flush()

    snapshot = PortfolioSnapshot(scheme_id=scheme.id, as_of_date=date(2026, 9, 1), source_id=source.id)
    db.add(snapshot)
    db.flush()
    db.add_all([
        PortfolioHolding(snapshot_id=snapshot.id, security_id=security_a.id, weight_pct=60.0),
        PortfolioHolding(snapshot_id=snapshot.id, security_id=security_b.id, weight_pct=40.0),
    ])
    db.commit()

    yield scheme

    db.query(PortfolioHolding).filter(PortfolioHolding.snapshot_id == snapshot.id).delete()
    db.query(PortfolioSnapshot).filter(PortfolioSnapshot.id == snapshot.id).delete()
    db.query(Security).filter(Security.id.in_([security_a.id, security_b.id])).delete()
    db.query(Sector).filter(Sector.id.in_([tech.id, financials.id])).delete()
    db.query(NavHistory).filter(NavHistory.scheme_variant_id == variant.id).delete()
    db.query(SchemeVariant).filter(SchemeVariant.scheme_id == scheme.id).delete()
    db.query(Scheme).filter(Scheme.id == scheme.id).delete()
    db.query(FundFamily).filter(FundFamily.id == family.id).delete()
    db.query(AMC).filter(AMC.id == amc.id).delete()
    db.commit()


def test_look_through_analysis_reuses_the_multi_fund_engine(look_through_test_scheme):
    pdf_bytes = _pdf_with_lines(LOOK_THROUGH_CAS_LINES)
    response = client.post(
        "/api/portfolio/cas/parse",
        files={"file": ("cas.pdf", pdf_bytes, "application/pdf")},
    )
    assert response.status_code == 200, response.text
    look_through = response.json()["overview"]["look_through_analysis"]

    assert look_through is not None
    assert len(look_through["funds"]) == 1
    assert look_through["funds"][0]["weight_pct"] == pytest.approx(100.0)

    # Sole holding at 100% weight -> combined sector allocation is exactly
    # this scheme's own disclosed 60/40 split, unchanged by any blending.
    sector_by_name = {s["label"]: s["weight_pct"] for s in look_through["sector_allocation"]}
    assert sector_by_name["CAS Test Technology Sector"] == pytest.approx(60.0)
    assert sector_by_name["CAS Test Financials Sector"] == pytest.approx(40.0)

    top_holdings = {h["security_name"]: h["effective_weight_pct"] for h in look_through["combined_top_holdings"]}
    assert top_holdings["CAS Test Security A"] == pytest.approx(60.0)
    assert top_holdings["CAS Test Security B"] == pytest.approx(40.0)

    # A single fund has no pairs to compare -- overlap is structurally empty.
    assert look_through["pairwise_overlap"] == []


def test_look_through_analysis_is_null_when_nothing_is_currently_valued():
    pdf_bytes = _pdf_with_lines(CAS_LINES)
    response = client.post(
        "/api/portfolio/cas/parse",
        files={"file": ("cas.pdf", pdf_bytes, "application/pdf")},
    )
    assert response.status_code == 200, response.text
    assert response.json()["overview"]["look_through_analysis"] is None


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
