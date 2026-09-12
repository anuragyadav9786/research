"""Tests for the AMFI historical NAV report parser.

The fixture text below is a SYNTHETIC sample mimicking the real historical
endpoint's *structure and column order* — confirmed against the live
endpoint, see data_pipeline/sources/amfi/historical_parser.py's module
docstring — using entirely fictional scheme codes/names/NAVs.
"""
from data_pipeline.sources.amfi.historical_parser import parse_historical_navall

SAMPLE_FIXTURE = """\
Scheme Code;NAV Name;Plan;Option;ISIN Div Payout/ISIN Growth;ISIN Div Reinvestment;Net Asset Value;Date

Open Ended Schemes ( Equity Scheme - Large Cap Fund )

Sample Fixture Mutual Fund
900001;Sample Fixture Bluechip Fund - Direct Plan - Growth;Direct;Growth;SAMPLE-FIX-ISIN-01;-;123.4567;10-Sep-2026
900001;Sample Fixture Bluechip Fund - Direct Plan - Growth;Direct;Growth;SAMPLE-FIX-ISIN-01;-;124.0000;11-Sep-2026
900002;Sample Fixture Bluechip Fund - Regular Plan - Growth;Regular;Growth;SAMPLE-FIX-ISIN-02;-;120.1234;10-Sep-2026
900004;Sample Fixture New Launch Fund;Direct;Growth;-;-;N.A.;10-Sep-2026
"""


def test_parses_all_data_rows():
    records = parse_historical_navall(SAMPLE_FIXTURE)
    assert len(records) == 4
    assert [r.scheme_code for r in records] == ["900001", "900001", "900002", "900004"]


def test_same_scheme_code_repeats_across_dates():
    records = parse_historical_navall(SAMPLE_FIXTURE)
    first_two = records[:2]
    assert [r.date_raw for r in first_two] == ["10-Sep-2026", "11-Sep-2026"]
    assert [r.nav_raw for r in first_two] == ["123.4567", "124.0000"]


def test_compound_nav_name_stored_as_scheme_name_uninterpreted():
    records = parse_historical_navall(SAMPLE_FIXTURE)
    assert records[0].scheme_name == "Sample Fixture Bluechip Fund - Direct Plan - Growth"


def test_does_not_extract_category_or_amc_name():
    records = parse_historical_navall(SAMPLE_FIXTURE)
    assert all(r.category is None for r in records)
    assert all(r.amc_name is None for r in records)


def test_extracts_isin_and_treats_dash_as_none():
    records = parse_historical_navall(SAMPLE_FIXTURE)
    assert records[0].isin_growth == "SAMPLE-FIX-ISIN-01"
    assert records[0].isin_div_reinvestment is None
    assert records[3].isin_growth is None


def test_skips_column_header_row():
    records = parse_historical_navall(SAMPLE_FIXTURE)
    assert all(r.scheme_code != "Scheme Code" for r in records)


def test_preserves_unparsed_na_values_for_validator_to_reject():
    records = parse_historical_navall(SAMPLE_FIXTURE)
    assert records[-1].nav_raw == "N.A."


def test_empty_input_returns_empty_list():
    assert parse_historical_navall("") == []
