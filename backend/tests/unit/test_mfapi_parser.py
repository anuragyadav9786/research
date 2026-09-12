"""Tests for parsing api.mfapi.in's per-scheme NAV history response.

The fixture below uses real-shaped fields confirmed against the live
endpoint (see client.py's module docstring) with fictional values."""
from datetime import date

from data_pipeline.sources.mfapi.parser import parse_mfapi_history

SAMPLE_BODY = {
    "meta": {"scheme_code": 135762, "scheme_name": "Sample Fixture Fund"},
    "data": [
        {"date": "11-09-2026", "nav": "29.96280"},
        {"date": "10-09-2026", "nav": "30.02900"},
        {"date": "09-09-2026", "nav": "N.A."},  # unparseable NAV
        {"date": "not-a-date", "nav": "30.00"},  # unparseable date
        {"date": "08-09-2026", "nav": "0"},  # non-positive NAV
        {"date": "07-09-2026", "nav": "-5.0"},  # negative NAV
    ],
    "status": "SUCCESS",
}


def test_parses_valid_points_in_order_given():
    result = parse_mfapi_history(SAMPLE_BODY)
    assert result.points[0] == (date(2026, 9, 11), 29.9628)
    assert result.points[1] == (date(2026, 9, 10), 30.029)


def test_skips_invalid_entries_and_counts_them():
    result = parse_mfapi_history(SAMPLE_BODY)
    assert len(result.points) == 2
    assert result.skipped == 4


def test_empty_data_returns_no_points():
    result = parse_mfapi_history({"data": []})
    assert result.points == []
    assert result.skipped == 0


def test_missing_data_key_returns_no_points():
    result = parse_mfapi_history({})
    assert result.points == []
    assert result.skipped == 0


def test_date_format_is_dd_mm_yyyy_not_dd_mon_yyyy():
    # mfapi.in uses "11-09-2026" (DD-MM-YYYY), unlike AMFI's own endpoints
    # which use "11-Sep-2026" (DD-Mon-YYYY) — a differently-formatted date
    # string here must not be silently misparsed as the wrong calendar date.
    result = parse_mfapi_history({"data": [{"date": "01-02-2020", "nav": "10.00"}]})
    assert result.points == [(date(2020, 2, 1), 10.0)]
