"""Unit tests for absl_disclosure_parser's pure row-classification logic.

Built from small, hand-constructed row fixtures (plain lists, the same
shape xlrd's own cell-value extraction produces) rather than a real or
synthetic `.xls` file -- `xlwt` (needed to write `.xls`) isn't installed,
and the real production-shaped correctness check already happened
against the actual downloaded September 2026 ABSL disclosure file this
session (104/104 schemes parsed, 5,646 holdings, 0 skipped rows, every
scheme's weight_pct summing to 99.99-100.01%) -- not repeated here as a
committed binary fixture of a real AMC's proprietary monthly file.

Column layout tested here matches the real file exactly (see parser's
own module docstring): index 0 blank, 1 AMC-internal code (unused),
2 name, 3 ISIN, 4 Industry^/Rating, 5 Quantity, 6 Market value (Lakhs),
7 % to AUM (fraction), 8 YTM % (fraction), 9 YTC % (fraction).
"""
from datetime import date

import pytest

from data_pipeline.normalization.absl_disclosure_parser import (
    _find_header_row,
    _match_category_header,
    _parse_pct_fraction,
    _parse_scheme_sheet_rows,
    _parse_weight_pct,
)

_HEADER_ROW = ["", "", "Name of the Instrument / Issuer", "ISIN", "Industry^ / Rating", "Quantity",
               "Market value\n(Rs. in Lakhs)", "% to AUM", "YTM %", "YTC %"]

_INTRO_ROWS = [
    ["TESTCODE", "", "SAMPLE TEST FUND", "", "", "", "", "", "", ""],
    ["", "", "An open ended test scheme", "", "", "", "", "", "", ""],
    ["", "", "Portfolio Statement as on September 30, 2026", "", "", "", "", "", "", ""],
]


def _rows(*data_rows: list) -> list[list]:
    return [*_INTRO_ROWS, _HEADER_ROW, *data_rows]


def _blank(n=10) -> list:
    return [""] * n


def test_extracts_scheme_name_and_as_of_date():
    rows = _rows()
    scheme = _parse_scheme_sheet_rows("TESTCODE", rows)
    assert scheme.scheme_name == "SAMPLE TEST FUND"
    assert scheme.as_of_date == date(2026, 9, 30)


def test_equity_holding_gets_sector_not_rating():
    row = _blank()
    row[2], row[3], row[4], row[5], row[6], row[7] = (
        "ICICI Bank Ltd.", "INE090A01021", "Banks", 11849171.0, 156610.49, 0.0559673125081035,
    )
    rows = _rows(["", "", "Equity & Equity Related", "", "", "", "", "", "", ""], row)
    scheme = _parse_scheme_sheet_rows("TESTCODE", rows)

    assert len(scheme.holdings) == 1
    h = scheme.holdings[0]
    assert h.instrument_type == "equity"
    assert h.sector == "Banks"
    assert h.credit_rating is None
    assert h.isin == "INE090A01021"
    assert h.quantity == 11849171.0
    assert h.market_value_rupees == 156610.49 * 100_000
    assert abs(h.weight_pct - 5.59673125081035) < 1e-9


def test_debt_holding_gets_rating_not_sector_plus_ytm():
    row = _blank()
    row[2], row[3], row[4], row[5], row[6], row[7], row[8] = (
        "7.48% National Bank for Agriculture and Rural Development (15/09/2028)",
        "INE261F08EO7", "CRISIL AAA", 109000.0, 108395.27, 0.0477058368093252, 0.0779,
    )
    rows = _rows(["", "", "Debt Instruments", "", "", "", "", "", "", ""], row)
    scheme = _parse_scheme_sheet_rows("TESTCODE", rows)

    h = scheme.holdings[0]
    assert h.instrument_type == "debt"
    assert h.credit_rating == "CRISIL AAA"
    assert h.sector is None
    assert abs(h.ytm_pct - 7.79) < 1e-6
    assert h.ytc_pct is None


def test_treps_row_has_no_isin_and_is_stored_as_cash_equivalent():
    row = _blank()
    row[1], row[2], row[6], row[7] = "110260100", "TREPS", 68587.0, 0.0245106824379299
    rows = _rows(["", "", "TREPS / Reverse Repo Investments", "", "", "", "", "", "", ""], row)
    scheme = _parse_scheme_sheet_rows("TESTCODE", rows)

    h = scheme.holdings[0]
    assert h.isin is None
    assert h.instrument_type == "cash_equivalent"
    assert h.sector is None
    assert h.credit_rating is None


def test_dollar_prefixed_weight_is_treated_as_zero_not_a_parse_failure():
    row = _blank()
    row[2], row[3], row[4], row[6], row[7] = (
        "Maestros Mediline Systems Ltd.", "INE408E01027", "Miscellaneous", 0.0, "$0.00%",
    )
    rows = _rows(["", "", "Equity & Equity Related", "", "", "", "", "", "", ""], row)
    scheme = _parse_scheme_sheet_rows("TESTCODE", rows)

    assert len(scheme.holdings) == 1
    assert scheme.holdings[0].weight_pct == 0.0
    assert scheme.skipped_rows == []


def test_total_and_grand_total_rows_are_never_holdings():
    equity_row = _blank()
    equity_row[2], equity_row[3], equity_row[6], equity_row[7] = "Some Co Ltd", "INE000000001", 100.0, 0.5
    rows = _rows(
        ["", "", "Equity & Equity Related", "", "", "", "", "", "", ""],
        equity_row,
        ["", "", "Total", "", "", "", 100.0, 0.5, "", ""],
        ["", "", "GRAND TOTAL (AUM)", "", "", "", 100.0, 1.0, "", ""],
    )
    scheme = _parse_scheme_sheet_rows("TESTCODE", rows)
    assert len(scheme.holdings) == 1  # only the real holding, not either total row


def test_parsing_stops_at_grand_total_even_if_later_rows_look_holding_shaped():
    equity_row = _blank()
    equity_row[2], equity_row[3], equity_row[6], equity_row[7] = "Some Co Ltd", "INE000000001", 100.0, 0.5
    # A row after GRAND TOTAL that happens to have numeric-looking data in
    # the same column positions (mirrors the real bug this guards against:
    # a derivatives-exposure sub-table further down the sheet).
    trailing_lookalike = _blank()
    trailing_lookalike[2], trailing_lookalike[6] = "7.34% INDIA GOVERNMENT BOND 22APR2064", 2500.0
    rows = _rows(
        ["", "", "Equity & Equity Related", "", "", "", "", "", "", ""],
        equity_row,
        ["", "", "GRAND TOTAL (AUM)", "", "", "", 100.0, 1.0, "", ""],
        trailing_lookalike,
    )
    scheme = _parse_scheme_sheet_rows("TESTCODE", rows)
    assert len(scheme.holdings) == 1
    assert scheme.skipped_rows == []


def test_a_holding_shaped_row_before_any_category_header_is_reported_not_guessed():
    row = _blank()
    row[2], row[3], row[6], row[7] = "Mystery Co Ltd", "INE999999999", 50.0, 0.1
    rows = _rows(row)  # no category header row at all
    scheme = _parse_scheme_sheet_rows("TESTCODE", rows)
    assert scheme.holdings == []
    assert len(scheme.skipped_rows) == 1
    assert "Mystery Co Ltd" in scheme.skipped_rows[0]


def test_unparseable_weight_is_reported_not_guessed():
    row = _blank()
    row[2], row[3], row[6], row[7] = "Weird Row Ltd", "INE888888888", 10.0, "not a percentage"
    rows = _rows(["", "", "Equity & Equity Related", "", "", "", "", "", "", ""], row)
    scheme = _parse_scheme_sheet_rows("TESTCODE", rows)
    assert scheme.holdings == []
    assert len(scheme.skipped_rows) == 1


def test_a_real_holding_whose_name_contains_a_category_marker_word_is_never_mistaken_for_a_header():
    # The real risk a naive substring-match-first implementation has:
    # a genuine equity holding named e.g. "XYZ Gold Mines Ltd" must not
    # be treated as the "Gold" category header just because it shares
    # the word -- this is only safe because category matching is gated
    # on a BLANK market value, which a real holding row never has.
    row = _blank()
    row[2], row[3], row[4], row[6], row[7] = "XYZ Gold Mines Ltd", "INE777777777", "Metals & Mining", 25.0, 0.2
    rows = _rows(["", "", "Equity & Equity Related", "", "", "", "", "", "", ""], row)
    scheme = _parse_scheme_sheet_rows("TESTCODE", rows)
    assert len(scheme.holdings) == 1
    assert scheme.holdings[0].instrument_type == "equity"
    assert scheme.holdings[0].sector == "Metals & Mining"


def test_reit_invit_and_foreign_security_are_sector_like_not_rating_like():
    invit_row = _blank()
    invit_row[2], invit_row[3], invit_row[4], invit_row[6], invit_row[7] = (
        "IndiGrid Infrastructure Trust", "INE219X23014", "Power", 21736.73, 0.022,
    )
    foreign_row = _blank()
    foreign_row[2], foreign_row[3], foreign_row[4], foreign_row[6], foreign_row[7] = (
        "Microsoft Corporation", "US5949181045", "IT - Software", 2434.89, 0.0067,
    )
    rows = _rows(
        ["", "", "Infrastructure Investment Trust", "", "", "", "", "", "", ""],
        invit_row,
        ["", "", "Foreign Securities and /or overseas ETF", "", "", "", "", "", "", ""],
        foreign_row,
    )
    scheme = _parse_scheme_sheet_rows("TESTCODE", rows)
    assert scheme.holdings[0].instrument_type == "reit_invit"
    assert scheme.holdings[0].sector == "Power"
    assert scheme.holdings[1].instrument_type == "foreign_security"
    assert scheme.holdings[1].sector == "IT - Software"


def test_gold_and_silver_and_exchange_traded_fund_categories_map_to_expected_types():
    gold_row = _blank()
    gold_row[2], gold_row[3], gold_row[6], gold_row[7] = "Gold", "IDIA00500001", 303492.33, 0.98313
    etf_row = _blank()
    etf_row[2], etf_row[3], etf_row[6], etf_row[7] = "Aditya Birla Sun Life Gold ETF", "INF209KB18D3", 180820.1, 1.002
    rows = _rows(
        ["", "", "Gold", "", "", "", "", "", "", ""],
        gold_row,
        ["", "", "Exchange Traded Fund", "", "", "", "", "", "", ""],
        etf_row,
    )
    scheme = _parse_scheme_sheet_rows("TESTCODE", rows)
    assert scheme.holdings[0].instrument_type == "other"
    assert scheme.holdings[1].instrument_type == "mutual_fund_unit"


def test_returns_none_when_as_of_date_or_scheme_name_missing():
    rows = [["", "", "", "", "", "", "", "", "", ""], _HEADER_ROW]
    assert _parse_scheme_sheet_rows("TESTCODE", rows) is None


def test_find_header_row_locates_it_regardless_of_intro_length():
    short_rows = [["x"] * 10, _HEADER_ROW]
    assert _find_header_row(short_rows) == 1
    long_rows = [["x"] * 10 for _ in range(5)] + [_HEADER_ROW]
    assert _find_header_row(long_rows) == 5


def test_match_category_header_is_none_for_unrecognized_text():
    assert _match_category_header("some random label") is None
    assert _match_category_header("equity & equity related") == "equity"


def test_parse_weight_pct_and_pct_fraction_helpers():
    assert _parse_weight_pct(0.05) == 5.0
    assert _parse_weight_pct("$0.00%") == 0.0
    assert _parse_weight_pct("garbage") is None
    assert _parse_pct_fraction(0.0779) == pytest.approx(7.79)
    assert _parse_pct_fraction("") is None
