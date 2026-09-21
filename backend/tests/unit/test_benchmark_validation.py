"""Unit tests for benchmark_validation.py — the same Section 19/20
guarantees nav_validation.py enforces, applied to fetched benchmark price
points before they're ever written to benchmark_history."""
from datetime import date, timedelta

from data_pipeline.sources.benchmarks.base import BenchmarkPricePoint
from data_pipeline.validation.benchmark_validation import validate_benchmark_points

TODAY = date(2026, 9, 21)


def _point(d: date, v) -> BenchmarkPricePoint:
    return BenchmarkPricePoint(price_date=d, value=v)


def test_accepts_well_formed_points_sorted_by_date():
    points = [_point(date(2026, 1, 3), 100.0), _point(date(2026, 1, 1), 98.0), _point(date(2026, 1, 2), 99.0)]
    result = validate_benchmark_points(points, as_of=TODAY)

    assert [p.price_date for p in result.accepted] == [date(2026, 1, 1), date(2026, 1, 2), date(2026, 1, 3)]
    assert result.rejected == []


def test_rejects_future_dated_point():
    result = validate_benchmark_points([_point(TODAY + timedelta(days=1), 100.0)], as_of=TODAY)
    assert result.accepted == []
    assert result.rejected[0].reason == "future_date"


def test_rejects_non_positive_value():
    result = validate_benchmark_points([_point(date(2026, 1, 1), 0.0), _point(date(2026, 1, 2), -5.0)], as_of=TODAY)
    assert result.accepted == []
    assert {r.reason for r in result.rejected} == {"non_positive_value"}


def test_rejects_duplicate_date_in_same_batch():
    result = validate_benchmark_points(
        [_point(date(2026, 1, 1), 100.0), _point(date(2026, 1, 1), 101.0)], as_of=TODAY
    )
    assert len(result.accepted) == 1
    assert result.rejected[0].reason == "duplicate_in_batch"


def test_rejects_missing_date():
    result = validate_benchmark_points([_point(None, 100.0)], as_of=TODAY)
    assert result.accepted == []
    assert result.rejected[0].reason == "missing_date"
