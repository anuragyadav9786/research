"""Integration tests for POST /api/portfolio/cas/compare, against the real
local Postgres database. Reuses test_cas_upload.py's PDF-building helper
and scheme fixtures rather than duplicating them.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.integration.test_cas_upload import (
    SECOND_TEST_ISIN,
    TEST_ISIN,
    _pdf_with_lines,
    db,  # noqa: F401 - pytest fixture, depended on by test_scheme/second_test_scheme
    second_test_scheme,  # noqa: F401 - pytest fixture, used via test function parameters
    test_scheme,  # noqa: F401 - pytest fixture, used via test function parameters
)

client = TestClient(app)

# An earlier statement: only the equity scheme, one purchase, generated
# well before the "current" statement below.
PREVIOUS_CAS_LINES = [
    "Consolidated Account Statement",
    "01-Jan-2003 To 22-Mar-2025",
    "PORTFOLIO SUMMARY",
    "Date Transaction Amount Units Price Unit Balance",
    "Test Fund House Mutual Fund",
    "Folio No: 12345678 / 0    PAN: ABCDE1234F    KYC: OK PAN: OK",
    "Test Investor",
    f"900TESTGG-Test Fund House Flexi Cap Fund - Regular Plan - Growth (Non Demat) - ISIN: {TEST_ISIN}(Advisor: ARN-1)",
    "Nominee 1: Jane Doe    Nominee 2:    Nominee 3:",
    "Opening Unit Balance: 0.000",
    "10-Jun-2024   Purchase    999.95    38.129    26.222    38.129",
    "Closing Unit Balance: 38.129    NAV on 22-Mar-2025: INR 28.0    Total Cost Value: 999.95    Market Value on 22-Mar-2025: INR 1067.61",
    "Entry Load: Nil; Exit Load: Nil.",
]

# The later statement: the same equity scheme with an additional SIP
# installment (its holding grew), plus a brand-new debt scheme.
CURRENT_CAS_LINES = [
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
    "Closing Unit Balance: 56.629    NAV on 22-Sep-2026: INR 30.5    Total Cost Value: 1499.95    Market Value on 22-Sep-2026: INR 1727.19",
    "Entry Load: Nil; Exit Load: Nil.",
    "Test Debt Fund House Mutual Fund",
    "Folio No: 55554444 / 0    PAN: ABCDE1234F    KYC: OK PAN: OK",
    "Test Investor",
    f"800DEBTGG-Test Debt Liquid Fund - Regular Plan - Growth (Non Demat) - ISIN: {SECOND_TEST_ISIN}(Advisor: ARN-1)",
    "Nominee 1:    Nominee 2:    Nominee 3:",
    "Opening Unit Balance: 0.000",
    "11-Mar-2025   Purchase    2000.00    100.000    20.00    100.000",
    "Closing Unit Balance: 100.000    NAV on 22-Sep-2026: INR 21.0    Total Cost Value: 2000.00    Market Value on 22-Sep-2026: INR 2100.00",
    "Entry Load: Nil; Exit Load: Nil.",
]


def test_compare_detects_growth_a_new_scheme_and_allocation_drift(test_scheme, second_test_scheme):
    response = client.post(
        "/api/portfolio/cas/compare",
        files={
            "previous_file": ("previous.pdf", _pdf_with_lines(PREVIOUS_CAS_LINES), "application/pdf"),
            "current_file": ("current.pdf", _pdf_with_lines(CURRENT_CAS_LINES), "application/pdf"),
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["dates_swapped"] is False
    assert body["previous_as_of_date"] == "2025-03-22"
    assert body["current_as_of_date"] == "2026-09-22"
    assert body["span_days"] == 549

    # Equity scheme invested 999.95 -> 1499.95 via one added SIP
    # installment; the debt scheme is brand new in the current statement.
    assert body["total_invested_previous"] == pytest.approx(999.95)
    assert body["total_invested_current"] == pytest.approx(999.95 + 500.0 + 2000.0)
    assert body["total_invested_change"] == pytest.approx(2500.0)

    # Both snapshots' values are priced at OUR platform's latest NAV
    # (32.0 / 22.0) regardless of each statement's own stated NAV, so
    # these changes reflect added units, not market movement in between.
    prev_equity_value = 38.129 * 32.0
    curr_equity_value = 56.629 * 32.0
    curr_debt_value = 100.0 * 22.0
    assert body["total_current_value_previous"] == pytest.approx(prev_equity_value, abs=0.01)
    assert body["total_current_value_current"] == pytest.approx(curr_equity_value + curr_debt_value, abs=0.01)
    assert body["total_current_value_change"] == pytest.approx(
        (curr_equity_value + curr_debt_value) - prev_equity_value, abs=0.01
    )

    # The debt scheme is new; the equity scheme is a scheme_change (held
    # in both, value and weight moved as a second scheme joined it).
    assert len(body["new_schemes"]) == 1
    assert body["new_schemes"][0]["isin"] == SECOND_TEST_ISIN
    assert body["new_schemes"][0]["current_value"] == pytest.approx(curr_debt_value, abs=0.01)
    assert body["exited_schemes"] == []

    assert len(body["scheme_changes"]) == 1
    equity_change = body["scheme_changes"][0]
    assert equity_change["isin"] == TEST_ISIN
    assert equity_change["value_change"] == pytest.approx(curr_equity_value - prev_equity_value, abs=0.01)
    assert equity_change["previous_weight_pct"] == pytest.approx(100.0)
    # Diluted from 100% to ~45% once a second scheme entered the portfolio.
    assert equity_change["current_weight_pct"] == pytest.approx(45.17, abs=0.1)
    assert equity_change["weight_pct_change"] == pytest.approx(-54.83, abs=0.1)

    drift_by_label = {d["label"]: d for d in body["asset_allocation_drift"]}
    assert drift_by_label["Equity"]["previous_weight_pct"] == pytest.approx(100.0)
    assert drift_by_label["Equity"]["current_weight_pct"] == pytest.approx(45.17, abs=0.1)
    assert drift_by_label["Debt"]["previous_weight_pct"] == pytest.approx(0.0)
    assert drift_by_label["Debt"]["current_weight_pct"] == pytest.approx(54.83, abs=0.1)


def test_compare_swaps_reversed_uploads_and_flags_it(test_scheme):
    # Deliberately pass the LATER statement as "previous" and the EARLIER
    # one as "current" -- the endpoint must correct this, not silently
    # report a nonsensical divestment.
    response = client.post(
        "/api/portfolio/cas/compare",
        files={
            "previous_file": ("later.pdf", _pdf_with_lines(CURRENT_CAS_LINES), "application/pdf"),
            "current_file": ("earlier.pdf", _pdf_with_lines(PREVIOUS_CAS_LINES), "application/pdf"),
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["dates_swapped"] is True
    assert body["previous_as_of_date"] == "2025-03-22"
    assert body["current_as_of_date"] == "2026-09-22"
