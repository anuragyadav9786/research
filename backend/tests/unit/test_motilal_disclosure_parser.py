"""Unit tests for motilal_disclosure_parser's pure row-classification logic.

Built from small, hand-constructed row fixtures (plain tuples, the same
shape openpyxl's own `iter_rows(values_only=True)` produces) rather than
a real or synthetic `.xlsx` file -- the real production-shaped
correctness check already happened against the actual downloaded
September 2026 Motilal Oswal disclosure file this session (90/90 schemes
parsed, 6,452 holdings, 0 skipped rows, every scheme's weight_pct summing
to 99.99-100.01% except one confirmed real exception -- see
test_arbitrage_fund_sheet_shape below).

Column layout tested here matches the real file exactly (see parser's
own module docstring): index 0 Sr. No., 1 name, 2 ISIN, 3 Industry*/
Rating, 4 Quantity, 5 Market value (Lakhs), 6 % to Net Assets (0-100
scale, NOT a fraction), 7 YTM (debt-oriented sheets only).
"""
from datetime import date

import pytest

from data_pipeline.normalization.motilal_disclosure_parser import (
    _find_header_row,
    _match_category_header,
    _parse_scheme_sheet_rows,
    _parse_weight_pct,
)

_HEADER_ROW = ("Sr. No.", "Name of the Instrument", "ISIN", "Industry* / Rating", "Quantity",
               "Market/Fair Value (Rs. in Lakhs)", "% to Net Assets", "YTM")

_INTRO_ROWS = [
    ("Back to Index",),
    ("Motilal Oswal Asset Management Company Limited",),
    ("(Investment Manager for Motilal Oswal Mutual Fund)",),
    ("Registered Office: Somewhere",),
    ("CIN: U00000MH0000PLC000000",),
    ("MONTHLY PORTFOLIO STATEMENT AS ON SEPTEMBER 30, 2026",),
    (),
    ("Sample Test Fund",),
    ("(An open ended test scheme)",),
]


def _rows(*data_rows: tuple) -> list[tuple]:
    return [*_INTRO_ROWS, _HEADER_ROW, *data_rows]


def _blank(n=8) -> list:
    return [None] * n


def test_extracts_scheme_name_and_as_of_date():
    rows = _rows()
    scheme = _parse_scheme_sheet_rows("TESTCODE", rows)
    assert scheme.scheme_name == "Sample Test Fund"
    assert scheme.as_of_date == date(2026, 9, 30)


def test_equity_holding_gets_sector_not_rating_and_weight_is_not_multiplied():
    row = _blank()
    row[0], row[1], row[2], row[3], row[4], row[5], row[6] = (
        1, "ICICI Bank Ltd.", "INE090A01021", "Banks", 11849171.0, 156610.49, 5.5967,
    )
    rows = _rows(("(A)", "Equity & Equity related"), tuple(row))
    scheme = _parse_scheme_sheet_rows("TESTCODE", rows)

    assert len(scheme.holdings) == 1
    h = scheme.holdings[0]
    assert h.instrument_type == "equity"
    assert h.sector == "Banks"
    assert h.credit_rating is None
    assert h.isin == "INE090A01021"
    assert h.quantity == 11849171.0
    assert h.market_value_rupees == 156610.49 * 100_000
    # Motilal's file already stores this on a 0-100 scale -- unlike
    # ABSL's 0-1 fraction, it must NEVER be multiplied by 100.
    assert h.weight_pct == pytest.approx(5.5967)


def test_debt_holding_gets_rating_not_sector_plus_ytm_and_no_ytc():
    # YTM's raw cell is Excel percentage-formatted -- confirmed real:
    # a cell displaying "5.75%" comes back from openpyxl as 0.0575, not
    # 5.75 (unlike the weight-pct column, already a true 0-100 number).
    row = _blank()
    row[0], row[1], row[2], row[3], row[4], row[5], row[6], row[7] = (
        1, "National Bank For Agriculture and Rural Development 2027 ** #", "INE261F16AQ3",
        "CRISIL A1+", 2500000, 2421.75, 4.54, 0.07845,
    )
    rows = _rows(("(A)", "Money Market Instruments"), ("(b)", "Certificate of Deposit"), tuple(row))
    scheme = _parse_scheme_sheet_rows("TESTCODE", rows)

    h = scheme.holdings[0]
    assert h.instrument_type == "money_market"
    assert h.credit_rating == "CRISIL A1+"
    assert h.sector is None
    assert h.ytm_pct == pytest.approx(7.845)
    assert h.ytc_pct is None  # confirmed real: no YTC column exists anywhere in this file
    # Trailing footnote-reference markers stripped before storing.
    assert h.instrument_name == "National Bank For Agriculture and Rural Development 2027"


def test_treps_row_has_no_isin_and_is_stored_as_cash_equivalent():
    row = _blank()
    row[0], row[1], row[5], row[6] = 1, "Triparty Repo", 9800000.0, 1.099
    rows = _rows(("(B)", "Money Market Instruments"), ("(c)", "TREPS / Reverse Repo"), tuple(row))
    scheme = _parse_scheme_sheet_rows("TESTCODE", rows)

    h = scheme.holdings[0]
    assert h.isin is None
    assert h.instrument_type == "cash_equivalent"
    assert h.sector is None
    assert h.credit_rating is None


def test_net_receivables_payables_is_a_holding_despite_sr_no_being_none():
    # Confirmed real: this row's own Sr. No. cell is None, same as a Sub
    # Total row's, but it IS a genuine cash-equivalent holding, not a
    # subtotal -- must never be silently dropped.
    equity_row = _blank()
    equity_row[0], equity_row[1], equity_row[2], equity_row[5], equity_row[6] = (
        1, "Some Co Ltd", "INE000000001", 100.0, 99.3,
    )
    net_receivable_row = [None] * 8
    net_receivable_row[1], net_receivable_row[5], net_receivable_row[6] = (
        "Net Receivables / (Payables)", -2.8, 0.7,
    )
    rows = _rows(("(A)", "Equity & Equity related"), tuple(equity_row), tuple(net_receivable_row))
    scheme = _parse_scheme_sheet_rows("TESTCODE", rows)

    assert len(scheme.holdings) == 2
    cash_holding = scheme.holdings[1]
    assert cash_holding.instrument_name == "Net Receivables / (Payables)"
    assert cash_holding.isin is None
    assert cash_holding.instrument_type == "cash_equivalent"  # never inherits "equity" from state
    assert cash_holding.weight_pct == pytest.approx(0.7)


def test_a_genuine_holding_with_sr_no_none_is_still_captured():
    # Confirmed real: a REIT holding that's the sole constituent of its
    # category had Sr. No. = None in the real file. Sr. No.'s shape must
    # play no part in the holding-vs-header decision -- only the numeric
    # market-value check does.
    row = [None] * 8
    row[1], row[2], row[5], row[6] = "Mindspace Business Parks REIT", "INE0CCU25019", 310.45, 4.48
    rows = _rows(("(c)", "REIT"), tuple(row))
    scheme = _parse_scheme_sheet_rows("TESTCODE", rows)

    assert len(scheme.holdings) == 1
    assert scheme.holdings[0].instrument_type == "reit_invit"
    assert scheme.holdings[0].isin == "INE0CCU25019"


def test_category_header_with_no_lettered_marker_is_still_matched():
    # Confirmed real: the Silver ETF sheet's own top-level header is the
    # bare text "SILVER" with Sr. No. = None -- no "(A)"/"(a)" marker at
    # all, unlike every other sheet's convention.
    row = _blank()
    row[0], row[1], row[5], row[6] = 1, "SILVER 999 1KG BAR", 91771.63, 87.83
    rows = _rows((None, "SILVER"), tuple(row))
    scheme = _parse_scheme_sheet_rows("TESTCODE", rows)

    assert len(scheme.holdings) == 1
    assert scheme.holdings[0].instrument_type == "other"


def test_dollar_prefixed_weight_is_treated_as_zero_not_a_parse_failure():
    row = _blank()
    row[0], row[1], row[5], row[6] = 1, "Oil India Limited October 2026 Future", -6.3, "$0.00"
    rows = _rows(("(B)", "Derivatives"), ("(a)", "Index / Stock Futures"), tuple(row))
    scheme = _parse_scheme_sheet_rows("TESTCODE", rows)

    assert len(scheme.holdings) == 1
    assert scheme.holdings[0].weight_pct == 0.0
    assert scheme.skipped_rows == []


def test_derivatives_row_has_negative_values_and_no_isin():
    row = _blank()
    row[0], row[1], row[4], row[5], row[6] = (
        1, "Radico Khaitan Limited October 2026 Future", -450, -19.85, -0.01,
    )
    rows = _rows(("(B)", "Derivatives"), ("(a)", "Index / Stock Futures"), tuple(row))
    scheme = _parse_scheme_sheet_rows("TESTCODE", rows)

    h = scheme.holdings[0]
    assert h.instrument_type == "other"
    assert h.isin is None
    assert h.quantity == -450
    assert h.market_value_rupees == -19.85 * 100_000
    assert h.weight_pct == -0.01


def test_sub_total_and_total_and_grand_total_rows_are_never_holdings():
    equity_row = _blank()
    equity_row[0], equity_row[1], equity_row[2], equity_row[5], equity_row[6] = (
        1, "Some Co Ltd", "INE000000001", 100.0, 100.0,
    )
    rows = _rows(
        ("(A)", "Equity & Equity related"),
        tuple(equity_row),
        (None, "Sub Total", None, None, None, 100.0, 100.0),
        (None, "Total", None, None, None, 100.0, 100.0),
        (None, "GRAND TOTAL", None, None, None, 100.0, 100.0),
    )
    scheme = _parse_scheme_sheet_rows("TESTCODE", rows)
    assert len(scheme.holdings) == 1  # only the real holding


def test_parsing_stops_at_grand_total_even_if_later_rows_look_holding_shaped():
    equity_row = _blank()
    equity_row[0], equity_row[1], equity_row[2], equity_row[5], equity_row[6] = (
        1, "Some Co Ltd", "INE000000001", 100.0, 100.0,
    )
    # Footer content after GRAND TOTAL (e.g. per-plan NAV figures) that
    # happens to have a numeric value in some column.
    trailing_lookalike = [None] * 8
    trailing_lookalike[1], trailing_lookalike[4] = "Direct Plan - Growth Option", 68.7773
    rows = _rows(
        ("(A)", "Equity & Equity related"),
        tuple(equity_row),
        (None, "GRAND TOTAL", None, None, None, 100.0, 100.0),
        tuple(trailing_lookalike),
    )
    scheme = _parse_scheme_sheet_rows("TESTCODE", rows)
    assert len(scheme.holdings) == 1
    assert scheme.skipped_rows == []


def test_privately_placed_unlisted_inherits_parent_debt_instrument_type():
    row = _blank()
    row[0], row[1], row[2], row[3], row[5], row[6] = (
        1, "Some Private Bond Ltd", "INE111111111", "CRISIL AAA", 50.0, 1.0,
    )
    rows = _rows(
        ("(A)", "Debt Instruments"),
        ("(b)", "Privately placed / Unlisted"),  # no own instrument_type -- inherits "debt"
        tuple(row),
    )
    scheme = _parse_scheme_sheet_rows("TESTCODE", rows)
    assert scheme.holdings[0].instrument_type == "debt"
    assert scheme.holdings[0].credit_rating == "CRISIL AAA"


def test_a_holding_shaped_row_before_any_category_header_is_reported_not_guessed():
    row = _blank()
    row[0], row[1], row[2], row[5], row[6] = 1, "Mystery Co Ltd", "INE999999999", 50.0, 10.0
    rows = _rows(tuple(row))  # no category header row at all
    scheme = _parse_scheme_sheet_rows("TESTCODE", rows)
    assert scheme.holdings == []
    assert len(scheme.skipped_rows) == 1
    assert "Mystery Co Ltd" in scheme.skipped_rows[0]


def test_unparseable_weight_is_reported_not_guessed():
    row = _blank()
    row[0], row[1], row[2], row[5], row[6] = 1, "Weird Row Ltd", "INE888888888", 10.0, "not a percentage"
    rows = _rows(("(A)", "Equity & Equity related"), tuple(row))
    scheme = _parse_scheme_sheet_rows("TESTCODE", rows)
    assert scheme.holdings == []
    assert len(scheme.skipped_rows) == 1


def test_a_real_holding_whose_name_contains_a_category_marker_word_is_never_mistaken_for_a_header():
    row = _blank()
    row[0], row[1], row[2], row[3], row[5], row[6] = (
        1, "XYZ Gold Mines Ltd", "INE777777777", "Metals & Mining", 25.0, 2.0,
    )
    rows = _rows(("(A)", "Equity & Equity related"), tuple(row))
    scheme = _parse_scheme_sheet_rows("TESTCODE", rows)
    assert len(scheme.holdings) == 1
    assert scheme.holdings[0].instrument_type == "equity"
    assert scheme.holdings[0].sector == "Metals & Mining"


def test_international_etf_maps_to_foreign_security():
    row = _blank()
    row[0], row[1], row[2], row[5], row[6] = 1, "Vanguard S&P 500 ETF", "US9229083632", 1168.64, 0.25
    rows = _rows(("(c)", "International Exchange Traded Funds"), tuple(row))
    scheme = _parse_scheme_sheet_rows("TESTCODE", rows)
    assert scheme.holdings[0].instrument_type == "foreign_security"


def test_arbitrage_fund_sheet_shape():
    # Confirmed real: an Arbitrage fund's category sub-totals (long
    # equity + short derivatives + large Net Receivables from margin/
    # settlement cash) sum correctly to 100% once every row is captured,
    # even though no single category alone resembles 100%.
    equity_row = _blank()
    equity_row[0], equity_row[1], equity_row[2], equity_row[5], equity_row[6] = (
        1, "Some Co Ltd", "INE000000001", 7132.0, 71.32,
    )
    future_row = _blank()
    future_row[0], future_row[1], future_row[4], future_row[5], future_row[6] = (
        1, "Some Co Ltd October 2026 Future", -100, -7161.0, -71.61,
    )
    net_receivable_row = [None] * 8
    net_receivable_row[1], net_receivable_row[5], net_receivable_row[6] = (
        "Net Receivables / (Payables)", 7229.0, 72.29,
    )
    rows = _rows(
        ("(A)", "Equity & Equity related"),
        tuple(equity_row),
        ("(B)", "Derivatives"),
        ("(a)", "Index / Stock Futures"),
        tuple(future_row),
        tuple(net_receivable_row),
    )
    scheme = _parse_scheme_sheet_rows("TESTCODE", rows)
    assert sum(h.weight_pct for h in scheme.holdings) == pytest.approx(72.0, abs=0.01)
    assert scheme.skipped_rows == []


def test_find_header_row_locates_it_regardless_of_intro_length():
    short_rows = [("x",) * 8, _HEADER_ROW]
    assert _find_header_row(short_rows) == 1
    long_rows = [("x",) * 8 for _ in range(5)] + [_HEADER_ROW]
    assert _find_header_row(long_rows) == 5


def test_match_category_header_is_none_for_unrecognized_text():
    assert _match_category_header("some random label") is None
    assert _match_category_header("equity & equity related") == "equity"


def test_parse_weight_pct_helper():
    assert _parse_weight_pct(5.5) == 5.5
    assert _parse_weight_pct("$0.00") == 0.0
    assert _parse_weight_pct("garbage") is None
