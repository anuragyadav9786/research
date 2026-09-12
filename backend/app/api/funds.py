"""Fund research API — Phase 5.

Structured, validated JSON only; SQLAlchemy models never returned directly
(Section 20). Analytics numbers are computed on demand from nav_history/
benchmark_history via app/services/fund_analytics_service.py, which wraps
the deterministic analytics/ engine — this endpoint layer contains no
financial arithmetic of its own.

Known limitation (documented, not hidden): metrics are computed live on
every request rather than precomputed into fund_metrics/analytics_runs
(Section 31's "precompute, don't recompute" guidance). For the current
data volumes (a handful of sample schemes) this is fast enough; wiring up
precomputation is a follow-up once real ingestion brings in the full fund
universe.
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from analytics.alpha_beta import beta as compute_beta
from analytics.returns import returns_series
from app.core.config import get_settings
from app.core.database import get_db
from app.models.reference import Scheme, SchemeVariant
from app.repositories import fund_repository, market_regime_repository, portfolio_repository
from app.schemas.funds import (
    DrawdownResponse,
    FundDetail,
    FundSummary,
    IntelligenceResponse,
    NavHistoryResponse,
    ReturnsResponse,
    RiskResponse,
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
    return variant


def _benchmark_series(db: Session, scheme: Scheme):
    if scheme.benchmark_id is None:
        return None
    return fund_repository.get_benchmark_series(db, scheme.benchmark_id)


@router.get("", response_model=list[FundSummary])
def list_funds(
    search: str | None = Query(None, description="Case-insensitive substring match on scheme name"),
    category: str | None = Query(None, description="Exact category match, e.g. 'Equity - Large Cap'"),
    amc: str | None = Query(None, description="Case-insensitive substring match on AMC name"),
    db: Session = Depends(get_db),
) -> list[FundSummary]:
    schemes = fund_repository.list_schemes(db, search=search, category=category, amc_name=amc)
    return [_fund_summary(s) for s in schemes]


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
    return fund_analytics_service.compute_returns(nav)


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

    returns = fund_analytics_service.compute_returns(nav)
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
        "returns": fund_analytics_service.compute_returns(nav),
        "risk": fund_analytics_service.compute_risk(nav, benchmark, risk_free_rate),
        "rolling_3y": fund_analytics_service.compute_rolling_returns(nav, benchmark, 3.0),
        "drawdown": fund_analytics_service.compute_drawdown(nav),
    }
