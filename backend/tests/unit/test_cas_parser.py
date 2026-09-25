"""Tests for cas_parser.py against a real CAS text layout.

FIXTURE_TEXT and SIP_SWITCH_FIXTURE_TEXT below are trimmed, anonymized
transcriptions of a genuine CAMS/KFintech Consolidated Account
Statement's pypdf layout-mode extraction
(`page.extract_text(extraction_mode="layout")`) — the investor
name/PAN/email/address/mobile are replaced with obviously fake
placeholders, but every structural detail that matters to the parser
(line wording, spacing conventions, a folio block split across a page
break by a repeated header/footer, parenthesized negative transaction
amounts, annotation-only rows, SIP installment numbering, Switch
In/Out wording) is preserved exactly as observed, not invented. This is
what caught the real bug this test guards against: pypdf's *default*
extract_text() reads text in an order that scrambles which
ISIN/folio/market-value belong to which folio across a multi-column
page — only extraction_mode="layout" gets this right (see cas_pdf.py). A
naive single-page fixture wouldn't have caught that; this one spans a
page break on purpose.
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
900XYZAG-Acme Bond Short Duration Fund - Regular Plan - Growth (Non Demat) - ISIN: INF000A00123(Advisor: ARN-999999)                                     Registrar :
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

SIP_SWITCH_FIXTURE_TEXT = """
                                         Consolidated Account Statement
                                                                01-Jan-2003 To 22-Sep-2026

 Email Id: test.investor@example.com                                                   This Consolidated Account Statement is brought to you as an investor

Date          Transaction                                                                         Amount              Units             Price                Unit
                                                                                                      (INR)                              (INR)               Balance
Acme Growth Mutual Fund
Folio No: 55556666 / 0                                                                            PAN: ABCDE1234F                                KYC: OK PAN: OK
Test Investor
700ZZZGG-Acme Growth Direct Fund - Direct Growth (Non Demat) - ISIN: INF336L01QN5(Advisor: DIRECT)                                                          Registrar :
                                                                                                                                                            KFINTECH
Nominee 1:      Jane Doe                                        Nominee 2:                                              Nominee 3:
                                                                                                                                         Opening Unit Balance: 0.000
03-Aug-2023   Switch In - From Acme Growth Regular Fund - Regular Growth- via MFCentral               5,865.98      492.017            11.9223                 492.017
03-Aug-2023   *** Stamp Duty ***                                                                           0.29
Closing Unit Balance: 492.017              NAV on 22-Sep-2026: INR 21.2040       Total Cost Value: 5865.98                      Market Value on 22-Sep-2026: INR 10437.66
Entry Load* : Nil

Acme SIP Mutual Fund
Folio No: 77778888 / 0                                                                             PAN: ABCDE1234F                                KYC: OK PAN: OK
Test Investor
900SIPGG-Acme SIP Small Cap Fund - Growth Plan Growth Option (Non Demat) - ISIN: INF204K01HY3(Advisor: ARN-0155)                                             Registrar :
                                                                                                                                                              KFINTECH
Nominee 1:      Jane Doe                                        Nominee 2:                                              Nominee 3:
                                                                                                                                            Opening Unit Balance: 0.000
13-Jun-2023   Sys. Investment New Purchase with SIP (1/121)                                          999.95             9.444          105.8802                    9.444
13-Jun-2023   *** Stamp Duty ***                                                                       0.05
11-Jul-2023   Sys. Investment (2/121)                                                                999.95             9.002          111.0790                  18.446
11-Jul-2023   *** Stamp Duty ***                                                                       0.05
27-Oct-2025   Lateral Shift Out (To IX (AG) F.No:477285782816)(To ACME NIFTY IT               (14,347.73)             (84.562)          169.6728                    0.005
              INDEX FUND - DIRECT GROWTH PLAN F.No:477285782816)
              less TDS, STT
27-Oct-2025 *** STT Paid ***                                                                          0.14
Closing Unit Balance: 0.005                NAV on 22-Sep-2026: INR 185.3650  Total Cost Value: 0.10                             Market Value on 22-Sep-2026: INR 0.93
"""


def test_parses_only_the_currently_held_folio():
    result = parse_cas_text(FIXTURE_TEXT)
    assert len(result.holdings) == 1
    h = result.holdings[0]
    assert h.isin == "INF109K01VQ1"
    assert h.folio_no == "46187451 / 13"
    assert h.closing_units == 0.241
    assert h.market_value == 100.38
    assert "Acme Prudential Liquid Fund" in h.scheme_name


def test_excludes_fully_redeemed_folio():
    result = parse_cas_text(FIXTURE_TEXT)
    isins = [h.isin for h in result.holdings]
    assert "INF000A00123" not in isins


def test_statement_end_date_parsed():
    assert statement_end_date(FIXTURE_TEXT) == date(2026, 9, 22)


def test_empty_text_yields_no_holdings_or_transactions():
    result = parse_cas_text("")
    assert result.holdings == []
    assert result.transactions == []


def test_text_with_no_folios_yields_no_holdings_or_transactions():
    result = parse_cas_text("This is not a CAS statement at all.")
    assert result.holdings == []
    assert result.transactions == []


def test_transactions_extracted_for_every_folio_including_fully_redeemed():
    result = parse_cas_text(FIXTURE_TEXT)
    isins = {t.isin for t in result.transactions}
    # Both folios have transactions, even the fully-redeemed one that's
    # excluded from `.holdings` -- the transaction ledger is not filtered
    # by current holding status.
    assert isins == {"INF000A00123", "INF109K01VQ1"}


def test_fee_and_status_annotation_rows_excluded_from_transactions():
    result = parse_cas_text(FIXTURE_TEXT)
    descriptions = [t.description for t in result.transactions]
    assert not any("Stamp Duty" in d for d in descriptions)
    assert not any("STT Paid" in d for d in descriptions)
    assert not any("Address Updated" in d for d in descriptions)
    # Exactly the 3 real transactions: Purchase, Redemption, Purchase.
    assert len(result.transactions) == 3


def test_purchase_and_redemption_signs_and_types():
    result = parse_cas_text(FIXTURE_TEXT)
    txns = [t for t in result.transactions if t.isin == "INF000A00123"]
    purchase, redemption = txns
    assert purchase.transaction_type == "PURCHASE"
    assert purchase.transaction_date == date(2024, 6, 10)
    assert purchase.amount == 499.98
    assert purchase.units == 38.129
    assert purchase.price == 13.113

    assert redemption.transaction_type == "REDEMPTION"
    assert redemption.transaction_date == date(2025, 2, 6)
    assert redemption.amount == -515.00
    assert redemption.units == -38.129
    assert redemption.price == 13.507


def test_switch_in_and_sip_and_lateral_shift_out_classified_correctly():
    result = parse_cas_text(SIP_SWITCH_FIXTURE_TEXT)

    switch_in = [t for t in result.transactions if t.isin == "INF336L01QN5"]
    assert len(switch_in) == 1
    assert switch_in[0].transaction_type == "SWITCH_IN"
    assert switch_in[0].amount == 5865.98
    assert switch_in[0].units == 492.017

    sip_fund = [t for t in result.transactions if t.isin == "INF204K01HY3"]
    sip_installments = [t for t in sip_fund if t.transaction_type == "SIP"]
    assert len(sip_installments) == 2
    assert sip_installments[0].transaction_date == date(2023, 6, 13)
    assert sip_installments[1].transaction_date == date(2023, 7, 11)

    lateral_shift_out = [t for t in sip_fund if t.transaction_type == "SWITCH_OUT"]
    assert len(lateral_shift_out) == 1
    assert lateral_shift_out[0].amount == -14347.73
    assert lateral_shift_out[0].units == -84.562
    # Continuation lines ("INDEX FUND - DIRECT..." / "less TDS, STT") never
    # produce their own spurious transaction rows.
    assert len(sip_fund) == 3


def test_fully_redeemed_folio_still_yields_a_current_holding_if_balance_positive():
    # The switch fixture's second folio ends with Closing Unit Balance:
    # 0.005 (not zero) -- a tiny but real remaining position, so it
    # should appear in .holdings despite nearly all units being switched out.
    result = parse_cas_text(SIP_SWITCH_FIXTURE_TEXT)
    isins = {h.isin for h in result.holdings}
    assert "INF204K01HY3" in isins
