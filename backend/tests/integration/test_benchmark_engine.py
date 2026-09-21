"""End-to-end tests of the benchmark data engine (Phase 17) against the
real local Postgres database — mirrors test_lazy_nav_backfill.py's
pattern: the external provider is monkeypatched (this sandbox has no
outbound network access at all), everything downstream (gap detection,
validation, upsert, the get_effective_benchmark_id mapping resolution)
runs for real.

Covers the benchmark-engine spec's TEST 1-10 scenarios (test case names
below reference them).
"""
from datetime import date

import pytest

import data_pipeline.orchestration.lazy_benchmark_backfill as backfill_module
from app.core.database import SessionLocal
from app.models.reference import Benchmark, FundBenchmarkHistory, Scheme
from app.models.timeseries import BenchmarkHistory, DataSource
from app.repositories import fund_repository
from data_pipeline.orchestration.lazy_benchmark_backfill import ensure_benchmark_history
from data_pipeline.sources.benchmarks.base import BenchmarkPricePoint, BenchmarkProviderError
from data_pipeline.storage.database_writer import write_benchmark_points
from data_pipeline.validation.benchmark_validation import ValidatedBenchmarkPoint

# A fixed past date range — safe from the "no future dates" validation
# rule (unlike the far-future dates the NAV fixtures use to dodge
# collisions, which doesn't apply here: this fixture always creates a
# brand-new Benchmark row, so there's no existing history to collide with
# regardless of which dates are used).
_START = date(2025, 1, 1)
_END = date(2025, 1, 10)


@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.rollback()  # a failed test can leave the session mid-transaction; never let that block cleanup
    session.close()


@pytest.fixture
def benchmark(db):
    bm = Benchmark(
        name="TEST FIXTURE INDEX TRI",
        provider="NSE",
        symbol="TEST FIXTURE INDEX",
        benchmark_type="TRI",
    )
    db.add(bm)
    db.commit()
    yield bm
    db.rollback()  # a failed test may have left the session mid-transaction
    db.query(BenchmarkHistory).filter(BenchmarkHistory.benchmark_id == bm.id).delete()
    db.query(FundBenchmarkHistory).filter(FundBenchmarkHistory.benchmark_id == bm.id).delete()
    db.delete(bm)
    db.commit()


def _fake_provider(points_by_range):
    """A stand-in BenchmarkProvider whose fetch_range returns canned
    points and records every call, so a test can assert exactly which
    sub-range(s) were actually requested."""
    calls = []

    class _Fake:
        name = "NSE"

        def fetch_range(self, symbol, start, end):
            calls.append((start, end))
            return points_by_range.get((start, end), [])

    return _Fake(), calls


def _points(*dates_values):
    return [BenchmarkPricePoint(price_date=d, value=v) for d, v in dates_values]


# TEST 2: benchmark not in cache -> fetch -> store -> calculate.
def test_cache_miss_fetches_full_range_and_stores_it(db, benchmark, monkeypatch):
    fake, calls = _fake_provider({(_START, _END): _points((_START, 100.0), (_END, 101.0))})
    monkeypatch.setattr(backfill_module, "get_provider", lambda name: fake)

    outcome = ensure_benchmark_history(db, benchmark, _START, _END)

    assert outcome.attempted is True
    assert outcome.success is True
    assert outcome.inserted == 2
    assert calls == [(_START, _END)]
    stored = fund_repository.get_benchmark_series(db, benchmark.id)
    assert len(stored) == 2


# TEST 1 / TEST 10: benchmark already fully cached -> no external call, repeated view is a no-op.
def test_cache_hit_makes_no_provider_call(db, benchmark, monkeypatch):
    fake, calls = _fake_provider({(_START, _END): _points((_START, 100.0), (_END, 101.0))})
    monkeypatch.setattr(backfill_module, "get_provider", lambda name: fake)
    ensure_benchmark_history(db, benchmark, _START, _END)
    assert len(calls) == 1

    outcome = ensure_benchmark_history(db, benchmark, _START, _END)

    assert outcome.attempted is False
    assert len(calls) == 1  # still just the first call — no second fetch


# TEST 3: partial coverage -> only the missing sub-range is fetched.
def test_partial_coverage_fetches_only_the_missing_tail(db, benchmark, monkeypatch):
    mid = date(2025, 1, 5)
    fake, calls = _fake_provider({
        (_START, mid): _points((_START, 100.0), (mid, 102.0)),
        (date(2025, 1, 6), _END): _points((date(2025, 1, 6), 103.0), (_END, 104.0)),
    })
    monkeypatch.setattr(backfill_module, "get_provider", lambda name: fake)

    ensure_benchmark_history(db, benchmark, _START, mid)
    assert calls == [(_START, mid)]

    outcome = ensure_benchmark_history(db, benchmark, _START, _END)

    assert calls == [(_START, mid), (date(2025, 1, 6), _END)]
    assert outcome.gaps_fetched == [(date(2025, 1, 6), _END)]
    stored = fund_repository.get_benchmark_series(db, benchmark.id)
    assert len(stored) == 4


# TEST 5: provider fails but usable cached data already covers the request -> use cache, no crash.
def test_provider_unavailable_falls_back_to_existing_cache(db, benchmark, monkeypatch):
    fake, calls = _fake_provider({(_START, _END): _points((_START, 100.0), (_END, 101.0))})
    monkeypatch.setattr(backfill_module, "get_provider", lambda name: fake)
    ensure_benchmark_history(db, benchmark, _START, _END)

    monkeypatch.setattr(backfill_module, "get_provider", lambda name: None)
    outcome = ensure_benchmark_history(db, benchmark, _START, _END)

    assert outcome.attempted is False  # already fresh — provider is never even consulted
    stored = fund_repository.get_benchmark_series(db, benchmark.id)
    assert len(stored) == 2


# TEST 6: provider unavailable and no cached data at all -> graceful outcome, never raises.
def test_provider_unavailable_with_no_cache_degrades_gracefully(db, benchmark, monkeypatch):
    monkeypatch.setattr(backfill_module, "get_provider", lambda name: None)

    outcome = ensure_benchmark_history(db, benchmark, _START, _END)

    assert outcome.attempted is True
    assert outcome.success is False
    assert outcome.reason == "provider_unavailable"
    stored = fund_repository.get_benchmark_series(db, benchmark.id)
    assert stored.empty


def test_provider_raising_does_not_crash_and_reports_failure(db, benchmark, monkeypatch):
    class _Failing:
        name = "NSE"

        def fetch_range(self, symbol, start, end):
            raise BenchmarkProviderError("simulated network failure")

    monkeypatch.setattr(backfill_module, "get_provider", lambda name: _Failing())

    outcome = ensure_benchmark_history(db, benchmark, _START, _END)

    assert outcome.attempted is True
    assert outcome.success is False
    assert "simulated network failure" in outcome.reason


# TEST 8: duplicate points from the provider (e.g. a re-fetched overlapping
# range) never create duplicate rows.
def test_duplicate_points_are_upserted_not_duplicated(db, benchmark, monkeypatch):
    fake, _ = _fake_provider({(_START, _END): _points((_START, 100.0), (_END, 101.0))})
    monkeypatch.setattr(backfill_module, "get_provider", lambda name: fake)
    ensure_benchmark_history(db, benchmark, _START, _END)

    source = db.query(DataSource).filter(DataSource.source_type == "nse").first()
    inserted_again = write_benchmark_points(
        db, source, benchmark.id, [ValidatedBenchmarkPoint(price_date=_START, value=999.0)]
    )
    db.commit()

    assert inserted_again == 0  # conflict on (benchmark_id, date) -> no-op, not an error
    row = db.query(BenchmarkHistory).filter(
        BenchmarkHistory.benchmark_id == benchmark.id, BenchmarkHistory.date == _START
    ).one()
    assert float(row.value) == 100.0  # original value untouched


# TEST 4: two schemes that share a benchmark reuse exactly one dataset.
def test_two_schemes_sharing_a_benchmark_reuse_the_same_dataset(db, benchmark, monkeypatch):
    schemes = db.query(Scheme).limit(2).all()
    assert len(schemes) >= 2, "requires Phase 2 seed data"
    original_benchmark_ids = [s.benchmark_id for s in schemes]
    for s in schemes:
        s.benchmark_id = benchmark.id
    db.commit()

    fake, calls = _fake_provider({(_START, _END): _points((_START, 100.0), (_END, 101.0))})
    monkeypatch.setattr(backfill_module, "get_provider", lambda name: fake)

    try:
        ensure_benchmark_history(db, benchmark, _START, _END)  # fund A's view
        ensure_benchmark_history(db, benchmark, _START, _END)  # fund B's view, same benchmark

        assert len(calls) == 1  # only fetched once, even though two "funds" requested it
        series_a = fund_repository.get_benchmark_series(db, schemes[0].benchmark_id)
        series_b = fund_repository.get_benchmark_series(db, schemes[1].benchmark_id)
        assert series_a.equals(series_b)
    finally:
        for s, original in zip(schemes, original_benchmark_ids):
            s.benchmark_id = original
        db.commit()


# TEST 9: fund_benchmark_history supports a scheme's benchmark changing
# over time, and get_effective_benchmark_id resolves the one in effect on
# a given date rather than always the current one.
def test_get_effective_benchmark_id_respects_historical_assignment(db, benchmark):
    scheme = db.query(Scheme).first()
    assert scheme is not None
    old_benchmark = Benchmark(name="TEST FIXTURE OLD INDEX TRI")
    db.add(old_benchmark)
    db.commit()

    # This scheme may already carry a migrated "current" mapping row (from
    # the Phase 17 migration's backfill of scheme.benchmark_id) — the
    # partial unique index only allows one open-ended row per scheme, so
    # clear it for the duration of this test and restore it afterward.
    preexisting = db.query(FundBenchmarkHistory).filter(FundBenchmarkHistory.scheme_id == scheme.id).all()
    preexisting_data = [
        {"benchmark_id": r.benchmark_id, "start_date": r.start_date, "end_date": r.end_date, "source": r.source}
        for r in preexisting
    ]
    for r in preexisting:
        db.delete(r)
    db.commit()

    old_row = FundBenchmarkHistory(
        scheme_id=scheme.id, benchmark_id=old_benchmark.id,
        start_date=date(2020, 1, 1), end_date=date(2023, 12, 31),
        source="test fixture",
    )
    new_row = FundBenchmarkHistory(
        scheme_id=scheme.id, benchmark_id=benchmark.id,
        start_date=date(2024, 1, 1), end_date=None,
        source="test fixture",
    )
    db.add_all([old_row, new_row])
    db.commit()

    try:
        assert fund_repository.get_effective_benchmark_id(db, scheme, as_of=date(2022, 6, 1)) == old_benchmark.id
        assert fund_repository.get_effective_benchmark_id(db, scheme, as_of=date(2025, 6, 1)) == benchmark.id
        assert fund_repository.get_effective_benchmark_id(db, scheme, as_of=date(2026, 9, 21)) == benchmark.id
    finally:
        db.delete(old_row)
        db.delete(new_row)
        db.commit()
        for data in preexisting_data:
            db.add(FundBenchmarkHistory(scheme_id=scheme.id, **data))
        db.commit()
        db.delete(old_benchmark)
        db.commit()


def test_get_effective_benchmark_id_falls_back_to_legacy_pointer_when_no_mapping_rows(db):
    scheme = db.query(Scheme).filter(Scheme.benchmark_id.isnot(None)).first()
    assert scheme is not None, "requires a seeded scheme with benchmark_id set"
    has_mapping = (
        db.query(FundBenchmarkHistory.id).filter(FundBenchmarkHistory.scheme_id == scheme.id).first()
    )
    if has_mapping is not None:
        pytest.skip("this scheme already has explicit mapping rows (migrated legacy row) — not the no-mapping case")

    assert fund_repository.get_effective_benchmark_id(db, scheme) == scheme.benchmark_id


def test_get_effective_benchmark_id_returns_none_for_unmapped_scheme(db):
    scheme = Scheme(fund_family_id=db.query(Scheme).first().fund_family_id, name="TEST FIXTURE UNMAPPED SCHEME", category="Equity - Test")
    db.add(scheme)
    db.commit()
    try:
        assert fund_repository.get_effective_benchmark_id(db, scheme) is None
    finally:
        db.delete(scheme)
        db.commit()
