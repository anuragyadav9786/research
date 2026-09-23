"""Tests for cas_parser.py against a real CAS text layout.

FIXTURE_TEXT below is a trimmed, anonymized transcription of a genuine
CAMS/KFintech Consolidated Account Statement's pypdf layout-mode
extraction (`page.extract_text(extraction_mode="layout")`) — the investor
name/PAN/email/address/mobile are replaced with obviously fake
placeholders, but every structural detail that matters to the parser
(line wording, spacing conventions, a folio block split across a page
break by a repeated header/footer, parenthesized negative
transaction amounts, annotation-only rows) is preserved exactly as
observed, not invented. This is what caught the real bug this test
guards against: pypdf's *default* extract_text() reads text in an order
that scrambles which ISIN/folio/market-value belong to which folio
across a multi-column page — only extraction_mode="layout" gets this
right (see cas_pdf.py). A naive single-page fixture wouldn't have caught
that; this one spans a page break on purpose.
"""
from __future__ import annotations

from datetime import date

from data_pipeline.normalization.cas_parser import parse_cas_text, statement_end_date

FIXTURE_TEXT = """
                                            Consolidated Account Statement
                                                                        01-Jan-2003 To 22-Sep-2026

 Email Id: test.investor@example.com                                                          This Consolidated Account Statement is brought to you as an investor
 Test Investor                                                                                friendly initiative by CAMS and KFintech.

                                                                             PORTFOLIO SUMMARY
                      Mutual Fund                                                    Cost Value                                                  Market Value
                                                                                         (INR)                                                        (INR)
      Acme Prudential Mutual Fund                                                      100.00                                                        100.38
      Acme Bond Mutual Fund                                                              0.00                                                          0.00
                         Total                                                         100.00                                                        100.38

Date          Transaction                                                                         Amount              Units             Price                Unit
                                                                                                      (INR)                              (INR)               Balance
Acme Bond Mutual Fund
Folio No: 11112222 / 0                                                                            PAN: ABCDE1234F                                KYC: OK PAN: OK
TEST INVESTOR
900XYZAG-Acme Bond Short Duration Fund - Regular Plan - Growth (Non Demat) - ISIN: INF000A001234(Advisor: ARN-999999)                                     Registrar :
                                                                                                                                                            KFINTECH
Nominee 1:      Jane Doe                                        Nominee 2:                                              Nominee 3:
                                                                                                                                         Opening Unit Balance: 0.000
10-Jun-2024   Purchase                                                                              499.98           38.129            13.113                 38.129
10-Jun-2024   *** Stamp Duty ***                                                                      0.02
06-Feb-2025   Redemption less TDS, STT                                                            (515.00)          (38.129)           13.507                   0.000
06-Feb-2025   *** STT Paid ***                                                                        0.01
Closing Unit Balance: 0.000              NAV on 22-Sep-2026: INR 15.397         Total Cost Value: 0.00                         Market Value on 22-Sep-2026: INR 0.00
Entry Load: Nil; Exit Load: Nil.

Acme Prudential Mutual Fund
Folio No: 46187451 / 13                                                                             PAN: ABCDE1234F                                 KYC: OK PAN: OK
Test Investor
                                                                                                                                                                Registrar :
P1565-Acme Prudential Liquid Fund - Growth (formerly Acme Prudential Liquid Plan) (Non-Demat) - ISIN: INF109K01VQ1(Advisor: ARN-314922)              CAMS

Nominee 1:                                                     Nominee 2:                                              Nominee 3:
                                                                                                                                            Opening Unit Balance: 0.000
26-Aug-2026   Purchase Appln : 61401 - ARN-314922/E596864                                            100.00             0.241          414.6015                    0.241
27-Aug-2026   ***Address Updated from KRA Data***

                                                                                                                                                           Page 1 of 2
                                          Consolidated Account Statement
                                                                    01-Jan-2003 To 22-Sep-2026


Date          Transaction                                                                             Amount             Units           Price              Unit
                                                                                                          (INR)                           (INR)             Balance
Closing Unit Balance: 0.241               NAV on 22-Sep-2026: INR 416.5194       Total Cost Value: 100.00                       Market Value on 22-Sep-2026: INR 100.38
Current: Entry Load - Nil. Exit Load w.e.f 20-Oct-2019 - If redeemed or switched out from Day1 - 0.0070%.
"""


def test_parses_only_the_currently_held_folio():
    holdings = parse_cas_text(FIXTURE_TEXT)
    assert len(holdings) == 1
    h = holdings[0]
    assert h.isin == "INF109K01VQ1"
    assert h.folio_no == "46187451 / 13"
    assert h.closing_units == 0.241
    assert h.market_value == 100.38
    assert "Acme Prudential Liquid Fund" in h.scheme_name


def test_excludes_fully_redeemed_folio():
    holdings = parse_cas_text(FIXTURE_TEXT)
    isins = [h.isin for h in holdings]
    assert "INF000A001234" not in isins


def test_statement_end_date_parsed():
    assert statement_end_date(FIXTURE_TEXT) == date(2026, 9, 22)


def test_empty_text_yields_no_holdings():
    assert parse_cas_text("") == []


def test_text_with_no_folios_yields_no_holdings():
    assert parse_cas_text("This is not a CAS statement at all.") == []
