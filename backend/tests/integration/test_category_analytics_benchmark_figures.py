"""Tests for category_analytics_service._benchmark_figures's per-metric
handling — specifically the bug where a single blanket `benchmark_reason`
covering all three metrics (CAGR/drawdown/volatility) at once produced a
bare, unexplained null whenever the metrics diverged (e.g. a benchmark
series long enough for drawdown/volatility, which only need
MIN_OBSERVATIONS_FOR_RISK, but too short for the 3-year CAGR window).
`benchmark_reason` is now only set for the two conditions true of every
metric at once (no benchmark mapped, or the series is completely empty);
a null figure with no explicit reason is the per-metric
insufficient-history case, which the frontend fills in — see
CategoryBenchmarkRow.tsx's benchmarkUnavailableLabel.
"""
from datetime import date, timedelta

import pandas as pd
import pytest

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models.reference import Benchmark, FundBenchmarkHistory, Scheme
from app.models.timeseries import BenchmarkHistory, DataSource
from app.services.category_analytics_service import _benchmark_figures


@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.rollback()
    session.close()


@pytest.fixture
def short_history_benchmark(db):
    """A real benchmark with ~18 months of daily price history — enough
    for drawdown/volatility (MIN_OBSERVATIONS_FOR_RISK is tiny) but short
    of the 3-year window compute_returns needs for a 3y CAGR figure."""
    source = db.query(DataSource).filter(DataSource.source_type == "manual").first()
    if source is None:
        source = DataSource(name="TEST FIXTURE SOURCE", source_type="manual")
        db.add(source)
        db.flush()

    bm = Benchmark(name="TEST FIXTURE SHORT HISTORY INDEX")
    db.add(bm)
    db.flush()

    end = date(2026, 6, 1)
    start = end - timedelta(days=550)  # ~18 months
    rows = []
    d = start
    value = 100.0
    while d <= end:
        rows.append(BenchmarkHistory(benchmark_id=bm.id, date=d, value=round(value, 4), source_id=source.id))
        value *= 1.0002
        d += timedelta(days=1)
    db.add_all(rows)
    db.commit()

    yield bm

    db.query(BenchmarkHistory).filter(BenchmarkHistory.benchmark_id == bm.id).delete()
    db.delete(bm)
    db.commit()


def test_short_history_gives_no_blanket_reason_when_some_metrics_succeed(db, short_history_benchmark):
    scheme = db.query(Scheme).first()
    assert scheme is not None
    original_benchmark_id = scheme.benchmark_id

    # get_effective_benchmark_id checks fund_benchmark_history before
    # falling back to scheme.benchmark_id — clear any existing mapping
    # rows for this scheme for the duration of the test (e.g. the Phase
    # 17 migration's legacy-pointer row) so setting benchmark_id below
    # actually takes effect, then restore them afterward.
    preexisting = db.query(FundBenchmarkHistory).filter(FundBenchmarkHistory.scheme_id == scheme.id).all()
    preexisting_data = [
        {"benchmark_id": r.benchmark_id, "start_date": r.start_date, "end_date": r.end_date, "source": r.source}
        for r in preexisting
    ]
    for r in preexisting:
        db.delete(r)
    db.commit()

    scheme.benchmark_id = short_history_benchmark.id
    db.commit()

    try:
        fund_nav = pd.Series(dtype=float)  # empty is fine — this scheme's own NAV range isn't under test here
        result = _benchmark_figures(db, scheme, fund_nav, risk_free_rate_annual=get_settings().risk_free_rate)

        # The whole point of the fix: CAGR-3y correctly comes up short
        # (not enough history for a 3-year window)...
        assert result["benchmark_cagr_3y_pct"] is None
        # ...while drawdown and volatility (much lower data requirements)
        # succeed on the exact same series...
        assert result["benchmark_max_drawdown_pct"] is not None
        assert result["benchmark_volatility_pct"] is not None
        # ...and benchmark_reason must NOT claim a blanket reason that
        # would incorrectly explain away the metrics that DID compute.
        assert result["benchmark_reason"] is None
        assert result["benchmark_name"] == "TEST FIXTURE SHORT HISTORY INDEX"
    finally:
        scheme.benchmark_id = original_benchmark_id
        db.commit()
        for data in preexisting_data:
            db.add(FundBenchmarkHistory(scheme_id=scheme.id, **data))
        db.commit()
