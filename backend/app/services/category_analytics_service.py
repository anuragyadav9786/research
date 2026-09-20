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

from sqlalchemy.orm import Session

from app.models.reference import Scheme
from app.repositories import fund_repository
from app.services import fund_analytics_service

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


def _benchmark_figures(db: Session, scheme: Scheme, risk_free_rate_annual: float) -> dict:
    if scheme.benchmark_id is None:
        return {"benchmark_name": None, "benchmark_cagr_3y_pct": None, "benchmark_max_drawdown_pct": None, "benchmark_volatility_pct": None}

    benchmark_series = fund_repository.get_benchmark_series(db, scheme.benchmark_id)
    if benchmark_series.empty:
        return {
            "benchmark_name": scheme.benchmark.name if scheme.benchmark else None,
            "benchmark_cagr_3y_pct": None,
            "benchmark_max_drawdown_pct": None,
            "benchmark_volatility_pct": None,
        }

    returns = fund_analytics_service.compute_returns(benchmark_series)
    window_3y = returns["windows"].get("3y")
    drawdown = fund_analytics_service.compute_drawdown(benchmark_series)
    risk = fund_analytics_service.compute_risk(benchmark_series, None, risk_free_rate_annual)

    return {
        "benchmark_name": scheme.benchmark.name if scheme.benchmark else None,
        "benchmark_cagr_3y_pct": window_3y["cagr_pct"] if window_3y and window_3y["available"] else None,
        "benchmark_max_drawdown_pct": drawdown["max_drawdown_pct"] if drawdown["available"] else None,
        "benchmark_volatility_pct": risk["volatility_pct"] if risk["available"] else None,
    }


def compute_fund_context(db: Session, scheme: Scheme, risk_free_rate_annual: float) -> dict:
    category = _category_averages(db, scheme.category, exclude_scheme_id=scheme.id, risk_free_rate_annual=risk_free_rate_annual)
    benchmark = _benchmark_figures(db, scheme, risk_free_rate_annual)
    return {**category, **benchmark}
