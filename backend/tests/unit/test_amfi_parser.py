"""Tests for the AMFI NAVAll.txt parser.

The fixture text below is a SYNTHETIC sample that mimics AMFI's published
file *structure* — verified against the live file, see
data_pipeline/sources/amfi/parser.py's module docstring — using entirely
fictional scheme codes/names/NAVs. It is not, and must never be treated
as, real AMFI data.
"""
from data_pipeline.sources.amfi.parser import parse_navall

SAMPLE_FIXTURE = """\
Scheme Code;ISIN Div Payout/ ISIN Growth;ISIN Div Reinvestment;Scheme Name;Plan;Option;Net Asset Value;Date

Open Ended Schemes(Equity Scheme - Large Cap Fund)

Sample Fixture Mutual Fund
900001;SAMPLE-FIX-ISIN-01;-;Sample Fixture Bluechip Fund;Direct Plan;Growth;123.4567;12-Sep-2026
900002;SAMPLE-FIX-ISIN-02;-;Sample Fixture Bluechip Fund;Regular Plan;Growth;120.1234;12-Sep-2026

Open Ended Schemes(Debt Scheme - Overnight Fund)

Sample Fixture Mutual Fund
900003;-;SAMPLE-FIX-ISIN-03;Sample Fixture Overnight Fund;Direct Plan;IDCW;1000.0000;12-Sep-2026
900004;N.A.;-;Sample Fixture New Launch Fund;Direct Plan;Growth;N.A.;12-Sep-2026
"""


def test_parses_all_data_rows():
    records = parse_navall(SAMPLE_FIXTURE)
    assert len(records) == 4
    assert [r.scheme_code for r in records] == ["900001", "900002", "900003", "900004"]


def test_tracks_amc_and_category_context():
    records = parse_navall(SAMPLE_FIXTURE)
    assert records[0].amc_name == "Sample Fixture Mutual Fund"
    assert records[0].category == "Open Ended Schemes(Equity Scheme - Large Cap Fund)"
    assert records[2].category == "Open Ended Schemes(Debt Scheme - Overnight Fund)"


def test_extracts_isin_and_treats_dash_as_none():
    records = parse_navall(SAMPLE_FIXTURE)
    assert records[0].isin_growth == "SAMPLE-FIX-ISIN-01"
    assert records[0].isin_div_reinvestment is None
    assert records[2].isin_growth is None
    assert records[2].isin_div_reinvestment == "SAMPLE-FIX-ISIN-03"


def test_extracts_plan_option_and_bare_scheme_name():
    records = parse_navall(SAMPLE_FIXTURE)
    assert records[0].scheme_name == "Sample Fixture Bluechip Fund"
    assert records[0].plan_raw == "Direct Plan"
    assert records[0].option_raw == "Growth"
    assert records[2].plan_raw == "Direct Plan"
    assert records[2].option_raw == "IDCW"


def test_skips_column_header_row():
    records = parse_navall(SAMPLE_FIXTURE)
    assert all(r.scheme_code != "Scheme Code" for r in records)


def test_preserves_unparsed_na_values_for_validator_to_reject():
    records = parse_navall(SAMPLE_FIXTURE)
    na_record = records[-1]
    assert na_record.nav_raw == "N.A."


def test_empty_input_returns_empty_list():
    assert parse_navall("") == []


def test_short_row_is_padded_not_dropped():
    text = "Some AMC\n900005;ISIN1\n"
    records = parse_navall(text)
    assert len(records) == 1
    assert records[0].scheme_code == "900005"
    assert records[0].scheme_name == ""  # missing fields padded empty, not silently discarded
    assert records[0].plan_raw == ""
    assert records[0].option_raw == ""
