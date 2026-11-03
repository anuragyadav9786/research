"""On-demand, cached fetch of the current risk-free rate -- replaces the
hardcoded Settings.risk_free_rate = 0.07 placeholder (docs/data-sources.md's
open decision #4) everywhere a Sharpe/Sortino computation needs one.

Mirrors lazy_nav_backfill.py / lazy_benchmark_backfill.py's shape: a
cheap local DB check first, a real fetch only when the cached value is
stale, and a silent, never-raising fallback whenever the fetch fails --
the research engine must never break, or show a different Sharpe/Sortino
on every request, just because FBIL (data_pipeline/sources/riskfree/
fbil_client.py) is briefly unreachable.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.timeseries import RiskFreeRateSnapshot
from data_pipeline.sources.riskfree.fbil_client import FbilFetchError, fetch_latest_3m_tbill_rate_pct
from data_pipeline.storage.database_writer import get_or_create_data_source

logger = logging.getLogger(__name__)

# FBIL publishes on business days only, and the observed response lags
# by a few calendar days (see fbil_client.py's module docstring) -- a
# cached rate up to this many days old is fresh enough to skip a
# re-fetch, since this value only ever feeds a Sharpe/Sortino annualized
# assumption, which doesn't need day-of fidelity.
_FRESHNESS_WINDOW_DAYS = 5
DATA_SOURCE_NAME = "FBIL T-Bill Benchmark (3 Months)"
DATA_SOURCE_URL = "https://www.fbil.org.in"


def _latest_snapshot(db: Session) -> RiskFreeRateSnapshot | None:
    return db.execute(
        select(RiskFreeRateSnapshot).order_by(RiskFreeRateSnapshot.as_of_date.desc()).limit(1)
    ).scalar_one_or_none()


def get_current_risk_free_rate(db: Session) -> float:
    """Annualized, decimal form (e.g. 0.0587 = 5.87%) -- the same
    convention Settings.risk_free_rate uses, which every call site that
    previously read `get_settings().risk_free_rate` should now call this
    with instead. Never raises: if there's no cached value yet AND the
    live fetch also fails, falls back to Settings.risk_free_rate's own
    configured default, exactly like ensure_nav_history's "never block
    the page, just use what's already there" contract."""
    cached = _latest_snapshot(db)
    if cached is not None and cached.as_of_date >= date.today() - timedelta(days=_FRESHNESS_WINDOW_DAYS):
        return float(cached.rate_pct) / 100.0

    try:
        as_of, rate_pct = fetch_latest_3m_tbill_rate_pct()
    except FbilFetchError as exc:
        logger.info("risk_free_rate_fetch_failed error=%s", exc)
        if cached is not None:
            return float(cached.rate_pct) / 100.0
        return get_settings().risk_free_rate

    source = get_or_create_data_source(db, name=DATA_SOURCE_NAME, url=DATA_SOURCE_URL, source_type="rbi")
    existing = db.execute(
        select(RiskFreeRateSnapshot).where(RiskFreeRateSnapshot.as_of_date == as_of)
    ).scalar_one_or_none()
    if existing is None:
        db.add(RiskFreeRateSnapshot(as_of_date=as_of, rate_pct=rate_pct, source_id=source.id))
    else:
        existing.rate_pct = rate_pct
        existing.source_id = source.id
    db.commit()

    return rate_pct / 100.0
