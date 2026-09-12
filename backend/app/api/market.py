"""General market reference data — Phase 10.

GET /api/market/regimes (Section 20's listed endpoint): the raw
market_regimes reference table, with no fund attached. Fund-specific
behaviour within each regime is GET /api/funds/{id}/market-regimes in
app/api/funds.py, since that needs a NAV series to compare against.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.repositories import market_regime_repository
from app.schemas.market_regime import MarketRegimeSummary

router = APIRouter(prefix="/api/market", tags=["market"])


@router.get("/regimes", response_model=list[MarketRegimeSummary])
def list_market_regimes(db: Session = Depends(get_db)) -> list[MarketRegimeSummary]:
    return [
        MarketRegimeSummary(
            id=r.id, name=r.name, regime_type=r.regime_type, start_date=r.start_date, end_date=r.end_date
        )
        for r in market_regime_repository.list_regimes(db)
    ]
