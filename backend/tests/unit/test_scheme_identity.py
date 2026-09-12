"""Tests for classifying AMFI's Plan/Option column values
(data_pipeline/normalization/scheme_identity.py). The Option examples
below mirror real-world variety confirmed against the live file (see
parser.py's module docstring) — "Growth Option", "IDCW-Re-investment",
"MONTHLY DCW Payout" etc. are genuine AMFI vocabulary, not fictional.
"""
from data_pipeline.normalization.scheme_identity import parse_category_header, parse_option, parse_plan


def test_plan_direct():
    assert parse_plan("Direct Plan") == "direct"


def test_plan_regular():
    assert parse_plan("Regular Plan") == "regular"


def test_plan_blank_returns_none():
    # Typical of an ETF: no distributor-plan concept at all.
    assert parse_plan("") is None
    assert parse_plan("-") is None


def test_plan_mentioning_both_returns_none():
    assert parse_plan("Direct and Regular Plan") is None


def test_option_growth_variants():
    assert parse_option("Growth Option") == "growth"
    assert parse_option("GROWTH") == "growth"
    assert parse_option("Growth") == "growth"


def test_option_idcw_variants():
    assert parse_option("IDCW Option") == "idcw"
    assert parse_option("IDCW") == "idcw"
    assert parse_option("IDCW-Re-investment") == "idcw"
    assert parse_option("MONTHLY DCW Payout") == "idcw"
    assert parse_option("QUARTERLY IDCW Payout") == "idcw"
    assert parse_option("Daily Dividend") == "idcw"


def test_option_blank_returns_none():
    assert parse_option("") is None
    assert parse_option("-") is None


def test_option_unsupported_returns_none():
    # "Bonus" isn't growth or IDCW — schema doesn't model it, so skip
    # rather than guess.
    assert parse_option("Bonus") is None


def test_option_mentioning_both_returns_none():
    assert parse_option("Growth and IDCW") is None


def test_category_header_extraction():
    assert (
        parse_category_header("Open Ended Schemes(Equity Scheme - Large Cap Fund)")
        == "Equity Scheme - Large Cap Fund"
    )
    assert parse_category_header("Close Ended Schemes(Debt Scheme - Fixed Term Plan)") == "Debt Scheme - Fixed Term Plan"


def test_category_header_without_parens_returns_none():
    assert parse_category_header("Sample Fixture Mutual Fund") is None
