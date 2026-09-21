"""Fund research API — Phase 5.

Structured, validated JSON only; SQLAlchemy models never returned directly
(Section 20). Analytics numbers are computed on demand from nav_history/
benchmark_history via app/services/fund_analytics_service.py, which wraps
the deterministic analytics/ engine — this endpoint layer contains no
financial arithmetic of its own.

/risk is the one exception: it first checks for a precomputed row set in
fund_metrics (data_pipeline/orchestration/precompute_metrics.py runs
nightly) and only falls back to a live computation on a cache miss. That
module's docstring explains why /returns and /drawdown still stay live —
their response shapes (per-window availability/dates; drawdown's own date
and boolean fields) don't fit fund_metrics' flat, numeric-only rows
without lossy encoding, whereas /risk's shape does, losslessly.
"""
from __future__ import annotations

from datetime import date as _date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from analytics.alpha_beta import beta as compute_beta
from analytics.returns import returns_series
from app.core.config import get_settings
from app.core.database import get_db
from app.models.reference import Scheme, SchemeVariant
from app.repositories import fund_repository, market_regime_repository, portfolio_repository
from data_pipeline.orchestration.lazy_nav_backfill import ensure_nav_history
from data_pipeline.orchestration.precompute_metrics import RISK_OPTIONAL_FIELDS, RISK_REQUIRED_FIELDS
from app.schemas.funds import (
    CategoryBenchmarkResponse,
    DiscoverFundsResponse,
    DiscoveryFiltersResponse,
    DrawdownResponse,
    FundDetail,
    FundListResponse,
    FundSummary,
    IntelligenceResponse,
    NavHistoryResponse,
    ReturnsResponse,
    RiskResponse,
    RollingReturnSeriesResponse,
    RollingReturnsResponse,
    VariantSummary,
)
from app.schemas.ai_explanation import AISummaryResponse
from app.schemas.market_regime import MarketRegimeBehaviorResponse
from app.schemas.overlap import OverlapResponse
from app.schemas.portfolio import PortfolioResponse
from app.schemas.stress_test import StressTestResponse
from app.services import (
    ai_explanation_service,
    category_analytics_service,
    discovery_service,
    fund_analytics_service,
    market_regime_service,
    overlap_service,
    portfolio_intelligence_service,
    stress_test_service,
)

router = APIRouter(prefix="/api/funds", tags=["funds"])


def _variant_summary(db: Session, variant: SchemeVariant) -> VariantSummary:
    latest = fund_repository.get_latest_nav(db, variant.id)
    return VariantSummary(
        id=variant.id,
        plan=variant.plan,
        option=variant.option,
        amfi_code=variant.amfi_code,
        isin=variant.isin,
        latest_nav=float(latest.nav) if latest else None,
        latest_nav_date=latest.date if latest else None,
    )


def _fund_summary(scheme: Scheme) -> FundSummary:
    return FundSummary(
        id=scheme.id,
        scheme_name=scheme.name,
        category=scheme.category,
        amc_name=scheme.fund_family.amc.name,
        fund_family_name=scheme.fund_family.name,
        benchmark_name=scheme.benchmark.name if scheme.benchmark else None,
    )


def _fund_detail(db: Session, scheme: Scheme) -> FundDetail:
    return FundDetail(
        **_fund_summary(scheme).model_dump(),
        variants=[_variant_summary(db, v) for v in scheme.variants],
    )


def _resolve_scheme(db: Session, fund_id: int) -> Scheme:
    scheme = fund_repository.get_scheme(db, fund_id)
    if scheme is None:
        raise HTTPException(status_code=404, detail=f"Fund {fund_id} not found")
    return scheme


def _resolve_variant(db: Session, scheme: Scheme, plan: str, option: str) -> SchemeVariant:
    variant = fund_repository.get_variant(db, scheme.id, plan, option)
    if variant is None:
        raise HTTPException(
            status_code=404,
            detail=f"Fund {scheme.id} has no {plan}/{option} variant",
        )
    # First-view lazy backfill (Phase 15): fetches this variant's full NAV
    # history from mfapi.in the first time it's ever requested, then
    # persists it — every request after that is a no-op here. Never raises:
    # a failed attempt still lets the page render with whatever NAV history
    # already exists, and simply retries on the next view.
    ensure_nav_history(db, variant)
    return variant


def _benchmark_series(db: Session, scheme: Scheme):
    if scheme.benchmark_id is None:
        return None
    return fund_repository.get_benchmark_series(db, scheme.benchmark_id)


def _risk_from_cache(db: Session, variant: SchemeVariant) -> dict | None:
    """Today's precomputed risk metrics for `variant`, reconstructed into
    the exact shape compute_risk returns — without touching raw
    nav_history at all. None on a cache miss (not yet precomputed today,
    or risk genuinely unavailable for this fund), in which case the
    caller falls back to a live computation exactly as before."""
    cached = fund_repository.get_cached_metrics(
        db, variant.id, RISK_REQUIRED_FIELDS + RISK_OPTIONAL_FIELDS, _date.today(), get_settings().analytics_version
    )
    if not all(field in cached for field in RISK_REQUIRED_FIELDS):
        return None
    return {
        "available": True,
        "reason": None,
        "observations_used": int(cached["observations_used"]),
        "risk_free_rate_pct": round(get_settings().risk_free_rate * 100, 4),
        "volatility_pct": cached["volatility_pct"],
        "downside_deviation_pct": cached["downside_deviation_pct"],
        "sharpe_ratio": cached.get("sharpe_ratio"),
        "sortino_ratio": cached.get("sortino_ratio"),
        "upside_capture_pct": cached.get("upside_capture_pct"),
        "downside_capture_pct": cached.get("downside_capture_pct"),
        "beta": cached.get("beta"),
        "jensen_alpha_pct": cached.get("jensen_alpha_pct"),
    }


@router.get("", response_model=FundListResponse)
def list_funds(
    search: str | None = Query(
        None, description="Scheme name search — substring match, tolerant of minor typos"
    ),
    category: str | None = Query(None, description="Case-insensitive substring match, e.g. 'Large Cap'. Comma-separated terms OR together, e.g. 'Small Cap,Mid Cap'."),
    amc: str | None = Query(None, description="Case-insensitive substring match on AMC name"),
    limit: int = Query(
        50, gt=0, le=2000,
        description="Max funds to return. The 2000 ceiling covers 'give me every fund' "
        "callers (a plan/option selector, say) as well as paged browsing.",
    ),
    offset: int = Query(0, ge=0, description="Number of funds to skip, for paging"),
    db: Session = Depends(get_db),
) -> dict:
    # One extra row past `limit` (never returned to the caller) reveals
    # whether a next page exists, without a separate COUNT(*) query over
    # what's now a 1,800+ row table.
    schemes = fund_repository.list_schemes(
        db, search=search, category=category, amc_name=amc, limit=limit + 1, offset=offset
    )
    has_more = len(schemes) > limit
    return {"items": [_fund_summary(s) for s in schemes[:limit]], "has_more": has_more}


@router.get("/count")
def count_funds(
    search: str | None = Query(
        None, description="Scheme name search — substring match, tolerant of minor typos"
    ),
    category: str | None = Query(None, description="Case-insensitive substring match, e.g. 'Large Cap'. Comma-separated terms OR together, e.g. 'Small Cap,Mid Cap'."),
    amc: str | None = Query(None, description="Case-insensitive substring match on AMC name"),
    db: Session = Depends(get_db),
) -> dict:
    """A lightweight total count — e.g. the dashboard's "Funds Covered"
    tile — without downloading every fund just to read len(list)."""
    return {"count": fund_repository.count_schemes(db, search=search, category=category, amc_name=amc)}


@router.get("/discover/filters", response_model=DiscoveryFiltersResponse)
def get_discovery_filters() -> dict:
    """The catalog of named research filters (product-upgrade brief
    Section 8) — each with its exact, fixed definition, never a hidden
    threshold or a ranking."""
    return {"filters": discovery_service.list_filters()}


@router.get("/discover", response_model=DiscoverFundsResponse)
def get_discovered_funds(
    filter: str = Query(..., description="A filter key from GET /api/funds/discover/filters"),
    db: Session = Depends(get_db),
) -> dict:
    """Funds matching one named research filter, live-computed and capped
    for cost (see discovery_service.py) — an "Explore Research" module,
    not a ranking. 404s on an unrecognized filter key rather than
    silently returning an empty result."""
    result = discovery_service.discover_funds(db, filter)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Unknown discovery filter: {filter}")
    return result


@router.get("/{fund_id}", response_model=FundDetail)
def get_fund(fund_id: int, db: Session = Depends(get_db)) -> FundDetail:
    scheme = _resolve_scheme(db, fund_id)
    return _fund_detail(db, scheme)


@router.get("/{fund_id}/returns", response_model=ReturnsResponse)
def get_fund_returns(
    fund_id: int,
    plan: Literal["direct", "regular"] = "direct",
    option: Literal["growth", "idcw"] = "growth",
    db: Session = Depends(get_db),
) -> dict:
    scheme = _resolve_scheme(db, fund_id)
    variant = _resolve_variant(db, scheme, plan, option)
    nav = fund_repository.get_nav_series(db, variant.id)
    return fund_analytics_service.compute_returns(nav, variant.nav_history_backfilled_at is not None)


@router.get("/{fund_id}/nav-history", response_model=NavHistoryResponse)
def get_fund_nav_history(
    fund_id: int,
    plan: Literal["direct", "regular"] = "direct",
    option: Literal["growth", "idcw"] = "growth",
    db: Session = Depends(get_db),
) -> dict:
    scheme = _resolve_scheme(db, fund_id)
    variant = _resolve_variant(db, scheme, plan, option)
    nav = fund_repository.get_nav_series(db, variant.id)
    benchmark = _benchmark_series(db, scheme)
    return {
        "variant": _variant_summary(db, variant),
        "benchmark_name": scheme.benchmark.name if scheme.benchmark else None,
        "fund_points": fund_analytics_service.series_to_points(nav),
        "benchmark_points": fund_analytics_service.series_to_points(benchmark) if benchmark is not None else [],
    }


@router.get("/{fund_id}/risk", response_model=RiskResponse)
def get_fund_risk(
    fund_id: int,
    plan: Literal["direct", "regular"] = "direct",
    option: Literal["growth", "idcw"] = "growth",
    db: Session = Depends(get_db),
) -> dict:
    scheme = _resolve_scheme(db, fund_id)
    variant = _resolve_variant(db, scheme, plan, option)

    cached = _risk_from_cache(db, variant)
    if cached is not None:
        return cached

    nav = fund_repository.get_nav_series(db, variant.id)
    benchmark = _benchmark_series(db, scheme)
    risk_free_rate = get_settings().risk_free_rate
    return fund_analytics_service.compute_risk(nav, benchmark, risk_free_rate)


@router.get("/{fund_id}/rolling-returns", response_model=RollingReturnsResponse)
def get_fund_rolling_returns(
    fund_id: int,
    plan: Literal["direct", "regular"] = "direct",
    option: Literal["growth", "idcw"] = "growth",
    window_years: float = Query(3.0, gt=0, le=10, description="Rolling window length in years, e.g. 1, 3, 5"),
    db: Session = Depends(get_db),
) -> dict:
    scheme = _resolve_scheme(db, fund_id)
    variant = _resolve_variant(db, scheme, plan, option)
    nav = fund_repository.get_nav_series(db, variant.id)
    benchmark = _benchmark_series(db, scheme)
    return fund_analytics_service.compute_rolling_returns(nav, benchmark, window_years)


@router.get("/{fund_id}/rolling-returns-series", response_model=RollingReturnSeriesResponse)
def get_fund_rolling_returns_series(
    fund_id: int,
    plan: Literal["direct", "regular"] = "direct",
    option: Literal["growth", "idcw"] = "growth",
    window: Literal["1m", "3m", "6m", "1y"] = Query("3m", description="Rolling window length"),
    lookback: Literal["1y", "3y", "5y", "10y"] = Query("1y", description="How far back the chart goes"),
    db: Session = Depends(get_db),
) -> dict:
    """Plottable rolling-return series for the bar chart — see
    RollingReturnSeriesResponse and compute_rolling_return_series. Distinct
    from /rolling-returns, which reports a distribution summary rather than
    a time series."""
    scheme = _resolve_scheme(db, fund_id)
    variant = _resolve_variant(db, scheme, plan, option)
    nav = fund_repository.get_nav_series(db, variant.id)
    return fund_analytics_service.compute_rolling_return_series(nav, window, lookback)


@router.get("/{fund_id}/drawdown", response_model=DrawdownResponse)
def get_fund_drawdown(
    fund_id: int,
    plan: Literal["direct", "regular"] = "direct",
    option: Literal["growth", "idcw"] = "growth",
    db: Session = Depends(get_db),
) -> dict:
    scheme = _resolve_scheme(db, fund_id)
    variant = _resolve_variant(db, scheme, plan, option)
    nav = fund_repository.get_nav_series(db, variant.id)
    return fund_analytics_service.compute_drawdown(nav)


@router.get("/{fund_id}/category-benchmark", response_model=CategoryBenchmarkResponse)
def get_fund_category_benchmark(fund_id: int, db: Session = Depends(get_db)) -> dict:
    """Fund vs. category-average vs. own-benchmark CAGR/drawdown/volatility
    — the "Fund → Category → Benchmark" context layer (product-upgrade
    brief Section 5). Category figures are live-computed across same-
    category funds that already have NAV history (see
    category_analytics_service.py for why this can't come from a cache);
    never triggers a live NAV backfill itself, so a category full of not-
    yet-backfilled funds degrades to `available: false` rather than a slow
    request. Benchmark figures come from this fund's own linked index."""
    scheme = _resolve_scheme(db, fund_id)
    return category_analytics_service.compute_fund_context(
        db, scheme, risk_free_rate_annual=get_settings().risk_free_rate
    )


@router.get("/{fund_id}/market-regimes", response_model=MarketRegimeBehaviorResponse)
def get_fund_market_regimes(
    fund_id: int,
    plan: Literal["direct", "regular"] = "direct",
    option: Literal["growth", "idcw"] = "growth",
    db: Session = Depends(get_db),
) -> dict:
    """Fund behaviour across defined market regimes (Phase 10). See
    MarketRegimeBehaviorResponse.methodology_note: the sample dataset's
    regimes are illustrative windows over synthetic data, not verified
    historical market classifications."""
    scheme = _resolve_scheme(db, fund_id)
    variant = _resolve_variant(db, scheme, plan, option)
    nav = fund_repository.get_nav_series(db, variant.id)
    benchmark = _benchmark_series(db, scheme)
    regimes = market_regime_repository.list_regimes(db)
    return market_regime_service.compute_regime_behavior(nav, benchmark, regimes)


@router.get("/{fund_id}/stress-test", response_model=StressTestResponse)
def get_fund_stress_test(
    fund_id: int,
    plan: Literal["direct", "regular"] = "direct",
    option: Literal["growth", "idcw"] = "growth",
    db: Session = Depends(get_db),
) -> dict:
    """Hypothetical stress scenarios (Phase 11) — see
    StressTestResponse.hypothetical_notice. Index-shock scenarios use beta
    against this fund's own benchmark; sector/market-cap scenarios use
    Phase 7's disclosed holdings exposure. Scenarios needing data this
    platform doesn't have (rates, recession, currency, inflation) are
    explicitly marked unavailable rather than estimated with invented
    sensitivities."""
    scheme = _resolve_scheme(db, fund_id)
    variant = _resolve_variant(db, scheme, plan, option)
    nav = fund_repository.get_nav_series(db, variant.id)
    benchmark = _benchmark_series(db, scheme)

    fund_beta = None
    if benchmark is not None and not benchmark.empty:
        fund_returns = returns_series(nav)
        benchmark_returns = returns_series(benchmark)
        try:
            fund_beta = compute_beta(fund_returns, benchmark_returns)
        except ValueError:
            fund_beta = None

    holdings, _ = _get_latest_holdings(db, scheme.id)
    sector_allocation = None
    market_cap_allocation = None
    if holdings:
        dna = portfolio_intelligence_service.compute_portfolio_dna(holdings)
        sector_allocation = {s["label"]: s["weight_pct"] for s in dna["sector_allocation"]}
        market_cap_allocation = {s["label"]: s["weight_pct"] for s in dna["market_cap_allocation"]}

    scenarios = stress_test_service.run_stress_test(fund_beta, sector_allocation, market_cap_allocation)
    return {
        "fund_beta": round(fund_beta, 4) if fund_beta is not None else None,
        "scenarios": scenarios,
    }


@router.get("/{fund_id}/ai-summary", response_model=AISummaryResponse)
def get_fund_ai_summary(
    fund_id: int,
    plan: Literal["direct", "regular"] = "direct",
    option: Literal["growth", "idcw"] = "growth",
    db: Session = Depends(get_db),
) -> dict:
    """AI Explanation Layer (Phase 12). The AI computes nothing — it only
    ever sees the `facts_used` dict below (built entirely from the other
    already-computed, already-tested endpoints on this router) and every
    number in its output is verified against those same facts before
    being returned. See ai_explanation_service.py's module docstring."""
    scheme = _resolve_scheme(db, fund_id)
    variant = _resolve_variant(db, scheme, plan, option)
    nav = fund_repository.get_nav_series(db, variant.id)
    benchmark = _benchmark_series(db, scheme)
    risk_free_rate = get_settings().risk_free_rate

    returns = fund_analytics_service.compute_returns(nav, variant.nav_history_backfilled_at is not None)
    risk = fund_analytics_service.compute_risk(nav, benchmark, risk_free_rate)
    drawdown = fund_analytics_service.compute_drawdown(nav)
    rolling = fund_analytics_service.compute_rolling_returns(nav, benchmark, 3.0)

    regimes = market_regime_repository.list_regimes(db)
    regime_behavior = market_regime_service.compute_regime_behavior(nav, benchmark, regimes) if regimes else None

    holdings, _ = _get_latest_holdings(db, scheme.id)
    portfolio_dna = portfolio_intelligence_service.compute_portfolio_dna(holdings) if holdings else None

    facts = ai_explanation_service.build_fund_facts(
        fund_name=scheme.name,
        category=scheme.category,
        amc_name=scheme.fund_family.amc.name,
        benchmark_name=scheme.benchmark.name if scheme.benchmark else None,
        returns=returns,
        risk=risk,
        drawdown=drawdown,
        rolling=rolling,
        regime_behavior=regime_behavior,
        portfolio_dna=portfolio_dna,
    )
    return ai_explanation_service.generate_fund_summary(facts)


@router.get("/{fund_id}/portfolio", response_model=PortfolioResponse)
def get_fund_portfolio(fund_id: int, db: Session = Depends(get_db)) -> dict:
    """Portfolio DNA + concentration (Phase 7). Scheme-level, not
    variant-specific — holdings are identical across a scheme's plan/
    option variants."""
    scheme = _resolve_scheme(db, fund_id)
    holdings, snapshot = _get_latest_holdings(db, scheme.id)
    if snapshot is None:
        result = portfolio_intelligence_service.compute_portfolio_dna([])
        result["as_of_date"] = None
        result["source_name"] = None
        return result

    source = portfolio_repository.get_snapshot_source(db, snapshot)
    result = portfolio_intelligence_service.compute_portfolio_dna(holdings)
    result["as_of_date"] = snapshot.as_of_date
    result["source_name"] = source.name if source else None
    return result


def _get_latest_holdings(db: Session, scheme_id: int):
    snapshot = portfolio_repository.get_latest_snapshot(db, scheme_id)
    if snapshot is None:
        return [], None
    return portfolio_repository.get_holdings(db, snapshot.id), snapshot


@router.get("/{fund_id}/overlap", response_model=OverlapResponse)
def get_fund_overlap(fund_id: int, compare_to: int = Query(..., description="Fund id to compare against"),
                      db: Session = Depends(get_db)) -> dict:
    """Pairwise fund overlap (Phase 8). Scheme-level, like /portfolio.
    Return correlation uses each scheme's direct/growth NAV series (or the
    first available variant) — see fund_repository.get_default_variant."""
    if fund_id == compare_to:
        raise HTTPException(status_code=400, detail="Cannot compare a fund to itself")

    scheme_a = _resolve_scheme(db, fund_id)
    scheme_b = _resolve_scheme(db, compare_to)

    holdings_a, snapshot_a = _get_latest_holdings(db, scheme_a.id)
    holdings_b, snapshot_b = _get_latest_holdings(db, scheme_b.id)

    variant_a = fund_repository.get_default_variant(db, scheme_a.id)
    variant_b = fund_repository.get_default_variant(db, scheme_b.id)
    returns_a = returns_series(fund_repository.get_nav_series(db, variant_a.id)) if variant_a else None
    returns_b = returns_series(fund_repository.get_nav_series(db, variant_b.id)) if variant_b else None

    result = overlap_service.compute_overlap(holdings_a, holdings_b, returns_a, returns_b)
    result["fund_a"] = {"id": scheme_a.id, "scheme_name": scheme_a.name}
    result["fund_b"] = {"id": scheme_b.id, "scheme_name": scheme_b.name}
    result["as_of_date_a"] = snapshot_a.as_of_date if snapshot_a else None
    result["as_of_date_b"] = snapshot_b.as_of_date if snapshot_b else None
    return result


@router.get("/{fund_id}/intelligence", response_model=IntelligenceResponse)
def get_fund_intelligence(
    fund_id: int,
    plan: Literal["direct", "regular"] = "direct",
    option: Literal["growth", "idcw"] = "growth",
    db: Session = Depends(get_db),
) -> dict:
    scheme = _resolve_scheme(db, fund_id)
    variant = _resolve_variant(db, scheme, plan, option)
    nav = fund_repository.get_nav_series(db, variant.id)
    benchmark = _benchmark_series(db, scheme)
    risk_free_rate = get_settings().risk_free_rate

    return {
        "fund": _fund_detail(db, scheme),
        "variant": _variant_summary(db, variant),
        "returns": fund_analytics_service.compute_returns(nav, variant.nav_history_backfilled_at is not None),
        "risk": fund_analytics_service.compute_risk(nav, benchmark, risk_free_rate),
        "rolling_3y": fund_analytics_service.compute_rolling_returns(nav, benchmark, 3.0),
        "drawdown": fund_analytics_service.compute_drawdown(nav),
    }
