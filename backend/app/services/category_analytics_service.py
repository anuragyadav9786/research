"""Fund -> Category -> Benchmark context — the product-upgrade brief's
Section 5.

Category averages have nowhere to be read from: fund_metrics (the
precomputed-analytics cache table) has no populating job wired up and is
always empty (see precompute_metrics.py's own docstring vs. reality), and
no other table stores a cross-fund rollup. The only honest way to produce
this today is to live-compute each same-category fund's own returns/
drawdown/risk from its NAV history — the exact same per-fund analytics
this platform already runs one fund at a time — and average across
whichever funds have enough history for a given metric.

Deliberately reuses fund_repository.get_nav_series (not
lazy_nav_backfill.ensure_nav_history): a category can hold dozens of
funds, and triggering a live mfapi.in backfill for each one inside a
single request would turn "show me a category average" into a slow
external-API fan-out. A fund with no NAV history yet is simply skipped
from the average — same "not enough data" honesty this platform already
applies everywhere else, never a fabricated stand-in value.

Benchmark figures are a separate, cheaper computation: the fund's own
linked index (Scheme.benchmark, a raw price series in benchmark_history)
run through the exact same compute_returns/compute_drawdown/compute_risk
functions — the fund's actual named benchmark, not a stand-in index fund
like the homepage's BenchmarkDeltaBadge uses (that trick exists there only
because a *cross-fund* homepage comparison needs one fixed benchmark to
compare every featured fund against; here we already have this specific
fund's own correct benchmark series on hand).
"""
from __future__ import annotations

from datetime import date

import pandas as pd
from sqlalchemy.orm import Session

from app.models.reference import Benchmark, Scheme
from app.repositories import fund_repository
from app.services import fund_analytics_service
from data_pipeline.orchestration.lazy_benchmark_backfill import ensure_benchmark_history

# Caps the live fan-out so one pathologically large category can't turn a
# single request into hundreds of NAV-history reads + analytics runs. A
# sample of up to this many funds is plenty to be a representative
# average, not a research-grade census.
MAX_CATEGORY_SAMPLE = 100


def _category_averages(db: Session, category: str, exclude_scheme_id: int, risk_free_rate_annual: float) -> dict:
    schemes = fund_repository.list_schemes(db, category=category, limit=MAX_CATEGORY_SAMPLE)

    cagr_values: list[float] = []
    drawdown_values: list[float] = []
    volatility_values: list[float] = []
    included_ids: set[int] = set()

    for scheme in schemes:
        if scheme.id == exclude_scheme_id:
            continue
        variant = fund_repository.get_default_variant(db, scheme.id)
        if variant is None:
            continue
        nav = fund_repository.get_nav_series(db, variant.id)
        if nav.empty:
            continue

        counted = False

        returns = fund_analytics_service.compute_returns(nav)
        window_3y = returns["windows"].get("3y")
        if window_3y and window_3y["available"]:
            cagr_values.append(window_3y["cagr_pct"])
            counted = True

        drawdown = fund_analytics_service.compute_drawdown(nav)
        if drawdown["available"]:
            drawdown_values.append(drawdown["max_drawdown_pct"])
            counted = True

        risk = fund_analytics_service.compute_risk(nav, None, risk_free_rate_annual)
        if risk["available"]:
            volatility_values.append(risk["volatility_pct"])
            counted = True

        if counted:
            included_ids.add(scheme.id)

    if not included_ids:
        return {
            "available": False,
            "reason": "no_comparable_funds",
            "category": category,
            "funds_included": 0,
            "avg_cagr_3y_pct": None,
            "avg_max_drawdown_pct": None,
            "avg_volatility_pct": None,
        }

    def _avg(values: list[float]) -> float | None:
        return round(sum(values) / len(values), 4) if values else None

    return {
        "available": True,
        "reason": None,
        "category": category,
        "funds_included": len(included_ids),
        "avg_cagr_3y_pct": _avg(cagr_values),
        "avg_max_drawdown_pct": _avg(drawdown_values),
        "avg_volatility_pct": _avg(volatility_values),
    }


_EMPTY_BENCHMARK_FIGURES = {
    "benchmark_name": None,
    "benchmark_cagr_3y_pct": None,
    "benchmark_max_drawdown_pct": None,
    "benchmark_volatility_pct": None,
}


def _benchmark_figures(db: Session, scheme: Scheme, fund_nav: pd.Series, risk_free_rate_annual: float) -> dict:
    """Fund's own benchmark, run through the exact same
    compute_returns/compute_drawdown/compute_risk functions used for the
    fund and category figures — see this module's docstring. Lazily
    ensures (Section 6) the benchmark's price history covers `fund_nav`'s
    own date range before reading it, same as the fund detail page's other
    benchmark-consuming endpoints (app/api/funds.py's _benchmark_series).

    `benchmark_reason` covers only the two conditions that apply
    uniformly to every metric here — "no_benchmark_mapped" (scheme has no
    known benchmark at all) and "data_unavailable" (benchmark identified,
    but its price history is completely empty) — never
    "insufficient_history", because that's a PER-METRIC condition: with a
    non-empty series, it's entirely possible for e.g. the 3-year CAGR
    window to come up short while drawdown/volatility (which need far
    fewer observations — see MIN_OBSERVATIONS_FOR_RISK) succeed, so no
    single reason can correctly describe all three at once. When the
    series is non-empty, `benchmark_reason` is left None even if some
    individual figures are still null; the frontend
    (CategoryBenchmarkRow) defaults an unreasoned null value to
    "insufficient_history" per metric, which is correct precisely because
    it means "we have some benchmark data, just not enough for this
    window" — never a flat null the UI can't explain.
    """
    benchmark_id = fund_repository.get_effective_benchmark_id(db, scheme)
    if benchmark_id is None:
        return {**_EMPTY_BENCHMARK_FIGURES, "benchmark_reason": "no_benchmark_mapped"}

    benchmark = db.get(Benchmark, benchmark_id)
    benchmark_name = benchmark.name if benchmark else None

    if benchmark is not None and not fund_nav.empty:
        start = fund_nav.index.min().date()
        end = min(fund_nav.index.max().date(), date.today())
        ensure_benchmark_history(db, benchmark, start, end)

    benchmark_series = fund_repository.get_benchmark_series(db, benchmark_id)
    if benchmark_series.empty:
        return {**_EMPTY_BENCHMARK_FIGURES, "benchmark_name": benchmark_name, "benchmark_reason": "data_unavailable"}

    returns = fund_analytics_service.compute_returns(benchmark_series)
    window_3y = returns["windows"].get("3y")
    drawdown = fund_analytics_service.compute_drawdown(benchmark_series)
    risk = fund_analytics_service.compute_risk(benchmark_series, None, risk_free_rate_annual)

    cagr_3y = window_3y["cagr_pct"] if window_3y and window_3y["available"] else None
    max_drawdown = drawdown["max_drawdown_pct"] if drawdown["available"] else None
    volatility = risk["volatility_pct"] if risk["available"] else None

    return {
        "benchmark_name": benchmark_name,
        "benchmark_cagr_3y_pct": cagr_3y,
        "benchmark_max_drawdown_pct": max_drawdown,
        "benchmark_volatility_pct": volatility,
        # None here doesn't mean "no reason" — it means "no reason that
        # applies to every metric uniformly"; a null figure alongside a
        # None reason is exactly the per-metric insufficient-history case
        # the frontend fills in (see this function's docstring).
        "benchmark_reason": None,
    }


def compute_fund_context(db: Session, scheme: Scheme, risk_free_rate_annual: float) -> dict:
    category = _category_averages(db, scheme.category, exclude_scheme_id=scheme.id, risk_free_rate_annual=risk_free_rate_annual)
    variant = fund_repository.get_default_variant(db, scheme.id)
    fund_nav = fund_repository.get_nav_series(db, variant.id) if variant is not None else pd.Series(dtype=float)
    benchmark = _benchmark_figures(db, scheme, fund_nav, risk_free_rate_annual)
    return {**category, **benchmark}
