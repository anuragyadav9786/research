"""Unit tests for lazy_benchmark_backfill._compute_gaps — the pure "what
date range is actually missing" logic behind Sections 6-9 (fetch only the
missing period, in either direction, never re-download what's cached)."""
from datetime import date

from data_pipeline.orchestration.lazy_benchmark_backfill import _compute_gaps


def test_nothing_cached_yet_fetches_the_whole_requested_range():
    gaps = _compute_gaps(None, None, date(2023, 1, 1), date(2026, 9, 21))
    assert gaps == [(date(2023, 1, 1), date(2026, 9, 21))]


def test_fully_covered_range_needs_no_fetch():
    gaps = _compute_gaps(date(2023, 1, 1), date(2026, 9, 21), date(2023, 6, 1), date(2026, 1, 1))
    assert gaps == []


def test_only_a_trailing_gap_is_fetched():
    # Database has 01-Jan-2023 -> 20-Sep-2026; today is 21-Sep-2026 -> fetch only the one missing day.
    gaps = _compute_gaps(date(2023, 1, 1), date(2026, 9, 20), date(2023, 1, 1), date(2026, 9, 21))
    assert gaps == [(date(2026, 9, 21), date(2026, 9, 21))]


def test_only_a_leading_gap_is_fetched():
    # Database has 01-Jan-2024 -> today; a 5-year-lookback request needs older history too.
    gaps = _compute_gaps(date(2024, 1, 1), date(2026, 9, 21), date(2021, 9, 21), date(2026, 9, 21))
    assert gaps == [(date(2021, 9, 21), date(2023, 12, 31))]


def test_both_leading_and_trailing_gaps_are_fetched_separately():
    gaps = _compute_gaps(date(2024, 1, 1), date(2024, 12, 31), date(2023, 1, 1), date(2026, 1, 1))
    assert gaps == [(date(2023, 1, 1), date(2023, 12, 31)), (date(2025, 1, 1), date(2026, 1, 1))]


def test_exact_boundary_dates_already_covered_need_no_fetch():
    gaps = _compute_gaps(date(2023, 1, 1), date(2026, 9, 21), date(2023, 1, 1), date(2026, 9, 21))
    assert gaps == []
