"""Validation rules for benchmark price points fetched from a provider —
the same Section 19/20 guarantees nav_validation.py enforces for NAV data,
applied to benchmark_history: never let a missing/invalid date, a
non-numeric or non-positive value, a duplicate date, or a future date
reach the database.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from data_pipeline.sources.benchmarks.base import BenchmarkPricePoint


@dataclass
class ValidatedBenchmarkPoint:
    price_date: date
    value: float


@dataclass
class RejectedBenchmarkPoint:
    raw: BenchmarkPricePoint
    reason: str


@dataclass
class BenchmarkValidationResult:
    accepted: list[ValidatedBenchmarkPoint] = field(default_factory=list)
    rejected: list[RejectedBenchmarkPoint] = field(default_factory=list)


def validate_benchmark_points(
    points: list[BenchmarkPricePoint], as_of: date
) -> BenchmarkValidationResult:
    """`as_of` is the run's reference "today" — a point dated after it is
    rejected as a future date rather than silently accepted (a provider
    bug or clock skew should never let tomorrow's index level in)."""
    result = BenchmarkValidationResult()
    seen_dates: set[date] = set()

    for point in points:
        if point.price_date is None:
            result.rejected.append(RejectedBenchmarkPoint(point, "missing_date"))
            continue
        if point.price_date > as_of:
            result.rejected.append(RejectedBenchmarkPoint(point, "future_date"))
            continue
        if point.price_date in seen_dates:
            result.rejected.append(RejectedBenchmarkPoint(point, "duplicate_in_batch"))
            continue
        if point.value is None or not isinstance(point.value, (int, float)):
            result.rejected.append(RejectedBenchmarkPoint(point, "non_numeric_value"))
            continue
        if point.value <= 0:
            result.rejected.append(RejectedBenchmarkPoint(point, "non_positive_value"))
            continue

        seen_dates.add(point.price_date)
        result.accepted.append(ValidatedBenchmarkPoint(price_date=point.price_date, value=float(point.value)))

    result.accepted.sort(key=lambda p: p.price_date)
    return result
