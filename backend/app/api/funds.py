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

from app.core.config import get_settings
from app.core.database import get_db
from app.models.reference import Scheme, SchemeVariant
from app.repositories import fund_repository
from app.schemas.funds import (
    DrawdownResponse,
    FundDetail,
    FundSummary,
    IntelligenceResponse,
    ReturnsResponse,
    RiskResponse,
    RollingReturnsResponse,
    VariantSummary,
)
from app.services import fund_analytics_service

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
