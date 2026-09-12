"""Multi-fund Portfolio Analysis API — Phase 9.

POST /api/portfolio/analyse (Section 20's listed endpoint): given a
hypothetical set of funds and their weights in a portfolio, computes
combined ("look-through") holdings, sector/market-cap allocation,
concentration, pairwise overlap between constituents, and portfolio-level
risk/drawdown — all built from the existing single-fund analytics engines,
never a new ad hoc calculation duplicating them.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from analytics.concentration import group_weights
from analytics.returns import returns_series
from app.core.config import get_settings
from app.core.database import get_db
from app.repositories import fund_repository, portfolio_repository
from app.schemas.portfolio_analysis import PortfolioAnalyseRequest, PortfolioAnalysisResponse
from app.services import portfolio_analysis_service

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])

WEIGHT_SUM_TOLERANCE_PCT = 0.5
UNCLASSIFIED_LABEL = "unclassified"


@router.post("/analyse", response_model=PortfolioAnalysisResponse)
def analyse_portfolio(request: PortfolioAnalyseRequest, db: Session = Depends(get_db)) -> dict:
    fund_ids = [h.fund_id for h in request.holdings]
    if len(fund_ids) != len(set(fund_ids)):
        raise HTTPException(status_code=400, detail="Duplicate fund_id in holdings")

    total_weight = sum(h.weight_pct for h in request.holdings)
    if abs(total_weight - 100.0) > WEIGHT_SUM_TOLERANCE_PCT:
        raise HTTPException(
            status_code=400,
            detail=f"holdings weight_pct must sum to ~100% (got {total_weight:.2f}%)",
        )

    fund_weights_pct = {h.fund_id: h.weight_pct for h in request.holdings}
    fund_names: dict[int, str] = {}
    per_fund_security_weights: dict[int, dict[str, float]] = {}
    per_fund_sector_weights: dict[int, dict[str, float]] = {}
    per_fund_mktcap_weights: dict[int, dict[str, float]] = {}
    per_fund_returns = {}

    for fund_id in fund_ids:
        scheme = fund_repository.get_scheme(db, fund_id)
        if scheme is None:
            raise HTTPException(status_code=404, detail=f"Fund {fund_id} not found")
        fund_names[fund_id] = scheme.name

        snapshot = portfolio_repository.get_latest_snapshot(db, scheme.id)
        if snapshot is not None:
            holdings = portfolio_repository.get_holdings(db, snapshot.id)
            per_fund_security_weights[fund_id] = {h.security_name: h.weight_pct for h in holdings}
            per_fund_sector_weights[fund_id] = group_weights(
                [(h.sector_name or UNCLASSIFIED_LABEL, h.weight_pct) for h in holdings]
            )
            per_fund_mktcap_weights[fund_id] = group_weights(
                [(h.market_cap_category or UNCLASSIFIED_LABEL, h.weight_pct) for h in holdings]
            )

        variant = fund_repository.get_default_variant(db, scheme.id)
        if variant is not None:
            nav = fund_repository.get_nav_series(db, variant.id)
            if not nav.empty:
                per_fund_returns[fund_id] = returns_series(nav)

    risk_free_rate = get_settings().risk_free_rate
    return portfolio_analysis_service.compute_portfolio_analysis(
        fund_names=fund_names,
        fund_weights_pct=fund_weights_pct,
        per_fund_security_weights=per_fund_security_weights,
        per_fund_sector_weights=per_fund_sector_weights,
        per_fund_mktcap_weights=per_fund_mktcap_weights,
        per_fund_returns=per_fund_returns,
        risk_free_rate_annual=risk_free_rate,
    )
