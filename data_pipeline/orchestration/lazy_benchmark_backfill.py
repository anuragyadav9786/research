"""On-demand, per-benchmark price-history backfill — the benchmark-side
counterpart to lazy_nav_backfill.py, with one structural difference: NAV
backfill is all-or-nothing (mfapi.in always returns a scheme's entire
history in one call), while a benchmark's required range depends on
*which fund is currently being viewed* and grows over time, so this
supports fetching only the missing sub-range(s) of an already-partially-
cached benchmark (Sections 6-9) instead of only "have we ever backfilled
this at all".

Shared across every scheme that uses the same benchmark (Section 2): the
first fund view for a given benchmark populates benchmark_history; every
other fund sharing that benchmark reuses it, and only ever triggers a
fetch for whatever later date range that first view didn't already cover.

Never raises: a failed provider call (network error, disabled/unimplemented
provider, malformed response) is reported in the returned outcome and
simply retried on the next view — the caller's request proceeds with
whatever benchmark_history already exists (possibly none), exactly like
lazy_nav_backfill.ensure_nav_history's contract.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.models.reference import Benchmark
from app.repositories import fund_repository
from data_pipeline.sources.benchmarks.base import BenchmarkProviderError
from data_pipeline.sources.benchmarks.registry import get_provider
from data_pipeline.storage.database_writer import get_or_create_data_source, write_benchmark_points
from data_pipeline.validation.benchmark_validation import validate_benchmark_points

logger = logging.getLogger(__name__)

DATA_SOURCE_URL = "https://www.niftyindices.com"


@dataclass
class BenchmarkBackfillOutcome:
    attempted: bool  # False if skipped (already fresh, no provider available)
    success: bool = False
    inserted: int = 0
    reason: str | None = None  # set when attempted=False or the fetch failed
    gaps_fetched: list[tuple[date, date]] = field(default_factory=list)


def _compute_gaps(
    existing_min: date | None, existing_max: date | None, start: date, end: date
) -> list[tuple[date, date]]:
    """Which sub-range(s) of [start, end] are NOT already covered by
    [existing_min, existing_max]. Returns [] when fully covered (Section
    8's freshness check), [(start, end)] when nothing is cached yet, or up
    to two ranges — older data needed before what's cached, newer data
    needed after it — when the cache only partially overlaps the request.
    Never re-requests a date already stored.
    """
    if existing_min is None or existing_max is None:
        return [(start, end)]

    gaps: list[tuple[date, date]] = []
    if start < existing_min:
        gaps.append((start, existing_min - timedelta(days=1)))
    if end > existing_max:
        gaps.append((existing_max + timedelta(days=1), end))
    return gaps


def ensure_benchmark_history(db: Session, benchmark: Benchmark, start_date: date, end_date: date) -> BenchmarkBackfillOutcome:
    """Make sure `benchmark`'s price history covers [start_date, end_date],
    fetching only what's missing. Safe to call on every fund-page request
    for that fund's benchmark — a no-op (no network call, no DB write)
    once the range is already covered.
    """
    logger.info("benchmark_requested benchmark_id=%s name=%r range=%s..%s", benchmark.id, benchmark.name, start_date, end_date)

    if not benchmark.is_active:
        logger.info("benchmark_inactive benchmark_id=%s", benchmark.id)
        return BenchmarkBackfillOutcome(attempted=False, reason="benchmark_inactive")

    existing_min, existing_max = fund_repository.get_benchmark_date_range(db, benchmark.id)
    gaps = _compute_gaps(existing_min, existing_max, start_date, end_date)

    if not gaps:
        logger.info("benchmark_cache_hit benchmark_id=%s", benchmark.id)
        return BenchmarkBackfillOutcome(attempted=False)

    logger.info("benchmark_cache_miss benchmark_id=%s gaps=%s", benchmark.id, gaps)

    provider = get_provider(benchmark.provider)
    if provider is None:
        logger.info("benchmark_provider_unavailable benchmark_id=%s provider=%r", benchmark.id, benchmark.provider)
        return BenchmarkBackfillOutcome(attempted=True, success=False, reason="provider_unavailable")

    symbol = benchmark.symbol or benchmark.name
    source = get_or_create_data_source(
        db, name=f"{provider.name} ({DATA_SOURCE_URL})", url=DATA_SOURCE_URL, source_type="nse"
    )
    db.commit()

    total_inserted = 0
    any_success = False
    last_error: str | None = None
    fetched_gaps: list[tuple[date, date]] = []

    for gap_start, gap_end in gaps:
        logger.info("benchmark_api_called benchmark_id=%s provider=%s range=%s..%s", benchmark.id, provider.name, gap_start, gap_end)
        try:
            raw_points = provider.fetch_range(symbol, gap_start, gap_end)
        except BenchmarkProviderError as exc:
            last_error = str(exc)
            logger.warning("benchmark_api_failure benchmark_id=%s provider=%s error=%s", benchmark.id, provider.name, exc)
            continue

        validated = validate_benchmark_points(raw_points, as_of=date.today())
        if validated.rejected:
            logger.warning(
                "benchmark_validation_rejections benchmark_id=%s rejected=%d reasons=%s",
                benchmark.id, len(validated.rejected), {r.reason for r in validated.rejected},
            )
        inserted = write_benchmark_points(db, source, benchmark.id, validated.accepted)
        db.commit()
        total_inserted += inserted
        any_success = True
        fetched_gaps.append((gap_start, gap_end))
        logger.info("benchmark_records_inserted benchmark_id=%s inserted=%d", benchmark.id, inserted)

    new_max = fund_repository.get_benchmark_date_range(db, benchmark.id)[1]
    if new_max is not None and new_max != benchmark.last_data_date:
        benchmark.last_data_date = new_max
        db.commit()

    if not any_success:
        return BenchmarkBackfillOutcome(attempted=True, success=False, reason=last_error or "fetch_failed")

    return BenchmarkBackfillOutcome(attempted=True, success=True, inserted=total_inserted, gaps_fetched=fetched_gaps)
