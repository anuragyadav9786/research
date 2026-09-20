"""Research-filter discovery modules — the product-upgrade brief's
Section 8 "solve the 1,833 funds problem": a small set of transparent,
named filters ("funds with a defensive drawdown profile", never "Top 10"
or "Best Funds") a user can browse by real behavioural characteristics
instead of scrolling an alphabetical list of every fund. Investigating
*why* a fund appears is built in: every match carries the actual metric
value that qualified it, not just a pass/fail flag.

Same cost constraint as category_analytics_service: nothing is
precomputed (fund_metrics has no populating job wired up), so each
filter's matches come from scanning schemes and live-computing returns/
drawdown/rolling-returns from NAV history. Capped at SCAN_CAP funds
*scanned* (not SCAN_CAP results found), so cost stays bounded regardless
of how large the fund universe grows — a filter that matches few funds
in the first SCAN_CAP scanned simply returns few results rather than
scanning the whole database. Never triggers a live NAV backfill; a
scheme with no history yet is skipped, not fetched.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from sqlalchemy.orm import Session

from app.models.reference import Scheme
from app.repositories import fund_repository
from app.services import fund_analytics_service

SCAN_CAP = 200
RESULT_CAP = 20


@dataclass
class FundMetrics:
    cagr_3y: float | None
    max_drawdown_pct: float | None
    recovered: bool | None
    recovery_duration_days: int | None
    rolling_spread_pct: float | None
    benchmark_cagr_3y: float | None


@dataclass
class DiscoveryFilter:
    key: str
    label: str
    criterion: str
    predicate: Callable[[FundMetrics], bool]
    metric_of: Callable[[FundMetrics], float | None]
    metric_label: str


def _compute_fund_metrics(db: Session, scheme: Scheme) -> FundMetrics | None:
    variant = fund_repository.get_default_variant(db, scheme.id)
    if variant is None:
        return None
    nav = fund_repository.get_nav_series(db, variant.id)
    if nav.empty:
        return None

    returns = fund_analytics_service.compute_returns(nav)
    window_3y = returns["windows"].get("3y")
    cagr_3y = window_3y["cagr_pct"] if window_3y and window_3y["available"] else None

    drawdown = fund_analytics_service.compute_drawdown(nav)
    max_dd = drawdown["max_drawdown_pct"] if drawdown["available"] else None
    recovered = drawdown["recovered"] if drawdown["available"] else None
    recovery_days = drawdown["recovery_duration_days"] if drawdown["available"] else None

    rolling = fund_analytics_service.compute_rolling_returns(nav, None, 3.0)
    dist = rolling["distribution"]
    rolling_spread = dist["max"] - dist["min"] if rolling["available"] and dist["max"] is not None and dist["min"] is not None else None

    benchmark_cagr_3y = None
    if scheme.benchmark_id is not None:
        benchmark_series = fund_repository.get_benchmark_series(db, scheme.benchmark_id)
        if not benchmark_series.empty:
            bench_returns = fund_analytics_service.compute_returns(benchmark_series)
            bench_window = bench_returns["windows"].get("3y")
            if bench_window and bench_window["available"]:
                benchmark_cagr_3y = bench_window["cagr_pct"]

    return FundMetrics(
        cagr_3y=cagr_3y,
        max_drawdown_pct=max_dd,
        recovered=recovered,
        recovery_duration_days=recovery_days,
        rolling_spread_pct=rolling_spread,
        benchmark_cagr_3y=benchmark_cagr_3y,
    )


# Every threshold is a stated, fixed definition surfaced to the reader as
# `criterion` — never a hidden cutoff, and never a percentile/rank relative
# to other funds (no cross-fund distribution data backs a percentile claim
# — see PERSONAS in the frontend's constants.ts for the same rule).
FILTERS: dict[str, DiscoveryFilter] = {
    "defensive_drawdown": DiscoveryFilter(
        key="defensive_drawdown",
        label="Defensive Drawdown Profile",
        criterion="Historical maximum drawdown of 20% or less.",
        predicate=lambda m: m.max_drawdown_pct is not None and m.max_drawdown_pct >= -20,
        metric_of=lambda m: m.max_drawdown_pct,
        metric_label="Max Drawdown (%)",
    ),
    "consistent_rolling": DiscoveryFilter(
        key="consistent_rolling",
        label="Consistent Rolling Returns",
        criterion="Rolling 3-year return spread (best outcome minus worst outcome) of 15 percentage points or less.",
        predicate=lambda m: m.rolling_spread_pct is not None and m.rolling_spread_pct <= 15,
        metric_of=lambda m: m.rolling_spread_pct,
        metric_label="Rolling 3Y Spread (pp)",
    ),
    "fast_recovery": DiscoveryFilter(
        key="fast_recovery",
        label="Quick Historical Recovery",
        criterion="Recovered from its largest historical drawdown within 180 days.",
        predicate=lambda m: m.recovered is True and m.recovery_duration_days is not None and m.recovery_duration_days <= 180,
        metric_of=lambda m: float(m.recovery_duration_days) if m.recovery_duration_days is not None else None,
        metric_label="Recovery Days",
    ),
    "benchmark_divergence": DiscoveryFilter(
        key="benchmark_divergence",
        label="Notable Benchmark Divergence",
        criterion="3-year annualised return at least 5 percentage points away from its own benchmark's 3-year return, in either direction.",
        predicate=lambda m: m.cagr_3y is not None
        and m.benchmark_cagr_3y is not None
        and abs(m.cagr_3y - m.benchmark_cagr_3y) >= 5,
        metric_of=lambda m: (m.cagr_3y - m.benchmark_cagr_3y) if m.cagr_3y is not None and m.benchmark_cagr_3y is not None else None,
        metric_label="CAGR vs Benchmark (pp)",
    ),
}


def list_filters() -> list[dict]:
    return [{"key": f.key, "label": f.label, "criterion": f.criterion} for f in FILTERS.values()]


def discover_funds(db: Session, filter_key: str) -> dict | None:
    """None means the filter key isn't recognized (the caller 404s);
    otherwise always returns a result, possibly with an empty item list."""
    filt = FILTERS.get(filter_key)
    if filt is None:
        return None

    schemes = fund_repository.list_schemes(db, limit=SCAN_CAP)
    items = []
    scanned = 0
    for scheme in schemes:
        scanned += 1
        metrics = _compute_fund_metrics(db, scheme)
        if metrics is None:
            continue
        if filt.predicate(metrics):
            items.append(
                {
                    "id": scheme.id,
                    "scheme_name": scheme.name,
                    "category": scheme.category,
                    "amc_name": scheme.fund_family.amc.name,
                    "metric_label": filt.metric_label,
                    "metric_value": round(filt.metric_of(metrics), 2),
                }
            )
            if len(items) >= RESULT_CAP:
                break

    return {
        "filter": filt.key,
        "label": filt.label,
        "criterion": filt.criterion,
        "funds_scanned": scanned,
        "items": items,
    }
