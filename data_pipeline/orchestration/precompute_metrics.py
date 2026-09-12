"""Precomputes each scheme_variant's returns/risk/drawdown into
fund_metrics, once per pipeline run, instead of every fund page view
recomputing them live from raw nav_history (see docs/analytics-methodology.md
and fund_analytics_service.py's own docstring, which flagged this as a
known, deferred gap: "not precomputed... a follow-up once real ingestion
brings in the full fund universe" — this is that follow-up).

Deliberately overwrites, not accumulates: every run replaces the previous
calc_date's rows for the same (scheme_variant_id, metric_name,
analytics_version) rather than keeping one row per day forever. There is
no reason to retain a permanent daily history of computed values here —
raw nav_history already IS that permanent record — and letting this table
grow by a full day's worth of new rows every single day is exactly the
unbounded-growth mistake that already emptied this project's Supabase
free-tier quota once (see git history: the bulk historical backfill).
After writing today's rows, every row from an earlier calc_date under the
same analytics_version is deleted in one statement, so steady-state size
stays flat regardless of how long this has been running.

Only /risk actually reads from this cache (see app/api/funds.py) — its
response shape is flat and entirely numeric, so it reconstructs losslessly
from metric rows. Returns' windows (available/reason/start_date/end_date
per window) and drawdown's date/boolean fields don't fit a flat
Numeric-only table without lossy encoding tricks, so those two endpoints
stay live-computed exactly as before; their values ARE still stored here
(cagr_* per window, max_drawdown_pct) for future uses like a fund
screener, just not served back through the API from this table yet.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone

from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, joinedload

from app.core.config import get_settings
from app.models.reference import SchemeVariant
from app.models.timeseries import AnalyticsRun, FundMetric
from app.repositories import fund_repository
from app.services import fund_analytics_service

_INSERT_BATCH_SIZE = 5000

RETURN_WINDOWS = ("1y", "3y", "5y", "7y", "10y")
# Present in RiskResponse whenever risk["available"] is True, unconditionally.
RISK_REQUIRED_FIELDS = ("volatility_pct", "downside_deviation_pct", "observations_used")
# Present only when computable even given available=True (e.g. no benchmark
# means beta/jensen_alpha/capture ratios stay None) — a missing metric row
# for one of these means "genuinely None", not "not yet precomputed".
RISK_OPTIONAL_FIELDS = (
    "sharpe_ratio", "sortino_ratio", "upside_capture_pct", "downside_capture_pct", "beta", "jensen_alpha_pct",
)


@dataclass
class PrecomputeResult:
    run_id: int = 0
    variants_processed: int = 0
    variants_skipped_no_history: int = 0
    metrics_written: int = 0


def _rows_for_variant(
    variant_id: int, returns: dict, risk: dict, drawdown: dict, calc_date: date, analytics_version: str
) -> list[dict]:
    rows: list[dict] = []

    def _row(metric_name: str, value: float) -> dict:
        # Cast defensively: these values arrive via pandas/numpy
        # computations upstream (analytics/), so a bare numpy.float64 can
        # slip through here — psycopg2 doesn't adapt that type, which
        # fails with a bizarre-looking "schema np does not exist" error
        # rather than anything mentioning numpy.
        return {
            "scheme_variant_id": variant_id,
            "metric_name": metric_name,
            "value": float(value),
            "calc_date": calc_date,
            "analytics_version": analytics_version,
        }

    for window in RETURN_WINDOWS:
        w = returns["windows"].get(window)
        if w and w["available"]:
            rows.append(_row(f"cagr_{window}", w["cagr_pct"]))

    if risk["available"]:
        for field in RISK_REQUIRED_FIELDS + RISK_OPTIONAL_FIELDS:
            value = risk.get(field)
            if value is not None:
                rows.append(_row(field, value))

    if drawdown["available"]:
        rows.append(_row("max_drawdown_pct", drawdown["max_drawdown_pct"]))

    return rows


def run_precompute(db: Session) -> PrecomputeResult:
    analytics_version = get_settings().analytics_version
    risk_free_rate = get_settings().risk_free_rate
    calc_date = date.today()

    run = AnalyticsRun(analytics_version=analytics_version, status="running")
    db.add(run)
    db.commit()
    db.refresh(run)

    try:
        result = PrecomputeResult(run_id=run.id)
        all_rows: list[dict] = []

        variants = db.query(SchemeVariant).options(joinedload(SchemeVariant.scheme)).all()
        for variant in variants:
            nav = fund_repository.get_nav_series(db, variant.id)
            if nav.empty:
                result.variants_skipped_no_history += 1
                continue

            benchmark = None
            if variant.scheme.benchmark_id is not None:
                benchmark = fund_repository.get_benchmark_series(db, variant.scheme.benchmark_id)

            returns = fund_analytics_service.compute_returns(nav)
            risk = fund_analytics_service.compute_risk(nav, benchmark, risk_free_rate)
            drawdown = fund_analytics_service.compute_drawdown(nav)

            all_rows.extend(_rows_for_variant(variant.id, returns, risk, drawdown, calc_date, analytics_version))
            result.variants_processed += 1

        for i in range(0, len(all_rows), _INSERT_BATCH_SIZE):
            batch = all_rows[i : i + _INSERT_BATCH_SIZE]
            stmt = pg_insert(FundMetric).values(batch)
            stmt = stmt.on_conflict_do_update(constraint="uq_metric_identity", set_={"value": stmt.excluded.value})
            db.execute(stmt)
        result.metrics_written = len(all_rows)

        # Overwrite, not accumulate (see module docstring).
        db.execute(
            delete(FundMetric).where(
                FundMetric.analytics_version == analytics_version, FundMetric.calc_date < calc_date
            )
        )

        run.status = "success"
        run.completed_at = datetime.now(timezone.utc)
        db.commit()
        return result

    except Exception:
        db.rollback()
        failed_run = db.get(AnalyticsRun, run.id)
        failed_run.status = "failed"
        failed_run.completed_at = datetime.now(timezone.utc)
        db.commit()
        raise
