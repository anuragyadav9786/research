"""Tests for the pure month-chunking logic in historical_backfill.py — the
piece that decides how a requested [start, end] range is split into
AMFI-sized requests (see that module's docstring for the sizing rationale)."""
from datetime import date

from data_pipeline.orchestration.historical_backfill import _fmt, _month_chunks


def test_single_month_range_is_one_chunk():
    chunks = _month_chunks(date(2026, 8, 1), date(2026, 8, 31))
    assert chunks == [(date(2026, 8, 1), date(2026, 8, 31))]


def test_partial_month_boundaries_are_clamped():
    chunks = _month_chunks(date(2026, 8, 15), date(2026, 9, 10))
    assert chunks == [
        (date(2026, 8, 15), date(2026, 8, 31)),
        (date(2026, 9, 1), date(2026, 9, 10)),
    ]


def test_multi_year_range_produces_one_chunk_per_calendar_month():
    chunks = _month_chunks(date(2024, 11, 1), date(2025, 2, 28))
    assert chunks == [
        (date(2024, 11, 1), date(2024, 11, 30)),
        (date(2024, 12, 1), date(2024, 12, 31)),
        (date(2025, 1, 1), date(2025, 1, 31)),
        (date(2025, 2, 1), date(2025, 2, 28)),
    ]


def test_start_after_end_produces_no_chunks():
    assert _month_chunks(date(2026, 9, 10), date(2026, 9, 1)) == []


def test_fmt_matches_amfi_date_format():
    assert _fmt(date(2026, 9, 12)) == "12-Sep-2026"
