"""Read-only data access for fund research endpoints.

Kept deliberately thin: query construction and ORM-to-pandas conversion
only, no business logic and no response shaping (that's
app/services/fund_analytics_service.py and app/schemas/funds.py) — so the
same queries can be reused by a future non-API caller (e.g. a batch
analytics job) without dragging API concerns along.
"""
from __future__ import annotations

import pandas as pd
from sqlalchemy.orm import Session, joinedload

from app.models.reference import AMC, Benchmark, FundFamily, Scheme, SchemeVariant
from app.models.timeseries import BenchmarkHistory, NavHistory


def list_schemes(
    db: Session, search: str | None = None, category: str | None = None, amc_name: str | None = None
) -> list[Scheme]:
    query = (
        db.query(Scheme)
        .join(FundFamily, Scheme.fund_family_id == FundFamily.id)
        .join(AMC, FundFamily.amc_id == AMC.id)
        .options(joinedload(Scheme.fund_family).joinedload(FundFamily.amc), joinedload(Scheme.benchmark))
    )
    if search:
        query = query.filter(Scheme.name.ilike(f"%{search}%"))
    if category:
        query = query.filter(Scheme.category == category)
    if amc_name:
        query = query.filter(AMC.name.ilike(f"%{amc_name}%"))
    return query.order_by(Scheme.name).all()


def get_scheme(db: Session, scheme_id: int) -> Scheme | None:
    return (
        db.query(Scheme)
        .options(
            joinedload(Scheme.fund_family).joinedload(FundFamily.amc),
            joinedload(Scheme.benchmark),
            joinedload(Scheme.variants),
        )
        .filter(Scheme.id == scheme_id)
        .first()
    )


def get_variant(db: Session, scheme_id: int, plan: str, option: str) -> SchemeVariant | None:
    return (
        db.query(SchemeVariant)
        .filter(SchemeVariant.scheme_id == scheme_id, SchemeVariant.plan == plan, SchemeVariant.option == option)
        .first()
    )


def get_default_variant(db: Session, scheme_id: int) -> SchemeVariant | None:
    """The variant used when a caller needs "a" NAV series for a scheme
    without the user having picked plan/option — e.g. return correlation
    in the Overlap Engine, which is a scheme-level comparison. Prefers
    direct/growth (the standard comparison basis in fund research); falls
    back to whatever variant exists rather than failing, since even the
    regular plan's returns are highly correlated with direct's (same
    portfolio, a small expense-ratio spread apart)."""
    preferred = get_variant(db, scheme_id, "direct", "growth")
    if preferred is not None:
        return preferred
    return db.query(SchemeVariant).filter(SchemeVariant.scheme_id == scheme_id).first()


def get_latest_nav(db: Session, scheme_variant_id: int) -> NavHistory | None:
    return (
        db.query(NavHistory)
        .filter(NavHistory.scheme_variant_id == scheme_variant_id)
        .order_by(NavHistory.date.desc())
        .first()
    )


def get_nav_series(db: Session, scheme_variant_id: int) -> pd.Series:
    """NAV history for one scheme variant as a date-indexed pandas Series,
    the shape every `analytics/` function expects."""
    rows = (
        db.query(NavHistory.date, NavHistory.nav)
        .filter(NavHistory.scheme_variant_id == scheme_variant_id)
        .order_by(NavHistory.date)
        .all()
    )
    if not rows:
        return pd.Series(dtype=float)
    series = pd.Series({d: float(v) for d, v in rows})
    series.index = pd.to_datetime(series.index)
    return series.sort_index()


def get_benchmark_series(db: Session, benchmark_id: int) -> pd.Series:
    rows = (
        db.query(BenchmarkHistory.date, BenchmarkHistory.value)
        .filter(BenchmarkHistory.benchmark_id == benchmark_id)
        .order_by(BenchmarkHistory.date)
        .all()
    )
    if not rows:
        return pd.Series(dtype=float)
    series = pd.Series({d: float(v) for d, v in rows})
    series.index = pd.to_datetime(series.index)
    return series.sort_index()
