"""Read-only data access for fund research endpoints.

Kept deliberately thin: query construction and ORM-to-pandas conversion
only, no business logic and no response shaping (that's
app/services/fund_analytics_service.py and app/schemas/funds.py) — so the
same queries can be reused by a future non-API caller (e.g. a batch
analytics job) without dragging API concerns along.
"""
from __future__ import annotations

from datetime import date

import pandas as pd
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from app.models.reference import AMC, Benchmark, FundFamily, Scheme, SchemeVariant
from app.models.timeseries import BenchmarkHistory, FundMetric, NavHistory

# How tolerant fuzzy fund-name search is to typos: word_similarity() (from
# the pg_trgm extension — see database/migrations/versions/*_phase_16_*)
# finds the best-matching substring of Scheme.name for the search term and
# scores it 0-1. Below ~0.3 a "match" is usually two unrelated names that
# happen to share a few trigrams, so results stop feeling like typo
# tolerance and start feeling random.
FUZZY_SEARCH_THRESHOLD = 0.3


def _name_search_filter(search: str):
    # ILIKE first: a plain substring match should never depend on the
    # trigram extension being present/healthy. word_similarity() is the
    # fallback that catches what ILIKE can't — a search term that's a
    # near-miss (typo, transposed letters, a dropped word) rather than an
    # exact substring of the fund name.
    return or_(Scheme.name.ilike(f"%{search}%"), func.word_similarity(search, Scheme.name) > FUZZY_SEARCH_THRESHOLD)


def list_schemes(
    db: Session,
    search: str | None = None,
    category: str | None = None,
    amc_name: str | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> list[Scheme]:
    query = (
        db.query(Scheme)
        .join(FundFamily, Scheme.fund_family_id == FundFamily.id)
        .join(AMC, FundFamily.amc_id == AMC.id)
        .options(joinedload(Scheme.fund_family).joinedload(FundFamily.amc), joinedload(Scheme.benchmark))
    )
    if search:
        query = query.filter(_name_search_filter(search))
    if category:
        query = query.filter(Scheme.category.ilike(f"%{category}%"))
    if amc_name:
        query = query.filter(AMC.name.ilike(f"%{amc_name}%"))
    if search:
        # Best-matching name first when fuzzy matching is in play; falls
        # back to alphabetical among equally-similar (e.g. exact-substring)
        # results so paging stays stable.
        query = query.order_by(func.word_similarity(search, Scheme.name).desc(), Scheme.name)
    else:
        query = query.order_by(Scheme.name)
    query = query.offset(offset)
    if limit is not None:
        query = query.limit(limit)
    return query.all()


def count_schemes(
    db: Session, search: str | None = None, category: str | None = None, amc_name: str | None = None
) -> int:
    query = (
        db.query(Scheme)
        .join(FundFamily, Scheme.fund_family_id == FundFamily.id)
        .join(AMC, FundFamily.amc_id == AMC.id)
    )
    if search:
        query = query.filter(_name_search_filter(search))
    if category:
        query = query.filter(Scheme.category.ilike(f"%{category}%"))
    if amc_name:
        query = query.filter(AMC.name.ilike(f"%{amc_name}%"))
    return query.count()


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


def get_cached_metrics(
    db: Session, scheme_variant_id: int, metric_names: tuple[str, ...], calc_date: date, analytics_version: str
) -> dict[str, float]:
    """Today's precomputed values for one variant (see
    data_pipeline/orchestration/precompute_metrics.py), keyed by metric
    name. Empty if nothing has been precomputed for this exact
    (variant, calc_date, analytics_version) yet — the caller falls back
    to a live computation in that case, never treats an empty result as
    an error."""
    rows = (
        db.query(FundMetric.metric_name, FundMetric.value)
        .filter(
            FundMetric.scheme_variant_id == scheme_variant_id,
            FundMetric.metric_name.in_(metric_names),
            FundMetric.calc_date == calc_date,
            FundMetric.analytics_version == analytics_version,
        )
        .all()
    )
    return {name: float(value) for name, value in rows}
