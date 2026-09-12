"""Integration tests for run_precompute against the real local Postgres
database (Phase 2 seed data must be loaded) — specifically the "overwrite,
not accumulate" behavior that matters for keeping fund_metrics small (see
precompute_metrics.py's module docstring for why that matters here)."""
from datetime import date, timedelta

import pytest

from app.core.database import SessionLocal
from app.core.config import get_settings
from app.models.reference import SchemeVariant
from app.models.timeseries import AnalyticsRun, FundMetric
from data_pipeline.orchestration.precompute_metrics import run_precompute


@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def seeded_variant_id(db) -> int:
    variant = db.query(SchemeVariant).filter(SchemeVariant.amfi_code.isnot(None)).first()
    assert variant is not None, "requires Phase 2 seed data to be loaded"
    return variant.id


def _cleanup(db, run_ids: list[int]) -> None:
    # run_precompute processes EVERY variant in the DB, not just the one
    # this test cares about — cleanup has to match that real footprint
    # (today's rows under this analytics_version), not just one variant's
    # rows, or it leaves other tests (e.g. test_funds.py's cache-hit test)
    # tripping over a stray precomputed row for their own variant.
    db.query(FundMetric).filter(
        FundMetric.calc_date == date.today(), FundMetric.analytics_version == get_settings().analytics_version
    ).delete()
    if run_ids:
        db.query(AnalyticsRun).filter(AnalyticsRun.id.in_(run_ids)).delete(synchronize_session=False)
    db.commit()


def test_precompute_writes_metrics_for_seeded_variant(db, seeded_variant_id):
    run_ids = []
    try:
        result = run_precompute(db)
        run_ids.append(result.run_id)

        assert result.variants_processed > 0
        rows = db.query(FundMetric).filter(FundMetric.scheme_variant_id == seeded_variant_id).all()
        assert len(rows) > 0
        metric_names = {r.metric_name for r in rows}
        assert "volatility_pct" in metric_names  # seed data has enough history for risk
    finally:
        _cleanup(db, run_ids)


def test_rerunning_precompute_overwrites_rather_than_accumulates(db, seeded_variant_id):
    run_ids = []
    try:
        first = run_precompute(db)
        run_ids.append(first.run_id)
        first_count = db.query(FundMetric).filter(FundMetric.scheme_variant_id == seeded_variant_id).count()

        second = run_precompute(db)
        run_ids.append(second.run_id)
        second_count = db.query(FundMetric).filter(FundMetric.scheme_variant_id == seeded_variant_id).count()

        assert second_count == first_count  # same day, same metrics -> no duplicates, no growth
    finally:
        _cleanup(db, run_ids)


def test_precompute_deletes_stale_older_calc_date_rows(db, seeded_variant_id):
    analytics_version = get_settings().analytics_version
    stale = FundMetric(
        scheme_variant_id=seeded_variant_id,
        metric_name="volatility_pct",
        value=999.0,
        calc_date=date.today() - timedelta(days=5),
        analytics_version=analytics_version,
    )
    db.add(stale)
    db.commit()

    run_ids = []
    try:
        result = run_precompute(db)
        run_ids.append(result.run_id)

        remaining = (
            db.query(FundMetric)
            .filter(FundMetric.scheme_variant_id == seeded_variant_id, FundMetric.metric_name == "volatility_pct")
            .all()
        )
        assert len(remaining) == 1  # the stale 5-day-old row is gone, only today's remains
        assert remaining[0].calc_date == date.today()
        assert float(remaining[0].value) != 999.0
    finally:
        _cleanup(db, run_ids)
