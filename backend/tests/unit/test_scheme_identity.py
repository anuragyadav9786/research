"""Tests for parsing plan/option/base-name identity out of AMFI scheme
names (data_pipeline/normalization/scheme_identity.py). All scheme names
below are fictional fixtures mirroring AMFI's real naming conventions —
never actual fund names.
"""
from data_pipeline.normalization.scheme_identity import parse_category_header, parse_scheme_identity


def test_direct_plan_growth():
    result = parse_scheme_identity("Sample Fixture Bluechip Fund - Direct Plan - Growth")
    assert result is not None
    assert result.base_name == "Sample Fixture Bluechip Fund"
    assert result.plan == "direct"
    assert result.option == "growth"


def test_regular_plan_idcw():
    result = parse_scheme_identity("Sample Fixture Overnight Fund - Regular Plan - IDCW")
    assert result is not None
    assert result.base_name == "Sample Fixture Overnight Fund"
    assert result.plan == "regular"
    assert result.option == "idcw"


def test_dividend_synonym_maps_to_idcw():
    result = parse_scheme_identity("Sample Fixture Liquid Fund - Direct Plan - Daily Dividend")
    assert result is not None
    assert result.option == "idcw"
    assert result.base_name == "Sample Fixture Liquid Fund"


def test_no_spaces_around_dashes():
    result = parse_scheme_identity("Sample Fixture Fund-Direct-Growth")
    assert result is not None
    assert result.base_name == "Sample Fixture Fund"
    assert result.plan == "direct"
    assert result.option == "growth"


def test_fund_name_containing_option_word_is_preserved():
    # "Growth" inside the fund's own name must survive; only the trailing,
    # purely-noise "Growth" segment should be stripped.
    result = parse_scheme_identity("Sample Fixture Growth Opportunities Fund - Direct Plan - Growth")
    assert result is not None
    assert result.base_name == "Sample Fixture Growth Opportunities Fund"
    assert result.plan == "direct"
    assert result.option == "growth"


def test_extra_series_segment_is_preserved():
    result = parse_scheme_identity("Sample Fixture Fund - Series A - Direct Plan - Growth")
    assert result is not None
    assert result.base_name == "Sample Fixture Fund - Series A"


def test_missing_plan_returns_none():
    # Typical of an ETF: no Direct/Regular plan concept at all.
    assert parse_scheme_identity("Sample Fixture Nifty 50 ETF") is None


def test_both_plans_mentioned_returns_none():
    assert parse_scheme_identity("Sample Fixture Fund - Direct and Regular Plan - Growth") is None


def test_both_options_mentioned_returns_none():
    assert parse_scheme_identity("Sample Fixture Fund - Direct Plan - Growth and IDCW") is None


def test_unsupported_option_returns_none():
    # "Bonus" isn't growth or IDCW — schema doesn't model it, so skip rather
    # than guess.
    assert parse_scheme_identity("Sample Fixture Fund - Direct Plan - Bonus") is None


def test_category_header_extraction():
    assert (
        parse_category_header("Open Ended Schemes(Equity Scheme - Large Cap Fund)")
        == "Equity Scheme - Large Cap Fund"
    )
    assert parse_category_header("Close Ended Schemes(Debt Scheme - Fixed Term Plan)") == "Debt Scheme - Fixed Term Plan"


def test_category_header_without_parens_returns_none():
    assert parse_category_header("Sample Fixture Mutual Fund") is None
